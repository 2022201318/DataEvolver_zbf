# DataEvolver

<p align="center">
  <b>Automatic Data Preparation for LLM Training via Multi-Level Self-Evolving</b><br/>
  A workflow-first system that turns raw input + seed examples into high-quality training data.
</p>

<p align="center">
  <a href="assets/DataEvolver.pdf">📄 Paper (PDF)</a> |
  <a href="#-demo-video">🎬 Demo</a> |
  <a href="#-quick-start-one-command">⚡ Quick Start</a> |
  <a href="#-citation">📚 Citation</a>
</p>

---

## 🔥 Why DataEvolver

Building training data pipelines for LLMs is hard because most solutions are either:

1. **Hard-coded and brittle** (do not transfer across datasets/tasks), or
2. **LLM-driven but opaque** (hard to debug, reproduce, and improve).

DataEvolver addresses this with a **multi-level self-evolving workflow**:

- **Operator-level self-evolving**: detect orchestration gaps and evolve missing operators.
- **Pipeline-level self-evolving**: use trial/quality feedback to improve future rounds.
- **Artifact-first execution**: every stage writes inspectable outputs under `data/`.
- **Unified semantics**: CLI, HTTP API, and Web UI share the same workflow state model.

---

## 🧠 Framework Overview

> System illustration from the paper.

📎 [Open full figure (PDF)](assets/ill.pdf)

The core loop is:

`understanding -> orchestration -> operator_evolution -> instantiation -> trial_run -> quality_check -> experience`

When quality passes, DataEvolver runs full execution (`run-full`) for final data generation.

---

## 📊 Main Results

### Overall Performance

![Main Experiment Results](assets/main_exp.png)

### Comparison Across Baselines

![Comparison Results](assets/compare.png)

### Ablation Study

![Ablation Study](assets/ablation.png)

### Case Study

📎 [Open case analysis (PDF)](assets/case.pdf)

---

## 🎬 Demo Video

- **GitHub Release (recommended for clean clone)**:  
  `https://github.com/<YOUR_ORG_OR_USER>/<YOUR_REPO>/releases/download/<TAG>/DataEvolver_Demo_small.mov`
- **Local file in this release bundle**: [`assets/DataEvolver_Demo_small.mov`](assets/DataEvolver_Demo_small.mov)

> Replace `<YOUR_ORG_OR_USER>`, `<YOUR_REPO>`, and `<TAG>` after creating your GitHub Release.

---

## ⚡ Quick Start (One Command)

### 1) Bootstrap full environment

```bash
cd DataEvolver
bash setup_env.sh
```

This command will automatically:

- create `.venv` and install backend dependencies
- install package in editable mode (`pip install -e .`)
- install frontend dependencies (`npm ci`)
- generate `config/api_config.json` / `config/api_keys.json` from examples (if missing)

### 2) Configure LLM API

Edit `config/api_config.json` (and/or `config/api_keys.json`) with your provider/model/key.

### 3) Run backend + frontend

Backend:

```bash
source .venv/bin/activate
python run_server.py --reload
```

Frontend:

```bash
cd frontend
npm run dev
```

Access:

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Frontend: [http://127.0.0.1:5173](http://127.0.0.1:5173)

---

## 🛠️ What You Can Do

- Create a pipeline session from raw input + seed examples.
- Advance workflow step-by-step and inspect artifacts at each stage.
- Rerun from any step (`rerun`) for controlled iteration.
- Run trial execution + quality checks before full execution.
- Track token usage and iterative history.

---

## 🧩 Project Structure

```text
DataEvolver/
├── core/                 # config/path/llm/log/token services
├── subsystems/           # workflow and stage implementations
├── web/                  # FastAPI app and routers
├── frontend/             # React + Vite app
├── cli/                  # Typer CLI
├── config/               # runtime config templates
├── data/                 # runtime artifacts
├── assets/               # paper figures, tables, demo media
└── setup_env.sh          # one-command environment bootstrap
```
