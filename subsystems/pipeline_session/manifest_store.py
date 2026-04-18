"""读取 `data/manifest.jsonl`，按 `pipeline_id` 取最后一次出现的记录。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def read_manifest_records(manifest_path: Path) -> Iterator[dict[str, Any]]:
    if not manifest_path.exists():
        return
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("pipeline_id"):
                yield rec


def get_latest_manifest_record(manifest_path: Path, pipeline_id: str) -> dict[str, Any] | None:
    pid = pipeline_id.strip()
    last: dict[str, Any] | None = None
    for rec in read_manifest_records(manifest_path):
        if str(rec.get("pipeline_id", "")).strip() == pid:
            last = rec
    return last
