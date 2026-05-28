#!/usr/bin/env python3
"""Cross-platform dev server helpers (backend / frontend)."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _venv_python() -> Path:
    if platform.system() == "Windows":
        p = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        p = ROOT / ".venv" / "bin" / "python"
    if not p.is_file():
        raise SystemExit(
            "Virtualenv not found. Run setup first:\n"
            "  python scripts/setup_env.py\n"
            "  # or: bash setup_env.sh  /  .\\setup_env.ps1"
        )
    return p


def _run_backend(host: str, port: int, reload: bool) -> int:
    py = _venv_python()
    cmd = [str(py), str(ROOT / "run_server.py"), "--host", host, "--port", str(port)]
    if reload:
        cmd.append("--reload")
    return subprocess.call(cmd, cwd=str(ROOT))


def _run_frontend() -> int:
    npm = "npm.cmd" if platform.system() == "Windows" else "npm"
    env = os.environ.copy()
    # vite dev: file watching on Windows / network drives
    env.setdefault("CHOKIDAR_USEPOLLING", "true")
    env.setdefault("CHOKIDAR_INTERVAL", "1000")
    return subprocess.call([npm, "run", "dev"], cwd=str(ROOT / "frontend"), env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DataEvolver dev servers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_back = sub.add_parser("backend", help="Start FastAPI (uvicorn)")
    p_back.add_argument("--host", default="0.0.0.0")
    p_back.add_argument("--port", type=int, default=8000)
    p_back.add_argument("--reload", action="store_true", default=True)

    sub.add_parser("frontend", help="Start Vite dev server")

    args = parser.parse_args(argv)
    if args.cmd == "backend":
        return _run_backend(args.host, args.port, args.reload)
    if args.cmd == "frontend":
        return _run_frontend()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
