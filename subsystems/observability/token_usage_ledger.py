"""按 pipeline 追加记录 LLM token 消耗（JSONL），供 CLI / HTTP 汇总。"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def token_ledger_path(root: Path, pipeline_id: str) -> Path:
    return root / "data" / "workflow_runs" / pipeline_id / "token_usage.jsonl"


def append_token_event(
    root: Path,
    pipeline_id: str,
    *,
    workflow_step: str,
    input_tokens: int,
    output_tokens: int,
    model: str,
    operation: str | None = None,
    duration_ms: float | int | None = None,
    request_id: str | None = None,
    api_host: str | None = None,
    provider: str | None = None,
    success: bool | None = True,
) -> None:
    path = token_ledger_path(root, pipeline_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    event: dict[str, Any] = {
        "schema_version": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "workflow_step": workflow_step,
        "operation": operation or workflow_step,
        "model": model,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(input_tokens) + int(output_tokens),
    }
    if duration_ms is not None:
        event["duration_ms"] = float(duration_ms)
    if request_id:
        event["request_id"] = request_id
    if api_host:
        event["api_host"] = api_host
    if provider:
        event["provider"] = provider
    if success is not None:
        event["success"] = bool(success)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_token_events(root: Path, pipeline_id: str) -> list[dict[str, Any]]:
    path = token_ledger_path(root, pipeline_id)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
    except (OSError, json.JSONDecodeError):
        return out
    return out


def summarize_token_ledger(
    root: Path,
    pipeline_id: str,
    *,
    include_events: bool = True,
    max_events: int = 500,
) -> dict[str, Any]:
    events = read_token_events(root, pipeline_id)
    tin = tout = 0
    by_step: dict[str, dict[str, int]] = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "api_calls": 0})
    by_op: dict[str, dict[str, int]] = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "api_calls": 0})
    by_model: dict[str, dict[str, int]] = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "api_calls": 0})
    total_duration_ms = 0.0
    n_duration = 0

    for ev in events:
        i = int(ev.get("input_tokens") or 0)
        o = int(ev.get("output_tokens") or 0)
        tin += i
        tout += o
        dm = ev.get("duration_ms")
        if dm is not None:
            try:
                total_duration_ms += float(dm)
                n_duration += 1
            except (TypeError, ValueError):
                pass
        step = str(ev.get("workflow_step") or "")
        op = str(ev.get("operation") or step)
        m = str(ev.get("model") or "")

        b = by_step[step]
        b["input_tokens"] += i
        b["output_tokens"] += o
        b["api_calls"] += 1

        bo = by_op[op]
        bo["input_tokens"] += i
        bo["output_tokens"] += o
        bo["api_calls"] += 1

        bm = by_model[m]
        bm["input_tokens"] += i
        bm["output_tokens"] += o
        bm["api_calls"] += 1

    tail = events[-max_events:] if len(events) > max_events else events

    series = []
    for ev in events:
        series.append(
            {
                "ts": ev.get("ts"),
                "workflow_step": ev.get("workflow_step"),
                "operation": ev.get("operation"),
                "model": ev.get("model"),
                "total_tokens": ev.get("total_tokens"),
                "duration_ms": ev.get("duration_ms"),
            }
        )

    first_ts = events[0].get("ts") if events else None
    last_ts = events[-1].get("ts") if events else None

    return {
        "ok": True,
        "schema_version": 1,
        "pipeline_id": pipeline_id,
        "ledger_path": f"data/workflow_runs/{pipeline_id}/token_usage.jsonl",
        "event_count": len(events),
        "total_input_tokens": tin,
        "total_output_tokens": tout,
        "total_tokens": tin + tout,
        "total_duration_ms": round(total_duration_ms, 2),
        "calls_with_duration": n_duration,
        "time_range": {"first_ts": first_ts, "last_ts": last_ts},
        "by_workflow_step": {k: dict(v) for k, v in sorted(by_step.items())},
        "by_operation": {k: dict(v) for k, v in sorted(by_op.items())},
        "by_model": {k: dict(v) for k, v in sorted(by_model.items()) if k},
        "for_frontend": {"token_series": series},
        **({"events": tail} if include_events else {}),
    }
