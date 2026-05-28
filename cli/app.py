"""
Typer CLI：调用 `advance_workflow`；显式子命令传 `requested_step`+`step_force`，`advance`/`HTTP POST advance` 仍为线性推进。

推荐入口：`dataevolver workflow ...`（与常见 PyPI 工具「主命令 + 子命令」一致）。
未安装 editable 时，在仓库根执行: python -m cli.app --help
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import shutil
from pathlib import Path
from typing import Annotated, Optional

import typer

from cli.i18n import bootstrap_cli_language, set_cli_language, t, tr

bootstrap_cli_language()

from core.config_manager import ConfigManager
from core.cli_prefs import load_cli_prefs, save_global_cli_prefs, save_project_cli_prefs
from .step_progress import step_running_display
from .presentation import (
    STEP_LABEL_ZH,
    STEP_TO_CLI,
    step_label,
    print_advance_error_human,
    print_advance_human,
    print_rerun_human,
    print_state_human,
    print_tokens_human,
)
from subsystems.observability.token_usage_ledger import summarize_token_ledger
from subsystems.workflow import (
    STEP_ORDER,
    WorkflowStepError,
    advance_workflow,
    load_workflow_state,
    rerun_workflow_from_step,
    run_full_pipeline,
    run_pipeline_assessment_and_persist,
)


def _package_version() -> str:
    try:
        return importlib.metadata.version("dataevolver")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(_package_version())
        raise typer.Exit()


def _resolve_root(root: Optional[Path]) -> Path:
    from core.workspace import WorkspaceNotFoundError, resolve_project_root

    try:
        return resolve_project_root(root)
    except WorkspaceNotFoundError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from e


_PIPELINE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _safe_filename(name: str | None) -> str:
    if not name:
        return "upload.bin"
    return Path(name).name


def _upsert_manifest_record(root: Path, record: dict) -> None:
    manifest = root / "data" / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    if manifest.is_file():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(obj.get("pipeline_id") or "").strip() != str(record.get("pipeline_id")):
                kept.append(json.dumps(obj, ensure_ascii=False))
    kept.append(json.dumps(record, ensure_ascii=False))
    manifest.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _do_run_full(
    pipeline_id: str,
    root: Optional[Path],
    force: bool,
    pipeline_run_execution_mode: str,
    subprocess_fallback: bool,
    subprocess_timeout: float,
    *,
    as_json: bool,
) -> None:
    r = _resolve_root(root)
    cm = ConfigManager(project_root=r)
    if pipeline_run_execution_mode not in ("in_process", "subprocess"):
        raise typer.BadParameter(
            tr(
                "pipeline_run_execution_mode 须为 in_process 或 subprocess",
                "pipeline_run_execution_mode must be in_process or subprocess",
            )
        )
    try:
        out = run_full_pipeline(
            r,
            pipeline_id,
            llm_config=cm.llm_config(),
            on_usage=None,
            pipeline_run_execution_mode=pipeline_run_execution_mode,  # type: ignore[arg-type]
            pipeline_run_subprocess_fallback_in_process=subprocess_fallback,
            pipeline_run_subprocess_timeout_sec=subprocess_timeout,
            force=force,
        )
    except Exception as e:  # noqa: BLE001 - CLI should show readable error
        if as_json:
            typer.secho(
                json.dumps(
                    {"ok": False, "error": "pipeline_run_failed", "message": str(e)},
                    ensure_ascii=False,
                    indent=2,
                ),
                err=True,
            )
        else:
            typer.secho(tr(f"全量执行失败: {e}", f"Pipeline run failed: {e}"), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        detail = out.get("detail") if isinstance(out, dict) else {}
        run_dir = (detail or {}).get("run_dir")
        out_path = (detail or {}).get("output_jsonl")
        count = (detail or {}).get("output_record_count")
        typer.secho(tr("全量执行完成。", "Pipeline run completed."), fg=typer.colors.GREEN)
        typer.echo(f"run_dir: {run_dir}")
        typer.echo(f"output_jsonl: {out_path}")
        typer.echo(f"output_record_count: {count}")


def _do_state(pipeline_id: str, root: Optional[Path], *, as_json: bool, verbose: bool = False) -> None:
    r = _resolve_root(root)
    st = load_workflow_state(r, pipeline_id)
    d = st.to_dict()
    if as_json:
        typer.echo(json.dumps(d, ensure_ascii=False, indent=2))
        typer.echo("\nSTEP_ORDER: " + json.dumps(STEP_ORDER, ensure_ascii=False))
    else:
        print_state_human(pipeline_id, d, verbose=verbose)
        if verbose:
            typer.secho("（STEP_ORDER: " + ", ".join(STEP_ORDER) + "）", fg=typer.colors.BLUE)
        typer.echo(
            tr("机器可读", "Machine-readable")
            + ": dataevolver workflow state --json "
            + pipeline_id
        )


def _do_advance(
    pipeline_id: str,
    root: Optional[Path],
    force_reset_state: bool,
    pipeline_run_execution_mode: str,
    subprocess_fallback: bool,
    subprocess_timeout: float,
    *,
    as_json: bool,
    verbose: bool = False,
) -> None:
    r = _resolve_root(root)
    cm = ConfigManager(project_root=r)
    if pipeline_run_execution_mode not in ("in_process", "subprocess"):
        raise typer.BadParameter(
            tr(
                "pipeline_run_execution_mode 须为 in_process 或 subprocess",
                "pipeline_run_execution_mode must be in_process or subprocess",
            )
        )
    st0 = load_workflow_state(r, pipeline_id)
    next_key = (
        STEP_ORDER[st0.step_index]
        if st0.step_index < len(STEP_ORDER)
        else STEP_ORDER[-1] if STEP_ORDER else "workflow"
    )
    spin_label = step_label(next_key)
    try:
        if as_json:
            out = advance_workflow(
                r,
                pipeline_id,
                llm_config=cm.llm_config(),
                on_usage=None,
                force=force_reset_state,
                pipeline_run_execution_mode=pipeline_run_execution_mode,  # type: ignore[arg-type]
                pipeline_run_subprocess_fallback_in_process=subprocess_fallback,
                pipeline_run_subprocess_timeout_sec=subprocess_timeout,
                requested_step=None,
                step_force=False,
            )
            elapsed = None
        else:
            with step_running_display(spin_label) as disp:
                out = advance_workflow(
                    r,
                    pipeline_id,
                    llm_config=cm.llm_config(),
                    on_usage=None,
                    force=force_reset_state,
                    pipeline_run_execution_mode=pipeline_run_execution_mode,  # type: ignore[arg-type]
                    pipeline_run_subprocess_fallback_in_process=subprocess_fallback,
                    pipeline_run_subprocess_timeout_sec=subprocess_timeout,
                    requested_step=None,
                    step_force=False,
                )
            elapsed = disp.elapsed_sec()
    except WorkflowStepError as e:
        if as_json:
            typer.secho(
                json.dumps(
                    {"ok": False, "error": "workflow_step_failed", "step": e.step_key, "message": str(e)},
                    ensure_ascii=False,
                    indent=2,
                ),
                err=True,
            )
            st = load_workflow_state(r, pipeline_id)
            typer.echo(json.dumps({"state": st.to_dict()}, ensure_ascii=False, indent=2))
        else:
            print_advance_error_human(pipeline_id, e.step_key, str(e), verbose=verbose)
        raise typer.Exit(code=1)
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_advance_human(pipeline_id, out, verbose=verbose, elapsed_sec=elapsed)


def _do_advance_all(
    pipeline_id: str,
    root: Optional[Path],
    max_steps: int,
    pipeline_run_execution_mode: str,
    subprocess_fallback: bool,
    subprocess_timeout: float,
    *,
    as_json: bool,
    verbose: bool = False,
) -> None:
    r = _resolve_root(root)
    cm = ConfigManager(project_root=r)
    if pipeline_run_execution_mode not in ("in_process", "subprocess"):
        raise typer.BadParameter(
            tr(
                "pipeline_run_execution_mode 须为 in_process 或 subprocess",
                "pipeline_run_execution_mode must be in_process or subprocess",
            )
        )
    guard = 0
    prev_sig: tuple | None = None
    while guard < max_steps:
        st = load_workflow_state(r, pipeline_id)
        if st.step_index >= len(STEP_ORDER):
            msg = {"ok": True, "done": True, "message": tr("已全部完成", "completed")}
            typer.echo(json.dumps(msg, ensure_ascii=False) if as_json else tr("已全部完成。", "All done."))
            return
        next_key = STEP_ORDER[st.step_index]
        spin_label = step_label(next_key)
        try:
            if as_json:
                out = advance_workflow(
                    r,
                    pipeline_id,
                    llm_config=cm.llm_config(),
                    on_usage=None,
                    force=False,
                    pipeline_run_execution_mode=pipeline_run_execution_mode,  # type: ignore[arg-type]
                    pipeline_run_subprocess_fallback_in_process=subprocess_fallback,
                    pipeline_run_subprocess_timeout_sec=subprocess_timeout,
                    requested_step=None,
                    step_force=False,
                )
                elapsed = None
            else:
                with step_running_display(spin_label) as disp:
                    out = advance_workflow(
                        r,
                        pipeline_id,
                        llm_config=cm.llm_config(),
                        on_usage=None,
                        force=False,
                        pipeline_run_execution_mode=pipeline_run_execution_mode,  # type: ignore[arg-type]
                        pipeline_run_subprocess_fallback_in_process=subprocess_fallback,
                        pipeline_run_subprocess_timeout_sec=subprocess_timeout,
                        requested_step=None,
                        step_force=False,
                    )
                elapsed = disp.elapsed_sec()
        except WorkflowStepError as e:
            if as_json:
                typer.secho(
                    json.dumps({"ok": False, "step": e.step_key, "message": str(e)}, ensure_ascii=False),
                    err=True,
                )
            else:
                print_advance_error_human(pipeline_id, e.step_key, str(e), verbose=verbose)
            raise typer.Exit(code=1)
        if as_json:
            typer.echo(
                json.dumps(
                    {"step": out.get("step"), "detail_status": (out.get("detail") or {}).get("status")},
                    ensure_ascii=False,
                )
            )
        else:
            print_advance_human(pipeline_id, out, verbose=verbose, elapsed_sec=elapsed)
        if out.get("done"):
            return
        st_after = load_workflow_state(r, pipeline_id)
        detail = out.get("detail") if isinstance(out, dict) else {}
        sig = (
            out.get("step"),
            (detail or {}).get("status") if isinstance(detail, dict) else None,
            st_after.step_index,
            st_after.round,
            st_after.dag_evolution_cycles,
        )
        if prev_sig == sig:
            msg = tr(
                "检测到状态未前进（连续两次相同结果），已停止 advance-all。请改用显式命令（如 orchestrate --force-reset-state）处理后再继续。",
                "No progress detected (same result twice). Stopped advance-all. Use explicit commands (e.g. orchestrate --force-reset-state) before continuing.",
            )
            if as_json:
                typer.secho(json.dumps({"ok": False, "stalled": True, "message": msg}, ensure_ascii=False), err=True)
            else:
                typer.secho(msg, err=True, fg=typer.colors.YELLOW)
            raise typer.Exit(code=2)
        prev_sig = sig
        guard += 1
    typer.secho(tr("达到 max_steps 上限，未跑完。", "Reached max_steps; not finished."), err=True)
    raise typer.Exit(code=2)


def _do_named_step(
    step_key: str,
    pipeline_id: str,
    root: Optional[Path],
    force_reset_state: bool,
    pipeline_run_execution_mode: str,
    subprocess_fallback: bool,
    subprocess_timeout: float,
    *,
    as_json: bool,
    verbose: bool = False,
) -> None:
    """显式执行某一步：只校验该步前置产物（见 runner._assert_step_prerequisites），并默认强制重跑会跳过的步。"""
    r = _resolve_root(root)
    cm = ConfigManager(project_root=r)
    if pipeline_run_execution_mode not in ("in_process", "subprocess"):
        raise typer.BadParameter(
            tr(
                "pipeline_run_execution_mode 须为 in_process 或 subprocess",
                "pipeline_run_execution_mode must be in_process or subprocess",
            )
        )
    spin_label = step_label(step_key)
    try:
        if as_json:
            out = advance_workflow(
                r,
                pipeline_id,
                llm_config=cm.llm_config(),
                on_usage=None,
                force=force_reset_state,
                pipeline_run_execution_mode=pipeline_run_execution_mode,  # type: ignore[arg-type]
                pipeline_run_subprocess_fallback_in_process=subprocess_fallback,
                pipeline_run_subprocess_timeout_sec=subprocess_timeout,
                requested_step=step_key,
                step_force=True,
            )
            elapsed = None
        else:
            with step_running_display(spin_label) as disp:
                out = advance_workflow(
                    r,
                    pipeline_id,
                    llm_config=cm.llm_config(),
                    on_usage=None,
                    force=force_reset_state,
                    pipeline_run_execution_mode=pipeline_run_execution_mode,  # type: ignore[arg-type]
                    pipeline_run_subprocess_fallback_in_process=subprocess_fallback,
                    pipeline_run_subprocess_timeout_sec=subprocess_timeout,
                    requested_step=step_key,
                    step_force=True,
                )
            elapsed = disp.elapsed_sec()
    except WorkflowStepError as e:
        if as_json:
            typer.secho(
                json.dumps(
                    {"ok": False, "error": "workflow_step_failed", "step": e.step_key, "message": str(e)},
                    ensure_ascii=False,
                    indent=2,
                ),
                err=True,
            )
            st = load_workflow_state(r, pipeline_id)
            typer.echo(json.dumps({"state": st.to_dict()}, ensure_ascii=False, indent=2))
        else:
            print_advance_error_human(pipeline_id, e.step_key, str(e), verbose=verbose)
        raise typer.Exit(code=1)
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_advance_human(pipeline_id, out, verbose=verbose, elapsed_sec=elapsed)


_RootOpt = Annotated[
    Optional[Path],
    typer.Option("--root", exists=True, file_okay=False, dir_okay=True, help=t("opt.root")),
]

workflow_app = typer.Typer(
    no_args_is_help=True,
    help=t("wf.group_help"),
)


@workflow_app.callback()
def _workflow_options(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help=t("opt.verbose")),
    ] = False,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@workflow_app.command("state", help=t("wf.state.doc"))
def wf_state(
    ctx: typer.Context,
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json", help=t("opt.json"))] = False,
) -> None:
    verbose = bool((ctx.obj or {}).get("verbose"))
    _do_state(pipeline_id, root, as_json=as_json, verbose=verbose)


@workflow_app.command("advance", help=t("wf.advance.doc"))
def wf_advance(
    ctx: typer.Context,
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    force_reset_state: Annotated[
        bool, typer.Option("--force-reset-state", help=t("opt.force_reset_state"))
    ] = False,
    pipeline_run_execution_mode: Annotated[
        str,
        typer.Option(help=t("opt.pipeline_run_mode")),
    ] = "in_process",
    subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
    subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
    as_json: Annotated[bool, typer.Option("--json", help=t("opt.json"))] = False,
) -> None:
    verbose = bool((ctx.obj or {}).get("verbose"))
    _do_advance(
        pipeline_id,
        root,
        force_reset_state,
        pipeline_run_execution_mode,
        subprocess_fallback,
        subprocess_timeout,
        as_json=as_json,
        verbose=verbose,
    )


@workflow_app.command("advance-all", help=t("wf.advance_all.doc"))
def wf_advance_all(
    ctx: typer.Context,
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    max_steps: Annotated[int, typer.Option("--max-steps", min=1, max=256)] = 32,
    pipeline_run_execution_mode: Annotated[str, typer.Option()] = "in_process",
    subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
    subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
    as_json: Annotated[bool, typer.Option("--json", help=t("opt.json_lines"))] = False,
) -> None:
    verbose = bool((ctx.obj or {}).get("verbose"))
    _do_advance_all(
        pipeline_id,
        root,
        max_steps,
        pipeline_run_execution_mode,
        subprocess_fallback,
        subprocess_timeout,
        as_json=as_json,
        verbose=verbose,
    )


@workflow_app.command("rerun", help=t("wf.rerun.doc"))
def wf_rerun(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    step: Annotated[str, typer.Argument(help=t("opt.step"))],
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    r = _resolve_root(root)
    try:
        out = rerun_workflow_from_step(r, pipeline_id, step.strip())
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_rerun_human(out)


@workflow_app.command("run-pipeline", help=t("wf.run_pipeline.doc"))
def wf_run_pipeline(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    force: Annotated[bool, typer.Option("--force", help=t("opt.force"))] = False,
    pipeline_run_execution_mode: Annotated[str, typer.Option(help=t("opt.pipeline_run_exec"))] = "in_process",
    subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
    subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _do_run_full(
        pipeline_id,
        root,
        force,
        pipeline_run_execution_mode,
        subprocess_fallback,
        subprocess_timeout,
        as_json=as_json,
    )


_NAMED_STEPS: list[tuple[str, str, str]] = [
    ("understanding", "understand", "wf.named.understand"),
    ("orchestration", "orchestrate", "wf.named.orchestrate"),
    ("operator_evolution", "evolve-operators", "wf.named.evolve_operators"),
    ("instantiation", "instantiate", "wf.named.instantiate"),
    ("trial_run", "trial", "wf.named.trial"),
    ("quality_check", "quality-check", "wf.named.quality_check"),
    ("experience", "experience", "wf.named.experience"),
]

def _register_one_named_step(step_key: str, cli_name: str, help_key: str) -> None:
    help_txt = t(help_key)

    @workflow_app.command(cli_name, help=help_txt)
    def _named_cmd(
        ctx: typer.Context,
        pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
        root: _RootOpt = None,
        force_reset_state: Annotated[
            bool,
            typer.Option("--force-reset-state", help=t("opt.force_reset_state_long")),
        ] = False,
        pipeline_run_execution_mode: Annotated[
            str,
            typer.Option(help=t("opt.pipeline_run_mode_run")),
        ] = "in_process",
        subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
        subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
        as_json: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        verbose = bool((ctx.obj or {}).get("verbose"))
        _do_named_step(
            step_key,
            pipeline_id,
            root,
            force_reset_state,
            pipeline_run_execution_mode,
            subprocess_fallback,
            subprocess_timeout,
            as_json=as_json,
            verbose=verbose,
        )

    _named_cmd.__doc__ = help_txt


for _sk, _cn, _hk in _NAMED_STEPS:
    _register_one_named_step(_sk, _cn, _hk)


@workflow_app.command("validate-dag", help=t("wf.validate_dag.help"))
def wf_validate_dag_only(
    ctx: typer.Context,
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    verbose = bool((ctx.obj or {}).get("verbose"))
    r = _resolve_root(root)
    cm = ConfigManager(project_root=r)
    try:
        if as_json:
            detail = run_pipeline_assessment_and_persist(
                r,
                pipeline_id,
                cm.llm_config(),
                on_usage=None,
                usage_operation="assessment_refresh.llm_task_fit",
            )
            elapsed = None
        else:
            with step_running_display(tr("刷新 DAG 评估", "Refreshing DAG assessment")) as disp:
                detail = run_pipeline_assessment_and_persist(
                    r,
                    pipeline_id,
                    cm.llm_config(),
                    on_usage=None,
                    usage_operation="assessment_refresh.llm_task_fit",
                )
            elapsed = disp.elapsed_sec()
    except (FileNotFoundError, ValueError, OSError) as e:
        if as_json:
            typer.echo(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), err=True)
        else:
            typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    st = load_workflow_state(r, pipeline_id)
    out = {
        "ok": True,
        "pipeline_id": pipeline_id,
        "done": False,
        "step": "assessment_refresh",
        "detail": {"status": "completed", **detail},
        "state": st.to_dict(),
        "invocation": "explicit",
        "state_unchanged": True,
    }
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_advance_human(pipeline_id, out, verbose=verbose, elapsed_sec=elapsed)


app = typer.Typer(
    no_args_is_help=True,
    help=t("app.help"),
)


@app.callback()
def _root_callback(
    _version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-V",
            help=t("app.opt.version"),
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
    lang: Annotated[
        str,
        typer.Option(
            "--lang",
            help=t("app.opt.lang"),
        ),
    ] = "",
) -> None:
    # 语言优先级：显式 --lang > 环境变量 > 项目级 prefs > 全局 prefs > 默认 zh
    # 注意：不要强依赖 cwd 是 repo root；全局 prefs 应始终可用。
    from core.workspace import WorkspaceNotFoundError, resolve_project_root

    project_root = None
    try:
        project_root = resolve_project_root()
    except WorkspaceNotFoundError:
        project_root = None
    prefs = load_cli_prefs(project_root)
    pref_lang = str(prefs.get("lang") or "").strip().lower()
    v = (lang or os.environ.get("DATAEVOLVER_LANG") or pref_lang or "zh").strip().lower()
    if v not in ("zh", "en"):
        raise typer.BadParameter(tr("lang 需为 zh 或 en", "lang must be zh or en"))
    set_cli_language(v)
    return


from .init_cmd import register_init_command
from .operators_cmd import operators_app

register_init_command(app)

app.add_typer(workflow_app, name="workflow")
# 更短的别名：减少输入负担（保留 workflow 兼容）
app.add_typer(workflow_app, name="wf")
app.add_typer(operators_app, name="operators")
app.add_typer(operators_app, name="op")


@app.command("lang", help=t("cmd.lang.doc"))
def cmd_lang(
    value: Annotated[str, typer.Argument(help=t("cmd.lang.arg"))],
    root: _RootOpt = None,
) -> None:
    r = _resolve_root(root)
    v = (value or "").strip().lower()
    if v not in ("zh", "en"):
        raise typer.BadParameter(tr("lang 需为 zh 或 en", "lang must be zh or en"))
    # global
    prefs = load_cli_prefs(None)
    prefs["lang"] = v
    gpath = save_global_cli_prefs(prefs)
    # project (optional)
    proj_rel: str | None = None
    if (r / "config").is_dir() and (r / "data").is_dir():
        try:
            proj = load_cli_prefs(r)
            proj["lang"] = v
            proj_rel = save_project_cli_prefs(r, proj)
        except Exception:
            proj_rel = None
    set_cli_language(v)
    tail = f"  ({gpath})" if not proj_rel else f"  ({gpath}; {proj_rel})"
    typer.echo(tr("已设置语言", "Language set") + f": {v}" + tail)


# 顶层短命令：dataevolver trial <pipeline_id> 代替 dataevolver workflow trial <pipeline_id>
@app.command("state", help=t("top.state.doc"))
def cmd_state(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json", help=t("opt.json"))] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help=t("opt.verbose_state"))] = False,
) -> None:
    # 顶层命令不走 workflow callback，这里显式接收 -v
    _do_state(pipeline_id, root, as_json=as_json, verbose=verbose)


@app.command("next", help=t("top.next.doc"))
def cmd_next(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
) -> None:
    r = _resolve_root(root)
    st = load_workflow_state(r, pipeline_id)
    d = st.to_dict()
    idx = int(d.get("step_index", 0))
    if 0 <= idx < len(STEP_ORDER):
        typer.echo("dataevolver " + STEP_TO_CLI.get(STEP_ORDER[idx], STEP_ORDER[idx]) + " " + pipeline_id)
    else:
        typer.echo("dataevolver state " + pipeline_id)


@app.command("advance", help=t("top.advance.doc"))
def cmd_advance(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    force_reset_state: Annotated[
        bool, typer.Option("--force-reset-state", help=t("opt.force_reset_state"))
    ] = False,
    pipeline_run_execution_mode: Annotated[str, typer.Option(help=t("opt.pipeline_run_mode"))] = "in_process",
    subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
    subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
    as_json: Annotated[bool, typer.Option("--json", help=t("opt.json"))] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help=t("opt.verbose_short"))] = False,
) -> None:
    _do_advance(
        pipeline_id,
        root,
        force_reset_state,
        pipeline_run_execution_mode,
        subprocess_fallback,
        subprocess_timeout,
        as_json=as_json,
        verbose=verbose,
    )


@app.command("rerun", help=t("top.rerun.doc"))
def cmd_rerun(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    step: Annotated[str, typer.Argument(help=t("opt.step_top"))],
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    r = _resolve_root(root)
    try:
        out = rerun_workflow_from_step(r, pipeline_id, step.strip())
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_rerun_human(out)


# 复用 workflow 内的 named steps 语义（顶层短命令）
_TOP_STEP_ALIASES: list[tuple[str, str]] = [
    ("understanding", "understand"),
    ("orchestration", "orchestrate"),
    ("operator_evolution", "evolve-operators"),
    ("instantiation", "instantiate"),
    ("trial_run", "trial"),
    ("quality_check", "quality-check"),
    ("experience", "experience"),
]


def _register_top_step(step_key: str, cli_name: str) -> None:
    @app.command(cli_name)
    def _top_step_cmd(
        ctx: typer.Context,
        pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
        root: _RootOpt = None,
        force_reset_state: Annotated[
            bool,
            typer.Option("--force-reset-state", help=t("opt.force_reset_state_long")),
        ] = False,
        pipeline_run_execution_mode: Annotated[str, typer.Option(help=t("opt.pipeline_run_mode_top"))] = "in_process",
        subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
        subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
        as_json: Annotated[bool, typer.Option("--json")] = False,
        verbose: Annotated[bool, typer.Option("--verbose", "-v", help=t("opt.verbose_short"))] = False,
    ) -> None:
        # 顶层：直接显式执行 step_key（等价 workflow 子命令）
        _do_named_step(
            step_key,
            pipeline_id,
            root,
            force_reset_state,
            pipeline_run_execution_mode,
            subprocess_fallback,
            subprocess_timeout,
            as_json=as_json,
            verbose=verbose,
        )

    _top_step_cmd.__doc__ = t("top.step.doc").format(cmd=cli_name)


for _sk, _cn in _TOP_STEP_ALIASES:
    _register_top_step(_sk, _cn)


@app.command("run", help=t("top.run.doc"))
def cmd_run(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    force: Annotated[bool, typer.Option("--force", help=t("opt.force"))] = False,
    pipeline_run_execution_mode: Annotated[str, typer.Option(help=t("opt.pipeline_run_exec"))] = "in_process",
    subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
    subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _do_run_full(
        pipeline_id,
        root,
        force,
        pipeline_run_execution_mode,
        subprocess_fallback,
        subprocess_timeout,
        as_json=as_json,
    )


@app.command("session-start", help=t("cmd.session.doc"))
def cmd_session_start(
    pipeline_id: Annotated[str, typer.Argument(help=t("cmd.session.pipeline_id"))],
    raw_file: Annotated[
        Path, typer.Option("--raw", exists=True, file_okay=True, dir_okay=False, help=t("cmd.session.raw"))
    ],
    seed_file: Annotated[
        Path, typer.Option("--seed", exists=True, file_okay=True, dir_okay=False, help=t("cmd.session.seed"))
    ],
    description_file: Annotated[
        Path | None,
        typer.Option(
            "--description",
            exists=True,
            file_okay=True,
            dir_okay=False,
            help=t("cmd.session.description"),
        ),
    ] = None,
    domain: Annotated[str, typer.Option("--domain")] = "",
    task_type: Annotated[str, typer.Option("--task-type")] = "",
    language: Annotated[str, typer.Option("--language")] = "",
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    pid = pipeline_id.strip()
    if not _PIPELINE_ID_RE.match(pid):
        raise typer.BadParameter(
            tr(
                "pipeline_id 无效：仅允许字母、数字、下划线、连字符，长度 1-128",
                "Invalid pipeline_id: only letters, numbers, underscore and hyphen, length 1-128",
            )
        )
    r = _resolve_root(root)
    base = r / "data" / "uploads" / pid
    raw_dest = base / "raw_data" / _safe_filename(raw_file.name)
    seed_dest = base / "seed_data" / _safe_filename(seed_file.name)
    desc_dest: Path | None = None
    raw_dest.parent.mkdir(parents=True, exist_ok=True)
    seed_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_file, raw_dest)
    shutil.copy2(seed_file, seed_dest)
    if description_file is not None:
        desc_dest = base / "description" / _safe_filename(description_file.name)
        desc_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(description_file, desc_dest)

    rec: dict[str, object] = {
        "pipeline_id": pid,
        "raw_data_files": [str(raw_dest.relative_to(r))],
        "seed_data_files": [str(seed_dest.relative_to(r))],
    }
    if desc_dest is not None:
        rec["description_data_files"] = [str(desc_dest.relative_to(r))]
    if domain.strip():
        rec["domain"] = domain.strip()
    if task_type.strip():
        rec["task_type"] = task_type.strip()
    if language.strip():
        rec["language"] = language.strip()
    _upsert_manifest_record(r, rec)
    out = {
        "ok": True,
        "pipeline_id": pid,
        "manifest_record": rec,
        "saved_paths": {
            "raw": str(raw_dest.relative_to(r)),
            "seed": str(seed_dest.relative_to(r)),
            "description": str(desc_dest.relative_to(r)) if desc_dest is not None else None,
        },
    }
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        typer.secho(tr("会话创建完成。", "Session created."), fg=typer.colors.GREEN)
        typer.echo(f"pipeline_id: {pid}")
        typer.echo(f"raw: {out['saved_paths']['raw']}")
        typer.echo(f"seed: {out['saved_paths']['seed']}")
        if out["saved_paths"]["description"]:
            typer.echo(f"description: {out['saved_paths']['description']}")


@app.command("tokens", help=t("cmd.tokens.doc"))
def cmd_tokens(
    pipeline_id: Annotated[str, typer.Argument(help=t("opt.pipeline_id"))],
    root: _RootOpt = None,
    no_events: Annotated[bool, typer.Option("--no-events", help=t("opt.no_events"))] = False,
    max_events: Annotated[int, typer.Option("--max-events", min=1, max=2000)] = 200,
    as_json: Annotated[bool, typer.Option("--json", help=t("opt.json_full"))] = False,
) -> None:
    r = _resolve_root(root)
    summary = summarize_token_ledger(
        r,
        pipeline_id,
        include_events=bool(as_json and not no_events),
        max_events=max_events,
    )
    if as_json:
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_tokens_human(summary)
        typer.secho(
            tr(
                "完整 JSON（含 for_frontend / 可选 events）: dataevolver tokens --json " + pipeline_id,
                "Full JSON (for_frontend / optional events): dataevolver tokens --json " + pipeline_id,
            ),
            fg=typer.colors.BLUE,
        )


# 兼容旧用法（不在顶层 --help 中列出；但不能与新顶层命令重名）
@app.command("legacy-state", hidden=True)
def legacy_state(pipeline_id: Annotated[str, typer.Argument()], root: _RootOpt = None) -> None:
    _do_state(pipeline_id, root, as_json=True)


@app.command("legacy-advance", hidden=True)
def legacy_advance(
    pipeline_id: Annotated[str, typer.Argument()],
    root: _RootOpt = None,
    force_reset_state: Annotated[bool, typer.Option("--force-reset-state")] = False,
    pipeline_run_execution_mode: Annotated[str, typer.Option()] = "in_process",
    subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
    subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
) -> None:
    _do_advance(
        pipeline_id,
        root,
        force_reset_state,
        pipeline_run_execution_mode,
        subprocess_fallback,
        subprocess_timeout,
        as_json=True,
    )


@app.command("legacy-advance-all", hidden=True)
def legacy_advance_all(
    pipeline_id: Annotated[str, typer.Argument()],
    root: _RootOpt = None,
    max_steps: Annotated[int, typer.Option("--max-steps", min=1, max=256)] = 32,
    pipeline_run_execution_mode: Annotated[str, typer.Option()] = "in_process",
    subprocess_fallback: Annotated[bool, typer.Option("--subprocess-fallback/--no-subprocess-fallback")] = True,
    subprocess_timeout: Annotated[float, typer.Option("--subprocess-timeout")] = 600.0,
) -> None:
    _do_advance_all(
        pipeline_id,
        root,
        max_steps,
        pipeline_run_execution_mode,
        subprocess_fallback,
        subprocess_timeout,
        as_json=True,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
