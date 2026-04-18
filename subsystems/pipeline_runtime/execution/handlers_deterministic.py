"""确定性算子：结构 / 控制 / 轻量质检（无 LLM）。"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from subsystems.pipeline_runtime.execution.records_io import load_records_from_rel_path, write_records_jsonl

OpFn = Callable[[list[dict[str, Any]], dict[str, Any], dict[str, Any]], list[dict[str, Any]]]


def _params(step: dict[str, Any]) -> dict[str, Any]:
    p = step.get("parameters")
    return p if isinstance(p, dict) else {}


def op_read_data(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(ctx["root"])
    rel = _params(step).get("file_path")
    if rel is None or (isinstance(rel, str) and not str(rel).strip()):
        raise ValueError(
            "read_data 缺少有效的 parameters.file_path；请重新执行 instantiate（将从 manifest 自动补全路径）"
            "或在编排中为 read_data 填写 file_path。"
        )
    max_r = ctx.get("max_input_records")
    return load_records_from_rel_path(root, str(rel).strip(), max_rows=max_r)


def op_write_data(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(ctx["root"])
    rel = _params(step).get("file_path")
    if rel is None or (isinstance(rel, str) and not str(rel).strip()):
        raise ValueError(
            "write_data 缺少有效的 parameters.file_path；请重新执行 instantiate（将从 manifest 约定路径补全）"
            "或在编排中为 write_data 填写 file_path。"
        )
    write_records_jsonl(root, str(rel).strip(), records)
    return records


def op_map_fields(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    fm = _params(step).get("field_mapping")
    if not isinstance(fm, dict) or not fm:
        return records
    out: list[dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        nr: dict[str, Any] = {}
        for k, v in r.items():
            nk = fm.get(k, k)
            if not isinstance(nk, str):
                nk = k
            nr[nk] = v
        out.append(nr)
    return out


def op_add_field(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    name = p.get("field_name")
    val = p.get("field_value")
    if not name:
        return records
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        c[str(name)] = deepcopy(val)
        out.append(c)
    return out


def op_remove_field(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    names = p.get("field_names") or p.get("field_name")
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, list) or not names:
        return records
    ns = {str(x) for x in names}
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        c = {k: v for k, v in r.items() if k not in ns}
        out.append(c)
    return out


def op_merge_fields(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    sources = p.get("source_fields")
    target = p.get("target_field")
    sep = str(p.get("separator", " "))
    if not isinstance(sources, list) or not target:
        return records
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        parts = [str(r.get(s, "")) for s in sources if s in r]
        c[str(target)] = sep.join(parts)
        out.append(c)
    return out


def op_split_field(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    src = p.get("source_field")
    targets = p.get("target_fields")
    delim = str(p.get("delimiter", "|"))
    if not src or not isinstance(targets, list) or not targets:
        return records
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        raw = str(r.get(src, ""))
        parts = raw.split(delim) if delim else [raw]
        for i, t in enumerate(targets):
            if isinstance(t, str):
                c[t] = parts[i].strip() if i < len(parts) else ""
        out.append(c)
    return out


def op_transform_field(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    fn = p.get("field_name")
    rules = p.get("transform_rules")
    if not fn or not isinstance(rules, dict):
        return records
    op = str(rules.get("op", "strip"))
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        v = c.get(fn)
        if isinstance(v, str):
            if op == "strip":
                c[fn] = v.strip()
            elif op == "lower":
                c[fn] = v.lower()
            elif op == "upper":
                c[fn] = v.upper()
            elif op == "regex_replace":
                pat = str(rules.get("pattern", ""))
                rep = str(rules.get("replacement", ""))
                if pat:
                    c[fn] = re.sub(pat, rep, v)
        out.append(c)
    return out


def op_normalize_schema(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    ts = p.get("target_schema")
    if not isinstance(ts, dict):
        return records
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        for k, default in ts.items():
            if k not in c:
                c[k] = deepcopy(default)
        out.append(c)
    return out


def op_filter_rows(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    pred = p.get("predicate")
    if not isinstance(pred, dict):
        return records
    mode = str(pred.get("mode", "all"))
    field = pred.get("field")
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        if mode == "all":
            out.append(r)
        elif mode == "field_exists" and field:
            if field in r and r[field] is not None and r[field] != "":
                out.append(r)
        elif mode == "field_missing" and field:
            if field not in r or r[field] is None or r[field] == "":
                out.append(r)
        elif mode == "min_length" and field:
            v = r.get(field, "")
            if isinstance(v, str) and len(v) >= int(pred.get("min", 0)):
                out.append(r)
        else:
            out.append(r)
    return out


def op_deduplicate(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    keys = p.get("key_fields")
    if isinstance(keys, str):
        keys = [keys]
    if not isinstance(keys, list):
        keys = []
    seen: set[Any] = set()
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        if keys:
            t = tuple(r.get(k) for k in keys)
        else:
            t = json.dumps(r, sort_keys=True, ensure_ascii=False)
        if t in seen:
            continue
        seen.add(t)
        out.append(r)
    return out


def op_sample_rows(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    cfg = p.get("sample_config")
    if not isinstance(cfg, dict):
        return records
    max_rows = cfg.get("max_rows")
    ratio = cfg.get("ratio")
    if isinstance(max_rows, int) and max_rows >= 0:
        return records[:max_rows]
    if isinstance(ratio, (int, float)) and 0 < ratio < 1:
        import random

        k = max(1, int(len(records) * ratio))
        return random.sample(records, min(k, len(records)))
    return records


def op_sort_rows(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    sk = p.get("sort_keys")
    if isinstance(sk, str):
        sk = [sk]
    if not isinstance(sk, list) or not sk:
        return records
    keys = [str(x) for x in sk]

    def keyfn(r: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(r.get(k) for k in keys)

    return sorted((r for r in records if isinstance(r, dict)), key=keyfn)


def op_validate_schema(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    rules = p.get("schema_rules")
    if not isinstance(rules, dict):
        return records
    required = rules.get("required")
    if isinstance(required, str):
        required = [required]
    req = [str(x) for x in required] if isinstance(required, list) else []
    reports: list[dict[str, Any]] = []
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        missing = [k for k in req if k not in r or r[k] is None or r[k] == ""]
        rep = {"ok": not missing, "missing_required": missing}
        reports.append(rep)
        c = dict(r)
        c["_validation_report"] = rep
        out.append(c)
    ctx["last_validation_reports"] = reports
    return out


def op_check_format(records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p = _params(step)
    rules = p.get("format_rules")
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        c["_format_report"] = {"checked": True, "rules": rules}
        out.append(c)
    return out


def op_combine_sources(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    """开源初版：仅从 context 取 secondary，与 primary records 按行 zip 合并字段。"""
    p = _params(step)
    secondary = ctx.get("records_secondary")
    if not isinstance(secondary, list) or not secondary:
        ctx.setdefault("execution_warnings", []).append(
            "combine_sources: 无 records_secondary，跳过合并"
        )
        return records
    out = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            continue
        c = dict(r)
        if i < len(secondary) and isinstance(secondary[i], dict):
            for k, v in secondary[i].items():
                if k not in c:
                    c[k] = v
        out.append(c)
    return out


def op_aggregate_group(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    ctx.setdefault("execution_warnings", []).append("aggregate_group: 运行时未实现，原样透传")
    return records


DETERMINISTIC_REGISTRY: dict[str, OpFn] = {
    "read_data": op_read_data,
    "write_data": op_write_data,
    "map_fields": op_map_fields,
    "add_field": op_add_field,
    "remove_field": op_remove_field,
    "merge_fields": op_merge_fields,
    "split_field": op_split_field,
    "transform_field": op_transform_field,
    "normalize_schema": op_normalize_schema,
    "filter_rows": op_filter_rows,
    "deduplicate": op_deduplicate,
    "sample_rows": op_sample_rows,
    "sort_rows": op_sort_rows,
    "validate_schema": op_validate_schema,
    "check_format": op_check_format,
    "combine_sources": op_combine_sources,
    "aggregate_group": op_aggregate_group,
}
