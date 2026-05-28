# Runtime data directory

This folder holds **local workflow state** and **versioned config** for DataEvolver.

## Shipped with the repo (safe to commit)

| File | Purpose |
|------|---------|
| `operator_registry.json` | Built-in operator definitions |
| `operator_categories.json` | UI category labels |
| `operator_registry_general.json` | Promoted cross-task operators (starts empty `{}`) |
| `pipeline_templates.json` | Pipeline templates |

## Created at runtime (gitignored)

| Path | Purpose |
|------|---------|
| `manifest.jsonl` | Session registry (raw/seed paths per pipeline) |
| `workflow_runs/<id>/` | Workflow step state |
| `uploads/<id>/` | Uploaded raw / seed / description files |
| `orchestration_results/` | DAG orchestration output |
| `generated_pipelines/` | Instantiated pipeline code |
| `artifact_history/` | Per-round / per-iteration snapshots |
| `dag_assessment_results/` | DAG assessment snapshots |
| `quality_check_results/` | Quality check snapshots |
| `operator_registry_user/<id>.json` | Task-specific evolved or CLI-added operators |
| `operator_registry_domain/` | Domain-level promoted operators |
| `operator_memory/` | Operator promotion stats & events |

Do not commit local experiment outputs. Use `tmp/samples/` or your own uploads under `data/uploads/` after `session-start`.
