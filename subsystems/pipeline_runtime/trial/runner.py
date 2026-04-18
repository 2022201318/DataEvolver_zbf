"""
试运行（采样数据）：按 `generated_pipelines` 步骤顺序加载各目录下 `operator_stub.run(records, context)`。

- **内置算子**的 `operator_stub` 为 **委托模块**，与 `execute_generated_pipeline` 使用同一套 handler（read/remove_field/… 会真实处理数据）。
- **LLM 生成**的自定义算子需 `context["llm_config"]` 含有效 API Key；否则可能失败或降级。
"""

from __future__ import annotations

import importlib.util
import json
import time

from subsystems.pipeline_runtime.execution.stub_invocation import run_stub_with_step_workdir
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_stub(py_file: Path) -> Any:
    name = f"_trial_{py_file.parent.name}_{id(py_file)}"
    spec = importlib.util.spec_from_file_location(name, py_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {py_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_seed_sample_records(
    root: Path, manifest_record: dict[str, Any], max_records: int
) -> list[dict[str, Any]]:
    """读取 manifest 中首个 seed 文件的前若干条记录（JSONL 或 JSON 数组），供质检 / LLM Judge 对比。"""
    files = [x for x in (manifest_record.get("seed_data_files") or []) if isinstance(x, str)]
    if not files or max_records <= 0:
        return []
    path = (root / files[0]).resolve()
    if not str(path).startswith(str(root.resolve())) or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".jsonl":
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if len(out) >= max_records:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out.append(obj)
        elif path.suffix.lower() == ".json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if len(out) >= max_records:
                        break
                    if isinstance(item, dict):
                        out.append(item)
            elif isinstance(data, dict):
                out.append(data)
    except (json.JSONDecodeError, OSError):
        return []
    return out


def _shallow_trim_record(rec: dict[str, Any], max_str: int = 4000, max_keys: int = 80) -> dict[str, Any]:
    """缩小 trial 落盘体积，避免 JSON 过大。"""
    keys = list(rec.keys())[:max_keys]
    slim: dict[str, Any] = {}
    for k in keys:
        v = rec[k]
        if isinstance(v, str) and len(v) > max_str:
            slim[k] = v[: max_str - 20] + "…(truncated)"
        elif isinstance(v, (int, float, bool)) or v is None:
            slim[k] = v
        elif isinstance(v, dict):
            slim[k] = _shallow_trim_record(v, max_str=max_str // 4, max_keys=min(32, max_keys))
        elif isinstance(v, list) and len(v) > 16:
            slim[k] = v[:16] + ["…(truncated)"]
        else:
            try:
                s = json.dumps(v, ensure_ascii=False)
            except (TypeError, ValueError):
                s = repr(v)
            if len(s) > max_str:
                slim[k] = s[: max_str - 20] + "…(truncated)"
            else:
                slim[k] = v
    return slim


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            if isinstance(r, dict):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _seed_key_profile(root: Path, manifest_record: dict[str, Any], max_keys: int = 64) -> dict[str, Any]:
    files = [x for x in (manifest_record.get("seed_data_files") or []) if isinstance(x, str)]
    if not files:
        return {"available": False}
    path = (root / files[0]).resolve()
    if not str(path).startswith(str(root.resolve())) or not path.is_file():
        return {"available": False, "error": "seed 文件不可读"}
    try:
        if path.suffix.lower() == ".jsonl":
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        keys = sorted(obj.keys())[:max_keys]
                        return {"available": True, "top_level_keys": keys, "path": files[0]}
        if path.suffix.lower() == ".json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                keys = sorted(data.keys())[:max_keys]
                return {"available": True, "top_level_keys": keys, "path": files[0]}
            if isinstance(data, list) and data and isinstance(data[0], dict):
                keys = sorted(data[0].keys())[:max_keys]
                return {"available": True, "top_level_keys": keys, "path": files[0]}
    except (json.JSONDecodeError, OSError) as e:
        return {"available": False, "error": str(e)}
    return {"available": False}


def _public_top_level_keys(record_keys: Iterable[Any]) -> set[str]:
    """与 seed 对齐时忽略以下划线开头的诊断/中间字段（如 _validation_report）。"""
    out: set[str] = set()
    for k in record_keys:
        if not isinstance(k, str):
            continue
        if k.startswith("_"):
            continue
        out.add(k)
    return out


def _reflux_from_trial(
    *,
    execution_ok: bool,
    schema: dict[str, Any],
) -> dict[str, Any]:
    targets: list[str] = []
    reasons: list[str] = []
    if not execution_ok:
        targets.extend(["instantiation", "orchestration"])
        reasons.append("试运行执行失败：检查 final_pipeline 顺序、算子桩与 read_data 路径")
    miss = schema.get("missing_for_seed_top_keys") or []
    if miss:
        if "orchestration" not in targets:
            targets.append("orchestration")
        if "understanding" not in targets:
            targets.append("understanding")
        reasons.append(f"输出记录缺少相对 seed 的顶层键: {miss[:8]}")
    extra = schema.get("extra_vs_seed_top_keys") or []
    # 仅统计「相对 seed 多出的业务字段」；诊断键已在 schema 计算中排除
    if len(extra) > 5:
        targets.append("orchestration")
        reasons.append("输出相对 seed 多余字段较多，可能需收敛 schema 或 map_fields")
    return {
        "targets": list(dict.fromkeys(targets)),
        "reasons": reasons,
    }


def run_pipeline_trial(
    root: Path,
    pipeline_id: str,
    manifest_record: dict[str, Any],
    *,
    max_records: int = 8,
    llm_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gen_main = root / "data" / "generated_pipelines" / f"{pipeline_id}.json"
    if not gen_main.is_file():
        raise FileNotFoundError(f"缺少实例化产物: {gen_main}")

    payload = json.loads(gen_main.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("generated_pipelines JSON 无效")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("实例化 steps 为空")

    ordered = sorted(
        [s for s in steps if isinstance(s, dict)],
        key=lambda x: int(x.get("step_index") or 0),
    )

    lc = llm_config if isinstance(llm_config, dict) else {}
    context: dict[str, Any] = {
        "root": str(root.resolve()),
        "pipeline_id": pipeline_id,
        "trial": True,
        "max_records": max_records,
        "max_input_records": max_records,
        "llm_config": lc,
        "on_usage": None,
        "llm_max_records_per_step": max_records,
    }

    records: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    execution_ok = True
    last_error: str | None = None
    partial_after_last_ok: list[dict[str, Any]] = []
    partial_after_step_index: int | None = None
    partial_after_operator: str | None = None
    # 每步落盘中间结果（trial 记录数很小，默认开启）
    trial_dir = root / "data" / "trial_runs" / pipeline_id
    step_dump_dir = trial_dir / "steps"
    dumped_steps: list[dict[str, Any]] = []

    for st in ordered:
        op = str(st.get("operator_name") or "")
        idx = int(st.get("step_index") or 0)
        art = st.get("artifact_dir")
        t0 = time.perf_counter()
        dur_ms = 0.0
        try:
            if not art or not isinstance(art, str):
                raise ValueError(f"步骤 {idx} 缺少 artifact_dir")
            stub = root / art / "operator_stub.py"
            if not stub.is_file():
                raise FileNotFoundError(f"缺少 operator_stub.py: {stub}")
            mod = _load_stub(stub)
            run_fn = getattr(mod, "run", None)
            if not callable(run_fn):
                raise TypeError("operator_stub 缺少 run(records, context)")
            records = run_stub_with_step_workdir(stub, run_fn, records, context)
            if records is None:
                records = []
            if not isinstance(records, list):
                raise TypeError(f"{op} run() 应返回 list，得到 {type(records).__name__}")
            for j, item in enumerate(records):
                if item is not None and not isinstance(item, dict):
                    raise TypeError(f"records[{j}] 应为 dict")
            partial_after_last_ok = [
                _shallow_trim_record(r) for r in records[:max_records] if isinstance(r, dict)
            ]
            partial_after_step_index = idx
            partial_after_operator = op
            # 落盘该步后的 records 快照（用于逐步对比）
            safe = [_shallow_trim_record(r) for r in records[:max_records] if isinstance(r, dict)]
            dump_name = f"step_{idx:03d}_{op}.jsonl" if op else f"step_{idx:03d}.jsonl"
            dump_rel = f"data/trial_runs/{pipeline_id}/steps/{dump_name}"
            _write_jsonl(step_dump_dir / dump_name, safe)
            dumped_steps.append(
                {
                    "step_index": idx,
                    "operator": op,
                    "path": dump_rel,
                    "n_records": len(safe),
                }
            )
            dur_ms = (time.perf_counter() - t0) * 1000
            trace.append(
                {
                    "step_index": idx,
                    "operator": op,
                    "ok": True,
                    "duration_ms": round(dur_ms, 2),
                    "n_records": len(records) if isinstance(records, list) else 0,
                    "records_dump": dump_rel,
                }
            )
        except Exception as e:
            execution_ok = False
            last_error = f"{type(e).__name__}: {e}"
            dur_ms = (time.perf_counter() - t0) * 1000
            trace.append(
                {
                    "step_index": idx,
                    "operator": op,
                    "ok": False,
                    "duration_ms": round(dur_ms, 2),
                    "error": last_error,
                }
            )
            break

    seed_prof = _seed_key_profile(root, manifest_record)
    schema_check: dict[str, Any] = {
        "seed_profile": seed_prof,
        "output_sample_keys": [],
        "missing_for_seed_top_keys": [],
        "extra_vs_seed_top_keys": [],
        "diagnostic_keys_in_output": [],
    }
    if execution_ok and records and isinstance(records, list) and records and isinstance(records[0], dict):
        out_keys = set(records[0].keys())
        schema_check["output_sample_keys"] = sorted(out_keys)[:64]
        diag = sorted(k for k in out_keys if isinstance(k, str) and k.startswith("_"))[:32]
        if diag:
            schema_check["diagnostic_keys_in_output"] = diag
        public_out = _public_top_level_keys(out_keys)
        if seed_prof.get("available") and seed_prof.get("top_level_keys"):
            sk = set(str(k) for k in seed_prof["top_level_keys"])
            schema_check["missing_for_seed_top_keys"] = sorted(sk - public_out)[:32]
            schema_check["extra_vs_seed_top_keys"] = sorted(public_out - sk)[:32]

    reflux = _reflux_from_trial(execution_ok=execution_ok, schema=schema_check)

    seed_sample = _load_seed_sample_records(root, manifest_record, max_records)
    output_sample: list[dict[str, Any]] = []
    if execution_ok and records and isinstance(records, list):
        for r in records[:max_records]:
            if isinstance(r, dict):
                output_sample.append(_shallow_trim_record(r))

    result: dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "source": "pipeline_trial_v1",
        "meta": {
            "created_at": _iso(),
            "max_records": max_records,
            "generated_pipeline_path": f"data/generated_pipelines/{pipeline_id}.json",
            "step_dumps_dir": f"data/trial_runs/{pipeline_id}/steps",
        },
        "execution_ok": execution_ok,
        "last_error": last_error,
        "step_trace": trace,
        "step_dumps": dumped_steps,
        "schema_check": schema_check,
        "reflux_recommendation": reflux,
        "data_samples": {
            "seed": [_shallow_trim_record(x) for x in seed_sample],
            "output": output_sample,
            "note": "与前端 QualityCheck 页「Seed / 采样输出」对齐的截断样本；完整数据见全量执行产物。",
        },
        "partial_pipeline_state": {
            "after_completed_step_index": partial_after_step_index,
            "after_operator": partial_after_operator,
            "records_sample": partial_after_last_ok,
            "note": "仅当在中间步骤失败时有意义：此处为上一成功步执行后的 records 截断；第一步失败时为空。",
        },
    }
    return result


def write_trial_artifacts(
    root: Path,
    pipeline_id: str,
    trial_result: dict[str, Any],
) -> Path:
    out_dir = root / "data" / "trial_runs" / pipeline_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "trial_result.json"
    path.write_text(json.dumps(trial_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def patch_orchestration_trial_summary(root: Path, pipeline_id: str, trial_result: dict[str, Any]) -> None:
    """在编排落盘中写入试运行摘要，便于单文件轮询闭环状态。"""
    orch_path = root / "data" / "orchestration_results" / f"{pipeline_id}.json"
    if not orch_path.is_file():
        return
    try:
        data = json.loads(orch_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        pilot = trial_result.get("llm_pilot_evaluation")
        trc: dict[str, Any] = {
            "checked_at": trial_result.get("meta", {}).get("created_at"),
            "execution_ok": trial_result.get("execution_ok"),
            "artifact": f"data/trial_runs/{pipeline_id}/trial_result.json",
            "reflux_targets": (trial_result.get("reflux_recommendation") or {}).get("targets", []),
        }
        if isinstance(pilot, dict) and pilot.get("present") and pilot.get("overall_score") is not None:
            trc["pilot_overall_score"] = pilot.get("overall_score")
            trc["pilot_recommendation"] = pilot.get("recommendation")
            if isinstance(pilot.get("dimension_scores"), dict):
                trc["pilot_dimension_scores"] = pilot.get("dimension_scores")
        data["trial_run_check"] = trc
        tmp = orch_path.with_suffix(orch_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(orch_path)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
