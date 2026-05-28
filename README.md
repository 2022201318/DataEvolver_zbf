<div align="center">

# DataEvolver

**Automatic data preparation for LLMs via multi-level self-evolving pipelines**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/dataevolver?color=306998)](https://pypi.org/project/dataevolver/)
[![Paper](https://img.shields.io/badge/Paper-PDF-red?logo=adobeacrobatreader&logoColor=white)](assets/DataEvolver.pdf)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**[Paper](assets/DataEvolver.pdf)** · **[Demo](#demo)** · **[Install](#install)** · **[Quick Start](#quick-start)** · **[Results](#results)**

<br/>

<img src="assets/DataEvolver.png" width="720" alt="DataEvolver overview"/>

<br/>

<sub>Give us a ⭐ if DataEvolver helps your data-prep workflow.</sub>

</div>

## What is DataEvolver?

**Raw corpora are noisy. Seeds show what “good” looks like. DataEvolver closes the gap automatically.**

You provide **raw data** + a handful of **seed examples** (and optionally a task description). DataEvolver:

1. **Understands** the target profile implied by seeds  
2. **Orchestrates** an operator DAG, validates it, and evolves missing operators when needed  
3. **Instantiates & trials** the pipeline, judges sample quality, and **refines across rounds**  
4. **Runs full preparation** when quality gates pass  

Unlike one-shot pipeline synthesis, DataEvolver jointly optimizes **executability** (does it run end-to-end?) and **seed alignment** (does output match your supervision style?) through **multi-level self-evolving** loops.

| Input | System | Output |
|:------|:-------|:-------|
| Raw data + seeds | LLM-guided understanding & DAG repair | Structured artifacts + executable pipeline |
| Trial feedback | Pilot judge + experience reflow | Iteratively better, seed-aligned datasets |

## Results

> Empirical evidence from our paper — DataEvolver improves downstream training across diverse task types.

<table align="center">
<tr>
<td align="center"><b>~12%</b><br/><sub>avg relative gain vs.<br/>weaker prep settings</sub></td>
<td align="center"><b>7</b> benchmarks<br/><sub>instruction · MC-QA · math · SQL</sub></td>
<td align="center"><b>~40%</b><br/><sub>lower amortized token cost<br/>on average</sub></td>
</tr>
</table>

<br/>

<p align="center">
  <img src="assets/main_exp.png" width="92%" alt="Main experiment: downstream performance across 7 benchmarks"/>
</p>

<p align="center"><i>Downstream performance across 7 benchmarks from 4 task categories.</i></p>

<p align="center">
  <img src="assets/compare.png" width="88%" alt="Comparison against strong baselines"/>
</p>

<p align="center"><i>DataEvolver vs. vanilla SFT on raw data and strong data-prep baselines — fewer, better-prepared samples can match larger weakly-prepared sets.</i></p>

<details>
<summary><b>Ablation & case study (click to expand)</b></summary>

<br/>

**Both evolution loops matter**

<p align="center"><img src="assets/ablation.png" width="80%" alt="Ablation study"/></p>

- Without **operator-level** evolution → pipelines are less executable and coherent  
- Without **pipeline-level** evolution → outputs are less seed-aligned  

**Case study: how a plan evolves across rounds**

<p align="center"><img src="assets/case.png" width="92%" alt="Case study"/></p>

</details>

## Demo

Watch the **evolution canvas** in action — DAG orchestration tabs, instantiation, trial scoring, and experience reflow across rounds.

<p align="center">
  <video src="assets/demo.mp4" controls width="92%">
    Your browser does not support embedded video.
    <a href="assets/demo.mp4">Download demo.mp4</a>
    or the
    <a href="https://github.com/Akanezora0/DataEvolver/releases/download/demo-2026-04-18/DataEvolver_Demo_small.mov">full-resolution release (.mov)</a>.
  </video>
</p>

## How it works

<p align="center">
  <img src="assets/ill.png" width="92%" alt="DataEvolver framework"/>
</p>

```text
understanding → orchestration → operator_evolution → instantiation
             → trial_run → quality_check → experience → (refine or full run)
```

**Three self-evolving layers**

| Layer | What happens |
|:------|:-------------|
| **Understanding** | Infer schema, style, and quality constraints from seeds + raw samples |
| **Operator evolution** | Repair DAG structure; synthesize operators when the registry is insufficient |
| **Pipeline evolution** | Convert trial-vs-seed gaps into experience for the next round |

Web UI, CLI, and HTTP API share the **same workflow semantics** — pick the interface that fits your workflow.

## Install

> Full cross-platform guide: **[docs/INSTALL.md](docs/INSTALL.md)**

**Requirements:** Python **3.10+** · Node.js **18+** (Web UI only) · OpenAI-compatible LLM API

### From source (Web UI + CLI + API)

```bash
git clone https://github.com/Akanezora0/DataEvolver.git
cd DataEvolver
python scripts/setup_env.py    # or: bash setup_env.sh / setup_env.ps1
```

Edit `config/api_config.json` and `config/api_keys.json` (copied from `*.example.json`).

### From PyPI (CLI + API)

```bash
pip install dataevolver
mkdir my_project && cd my_project
dataevolver init
# edit config/api_config.json & config/api_keys.json
dataevolver --help
```

## Quick Start

**Terminal 1 — backend**

```bash
python scripts/dev.py backend          # → http://127.0.0.1:8000
```

**Terminal 2 — frontend**

```bash
python scripts/dev.py frontend         # → http://127.0.0.1:5173
```

**CLI — first pipeline**

```bash
dataevolver session-start my_pipeline \
  --raw tmp/samples/finance_raw.jsonl \
  --seed tmp/samples/finance_seed.jsonl \
  --description tmp/samples/finance_description.txt

dataevolver workflow advance-all my_pipeline --max-steps 32
dataevolver state my_pipeline
```

Open **http://127.0.0.1:5173** to explore the evolution canvas, or stay in the terminal with `dataevolver advance my_pipeline`.

## Usage

<table>
<tr><th>Interface</th><th>Best for</th><th>Entry</th></tr>
<tr>
  <td><b>Web UI</b></td>
  <td>Exploration, visual DAG & trial inspection</td>
  <td><code>http://127.0.0.1:5173</code></td>
</tr>
<tr>
  <td><b>CLI</b></td>
  <td>Reproducible runs, scripting, CI</td>
  <td><code>dataevolver --help</code> · <code>dataevolver wf --help</code></td>
</tr>
<tr>
  <td><b>HTTP API</b></td>
  <td>Integration & automation</td>
  <td><code>http://127.0.0.1:8000/docs</code></td>
</tr>
</table>

**Common CLI commands**

| Action | Command |
|:-------|:--------|
| Check progress | `dataevolver state my_pipeline` |
| Run next step | `dataevolver advance my_pipeline` |
| Run full chain | `dataevolver workflow advance-all my_pipeline` |
| Re-orchestrate | `dataevolver orchestrate my_pipeline` |
| Full dataset run | `dataevolver run my_pipeline` |
| Token usage | `dataevolver tokens my_pipeline` |
| Switch language | `dataevolver lang en` |

**Operator pool** — add custom operators, then re-orchestrate:

```bash
dataevolver op list -p my_pipeline
dataevolver op add my_op -p my_pipeline -d "Clean records" -c structure
dataevolver orchestrate my_pipeline
```

<details>
<summary><b>Project layout & configuration</b></summary>

```text
DataEvolver/
├── core/           # config, paths, LLM client, logging
├── subsystems/     # understanding, orchestration, workflow, …
├── web/            # FastAPI
├── frontend/       # React evolution canvas
├── cli/            # Typer CLI (dataevolver)
├── config/         # api_config, api_keys, operator registry
├── data/           # runtime artifacts (gitignored)
└── assets/         # paper figures, demo video
```

| File | Purpose |
|:-----|:--------|
| `config/api_config.json` | LLM provider, model, endpoints |
| `config/api_keys.json` | API credentials (**gitignored**) |
| `data/workflow_runs/{id}/state.json` | Per-pipeline progress |

</details>

<details>
<summary><b>FAQ</b></summary>

**Why does instantiation finish instantly?**  
Artifacts may be **reused** (`skipped`). Built-in operators use templates; only `requires_llm` operators trigger LLM codegen. Check UI banners or `dataevolver state`.

**Why does experience finish quickly?**  
Experience is **rule-based aggregation** over quality/trial results — deterministic reflow, not LLM rewriting.

**Why multiple orchestration tabs?**  
Each tab is a distinct attempt (e.g. failed validation → repaired DAG). Archives: `data/artifact_history/{pipeline_id}/`.

**Supported data formats?**  
Text preparation for LLM training: instruction tuning, QA, math reasoning, text-to-SQL.

</details>

## Community

| | |
|:--|:--|
| **Issues & features** | [GitHub Issues](https://github.com/Akanezora0/DataEvolver/issues) |
| **Questions** | [GitHub Discussions](https://github.com/Akanezora0/DataEvolver/discussions) |
| **Contributing** | Fork → focused PR with verify steps; good first areas: operators, docs, UI polish |

## Citation

If you use DataEvolver in research, please cite our paper:

```bibtex
@article{dataevolver2026,
  title   = {DataEvolver: Automatic Data Preparation for Large Language Models via Multi-Level Self-Evolving},
  author  = {/* authors */},
  journal = {/* venue */},
  year    = {2026}
}
```

📄 [assets/DataEvolver.pdf](assets/DataEvolver.pdf)

---

<p align="center">
  <sub>Built for teams who want <b>executable</b> and <b>seed-aligned</b> data pipelines — not one-shot prompts.</sub>
</p>
