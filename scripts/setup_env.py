#!/usr/bin/env python3
"""
Cross-platform environment bootstrap for DataEvolver.

Used by setup_env.sh / setup_env.ps1 / setup_env.bat at the repository root.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
MIN_PYTHON = (3, 10)
MIN_NODE_MAJOR = 18


def _tr(zh: str, en: str) -> str:
    lang = (os.environ.get("DATAEVOLVER_LANG") or "zh").strip().lower()
    return en if lang == "en" else zh


def _step(msg: str) -> None:
    print(msg, flush=True)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    subprocess.run(cmd, cwd=str(cwd or ROOT), env=merged, check=True)


def _python_version_tuple(exe: str) -> tuple[int, int, int]:
    out = subprocess.check_output([exe, "-c", "import sys; print(sys.version_info[:3])"], text=True)
    parts = [int(x.strip()) for x in out.strip().strip("()").split(",")]
    return parts[0], parts[1], parts[2] if len(parts) > 2 else 0


def _resolve_host_python() -> str:
    if os.environ.get("PYTHON_BIN"):
        return os.environ["PYTHON_BIN"]
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(_tr("未找到 Python，请安装 Python 3.10+", "Python not found; install Python 3.10+"))


def _venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _venv_activate_hint() -> tuple[str, str]:
    if platform.system() == "Windows":
        ps1 = ".\\.venv\\Scripts\\Activate.ps1"
        bash = "source .venv/Scripts/activate"
        return ps1, bash
    return "source .venv/bin/activate", "source .venv/bin/activate"


def _check_host_python() -> str:
    py = _resolve_host_python()
    major, minor, _ = _python_version_tuple(py)
    if (major, minor) < MIN_PYTHON:
        need = ".".join(str(x) for x in MIN_PYTHON)
        raise RuntimeError(
            _tr(
                f"需要 Python {need}+，当前 {major}.{minor}",
                f"Python {need}+ required, got {major}.{minor}",
            )
        )
    return py


def _ensure_venv(host_python: str) -> Path:
    vpy = _venv_python()
    if not vpy.is_file():
        _step(_tr("[1/5] 创建虚拟环境 (.venv)", "[1/5] Create virtual environment (.venv)"))
        _run([host_python, "-m", "venv", str(VENV_DIR)])
    else:
        _step(_tr("[1/5] 虚拟环境已存在 (.venv)", "[1/5] Virtual environment exists (.venv)"))
    if not vpy.is_file():
        raise RuntimeError(_tr("创建 .venv 失败", "Failed to create .venv"))
    return vpy


def _install_backend(vpy: Path) -> None:
    _step(_tr("[2/5] 升级 pip", "[2/5] Upgrade pip"))
    _run([str(vpy), "-m", "pip", "install", "--upgrade", "pip"])
    _step(_tr("[3/5] 安装后端依赖", "[3/5] Install backend dependencies"))
    _run([str(vpy), "-m", "pip", "install", "-r", "requirements.txt"])
    _run([str(vpy), "-m", "pip", "install", "-e", "."])


def _prepare_config() -> None:
    _step(_tr("[4/5] 准备配置模板", "[4/5] Prepare config templates"))
    cfg = ROOT / "config"
    pairs = [
        ("api_config.example.json", "api_config.json"),
        ("api_keys.example.json", "api_keys.json"),
    ]
    for src_name, dst_name in pairs:
        src, dst = cfg / src_name, cfg / dst_name
        if not dst.is_file() and src.is_file():
            shutil.copy2(src, dst)
            _step(f"  + {dst.relative_to(ROOT)}")


def _node_major() -> int | None:
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        out = subprocess.check_output(["node", "-v"], text=True).strip()
        if out.startswith("v"):
            out = out[1:]
        return int(out.split(".")[0])
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def _install_frontend(*, required: bool) -> None:
    major = _node_major()
    if major is None:
        msg = _tr(
            "未找到 Node.js / npm。请安装 Node.js 18+ LTS: https://nodejs.org/",
            "Node.js / npm not found. Install Node.js 18+ LTS: https://nodejs.org/",
        )
        if required:
            raise RuntimeError(msg)
        _step(_tr("[5/5] 跳过前端（未安装 npm）", "[5/5] Skip frontend (npm missing)"))
        print(msg)
        return
    if major < MIN_NODE_MAJOR:
        raise RuntimeError(
            _tr(
                f"需要 Node.js {MIN_NODE_MAJOR}+，当前主版本 {major}",
                f"Node.js {MIN_NODE_MAJOR}+ required, got major {major}",
            )
        )
    _step(_tr("[5/5] 安装前端依赖", "[5/5] Install frontend dependencies"))
    frontend = ROOT / "frontend"
    lock = frontend / "package-lock.json"
    cmd = ["npm", "ci"] if lock.is_file() else ["npm", "install"]
    _run(cmd, cwd=frontend)


def _print_next_steps(*, skipped_frontend: bool) -> None:
    ps1, bash = _venv_activate_hint()
    plat = platform.system()
    _step("")
    _step(_tr("环境就绪。", "Environment is ready."))
    _step(_tr("下一步：", "Next steps:"))
    _step(_tr("  1) 填写 LLM 配置:", "  1) Configure LLM:"))
    _step("     config/api_config.json")
    _step("     config/api_keys.json")
    _step(_tr("  2) 启动后端:", "  2) Start backend:"))
    if plat == "Windows":
        _step(f"     PowerShell: {ps1}")
        _step("     python run_server.py --reload")
        _step(_tr("     或: python scripts/dev.py backend", "     Or: python scripts/dev.py backend"))
    else:
        _step(f"     {bash}")
        _step("     python run_server.py --reload")
        _step(_tr("     或: python scripts/dev.py backend", "     Or: python scripts/dev.py backend"))
    if not skipped_frontend:
        _step(_tr("  3) 启动前端:", "  3) Start frontend:"))
        _step(_tr("     cd frontend && npm run dev", "     cd frontend && npm run dev"))
        _step(_tr("     或: python scripts/dev.py frontend", "     Or: python scripts/dev.py frontend"))
    _step(_tr("  4) 打开 Web UI: http://127.0.0.1:5173", "  4) Open Web UI: http://127.0.0.1:5173"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DataEvolver cross-platform setup")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip npm install (API/CLI only)",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Only install frontend dependencies (venv must exist)",
    )
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    _step(_tr(f"DataEvolver 安装 · {platform.system()} · {ROOT}", f"DataEvolver setup · {platform.system()} · {ROOT}"))

    try:
        if args.frontend_only:
            _install_frontend(required=True)
            _print_next_steps(skipped_frontend=False)
            return 0

        host_python = _check_host_python()
        vpy = _ensure_venv(host_python)
        _install_backend(vpy)
        _prepare_config()
        if args.skip_frontend:
            _print_next_steps(skipped_frontend=True)
        else:
            _install_frontend(required=False)
            _print_next_steps(skipped_frontend=shutil.which("npm") is None)
        return 0
    except subprocess.CalledProcessError as e:
        _step(_tr(f"\n命令失败 (exit {e.returncode}): {' '.join(e.cmd)}", f"\nCommand failed (exit {e.returncode})"))
        return e.returncode or 1
    except RuntimeError as e:
        _step(f"\n{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
