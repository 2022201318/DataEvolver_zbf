"""
按 `generated_pipelines/{id}.json` 的 `final_pipeline_snapshot` 顺序执行算子。

- **in_process**（默认）：内置 handler（I/O、确定性、LLM）；无内置则进程内加载 `operator_stub.py`。
- **subprocess**：对 **无内置 handler** 且存在桩文件的步骤，用 `subprocess_bridge.py` 子进程执行（对齐旧版「每步独立进程」）；`read_data` / `write_data` / 全部 LLM 算子仍在进程内。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from subsystems.operator_management.registry_store import OperatorRegistryStore

from subsystems.pipeline_runtime.execution.handlers_deterministic import DETERMINISTIC_REGISTRY
from subsystems.pipeline_runtime.execution.handlers_llm import LLM_OPERATOR_NAMES, LLM_REGISTRY
from subsystems.pipeline_runtime.execution.stub_invocation import run_stub_with_step_workdir
from subsystems.pipeline_runtime.execution.subprocess_step import SubprocessOperatorError, run_operator_subprocess


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_generated(root: Path, pipeline_id: str) -> dict[str, Any]:
    p = root / "data" / "generated_pipelines" / f"{pipeline_id}.json"
    if not p.is_file():
        raise FileNotFoundError(f"缺少实例化产物: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("generated_pipelines JSON 无效")
    return data


def _final_pipeline(gen: dict[str, Any]) -> list[dict[str, Any]]:
    fp = gen.get("final_pipeline_snapshot")
    if not isinstance(fp, list):
        return []
    return [x for x in fp if isinstance(x, dict)]


def _artifact_dir_for_step(gen: dict[str, Any], step_index_1based: int) -> str | None:
    for s in gen.get("steps") or []:
        if not isinstance(s, dict):
            continue
        if int(s.get("step_index") or -1) == step_index_1based:
            rel = s.get("artifact_dir")
            return str(rel) if isinstance(rel, str) else None
    return None


def _load_stub_module(py_file: Path) -> Any:
    name = f"_exec_stub_{py_file.parent.name}_{id(py_file)}"
    spec = importlib.util.spec_from_file_location(name, py_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {py_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ensure_llm_config_for_pipeline(
    fp: list[dict[str, Any]],
    merged_registry: dict[str, Any],
    llm_config: dict[str, Any],
) -> None:
    needs = False
    for step in fp:
        op = step.get("operator")
        if not isinstance(op, str):
            continue
        if op in LLM_OPERATOR_NAMES:
            needs = True
            break
        spec = merged_registry.get(op)
        if isinstance(spec, dict) and spec.get("requires_llm"):
            needs = True
            break
    if needs and not str(llm_config.get("api_key") or "").strip():
        raise ValueError("流水线包含 LLM 算子但未配置 API Key（config 中 api_config.api_key）")


def _should_run_step_in_subprocess(
    op: str,
    execution_mode: str,
    stub_exists: bool,
    handlers: dict[str, Any],
) -> bool:
    if execution_mode != "subprocess":
        return False
    if not stub_exists:
        return False
    if op in ("read_data", "write_data"):
        return False
    if op in handlers:
        return False
    return True


def _run_step_in_process(
    op: str,
    records: list[dict[str, Any]],
    step: dict[str, Any],
    ctx: dict[str, Any],
    handlers: dict[str, Any],
    gen: dict[str, Any],
    root: Path,
    si: int,
) -> list[dict[str, Any]]:
    fn = handlers.get(op)
    if fn is not None:
        return fn(records, step, ctx)
    art = _artifact_dir_for_step(gen, si)
    if not art:
        raise RuntimeError(f"未知算子 {op!r} 且无 artifact_dir")
    stub = root / art / "operator_stub.py"
    if not stub.is_file():
        raise FileNotFoundError(f"未知算子 {op!r} 且缺少 {stub}")
    mod = _load_stub_module(stub)
    run_fn = getattr(mod, "run", None)
    if not callable(run_fn):
        raise TypeError("operator_stub.run 不可调用")
    out = run_stub_with_step_workdir(stub, run_fn, records, ctx)
    if out is None:
        out = []
    if not isinstance(out, list):
        raise TypeError("run() 必须返回 list")
    return out


def execute_generated_pipeline(
    root: Path,
    pipeline_id: str,
    *,
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None = None,
    max_input_records: int | None = None,
    llm_max_records_per_step: int | None = 32,
    execution_mode: Literal["in_process", "subprocess"] = "in_process",
    subprocess_fallback_in_process: bool = True,
    subprocess_timeout_sec: float = 600.0,
) -> dict[str, Any]:
    """
    执行完整管线并落盘到 `data/run_pipeline_results/{pipeline_id}/{run_tag}/`。

    - `max_input_records`: 限制 read_data 后记录条数（调试用；None 表示不截断）。
    - `llm_max_records_per_step`: 每个 LLM 步最多处理的行数（控制费用）；超出部分原样透传拼回。
    - `execution_mode=subprocess`: 对**无内置 Python handler**的步骤用子进程跑 `operator_stub.py`（见模块头说明）。
    """
    gen = _load_generated(root, pipeline_id)
    fp = _final_pipeline(gen)
    if not fp:
        raise ValueError("final_pipeline_snapshot 为空，请先完成实例化")

    store = OperatorRegistryStore(root)
    merged = store.merged_raw()
    _ensure_llm_config_for_pipeline(fp, merged, llm_config)

    run_id = _run_tag()
    run_dir = root / "data" / "run_pipeline_results" / pipeline_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ctx: dict[str, Any] = {
        "root": str(root.resolve()),
        "pipeline_id": pipeline_id,
        "llm_config": llm_config,
        "on_usage": on_usage,
        "max_input_records": max_input_records,
        "llm_max_records_per_step": llm_max_records_per_step,
        "execution_warnings": [],
    }

    handlers: dict[str, Any] = {**DETERMINISTIC_REGISTRY, **LLM_REGISTRY}

    records: list[dict[str, Any]] = []
    step_logs: list[dict[str, Any]] = []
    status = "success"
    failed_step: dict[str, Any] | None = None
    err_text: str | None = None

    for i, step in enumerate(fp):
        op = str(step.get("operator") or "")
        si = i + 1
        ctx["usage_operation"] = f"pipeline_run.step_{si:02d}.{op}"
        t0 = time.perf_counter()
        n_before = len(records)
        art = _artifact_dir_for_step(gen, si)
        stub_path = (root / art / "operator_stub.py") if art else None
        stub_exists = stub_path.is_file() if stub_path else False
        use_sub = _should_run_step_in_subprocess(op, execution_mode, stub_exists, handlers)
        try:
            handler_tag = "builtin"
            if use_sub and stub_path is not None:
                try:
                    log_f = run_dir / f"step_{si:02d}_subprocess.log"
                    records = run_operator_subprocess(
                        root,
                        stub_path,
                        records,
                        timeout_sec=subprocess_timeout_sec,
                        log_path=log_f,
                    )
                    handler_tag = "subprocess"
                except (SubprocessOperatorError, OSError, subprocess.TimeoutExpired) as e:
                    if subprocess_fallback_in_process:
                        records = _run_step_in_process(
                            op, records, step, ctx, handlers, gen, root, si
                        )
                        handler_tag = "subprocess_fallback_in_process"
                    else:
                        raise
            else:
                records = _run_step_in_process(
                    op, records, step, ctx, handlers, gen, root, si
                )
                if op in handlers:
                    handler_tag = "builtin"
                else:
                    handler_tag = "stub_in_process"
            dur = (time.perf_counter() - t0) * 1000
            step_logs.append(
                {
                    "step_index": si,
                    "operator": op,
                    "ok": True,
                    "duration_ms": round(dur, 2),
                    "n_in": n_before,
                    "n_out": len(records),
                    "handler": handler_tag,
                }
            )
        except Exception as e:
            status = "failed"
            failed_step = {"step_index": si, "operator": op}
            err_text = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-4000:]}"
            dur = (time.perf_counter() - t0) * 1000
            step_logs.append(
                {
                    "step_index": si,
                    "operator": op,
                    "ok": False,
                    "duration_ms": round(dur, 2),
                    "error": str(e),
                }
            )
            break

    out_jsonl = run_dir / "output.jsonl"
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for r in records:
            if isinstance(r, dict):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report: dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "source": "pipeline_execution_v1",
        "meta": {
            "created_at": _iso(),
            "run_id": run_id,
            "run_dir": f"data/run_pipeline_results/{pipeline_id}/{run_id}",
            "generated_pipeline_path": f"data/generated_pipelines/{pipeline_id}.json",
            "execution_mode": execution_mode,
            "subprocess_fallback_in_process": subprocess_fallback_in_process,
            "subprocess_timeout_sec": subprocess_timeout_sec,
        },
        "status": status,
        "failed_step": failed_step,
        "error": err_text,
        "output_record_count": len(records),
        "output_jsonl": f"data/run_pipeline_results/{pipeline_id}/{run_id}/output.jsonl",
        "steps": step_logs,
        "warnings": list(ctx.get("execution_warnings") or []),
    }
    (run_dir / "run_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    latest = root / "data" / "run_pipeline_results" / pipeline_id / "latest.json"
    latest.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "run_dir": report["meta"]["run_dir"],
                "status": status,
                "updated_at": _iso(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report["records"] = records
    return report


def patch_orchestration_pipeline_run_summary(root: Path, pipeline_id: str, report: dict[str, Any]) -> None:
    """在编排落盘文件中写入最近一次全量执行摘要。"""
    orch_path = root / "data" / "orchestration_results" / f"{pipeline_id}.json"
    if not orch_path.is_file():
        return
    try:
        data = json.loads(orch_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        meta = report.get("meta") or {}
        data["pipeline_run_summary"] = {
            "updated_at": _iso(),
            "status": report.get("status"),
            "run_dir": meta.get("run_dir"),
            "output_jsonl": report.get("output_jsonl"),
            "output_record_count": report.get("output_record_count"),
            "failed_step": report.get("failed_step"),
        }
        tmp = orch_path.with_suffix(orch_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(orch_path)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
