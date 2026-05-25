"""
Pilot 阶段 LLM 多维度评估：输出与前端 `JudgeResult` 对齐的结构 + 流水线级经验要点 + 下一步建议。

维度与 QualityCheck / EvolutionCanvas 一致：semantic, format, diversity, info, noise, logic（0–1）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from core.llm_client import LLMClientError, chat_completion, parse_message_content_json

logger = logging.getLogger(__name__)

_DIMS = ("semantic", "format", "diversity", "info", "noise", "logic")

PILOT_JUDGE_SYSTEM = """You are a data-pipeline quality judge for DataEvolver pilot runs.
You compare **seed** reference records vs **pipeline output** records on a small sample.
Output **only one JSON object** (no markdown).

**Primary: multi-dimensional scores (0–100 integers, each axis scored independently)**

Required keys:
- "dimension_scores": object with **integers 0..100** for **each** of: semantic, format, diversity, info, noise, logic.
  - semantic: task meaning / intent alignment vs seed (instruction-following, answer relevance)
  - format: JSON keys, nesting, types, presence of expected fields vs seed shape
  - diversity: across the sample, useful variety (not copies); N/A → score by whether variety is appropriate
  - info: completeness, depth, useful detail vs seed reference level
  - noise: freedom from garbage, redundancy, contradictions, filler (**100 = clean**)
  - logic: ordering, internal consistency, coherent multi-step structure
  Do **not** assign the same number to every key unless they are genuinely equal; spread reflects real weaknesses.
- "dimension_notes": object with the **same six keys**; each value is **one short phrase** (≤90 chars) justifying that dimension’s score.
- "overall_score": integer 0..100 — holistic summary; should be consistent with dimension_scores (often near their mean ± a small adjustment for critical failures).
- "has_differences": boolean — true if output materially differs from seed in ways worth reviewing.
- "overall_assessment": one short paragraph (same language as the task text when possible).
- "critical_insights": array of 2–6 short strings (actionable).
- "implicit_quality_requirements": object with "response_quality_gaps" and "format_rigor_gaps" (arrays of short strings; can be empty).
- "experience_bullets": array of 2–5 strings — **pipeline-level** lessons for the next orchestration / evolution round (not record-level trivia).
- "recommendation": one of "proceed_full", "evolve_pipeline", "fix_execution"
  - fix_execution: broken run, empty output when seed exists, or obvious crashes / missing keys that block the task
  - evolve_pipeline: quality or schema alignment still weak; user should re-orchestrate or evolve operators before full run
  - proceed_full: sample looks good enough to run full data
- "recommendation_rationale": one short sentence.

Optional legacy key (ignored if dimension_scores is present): "scores" as floats 0..1 — the system will derive 0..1 scores from dimension_scores.

