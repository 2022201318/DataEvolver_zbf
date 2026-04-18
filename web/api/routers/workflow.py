"""
主流程分步推进 API，与画布「推进一步」语义对齐（前端可后续对接）。

步骤顺序（发布语义）：理解 → 编排（含 DAG 校验）→ 算子进化 → 实例化 → 试运行 → 质量评估；
若未达标再进入经验回流并重启下一轮。全量执行由独立 run-full API 触发。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from subsystems.observability.token_usage_ledger import summarize_token_ledger
from subsystems.workflow import (
    WorkflowStepError,
    advance_workflow,
    load_workflow_state,
    reset_workflow_for_debug,
    rerun_workflow_from_step,
)

router = APIRouter(prefix="/workflow", tags=["workflow"])

_PIPELINE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _pid(pipeline_id: str) -> str:
    p = pipeline_id.strip()
    if not _PIPELINE_ID_RE.match(p):
        raise HTTPException(status_code=400, detail="pipeline_id 无效")
    return p


def _artifact_flags(root: Path, pipeline_id: str) -> dict[str, bool]:
    r = root
    return {
        "understanding": (r / "data" / "understanding_results" / f"{pipeline_id}.json").is_file(),
        "orchestration": (r / "data" / "orchestration_results" / f"{pipeline_id}.json").is_file(),
        "instantiation": (r / "data" / "generated_pipelines" / f"{pipeline_id}.json").is_file(),
        "trial_run": (r / "data" / "trial_runs" / pipeline_id / "trial_result.json").is_file(),
        "pipeline_run": (r / "data" / "run_pipeline_results" / pipeline_id / "latest.json").is_file(),
        "quality_check": (r / "data" / "quality_check_results" / f"{pipeline_id}.json").is_file(),
        "experience": (r / "data" / "experiences" / f"{pipeline_id}.json").is_file(),
    }


@router.get("/{pipeline_id}/state")
def get_workflow_state(request: Request, pipeline_id: str) -> dict[str, Any]:
    root = request.app.state.config.root
    pid = _pid(pipeline_id)
    st = load_workflow_state(root, pid)
    return {
        "ok": True,
        "pipeline_id": pid,
        "state": st.to_dict(),
        "artifacts": _artifact_flags(root, pid),
    }


@router.get("/{pipeline_id}/artifact-history")
def get_artifact_history(
    request: Request,
    pipeline_id: str,
    limit: int = Query(default=80, ge=1, le=500, description="从索引尾部返回的条数"),
) -> dict[str, Any]:
    """
    返回 `data/artifact_history/{id}/index.jsonl` 中的归档记录（覆盖理解/编排前的快照）。
    用于前端按轮次展示历史卡片；与 `state.understanding_revision` / `orchestration_revision` 对照。
    """
    root = request.app.state.config.root
    pid = _pid(pipeline_id)
    idx_path = root / "data" / "artifact_history" / pid / "index.jsonl"
    rounds_path = root / "data" / "artifact_history" / pid / "rounds.jsonl"
    if not idx_path.is_file():
        return {
            "ok": True,
            "pipeline_id": pid,
            "index_path": f"data/artifact_history/{pid}/index.jsonl",
            "entries": [],
            "round_snapshots": [],
        }
    lines = idx_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-limit:] if len(lines) > limit else lines
    entries: list[dict[str, Any]] = []
    for ln in tail:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                entries.append(obj)
        except json.JSONDecodeError:
            continue
    round_snapshots: list[dict[str, Any]] = []
    if rounds_path.is_file():
        r_lines = rounds_path.read_text(encoding="utf-8", errors="replace").splitlines()
        r_tail = r_lines[-limit:] if len(r_lines) > limit else r_lines
        for ln in r_tail:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    round_snapshots.append(obj)
            except json.JSONDecodeError:
                continue
    return {
        "ok": True,
        "pipeline_id": pid,
        "index_path": f"data/artifact_history/{pid}/index.jsonl",
        "entries": entries,
        "round_snapshots": round_snapshots,
    }


class RerunBody(BaseModel):
    """从指定步骤重新执行：级联删除该步及之后产物，并将 state 置为该步。"""

    step: str = Field(
        ...,
        description="STEP_ORDER 中的键，如 understanding / orchestration / quality_check / experience",
        examples=["understanding"],
    )


class AdvanceBody(BaseModel):
    """
    force_reset_state：删除 `workflow_runs/.../state.json` 后从第 1 步重新执行本请求的 advance
    （不删除理解/编排等产物；若要重跑理解请手动删对应 json）。

    pipeline_run_* 为兼容字段：当前 workflow 主流程不依赖该步，全量执行由 run-full 触发。
    """

    force_reset_state: bool = Field(default=False)
    pipeline_run_execution_mode: Literal["in_process", "subprocess"] = Field(
        default="in_process",
        description="全量执行：是否对无内置 handler 的步骤走子进程 stub",
    )
    pipeline_run_subprocess_fallback_in_process: bool = Field(
        default=True,
        description="子进程失败时回退进程内 stub",
    )
    pipeline_run_subprocess_timeout_sec: float = Field(
        default=600.0,
        ge=10.0,
        le=86400.0,
    )


@router.post("/{pipeline_id}/advance")
def post_advance(request: Request, pipeline_id: str, body: AdvanceBody = AdvanceBody()) -> dict[str, Any]:
    root = request.app.state.config.root
    pid = _pid(pipeline_id)
    cm = request.app.state.config
    llm_cfg = cm.llm_config()
    tracker = request.app.state.token_usage_tracker

    def on_usage(*, input_tokens: int, output_tokens: int, model: str | None = None, **__: Any) -> None:
        tracker.record(input_tokens=input_tokens, output_tokens=output_tokens, model=model)

    try:
        return advance_workflow(
            root,
            pid,
            llm_config=llm_cfg,
            on_usage=on_usage,
            force=body.force_reset_state,
            pipeline_run_execution_mode=body.pipeline_run_execution_mode,
            pipeline_run_subprocess_fallback_in_process=body.pipeline_run_subprocess_fallback_in_process,
            pipeline_run_subprocess_timeout_sec=body.pipeline_run_subprocess_timeout_sec,
        )
    except WorkflowStepError as e:
        st = load_workflow_state(root, pid)
        raise HTTPException(
            status_code=422,
            detail={
                "ok": False,
                "error": "workflow_step_failed",
                "step": e.step_key,
                "message": str(e),
                "pipeline_id": pid,
                "state": st.to_dict(),
            },
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{pipeline_id}/rerun")
def post_rerun(request: Request, pipeline_id: str, body: RerunBody) -> dict[str, Any]:
    root = request.app.state.config.root
    pid = _pid(pipeline_id)
    try:
        return rerun_workflow_from_step(root, pid, body.step.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{pipeline_id}/tokens")
def get_pipeline_tokens(
    request: Request,
    pipeline_id: str,
    include_events: bool = Query(default=False, description="是否附带最近若干条 JSONL 事件"),
    max_events: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    """汇总 `data/workflow_runs/{id}/token_usage.jsonl`（workflow advance 与各 API LLM 调用写入）。"""
    root = request.app.state.config.root
    pid = _pid(pipeline_id)
    return summarize_token_ledger(root, pid, include_events=include_events, max_events=max_events)


@router.post("/{pipeline_id}/reset")
def post_reset(request: Request, pipeline_id: str) -> dict[str, Any]:
    """仅清除分步状态（`data/workflow_runs/{id}/state.json`），便于重新从第一步 advance。"""
    root = request.app.state.config.root
    pid = _pid(pipeline_id)
    sp = root / "data" / "workflow_runs" / pid / "state.json"
    existed = sp.exists()
    if existed:
        sp.unlink()
    return {"ok": True, "pipeline_id": pid, "state_removed": existed}


@router.post("/{pipeline_id}/reset-for-debug")
def post_reset_for_debug(request: Request, pipeline_id: str) -> dict[str, Any]:
    """开发调试专用：回到 round=1 的入口，并清理历史轮次与中间产物。"""
    root = request.app.state.config.root
    pid = _pid(pipeline_id)
    return reset_workflow_for_debug(root, pid)
