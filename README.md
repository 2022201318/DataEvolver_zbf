# DataEvolver

<p align="center">
  <b>Automatic Data Preparation for Large Language Models via Multi-Level Self-Evolving</b><br/>
  Turn raw data and a small set of high-quality seed examples into training-ready data automatically.
</p>

<p align="center">
  <a href="assets/DataEvolver.pdf">📄 Paper</a> |
  <a href="#-demo-video">🎬 Demo</a> |
  <a href="#-framework-overview">🧠 Framework</a> |
  <a href="#-main-results">📊 Results</a> |
  <a href="#-quick-start">⚡ Quick Start</a>
</p>

---

## Overview

Training data quality is one of the key bottlenecks in LLM post-training.  
In practical scenarios, raw data is often noisy, structurally inconsistent, redundant, or not directly suitable for supervised fine-tuning.

**DataEvolver** is a system for **automatic data preparation**.  
Given:

- **raw data**
- a small set of **high-quality seed examples**
- an optional **task description**

DataEvolver automatically constructs and iteratively improves a data preparation pipeline, then produces **high-quality, training-ready data** aligned with the seed specification.

Unlike fixed data recipes or one-shot pipeline synthesis, DataEvolver is designed as a **self-evolving system**: it not only generates pipelines, but also checks, repairs, instantiates, trials, evaluates, and refines them through feedback.

---

## 🔥 Why DataEvolver

Most existing solutions for LLM data preparation fall into two categories:

1. **Predefined pipelines**  
   Strong engineering systems, but heavily dependent on manually designed recipes and less adaptive to new tasks.

2. **One-shot pipeline synthesis**  
   More flexible, but often unstable in executability and output quality.

DataEvolver targets a harder but more practical setting:

> **Can we automatically build a high-quality data preparation pipeline from raw data and only a small set of seed examples?**

This requires jointly optimizing:

- **executability** (the pipeline must run correctly)
- **quality alignment** (outputs must match the target profile implied by seeds)

DataEvolver addresses both through **multi-level self-evolving**.

---

## ✨ Key Ideas

### 1) Seed-guided understanding

Instead of requiring users to describe every data transformation manually, DataEvolver learns the target profile directly from seed examples and sampled raw data, including:

- field structure and output format
- style and quality constraints
- difficulty and preference signals

### 2) Operator-level self-evolving

A one-shot long pipeline is often logically fragile.  
DataEvolver builds and validates a DAG, detects issues (dependency gaps, interface mismatch, ordering conflicts), and can repair the DAG or synthesize new operators when needed.

### 3) Pipeline-level self-evolving

Even executable pipelines may still produce low-quality outputs.  
DataEvolver runs trial execution, compares trial outputs against seed quality, summarizes discrepancy as **experience**, and uses it to refine the next round.

This pushes the system from:

`raw-data-compatible -> executable -> seed-aligned -> training-ready`

---

## 🧠 Framework Overview

📎 [Open framework figure (PDF)](assets/ill.pdf)

**Figure explanation.**
DataEvolver takes raw data, seed data, and optional user descriptions as input, then runs four major stages:

1. **Understanding**: infer a structured target profile from seeds and sampled raw data.
2. **Logic orchestration**: generate a logical pipeline DAG from operator library and constraints.
3. **Operator instantiation**: convert logical operators into executable actions and run them on sample data.
4. **Quality check + experience update**: compare trial outputs with seed expectations, summarize discrepancies, and refine next-round planning.

Core loop:

```text
understanding -> orchestration -> operator_evolution -> instantiation -> trial_run -> quality_check -> experience
```

When quality is sufficient, DataEvolver applies the refined pipeline to full data execution.

---

## 📊 Main Results

### Overall downstream performance

![Main Experiment Results](assets/main_exp.png)

**What this figure shows.**
Across 7 benchmarks from 4 task categories (instruction following, multiple-choice QA, math reasoning, text-to-SQL), DataEvolver consistently improves training data quality and downstream model performance.
On average, it brings **about 12% relative gain** on downstream outcomes compared with weaker data preparation settings.

### Comparison against strong baselines

![Comparison Results](assets/compare.png)

**What this figure shows.**
DataEvolver outperforms both vanilla SFT on raw/original data and strong data-preparation baselines.
A key takeaway is that better prepared data can partially compensate for data scale: in several settings, fewer DataEvolver-produced samples approach or exceed larger but weaker-prepared alternatives.

### Why the system works: multi-level self-evolving matters

![Ablation Study](assets/ablation.png)

**What this figure shows.**
The gains are not from a single module.
Removing either self-evolving loop hurts performance:

- without operator-level self-evolving, pipelines are less executable/coherent
- without pipeline-level self-evolving, outputs are less aligned with seed quality

