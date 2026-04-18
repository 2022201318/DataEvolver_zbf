"""
结构化理解：stub（无 Key）或完整多步 LLM（对齐旧版 UnderstandingAnalyzerSimple）。

落盘：`data/understanding_results/{pipeline_id}.json`
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from core.llm_client import LLMClientError
from subsystems.pipeline_session.file_preview import preview_repo_file
from subsystems.pipeline_session.manifest_store import get_latest_manifest_record
from subsystems.structured_understanding.full_analyzer import run_full_understanding

UnderstandingMode = Literal["auto", "stub", "llm"]


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return cjk / max(len(text), 1)


def _latin_ratio(text: str) -> float:
    if not text:
        return 0.0
    lat = sum(1 for c in text if ("a" <= c.lower() <= "z"))
    return lat / max(len(text), 1)


def heuristic_content_language(sample: str) -> tuple[str, str]:
    t = sample[:50_000]
    cr = _cjk_ratio(t)
    lr = _latin_ratio(t)
    if cr > 0.08 and lr > 0.04:
        return "mixed", "Mixed Chinese-English"
    if cr > 0.06:
        return "zh", "Chinese"
    if lr > 0.15:
        return "en", "English"
    return "unknown", "Unknown"


def build_stub_profile(
    *,
    pipeline_id: str,
    record: dict[str, Any],
    content_language: str,
    language_label: str,
    understanding_mode: str,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    user_lang = record.get("language")
    domain = record.get("domain")
    task_type = record.get("task_type")
    meta: dict[str, Any] = {
        "understanding_mode": understanding_mode,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "design_note": "content_language 用于驱动后续经验、报告等自然语言展示语言；UI 语言仍独立。",
    }
    if fallback_reason:
        meta["fallback_reason"] = fallback_reason
    return {
        "pipeline_id": pipeline_id,
        "language": content_language,
        "language_label": language_label,
        "user_declared_language": user_lang if isinstance(user_lang, str) and user_lang.strip() else None,
        "domain": domain if isinstance(domain, str) else None,
        "task_type": task_type if isinstance(task_type, str) else None,
        "basic_information": {
            "language": language_label,
            "content_language_code": content_language,
            "user_declared_language": user_lang if isinstance(user_lang, str) and user_lang.strip() else None,
            "file_format_analysis": {
                "note": "stub: 无 API Key 或完整理解失败回退",
                "raw_files": len(record.get("raw_data_files") or []),
                "seed_files": len(record.get("seed_data_files") or []),
                "description_files": len(record.get("description_data_files") or []),
            },
            "seed_vs_raw_quality": {
                "note": "stub: 占位",
            },
            "processing_targets": [
                "stub: 配置 API Key 后使用完整多步理解（basic / schema / dataset_delta）",
            ],
            "domain_characteristics": domain or "unknown",
            "transformation_direction": "stub: raw → seed 对齐（待完整分析）",
            "quality_standards": "stub: 待完整质量维度抽取",
        },
        "schema_analysis": {
            "note": "stub: 完整理解将输出 raw_fields / seed_fields 等",
        },
        "dataset_level_delta": {
            "note": "stub: 完整理解将输出 key_improvements / summary 等",
        },
        "content_slot_library": {},
        "quality_rubrics": {},
        "meta": meta,
    }


def _collect_sample_text(
    root: Path,
    record: dict[str, Any],
    *,
    preview_lines: int = 24,
) -> tuple[str, str, str]:
    raw_texts: list[str] = []
    for rel in record.get("raw_data_files") or []:
        if isinstance(rel, str):
            pv = preview_repo_file(root, rel, max_lines=preview_lines, max_chars=24_000)
            if pv.get("ok"):
                raw_texts.extend(pv.get("lines") or [])
    seed_texts: list[str] = []
    for rel in record.get("seed_data_files") or []:
        if isinstance(rel, str):
            pv = preview_repo_file(root, rel, max_lines=preview_lines, max_chars=24_000)
            if pv.get("ok"):
                seed_texts.extend(pv.get("lines") or [])
    desc_texts: list[str] = []
    for rel in record.get("description_data_files") or []:
        if isinstance(rel, str):
            pv = preview_repo_file(root, rel, max_lines=preview_lines, max_chars=16_000)
            if pv.get("ok"):
                desc_texts.extend(pv.get("lines") or [])
    return "\n".join(raw_texts), "\n".join(seed_texts), "\n".join(desc_texts)


def run_understanding(
    root: Path,
    pipeline_id: str,
    *,
    mode: UnderstandingMode = "auto",
    llm_config: dict[str, Any] | None = None,
    on_usage: Any | None = None,
) -> dict[str, Any]:
    """
    执行理解并写入 `data/understanding_results/{pipeline_id}.json`。
    - `stub`：启发式语言 + 占位结构。
    - `llm` / `auto`（且已配置 Key）：**三次 LLM 调用**（basic → schema → delta），对齐旧版。
    - `auto` 且 LLM 失败：回退 stub，`meta.fallback_reason` 记录原因。
    """
    manifest_path = root / "data" / "manifest.jsonl"
    record = get_latest_manifest_record(manifest_path, pipeline_id)
    if not record:
        raise FileNotFoundError(f"manifest 中未找到 pipeline_id={pipeline_id!r}")

    raw_s, seed_s, _desc_s = _collect_sample_text(root, record)
    combined = "\n".join([raw_s, seed_s])
    if not combined.strip():
        raise ValueError("未找到可读取的 raw/seed 文件内容，请先完成上传会话")

    llm_cfg = llm_config or {}
    has_key = bool(str(llm_cfg.get("api_key") or "").strip())

    use_llm = mode == "llm" or (mode == "auto" and has_key)
    if mode == "llm" and not has_key:
        raise ValueError("mode=llm 需要配置 API Key")

    if not use_llm:
        content_language, language_label = heuristic_content_language(combined)
        result = build_stub_profile(
            pipeline_id=pipeline_id,
            record=record,
            content_language=content_language,
            language_label=language_label,
            understanding_mode="stub",
        )
    else:
        try:
            result = run_full_understanding(
                root,
                pipeline_id,
                record,
                llm_cfg,
                on_usage=on_usage,
            )
            result["meta"] = {
                "understanding_mode": "full_llm",
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "llm_steps": ["unified_profile"],
            }
        except (LLMClientError, ValueError, OSError, json.JSONDecodeError) as e:
            if mode == "llm":
                raise
            content_language, language_label = heuristic_content_language(combined)
            result = build_stub_profile(
                pipeline_id=pipeline_id,
                record=record,
                content_language=content_language,
                language_label=language_label,
                understanding_mode="stub_fallback",
                fallback_reason=str(e),
            )

    out_dir = root / "data" / "understanding_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pipeline_id}.json"
    prev = load_understanding_result(root, pipeline_id)
    if prev:
        if isinstance(prev.get("orchestration_assessment_feedback"), dict):
            result["orchestration_assessment_feedback"] = prev["orchestration_assessment_feedback"]
        if isinstance(prev.get("pilot_run_feedback_history"), list):
            result["pilot_run_feedback_history"] = list(prev["pilot_run_feedback_history"])
        if isinstance(prev.get("pilot_run_feedback"), dict):
            result["pilot_run_feedback"] = prev["pilot_run_feedback"]
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["saved_path"] = f"data/understanding_results/{pipeline_id}.json"
    return result


def load_understanding_result(root: Path, pipeline_id: str) -> dict[str, Any] | None:
    p = root / "data" / "understanding_results" / f"{pipeline_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
