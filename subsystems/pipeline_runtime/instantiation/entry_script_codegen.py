"""生成 `data/generated_pipelines/{id}/run_pipeline.py` 入口（模板在组件内，不手改生成目录）。"""

from __future__ import annotations

from pathlib import Path

# 生成脚本需在 import 子系统前把仓库根加入 sys.path，并注入环境变量供 bundle_runner 解析。
RUN_PIPELINE_ENTRY = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多模态数据准备 实例化包入口：少量评估（pilot）或全量执行（full）。由 instantiate 生成，勿手改。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    env = (os.environ.get("DATAEVOLVER_ROOT") or "").strip()
    if env:
        p = Path(env).resolve()
        if (p / "config").is_dir() and (p / "data").is_dir():
            return p
    for d in [start.resolve(), *start.resolve().parents]:
        if (d / "config").is_dir() and (d / "data").is_dir():
            return d
    sys.exit(
        "未找到 多模态数据准备 仓库根（需含 config/ 与 data/）。"
        "请 cd 到仓库根、设置 DATAEVOLVER_ROOT，或从本文件所在目录执行: python run_pipeline.py"
    )


def main() -> None:
    here = Path(__file__).resolve().parent
    root = _find_repo_root(here)
    os.environ["DATAEVOLVER_ROOT"] = str(root)
    os.environ["DATAEVOLVER_PIPELINE_ID"] = here.name
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from subsystems.pipeline_runtime.pilot.bundle_runner import entrypoint_main

    raise SystemExit(entrypoint_main())


if __name__ == "__main__":
    main()
'''


def write_run_pipeline_entry(bundle_dir: Path) -> Path:
    path = bundle_dir / "run_pipeline.py"
    path.write_text(RUN_PIPELINE_ENTRY.strip() + "\n", encoding="utf-8")
    try:
        mode = path.stat().st_mode | 0o111
        path.chmod(mode)
    except OSError:
        pass
    return path
