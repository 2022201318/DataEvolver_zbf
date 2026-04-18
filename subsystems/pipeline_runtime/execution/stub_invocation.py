"""
在 `operator_stub.py` 所在目录执行 `run()`。

LLM 生成的桩常使用 `open("step_meta.json")` 等 cwd 相对路径；trial / execute 的进程 cwd 多为仓库根，
会导致找不到元数据。内置委托桩使用 `Path(__file__).parent`，不受此影响。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable


def run_stub_with_step_workdir(
    stub_file: Path | str,
    run_fn: Callable[[list[dict[str, Any]], dict[str, Any]], Any],
    records: list[dict[str, Any]],
    context: dict[str, Any],
) -> Any:
    path = Path(stub_file).resolve()
    step_dir = path.parent
    previous = os.getcwd()
    try:
        os.chdir(step_dir)
        return run_fn(records, context)
    finally:
        try:
            os.chdir(previous)
        except OSError:
            pass
