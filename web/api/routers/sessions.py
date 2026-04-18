"""
会话与上传：将用户上传保存到仓库 `data/` 下，并追加 `data/manifest.jsonl`。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

router = APIRouter(prefix="/sessions", tags=["sessions"])

_PIPELINE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _safe_filename(name: str | None) -> str:
    if not name:
        return "upload.bin"
    return Path(name).name


async def _write_upload(dest: Path, upload: UploadFile) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = await upload.read()
    dest.write_bytes(data)


@router.post("/start")
async def start_session(
    request: Request,
    pipeline_id: str = Form(...),
    domain: str = Form(""),
    task_type: str = Form(""),
    language: str = Form(""),
    raw_file: UploadFile | None = File(None),
    seed_file: UploadFile | None = File(None),
    description_file: UploadFile | None = File(None),
) -> dict[str, Any]:
    root: Path = request.app.state.config.root
    pid = pipeline_id.strip()
    if not _PIPELINE_ID_RE.match(pid):
        raise HTTPException(
            status_code=400,
            detail="pipeline_id 无效：仅允许字母、数字、下划线、连字符，长度 1–128",
        )

    base = root / "data" / "uploads" / pid
    raw_dir = base / "raw_data"
    seed_dir = base / "seed_data"
    desc_dir = base / "description"

    raw_paths: list[str] = []
    seed_paths: list[str] = []
    desc_paths: list[str] = []
    saved: dict[str, str | None] = {"raw": None, "seed": None, "description": None}

    if raw_file is not None and raw_file.filename:
        fn = _safe_filename(raw_file.filename)
        dest = raw_dir / fn
        await _write_upload(dest, raw_file)
        rel = f"data/uploads/{pid}/raw_data/{fn}"
        raw_paths.append(rel)
        saved["raw"] = rel

    if seed_file is not None and seed_file.filename:
        fn = _safe_filename(seed_file.filename)
        dest = seed_dir / fn
        await _write_upload(dest, seed_file)
        rel = f"data/uploads/{pid}/seed_data/{fn}"
        seed_paths.append(rel)
        saved["seed"] = rel

    if description_file is not None and description_file.filename:
        fn = _safe_filename(description_file.filename)
        dest = desc_dir / fn
        await _write_upload(dest, description_file)
        rel = f"data/uploads/{pid}/description/{fn}"
        desc_paths.append(rel)
        saved["description"] = rel

    record: dict[str, Any] = {
        "pipeline_id": pid,
        "raw_data_files": raw_paths,
        "seed_data_files": seed_paths,
    }
    if desc_paths:
        record["description_data_files"] = desc_paths
    if domain.strip():
        record["domain"] = domain.strip()
    if task_type.strip():
        record["task_type"] = task_type.strip()
    if language.strip():
        record["language"] = language.strip()

    manifest_path = root / "data" / "manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(line)

    return {
        "ok": True,
        "pipeline_id": pid,
        "manifest_record": record,
        "saved_paths": saved,
    }
