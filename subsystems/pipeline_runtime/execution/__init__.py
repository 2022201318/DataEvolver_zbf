"""管线执行：按实例化快照跑通 read → 变换 → write（含 LLM；可选子进程 stub）。"""

from subsystems.pipeline_runtime.execution.runner import execute_generated_pipeline, patch_orchestration_pipeline_run_summary
from subsystems.pipeline_runtime.execution.subprocess_step import (
    SubprocessOperatorError,
    bridge_script_path,
    run_operator_subprocess,
)

__all__ = [
    "SubprocessOperatorError",
    "bridge_script_path",
    "execute_generated_pipeline",
    "patch_orchestration_pipeline_run_summary",
    "run_operator_subprocess",
]
