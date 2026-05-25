"""
Operator registry API (memory hierarchy):
- base: `data/operator_registry.json`
- general: `data/operator_registry_general.json`
- domain: `data/operator_registry_domain/<domain>.json`
- task: `data/operator_registry_user/<pipeline_id>.json`
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from subsystems.operator_management import OperatorRegistryStore

router = APIRouter(prefix="/operators", tags=["operators"])


def _store(request: Request, pipeline_id: str | None = None) -> OperatorRegistryStore:
    root = request.app.state.config.root
    return OperatorRegistryStore(root, pipeline_id=pipeline_id)


@router.get("/")
def list_operators(
    request: Request,
    pipeline_id: str | None = Query(default=None, description="Optional pipeline id for isolated user registry"),
) -> dict[str, Any]:
    """
    Return merged operator list for UI.
    Source label: base | general | domain | task.
    Does not include legacy global user registry (see OperatorRegistryStore.to_api_operator_list).
    """
    store = _store(request, pipeline_id=pipeline_id)
    operators = store.to_api_operator_list()
    task_names = sorted(store.load_task().keys()) if pipeline_id else []
    domain_names = sorted(store.load_domain().keys()) if pipeline_id else []
    general_names = sorted(store.load_general().keys())
    legacy_names = sorted(store.load_legacy_user().keys())
    return {
        "operators": operators,
        "categories": store.load_categories(),
        "counts": {
            "merged": len(operators),
            "base": len(store.load_base()),
            "general": len(general_names),
            "domain": len(domain_names),
            "task": len(task_names),
            "legacy_user": len(legacy_names),
        },
        "task_operator_names": task_names,
        "domain_operator_names": domain_names,
        "general_operator_names": general_names,
        "legacy_user_operator_names": legacy_names,
        "paths": {
            "base": "data/operator_registry.json",
            "general": "data/operator_registry_general.json",
            "domain": (str(store.domain_path.relative_to(request.app.state.config.root)) if store.domain_path else None),
            "user": store.user_path_relative,
            "categories": "data/operator_categories.json",
        },
    }


@router.get("/raw")
def operators_raw(
    request: Request,
    pipeline_id: str | None = Query(default=None, description="Optional pipeline id for isolated user registry"),
) -> dict[str, Any]:
    """Debug / tools: separate base, user, and merged dicts."""
    store = _store(request, pipeline_id=pipeline_id)
    return {
        "base": store.load_base(),
        "general": store.load_general(),
        "domain": store.load_domain() if pipeline_id else {},
        "task": store.load_task() if pipeline_id else {},
        "legacy_user": store.load_legacy_user() if not pipeline_id else {},
        "merged": store.merged_raw(),
    }
