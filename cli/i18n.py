"""
CLI 国际化：启动时解析语言（环境变量 / --lang / prefs），供 Typer help 与运行时输出共用。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
_LANG_ENV = "DATAEVOLVER_LANG"

# key -> (zh, en)
_MESSAGES: dict[str, tuple[str, str]] = {
    # --- shared options ---
    "opt.pipeline_id": ("如 my_pipeline", "e.g. my_pipeline"),
    "opt.root": (
        "仓库根；不设则用 DATAEVOLVER_ROOT 或当前目录",
        "Repo root; default DATAEVOLVER_ROOT or cwd",
    ),
    "opt.root_repo": ("仓库根目录", "Repository root directory"),
    "opt.json": ("输出 JSON（默认人类可读）", "Emit JSON (default: human-readable)"),
    "opt.json_lines": ("每步一行 JSON", "One JSON object per step"),
    "opt.json_full": ("完整 JSON（含 for_frontend）", "Full JSON (includes for_frontend)"),
    "opt.verbose": ("显示完整步骤说明、分支提示与路径（默认简洁输出）", "Verbose step hints and paths (default: compact)"),
    "opt.verbose_state": ("显示更完整状态", "More detailed status"),
    "opt.verbose_short": ("显示完整说明", "Verbose output"),
    "opt.force_reset_state": (
        "删 state 后从第 0 步执行本步",
        "Delete state.json and run from step 0",
    ),
    "opt.force_reset_state_long": (
        "删除 state.json；下一待执行步将回到 understanding",
        "Delete state.json; next pending step becomes understanding",
    ),
    "opt.pipeline_run_mode": ("仅当本步为 pipeline_run 时有效", "Only when this step is pipeline_run"),
    "opt.pipeline_run_mode_run": ("仅 run-pipeline 步有效", "Only for run-pipeline step"),
    "opt.pipeline_run_mode_top": ("仅 run 步有效", "Only for run step"),
    "opt.pipeline_run_exec": (
        "执行模式：in_process 或 subprocess",
        "Execution mode: in_process or subprocess",
    ),
    "opt.force": ("忽略 latest 成功记录并强制重跑", "Ignore latest success and force re-run"),
    "opt.step": ("步骤名，见 workflow state 中的 STEP_ORDER", "Step name; see STEP_ORDER in workflow state"),
    "opt.step_top": ("步骤名，见 state 的 STEP_ORDER", "Step name; see STEP_ORDER in state"),
    "opt.no_events": ("不输出 events 数组，只看汇总", "Omit events array; summary only"),
    # --- main app ---
    "app.help": (
        "DataEvolver 开源版 CLI。推荐：`dataevolver --help`（支持短命令别名与中英文输出）。",
        "DataEvolver CLI. Run `dataevolver --help` (short aliases; zh/en output).",
    ),
    "app.root.doc": (
        "根级选项（如 --version）；子命令见 workflow / operators / init / tokens。",
        "Root options (--version); subcommands: workflow, operators, init, tokens, …",
    ),
    "app.opt.version": ("打印包版本", "Print package version"),
    "app.opt.lang": (
        "CLI 输出语言：zh / en；也可用环境变量 DATAEVOLVER_LANG",
        "CLI language: zh / en; or env DATAEVOLVER_LANG",
    ),
    "cmd.lang.doc": (
        "一条命令切换 CLI 输出语言（写入全局 prefs；若在仓库根也写入项目 prefs）",
        "Set CLI language (global prefs; also project prefs when in a workspace)",
    ),
    "cmd.lang.arg": ("zh 或 en", "zh or en"),
    # --- workflow group ---
    "wf.group_help": (
        "工作流：understand / orchestrate 等子命令可**随时执行**（只检查前置产物，并默认强制重跑会跳过的步）；"
        "编排结束会自动写 LLM 评估。`validate-dag` 仅刷新评估。`advance` 按 state 推「下一步」。"
        " 长步骤运行时终端会显示动态等待行（已用时间）；`DATAEVOLVER_NO_PROGRESS=1` 可关闭。默认简洁输出，`--verbose` 显示完整说明。",
        "Workflow: understand / orchestrate / … can run anytime (prerequisite artifacts only; skipped steps are forced by default). "
        "Orchestration auto-writes LLM assessment. `validate-dag` refreshes assessment only. `advance` runs the next step from state. "
        "Long steps show a live wait line (elapsed time); set DATAEVOLVER_NO_PROGRESS=1 to disable. Compact by default; use --verbose for details.",
    ),
    "wf.state.doc": ("查看当前 workflow 状态与步骤顺序。", "Show workflow state and step order."),
    "wf.advance.doc": ("只执行「下一步」；可反复执行直到整链跑完。", "Run only the next step; repeat until done."),
    "wf.advance_all.doc": (
        "连续 advance 直到完成、失败或达到 --max-steps。",
        "Advance repeatedly until done, failure, or --max-steps.",
    ),
    "wf.rerun.doc": (
        "从指定步骤重跑：删除该步及之后的产物，并把 state 指到该步；随后执行该步对应的 workflow 子命令。",
        "Rerun from a step: remove its artifacts and later ones, reset state, then run that step's command.",
    ),
    "wf.run_pipeline.doc": (
        "执行 full run（不属于 workflow 中间推进步）。",
        "Full pipeline run (not a workflow advance step).",
    ),
    "wf.validate_dag.help": (
        "不重新编排：仅对当前 orchestration_results 重新跑结构检查 + LLM 评估并写回（不改 workflow state）",
        "Re-assess current orchestration_results (structure + LLM); does not change workflow state",
    ),
    "wf.named.understand": ("结构化理解（LLM）", "Structured understanding (LLM)"),
    "wf.named.orchestrate": (
        "算子编排三阶段（LLM）；完成后自动结构检查 + 模型评估 DAG",
        "Three-stage operator orchestration (LLM); then structural check + DAG assessment",
    ),
    "wf.named.evolve_operators": (
        "算子进化：仅当编排内评估建议新增算子时生成粗粒度算子并写入注册表",
        "Evolve operators when assessment suggests new ones; write coarse operators to registry",
    ),
    "wf.named.instantiate": ("管线实例化", "Pipeline instantiation"),
    "wf.named.trial": ("试运行（采样）", "Trial run (sample)"),
    "wf.named.quality_check": ("质量快照", "Quality snapshot"),
    "wf.named.experience": ("经验快照", "Experience snapshot"),
    # --- top-level short commands ---
    "top.state.doc": ("查看当前 workflow 状态与下一步。", "Show workflow state and next step."),
    "top.next.doc": (
        "只打印「下一步命令」（适合脚本与复制粘贴）。",
        "Print only the next command (for scripts / copy-paste).",
    ),
    "top.advance.doc": ("只执行「下一步」（顶层短命令）。", "Run the next step (top-level shortcut)."),
    "top.rerun.doc": ("从指定步骤重跑（顶层短命令）。", "Rerun from a step (top-level shortcut)."),
    "top.run.doc": (
        "顶层 full run 短命令（等价 `dataevolver workflow run-pipeline <pipeline_id>`）。",
        "Top-level full run (same as `dataevolver workflow run-pipeline <id>`).",
    ),
    "top.step.doc": (
        "顶层短命令：等价 `dataevolver workflow {cmd} <pipeline_id>`",
        "Top-level shortcut: same as `dataevolver workflow {cmd} <pipeline_id>`",
    ),
    # --- session / tokens / init ---
    "cmd.session.doc": (
        "CLI 创建会话并写入 manifest（等价前端 sessions/start）",
        "Create session and write manifest (same as web sessions/start)",
    ),
    "cmd.session.pipeline_id": ("会话 id，例如 demo_001", "Session id, e.g. demo_001"),
    "cmd.session.raw": ("原始数据文件路径", "Raw data file path"),
    "cmd.session.seed": ("种子数据文件路径", "Seed data file path"),
    "cmd.session.description": ("可选任务描述文件", "Optional task description file"),
    "cmd.tokens.doc": (
        "汇总该 pipeline 的 LLM token（`data/workflow_runs/<id>/token_usage.jsonl`）",
        "Summarize LLM tokens for a pipeline (`data/workflow_runs/<id>/token_usage.jsonl`)",
    ),
    "init.target": ("目标目录，默认当前目录", "Target directory (default: cwd)"),
    "init.force": ("覆盖已存在的配置文件", "Overwrite existing config files"),
    "init.doc": (
        "初始化 DataEvolver 工作区（config/ + data/ + 运行时目录）。\n\n"
        "PyPI 安装后首次使用前必须执行；git 克隆仓库通常可跳过。",
        "Initialize a DataEvolver workspace (config/, data/, runtime dirs).\n\n"
        "Required after PyPI install; usually skipped when cloning the git repo.",
    ),
    # --- operators ---
    "op.group_help": (
        "算子池：手动添加、列出、删除自定义算子（写入 task / domain / general 记忆层）。",
        "Operator pool: add, list, remove custom operators (task / domain / general memory).",
    ),
    "op.scope": (
        "写入层级：task（默认，按 pipeline 隔离）| domain | general",
        "Memory scope: task (default, per pipeline) | domain | general",
    ),
    "op.list.doc": ("列出当前算子池（含来源与分类）。", "List operator pool (source and category)."),
    "op.list.pipeline": ("按 pipeline 查看隔离后的算子池（推荐）", "Filter by pipeline (recommended)"),
    "op.list.source": ("仅显示某来源：base|general|domain|task", "Filter by source: base|general|domain|task"),
    "op.add.doc": (
        "手动添加算子到算子池。\n\n"
        "示例：\n"
        "  dataevolver operators add my_op -p demo --description \"清理多余字段\" -c structure",
        "Manually add operators to the pool.\n\n"
        "Example:\n"
        "  dataevolver operators add my_op -p demo --description \"clean fields\" -c structure",
    ),
    "op.remove.doc": (
        "从 task / domain / general 记忆层删除手动或进化写入的算子（不能删 base）。",
        "Remove manual/evolved operators from task/domain/general (not base).",
    ),
    "op.show.doc": ("查看合并后某算子的完整规格。", "Show merged operator spec."),
    "op.arg.name": ("算子名，如 my_bridge.clean_records", "Operator name, e.g. my_bridge.clean_records"),
    "op.arg.remove": ("要删除的算子名", "Operator name to remove"),
    "op.arg.show": ("算子名", "Operator name"),
    "op.opt.description": ("算子说明", "Operator description"),
    "op.opt.category": (
        "分类：io|structure|control|semantic|quality|bridge",
        "Category: io|structure|control|semantic|quality|bridge",
    ),
    "op.opt.input_keys": ("输入键，逗号分隔，默认 records", "Input keys, comma-separated (default records)"),
    "op.opt.output_keys": ("输出键，逗号分隔，默认 records", "Output keys, comma-separated (default records)"),
    "op.opt.requires_llm": ("实例化时是否调用 LLM", "Call LLM during instantiation"),
    "op.opt.from_file": ("从 JSON 导入（单算子或算子字典）", "Import from JSON (one operator or dict)"),
    "op.opt.copy_from": ("从已有算子复制规格作为模板", "Copy spec from existing operator as template"),
    "op.opt.interactive": ("交互式填写", "Interactive prompts"),
    "op.opt.overwrite": ("覆盖同作用域已有同名算子", "Overwrite same-name operator in scope"),
    "op.opt.pipeline_id": ("目标 pipeline（task 记忆层隔离）", "Target pipeline (task memory isolation)"),
}


def _normalize_lang(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    return v if v in ("zh", "en") else None


def _lang_from_argv() -> str | None:
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg in ("--lang", "-lang") and i + 1 < len(argv):
            return _normalize_lang(argv[i + 1])
        if arg.startswith("--lang="):
            return _normalize_lang(arg.split("=", 1)[1])
    return None


def _try_project_root() -> Path | None:
    try:
        from core.workspace import WorkspaceNotFoundError, resolve_project_root

        return resolve_project_root()
    except WorkspaceNotFoundError:
        return None
    except Exception:
        return None


def bootstrap_cli_language() -> str:
    """
    在定义 Typer help 之前调用：env > argv --lang > 项目 prefs > 全局 prefs > zh。
    结果写入 DATAEVOLVER_LANG。
    """
    lang = _normalize_lang(os.environ.get(_LANG_ENV))
    if not lang:
        lang = _lang_from_argv()
    if not lang:
        from core.cli_prefs import load_cli_prefs

        prefs = load_cli_prefs(_try_project_root())
        lang = _normalize_lang(str(prefs.get("lang") or ""))
    if not lang:
        lang = "zh"
    os.environ[_LANG_ENV] = lang
    return lang


def current_lang() -> str:
    v = _normalize_lang(os.environ.get(_LANG_ENV))
    return v or "zh"


def set_cli_language(lang: str) -> None:
    v = _normalize_lang(lang)
    if not v:
        raise ValueError("lang must be zh or en")
    os.environ[_LANG_ENV] = v


def tr(zh: str, en: str) -> str:
    return en if current_lang() == "en" else zh


def t(key: str) -> str:
    pair = _MESSAGES.get(key)
    if not pair:
        return key
    return pair[1] if current_lang() == "en" else pair[0]


# 模块被 import 时即解析语言（保证 Typer help 与 prefs 一致）
bootstrap_cli_language()
