"""
Workflow 后半段落盘：质量快照 + 经验摘要（无 LLM，便于先搭全链路再逐步换真 judge）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def build_quality_check_snapshot(root: Path, pipeline_id: str) -> dict[str, Any]:
    u_path = root / "data" / "understanding_results" / f"{pipeline_id}.json"
    o_path = root / "data" / "orchestration_results" / f"{pipeline_id}.json"
    g_path = root / "data" / "generated_pipelines" / f"{pipeline_id}.json"
    trial_path = root / "data" / "trial_runs" / pipeline_id / "trial_result.json"
    run_latest_path = root / "data" / "run_pipeline_results" / pipeline_id / "latest.json"

    u = _read_json(u_path)
    if u is None:
        raise FileNotFoundError(f"缺少理解结果: {u_path}")

    orch = _read_json(o_path)
    gen = _read_json(g_path)
    trial = _read_json(trial_path)
    run_latest = _read_json(run_latest_path)

    schema = u.get("schema_analysis") if isinstance(u.get("schema_analysis"), dict) else {}
    delta = u.get("dataset_level_delta") if isinstance(u.get("dataset_level_delta"), dict) else {}
    new_fields = [str(x) for x in (schema.get("new_fields") or []) if x is not None]
    strategies = [str(x) for x in (delta.get("transformation_strategies") or []) if x]
    key_improvements = [str(x) for x in (delta.get("key_improvements") or []) if x]

    vr: dict[str, Any] = {}
    if isinstance(orch, dict):
        cs = orch.get("constrained_search")
        if isinstance(cs, dict) and isinstance(cs.get("validation_result"), dict):
            vr = cs["validation_result"]

    insights: list[str] = []
    if new_fields:
        preview = ", ".join(new_fields[:12])
        more = "…" if len(new_fields) > 12 else ""
        insights.append(f"理解阶段标记需对齐的字段（new_fields）: {preview}{more}")
    for s in strategies[:6]:
        insights.append(f"转化策略: {s[:200]}")
    for k in key_improvements[:4]:
        insights.append(f"关键改进: {k[:200]}")
    if not insights:
        insights.append("理解结果中未抽取到额外 insight，可检查 schema_analysis / dataset_level_delta。")

    assessment = (
        str(delta.get("summary") or "").strip()
        or str(schema.get("schema_constraint") or "").strip()
        or "基于理解结果的静态快照；尚未接入采样与 judge LLM。"
    )

    gaps: list[str] = []
    god = str(delta.get("global_optimization_direction") or "").strip()
    if god:
        gaps.append(god[:500])
    qf = delta.get("quality_focus") or []
    if isinstance(qf, list):
        gaps.extend(str(x) for x in qf[:8] if x)

    trial_schema: dict[str, Any] = {}
    pilot_eval: dict[str, Any] = {}
    if isinstance(trial, dict):
        ts = trial.get("schema_check")
        if isinstance(ts, dict):
            trial_schema = ts
        pe = trial.get("llm_pilot_evaluation")
        if isinstance(pe, dict) and pe.get("present"):
            pilot_eval = pe
    miss_seed = list(trial_schema.get("missing_for_seed_top_keys") or [])
    trial_failed = bool(trial) and not trial.get("execution_ok", False)
    trial_schema_drift = bool(miss_seed)

    if trial_failed:
        insights.insert(0, f"试运行失败: {trial.get('last_error', 'unknown')}"[:300])
    elif isinstance(trial, dict) and trial.get("execution_ok") and trial_schema_drift:
        insights.insert(0, f"试运行通过但相对 seed 缺键: {', '.join(str(x) for x in miss_seed[:10])}")

    judge_for_ui: dict[str, Any] | None = None
    sample_metrics_01: dict[str, float] | None = None
    pilot_score: int | None = None
    pilot_rec: str | None = None
    pilot_dim: dict[str, int] | None = None
    if pilot_eval:
        jr = pilot_eval.get("judge_result")
        if isinstance(jr, dict):
            judge_for_ui = {
                "has_differences": jr.get("has_differences"),
                "overall_assessment": jr.get("overall_assessment"),
                "critical_insights": jr.get("critical_insights"),
                "implicit_quality_requirements": jr.get("implicit_quality_requirements"),
            }
            for x in jr.get("critical_insights") or []:
                if isinstance(x, str) and x.strip():
                    insights.insert(0, x.strip()[:400])
        sc = pilot_eval.get("scores")
        if isinstance(sc, dict):
            sample_metrics_01 = {}
            for k, v in sc.items():
                try:
                    sample_metrics_01[str(k)] = float(v)
                except (TypeError, ValueError):
                    pass
        try:
            pilot_score = int(pilot_eval.get("overall_score"))
        except (TypeError, ValueError):
            pilot_score = None
        pilot_rec = str(pilot_eval.get("recommendation") or "") or None
        pds = pilot_eval.get("dimension_scores")
        if isinstance(pds, dict):
            pilot_dim = {}
            for k, v in pds.items():
                try:
                    pilot_dim[str(k)] = max(0, min(100, int(round(float(v)))))
                except (TypeError, ValueError):
                    pass
            if not pilot_dim:
                pilot_dim = None
        if pilot_eval.get("recommendation_rationale"):
            insights.insert(0, str(pilot_eval["recommendation_rationale"])[:400])
        if judge_for_ui and str(judge_for_ui.get("overall_assessment") or "").strip():
            assessment = str(judge_for_ui["overall_assessment"]).strip()[:2000]

    resp_gaps: list[str] = gaps[:15] or ["待接入 rubric / judge 后填充"]
    fmt_gaps: list[str] = []
    if judge_for_ui and isinstance(judge_for_ui.get("implicit_quality_requirements"), dict):
        ir = judge_for_ui["implicit_quality_requirements"]
        jresp = [str(x) for x in (ir.get("response_quality_gaps") or []) if x]
        if jresp:
            resp_gaps = jresp[:15]
        fmt_gaps = [str(x) for x in (ir.get("format_rigor_gaps") or []) if x][:15]

    return {
        "pipeline_id": pipeline_id,
        "source": "quality_snapshot_v1",
        "has_differences": bool(
            new_fields or strategies or not vr.get("is_valid", True) or trial_failed or trial_schema_drift
        ),
        "overall_assessment": assessment[:2000],
        "critical_insights": insights[:20],
        "implicit_quality_requirements": {
            "response_quality_gaps": resp_gaps,
            "format_rigor_gaps": fmt_gaps,
        },
        "provenance": {
            "understanding_path": f"data/understanding_results/{pipeline_id}.json",
            "orchestration_path": f"data/orchestration_results/{pipeline_id}.json",
            "generated_pipeline_path": f"data/generated_pipelines/{pipeline_id}.json",
            "has_generated_pipeline": gen is not None,
            "orchestration_validation_ok": bool(vr.get("is_valid")) if vr else None,
            "trial_run_path": f"data/trial_runs/{pipeline_id}/trial_result.json",
            "trial_run_found": trial is not None,
            "trial_execution_ok": trial.get("execution_ok") if trial else None,
            "pipeline_run_latest_path": f"data/run_pipeline_results/{pipeline_id}/latest.json",
            "pipeline_run_latest": run_latest,
        },
        "trial_run": {
            "present": trial is not None,
            "execution_ok": trial.get("execution_ok") if trial else None,
            "schema_check": trial.get("schema_check") if trial else None,
            "reflux_recommendation": trial.get("reflux_recommendation") if trial else None,
            "step_trace": trial.get("step_trace") if trial else None,
            "data_samples": trial.get("data_samples") if trial else None,
        },
        "llm_pilot_evaluation": pilot_eval if pilot_eval else None,
        "judge_result": judge_for_ui,
        "pilot_overall_score": pilot_score,
        "pilot_recommendation": pilot_rec,
        "pilot_dimension_scores": pilot_dim,
        "sample_metrics_0_1": sample_metrics_01,
        "meta": {"created_at": _iso(), "note": "含试运行与可选 Pilot LLM 评估；judge_result 对齐前端 QualityCheck / JudgeResult"},
    }


def build_experience_snapshot(root: Path, pipeline_id: str) -> dict[str, Any]:
    qc_path = root / "data" / "quality_check_results" / f"{pipeline_id}.json"
    o_path = root / "data" / "orchestration_results" / f"{pipeline_id}.json"
    u_path = root / "data" / "understanding_results" / f"{pipeline_id}.json"
    trial_path = root / "data" / "trial_runs" / pipeline_id / "trial_result.json"

    qc = _read_json(qc_path)
    orch = _read_json(o_path)
    u = _read_json(u_path)
    trial = _read_json(trial_path)

    vr: dict[str, Any] = {}
    if isinstance(orch, dict):
        cs = orch.get("constrained_search")
        if isinstance(cs, dict) and isinstance(cs.get("validation_result"), dict):
            vr = cs["validation_result"]
    valid = bool(vr.get("is_valid")) if vr else True

    parts: list[str] = []
    parts.append("编排 DAG 校验" + ("通过。" if valid else "未通过，下一轮应优先修复数据流或算子选择。"))
    if isinstance(trial, dict):
        if trial.get("execution_ok"):
            parts.append("试运行：采样数据已沿实例化桩执行完成。")
        else:
            parts.append("试运行失败: " + str(trial.get("last_error") or "unknown")[:220])
        pe = trial.get("llm_pilot_evaluation") if isinstance(trial.get("llm_pilot_evaluation"), dict) else {}
        if pe.get("present"):
            for b in pe.get("experience_bullets") or []:
                if isinstance(b, str) and b.strip():
                    parts.append("Pilot 经验: " + b.strip()[:280])
            if pe.get("recommendation"):
                parts.append(
                    "Pilot 建议下一步: "
                    + str(pe.get("recommendation"))
                    + (" — " + str(pe.get("recommendation_rationale"))[:160] if pe.get("recommendation_rationale") else "")
                )
        rr = trial.get("reflux_recommendation") if isinstance(trial.get("reflux_recommendation"), dict) else {}
        for r in rr.get("reasons") or []:
            if isinstance(r, str) and r.strip():
                parts.append(r[:200])
    if isinstance(qc, dict) and qc.get("overall_assessment"):
        parts.append(str(qc["overall_assessment"])[:500])
    if isinstance(u, dict):
        delta = u.get("dataset_level_delta")
        if isinstance(delta, dict) and delta.get("summary"):
            parts.append("数据集级摘要: " + str(delta["summary"])[:400])

    exp_text = " ".join(parts).strip()
    if len(exp_text) > 1200:
        exp_text = exp_text[:1197] + "…"

    reflux: list[str] = ["orchestration", "operator_evolution"] if not valid else ["orchestration"]
    if isinstance(qc, dict) and qc.get("has_differences"):
        reflux.append("understanding")
    if isinstance(trial, dict):
        rt = trial.get("reflux_recommendation") if isinstance(trial.get("reflux_recommendation"), dict) else {}
        for t in rt.get("targets") or []:
            if isinstance(t, str) and t.strip():
                reflux.append(t.strip())
    reflux = list(dict.fromkeys(reflux))

    return {
        "pipeline_id": pipeline_id,
        "experience_text": exp_text or "（空经验：请检查上游产物是否完整）",
        "reflux_targets": list(dict.fromkeys(reflux)),
        "source": "experience_snapshot_v1",
        "meta": {
            "created_at": _iso(),
            "inputs": {
                "quality_check_path": f"data/quality_check_results/{pipeline_id}.json",
                "quality_check_found": qc is not None,
                "trial_run_path": f"data/trial_runs/{pipeline_id}/trial_result.json",
                "trial_run_found": trial is not None,
            },
        },
    }
