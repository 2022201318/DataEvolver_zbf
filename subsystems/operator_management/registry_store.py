"""
Two registry files:

- `data/operator_registry.json` — Layer 1 base operators (see docs/OPERATOR_REGISTRY_DESIGN.md).
- `data/operator_registry_user.json` — Layer 2 user / bridge operators from evolution.

Category metadata: `data/operator_categories.json` (labels + `card_variant` for UI).

Merge rule: start from base, then overlay user entries (same operator name: user wins).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _infer_category_id(name: str) -> str:
    """Fallback when an operator spec omits `category` (e.g. user-evolved bridge ops)."""
    if name in ("read_data", "write_data"):
        return "io"
    if name.startswith("llm_generate_") or name.startswith("llm_rewrite_"):
        return "semantic"
    if name.startswith("llm_extract") or name.startswith("llm_expand_"):
        return "semantic"
    if name.startswith("llm_score_") or name.startswith("llm_check_") or name.startswith("llm_verify_"):
        return "quality"
    if name in (
        "map_fields",
        "add_field",
        "remove_field",
        "merge_fields",
        "split_field",
        "transform_field",
        "normalize_schema",
        "combine_sources",
        "aggregate_group",
    ):
        return "structure"
    if name in ("filter_rows", "deduplicate", "sample_rows", "sort_rows"):
        return "control"
    if name in ("validate_schema", "check_format"):
        return "quality"
    # Evolved task-specific operators default to bridge
    return "bridge"


class OperatorRegistryStore:
    """Load / merge / persist operator definitions."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._base_path = project_root / "data" / "operator_registry.json"
        self._user_path = project_root / "data" / "operator_registry_user.json"
        self._categories_path = project_root / "data" / "operator_categories.json"

    @property
    def base_path(self) -> Path:
        return self._base_path

    @property
    def user_path(self) -> Path:
        return self._user_path

    @property
    def categories_path(self) -> Path:
        return self._categories_path

    def load_base(self) -> dict[str, Any]:
        return _read_json_object(self._base_path)

    def load_user(self) -> dict[str, Any]:
        return _read_json_object(self._user_path)

    def load_categories(self) -> dict[str, Any]:
        return _read_json_object(self._categories_path)

    def merged_raw(self) -> dict[str, Any]:
        """Merged operator_name -> spec (user overlays base)."""
        merged = dict(self.load_base())
        merged.update(self.load_user())
        return merged

    def to_api_operator_list(self) -> list[dict[str, Any]]:
        """List for UI: one entry per operator with category metadata for card styling."""
        user = self.load_user()
        merged = self.merged_raw()
        categories = self.load_categories()
        out: list[dict[str, Any]] = []
        for name in sorted(merged.keys()):
            spec = merged[name]
            if not isinstance(spec, dict):
                continue
            src = "user" if name in user else "base"
            req = bool(spec.get("requires_llm", False))
            cid = spec.get("category")
            if not isinstance(cid, str) or not cid.strip():
                cid = _infer_category_id(name)
            else:
                cid = cid.strip()
            raw_meta = categories.get(cid)
            meta = raw_meta if isinstance(raw_meta, dict) else {}
            label = meta.get("label", cid)
            out.append(
                {
                    "name": name,
                    "source": src,
                    "category_id": cid,
                    "category_label": label,
                    "category_label_zh": meta.get("label_zh"),
                    "card_variant": meta.get("card_variant", "slate"),
                    "category": label,
                    "description": spec.get("description", ""),
                    "input_keys": spec.get("input_keys", []),
                    "output_keys": spec.get("output_keys", []),
                    "requires_llm": req,
                }
            )
        return out

    def save_user_registry(self, entries: dict[str, Any]) -> None:
        """Replace entire user registry file (used by evolution after validation)."""
        self._user_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._user_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    def upsert_user_operators(self, new_ops: dict[str, Any]) -> dict[str, Any]:
        """Merge new_ops into existing user registry and persist."""
        user = self.load_user()
        for k, v in new_ops.items():
            if isinstance(v, dict):
                user[k] = v
        self.save_user_registry(user)
        return user
