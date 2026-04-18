"""
为 read_data / write_data 补全 `parameters.file_path`，与 manifest 及 orchestrator 默认约定一致。

编排可能已包含首尾 IO 算子但漏写路径；实例化与编排落盘前应调用，避免 trial / execute 读到 None。
"""

from __future__ import annotations

from typing import Any


def apply_manifest_file_paths_to_pipeline(
    steps: list[dict[str, Any]],
    *,
    pipeline_id: str,
    manifest_record: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not steps:
        return steps
    rec = manifest_record if isinstance(manifest_record, dict) else {}
    raw_files = [x for x in (rec.get("raw_data_files") or []) if isinstance(x, str)]
    read_path = raw_files[0] if raw_files else f"data/uploads/{pipeline_id}/raw_data/{pipeline_id}_raw.jsonl"
    write_path = f"data/uploads/{pipeline_id}/outputs/{pipeline_id}_processed.jsonl"

    for step in steps:
        if not isinstance(step, dict):
            continue
        op = step.get("operator")
        params = step.get("parameters")
        if not isinstance(params, dict):
            params = {}
        if op == "read_data":
            fp = params.get("file_path")
            if fp is None or (isinstance(fp, str) and not str(fp).strip()):
                step["parameters"] = {**params, "file_path": read_path}
        elif op == "write_data":
            fp = params.get("file_path")
            if fp is None or (isinstance(fp, str) and not str(fp).strip()):
                step["parameters"] = {**params, "file_path": write_path}
    return steps
