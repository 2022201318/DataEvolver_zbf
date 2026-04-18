"""
实例化包入口 `run_pipeline.py` 调用的运行时：pilot / full。

与 `dataevolver workflow trial` / `run-pipeline` 写入相同落盘路径，便于 DataEvolver 评估与前端读 JSON。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from subsystems.observability.token_usage_ledger import append_token_event
from subsystems.pipeline_runtime.execution.runner import (
    execute_generated_pipeline,
    patch_orchestration_pipeline_run_summary,
)
from subsystems.pipeline_runtime.pilot.flow import run_trial_with_optional_pilot_judge
from subsystems.pipeline_runtime.trial.runner import (
    patch_orchestration_trial_summary,
    write_trial_artifacts,
)
from subsystems.pipeline_session.manifest_store import get_latest_manifest_record


def find_repo_root(start: Path) -> Path:
    env = __import__("os").environ.get("DATAEVOLVER_ROOT", "").strip()
    if env:
        p = Path(env).resolve()
        if (p / "config").is_dir() and (p / "data").is_dir():
            return p
    for d in [start.resolve(), *start.resolve().parents]:
        if (d / "config").is_dir() and (d / "data").is_dir():
            return d
    raise FileNotFoundError(
        "未找到 DataEvolver 仓库根（需含 config/ 与 data/）。请 cd 到仓库根或设置环境变量 DATAEVOLVER_ROOT。"
    )


def _make_on_usage(root: Path, pipeline_id: str) -> Callable[..., None]:
    model_default = ""

    def cb(
        *,
        input_tokens: int,
        output_tokens: int,
        model: str | None = None,
        operation: str | None = None,
        duration_ms: float | int | None = None,
        request_id: str | None = None,
        api_host: str | None = None,
        **extra: Any,
    ) -> None:
        append_token_event(
            root,
            pipeline_id,
            workflow_step="entry.run_pipeline",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model or model_default or "unknown",
            operation=operation or "entry.run_pipeline",
            duration_ms=duration_ms if duration_ms is not None else None,
            request_id=request_id if request_id else None,
            api_host=api_host if api_host else None,
        )

    return cb


def run_pilot_bundle(
    root: Path,
    pipeline_id: str,
    *,
    max_records: int,
    skip_judge: bool,
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None,
) -> dict[str, Any]:
    manifest_path = root / "data" / "manifest.jsonl"
    record = get_latest_manifest_record(manifest_path, pipeline_id)
    if record is None:
        raise FileNotFoundError(f"manifest 中未找到 pipeline_id={pipeline_id!r}")
    trial = run_trial_with_optional_pilot_judge(
        root,
        pipeline_id,
        record,
        max_records=max_records,
        llm_config=llm_config,
        on_usage=on_usage,
        with_llm_judge=not skip_judge,
    )
    write_trial_artifacts(root, pipeline_id, trial)
    patch_orchestration_trial_summary(root, pipeline_id, trial)
    return trial


def run_full_bundle(
    root: Path,
    pipeline_id: str,
    *,
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None,
    execution_mode: str,
    subprocess_fallback: bool,
    subprocess_timeout: float,
) -> dict[str, Any]:
    report = execute_generated_pipeline(
        root,
        pipeline_id,
        llm_config=llm_config,
        on_usage=on_usage,
        max_input_records=None,
        llm_max_records_per_step=32,
        execution_mode=execution_mode,  # type: ignore[arg-type]
        subprocess_fallback_in_process=subprocess_fallback,
        subprocess_timeout_sec=subprocess_timeout,
    )
    patch_orchestration_pipeline_run_summary(root, pipeline_id, report)
    report.pop("records", None)
    return report


def entrypoint_main(argv: list[str] | None = None) -> int:
    """供生成的 `run_pipeline.py` 调用；需在 `sys.path` 含仓库根后 import。"""
    import os

    from core.config_manager import ConfigManager

    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(
        description="DataEvolver 生成管线入口：pilot=采样+可选 LLM 评估，full=全量执行。",
    )
    ap.add_argument(
        "--mode",
        choices=("pilot", "full"),
        default="pilot",
        help="pilot：默认推荐，便于评估与自进化；full：全量生成（确认质量后）",
    )
    ap.add_argument("--max-records", type=int, default=8, help="pilot 模式每条流最大采样条数")
    ap.add_argument("--skip-judge", action="store_true", help="pilot 下跳过 LLM 多维度评估")
    ap.add_argument(
        "--execution-mode",
        choices=("in_process", "subprocess"),
        default="in_process",
        help="仅 full 模式：与 workflow run-pipeline 一致",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--subprocess-fallback", dest="subprocess_fallback", action="store_true")
    g.add_argument("--no-subprocess-fallback", dest="subprocess_fallback", action="store_false")
    ap.set_defaults(subprocess_fallback=True)
    ap.add_argument("--subprocess-timeout", type=float, default=600.0)
    args, unknown = ap.parse_known_args(argv)
    if unknown:
        print("忽略未识别参数:", unknown, file=sys.stderr)

    root_s = os.environ.get("DATAEVOLVER_ROOT", "").strip()
    pid = os.environ.get("DATAEVOLVER_PIPELINE_ID", "").strip()
    if root_s:
        root = Path(root_s).resolve()
    else:
        main_mod = sys.modules.get("__main__")
        mf = getattr(main_mod, "__file__", None) if main_mod else None
        start = Path(mf).resolve().parent if isinstance(mf, str) and mf else Path.cwd()
        root = find_repo_root(start)
    if not pid:
        main_mod = sys.modules.get("__main__")
        mf = getattr(main_mod, "__file__", None) if main_mod else None
        if isinstance(mf, str) and Path(mf).resolve().name == "run_pipeline.py":
            pid = Path(mf).resolve().parent.name
    if not pid:
        pid = Path.cwd().name

    cm = ConfigManager(project_root=root)
    lc = cm.llm_config()
    on_usage = _make_on_usage(root, pipeline_id)

    try:
        if args.mode == "pilot":
            trial = run_pilot_bundle(
                root,
                pipeline_id,
                max_records=args.max_records,
                skip_judge=args.skip_judge,
                llm_config=lc,
                on_usage=on_usage,
            )
            ds = trial.get("data_samples") if isinstance(trial.get("data_samples"), dict) else {}
            summary = {
                "ok": True,
                "mode": "pilot",
                "artifact": f"data/trial_runs/{pipeline_id}/trial_result.json",
                "execution_ok": trial.get("execution_ok"),
                "llm_pilot_evaluation": trial.get("llm_pilot_evaluation"),
                "data_samples_counts": {
                    "seed": len(ds.get("seed") or []) if isinstance(ds.get("seed"), list) else 0,
                    "output": len(ds.get("output") or []) if isinstance(ds.get("output"), list) else 0,
                },
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            pilot = trial.get("llm_pilot_evaluation") or {}
            print("\n── Pilot 完成 ──", file=sys.stderr)
            print(f"  execution_ok: {trial.get('execution_ok')}", file=sys.stderr)
            if isinstance(pilot, dict) and pilot.get("present"):
                print(
                    f"  LLM 总分: {pilot.get('overall_score')}  建议: {pilot.get('recommendation')}",
                    file=sys.stderr,
                )
                ds = pilot.get("dimension_scores") if isinstance(pilot.get("dimension_scores"), dict) else {}
                if ds:
                    order = ("semantic", "format", "diversity", "info", "noise", "logic")
                    zh = {
                        "semantic": "语义",
                        "format": "格式",
                        "diversity": "多样性",
                        "info": "信息",
                        "noise": "洁净",
                        "logic": "逻辑",
                    }
                    parts = []
                    for k in order:
                        if k in ds:
                            try:
                                parts.append(f"{zh.get(k, k)}={int(ds[k])}")
                            except (TypeError, ValueError):
                                pass
                    if parts:
                        print(f"  各维度(0–100): {' · '.join(parts)}", file=sys.stderr)
                print(f"  理由: {pilot.get('recommendation_rationale', '')[:300]}", file=sys.stderr)
            elif isinstance(pilot, dict):
                print(f"  LLM 评估: 已跳过（{pilot.get('skipped_reason')}）", file=sys.stderr)
            print(f"  落盘: data/trial_runs/{pipeline_id}/trial_result.json", file=sys.stderr)
            print("  下一步: 若建议 proceed_full → 本脚本 --mode full；若 evolve_pipeline → workflow 回退 orchestrate", file=sys.stderr)
            return 0 if trial.get("execution_ok") else 1

        report = run_full_bundle(
            root,
            pipeline_id,
            llm_config=lc,
            on_usage=on_usage,
            execution_mode=args.execution_mode,
            subprocess_fallback=args.subprocess_fallback,
            subprocess_timeout=args.subprocess_timeout,
        )
        print(
            json.dumps(
                {
                    "ok": report.get("status") == "success",
                    "mode": "full",
                    "status": report.get("status"),
                    "output_jsonl": report.get("output_jsonl"),
                    "output_record_count": report.get("output_record_count"),
                    "run_dir": (report.get("meta") or {}).get("run_dir"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("\n── 全量执行 ──", file=sys.stderr)
        print(f"  status: {report.get('status')}", file=sys.stderr)
        print(f"  输出: {report.get('output_jsonl')}", file=sys.stderr)
        return 0 if report.get("status") == "success" else 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
