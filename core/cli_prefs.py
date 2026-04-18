"""
CLI 用户偏好（轻量、本地）：

- 全局（推荐）：~/.config/dataevolver/cli_prefs.json 或 $XDG_CONFIG_HOME/dataevolver/cli_prefs.json
- 项目级（兼容）：<repo_root>/data/cli_prefs.json

目的：一次命令切换中英文，后续所有 CLI 默认生效；同时允许项目级覆盖（可选）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _project_prefs_path(project_root: Path) -> Path:
    return project_root / "data" / "cli_prefs.json"


def _global_prefs_path() -> Path:
    base = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    root = Path(base).expanduser().resolve() if base else (Path.home() / ".config")
    return root / "dataevolver" / "cli_prefs.json"


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_cli_prefs(project_root: Path | None = None) -> dict[str, Any]:
    """
    合并读取：先读全局，再读项目级（若提供 project_root，且文件存在则覆盖同名键）。
    """
    prefs = dict(_read_json_dict(_global_prefs_path()))
    if project_root is not None:
        prefs.update(_read_json_dict(_project_prefs_path(project_root)))
    return prefs


def save_global_cli_prefs(prefs: dict[str, Any]) -> str:
    p = _global_prefs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(prefs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return str(p)


def save_project_cli_prefs(project_root: Path, prefs: dict[str, Any]) -> str:
    p = _project_prefs_path(project_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(prefs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return str(p.relative_to(project_root))

