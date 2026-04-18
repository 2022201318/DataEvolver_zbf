"""
Operator registry API: system (`data/operator_registry.json`) + user
(`data/operator_registry_user.json`), merged for listing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from subsystems.operator_management import OperatorRegistryStore

router = APIRouter(prefix="/operators", tags=["operators"])


def _store(request: Request) -> OperatorRegistryStore:
    st = getattr(request.app.state, "operator_registry_store", None)
    if st is None:
        root = request.app.state.config.root
        st = OperatorRegistryStore(root)
        request.app.state.operator_registry_store = st
    return st


@router.get("/")
def list_operators(request: Request) -> dict[str, Any]:
    """
    Return merged operator list for UI (with `source`: base | user).

    Static files:
    - `data/operator_registry.json` — default pool
    - `data/operator_registry_user.json` — evolved / user-added
    """
    store = _store(request)
    operators = store.to_api_operator_list()
    user_names = sorted(store.load_user().keys())
    return {
        "operators": operators,
        "categories": store.load_categories(),
        "counts": {
            "merged": len(operators),
            "base": len(store.load_base()),
            "user": len(user_names),
        },
        "user_operator_names": user_names,
        "paths": {
            "base": "data/operator_registry.json",
            "user": "data/operator_registry_user.json",
            "categories": "data/operator_categories.json",
        },
    }


@router.get("/raw")
def operators_raw(request: Request) -> dict[str, Any]:
    """Debug / tools: separate base, user, and merged dicts."""
    store = _store(request)
    return {
        "base": store.load_base(),
        "user": store.load_user(),
        "merged": store.merged_raw(),
    }
