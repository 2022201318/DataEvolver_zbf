"""采样试运行：验证数据流与 schema 对齐，支撑闭环回流建议。"""

from subsystems.pipeline_runtime.trial.runner import (
    patch_orchestration_trial_summary,
    run_pipeline_trial,
    write_trial_artifacts,
)

__all__ = ["patch_orchestration_trial_summary", "run_pipeline_trial", "write_trial_artifacts"]
