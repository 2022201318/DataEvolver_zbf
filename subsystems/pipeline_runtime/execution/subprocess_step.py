"""单步子进程执行：临时 JSONL + `subprocess_bridge`。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import sys
import uuid
from pathlib import Path
from typing import Any


class SubprocessOperatorError(RuntimeError):
    """子进程算子失败（非零退出或输出无效）。"""


def bridge_script_path() -> Path:
    return Path(__file__).resolve().parent / "subprocess_bridge.py"


def run_operator_subprocess(
    root: Path,
    stub_py: Path,
    records: list[dict[str, Any]],
    *,
    timeout_sec: float = 600.0,
    log_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    将 records 写入临时 JSONL，调用 `subprocess_bridge.py` 加载 stub 执行，再读回输出。
    """
    root_r = root.resolve()
    stub = stub_py.resolve()
    if not str(stub).startswith(str(root_r)):
        raise ValueError(f"stub 路径必须在仓库根下: {stub}")

    bridge = bridge_script_path()
    if not bridge.is_file():
        raise FileNotFoundError(f"缺少桥梁脚本: {bridge}")

    tmp_dir = root_r / "temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_in = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".in.jsonl",
        delete=False,
        dir=str(tmp_dir),
    )
    in_path = Path(tmp_in.name)
    out_path = in_path.with_suffix(".out.jsonl")
    try:
        for r in records:
            tmp_in.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp_in.close()

        cmd = [
            sys.executable,
            str(bridge),
            str(stub),
            str(in_path),
            str(out_path),
            str(root_r),
        ]
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(root_r),
            env=env,
        )
        log_txt = (
            f"cmd: {' '.join(cmd)}\n"
            f"returncode: {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}\n"
        )
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(log_txt, encoding="utf-8")

        if proc.returncode != 0:
            raise SubprocessOperatorError(log_txt[-8000:])

        if not out_path.is_file():
            raise SubprocessOperatorError("子进程未写出 output.jsonl")

        outp: list[dict[str, Any]] = []
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    outp.append(obj)
        return outp
    finally:
        in_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)
