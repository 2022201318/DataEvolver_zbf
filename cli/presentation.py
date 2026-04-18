"""
CLI 人类可读输出：阶段说明、下一步命令、Typer 颜色。
与 `subsystems.workflow.runner` 的 STEP_ORDER 对齐。
"""

from __future__ import annotations

import os
from typing import Any

import typer

from subsystems.workflow import STEP_ORDER

def _lang() -> str:
    v = (os.environ.get("DATAEVOLVER_LANG") or "zh").strip().lower()
    return "en" if v == "en" else "zh"


def _tr(zh: str, en: str) -> str:
    return en if _lang() == "en" else zh


STEP_LABEL_ZH: dict[str, str] = {
    "understanding": "结构化理解（raw vs seed）",
    "orchestration": "算子编排（三阶段 LLM，含自动评估）",
    "assessment_refresh": "刷新 DAG 评估（仅结构+模型，不重新编排）",
    "operator_evolution": "算子进化（按需写入粗粒度算子）",
    "instantiation": "管线实例化（生成可执行桩）",
    "trial_run": "试运行（采样）",
    "pipeline_run": "全量流水线执行",
    "quality_check": "质量快照（确定性聚合）",
    "experience": "经验回流快照",
}

STEP_LABEL_EN: dict[str, str] = {
    "understanding": "Understanding (raw vs seed)",
    "orchestration": "Orchestration (3-stage LLM + auto assessment)",
    "assessment_refresh": "Refresh DAG assessment (no re-orchestrate)",
    "operator_evolution": "Operator evolution (optional)",
    "instantiation": "Instantiation (generate runnable stubs)",
    "trial_run": "Trial run (sample)",
    "pipeline_run": "Pipeline run (full)",
    "quality_check": "Quality snapshot",
    "experience": "Experience snapshot",
}

def step_label(step_key: str) -> str:
    return (STEP_LABEL_EN if _lang() == "en" else STEP_LABEL_ZH).get(step_key, step_key)

# workflow 内部 step_key → CLI 子命令名（与 app.py 注册一致）
STEP_TO_CLI: dict[str, str] = {
    "understanding": "understand",
    "orchestration": "orchestrate",
    "assessment_refresh": "validate-dag",
    "operator_evolution": "evolve-operators",
    "instantiation": "instantiate",
    "trial_run": "trial",
    "pipeline_run": "run",
    "quality_check": "quality-check",
    "experience": "experience",
}


def cli_step_invocation(pipeline_id: str, step_key: str) -> str:
    sub = STEP_TO_CLI.get(step_key, step_key)
    # 优先推荐短命令（顶层），但仍兼容 workflow 子命令
    return f"dataevolver {sub} {pipeline_id}"


# Pilot 总分低于此阈值且非 proceed_full 时，与 evolve_pipeline 一样走「先理解回流」提示
PILOT_EVOLVE_SCORE_THRESHOLD = 60

# 与 pilot_llm_judge._DIMS 顺序一致，便于终端对齐
PILOT_DIM_ORDER = ("semantic", "format", "diversity", "info", "noise", "logic")
PILOT_DIM_LABEL_ZH: dict[str, str] = {
    "semantic": "语义",
    "format": "格式",
    "diversity": "多样性",
    "info": "信息",
    "noise": "洁净",
    "logic": "逻辑",
}

PILOT_DIM_LABEL_EN: dict[str, str] = {
    "semantic": "sem",
    "format": "fmt",
    "diversity": "div",
    "info": "info",
    "noise": "clean",
    "logic": "logic",
}


def _format_pilot_dimension_scores_line(detail: dict[str, Any]) -> str | None:
    ds = detail.get("pilot_dimension_scores")
    if not isinstance(ds, dict) or not ds:
        return None
    parts: list[str] = []
    for k in PILOT_DIM_ORDER:
        if k not in ds:
            continue
        try:
            v = int(ds[k])
        except (TypeError, ValueError):
            continue
        label = (PILOT_DIM_LABEL_EN if _lang() == "en" else PILOT_DIM_LABEL_ZH).get(k, k)
        parts.append(f"{label}{v}")
    return " · ".join(parts) if parts else None


def _trial_detail_suggests_evolve(detail: dict[str, Any]) -> bool:
    if not detail:
        return False
    rec = str(detail.get("pilot_recommendation") or "").strip()
    if rec == "proceed_full":
        return False
    if rec == "evolve_pipeline":
        return True
    if rec == "fix_execution":
        return True
    score = detail.get("pilot_overall_score")
    if isinstance(score, (int, float)) and score < PILOT_EVOLVE_SCORE_THRESHOLD:
        return True
    return False


