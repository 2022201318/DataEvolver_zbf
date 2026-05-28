"""
手动添加 / 删除算子（CLI、API 共用）。

默认写入 task memory（`operator_registry_user/<pipeline_id>.json`），
并通过 `assimilate_evolved_operators` 记录 memory 事件，支持后续 domain/general 晋升。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .registry_store import OperatorRegistryStore, _infer_category_id

OperatorScope = Literal["task", "domain", "general"]

OPERATOR_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,119}$")

VALID_CATEGORIES = frozenset({"io", "structure", "control", "semantic", "quality", "bridge"})


class ManualOperatorError(ValueError):
    """用户可读的算子注册错误。"""


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_operator_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        raise ManualOperatorError("算子名称不能为空")
    if not OPERATOR_NAME_RE.match(raw):
        raise ManualOperatorError(
            "算子名称无效：须以字母开头，仅允许字母、数字、下划线、点、连字符，长度 1–120"
        )
    return raw


def _parse_keys(value: str | list[str] | None, *, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
    else:
        out = [p.strip() for p in str(value).split(",") if p.strip()]
    if not out:
        raise ManualOperatorError(f"{field} 至少需要一个键名")
    return out


def build_operator_spec(
    *,
    description: str,
    input_keys: str | list[str] | None = None,
    output_keys: str | list[str] | None = None,
    requires_llm: bool = False,
    category: str | None = None,
    name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    desc = (description or "").strip()
    if not desc:
        raise ManualOperatorError("description 不能为空")
    in_keys = _parse_keys(input_keys if input_keys is not None else ["records"], field="input_keys")
    out_keys = _parse_keys(output_keys if output_keys is not None else ["records"], field="output_keys")
    cid = (category or "").strip() or (_infer_category_id(name) if name else "bridge")
    if cid not in VALID_CATEGORIES:
        raise ManualOperatorError(
            f"category 无效：{cid!r}；可选 {', '.join(sorted(VALID_CATEGORIES))}"
        )
    spec: dict[str, Any] = {
        "description": desc,
        "input_keys": in_keys,
        "output_keys": out_keys,
        "requires_llm": bool(requires_llm),
        "category": cid,
        "source": "manual",
        "added_at": _iso(),
    }
    if extra:
        for k, v in extra.items():
            if k not in spec:
                spec[k] = v
    return spec


def parse_operator_payload(data: Any) -> dict[str, dict[str, Any]]:
    """
    支持：
    - `{"op_name": {spec...}}`
    - `{"name": "op_name", "description": ...}`
    - 单算子 spec 且外层带 name 字段
    """
    if not isinstance(data, dict):
        raise ManualOperatorError("JSON 根类型须为 object")
    if "name" in data and isinstance(data.get("name"), str):
        name = normalize_operator_name(str(data["name"]))
        spec = build_operator_spec(
            description=str(data.get("description") or ""),
            input_keys=data.get("input_keys"),  # type: ignore[arg-type]
            output_keys=data.get("output_keys"),  # type: ignore[arg-type]
            requires_llm=bool(data.get("requires_llm", False)),
            category=str(data.get("category") or "") or None,
            name=name,
            extra={k: v for k, v in data.items() if k not in {"name", "description", "input_keys", "output_keys", "requires_llm", "category"}},
        )
        return {name: spec}
    out: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        name = normalize_operator_name(str(k))
        out[name] = build_operator_spec(
            description=str(v.get("description") or ""),
            input_keys=v.get("input_keys"),  # type: ignore[arg-type]
            output_keys=v.get("output_keys"),  # type: ignore[arg-type]
            requires_llm=bool(v.get("requires_llm", False)),
            category=str(v.get("category") or "") or None,
            name=name,
            extra={kk: vv for kk, vv in v.items() if kk not in {"description", "input_keys", "output_keys", "requires_llm", "category"}},
        )
    if not out:
        raise ManualOperatorError("未解析到任何算子定义")
    return out


def load_operators_from_file(path: Path) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ManualOperatorError(f"无法读取文件: {path}") from e
    except json.JSONDecodeError as e:
        raise ManualOperatorError(f"JSON 解析失败: {e}") from e
    return parse_operator_payload(raw)


def add_manual_operators(
    store: OperatorRegistryStore,
    operators: dict[str, dict[str, Any]],
    *,
    pipeline_id: str,
    scope: OperatorScope = "task",
    overwrite: bool = False,
    record_assimilation: bool = True,
) -> dict[str, Any]:
    if not pipeline_id.strip():
        raise ManualOperatorError("pipeline_id 不能为空")
    if scope == "task" and store._pipeline_id is None:
        raise ManualOperatorError("task 作用域需要有效的 pipeline_id")

    base = store.load_base()
    normalized = {normalize_operator_name(k): v for k, v in operators.items()}
    to_write: dict[str, dict[str, Any]] = {}
    added: list[str] = []
    skipped: list[dict[str, str]] = []

    for name, spec in normalized.items():
        if name in base:
            skipped.append({"name": name, "reason": "不能与内置 base 算子同名"})
            continue
        if scope == "task":
            if name in store.load_task() and not overwrite:
                skipped.append({"name": name, "reason": "task 中已存在；使用 --overwrite 覆盖"})
                continue
        elif scope == "domain":
            if store.domain_path is None:
                skipped.append({"name": name, "reason": "无法推断 domain；请在 manifest 中设置 domain/task_type"})
                continue
            if name in store.load_domain() and not overwrite:
                skipped.append({"name": name, "reason": "domain 中已存在；使用 --overwrite 覆盖"})
                continue
        elif scope == "general":
            if name in store.load_general() and not overwrite:
                skipped.append({"name": name, "reason": "general 中已存在；使用 --overwrite 覆盖"})
                continue
        to_write[name] = spec

    memory_update: dict[str, Any] | None = None
    if scope == "task" and to_write:
        if record_assimilation:
            memory_update = store.assimilate_evolved_operators(
                to_write,
                pipeline_id=pipeline_id,
                assessment={"recommended_fixes": ["manual_add"], "recommend_new_operators": True},
            )
            added = [str(x) for x in (memory_update.get("task_added") or [])]
        else:
            store.upsert_user_operators(to_write)
            added = sorted(to_write.keys())
    elif scope == "domain" and to_write:
        pool = store.load_domain()
        pool.update(to_write)
        store.save_domain_registry(pool)
        added = sorted(to_write.keys())
    elif scope == "general" and to_write:
        pool = store.load_general()
        pool.update(to_write)
        store.save_general_registry(pool)
        added = sorted(to_write.keys())

    store._append_memory_event(
        {
            "kind": "manual_operator_add",
            "at": _iso(),
            "pipeline_id": pipeline_id,
            "scope": scope,
            "added": sorted(added),
            "skipped": skipped,
            "paths": {
                "task": store.user_path_relative,
                "domain": str(store.domain_path.relative_to(store._root)) if store.domain_path else None,
                "general": str(store._general_path.relative_to(store._root)),
            },
        }
    )

    counts = store.to_api_operator_list()
    return {
        "ok": True,
        "pipeline_id": pipeline_id,
        "scope": scope,
        "added": sorted(added),
        "skipped": skipped,
        "memory_update": memory_update,
        "registry_path": store.user_path_relative,
        "domain_key": store.domain_key,
        "pool_size": len(counts),
        "paths": {
            "task": store.user_path_relative,
            "domain": str(store.domain_path.relative_to(store._root)) if store.domain_path else None,
            "general": str(store._general_path.relative_to(store._root)),
        },
    }


def remove_manual_operator(
    store: OperatorRegistryStore,
    name: str,
    *,
    scope: OperatorScope = "task",
) -> dict[str, Any]:
    name = normalize_operator_name(name)
    if name in store.load_base():
        raise ManualOperatorError(f"不能删除内置算子 {name!r}")

    removed = False
    path: str | None = None
    if scope == "task":
        pool = store.load_task()
        if name in pool:
            del pool[name]
            store.save_task_registry(pool)
            removed = True
        path = store.user_path_relative
    elif scope == "domain":
        pool = store.load_domain()
        if name in pool:
            del pool[name]
            store.save_domain_registry(pool)
            removed = True
        path = str(store.domain_path.relative_to(store._root)) if store.domain_path else None
    elif scope == "general":
        pool = store.load_general()
        if name in pool:
            del pool[name]
            store.save_general_registry(pool)
            removed = True
        path = str(store._general_path.relative_to(store._root))

    if removed:
        store._append_memory_event(
            {
                "kind": "manual_operator_remove",
                "at": _iso(),
                "pipeline_id": store._pipeline_id or "",
                "scope": scope,
                "name": name,
                "path": path,
            }
        )

    return {
        "ok": removed,
        "name": name,
        "scope": scope,
        "removed": removed,
        "path": path,
        "detail": "已删除" if removed else "未在该作用域找到该算子",
    }


def list_operators_summary(store: OperatorRegistryStore) -> dict[str, Any]:
    ops = store.to_api_operator_list()
    by_source: dict[str, list[str]] = {}
    for o in ops:
        src = str(o.get("source") or "base")
        by_source.setdefault(src, []).append(str(o.get("name")))
    return {
        "counts": {k: len(v) for k, v in by_source.items()},
        "total": len(ops),
        "operators": ops,
        "paths": {
            "task": store.user_path_relative,
            "domain": str(store.domain_path.relative_to(store._root)) if store.domain_path else None,
            "general": str(store._general_path.relative_to(store._root)),
        },
        "domain_key": store.domain_key,
    }
