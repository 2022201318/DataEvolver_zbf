# Installation & deployment

DataEvolver runs as **backend (Python/FastAPI)** + **frontend (React/Vite)**. All platforms use the same bootstrap entry: `scripts/setup_env.py`.

## Requirements

| Component | Version | Notes |
|-----------|---------|--------|
| Python | **3.10+** | Used for API, CLI, workflow engine |
| Node.js | **18+ LTS** | Required for Web UI (`frontend/`) |
| npm | bundled with Node | `npm ci` in `frontend/` |
| LLM API | OpenAI-compatible | Configure after install |

Optional: **Git** (clone), **8GB+ RAM** recommended when running LLM steps locally via API.

## One-command setup

From the repository root:

| Platform | Command |
|----------|---------|
| **Linux / macOS** | `bash setup_env.sh` |
| **Windows PowerShell** | `powershell -ExecutionPolicy Bypass -File .\setup_env.ps1` |
| **Windows CMD** | `setup_env.bat` |
| **Any OS** (recommended) | `python scripts/setup_env.py` |

### Setup options

```bash
python scripts/setup_env.py              # full install (backend + frontend)
python scripts/setup_env.py --skip-frontend   # API / CLI only
python scripts/setup_env.py --frontend-only   # npm only (venv must exist)
```

Environment variable `PYTHON_BIN` overrides the Python executable (all wrappers respect it).

## Configure LLM

After setup, edit (created from templates if missing):

```text
config/api_config.json    # provider, base_url, model, temperature, …
config/api_keys.json      # api_key (or set api_key inside api_config.json)
```

These files are **gitignored** — do not commit secrets.

## Start services (development)

Use **two terminals** (backend + frontend).

### Backend (port 8000)

| Platform | Command |
|----------|---------|
| Linux / macOS | `source .venv/bin/activate && python run_server.py --reload` |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` then `python run_server.py --reload` |
| **Cross-platform** | `python scripts/dev.py backend` |

### Frontend (port 5173)

| Platform | Command |
|----------|---------|
| Any | `cd frontend && npm run dev` |
| **Cross-platform** | `python scripts/dev.py frontend` |

### URLs

| Service | URL |
|---------|-----|
| Web UI | http://127.0.0.1:5173 |
| HTTP API | http://127.0.0.1:8000 |
| OpenAPI | http://127.0.0.1:8000/docs |

## CLI smoke test

```bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

dataevolver --help
python scripts/setup_env.py   # if not done yet
```

Example session (sample data under `tmp/samples/`):

```bash
dataevolver session-start demo_fin \
  --raw tmp/samples/finance_raw.jsonl \
  --seed tmp/samples/finance_seed.jsonl \
  --description tmp/samples/finance_description.txt

dataevolver workflow advance-all demo_fin --max-steps 32
```

## Production notes

- Build frontend: `cd frontend && npm run build` → static assets in `frontend/dist/`
- Run API without reload: `python run_server.py --host 0.0.0.0 --port 8000`
- Serve `frontend/dist/` behind nginx/Caddy, or use `npm run preview` for a quick static preview
- Set `DATAEVOLVER_ROOT` to the repo root if the process cwd differs
- Runtime data lives under `data/` (see `data/README.md`) — back up `data/uploads/` and workflow state as needed

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Python not found` | Install Python 3.10+ and ensure it is on `PATH` |
| Windows `execution of scripts is disabled` | Run PowerShell as: `-ExecutionPolicy Bypass -File .\setup_env.ps1` |
| `npm not found` | Install [Node.js LTS](https://nodejs.org/); reopen terminal |
| Port 8000 / 5173 in use | Change port: `python run_server.py --port 8001`; Vite port in `frontend/vite.config.ts` |
| API 401 / LLM errors | Check `config/api_config.json` and `config/api_keys.json` |
| Frontend cannot reach API | Ensure backend is running; check browser network tab for `localhost:8000` |

## Directory layout (after install)

```text
DataEvolver/
├── .venv/                 # Python virtualenv (created by setup)
├── config/                # api_config.json, api_keys.json (local)
├── data/                  # runtime artifacts (gitignored)
├── frontend/node_modules/ # npm deps (created by setup)
├── scripts/
│   ├── setup_env.py       # cross-platform installer
│   └── dev.py             # dev server helpers
├── setup_env.sh           # Linux / macOS / Git Bash
├── setup_env.ps1          # Windows PowerShell
└── setup_env.bat          # Windows CMD
```
