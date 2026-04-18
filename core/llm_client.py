"""
轻量 OpenAI 兼容 Chat Completions 调用（标准库 urllib，无额外依赖）。
供理解阶段等子系统在配置好 `api_config` 后发起极简 LLM 请求。
"""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse


def extract_json_object(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    l, r = s.find("{"), s.rfind("}")
    if l != -1 and r != -1 and r > l:
        return s[l : r + 1]
    return s


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 512,
    timeout_sec: float = 120.0,
    json_mode: bool = True,
) -> dict[str, Any]:
    """
    POST `{base_url}/chat/completions`（base_url 应已含 `/v1`）。
    返回 OpenAPI 解析后的 dict；失败抛出 LLMClientError。
    """
    url = base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    ctx = ssl.create_default_context()
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:2000]
        raise LLMClientError(f"HTTP {e.code}: {err_body}") from e
    except urllib.error.URLError as e:
        raise LLMClientError(f"URL error: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMClientError(f"Invalid JSON from API: {raw[:500]}") from e

    if isinstance(data, dict):
        duration_ms = round((time.monotonic() - t0) * 1000.0, 2)
        host = urlparse(base_url).netloc or base_url[:120]
        meta = {"duration_ms": duration_ms, "api_host": host}
        rid = data.get("id")
        if rid is not None:
            meta["request_id"] = str(rid)
        data["_client_meta"] = meta
    return data


def parse_message_content_json(resp: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """从 chat completion 响应中取出 JSON 对象与 usage 元数据（含 token 与可选 duration/request_id）。"""
    try:
        choice = resp["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMClientError(f"Unexpected response shape: {repr(resp)[:800]}") from e
    block = extract_json_object(str(content))
    try:
        parsed = json.loads(block)
    except json.JSONDecodeError as e:
        raise LLMClientError(f"Model did not return valid JSON: {block[:800]}") from e
    if not isinstance(parsed, dict):
        raise LLMClientError("Model JSON root must be an object")
    usage = resp.get("usage") or {}
    u_in = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    u_out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    out: dict[str, Any] = {"input_tokens": u_in, "output_tokens": u_out}
    cm = resp.get("_client_meta")
    if isinstance(cm, dict):
        if "duration_ms" in cm:
            out["duration_ms"] = cm["duration_ms"]
        if "api_host" in cm:
            out["api_host"] = cm["api_host"]
        if "request_id" in cm:
            out["request_id"] = cm["request_id"]
    return parsed, out


class LLMClientError(Exception):
    pass
