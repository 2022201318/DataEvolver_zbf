"""
Operator memory hierarchy (persistent capability memory):

- `data/operator_registry.json` — predefined general operators (stable base).
- `data/operator_registry_general.json` — promoted general memory operators.
- `data/operator_registry_domain/<domain>.json` — domain-level memory operators.
- `data/operator_registry_user/<pipeline_id>.json` — task-specific evolved operators.
- `data/operator_registry_user.json` — legacy global user registry (backward compatibility).

Category metadata: `data/operator_categories.json` (labels + `card_variant` for UI).

Merge precedence for a pipeline:
base -> general memory -> domain memory -> task memory.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_domain_key(value: str | None) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    key = re.sub(r"[^a-z0-9_-]+", "_", raw).strip("_")
    return key or None


def _read_manifest_latest_domain(project_root: Path, pipeline_id: str | None) -> str | None:
    pid = (pipeline_id or "").strip()
    if not pid:
        return None
    manifest = project_root / "data" / "manifest.jsonl"
    if not manifest.is_file():
        return None
    domain: str | None = None
    try:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if str(rec.get("pipeline_id") or "").strip() != pid:
                continue
            d = (
                str(rec.get("domain") or "").strip()
                or str(rec.get("task_type") or "").strip()
                or str(rec.get("language") or "").strip()
            )
            domain = d or domain
    except OSError:
        return None
    return _normalize_domain_key(domain)


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

    def __init__(
        self,
        project_root: Path,
        pipeline_id: str | None = None,
        domain_key: str | None = None,
    ) -> None:
        self._root = project_root
        self._pipeline_id = (pipeline_id or "").strip() or None
        self._domain_key = _normalize_domain_key(domain_key)
        if self._domain_key is None:
            self._domain_key = _read_manifest_latest_domain(project_root, self._pipeline_id)
        self._base_path = project_root / "data" / "operator_registry.json"
        self._general_path = project_root / "data" / "operator_registry_general.json"
        self._domain_dir = project_root / "data" / "operator_registry_domain"
        if self._pipeline_id is not None:
            self._task_path = (
                project_root / "data" / "operator_registry_user" / f"{self._pipeline_id}.json"
            )
        else:
            self._task_path = project_root / "data" / "operator_registry_user.json"
        self._legacy_user_path = project_root / "data" / "operator_registry_user.json"
        self._categories_path = project_root / "data" / "operator_categories.json"
        self._memory_dir = project_root / "data" / "operator_memory"
        self._memory_stats_path = self._memory_dir / "memory_stats.json"
        self._memory_events_path = self._memory_dir / "memory_events.jsonl"

    @property
    def base_path(self) -> Path:
        return self._base_path

    @property
    def user_path(self) -> Path:
        return self._task_path

    @property
    def user_path_relative(self) -> str:
        return str(self._task_path.relative_to(self._root))

    @property
    def domain_key(self) -> str | None:
        return self._domain_key

    @property
    def domain_path(self) -> Path | None:
        if self._domain_key is None:
            return None
        return self._domain_dir / f"{self._domain_key}.json"

    @property
    def categories_path(self) -> Path:
        return self._categories_path

    def load_base(self) -> dict[str, Any]:
        return _read_json_object(self._base_path)

    def load_general(self) -> dict[str, Any]:
        return _read_json_object(self._general_path)

    def load_domain(self) -> dict[str, Any]:
        p = self.domain_path
        if p is None:
            return {}
        return _read_json_object(p)

    def load_task(self) -> dict[str, Any]:
        return _read_json_object(self._task_path)

    def load_legacy_user(self) -> dict[str, Any]:
        return _read_json_object(self._legacy_user_path)

    def load_user(self) -> dict[str, Any]:
        # backward-compatible alias
        if self._pipeline_id is not None:
            return self.load_task()
        return self.load_legacy_user()

    def load_categories(self) -> dict[str, Any]:
        return _read_json_object(self._categories_path)

    def merged_raw(self) -> dict[str, Any]:
        """
        Merged operator_name -> spec.
        For pipeline-aware mode: base -> general -> domain -> task.
        For legacy/global mode: base -> general -> legacy_user.
        """
        merged = dict(self.load_base())
        merged.update(self.load_general())
        if self._pipeline_id is not None:
            merged.update(self.load_domain())
            merged.update(self.load_task())
        else:
            merged.update(self.load_legacy_user())
        return merged

    def to_api_operator_list(self) -> list[dict[str, Any]]:
        """
        List for UI: one entry per operator with category metadata for card styling.

        UI 算子池只展示 base + general (+ domain/task when pipeline_id set)。
        不再混入 legacy 全局 `operator_registry_user.json`，避免启动前后数量跳变及跨任务污染。
        """
        base = self.load_base()
        general = self.load_general()
        domain = self.load_domain() if self._pipeline_id is not None else {}
        task = self.load_task() if self._pipeline_id is not None else {}
        merged = dict(base)
        merged.update(general)
        merged.update(domain)
        merged.update(task)
        categories = self.load_categories()
        out: list[dict[str, Any]] = []
        for name in sorted(merged.keys()):
            spec = merged[name]
            if not isinstance(spec, dict):
                continue
            if name in task:
                src = "task"
            elif name in domain:
                src = "domain"
            elif name in general:
                src = "general"
            else:
                src = "base"
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

    def save_task_registry(self, entries: dict[str, Any]) -> None:
        """Replace entire task registry file."""
        self._task_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._task_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    def save_domain_registry(self, entries: dict[str, Any]) -> None:
        p = self.domain_path
        if p is None:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    def save_general_registry(self, entries: dict[str, Any]) -> None:
        self._general_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._general_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    def save_user_registry(self, entries: dict[str, Any]) -> None:
        """Backward-compatible alias (task registry in pipeline-aware mode)."""
        self.save_task_registry(entries)

    def upsert_user_operators(self, new_ops: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible alias for task-level upsert."""
        user = self.load_task() if self._pipeline_id is not None else self.load_user()
        for k, v in new_ops.items():
            if isinstance(v, dict):
                user[k] = v
        if self._pipeline_id is not None:
            self.save_task_registry(user)
        else:
            self.save_user_registry(user)
        return user

    def _read_memory_stats(self) -> dict[str, Any]:
        return _read_json_object(self._memory_stats_path)

    def _write_memory_stats(self, stats: dict[str, Any]) -> None:
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        with open(self._memory_stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    def _append_memory_event(self, line: dict[str, Any]) -> None:
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        with open(self._memory_events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def assimilate_evolved_operators(
        self,
        new_ops: dict[str, Any],
        *,
        pipeline_id: str,
        assessment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        将新算子写入 task memory，并按 evidence 尝试晋升到 domain/general。
        晋升规则（可配置化前的默认策略）：
        - task -> domain: 同域命中 >= 3 次，或同域来自 >= 2 个 pipeline
        - domain -> general: 覆盖 >= 2 个 domain 且总命中 >= 4
        """
        if not new_ops:
            return {
                "task_added": [],
                "promoted_to_domain": [],
                "promoted_to_general": [],
                "domain_key": self._domain_key,
                "paths": {
                    "task": self.user_path_relative,
                    "domain": str(self.domain_path.relative_to(self._root)) if self.domain_path else None,
                    "general": str(self._general_path.relative_to(self._root)),
                },
            }

        task = self.load_task() if self._pipeline_id is not None else self.load_user()
        for k, v in new_ops.items():
            if isinstance(v, dict):
                task[k] = v
        if self._pipeline_id is not None:
            self.save_task_registry(task)
        else:
            self.save_user_registry(task)

        stats = self._read_memory_stats()
        domain = self._domain_key
        promoted_domain: list[str] = []
        promoted_general: list[str] = []
        domain_pool = self.load_domain() if domain else {}
        general_pool = self.load_general()
        rec_fixes = list((assessment or {}).get("recommended_fixes") or [])
        importance_delta = max(1, min(3, len(rec_fixes)))
        for name, spec in new_ops.items():
            if not isinstance(spec, dict):
                continue
            rec = stats.get(name)
            if not isinstance(rec, dict):
                rec = {
                    "total_hits": 0,
                    "pipelines": [],
                    "domains": {},
                    "importance_sum": 0,
                    "promoted_to_domain": [],
                    "promoted_to_general": False,
                }
            rec["total_hits"] = int(rec.get("total_hits") or 0) + 1
            pls = set(str(x) for x in (rec.get("pipelines") or []) if x)
            pls.add(pipeline_id)
            rec["pipelines"] = sorted(pls)
            dom_map = rec.get("domains") if isinstance(rec.get("domains"), dict) else {}
            if domain:
                drec = dom_map.get(domain) if isinstance(dom_map.get(domain), dict) else {"hits": 0, "pipelines": []}
                drec["hits"] = int(drec.get("hits") or 0) + 1
                dpls = set(str(x) for x in (drec.get("pipelines") or []) if x)
                dpls.add(pipeline_id)
                drec["pipelines"] = sorted(dpls)
                dom_map[domain] = drec
            rec["domains"] = dom_map
            rec["importance_sum"] = int(rec.get("importance_sum") or 0) + importance_delta
            rec["last_seen_at"] = _iso()
            rec["last_seen_pipeline"] = pipeline_id
            stats[name] = rec

            if domain:
                drec = dom_map.get(domain) if isinstance(dom_map.get(domain), dict) else {"hits": 0, "pipelines": []}
                same_domain_hits = int(drec.get("hits") or 0)
                same_domain_pipelines = len(set(str(x) for x in (drec.get("pipelines") or []) if x))
                already_promoted_domains = set(str(x) for x in (rec.get("promoted_to_domain") or []) if x)
                if (
                    domain not in already_promoted_domains
                    and (same_domain_hits >= 3 or same_domain_pipelines >= 2)
                ):
                    domain_pool[name] = spec
                    promoted_domain.append(name)
                    already_promoted_domains.add(domain)
                    rec["promoted_to_domain"] = sorted(already_promoted_domains)
                    stats[name] = rec

            distinct_domains = [k for k, v in dom_map.items() if isinstance(v, dict) and int(v.get("hits") or 0) > 0]
            if (not bool(rec.get("promoted_to_general"))) and len(distinct_domains) >= 2 and int(rec.get("total_hits") or 0) >= 4:
                general_pool[name] = spec
                promoted_general.append(name)
                rec["promoted_to_general"] = True
                stats[name] = rec

        if promoted_domain and domain:
            self.save_domain_registry(domain_pool)
        if promoted_general:
            self.save_general_registry(general_pool)
        self._write_memory_stats(stats)
        self._append_memory_event(
            {
                "kind": "operator_memory_assimilation",
                "at": _iso(),
                "pipeline_id": pipeline_id,
                "domain_key": domain,
                "task_added": sorted([k for k in new_ops.keys() if isinstance(new_ops.get(k), dict)]),
                "promoted_to_domain": sorted(promoted_domain),
                "promoted_to_general": sorted(promoted_general),
                "task_registry_path": self.user_path_relative,
                "domain_registry_path": str(self.domain_path.relative_to(self._root)) if self.domain_path else None,
                "general_registry_path": str(self._general_path.relative_to(self._root)),
            }
        )
        return {
            "task_added": sorted([k for k in new_ops.keys() if isinstance(new_ops.get(k), dict)]),
            "promoted_to_domain": sorted(promoted_domain),
            "promoted_to_general": sorted(promoted_general),
            "domain_key": domain,
            "paths": {
                "task": self.user_path_relative,
                "domain": str(self.domain_path.relative_to(self._root)) if self.domain_path else None,
                "general": str(self._general_path.relative_to(self._root)),
            },
        }
