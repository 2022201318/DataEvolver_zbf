"""LLM 算子：逐条调用 `core.llm_client`（JSON mode），适合训练数据改写/生成/抽取。"""

from __future__ import annotations

import json
from typing import Any, Callable

from core.llm_client import LLMClientError, chat_completion, parse_message_content_json

from subsystems.pipeline_runtime.execution.handlers_deterministic import _params


def _emit_usage(ctx: dict[str, Any], usage: dict[str, Any]) -> None:
    fn = ctx.get("on_usage")
    if not callable(fn):
        return
    op = str(ctx.get("usage_operation") or "pipeline_run.llm")
    cfg = ctx.get("llm_config") or {}
    kw: dict[str, Any] = {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "model": str(cfg.get("model")),
        "operation": op,
    }
    for k in ("duration_ms", "request_id", "api_host"):
        if usage.get(k) is not None:
            kw[k] = usage[k]
    try:
        fn(**kw)
    except TypeError:
        fn(
            input_tokens=kw["input_tokens"],
            output_tokens=kw["output_tokens"],
            model=kw["model"],
        )


def _call_llm(ctx: dict[str, Any], system: str, user_obj: dict[str, Any]) -> dict[str, Any]:
    cfg = ctx["llm_config"]
    resp = chat_completion(
        base_url=str(cfg["base_url"]),
        api_key=str(cfg["api_key"]),
        model=str(cfg["model"]),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_obj, ensure_ascii=False)},
        ],
        temperature=float(cfg.get("temperature", 0.2)),
        max_tokens=min(8192, int(cfg.get("max_tokens", 4096))),
        timeout_sec=float(cfg.get("timeout", 180)),
        json_mode=True,
    )
    parsed, usage = parse_message_content_json(resp)
    _emit_usage(ctx, usage)
    return parsed


