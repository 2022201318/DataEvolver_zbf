"""
DAG 语义层：LLM 判断管线是否满足「理解阶段」所描述的数据任务，并在进化步生成用户算子定义。

与 `dag_validator.merge_dag_validation`（结构/注册表/图论）互补；结构问题仍由规则检出。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

from core.llm_client import LLMClientError, chat_completion, parse_message_content_json
from subsystems.pipeline_orchestration.orchestration_prompts import CLI_WORKFLOW_FOR_LLM

logger = logging.getLogger(__name__)

TASK_FIT_SYSTEM = CLI_WORKFLOW_FOR_LLM + """

You are a senior ML data-pipeline reviewer for DataEvolver.
You receive: the structured understanding (task), the merged operator registry (what exists), and the proposed DAG.

Goals:
1) Judge whether this DAG can fulfill the understanding's data preparation goals when combined with **existing** registry operators.
2) Decide if **new registry operators** are truly needed, or if problems are fixable by **re-orchestration** (rewire DAG, reorder steps, pick different existing operators) only.

Rules:
1. Output **only** one JSON object, no markdown.
2. Keys:
   - "satisfies_data_task" (boolean): true only if the DAG plausibly completes the task end-to-end with existing operators.
   - "reasoning" (string): why yes/no; separate **structure/wiring** vs **semantic coverage** (same language as the task when possible).
   - "recommend_new_operators" (boolean): **true only** if a **genuine capability gap** exists that cannot be closed by re-orchestrating with existing operators. For self-loops, broken edges, wrong keys, missing outputs — set **false** and say to re-orchestrate. Do **not** recommend new operators just to "patch" fixable graph bugs.
   - "recommended_fixes" (array of short strings): concrete actions (prefer "重新编排以…" / "调整某步输出键" before "新增算子").
   - "optimization_suggestions" (array of strings): optional quality/robustness improvements (can be empty).
   - "next_steps_for_user" (array of 2–6 short strings): what the user should do next (e.g. "重新运行 orchestrate 修正环路与键", "若仍缺语义能力再运行 evolve-operators").
3. If structural checks failed, satisfies_data_task=false; recommend_new_operators is usually false unless the registry truly lacks a whole capability class.
4. Prefer fewer, clearer next steps over long prose.

**Important (DataEvolver semantics)**:
- Many steps use the same logical stream name (e.g. `records`) as both input and output to mean *map-over-records* in a **linear** chain. That is **not** a directed graph cycle.
- If `structural_checks_passed` is **true**, do **not** claim failure due to "self-loops on records" or similar; judge semantic/task fit instead.
- If `structural_checks_passed` is **false**, rely on `structural_issue_summaries` only; do not invent extra graph defects not listed there."""

OPERATOR_GEN_SYSTEM = CLI_WORKFLOW_FOR_LLM + """

You design **coarse-grained** operators for a data-pipeline registry: each operator = one **end-to-end capability**
(e.g. "align raw records to seed schema and normalize key fields"), NOT a grab-bag of micro-steps.

Context (aligned with legacy operator-level self-evolving): structured understanding and orchestration have already run. New operators here close **registry capability gaps** called out by assessment — they will be merged into `operator_registry_user.json`, then the user **re-orchestrates** so constrained search can emit real step names. Prefer **JSONL record-stream** semantics (`records` in/out) consistent with instantiated stubs.

Output **only** JSON: {"operators": [ ... ]}
Each operator object must have:
- "operator_id": short snake_case, ASCII, no dots.
- "description": one or two sentences stating the **whole responsibility** of this operator (what it achieves for the task), not implementation trivia.
- "input_keys", "output_keys": arrays of strings (often ["records"]).
- "requires_llm": boolean.
- "category": one of "bridge", "structure", "semantic", "quality", "control", "io".