def print_next_workflow_hint(
    pipeline_id: str,
    st: dict[str, Any],
    done: bool,
    *,
    prior_step: str = "",
    prior_detail: dict[str, Any] | None = None,
    verbose: bool = False,
) -> None:
    """根据上一步结果（尤其 trial + Pilot）决定下一步文案：低分/进化建议时优先列出 understand→orchestrate 链路。"""
    title = "\n── 下一步 ──" if verbose else ("\n" + _tr("下一步", "Next"))
    typer.secho(title, fg=typer.colors.CYAN, bold=True)
    if done:
        typer.secho("  " + _tr("全部步骤已完成。", "All steps completed."), fg=typer.colors.GREEN, bold=(not verbose))
        if verbose:
            typer.echo("  " + _tr("查看 token", "Tokens") + f": dataevolver tokens {pipeline_id} --no-events")
        else:
            typer.echo("  " + _tr("Token", "Tokens") + f": dataevolver tokens {pipeline_id} --no-events")
        typer.echo("")
        return

    idx = int(st.get("step_index", 0))
    if not (0 <= idx < len(STEP_ORDER)):
        typer.echo("")
        return

    nk = STEP_ORDER[idx]
    d = prior_detail if isinstance(prior_detail, dict) else {}
    evolve = (
        prior_step == "trial_run"
        and d.get("status") == "completed"
        and _trial_detail_suggests_evolve(d)
    )
    proceed = (
        prior_step == "trial_run"
        and d.get("status") == "completed"
        and str(d.get("pilot_recommendation") or "").strip() == "proceed_full"
    )

    if evolve and nk == "pipeline_run":
        typer.secho(
            "  "
            + _tr(
                "Pilot 建议先改进管线：请把本轮评估融入结构化理解后再编排。",
                "Pilot suggests improving the pipeline first: reflux feedback into understanding, then re-orchestrate.",
            ),
            fg=typer.colors.YELLOW,
        )
        if d.get("pilot_feedback_persisted"):
            typer.echo(
                "  "
                + _tr("已写入 understanding", "Written to understanding")
                + f": data/understanding_results/{pipeline_id}.json (pilot_run_feedback)"
            )
        else:
            typer.secho(
                "  "
                + _tr(
                    "（未写入 understanding：缺少理解文件或写入失败；仍建议先 understand）",
                    "(Not written to understanding: missing file or write failed; still recommend running understand first.)",
                ),
                fg=typer.colors.YELLOW,
            )
        typer.secho(
            "\n  " + _tr("推荐顺序（每步可单独执行）:", "Recommended sequence (each step is manual):"),
            fg=typer.colors.GREEN,
            bold=True,
        )
        typer.secho(f"    1. {cli_step_invocation(pipeline_id, 'understanding')}", fg=typer.colors.WHITE, bold=True)
        typer.echo(f"    2. {cli_step_invocation(pipeline_id, 'orchestration')}")
        typer.echo("    3. " + _tr("按需", "Optional") + ": evolve-operators → instantiate → trial …")
        typer.secho("\n  " + _tr("若仍要全量执行:", "If you still want full run:"), fg=typer.colors.BLUE)
        typer.echo(f"    {cli_step_invocation(pipeline_id, 'pipeline_run')}")
        typer.echo("")
        return

    if proceed and nk == "pipeline_run":
        if verbose:
            typer.echo(f"  {_tr('将执行', 'Will run')}: {nk} — {step_label(nk)}")
            typer.secho(
                f"\n  {_tr('下一步命令', 'Next')}: {cli_step_invocation(pipeline_id, nk)}",
                fg=typer.colors.WHITE,
                bold=True,
            )
        else:
            typer.secho(f"  {cli_step_invocation(pipeline_id, nk)}", fg=typer.colors.WHITE, bold=True)
            typer.secho(
                "  "
                + _tr(
                    "（Pilot 建议 proceed_full；不满意可 understand → orchestrate …）",
                    "(Pilot suggests proceed_full; if unhappy, run understand → orchestrate …)",
                ),
                fg=typer.colors.BLUE,
            )
        if verbose:
            _print_next_step_blueprint(pipeline_id, nk)
        typer.echo("")
        return

    if verbose:
        typer.echo(f"  {_tr('将执行', 'Will run')}: {nk} — {step_label(nk)}")
        typer.secho(
            f"\n  {_tr('下一步命令', 'Next')}: {cli_step_invocation(pipeline_id, nk)}",
            fg=typer.colors.WHITE,
            bold=True,
        )
    else:
        typer.secho(f"  {cli_step_invocation(pipeline_id, nk)}", fg=typer.colors.WHITE, bold=True)
    if verbose:
        _print_next_step_blueprint(pipeline_id, nk)
    typer.echo("")