This validates the need to jointly optimize **executability + quality alignment**.

### Data quality and efficiency

DataEvolver improves prepared data quality (training-readiness, seed alignment, consistency, and redundancy reduction) while also reducing preparation overhead.
It lowers amortized token cost in data preparation by **about 40% on average**.

### Case study

📎 [Open case analysis (PDF)](assets/case.pdf)

The case study shows how DataEvolver evolves from an initial logical plan to a refined executable pipeline, and how trial feedback is translated into better constraints and better data in later rounds.

---

## 🎬 Demo Video

- **GitHub Release (recommended; small download for a clean clone)**:  
  [Download `DataEvolver_Demo_small.mov`](https://github.com/Akanezora0/DataEvolver/releases/download/demo-2026-04-18/DataEvolver_Demo_small.mov)

- **Bundled in this repo** (if you already have the source tree): [`assets/DataEvolver_Demo_small.mov`](assets/DataEvolver_Demo_small.mov)

---

## 🖥️ System Interfaces

DataEvolver supports three aligned interfaces:

- **Web UI**: visualize DAG, inspect stages/artifacts, and control workflow interactively.
- **CLI**: reproducible experiments, scripted runs, and debugging.
- **HTTP API**: integration with external services.

All interfaces share the same workflow semantics and state-driven execution logic.

---

## ⚡ Quick Start

### 1) Bootstrap environment

```bash
cd DataEvolver
bash setup_env.sh
```

This script automatically:

- creates a Python virtual environment
- installs backend dependencies
- installs package in editable mode
- installs frontend dependencies
- generates config templates if missing

### 2) Configure LLM API

Edit:

```text
config/api_config.json
config/api_keys.json
```

Fill provider, base URL, model, and API key.

### 3) Start backend and frontend

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

### 4) Open the system

- Frontend: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`

---

## 🛠️ Usage Guide

### A) Web UI workflow

Recommended workflow:

1. Create/select a pipeline session
2. Upload raw data
3. Upload seed data
4. Optionally provide task description
5. Run steps one-by-one or continuously
6. Inspect artifacts and evolution history
7. Trigger full execution only after quality criteria are met

Typical stages:

```text
understanding
orchestration
operator_evolution
instantiation
trial_run
quality_check
experience
run_full
```

### B) CLI workflow

Check help and state:

```bash
source .venv/bin/activate
dataevolver --help
dataevolver state my_pipeline
```

Run next required step:

```bash
dataevolver advance my_pipeline
dataevolver state my_pipeline
```

Run multiple steps continuously:

```bash
dataevolver workflow advance-all my_pipeline --max-steps 32
```

Run specific stages directly:

```bash
dataevolver understand my_pipeline
dataevolver orchestrate my_pipeline
dataevolver instantiate my_pipeline
dataevolver trial my_pipeline
dataevolver quality-check my_pipeline
dataevolver experience my_pipeline
dataevolver run my_pipeline
```

Rerun from a stage:

```bash
dataevolver rerun my_pipeline orchestration
```

Inspect token statistics:

```bash
dataevolver tokens my_pipeline
dataevolver tokens --json my_pipeline
```

Machine-readable outputs for automation:

```bash
dataevolver state --json my_pipeline
dataevolver advance --json my_pipeline
```

### C) HTTP API

Core routes:

- `POST /api/sessions/start`
- `GET /api/workflow/{pipeline_id}/state`
- `POST /api/workflow/{pipeline_id}/advance`
- `POST /api/workflow/{pipeline_id}/rerun`
- `POST /api/pipeline/{pipeline_id}/run-full`

OpenAPI:

```text
http://127.0.0.1:8000/docs
```

---

## 🧩 Project Structure

```text
DataEvolver/
├── core/                 # config / path / llm / log / token services
├── subsystems/           # main workflow subsystems
├── web/                  # FastAPI app and routers
├── frontend/             # React + Vite frontend
├── cli/                  # Typer CLI
├── config/               # runtime configs and templates
├── data/                 # runtime artifacts and workflow states
├── assets/               # paper figures, tables, demo media
└── setup_env.sh          # one-command environment bootstrap
```

---

## 📌 Current Scope

DataEvolver currently focuses on **text data preparation for LLM training**.
The current release mainly targets:

- instruction tuning data
- QA-style supervision
- math reasoning traces
- text-to-SQL training data

The architecture is extensible to broader tasks and modalities in future versions.

---

## 📚 Citation

If you find DataEvolver useful, please cite:

```bibtex
@article{dataevolver2026,
  title={DataEvolver: Automatic Data Preparation for Large Language Models through Multi-Level Self-Evolving},
  author={Anonymous},
  journal={ACL 2026},
  year={2026}
}
```

---

## Star History

If this project helps your research or product, please consider starring the repository.
