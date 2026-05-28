"""
CLI：算子池管理（手动添加 / 列出 / 删除 / 从文件导入）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from subsystems.operator_management import OperatorRegistryStore
from subsystems.operator_management.manual_registry import (
    ManualOperatorError,
    VALID_CATEGORIES,
    add_manual_operators,
    build_operator_spec,
    load_operators_from_file,
    list_operators_summary,
    normalize_operator_name,
    remove_manual_operator,
)

operators_app = typer.Typer(
    no_args_is_help=True,
    help="算子池：手动添加、列出、删除自定义算子（写入 task / domain / general 记忆层）。",
)


def _lang() -> str:
    v = (os.environ.get("DATAEVOLVER_LANG") or "zh").strip().lower()
    return "en" if v == "en" else "zh"


def _tr(zh: str, en: str) -> str:
    return en if _lang() == "en" else zh


_RootOpt = Annotated[
    Optional[Path],
    typer.Option("--root", exists=True, file_okay=False, dir_okay=True, help="仓库根目录"),
]

_ScopeOpt = Annotated[
    str,
    typer.Option(
        "--scope",
        help="写入层级：task（默认，按 pipeline 隔离）| domain | general",
    ),
]


def _resolve_root(root: Optional[Path]) -> Path:
    if root is not None:
        return Path(root).resolve()
    env_root = (os.environ.get("DATAEVOLVER_ROOT") or "").strip()
    return Path(env_root).resolve() if env_root else Path.cwd().resolve()


def _validate_pipeline_id(pipeline_id: str) -> str:
    import re

    pid = pipeline_id.strip()
    if not re.match(r"^[a-zA-Z0-9_-]{1,128}$", pid):
        raise typer.BadParameter(
            _tr(
                "pipeline_id 无效：仅允许字母、数字、下划线、连字符",
                "Invalid pipeline_id: letters, numbers, underscore, hyphen only",
            )
        )
    return pid


def _store(root: Path, pipeline_id: str | None) -> OperatorRegistryStore:
    return OperatorRegistryStore(root, pipeline_id=pipeline_id)


def _print_add_result(out: dict, *, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
        return
    if out.get("added"):
        typer.secho(
            _tr("已添加算子", "Added operators") + ": " + ", ".join(out["added"]),
            fg=typer.colors.GREEN,
        )
    for sk in out.get("skipped") or []:
        typer.secho(
            f"  · {sk.get('name')}: {sk.get('reason')}",
            fg=typer.colors.YELLOW,
        )
    mem = out.get("memory_update")
    if isinstance(mem, dict):
        promoted_d = mem.get("promoted_to_domain") or []
        promoted_g = mem.get("promoted_to_general") or []
        if promoted_d or promoted_g:
            typer.echo(
                _tr("记忆晋升", "Memory promotion")
                + f": domain={promoted_d or '-'}  general={promoted_g or '-'}"
            )
    typer.echo(
        _tr("注册表路径", "Registry path")
        + f": {out.get('registry_path')}  ·  "
        + _tr("算子池合计", "Pool size")
        + f": {out.get('pool_size')}"
    )
    if out.get("domain_key"):
        typer.echo(_tr("域键", "Domain key") + f": {out['domain_key']}")
    typer.secho(
        _tr("提示：添加后请重新执行 orchestrate 以在 DAG 中使用新算子。", "Tip: re-run orchestrate to use new operators in the DAG."),
        fg=typer.colors.BLUE,
    )


@operators_app.command("list")
def cmd_list(
    pipeline_id: Annotated[
        str | None,
        typer.Option("--pipeline-id", "-p", help="按 pipeline 查看隔离后的算子池（推荐）"),
    ] = None,
    root: _RootOpt = None,
    source: Annotated[
        str | None,
        typer.Option("--source", help="仅显示某来源：base|general|domain|task"),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """列出当前算子池（含来源与分类）。"""
    r = _resolve_root(root)
    pid = _validate_pipeline_id(pipeline_id) if pipeline_id else None
    summary = list_operators_summary(_store(r, pid))
    ops = summary["operators"]
    if source:
        src = source.strip().lower()
        ops = [o for o in ops if str(o.get("source")) == src]
    if as_json:
        typer.echo(json.dumps({**summary, "operators": ops}, ensure_ascii=False, indent=2))
        return
    typer.echo(_tr("算子池", "Operator pool") + f"  total={len(ops)}  pipeline={pid or '(global)'}")
    if summary.get("domain_key"):
        typer.echo(f"  domain_key={summary['domain_key']}")
    for o in ops:
        llm = " [LLM]" if o.get("requires_llm") else ""
        typer.echo(
            f"  {o.get('name'):<32}  {str(o.get('source')):<8}  {str(o.get('category_id')):<10}{llm}"
        )
        desc = str(o.get("description") or "")[:72]
        if desc:
            typer.echo(f"      {desc}")


@operators_app.command("add")
def cmd_add(
    name: Annotated[
        str | None,
        typer.Argument(help="算子名，如 my_bridge.clean_records"),
    ] = None,
    pipeline_id: Annotated[
        str,
        typer.Option("--pipeline-id", "-p", help="目标 pipeline（task 记忆层隔离）"),
    ] = "",
    description: Annotated[str, typer.Option("--description", "-d", help="算子说明")] = "",
    category: Annotated[
        str,
        typer.Option("--category", "-c", help="分类：io|structure|control|semantic|quality|bridge"),
    ] = "bridge",
    input_keys: Annotated[
        str,
        typer.Option("--input-keys", help="输入键，逗号分隔，默认 records"),
    ] = "records",
    output_keys: Annotated[
        str,
        typer.Option("--output-keys", help="输出键，逗号分隔，默认 records"),
    ] = "records",
    requires_llm: Annotated[bool, typer.Option("--requires-llm", help="实例化时是否调用 LLM")] = False,
    from_file: Annotated[
        Path | None,
        typer.Option("--from-file", exists=True, file_okay=True, dir_okay=False, help="从 JSON 导入（单算子或算子字典）"),
    ] = None,
    copy_from: Annotated[
        str | None,
        typer.Option("--copy-from", help="从已有算子复制规格作为模板"),
    ] = None,
    interactive: Annotated[bool, typer.Option("--interactive", "-i", help="交互式填写")] = False,
    scope: _ScopeOpt = "task",
    overwrite: Annotated[bool, typer.Option("--overwrite", help="覆盖同作用域已有同名算子")] = False,
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    手动添加算子到算子池。

    示例：

      dataevolver operators add my_op -p demo --description "清理多余字段" -c structure

      dataevolver operators add -p demo --from-file ./my_operator.json

      dataevolver operators add -p demo -i
    """
    r = _resolve_root(root)
    if not pipeline_id.strip():
        typer.secho(
            _tr("请指定 --pipeline-id / -p", "Please set --pipeline-id / -p"),
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    pid = _validate_pipeline_id(pipeline_id)
    sc = scope.strip().lower()
    if sc not in ("task", "domain", "general"):
        raise typer.BadParameter(_tr("scope 须为 task|domain|general", "scope must be task|domain|general"))

    store = _store(r, pid)
    operators: dict[str, dict] = {}

    try:
        if from_file is not None:
            operators = load_operators_from_file(from_file)
        elif interactive:
            if not typer.confirm(_tr("交互式添加算子", "Interactive add operator"), default=True):
                raise typer.Exit()
            in_name = typer.prompt(_tr("算子名称", "Operator name"))
            in_desc = typer.prompt(_tr("描述", "Description"))
            in_cat = typer.prompt(
                _tr("分类", "Category") + f" ({'/'.join(sorted(VALID_CATEGORIES))})",
                default="bridge",
            )
            in_in = typer.prompt(_tr("input_keys（逗号分隔）", "input_keys (comma-separated)"), default="records")
            in_out = typer.prompt(_tr("output_keys（逗号分隔）", "output_keys (comma-separated)"), default="records")
            in_llm = typer.confirm(_tr("requires_llm？", "requires_llm?"), default=False)
            op_name = normalize_operator_name(in_name)
            operators[op_name] = build_operator_spec(
                description=in_desc,
                input_keys=in_in,
                output_keys=in_out,
                requires_llm=in_llm,
                category=in_cat,
                name=op_name,
            )
        elif copy_from:
            template_name = copy_from.strip()
            merged = store.merged_raw()
            if template_name not in merged:
                raise ManualOperatorError(
                    _tr(f"模板算子不存在: {template_name}", f"Template operator not found: {template_name}")
                )
            if not name:
                raise ManualOperatorError(
                    _tr("使用 --copy-from 时请同时提供新算子名称", "Provide new operator name when using --copy-from")
                )
            op_name = normalize_operator_name(name)
            tpl = dict(merged[template_name])
            tpl["source"] = "manual"
            tpl.pop("added_at", None)
            operators[op_name] = tpl
        else:
            if not name:
                typer.secho(
                    _tr(
                        "请提供算子名，或使用 --from-file / --interactive / --copy-from",
                        "Provide operator name, or use --from-file / --interactive / --copy-from",
                    ),
                    err=True,
                    fg=typer.colors.RED,
                )
                raise typer.Exit(code=2)
            if not description.strip():
                typer.secho(
                    _tr("请提供 --description，或使用 --from-file / -i", "Provide --description, or use --from-file / -i"),
                    err=True,
                    fg=typer.colors.RED,
                )
                raise typer.Exit(code=2)
            op_name = normalize_operator_name(name)
            operators[op_name] = build_operator_spec(
                description=description,
                input_keys=input_keys,
                output_keys=output_keys,
                requires_llm=requires_llm,
                category=category,
                name=op_name,
            )

        out = add_manual_operators(
            store,
            operators,
            pipeline_id=pid,
            scope=sc,  # type: ignore[arg-type]
            overwrite=overwrite,
        )
    except ManualOperatorError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    _print_add_result(out, as_json=as_json)


@operators_app.command("remove")
def cmd_remove(
    name: Annotated[str, typer.Argument(help="要删除的算子名")],
    pipeline_id: Annotated[str, typer.Option("--pipeline-id", "-p", help="pipeline id")],
    scope: _ScopeOpt = "task",
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """从 task / domain / general 记忆层删除手动或进化写入的算子（不能删 base）。"""
    r = _resolve_root(root)
    pid = _validate_pipeline_id(pipeline_id)
    sc = scope.strip().lower()
    if sc not in ("task", "domain", "general"):
        raise typer.BadParameter("scope must be task|domain|general")
    store = _store(r, pid)
    try:
        out = remove_manual_operator(store, name, scope=sc)  # type: ignore[arg-type]
    except ManualOperatorError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
    if as_json:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    elif out.get("removed"):
        typer.secho(_tr("已删除", "Removed") + f" {out['name']} @ {out.get('path')}", fg=typer.colors.GREEN)
    else:
        typer.secho(out.get("detail", "not found"), fg=typer.colors.YELLOW)


@operators_app.command("show")
def cmd_show(
    name: Annotated[str, typer.Argument(help="算子名")],
    pipeline_id: Annotated[str | None, typer.Option("--pipeline-id", "-p")] = None,
    root: _RootOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """查看合并后某算子的完整规格。"""
    r = _resolve_root(root)
    pid = _validate_pipeline_id(pipeline_id) if pipeline_id else None
    store = _store(r, pid)
    n = normalize_operator_name(name)
    merged = store.merged_raw()
    if n not in merged:
        typer.secho(_tr(f"未找到算子: {n}", f"Operator not found: {n}"), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    spec = merged[n]
    layer = "base"
    if n in store.load_task():
        layer = "task"
    elif n in store.load_domain():
        layer = "domain"
    elif n in store.load_general():
        layer = "general"
    payload = {"name": n, "source_layer": layer, "spec": spec}
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"{n}  ({layer})")
        typer.echo(json.dumps(spec, ensure_ascii=False, indent=2))
