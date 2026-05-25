#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ -n "${PYTHON_BIN:-}" ]; then
  :
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python is not found in PATH. Please install Python 3.10+." >&2
  exit 1
fi

echo "[1/5] Create virtual environment (.venv)"
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

# Linux/macOS: .venv/bin/activate; Windows (Git Bash): .venv/Scripts/activate
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
elif [ -f ".venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/Scripts/activate"
else
  echo "Cannot find virtualenv activate script under .venv/" >&2
  exit 1
fi

echo "[2/5] Upgrade pip"
python -m pip install --upgrade pip

echo "[3/5] Install backend dependencies"
pip install -r requirements.txt
pip install -e .

echo "[4/5] Prepare config templates"
if [ ! -f "config/api_config.json" ] && [ -f "config/api_config.example.json" ]; then
  cp "config/api_config.example.json" "config/api_config.json"
fi
if [ ! -f "config/api_keys.json" ] && [ -f "config/api_keys.example.json" ]; then
  cp "config/api_keys.example.json" "config/api_keys.json"
fi

echo "[5/5] Install frontend dependencies"
cd frontend
if [ -f "package-lock.json" ]; then
  npm ci
else
  npm install
fi
cd "$ROOT_DIR"

echo
echo "Environment is ready."
echo "Next:"
echo "  1) Fill API keys in config/api_config.json (and/or config/api_keys.json)."
echo "  2) Start backend:"
echo "     Linux/macOS: source .venv/bin/activate && python run_server.py --reload"
echo "     Windows(Git Bash): source .venv/Scripts/activate && python run_server.py --reload"
echo "  3) Start frontend: cd frontend && npm run dev"
