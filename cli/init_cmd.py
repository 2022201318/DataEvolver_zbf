"""`dataevolver init` — create a workspace for PyPI / portable installs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from cli.i18n import tr, t
from core.workspace import materialize_workspace


def register_init_command(app: typer.Typer) -> None:
    @app.command("init", help=t("init.doc"))
    def cmd_init(
        directory: Annotated[
            Optional[Path],
            typer.Argument(help=t("init.target")),
        ] = None,
        force: Annotated[
            bool,
            typer.Option("--force", help=t("init.force")),
        ] = False,
        as_json: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        target = (directory or Path.cwd()).resolve()
        result = materialize_workspace(target, force=force)
        if as_json:
            typer.echo(
                json.dumps(
                    {"ok": True, "workspace": str(target), **result},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        typer.secho(
            tr(f"工作区已初始化: {target}", f"Workspace initialized: {target}"),
            fg=typer.colors.GREEN,
        )
        if result["created"]:
            typer.echo(tr("已创建:", "Created:"))
            for p in result["created"]:
                typer.echo(f"  + {p}")
        if result["skipped"]:
            typer.echo(tr("已跳过（已存在）:", "Skipped (already exists):"))
            for p in result["skipped"]:
                typer.echo(f"  · {p}")
        typer.secho(
            tr(
                "\n下一步: 编辑 config/api_config.json 与 config/api_keys.json，然后运行 dataevolver --help",
                "\nNext: edit config/api_config.json and config/api_keys.json, then run dataevolver --help",
            ),
            fg=typer.colors.BLUE,
        )
