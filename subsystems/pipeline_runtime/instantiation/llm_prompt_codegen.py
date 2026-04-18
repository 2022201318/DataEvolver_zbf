"""
为「需要调用 LLM」的内置算子生成 pipeline-specific 的 prompt / rubric / instruction 文本。

目标：
- 不把 LLM 算子的核心提示词写死在 handler 里（仅保留稳定的 JSON 输出约束）
- 实例化阶段根据 understanding + 编排 step + 注册表 spec 生成本 pipeline 的可执行提示词
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from core.llm_client import LLMClientError, chat_completion, parse_message_content_json

logger = logging.getLogger(__name__)


_SYSTEM = """You are a prompt engineer for a data preparation pipeline.
You will be given:
- structured_understanding_excerpt (what "good" looks like),
- an operator spec (what the operator is supposed to do),
- one orchestration step (operator + parameters).

Task:
Return ONLY one JSON object with:
- parameter_overrides: object (may be empty). Keys must be existing parameter keys of the step.
  For LLM-style operators, you should produce concise, high-quality natural-language instructions (strings),
  e.g. expansion_spec / rewrite_spec / generation_spec / extraction_spec / rubric / constraints.
- prompt_notes: array of short strings (optional), for debugging / UI.

Rules:
- Do NOT output markdown.
- Do NOT invent new parameter names.
- Keep instructions short but specific (usually 1-6 sentences).
- Use the SAME language as structured_understanding_excerpt when possible.
"""


def _emit_usage(
    on_usage: Callable[..., None] | None,
    usage: dict[str, Any],
    model: str,
    operation: str,
) -> None:
    if not callable(on_usage):
        return
    try:
        on_usage(
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=model,
            operation=operation,
            duration_ms=usage.get("duration_ms"),
        )
    except TypeError:
        on_usage(
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model=model,
        )


def generate_llm_parameter_overrides(
    *,
    pipeline_id: str,
    step: dict[str, Any],
    registry_spec: dict[str, Any] | None,
    understanding: dict[str, Any],
    llm_config: dict[str, Any],
    on_usage: Callable[..., None] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    返回 (overrides, notes)。失败时返回 ({}, [reason])。
    """
    api_key = str(llm_config.get("api_key") or "").strip()
    if not api_key:
        return {}, ["no_api_key"]

    u_excerpt = {
        "basic_information": understanding.get("basic_information"),
        "schema_analysis": understanding.get("schema_analysis"),
        "dataset_level_delta": understanding.get("dataset_level_delta"),
        "pilot_run_feedback": understanding.get("pilot_run_feedback"),
    }
    user_obj = {
        "pipeline_id": pipeline_id,
        "operator": step.get("operator"),
        "step_description": step.get("description"),
        "step_parameters": step.get("parameters") if isinstance(step.get("parameters"), dict) else {},
        "registry_operator_spec": registry_spec if isinstance(registry_spec, dict) else {},
        "structured_understanding_excerpt": u_excerpt,
    }
    prompt = json.dumps(user_obj, ensure_ascii=False, indent=2)
    if len(prompt) > 120_000:
        prompt = prompt[:119_000] + "\n...(truncated)\n"

    try:
        resp = chat_completion(
            base_url=str(llm_config["base_url"]),
            api_key=api_key,
            model=str(llm_config["model"]),
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=float(llm_config.get("temperature", 0.15)),
            max_tokens=min(4096, int(llm_config.get("max_tokens", 4096))),
            timeout_sec=max(120.0, float(llm_config.get("timeout", 300))),
            json_mode=True,
        )
        parsed, usage = parse_message_content_json(resp)
        _emit_usage(on_usage, usage, str(llm_config.get("model")), f"instantiation.llm_prompt.{step.get('operator','op')}")
        if not isinstance(parsed, dict):
            return {}, ["llm_invalid_response"]
        overrides = parsed.get("parameter_overrides")
        notes = parsed.get("prompt_notes")
        if not isinstance(overrides, dict):
            overrides = {}
        if not isinstance(notes, list):
            notes = []
        notes = [str(x) for x in notes if str(x).strip()][:12]
        # 只允许覆盖现有 key
        base_params = step.get("parameters") if isinstance(step.get("parameters"), dict) else {}
        safe: dict[str, Any] = {}
        for k, v in overrides.items():
            if k in base_params:
                safe[str(k)] = v
        return safe, notes
    except (LLMClientError, KeyError, TypeError, json.JSONDecodeError) as e:
        logger.warning("llm prompt codegen failed: %s", e)
        return {}, [f"llm_error:{type(e).__name__}"]

