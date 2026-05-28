"""
Operator registry API (memory hierarchy):
- base: `data/operator_registry.json`
- general: `data/operator_registry_general.json`
- domain: `data/operator_registry_domain/<domain>.json`
- task: `data/operator_registry_user/<pipeline_id>.json`
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from subsystems.operator_management import OperatorRegistryStore
from subsystems.operator_management.manual_registry import (
    ManualOperatorError,
    add_manual_operators,
    build_operator_spec,
    remove_manual_operator,
)

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


class OperatorSpecBody(BaseModel):
    description: str = Field(..., min_length=1)
    input_keys: list[str] = Field(default_factory=lambda: ["records"])
    output_keys: list[str] = Field(default_factory=lambda: ["records"])
    requires_llm: bool = False
    category: str | None = None


class OperatorAddBody(BaseModel):
    pipeline_id: str = Field(..., min_length=1, max_length=128)
    name: str | None = Field(default=None, description="单算子名；与 operators 二选一")
    description: str | None = None
    input_keys: list[str] = Field(default_factory=lambda: ["records"])
    output_keys: list[str] = Field(default_factory=lambda: ["records"])
    requires_llm: bool = False
    category: str | None = None
    operators: dict[str, OperatorSpecBody] | None = Field(
        default=None,
        description="批量：算子名 -> 规格",
    )
    scope: str = Field(default="task", pattern="^(task|domain|general)$")
    overwrite: bool = False


class OperatorRemoveBody(BaseModel):
    pipeline_id: str
    name: str
    scope: str = Field(default="task", pattern="^(task|domain|general)$")


@router.post("/add")
def add_operator(request: Request, body: OperatorAddBody = Body(...)) -> dict[str, Any]:
    """手动添加算子（与 CLI `operators add` 一致）。"""
    root = request.app.state.config.root
    store = OperatorRegistryStore(root, pipeline_id=body.pipeline_id.strip())
    ops: dict[str, dict[str, Any]] = {}
    if body.operators:
        for k, v in body.operators.items():
            ops[k] = build_operator_spec(
                description=v.description,
                input_keys=v.input_keys,
                output_keys=v.output_keys,
                requires_llm=v.requires_llm,
                category=v.category,
                name=k,
            )
    elif body.name and body.description:
        ops[body.name] = build_operator_spec(
            description=body.description,
            input_keys=body.input_keys,
            output_keys=body.output_keys,
            requires_llm=body.requires_llm,
            category=body.category,
            name=body.name,
        )
    else:
        raise HTTPException(status_code=422, detail="请提供 operators 字典，或 name + description")
    try:
        return add_manual_operators(
            store,
            ops,
            pipeline_id=body.pipeline_id.strip(),
            scope=body.scope,  # type: ignore[arg-type]
            overwrite=body.overwrite,
        )
    except ManualOperatorError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/remove")
def remove_operator(request: Request, body: OperatorRemoveBody = Body(...)) -> dict[str, Any]:
    store = OperatorRegistryStore(root=request.app.state.config.root, pipeline_id=body.pipeline_id.strip())
    try:
        return remove_manual_operator(store, body.name, scope=body.scope)  # type: ignore[arg-type]
    except ManualOperatorError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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