def _fmt_elapsed(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        if seconds > 0 and seconds < 0.1:
            return " · <0.1s"
        return f" · {seconds:.1f}s"
    m, s = int(seconds // 60), int(seconds % 60)
    return f" · {m}{_tr('分', 'm')}{s:02d}{_tr('秒', 's')}"


def _status_word(status: str) -> str:
    if status == "completed":
        return _tr("已完成", "completed")
    if status == "skipped":
        return _tr("已跳过", "skipped")
    return status or "ok"


def _print_advance_compact(
    pipeline_id: str,
    payload: dict[str, Any],
    *,
    elapsed_sec: float | None,
) -> None:
    step = str(payload.get("step") or "")
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    status = str(detail.get("status") or "")
    done = bool(payload.get("done"))
    st = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    label = step_label(step)
    tim = _fmt_elapsed(elapsed_sec)

    if payload.get("state_unchanged"):
        typer.secho(
            f"✓ {label}{_tr('：评估已更新（workflow 状态未改）', ': assessment updated (workflow state unchanged)')}{tim}",
            fg=typer.colors.GREEN,
        )
        print_next_workflow_hint(
            pipeline_id, st, done, prior_step=step, prior_detail=detail, verbose=False
        )
        return

    if status == "completed":
        sym, fg = "✓", typer.colors.GREEN
    elif status == "skipped":
        sym, fg = "○", typer.colors.YELLOW
    else:
        sym, fg = "·", typer.colors.WHITE

    typer.secho(
        f"{sym} {label}  {_status_word(status)}{tim}",
        fg=fg,
        bold=(status == "completed"),
    )

    if detail.get("path"):
        typer.secho(f"  {_tr('产物', 'Artifact')}: {detail.get('path')}", fg=typer.colors.WHITE)

    if step == "orchestration" and status == "completed" and "is_valid" in detail:
        iv = detail.get("is_valid")
        tf = detail.get("task_fit_satisfied")
        rec = detail.get("recommend_new_operators")
        parts = ["DAG " + (_tr("通过", "pass") if iv else _tr("未通过", "fail"))]
        if tf is True:
            parts.append(_tr("任务达标", "task OK"))
        elif tf is False:
            parts.append(_tr("任务未达标", "task NOT OK"))
        if rec is True:
            parts.append(_tr("建议新算子", "new operators"))
        typer.echo("  " + " · ".join(parts))
        nxt = list(detail.get("next_steps_for_user") or [])[:2]
        for x in nxt:
            typer.secho(f"  → {_truncate_line(str(x), 96)}", fg=typer.colors.CYAN)
        if detail.get("workflow_skip_operator_evolution"):
            typer.secho(
                "  "
                + _tr(
                    "流程: 评估通过且无需新算子，已跳过「算子进化」→ 下一步直接实例化。",
                    "Flow: assessment passed and no new operators needed; skipped operator evolution → next is instantiation.",
                ),
                fg=typer.colors.GREEN,
            )

    if step == "operator_evolution":
        if status == "skipped":
            typer.echo("  " + _tr("（本步已跳过）", "(step skipped)"))
        elif status == "completed" and detail.get("added_operators"):
            names = ", ".join(str(x) for x in (detail.get("added_operators") or [])[:4])
            typer.echo(f"  {_tr('新算子', 'New operators')}: {names}")

    if step == "instantiation" and status == "completed":
        entry = str(
            detail.get("entry_script") or f"data/generated_pipelines/{pipeline_id}/run_pipeline.py"
        )
        typer.secho(f"  {_tr('试跑', 'Try')}: python {entry} --mode pilot", fg=typer.colors.CYAN)

    if step == "trial_run" and status == "completed":
        ok = detail.get("execution_ok")
        typer.echo(f"  {_tr('采样执行', 'Sample execution')}: {_tr('成功', 'ok') if ok else _tr('失败', 'failed')}")
        if detail.get("pilot_overall_score") is not None:
            typer.secho(
                f"  Pilot {_tr('总分', 'score')}: {detail.get('pilot_overall_score')} · {detail.get('pilot_recommendation')}",
                fg=typer.colors.CYAN,
            )
            dim_line = _format_pilot_dimension_scores_line(detail)
            if dim_line:
                typer.echo(f"  {_tr('各维度', 'Dims')}(0–100): {dim_line}")
        elif detail.get("pilot_judge_skipped"):
            typer.secho(
                f"  Pilot {_tr('未评分', 'skipped')} ({detail.get('pilot_judge_skipped')})",
                fg=typer.colors.YELLOW,
            )
        if ok is False:
            typer.secho(
                f"  {_tr('重试', 'Retry')}: {cli_step_invocation(pipeline_id, 'trial_run')}",
                fg=typer.colors.YELLOW,
            )

    if step == "pipeline_run" and status == "completed":
        typer.secho(
            "  " + _tr("全量结果已落盘（见产物路径）", "Full run results saved (see artifact path)."),
            fg=typer.colors.GREEN,
        )

    if step == "assessment_refresh" and status == "completed" and "is_valid" in detail:
        iv = detail.get("is_valid")
        typer.echo(f"  DAG {_tr('评估', 'assessment')}: {_tr('通过', 'pass') if iv else _tr('未通过', 'fail')}")

    print_next_workflow_hint(
        pipeline_id, st, done, prior_step=step, prior_detail=detail, verbose=False
    )


def _rerun_cmd(pid: str, step: str) -> str:
    return f"dataevolver workflow rerun {pid} {step}"


def _chain_line_for_next(next_key: str) -> str | None:
    """默认不打印长链路；细节见状态文件或 --json。"""
    return None


def _optional_paths_for_next(pipeline_id: str, next_key: str) -> list[str]:
    """与当前「下一步」相关的短提示（一行级）。"""
    out: list[str] = []
    if next_key == "orchestration":
        out.append(
            f"手改编排 JSON 后只刷新评估（不改 state）：dataevolver workflow validate-dag {pipeline_id}"
        )
    elif next_key == "operator_evolution":
        out.append(
            f"只重评 DAG：dataevolver workflow validate-dag {pipeline_id}"
        )
    elif next_key == "instantiation":
        out.append(
            f"大改 DAG：{_rerun_cmd(pipeline_id, 'orchestration')} → {cli_step_invocation(pipeline_id, 'orchestration')}"
        )
    elif next_key == "trial_run":
        out.append(
            f"重做实例化/试运行：{_rerun_cmd(pipeline_id, 'instantiation')} → {cli_step_invocation(pipeline_id, 'instantiation')}"
        )
        out.append(
            f"或一键 pilot（采样+LLM 评估，与 trial 同落盘）：python data/generated_pipelines/{pipeline_id}/run_pipeline.py --mode pilot"
        )
    elif next_key == "pipeline_run":
        out.append(
            f"重跑试运行：{_rerun_cmd(pipeline_id, 'trial_run')} → {cli_step_invocation(pipeline_id, 'trial_run')}"
        )
    elif next_key == "experience":
        out.append(
            f"从理解重来：{_rerun_cmd(pipeline_id, 'understanding')} → {cli_step_invocation(pipeline_id, 'understanding')}"
        )
    return out


def _truncate_line(s: str, max_len: int = 140) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _print_pipeline_assessment_detail(pipeline_id: str, detail: dict[str, Any]) -> None:
    """编排完成或 validate-dag 刷新后的评估展示（终端精简版；完整内容见 assessment 文件）。"""
    if detail.get("is_valid") is None and not detail.get("assessment_path"):
        return
    iv = detail.get("is_valid")
    ic = int(detail.get("structural_issue_count") or detail.get("issue_count") or 0)
    tf = detail.get("task_fit_satisfied")
    tf_skip = bool(detail.get("task_fit_skipped"))
    reason = (detail.get("task_fit_reasoning") or "").strip()
    assess_p = detail.get("assessment_path")
    fixes = detail.get("recommended_fixes") or []
    rec_ops = detail.get("recommend_new_operators")
    nxt = list(detail.get("next_steps_for_user") or [])[:3]
    if not nxt and isinstance(fixes, list) and fixes:
        nxt = [_truncate_line(str(x)) for x in fixes[:3]]

    st = _tr("通过", "pass") if iv is True else (_tr("未通过", "fail") if iv is False else "—")
    if tf_skip:
        task_w = _tr("未评(API 跳过)", "skipped (API)")
    elif tf is True:
        task_w = _tr("达标", "OK")
    elif tf is False:
        task_w = _tr("未达标", "NOT OK")
    else:
        task_w = "—"
    if rec_ops is True:
        rec_w = _tr("是", "yes")
    elif rec_ops is False:
        rec_w = _tr("否", "no")
    else:
        rec_w = _tr("—(可 validate-dag 刷新)", "— (refresh via validate-dag)")

    fg = typer.colors.GREEN if iv is True else (typer.colors.YELLOW if iv is False else typer.colors.WHITE)
    typer.secho(
        f"\n  {_tr('评估', 'Assessment')}: {st}  ·  {_tr('结构问题', 'struct issues')} {ic}  ·  {_tr('任务', 'task')} {task_w}  ·  {_tr('建议新算子', 'new operators')} {rec_w}",
        fg=fg,
        bold=iv is False,
    )
    if reason:
        typer.echo(f"  {_tr('摘要', 'Summary')}: {_truncate_line(reason, 200)}")
    if assess_p:
        typer.echo(f"  {_tr('完整结果', 'Full')}: {assess_p}")
    if nxt:
        typer.secho("  " + _tr("建议下一步", "Suggested next") + ":", fg=typer.colors.MAGENTA)
        for x in nxt:
            typer.echo(f"    • {_truncate_line(str(x))}")


def _print_next_step_blueprint(pipeline_id: str, next_key: str) -> None:
    chain = _chain_line_for_next(next_key)
    if chain:
        typer.secho(f"\n  {_tr('链路说明', 'Flow')}: {chain}", fg=typer.colors.WHITE)
    extras = _optional_paths_for_next(pipeline_id, next_key)
    if extras:
        typer.secho("\n  " + _tr("可选路径", "Optional") + ":", fg=typer.colors.YELLOW)
        for line in extras:
            typer.echo(f"    · {line}")


def print_state_human(pipeline_id: str, st_dict: dict[str, Any], *, verbose: bool = False) -> None:
    idx = int(st_dict.get("step_index", 0))
    done_list = list(st_dict.get("steps_completed") or [])
    if not verbose:
        typer.secho(f"\n{_tr('流水线', 'Pipeline')} {pipeline_id}", fg=typer.colors.CYAN, bold=True)
        typer.echo(f"  {_tr('已完成', 'Completed')}: {len(done_list)}")
        ur = int(st_dict.get("understanding_revision", 0))
        orv = int(st_dict.get("orchestration_revision", 0))
        if ur or orv:
            typer.echo(
                "  "
                + _tr("成品版次", "Revisions")
                + f": understanding={ur} · orchestration={orv} · history=data/artifact_history/{pipeline_id}/"
            )
        if idx >= len(STEP_ORDER):
            typer.secho("  " + _tr("状态: 全部完成", "Status: complete"), fg=typer.colors.GREEN, bold=True)
        else:
            nk = STEP_ORDER[idx]
            typer.secho(
                f"  {_tr('下一命令', 'Next')}: {cli_step_invocation(pipeline_id, nk)}",
                fg=typer.colors.WHITE,
                bold=True,
            )
        typer.secho(
            "  "
            + _tr(
                f"（完整状态: dataevolver workflow --verbose state {pipeline_id}）",
                f"(Verbose state: dataevolver workflow --verbose state {pipeline_id})",
            ),
            fg=typer.colors.BLUE,
        )
        typer.echo("")
        return

    typer.secho("\n── " + _tr("Workflow 状态", "Workflow state") + " ──", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  pipeline_id: {pipeline_id}")
    typer.echo(
        "  "
        + _tr("成品版次", "Revisions")
        + f": understanding_revision={st_dict.get('understanding_revision', 0)}  "
        f"orchestration_revision={st_dict.get('orchestration_revision', 0)}  "
        f"dag_evolution_cycles={st_dict.get('dag_evolution_cycles', 0)}"
    )
    typer.echo(
        "  " + _tr("覆盖前归档索引", "Archive index") + f": data/artifact_history/{pipeline_id}/index.jsonl"
    )
    typer.echo(f"  {_tr('已完成步骤', 'Completed steps')} ({len(done_list)}): ", nl=False)
    if done_list:
        typer.secho(", ".join(done_list), fg=typer.colors.GREEN)
    else:
        typer.secho(_tr("(无)", "(none)"), fg=typer.colors.YELLOW)

    if idx >= len(STEP_ORDER):
        typer.secho("  " + _tr("状态: 全部步骤已完成。", "Status: all steps completed."), fg=typer.colors.GREEN, bold=True)
        return

    next_key = STEP_ORDER[idx]
    typer.secho(f"  {_tr('下一步将执行', 'Next step')}: ", nl=False)
    typer.secho(f"{next_key}", fg=typer.colors.MAGENTA, bold=True, nl=False)
    typer.echo(f" — {step_label(next_key)}")
    cyc = int(st_dict.get("dag_evolution_cycles") or 0)
    if next_key == "orchestration" and cyc > 0:
        typer.secho(
            "  "
            + _tr(
                f"（已完成编排↔进化闭环 {cyc} 轮；新算子已在注册表中，请重新编排）",
                f"(Completed {cyc} orchestration↔evolution cycles; new operators are in registry; please re-orchestrate.)",
            ),
            fg=typer.colors.YELLOW,
        )
    typer.secho("\n  " + _tr("推荐命令", "Recommended") + ":", fg=typer.colors.CYAN)
    typer.secho(f"    {cli_step_invocation(pipeline_id, next_key)}", fg=typer.colors.WHITE, bold=True)
    _print_next_step_blueprint(pipeline_id, next_key)
    typer.echo("")


def print_advance_human(
    pipeline_id: str,
    payload: dict[str, Any],
    *,
    verbose: bool = False,
    elapsed_sec: float | None = None,
) -> None:
    if not verbose:
        _print_advance_compact(pipeline_id, payload, elapsed_sec=elapsed_sec)
        return

    step = str(payload.get("step") or "")
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    status = str(detail.get("status") or "")
    done = bool(payload.get("done"))
    st = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    tim = _fmt_elapsed(elapsed_sec)

    typer.secho(f"\n── {_tr('本步结果', 'Step result')} ──{tim}", fg=typer.colors.CYAN, bold=True)
    if payload.get("state_unchanged"):
        typer.secho(
            "  "
            + _tr(
                "（validate-dag：评估已落盘，workflow state 未改）",
                "(validate-dag: assessment saved; workflow state unchanged)",
            ),
            fg=typer.colors.BLUE,
        )
    typer.echo(f"  {_tr('步骤', 'Step')}: {step} — {step_label(step)}")
    if status == "completed":
        typer.secho(f"  {_tr('状态', 'Status')}: {_tr('已完成', 'completed')} (completed)", fg=typer.colors.GREEN)
    elif status == "skipped":
        typer.secho(
            "  "
            + _tr("状态: 已跳过 (skipped) — 产物已存在", "Status: skipped — artifact already exists"),
            fg=typer.colors.YELLOW,
        )
        if detail.get("detail"):
            typer.echo(f"  {_tr('说明', 'Note')}: {detail.get('detail')}")
    else:
        typer.echo(f"  {_tr('状态', 'Status')}: {status or 'ok'}")

    if detail.get("path"):
        typer.echo(f"  {_tr('产物', 'Artifact')}: {detail.get('path')}")

    if step == "orchestration" and status == "completed" and "is_valid" in detail:
        _print_pipeline_assessment_detail(pipeline_id, detail)
        if detail.get("understanding_feedback_persisted"):
            if detail.get("is_valid"):
                typer.secho(
                    "  "
                    + _tr(
                        "理解结果: 已同步编排评估（本轮通过）。",
                        "Understanding: orchestration assessment synced (passed).",
                    ),
                    fg=typer.colors.GREEN,
                )
            else:
                typer.secho(
                    "  "
                    + _tr(
                        "理解结果: 已将本轮评估问题写入 understanding，下一轮 orchestrate 会在提示中携带。",
                        "Understanding: assessment issues written back; next orchestrate will include them in prompt.",
                    ),
                    fg=typer.colors.CYAN,
                )
        if detail.get("workflow_skip_operator_evolution"):
            typer.secho(
                "  "
                + _tr(
                    "流程: 评估通过且未建议新增算子，已跳过「算子进化」步，下一步直接实例化。",
                    "Flow: passed and no new operators suggested; skipped operator evolution; next is instantiation.",
                ),
                fg=typer.colors.GREEN,
            )

    if step == "assessment_refresh" and status == "completed":
        _print_pipeline_assessment_detail(pipeline_id, detail)
        if detail.get("understanding_feedback_persisted"):
            msg = (
                "  "
                + _tr("理解结果: 已同步编排评估（本轮通过）。", "Understanding: assessment synced (passed).")
                if detail.get("is_valid")
                else "  "
                + _tr(
                    "理解结果: 已根据本轮评估更新 understanding 中的反馈字段。",
                    "Understanding: feedback fields updated from latest assessment.",
                )
            )
            typer.secho(msg, fg=typer.colors.GREEN if detail.get("is_valid") else typer.colors.CYAN)

    if step == "operator_evolution":
        soft = bool(detail.get("rewind_to_orchestration_soft"))
        hard = bool(detail.get("rewind_to_orchestration"))
        if status == "skipped":
            if soft:
                typer.secho(
                    "\n  "
                    + _tr(
                        "算子进化: 已跳过（无需新算子）；请重新 orchestrate。",
                        "Operator evolution: skipped (no new operators needed); please re-orchestrate.",
                    ),
                    fg=typer.colors.YELLOW,
                )
            else:
                typer.secho(
                    "\n  "
                    + _tr(
                        "算子进化: 已跳过（评估已通过）。",
                        "Operator evolution: skipped (assessment passed).",
                    ),
                    fg=typer.colors.GREEN,
                )
        elif status == "completed":
            llm_ok = bool(detail.get("llm_generated_operators"))
            added = detail.get("added_operators") or []
            names = ", ".join(str(x) for x in added) if added else "(无)"
            reg = detail.get("registry_path") or "data/operator_registry_user.json"
            if soft:
                typer.secho(
                    "\n  "
                    + _tr(
                        "算子进化: 未写入注册表（模型无有效定义）；已指回编排，请 orchestrate。",
                        "Operator evolution: nothing written (no valid definitions); rewind to orchestration; please orchestrate.",
                    ),
                    fg=typer.colors.YELLOW,
                )
            elif hard and llm_ok:
                typer.secho(
                    "\n  "
                    + _tr(
                        f"算子进化: 已写入 {len(added)} 个算子 → {reg}：{names}；请重新 orchestrate。",
                        f"Operator evolution: wrote {len(added)} operators → {reg}: {names}; please re-orchestrate.",
                    ),
                    fg=typer.colors.GREEN,
                )
            elif hard:
                typer.secho(
                    "\n  " + _tr("算子进化: 硬回退编排，请 orchestrate。", "Operator evolution: hard rewind; please orchestrate."),
                    fg=typer.colors.YELLOW,
                )

    if step == "instantiation" and status == "completed":
        typer.secho(
            "\n  "
            + _tr(
                "实例化完成：内置算子已生成与全量执行一致的 handler 委托代码；注册表外算子在有 API Key 时会尝试 LLM 生成 run()。已写入入口脚本 run_pipeline.py。",
                "Instantiation done: built-in operators use the same handler delegation as full run; non-registry operators may be LLM-generated with API key; entry script run_pipeline.py written.",
            ),
            fg=typer.colors.CYAN,
        )
        cw = detail.get("codegen_warnings") or []
        if isinstance(cw, list) and cw:
            typer.secho("  " + _tr("说明", "Notes") + ":", fg=typer.colors.YELLOW)
            for w in cw[:6]:
                typer.echo(f"    · {w}")
        entry = str(
            detail.get("entry_script") or f"data/generated_pipelines/{pipeline_id}/run_pipeline.py"
        )
        typer.secho("\n  " + _tr("一键启动生成管线（推荐）", "Run generated pipeline (recommended)") + ":", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"    python {entry} --mode pilot")
        typer.secho(
            "      → "
            + _tr(
                "采样执行 + 默认 LLM 多维度打分与经验；结果写入 data/trial_runs/",
                "sample execution + default multi-dim LLM judge; saved to data/trial_runs/",
            ),
            fg=typer.colors.WHITE,
        )
        typer.echo(f"    python {entry} --mode full")
        typer.secho(
            "      → "
            + _tr(
                "全量执行（确认 pilot 建议 proceed_full 或你满意后再跑）",
                "full run (run after pilot suggests proceed_full or you are satisfied)",
            ),
            fg=typer.colors.WHITE,
        )
        typer.secho(
            "\n  "
            + _tr(
                "工作流递进（等价 trial 也会跑 Pilot LLM，若有 API Key）",
                "Workflow step (equivalent; trial also runs Pilot judge if API key set)",
            )
            + ":",
            fg=typer.colors.BLUE,
        )
        typer.echo(f"    {cli_step_invocation(pipeline_id, 'trial_run')}")

    if step == "trial_run" and status == "completed":
        ok = detail.get("execution_ok")
        typer.echo(f"\n  {_tr('试运行', 'Trial')} execution_ok: {ok}")
        if detail.get("pilot_overall_score") is not None:
            typer.secho(
                f"  Pilot {_tr('总分', 'score')}: {detail.get('pilot_overall_score')} · {detail.get('pilot_recommendation')}",
                fg=typer.colors.CYAN,
            )
            dim_line = _format_pilot_dimension_scores_line(detail)
            if dim_line:
                typer.echo(f"  {_tr('各维度', 'Dims')}(0–100): {dim_line}")
            if _trial_detail_suggests_evolve(detail):
                typer.secho(
                    "  "
                    + _tr(
                        "低分或建议进化：见下方「下一步」— 从 understand 回流后再 orchestrate / instantiate。",
                        "Low score or evolve suggested: see Next — reflux via understand, then orchestrate / instantiate.",
                    ),
                    fg=typer.colors.YELLOW,
                )
            elif str(detail.get("pilot_recommendation") or "").strip() == "proceed_full":
                typer.secho(
                    "  "
                    + _tr(
                        "可全量: run 或 python …/run_pipeline.py --mode full",
                        "You can run full: run / python …/run_pipeline.py --mode full",
                    ),
                    fg=typer.colors.WHITE,
                )
        elif detail.get("pilot_judge_skipped"):
            typer.secho(
                "  "
                + _tr(
                    f"Pilot 未评分: {detail.get('pilot_judge_skipped')}（配置 API Key 后可重试 trial）",
                    f"Pilot skipped: {detail.get('pilot_judge_skipped')} (set API key then retry trial)",
                ),
                fg=typer.colors.YELLOW,
            )
        if detail.get("pilot_feedback_persisted"):
            typer.echo(
                "  "
                + _tr(
                    "评估摘要已写入",
                    "Judge summary written",
                )
                + f": data/understanding_results/{pipeline_id}.json (pilot_run_feedback)"
            )
        if ok is False:
            typer.secho(
                "  "
                + _tr(
                    f"排错: 查看 data/trial_runs/{pipeline_id}/；或 {_rerun_cmd(pipeline_id, 'instantiation')}",
                    f"Debug: see data/trial_runs/{pipeline_id}/; or {_rerun_cmd(pipeline_id, 'instantiation')}",
                ),
                fg=typer.colors.YELLOW,
            )

    if step == "pipeline_run" and status == "completed":
        typer.secho("\n  " + _tr("全量执行已成功落盘。", "Full run saved successfully."), fg=typer.colors.GREEN)

    if step == "experience":
        typer.secho("\n  " + _tr("经验快照已落盘。", "Experience snapshot saved."), fg=typer.colors.WHITE)

    print_next_workflow_hint(
        pipeline_id, st, done, prior_step=step, prior_detail=detail, verbose=True
    )


def print_advance_error_human(
    pipeline_id: str,
    step_key: str,
    message: str,
    *,
    verbose: bool = False,
) -> None:
    label = step_label(step_key)
    if not verbose:
        typer.secho(f"\n✗ {label} {_tr('失败', 'failed')}", fg=typer.colors.RED, bold=True)
        typer.secho(f"  {_truncate_line(message, 220)}", fg=typer.colors.RED)
        typer.secho(f"\n  {_tr('重试', 'Retry')}: {cli_step_invocation(pipeline_id, step_key)}", fg=typer.colors.CYAN)
        typer.secho("  " + _tr("（原因与分支说明: 加 --verbose）", "(Use --verbose for details.)"), fg=typer.colors.BLUE)
        typer.echo("")
        return

    typer.secho("\n── " + _tr("本步失败", "Step failed") + " ──", fg=typer.colors.RED, bold=True)
    typer.echo(f"  {_tr('步骤', 'Step')}: {step_key} — {label}")
    typer.secho(f"  {_tr('原因', 'Reason')}: {message}", fg=typer.colors.RED)
    typer.secho(f"\n  {_tr('可重试', 'Retry')}: {cli_step_invocation(pipeline_id, step_key)}", fg=typer.colors.CYAN)
    hints = _optional_paths_for_next(pipeline_id, step_key)
    if hints:
        typer.secho("\n  " + _tr("相关路径", "Related paths") + ":", fg=typer.colors.YELLOW)
        for h in hints:
            typer.echo(f"    · {h}")
    typer.echo("")


def print_wrong_step_human(
    pipeline_id: str,
    *,
    expected_step_key: str,
    attempted_step_key: str,
) -> None:
    typer.secho("\n── " + _tr("步骤顺序不符", "Wrong step order") + " ──", fg=typer.colors.RED, bold=True)
    typer.echo(f"  {_tr('你请求执行', 'You requested')}: {attempted_step_key} — {step_label(attempted_step_key)}")
    typer.echo(f"  {_tr('当前应执行', 'Expected')}: {expected_step_key} — {step_label(expected_step_key)}")
    typer.secho(
        f"\n  {_tr('请运行', 'Run')}: {cli_step_invocation(pipeline_id, expected_step_key)}",
        fg=typer.colors.GREEN,
        bold=True,
    )
    typer.secho(
        "  "
        + _tr(
            f"若要从「{attempted_step_key}」起整段重做: {_rerun_cmd(pipeline_id, attempted_step_key)}，再执行对应步骤命令",
            f"To redo from '{attempted_step_key}': {_rerun_cmd(pipeline_id, attempted_step_key)}, then run the step command",
        ),
        fg=typer.colors.YELLOW,
    )
    typer.echo("")


def print_tokens_human(summary: dict[str, Any]) -> None:
    typer.secho("\n── LLM Token 汇总 ──", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  pipeline_id: {summary.get('pipeline_id')}")
    typer.echo(f"  账本: {summary.get('ledger_path')}")
    typer.echo(f"  事件条数: {summary.get('event_count')}")
    typer.secho(
        f"  合计: in={summary.get('total_input_tokens')}  out={summary.get('total_output_tokens')}  "
        f"total={summary.get('total_tokens')}",
        fg=typer.colors.WHITE,
        bold=True,
    )
    if summary.get("total_duration_ms"):
        typer.echo(f"  API 耗时累计(有记录的调用): {summary.get('total_duration_ms')} ms")
    tr = summary.get("time_range") or {}
    if tr.get("first_ts"):
        typer.echo(f"  时间范围: {tr.get('first_ts')} → {tr.get('last_ts')}")

    by_step = summary.get("by_workflow_step") or {}
    if by_step:
        typer.secho("\n  按 workflow 步骤:", fg=typer.colors.MAGENTA)
        for k, v in by_step.items():
            typer.echo(
                f"    • {k}: calls={v.get('api_calls')}  in={v.get('input_tokens')}  out={v.get('output_tokens')}"
            )
    by_op = summary.get("by_operation") or {}
    if len(by_op) <= 20:
        typer.secho("\n  按 operation:", fg=typer.colors.MAGENTA)
        for k, v in sorted(
            by_op.items(),
            key=lambda x: -(int(x[1].get("input_tokens", 0)) + int(x[1].get("output_tokens", 0))),
        ):
            tot = int(v.get("input_tokens", 0)) + int(v.get("output_tokens", 0))
            typer.echo(f"    • {k}: calls={v.get('api_calls')}  tokens≈{tot}")
    typer.echo("")


def print_rerun_human(result: dict[str, Any]) -> None:
    pid = str(result.get("pipeline_id", ""))
    sk = str(result.get("rerun_from", ""))
    typer.secho("\n── " + _tr("已重置 workflow", "Workflow reset") + " ──", fg=typer.colors.GREEN, bold=True)
    typer.echo(
        "  "
        + _tr(
            f"从步骤「{sk}」重新执行；step_index={result.get('step_index')}",
            f"Rerun from '{sk}'; step_index={result.get('step_index')}",
        )
    )
    typer.secho("\n  " + _tr("已处理产物", "Touched artifacts") + ":", fg=typer.colors.CYAN)
    for a in result.get("artifacts_touched") or []:
        typer.echo(f"    • {a}")
    si = int(result.get("step_index", 0))
    if 0 <= si < len(STEP_ORDER):
        nk = STEP_ORDER[si]
        typer.secho(f"\n  {_tr('下一步', 'Next')}: {cli_step_invocation(pid, nk)}", fg=typer.colors.WHITE, bold=True)
    else:
        typer.secho(
            "\n  "
            + _tr(
                "请用 `dataevolver workflow state <pipeline_id>` 查看当前进度。",
                "Use `dataevolver workflow state <pipeline_id>` to view progress.",
            ),
            fg=typer.colors.WHITE,
            bold=True,
        )
    typer.echo("")
