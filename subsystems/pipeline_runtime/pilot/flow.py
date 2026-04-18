"""试运行 + 可选 Pilot LLM 评估（与 workflow `trial_run`、入口脚本共用）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from subsystems.pipeline_runtime.pilot.pilot_llm_judge import apply_pilot_llm_judge
from subsystems.pipeline_runtime.trial.runner import run_pipeline_trial


def run_trial_with_optional_pilot_judge(
    root: Path,
    pipeline_id: str,
    manifest_record: dict[str, Any],
    *,
    max_records: int = 8,
    llm_config: dict[str, Any] | None = None,
    on_usage: Callable[..., None] | None = None,
    with_llm_judge: bool = True,
) -> dict[str, Any]:
    trial = run_pipeline_trial(
        root,
        pipeline_id,
        manifest_record,
        max_records=max_records,
        llm_config=llm_config,
    )
    apply_pilot_llm_judge(
        root,
        pipeline_id,
        trial,
        llm_config=llm_config,
        on_usage=on_usage,
        enabled=with_llm_judge,
    )
    return trial
