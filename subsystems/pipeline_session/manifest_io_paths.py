"""
为 read_data / write_data 补全 `parameters.file_path`，与 manifest 及 orchestrator 默认约定一致。

编排可能已包含首尾 IO 算子但漏写路径；实例化与编排落盘前应调用，避免 trial / execute 读到 None。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def is_placeholder_io_path(path: str | None) -> bool:
    """LLM 编排常见占位路径，运行时不可直接使用。"""
    if path is None or not isinstance(path, str):
        return True
    p = path.strip()
    if not p:
        return True
    low = p.lower().replace("\\", "/")
    if low.startswith("path/to/") or low.startswith("/path/to/"):
        return True
    if "placeholder" in low or "your_" in low or "example/" in low:
        return True
    if low in {
        "raw_data.jsonl",
        "processed_data.jsonl",
        "output.jsonl",
        "output_file_path.jsonl",
        "path/to/raw_data.jsonl",
        "path/to/processed_data.jsonl",
    }:
        return True
    return False


def manifest_read_write_paths(
    pipeline_id: str,
    manifest_record: dict[str, Any] | None,
) -> tuple[str, str]:
    rec = manifest_record if isinstance(manifest_record, dict) else {}
    raw_files = [x for x in (rec.get("raw_data_files") or []) if isinstance(x, str)]
    read_path = raw_files[0] if raw_files else f"data/uploads/{pipeline_id}/raw_data/{pipeline_id}_raw.jsonl"
    write_path = f"data/uploads/{pipeline_id}/outputs/{pipeline_id}_processed.jsonl"
    return read_path, write_path


def resolve_io_file_path(
    rel: str | None,
    *,
    op: str,
    pipeline_id: str,
    manifest_record: dict[str, Any] | None,
    root: Path | None = None,
) -> str:
    """
    解析 read_data / write_data 的实际相对路径。
    占位路径或文件不存在时回退到 manifest 约定路径。
    """
    read_path, write_path = manifest_read_write_paths(pipeline_id, manifest_record)
    canonical = read_path if op == "read_data" else write_path
    candidate = str(rel).strip() if isinstance(rel, str) else ""
    if is_placeholder_io_path(candidate):
        return canonical
    if root is not None and candidate:
        try:
            abs_p = (root / candidate).resolve()
            if abs_p.is_file():
                return candidate
        except OSError:
            pass
        return canonical
    return candidate or canonical


def apply_manifest_file_paths_to_pipeline(
    steps: list[dict[str, Any]],
    *,
    pipeline_id: str,
    manifest_record: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not steps:
        return steps
    read_path, write_path = manifest_read_write_paths(pipeline_id, manifest_record)

    for step in steps:
        if not isinstance(step, dict):
            continue
        op = step.get("operator")
        params = step.get("parameters")
        if not isinstance(params, dict):
            params = {}
        if op == "read_data":
            # Always bind read_data to manifest raw path.
            # LLM orchestration may emit placeholders such as "path/to/raw_data.jsonl",
            # which caused runtime "file not found" and collapsed pilot score.
            step["parameters"] = {**params, "file_path": read_path}
        elif op == "write_data":
            # Always bind write_data to canonical output path for the pipeline session.
            step["parameters"] = {**params, "file_path": write_path}
    return steps
