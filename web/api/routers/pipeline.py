"""
按 pipeline_id 提供：会话、预览、理解、编排/实例化/试运行/质检/经验的只读查询，以及全量执行（run / run-full）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.llm_client import LLMClientError
from subsystems.observability.token_usage_ledger import append_token_event
from subsystems.pipeline_session import get_latest_manifest_record, preview_repo_file
from subsystems.pipeline_runtime import execute_generated_pipeline
from subsystems.structured_understanding import load_understanding_result, run_understanding

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_PIPELINE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

PreviewKind = Literal["raw", "seed", "description"]


def _validate_pipeline_id(pipeline_id: str) -> str:
    pid = pipeline_id.strip()
    if not _PIPELINE_ID_RE.match(pid):
        raise HTTPException(
            status_code=400,
            detail="pipeline_id 无效：仅允许字母、数字、下划线、连字符，长度 1–128",
        )
    return pid


def _file_list_for_kind(record: dict[str, Any], kind: PreviewKind) -> list[str]:
    if kind == "raw":
        key = "raw_data_files"
    elif kind == "seed":
        key = "seed_data_files"
    else:
        key = "description_data_files"
    files = record.get(key) or []
    return [str(x) for x in files if isinstance(x, str)]


@router.get("/{pipeline_id}/session")
def get_pipeline_session(request: Request, pipeline_id: str) -> dict[str, Any]:
    """返回 manifest 中该 pipeline 的最后一次记录。"""
    pid = _validate_pipeline_id(pipeline_id)
    root = request.app.state.config.root
    manifest_path = root / "data" / "manifest.jsonl"
    record = get_latest_manifest_record(manifest_path, pid)
    if not record:
        raise HTTPException(status_code=404, detail=f"未找到 pipeline_id={pid} 的 manifest 记录")
    return {"ok": True, "pipeline_id": pid, "record": record}


@router.get("/{pipeline_id}/preview/{kind}")
def get_preview(
    request: Request,
    pipeline_id: str,
    kind: PreviewKind,
    index: int = Query(0, ge=0, description="同一类多个文件时的下标"),
    max_lines: int = Query(80, ge=1, le=400),
    max_chars: int = Query(96_000, ge=1_000, le=500_000),
) -> dict[str, Any]:
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    manifest_path = root / "data" / "manifest.jsonl"
    record = get_latest_manifest_record(manifest_path, pid)
    if not record:
        raise HTTPException(status_code=404, detail="manifest 中无此 pipeline")

    files = _file_list_for_kind(record, kind)
    if not files:
        raise HTTPException(status_code=404, detail=f"该会话没有 {kind} 类文件")
    if index >= len(files):
        raise HTTPException(status_code=400, detail=f"index 超出范围（共 {len(files)} 个文件）")

    rel = files[index]
    pv = preview_repo_file(root, rel, max_lines=max_lines, max_chars=max_chars)
    return {
        "ok": bool(pv.get("ok")),
        "pipeline_id": pid,
        "kind": kind,
        "file_index": index,
        "relative_path": rel,
        **pv,
    }


class UnderstandBody(BaseModel):
    """理解阶段模式：auto 有 Key 则走极简 LLM 语言判定，否则启发式 stub。"""

    mode: Literal["auto", "stub", "llm"] = Field(default="auto")


@router.post("/{pipeline_id}/understand")
def post_understand(
    request: Request,
    pipeline_id: str,
    body: UnderstandBody = UnderstandBody(),
) -> dict[str, Any]:
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    mode = body.mode
    cm = request.app.state.config
    llm_cfg = cm.llm_config()

    tracker = request.app.state.token_usage_tracker

    def on_usage(
        *,
        input_tokens: int,
        output_tokens: int,
        model: str | None = None,
        operation: str | None = None,
        duration_ms: float | int | None = None,
        request_id: str | None = None,
        api_host: str | None = None,
        **_: Any,
    ) -> None:
        m = model or str(llm_cfg.get("model") or "")
        tracker.record(input_tokens=input_tokens, output_tokens=output_tokens, model=model)
        append_token_event(
            root,
            pid,
            workflow_step="api.post_understand",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=m,
            operation=operation or "understanding.unified_profile",
            duration_ms=duration_ms,
            request_id=request_id,
            api_host=api_host,
        )

    try:
        result = run_understanding(
            root,
            pid,
            mode=mode,
            llm_config=llm_cfg,
            on_usage=on_usage,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMClientError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}") from e

    return {"ok": True, "pipeline_id": pid, "result": result}


@router.get("/{pipeline_id}/understanding/result")
def get_understanding_result(request: Request, pipeline_id: str) -> dict[str, Any]:
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    data = load_understanding_result(root, pid)
    if not data:
        raise HTTPException(status_code=404, detail="尚无理解结果，请先调用 POST .../understand")
    return {"ok": True, "pipeline_id": pid, "data": data}


class RunPipelineBody(BaseModel):
    """全量执行：需已完成实例化（`generated_pipelines/{id}.json`）。"""

    max_input_records: int | None = Field(
        default=None,
        ge=1,
        description="限制 read_data 后最大条数；默认不截断",
    )
    llm_max_records_per_step: int = Field(
        default=32,
        ge=1,
        le=500,
        description="每个 LLM 算子最多处理行数，超出部分原样透传拼回",
    )
    execution_mode: Literal["in_process", "subprocess"] = Field(
        default="in_process",
        description="subprocess：无内置 handler 的步骤用子进程跑 operator_stub；read/write/LLM 仍在进程内",
    )
    subprocess_fallback_in_process: bool = Field(
        default=True,
        description="子进程失败时是否回退到进程内加载 stub",
    )
    subprocess_timeout_sec: float = Field(
        default=600.0,
        ge=10.0,
        le=86400.0,
        description="单步子进程超时（秒）",
    )


def _execute_pipeline_run(request: Request, pipeline_id: str, body: RunPipelineBody) -> dict[str, Any]:
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    cm = request.app.state.config
    llm_cfg = cm.llm_config()
    tracker = request.app.state.token_usage_tracker

    def on_usage(
        *,
        input_tokens: int,
        output_tokens: int,
        model: str | None = None,
        operation: str | None = None,
        duration_ms: float | int | None = None,
        request_id: str | None = None,
        api_host: str | None = None,
        **_: Any,
    ) -> None:
        m = model or str(llm_cfg.get("model") or "")
        tracker.record(input_tokens=input_tokens, output_tokens=output_tokens, model=model)
        append_token_event(
            root,
            pid,
            workflow_step="api.post_run_pipeline",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=m,
            operation=operation,
            duration_ms=duration_ms,
            request_id=request_id,
            api_host=api_host,
        )

    try:
        report = execute_generated_pipeline(
            root,
            pid,
            llm_config=llm_cfg,
            on_usage=on_usage,
            max_input_records=body.max_input_records,
            llm_max_records_per_step=body.llm_max_records_per_step,
            execution_mode=body.execution_mode,
            subprocess_fallback_in_process=body.subprocess_fallback_in_process,
            subprocess_timeout_sec=body.subprocess_timeout_sec,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMClientError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}") from e

    report.pop("records", None)
    if report.get("status") != "success":
        raise HTTPException(
            status_code=500,
            detail={"message": "管线执行未成功", "report": report},
        )
    return {"ok": True, "pipeline_id": pid, "report": report}


@router.post("/{pipeline_id}/run")
@router.post("/{pipeline_id}/run-full")
def post_run_pipeline(
    request: Request,
    pipeline_id: str,
    body: RunPipelineBody = RunPipelineBody(),
) -> dict[str, Any]:
    """
    按实例化快照执行完整数据处理管线，写出 `write_data` 路径及 `run_pipeline_results/.../output.jsonl`。
    含 LLM 算子时必须配置 API Key。

    `run` 与 `run-full` 行为一致（后者与前端页面历史路径对齐）。
    """
    return _execute_pipeline_run(request, pipeline_id, body)


# --- 编排 / 实例化 / 试运行 / 质检 / 经验：读落盘，供前端画布与分步页对接 ---


@router.get("/{pipeline_id}/orchestration")
def get_orchestration_full(request: Request, pipeline_id: str) -> dict[str, Any]:
    """返回 `data/orchestration_results/{id}.json` 全文（体积可能较大）。"""
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    path = root / "data" / "orchestration_results" / f"{pid}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无编排结果，请先完成 workflow 编排步或存在对应 JSON")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"编排文件无法解析: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="编排 JSON 根类型无效")
    return {
        "ok": True,
        "pipeline_id": pid,
        "relative_path": f"data/orchestration_results/{pid}.json",
        "data": data,
    }


@router.get("/{pipeline_id}/orchestration/dag")
def get_orchestration_dag(request: Request, pipeline_id: str) -> dict[str, Any]:
    """
    编排摘要：DAG、`final_pipeline`、`pipeline_plan`、DAG 校验摘要、试运行/全量执行摘要（若已写入编排文件）。
    """
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    path = root / "data" / "orchestration_results" / f"{pid}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无编排结果")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"编排文件无法解析: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="编排 JSON 根类型无效")
    cs = data.get("constrained_search")
    final_from_cs = cs.get("final_pipeline") if isinstance(cs, dict) else None
    final_pipeline = data.get("final_pipeline")
    if not isinstance(final_pipeline, list) and isinstance(final_from_cs, list):
        final_pipeline = final_from_cs
    return {
        "ok": True,
        "pipeline_id": pid,
        "relative_path": f"data/orchestration_results/{pid}.json",
        "dag": data.get("dag"),
        "final_pipeline": final_pipeline if isinstance(final_pipeline, list) else [],
        "pipeline_plan": data.get("pipeline_plan"),
        # 画布需从 constrained_search.validation_result 拉 issues；顶层 final_pipeline 与 cs 内可能重复，体积可接受
        "constrained_search": cs if isinstance(cs, dict) else None,
        "dag_validation": data.get("dag_validation"),
        "trial_run_check": data.get("trial_run_check"),
        "pipeline_run_summary": data.get("pipeline_run_summary"),
        "meta": data.get("meta"),
        "source": data.get("source"),
    }


@router.get("/{pipeline_id}/instantiation")
def get_instantiation_bundle(request: Request, pipeline_id: str) -> dict[str, Any]:
    """返回实例化主 JSON（默认不含各步 `code`，避免响应过大）。"""
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    path = root / "data" / "generated_pipelines" / f"{pid}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无实例化产物，请先完成 workflow 实例化步")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"实例化文件无法解析: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="实例化 JSON 根类型无效")
    steps = data.get("steps")
    slim_steps: list[dict[str, Any]] = []
    if isinstance(steps, list):
        for s in steps:
            if isinstance(s, dict):
                slim = {k: v for k, v in s.items() if k != "code"}
                slim_steps.append(slim)
    out = {k: v for k, v in data.items() if k != "steps"}
    out["steps"] = slim_steps
    return {
        "ok": True,
        "pipeline_id": pid,
        "relative_path": f"data/generated_pipelines/{pid}.json",
        "data": out,
    }


@router.get("/{pipeline_id}/instantiation/steps")
def get_instantiation_steps(
    request: Request,
    pipeline_id: str,
    include_code: bool = Query(False, description="为 true 时返回每步完整桩源码（体积大）"),
) -> dict[str, Any]:
    """实例化分步列表，供「实例化进度」类 UI 使用。"""
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    path = root / "data" / "generated_pipelines" / f"{pid}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无实例化产物")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"实例化文件无法解析: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="实例化 JSON 根类型无效")
    raw_steps = data.get("steps")
    steps_out: list[dict[str, Any]] = []
    if isinstance(raw_steps, list):
        for s in raw_steps:
            if not isinstance(s, dict):
                continue
            if include_code:
                steps_out.append(dict(s))
            else:
                steps_out.append({k: v for k, v in s.items() if k != "code"})
    return {
        "ok": True,
        "pipeline_id": pid,
        "relative_path": f"data/generated_pipelines/{pid}.json",
        "meta": data.get("meta"),
        "total_steps": len(steps_out),
        "steps": steps_out,
    }


@router.get("/{pipeline_id}/run/latest")
def get_pipeline_run_latest(request: Request, pipeline_id: str) -> dict[str, Any]:
    """
    最近一次全量执行的 `latest.json` 指针；若存在对应 `run_report.json` 一并返回（不含 records 大数组）。
    """
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    latest_path = root / "data" / "run_pipeline_results" / pid / "latest.json"
    if not latest_path.is_file():
        return {"ok": True, "pipeline_id": pid, "latest": None, "report": None}
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": True, "pipeline_id": pid, "latest": None, "report": None}
    report: dict[str, Any] | None = None
    if isinstance(latest, dict):
        run_dir_rel = latest.get("run_dir")
        if isinstance(run_dir_rel, str):
            rr = root / run_dir_rel / "run_report.json"
            if rr.is_file():
                try:
                    report = json.loads(rr.read_text(encoding="utf-8"))
                    if isinstance(report, dict):
                        report.pop("records", None)
                except (OSError, json.JSONDecodeError, TypeError):
                    report = None
    return {"ok": True, "pipeline_id": pid, "latest": latest, "report": report}


@router.get("/{pipeline_id}/trial")
def get_trial_result(request: Request, pipeline_id: str) -> dict[str, Any]:
    """读取 `data/trial_runs/{id}/trial_result.json`。"""
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    path = root / "data" / "trial_runs" / pid / "trial_result.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无试运行结果")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"试运行文件无法解析: {e}") from e
    return {
        "ok": True,
        "pipeline_id": pid,
        "relative_path": f"data/trial_runs/{pid}/trial_result.json",
        "data": data,
    }


@router.get("/{pipeline_id}/quality-check")
def get_quality_check(request: Request, pipeline_id: str) -> dict[str, Any]:
    """读取 workflow 质检步落盘 `data/quality_check_results/{id}.json`。"""
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    path = root / "data" / "quality_check_results" / f"{pid}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无质检结果")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"质检文件无法解析: {e}") from e
    return {
        "ok": True,
        "pipeline_id": pid,
        "relative_path": f"data/quality_check_results/{pid}.json",
        "data": data,
    }


@router.get("/{pipeline_id}/experience")
def get_experience(request: Request, pipeline_id: str) -> dict[str, Any]:
    """读取 workflow 经验步落盘 `data/experiences/{id}.json`。"""
    root = request.app.state.config.root
    pid = _validate_pipeline_id(pipeline_id)
    path = root / "data" / "experiences" / f"{pid}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无经验快照")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"经验文件无法解析: {e}") from e
    return {
        "ok": True,
        "pipeline_id": pid,
        "relative_path": f"data/experiences/{pid}.json",
        "data": data,
    }
