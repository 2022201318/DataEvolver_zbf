"""
在覆盖「当前」理解/编排 JSON 前归档副本，供 CLI/前端按轮次展示。

目录：data/artifact_history/{pipeline_id}/
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _append_index(root: Path, pipeline_id: str, line: dict[str, Any]) -> None:
    base = root / "data" / "artifact_history" / pipeline_id
    base.mkdir(parents=True, exist_ok=True)
    p = base / "index.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def archive_understanding_before_overwrite(
    root: Path,
    pipeline_id: str,
    *,
    understanding_revision: int,
    dag_evolution_cycles: int = 0,
) -> str | None:
    """
    若当前理解文件存在且 revision>=1，复制为 history 文件并写索引。
    返回相对仓库根的归档路径，未归档则 None。
    """
    src = root / "data" / "understanding_results" / f"{pipeline_id}.json"
    if not src.is_file() or understanding_revision < 1:
        return None
    dest_dir = root / "data" / "artifact_history" / pipeline_id / "understanding"
    dest_dir.mkdir(parents=True, exist_ok=True)
    tag = _iso_compact()
    name = f"r{understanding_revision:04d}_{tag}.json"
    dest = dest_dir / name
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    rel = str(dest.relative_to(root))
    _append_index(
        root,
        pipeline_id,
        {
            "kind": "understanding",
            "understanding_revision": understanding_revision,
            "orchestration_revision": None,
            "dag_evolution_cycles": dag_evolution_cycles,
            "path": rel,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return rel


def archive_orchestration_before_overwrite(
    root: Path,
    pipeline_id: str,
    *,
    orchestration_revision: int,
    understanding_revision: int = 0,
    dag_evolution_cycles: int = 0,
    round: int = 1,
) -> str | None:
    src = root / "data" / "orchestration_results" / f"{pipeline_id}.json"
    if not src.is_file() or orchestration_revision < 1:
        return None
    dest_dir = root / "data" / "artifact_history" / pipeline_id / "orchestration"
    dest_dir.mkdir(parents=True, exist_ok=True)
    tag = _iso_compact()
    name = f"r{orchestration_revision:04d}_{tag}.json"
    dest = dest_dir / name
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    rel = str(dest.relative_to(root))
    _append_index(
        root,
        pipeline_id,
        {
            "kind": "orchestration",
            "round": max(1, int(round)),
            "understanding_revision": understanding_revision,
            "orchestration_revision": orchestration_revision,
            "dag_evolution_cycles": dag_evolution_cycles,
            "path": rel,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return rel


def snapshot_round_artifacts(
    root: Path,
    pipeline_id: str,
    *,
    round_no: int,
    quality_passed: bool,
) -> dict[str, Any]:
    """
    将“本轮最终产物”归档到独立目录，供前端按轮次展示与对比。
    目录：data/artifact_history/{pipeline_id}/rounds/rXXXX/
    """
    round_no = max(1, int(round_no))
    base = root / "data" / "artifact_history" / pipeline_id
    rounds_dir = base / "rounds" / f"r{round_no:04d}"
    rounds_dir.mkdir(parents=True, exist_ok=True)

    current = root / "data"
    src_map = {
        "understanding": current / "understanding_results" / f"{pipeline_id}.json",
        "orchestration": current / "orchestration_results" / f"{pipeline_id}.json",
        "instantiation": current / "generated_pipelines" / f"{pipeline_id}.json",
        "quality_check": current / "quality_check_results" / f"{pipeline_id}.json",
        "experience": current / "experiences" / f"{pipeline_id}.json",
    }
    copied: dict[str, str] = {}
    payloads: dict[str, Any] = {}
    for key, src in src_map.items():
        if not src.is_file():
            continue
        dest = rounds_dir / f"{key}.json"
        text = src.read_text(encoding="utf-8")
        dest.write_text(text, encoding="utf-8")
        copied[key] = str(dest.relative_to(root))
        try:
            payloads[key] = json.loads(text)
        except json.JSONDecodeError:
            payloads[key] = None

    orch = payloads.get("orchestration") if isinstance(payloads.get("orchestration"), dict) else {}
    quality = payloads.get("quality_check") if isinstance(payloads.get("quality_check"), dict) else {}
    exp = payloads.get("experience") if isinstance(payloads.get("experience"), dict) else {}
    inst = payloads.get("instantiation") if isinstance(payloads.get("instantiation"), dict) else {}

    dag = orch.get("dag") if isinstance(orch, dict) else None
    dag_nodes = dag.get("nodes") if isinstance(dag, dict) else None
    inst_steps = inst.get("steps") if isinstance(inst, dict) else None
    score = quality.get("pilot_overall_score") if isinstance(quality, dict) else None
    if not isinstance(score, (int, float)):
        score = None

    line = {
        "kind": "round_snapshot",
        "round": round_no,
        "quality_passed": bool(quality_passed),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "paths": copied,
        "summary": {
            "understanding_done": "understanding" in copied,
            "dag_node_count": len(dag_nodes) if isinstance(dag_nodes, list) else 0,
            "instantiation_steps": len(inst_steps) if isinstance(inst_steps, list) else 0,
            "sample_score": score,
            "experience_text": str(exp.get("experience_text")) if isinstance(exp, dict) and exp.get("experience_text") else "",
        },
    }
    _append_index(root, pipeline_id, line)
    rp = base / "rounds.jsonl"
    with rp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


def snapshot_iteration_artifacts(
    root: Path,
    pipeline_id: str,
    *,
    round_no: int,
    dag_evolution_cycles: int,
    reason: str,
) -> dict[str, Any]:
    """
    在进入下一次编排/轮次前，保存一份“迭代级”中间产物快照。
    目录：data/artifact_history/{pipeline_id}/iterations/iXXXX/
    """
    base = root / "data" / "artifact_history" / pipeline_id
    it_dir = base / "iterations"
    it_dir.mkdir(parents=True, exist_ok=True)

    max_idx = 0
    for d in it_dir.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if name.startswith("i") and name[1:].isdigit():
            max_idx = max(max_idx, int(name[1:]))
    idx = max_idx + 1
    cur = it_dir / f"i{idx:04d}"
    cur.mkdir(parents=True, exist_ok=True)

    src_map = {
        "understanding": root / "data" / "understanding_results" / f"{pipeline_id}.json",
        "orchestration": root / "data" / "orchestration_results" / f"{pipeline_id}.json",
        "dag_assessment": root / "data" / "dag_assessment_results" / f"{pipeline_id}.json",
        "instantiation": root / "data" / "generated_pipelines" / f"{pipeline_id}.json",
        "quality_check": root / "data" / "quality_check_results" / f"{pipeline_id}.json",
        "experience": root / "data" / "experiences" / f"{pipeline_id}.json",
    }
    copied: dict[str, str] = {}
    for key, src in src_map.items():
        if not src.is_file():
            continue
        dest = cur / f"{key}.json"
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        copied[key] = str(dest.relative_to(root))

    line = {
        "kind": "iteration_snapshot",
        "iteration": idx,
        "round": max(1, int(round_no)),
        "dag_evolution_cycles": max(0, int(dag_evolution_cycles)),
        "reason": reason,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "paths": copied,
    }
    _append_index(root, pipeline_id, line)
    ip = base / "iterations.jsonl"
    with ip.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line