Hard limits:
- **At most 2 operators.** Prefer **0 or 1** unless two clearly separate capability gaps exist.
- Do **not** emit separate operators for logging, monitoring, generic error handling, or validation unless that is the **only** missing capability for the task.
- Do not duplicate roles already covered by operators present in the current pipeline."""


def _ui_lang() -> str:
    v = (os.environ.get("DATAEVOLVER_LANG") or "zh").strip().lower()
    return "en" if v == "en" else "zh"


def _tr(zh: str, en: str) -> str:
    return en if _ui_lang() == "en" else zh


def _lang_instruction() -> str:
    if _ui_lang() == "en":
        return "\n\nLanguage requirement: Write all natural-language strings in ENGLISH."
    return "\n\n语言要求：所有自然语言字符串请使用中文。"

def _emit(
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


def _truncate(obj: Any, max_chars: int) -> str:
    s = json.dumps(obj, ensure_ascii=False, indent=2) if not isinstance(obj, str) else obj
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "\n... (truncated)"


def _summarize_pipeline(fp: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(fp, list):
        return out
    for i, step in enumerate(fp):
        if not isinstance(step, dict):
            continue
        out.append(
            {
                "step_id": step.get("step_id", f"step_{i + 1}"),
                "operator": step.get("operator"),
                "description": (step.get("description") or "")[:400],
                "input_keys": step.get("input_keys"),
                "output_keys": step.get("output_keys"),
            }
        )
    return out


def assess_pipeline_task_fit(
    *,
    understanding: dict[str, Any],
    orchestration: dict[str, Any],
    structural_valid: bool,
    structural_issues: list[dict[str, Any]],
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None,
    registry_operator_summaries: list[dict[str, Any]] | None = None,
    usage_operation: str = "orchestration.llm_task_fit",
) -> dict[str, Any]:
    """返回 llm_task_assessment：含 recommend_new_operators、next_steps_for_user 等。"""
    api_key = str(llm_config.get("api_key") or "").strip()
    if not api_key:
        return {
            "satisfied": True,
            "reasoning": _tr("未配置 API Key，已跳过任务级评估。", "No API key; task-fit assessment skipped."),
            "recommended_fixes": [],
            "optimization_suggestions": [],
            "recommend_new_operators": False,
            "next_steps_for_user": [
                _tr("配置 API Key 后重新编排以获取模型评估", "Set API key and re-orchestrate to get model assessment")
            ],
            "skipped": True,
            "skip_reason": "no_api_key",
        }

    fp = orchestration.get("final_pipeline")
    if not isinstance(fp, list):
        fp = []

    issue_lines = []
    for it in structural_issues[:24]:
        if isinstance(it, dict):
            issue_lines.append(str(it.get("description") or it))
        else:
            issue_lines.append(str(it))

    reg = registry_operator_summaries if isinstance(registry_operator_summaries, list) else []
    reg = reg[:200]

    user_obj = {
        "structural_checks_passed": structural_valid,
        "structural_issue_summaries": issue_lines,
        "merged_registry_operators": reg,
        "understanding_excerpt": _truncate(
            {
                "basic_information": understanding.get("basic_information"),
                "schema_analysis": understanding.get("schema_analysis"),
                "dataset_level_delta": understanding.get("dataset_level_delta"),
            },
            12000,
        ),
        "pipeline_steps": _summarize_pipeline(fp),
        "orchestration_meta": orchestration.get("meta"),
    }
    user_prompt = (
        "Assess whether the proposed pipeline satisfies the data preparation task implied by the understanding.\n\n"
        + json.dumps(user_obj, ensure_ascii=False, indent=2)
    )

    base_url = str(llm_config["base_url"])
    model = str(llm_config["model"])
    temperature = float(llm_config.get("temperature", 0.15))
    max_tokens = min(4096, int(llm_config.get("max_tokens", 4096)))
    timeout = max(120.0, float(llm_config.get("timeout", 180)))

    try:
        resp = chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": TASK_FIT_SYSTEM + _lang_instruction()},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_sec=timeout,
            json_mode=True,
        )
        parsed, usage = parse_message_content_json(resp)
        _emit(on_usage, usage, model, usage_operation)
        sat = bool(parsed.get("satisfies_data_task"))
        reasoning = str(parsed.get("reasoning") or "").strip() or "(无说明)"
        rec_ops = bool(parsed.get("recommend_new_operators"))
        fixes = parsed.get("recommended_fixes")
        if not isinstance(fixes, list):
            fixes = []
        fixes = [str(x) for x in fixes if str(x).strip()][:12]
        opt = parsed.get("optimization_suggestions")
        if not isinstance(opt, list):
            opt = []
        opt = [str(x) for x in opt if str(x).strip()][:12]
        nxt = parsed.get("next_steps_for_user")
        if not isinstance(nxt, list):
            nxt = []
        nxt = [str(x) for x in nxt if str(x).strip()][:8]
        if not nxt:
            if sat:
                nxt = [
                    _tr(
                        "可继续执行 evolve-operators（通常会跳过）→ instantiate → trial",
                        "Continue: evolve-operators (often skipped) → instantiate → trial",
                    )
                ]
            elif rec_ops:
                nxt = [
                    _tr(
                        "运行 evolve-operators 生成注册算子（若评估建议）",
                        "Run evolve-operators to generate registry operators (if suggested)",
                    ),
                    _tr("再 orchestrate 纳入新算子", "Then orchestrate again to include new operators"),
                ]
            else:
                nxt = [
                    _tr(
                        "重新运行 orchestrate 修正 DAG（环、键、顺序）",
                        "Re-run orchestrate to fix DAG (cycles/keys/order)",
                    ),
                    _tr("必要时 validate-dag 仅刷新评估", "If needed, use validate-dag to refresh assessment only"),
                ]
        return {
            "satisfied": sat,
            "reasoning": reasoning,
            "recommend_new_operators": rec_ops,
            "recommended_fixes": fixes,
            "optimization_suggestions": opt,
            "next_steps_for_user": nxt,
            "skipped": False,
        }
    except (LLMClientError, KeyError, TypeError, ValueError) as e:
        logger.warning("LLM task fit assessment failed: %s", e)
        return {
            "satisfied": True,
            "reasoning": _tr(
                f"任务级评估调用失败，已跳过：{e}",
                f"Task-fit assessment failed; skipped: {e}",
            ),
            "recommended_fixes": [],
            "optimization_suggestions": [],
            "recommend_new_operators": False,
            "next_steps_for_user": [
                _tr("检查 LLM 配置后重新 orchestrate", "Check LLM config then re-orchestrate")
            ],
            "skipped": True,
            "skip_reason": "llm_error",
            "error": str(e),
        }


def _sanitize_op_id(raw: str, pipeline_id: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", raw.lower().strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "custom_op"
    return f"evolved.{pipeline_id}.{s}"[:120]


def evolve_operators_via_llm(
    *,
    pipeline_id: str,
    understanding: dict[str, Any],
    orchestration: dict[str, Any],
    assessment: dict[str, Any],
    structural_issues: list[dict[str, Any]],
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None,
) -> dict[str, Any]:
    """
    根据评估理由与结构问题，让 LLM 产出算子定义 dict[name, spec]。
    若失败或为空，返回空 dict（由 runner 决定是否回退桩）。
    """
    api_key = str(llm_config.get("api_key") or "").strip()
    if not api_key:
        return {}

    reasoning = str(assessment.get("reasoning") or "")
    fixes = assessment.get("recommended_fixes") or []
    if not isinstance(fixes, list):
        fixes = []
    opt_sug = assessment.get("optimization_suggestions") or []
    if not isinstance(opt_sug, list):
        opt_sug = []
    opt_sug = [str(x) for x in opt_sug if str(x).strip()][:12]

    issue_lines = []
    for it in structural_issues[:20]:
        if isinstance(it, dict):
            issue_lines.append(str(it.get("description") or it))
        else:
            issue_lines.append(str(it))

    existing_ops = [s.get("operator") for s in _summarize_pipeline(orchestration.get("final_pipeline"))]

    user_obj = {
        "pipeline_id": pipeline_id,
        "prior_assessment_reasoning": reasoning,
        "recommended_fixes": fixes,
        "optimization_suggestions": opt_sug,
        "structural_issue_summaries": issue_lines,
        "understanding_excerpt": _truncate(understanding.get("dataset_level_delta") or understanding, 6000),
        "existing_operators_in_pipeline": existing_ops,
    }
    user_prompt = (
        "The assessment already marked recommend_new_operators=true. Propose **at most 2** registry operators, "
        "each describing one **coarse end-to-end capability** for this task. Return JSON with key \"operators\" only.\n\n"
        + json.dumps(user_obj, ensure_ascii=False, indent=2)
    )

    base_url = str(llm_config["base_url"])
    model = str(llm_config["model"])
    temperature = float(llm_config.get("temperature", 0.2))
    max_tokens = min(8192, int(llm_config.get("max_tokens", 8192)))
    timeout = max(120.0, float(llm_config.get("timeout", 180)))

    try:
        resp = chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": OPERATOR_GEN_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_sec=timeout,
            json_mode=True,
        )
        parsed, usage = parse_message_content_json(resp)
        _emit(on_usage, usage, model, "operator_evolution.llm_propose_operators")
        ops_raw = parsed.get("operators")
        if not isinstance(ops_raw, list):
            return {}

        out: dict[str, Any] = {}
        for item in ops_raw[:2]:
            if not isinstance(item, dict):
                continue
            oid = str(item.get("operator_id") or "").strip()
            if not oid:
                continue
            name = _sanitize_op_id(oid, pipeline_id)
            desc = str(item.get("description") or "LLM-proposed operator")
            ink = item.get("input_keys")
            outk = item.get("output_keys")
            if not isinstance(ink, list):
                ink = ["records"]
            if not isinstance(outk, list):
                outk = ["records"]
            ink = [str(x) for x in ink][:16]
            outk = [str(x) for x in outk][:16]
            cat = str(item.get("category") or "bridge").strip() or "bridge"
            req_llm = bool(item.get("requires_llm", True))
            out[name] = {
                "description": desc[:2000],
                "input_keys": ink,
                "output_keys": outk,
                "requires_llm": req_llm,
                "category": cat[:32],
                "source": "llm_operator_evolution",
            }
        return out
    except (LLMClientError, KeyError, TypeError, ValueError) as e:
        logger.warning("LLM operator evolution failed: %s", e)
        return {}

