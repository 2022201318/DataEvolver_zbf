"""
Resolve the DataEvolver **workspace** (runtime project root) and ship default templates.

- **Editable / git checkout**: repository root (`core/../`) with `config/` + `data/`.
- **PyPI install**: user runs `dataevolver init` in a directory; templates come from `core/_bundled/`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_BUNDLED = Path(__file__).resolve().parent / "_bundled"


class WorkspaceNotFoundError(FileNotFoundError):
    """No valid workspace root could be resolved."""


def bundled_dir() -> Path:
    return _BUNDLED


def is_workspace(root: Path) -> bool:
    return (root / "config").is_dir() and (root / "data").is_dir()


def resolve_project_root(explicit: str | Path | None = None) -> Path:
    """
  Resolution order:
  1. explicit path (--root / argument)
  2. DATAEVOLVER_ROOT
  3. parent of `core/` when it is a git/source tree (editable install)
  4. current working directory
    """
    if explicit is not None:
        root = Path(explicit).expanduser().resolve()
        if not is_workspace(root):
            raise WorkspaceNotFoundError(
                f"Not a DataEvolver workspace (missing config/ or data/): {root}"
            )
        return root

    env = (os.environ.get("DATAEVOLVER_ROOT") or "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if is_workspace(root):
            return root

    source_root = Path(__file__).resolve().parent.parent
    if is_workspace(source_root):
        return source_root

    cwd = Path.cwd().resolve()
    if is_workspace(cwd):
        return cwd

    raise WorkspaceNotFoundError(
        "DataEvolver workspace not found.\n"
        "  • From a git clone: run commands inside the repository root.\n"
        "  • From PyPI: run `dataevolver init` in your project directory first,\n"
        "    or set DATAEVOLVER_ROOT to a directory that contains config/ and data/."
    )


def _copy_if_missing(src: Path, dst: Path, *, force: bool) -> bool:
    if dst.exists() and not force:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def materialize_workspace(target: Path, *, force: bool = False) -> dict[str, list[str]]:
    """
    Create config/ and data/ under `target` from bundled templates.
    Returns lists of created paths (relative to target).
    """
    root = target.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    skipped: list[str] = []

    bundled_cfg = _BUNDLED / "config"
    bundled_data = _BUNDLED / "data"

    mapping = [
        (bundled_cfg / "config.json", root / "config" / "config.json"),
        (bundled_cfg / "api_config.example.json", root / "config" / "api_config.json"),
        (bundled_cfg / "api_keys.example.json", root / "config" / "api_keys.json"),
    ]
    for src, dst in mapping:
        if not src.is_file():
            continue
        if _copy_if_missing(src, dst, force=force):
            created.append(str(dst.relative_to(root)))
        else:
            skipped.append(str(dst.relative_to(root)))

    if bundled_data.is_dir():
        for src in bundled_data.iterdir():
            if not src.is_file():
                continue
            dst = root / "data" / src.name
            if _copy_if_missing(src, dst, force=force):
                created.append(str(dst.relative_to(root)))
            else:
                skipped.append(str(dst.relative_to(root)))

    # Runtime subdirectories (gitignored in dev, created on first use)
    from core.path_manager import PathManager

    PathManager(root)
    return {"created": created, "skipped": skipped}