Rules:
- Record keys starting with `_` (e.g. `_validation_report`) are **diagnostic attachments**, not seed schema fields. If all seed-required keys (`instruction`, `input`, `output`, `text`, etc.) are present, **do not** treat underscore-prefixed extras as a severe format failure; score format mainly on those public keys.
- If execution failed or output sample is empty while seed is non-empty, use recommendation "fix_execution" and **low dimension_scores** (many axes ≤35).
- If execution_ok is true in the payload, the Python runner did not crash. Output that **lacks seed keys** but is otherwise structured data usually means **schema / orchestration mismatch** → use "evolve_pipeline" with **uneven** dimension_scores (e.g. format low, semantic medium), NOT "fix_execution" and NOT all zeros, unless records contain explicit infra errors (e.g. "Failed to load step metadata", tracebacks).
- Prefer honest scores; do not inflate.
- Keep strings concise for UI display."""


def _emit_usage(
    on_usage: Callable[..., None] | None,
    usage: dict[str, Any],
    model: str,
    operation: str,
) -> None:
    if not on_usage:
        return
    kw: dict[str, Any] = {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "model": model,
        "operation": operation,
    }
    for k in ("duration_ms", "request_id", "api_host"):
        if usage.get(k) is not None:
            kw[k] = usage[k]
    try:
        on_usage(**kw)
    except TypeError:
        on_usage(input_tokens=kw["input_tokens"], output_tokens=kw["output_tokens"], model=model)


def _load_understanding_snippet(root: Path, pipeline_id: str) -> dict[str, Any]:
    p = Path(root) / "data" / "understanding_results" / f"{pipeline_id}.json"
    if not p.is_file():
        return {}
    try:
        u = json.loads(p.read_text(encoding="utf-8"))
        return u if isinstance(u, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize_scores(raw: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    if not isinstance(raw, dict):
        raw = {}
    for d in _DIMS:
        v = raw.get(d)
        try:
            x = float(v)
        except (TypeError, ValueError):
            x = 0.0
        out[d] = max(0.0, min(1.0, x))
    return out


def _normalize_dimension_scores_100(raw: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    src = raw if isinstance(raw, dict) else {}
    for d in _DIMS:
        v = src.get(d)
        try:
            x = int(round(float(v)))
        except (TypeError, ValueError):
            x = 0
        out[d] = max(0, min(100, x))
    return out


def _normalize_dimension_notes(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    src = raw if isinstance(raw, dict) else {}
    for d in _DIMS:
        t = src.get(d)
        if isinstance(t, str):
            s = t.strip()
            if s:
                out[d] = s[:90] + ("…" if len(s) > 90 else "")
    return out


def _dimension_scores_from_01(scores_01: dict[str, float]) -> dict[str, int]:
    return {d: max(0, min(100, int(round(scores_01.get(d, 0.0) * 100)))) for d in _DIMS}


def _merge_dimension_and_01_scores(parsed: dict[str, Any]) -> tuple[dict[str, int], dict[str, float]]:
    """Prefer integer dimension_scores; fall back to legacy floats 0..1 in scores."""
    dim100 = _normalize_dimension_scores_100(parsed.get("dimension_scores"))
    scores_legacy = _normalize_scores(parsed.get("scores"))
    has_dim = any(dim100[d] > 0 for d in _DIMS)
    has_01 = any(scores_legacy[d] > 0 for d in _DIMS)
    if not has_dim and has_01:
        dim100 = _dimension_scores_from_01(scores_legacy)
    scores_01 = {d: dim100[d] / 100.0 for d in _DIMS}
    return dim100, scores_01


def _clamp_recommendation(
    s: str,
    *,
    execution_ok: bool,
    has_output: bool,
    has_seed: bool,
) -> str:
    t = (s or "").strip().lower()
    if t in ("proceed_full", "evolve_pipeline", "fix_execution"):
        rec = t
    else:
        rec = "evolve_pipeline"
    if not execution_ok:
        return "fix_execution"
    if has_seed and not has_output:
        return "fix_execution"
    return rec


def run_pilot_llm_judge(
    root: Any,
    pipeline_id: str,
    trial_result: dict[str, Any],
    *,
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    """返回写入 trial 的 `llm_pilot_evaluation` 对象（不含外层的 present 等由 apply 函数补全）。"""
    root = Path(root)
    cfg = llm_config if isinstance(llm_config, dict) else {}
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key:
        return {"error": "no_api_key"}

    execution_ok = bool(trial_result.get("execution_ok"))
    ds = trial_result.get("data_samples") if isinstance(trial_result.get("data_samples"), dict) else {}
    seed = ds.get("seed") if isinstance(ds.get("seed"), list) else []
    output = ds.get("output") if isinstance(ds.get("output"), list) else []
    has_seed = bool(seed)
    has_output = bool(output)

    u = _load_understanding_snippet(root, pipeline_id)
    task_bits: list[str] = []
    prof = u.get("unified_profile") if isinstance(u.get("unified_profile"), dict) else {}
    if isinstance(prof, dict):
        for k in ("task_summary", "data_domain", "primary_objective"):
            v = prof.get(k)
            if isinstance(v, str) and v.strip():
                task_bits.append(f"{k}: {v.strip()[:800]}")
    delta = u.get("dataset_level_delta") if isinstance(u.get("dataset_level_delta"), dict) else {}
    if isinstance(delta, dict) and delta.get("summary"):
        task_bits.append(f"dataset_summary: {str(delta['summary'])[:800]}")

    user_obj: dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "execution_ok": execution_ok,
        "last_error": trial_result.get("last_error"),
        "schema_check": trial_result.get("schema_check"),
        "task_context": task_bits[:12] or ["(no understanding snippet)"],
        "seed_sample": seed[:12],
        "output_sample": output[:12],
    }
    user_prompt = json.dumps(user_obj, ensure_ascii=False, indent=2)
    if len(user_prompt) > 120_000:
        user_prompt = user_prompt[:119_000] + "\n…(truncated for judge prompt)\n"

    base_url = str(cfg["base_url"])
    model = str(cfg["model"])
    temperature = float(cfg.get("temperature", 0.15))
    max_tokens = min(4096, int(cfg.get("max_tokens", 2048)))
    timeout_sec = float(cfg.get("timeout", 180))

    parsed: dict[str, Any] = {}
    last_err: Exception | None = None
    prompt = user_prompt
    for attempt in range(max_retries + 1):
        try:
            resp = chat_completion(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=[
                    {"role": "system", "content": PILOT_JUDGE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
                json_mode=True,
            )
            parsed, usage = parse_message_content_json(resp)
            if not isinstance(parsed, dict):
                raise ValueError("judge response not object")
            _emit_usage(on_usage, usage, model, "pilot.llm_judge")
            break
        except (LLMClientError, json.JSONDecodeError, TypeError, ValueError) as e:
            last_err = e
            logger.warning("pilot judge attempt %s failed: %s", attempt + 1, e)
            prompt = (
                user_prompt
                + "\n\nReturn one valid JSON object with dimension_scores (0-100 ints), "
                "dimension_notes (six short strings), and all other required keys. No markdown."
            )
    if not parsed:
        return {
            "error": "llm_failed",
            "detail": str(last_err) if last_err else "unknown",
        }

    dimension_scores, scores = _merge_dimension_and_01_scores(parsed)
    dim_notes = _normalize_dimension_notes(parsed.get("dimension_notes"))
    try:
        overall = int(parsed.get("overall_score"))
    except (TypeError, ValueError):
        overall = int(round(sum(dimension_scores.values()) / max(len(dimension_scores), 1)))
    overall = max(0, min(100, overall))

    rec = _clamp_recommendation(
        str(parsed.get("recommendation") or ""),
        execution_ok=execution_ok,
        has_output=has_output,
        has_seed=has_seed,
    )
    if overall < 50 and rec == "proceed_full":
        rec = "evolve_pipeline"
    if overall >= 78 and execution_ok and has_output and rec == "fix_execution":
        rec = "evolve_pipeline"

    judge_result: dict[str, Any] = {
        "has_differences": bool(parsed.get("has_differences", True)),
        "overall_assessment": str(parsed.get("overall_assessment") or "").strip() or "（无评估摘要）",
        "critical_insights": [str(x) for x in (parsed.get("critical_insights") or []) if isinstance(x, str)][:10],
        "implicit_quality_requirements": parsed.get("implicit_quality_requirements")
        if isinstance(parsed.get("implicit_quality_requirements"), dict)
        else {"response_quality_gaps": [], "format_rigor_gaps": []},
    }
    iq = judge_result["implicit_quality_requirements"]
    if not isinstance(iq, dict):
        iq = {}
    judge_result["implicit_quality_requirements"] = {
        "response_quality_gaps": [str(x) for x in (iq.get("response_quality_gaps") or []) if x][:20],
        "format_rigor_gaps": [str(x) for x in (iq.get("format_rigor_gaps") or []) if x][:20],
    }

    exp = [str(x) for x in (parsed.get("experience_bullets") or []) if isinstance(x, str)][:8]

    return {
        "dimension_scores": dimension_scores,
        "dimension_notes": dim_notes,
        "scores": scores,
        "overall_score": overall,
        "recommendation": rec,
        "recommendation_rationale": str(parsed.get("recommendation_rationale") or "").strip()[:500],
        "judge_result": judge_result,
        "experience_bullets": exp,
    }


def apply_pilot_llm_judge(
    root: Any,
    pipeline_id: str,
    trial_result: dict[str, Any],
    *,
    llm_config: dict[str, Any] | None,
    on_usage: Callable[..., None] | None,
    enabled: bool = True,
) -> None:
    """就地写入 trial_result['llm_pilot_evaluation']。"""
    lc = llm_config if isinstance(llm_config, dict) else {}
    if not enabled:
        trial_result["llm_pilot_evaluation"] = {
            "present": False,
            "skipped_reason": "disabled",
        }
        return
    if not str(lc.get("api_key") or "").strip():
        trial_result["llm_pilot_evaluation"] = {
            "present": False,
            "skipped_reason": "no_api_key",
            "hint": "配置 API Key 后重跑 trial 或执行 run_pipeline.py --mode pilot 以启用 LLM 评估。",
        }
        return

    inner = run_pilot_llm_judge(
        root,
        pipeline_id,
        trial_result,
        llm_config=lc,
        on_usage=on_usage,
    )
    if inner.get("error") == "no_api_key":
        trial_result["llm_pilot_evaluation"] = {"present": False, "skipped_reason": "no_api_key"}
        return
    if "error" in inner:
        trial_result["llm_pilot_evaluation"] = {
            "present": False,
            "skipped_reason": "llm_error",
            "detail": inner.get("detail") or inner.get("error"),
        }
        return

    trial_result["llm_pilot_evaluation"] = {
        "present": True,
        "skipped_reason": None,
        "dimension_scores": inner.get("dimension_scores"),
        "dimension_notes": inner.get("dimension_notes"),
        "scores": inner.get("scores"),
        "overall_score": inner.get("overall_score"),
        "recommendation": inner.get("recommendation"),
        "recommendation_rationale": inner.get("recommendation_rationale"),
        "judge_result": inner.get("judge_result"),
        "experience_bullets": inner.get("experience_bullets") or [],
    }
