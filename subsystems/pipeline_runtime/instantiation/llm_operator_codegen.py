# -*- coding: utf-8 -*-
"""
对「注册表内无内置 handler」的算子（如 evolved.*），用 LLM 生成 `run(records, context)` 模块。
风格对齐旧版 多模态数据准备 operator_generation，但契约固定为开源运行时（与 trial / subprocess 一致）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from core.llm_client import LLMClientError, chat_completion, parse_message_content_json

logger = logging.getLogger(__name__)

_CODEGEN_SYSTEM = """You are an expert Python engineer for the 多模态数据准备 open-source runtime.

Output **only** one JSON object: {"code": "<entire Python module as a single string>"}.

The module MUST:
1. Define run(records, context) returning list[dict] (and optional describe()).
2. Load step metadata with an absolute path — NEVER rely on process cwd:
   from pathlib import Path
   import json
   _meta_path = Path(__file__).resolve().parent / "step_meta.json"
   with open(_meta_path, encoding="utf-8") as _f:
       step_meta = json.load(_f)
   step = step_meta["orchestration_step"]
   Do NOT use open("step_meta.json") alone.
3. Use step["operator"], step["parameters"], step["description"], input_keys, output_keys.
4. For LLM calls: add `from core.llm_client import chat_completion, parse_message_content_json` then call chat_completion(...) with context["llm_config"] keys: base_url, api_key, model, temperature, max_tokens, timeout. Do NOT reference core.llm_client without importing.
5. Be defensive on errors per row; keep list[dict] JSON-serializable.
6. No subprocess/os.system; no extra network APIs.

The "code" string must be valid Python 3.10+ (escape newlines properly inside JSON)."""


def _truncate(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 20] + "\n... (truncated)"


def generate_llm_operator_module(
    *,
    root: Path,
    pipeline_id: str,
    step: dict[str, Any],
    registry_spec: dict[str, Any] | None,
    understanding: dict[str, Any],
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None = None,
) -> str | None:
    api_key = str(llm_config.get("api_key") or "").strip()
    if not api_key:
        return None

    u_excerpt = {
        "basic_information": understanding.get("basic_information"),
        "schema_analysis": understanding.get("schema_analysis"),
        "dataset_level_delta": understanding.get("dataset_level_delta"),
    }
    user_obj = {
        "pipeline_id": pipeline_id,
        "orchestration_step": step,
        "registry_operator_spec": registry_spec,
        "structured_understanding_excerpt": _truncate(json.dumps(u_excerpt, ensure_ascii=False), 14_000),
    }
    user_prompt = (
        "Generate the Python module.\n\n" + json.dumps(user_obj, ensure_ascii=False, indent=2)
    )

    try:
        resp = chat_completion(
            base_url=str(llm_config["base_url"]),
            api_key=api_key,
            model=str(llm_config["model"]),
            messages=[
                {"role": "system", "content": _CODEGEN_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(llm_config.get("temperature", 0.15)),
            max_tokens=min(12_288, int(llm_config.get("max_tokens", 8192))),
            timeout_sec=max(120.0, float(llm_config.get("timeout", 300))),
            json_mode=True,
        )
        parsed, usage = parse_message_content_json(resp)
        if on_usage:
            try:
                on_usage(
                    input_tokens=int(usage.get("input_tokens", 0)),
                    output_tokens=int(usage.get("output_tokens", 0)),
                    model=str(llm_config.get("model")),
                    operation=f"instantiation.llm_codegen.{step.get('operator', 'op')}",
                    duration_ms=usage.get("duration_ms"),
                )
            except TypeError:
                on_usage(
                    input_tokens=int(usage.get("input_tokens", 0)),
                    output_tokens=int(usage.get("output_tokens", 0)),
                    model=str(llm_config.get("model")),
                )
        raw_code = parsed.get("code")
        if not isinstance(raw_code, str) or len(raw_code.strip()) < 80:
            logger.warning("LLM codegen returned empty or short code for %s", step.get("operator"))
            return None
        code = raw_code.strip()
        if "def run(" not in code:
            logger.warning("LLM codegen missing run() for %s", step.get("operator"))
            return None
        return code
    except (LLMClientError, KeyError, TypeError, json.JSONDecodeError) as e:
        logger.warning("LLM operator codegen failed: %s", e)
        return None
