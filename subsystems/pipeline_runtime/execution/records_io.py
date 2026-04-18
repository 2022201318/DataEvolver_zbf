"""JSONL / JSON 记录读写（相对仓库根路径，防目录穿越）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_records_from_rel_path(
    root: Path,
    rel: str,
    *,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    if not rel or not isinstance(rel, str):
        raise ValueError("缺少 file_path")
    path = (root / rel).resolve()
    root_r = root.resolve()
    if not str(path).startswith(str(root_r)):
        raise ValueError("路径越界")
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {rel}")
    out: list[dict[str, Any]] = []
    if path.suffix.lower() == ".jsonl":
        with open(path, encoding="utf-8") as f:
            for line in f:
                if max_rows is not None and len(out) >= max_rows:
                    break
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
        return out
    if path.suffix.lower() == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for obj in data:
                if max_rows is not None and len(out) >= max_rows:
                    break
                if isinstance(obj, dict):
                    out.append(obj)
        elif isinstance(data, dict):
            out.append(data)
        return out
    raise ValueError(f"不支持的格式: {path.suffix}")


def write_records_jsonl(root: Path, rel: str, records: list[dict[str, Any]]) -> None:
    if not rel or not isinstance(rel, str):
        raise ValueError("缺少 file_path")
    path = (root / rel).resolve()
    root_r = root.resolve()
    if not str(path).startswith(str(root_r)):
        raise ValueError("路径越界")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
