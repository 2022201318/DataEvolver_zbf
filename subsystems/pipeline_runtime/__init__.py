"""
管线运行时：实例化（桩代码）→ 试运行（采样）→ 全量执行（进程内 / 可选子进程）。

对齐旧版「生成 + 跑通」大块能力，合并原 `pipeline_instantiation` / `pipeline_trial` / `pipeline_execution`。
"""

from subsystems.pipeline_runtime.execution import (
    SubprocessOperatorError,
    bridge_script_path,
    execute_generated_pipeline,
    patch_orchestration_pipeline_run_summary,
    run_operator_subprocess,
)
from subsystems.pipeline_runtime.instantiation import run_instantiation
from subsystems.pipeline_runtime.pilot.flow import run_trial_with_optional_pilot_judge
from subsystems.pipeline_runtime.trial import (
    patch_orchestration_trial_summary,
    run_pipeline_trial,
    write_trial_artifacts,
)

__all__ = [
    "SubprocessOperatorError",
    "bridge_script_path",
    "execute_generated_pipeline",
    "patch_orchestration_pipeline_run_summary",
    "patch_orchestration_trial_summary",
    "run_instantiation",
    "run_operator_subprocess",
    "run_pipeline_trial",
    "run_trial_with_optional_pilot_judge",
    "write_trial_artifacts",
]