def _cap_records(records: list[dict[str, Any]], ctx: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lim = ctx.get("llm_max_records_per_step")
    if lim is None:
        return records, []
    n = int(lim)
    if n <= 0 or len(records) <= n:
        return records, []
    return records[:n], records[n:]


def op_llm_rewrite_field(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    field = str(p.get("field_name") or "")
    spec = str(p.get("rewrite_spec") or "Improve clarity and completeness while preserving meaning.")
    if not field:
        return records
    head, tail = _cap_records(records, ctx)
    sys = (
        "You rewrite one field of a training-data record. Output JSON only: "
        '{"text": "<rewritten string>"}. Preserve factual content unless spec asks otherwise.'
    )
    out: list[dict[str, Any]] = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        try:
            raw = c.get(field, "")
            parsed = _call_llm(
                ctx,
                sys,
                {"field": field, "instruction": spec, "original": raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)},
            )
            txt = parsed.get("text")
            if isinstance(txt, str):
                c[field] = txt
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            ctx.setdefault("execution_warnings", []).append(f"llm_rewrite_field failed on one row; kept original ({field})")
        out.append(c)
    return out + tail


def op_llm_generate_field(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    target = str(p.get("target_field") or "")
    spec = str(p.get("generation_spec") or "Generate appropriate content.")
    ctx_fields = p.get("prompt_context_fields") or []
    if isinstance(ctx_fields, str):
        ctx_fields = [ctx_fields]
    if not target:
        return records
    head, tail = _cap_records(records, ctx)
    sys = (
        "You fill one target field for a training-data record from given context fields. "
        'Output JSON only: {"value": <string or structured value as JSON-compatible>}.'
    )
    out = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        subset = {k: r.get(k) for k in ctx_fields if isinstance(k, str)}
        try:
            parsed = _call_llm(ctx, sys, {"context": subset, "target_field": target, "instruction": spec})
            val = parsed.get("value")
            if val is not None:
                c[target] = val
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            ctx.setdefault("execution_warnings", []).append("llm_generate_field failed on one row; skipped value")
        out.append(c)
    return out + tail


def op_llm_expand_content(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    field = str(p.get("field_name") or "")
    spec = str(p.get("expansion_spec") or "Expand with useful detail.")
    if not field:
        return records
    head, tail = _cap_records(records, ctx)
    sys = 'Output JSON only: {"text": "<expanded string>"}.'
    out = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        try:
            raw = c.get(field, "")
            parsed = _call_llm(
                ctx,
                sys,
                {"task": "expand", "field": field, "instruction": spec, "original": str(raw)[:120_000]},
            )
            t = parsed.get("text")
            if isinstance(t, str):
                c[field] = t
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            ctx.setdefault("execution_warnings", []).append("llm_expand_content failed on one row")
        out.append(c)
    return out + tail


def op_llm_extract_structure(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    sf = str(p.get("source_field") or "")
    spec = str(p.get("extraction_spec") or "Extract structured key-value pairs from the text.")
    if not sf:
        return records
    head, tail = _cap_records(records, ctx)
    sys = (
        "Extract structured fields from one text field. Output JSON only: "
        '{"fields": {<key>: <value>, ...}}. Use flat string values when possible.'
    )
    out = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        try:
            text = r.get(sf, "")
            parsed = _call_llm(ctx, sys, {"instruction": spec, "text": str(text)[:120_000]})
            fields = parsed.get("fields")
            if isinstance(fields, dict):
                for k, v in fields.items():
                    if isinstance(k, str) and k not in c:
                        c[k] = v
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            ctx.setdefault("execution_warnings", []).append("llm_extract_structure failed on one row")
        out.append(c)
    return out + tail


def op_llm_score_quality(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    field = str(p.get("field_name") or "")
    rubric = str(p.get("rubric") or "Score 1-5 on usefulness for supervised fine-tuning.")
    if not field:
        return records
    head, tail = _cap_records(records, ctx)
    sys = 'Output JSON only: {"score": <number>, "note": "<short string>"}.'
    out = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        try:
            parsed = _call_llm(
                ctx,
                sys,
                {"field": field, "rubric": rubric, "content": str(r.get(field, ""))[:80_000]},
            )
            c["_llm_scores"] = {"field": field, "score": parsed.get("score"), "note": parsed.get("note")}
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            c["_llm_scores"] = {"field": field, "error": True}
        out.append(c)
    return out + tail


def op_llm_check_consistency(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    group = p.get("field_group") or []
    if isinstance(group, str):
        group = [group]
    cons = str(p.get("constraints") or "Check internal consistency across fields.")
    head, tail = _cap_records(records, ctx)
    sys = 'Output JSON only: {"ok": <bool>, "issues": [<string>, ...]}.'
    out = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        try:
            payload = {k: r.get(k) for k in group if isinstance(k, str)}
            parsed = _call_llm(ctx, sys, {"fields": payload, "constraints": cons})
            c["_consistency_report"] = {"ok": parsed.get("ok"), "issues": parsed.get("issues")}
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            c["_consistency_report"] = {"ok": None, "error": True}
        out.append(c)
    return out + tail


def op_llm_verify_reasoning(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    spec = str(p.get("reasoning_spec") or "Verify reasoning quality.")
    head, tail = _cap_records(records, ctx)
    sys = 'Output JSON only: {"ok": <bool>, "report": "<short>"}.'
    out = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        try:
            parsed = _call_llm(ctx, sys, {"spec": spec, "record": {k: v for k, v in list(r.items())[:24]}})
            c["_reasoning_report"] = parsed
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            c["_reasoning_report"] = {"error": True}
        out.append(c)
    return out + tail


def op_llm_verify_answer_grounding(
    records: list[dict[str, Any]], step: dict[str, Any], ctx: dict[str, Any]
) -> list[dict[str, Any]]:
    p = _params(step)
    spec = str(p.get("grounding_spec") or "Check if answer is grounded in context.")
    head, tail = _cap_records(records, ctx)
    sys = 'Output JSON only: {"grounded": <bool>, "note": "<short>"}.'
    out = []
    for r in head:
        if not isinstance(r, dict):
            continue
        c = dict(r)
        try:
            parsed = _call_llm(ctx, sys, {"spec": spec, "record": {k: v for k, v in list(r.items())[:24]}})
            c["_grounding_report"] = parsed
        except (LLMClientError, TypeError, KeyError, json.JSONDecodeError):
            c["_grounding_report"] = {"error": True}
        out.append(c)
    return out + tail


LLM_REGISTRY: dict[str, Callable[..., Any]] = {
    "llm_rewrite_field": op_llm_rewrite_field,
    "llm_generate_field": op_llm_generate_field,
    "llm_expand_content": op_llm_expand_content,
    "llm_extract_structure": op_llm_extract_structure,
    "llm_score_quality": op_llm_score_quality,
    "llm_check_consistency": op_llm_check_consistency,
    "llm_verify_reasoning": op_llm_verify_reasoning,
    "llm_verify_answer_grounding": op_llm_verify_answer_grounding,
}

LLM_OPERATOR_NAMES = frozenset(LLM_REGISTRY.keys())
