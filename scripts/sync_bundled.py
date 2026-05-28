#!/usr/bin/env python3
"""
Sync repository config/ and data/ defaults into core/_bundled/ before a PyPI release.

Usage (from repo root):
  python scripts/sync_bundled.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLED = ROOT / "core" / "_bundled"


def main() -> None:
    pairs = [
        (ROOT / "config" / "config.json", BUNDLED / "config" / "config.json"),
        (ROOT / "config" / "api_config.example.json", BUNDLED / "config" / "api_config.example.json"),
        (ROOT / "config" / "api_keys.example.json", BUNDLED / "config" / "api_keys.example.json"),
    ]
    for src, dst in pairs:
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  config: {dst.relative_to(ROOT)}")

    for name in (
        "operator_registry.json",
        "operator_categories.json",
        "operator_registry_general.json",
        "operator_registry_user.json",
        "pipeline_templates.json",
        "README.md",
    ):
        src = ROOT / "data" / name
        if src.is_file():
            dst = BUNDLED / "data" / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  data: {dst.relative_to(ROOT)}")

    print("Bundled templates updated.")


if __name__ == "__main__":
    main()
