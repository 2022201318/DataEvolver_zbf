"""
LLM settings: read for the settings form, save from the frontend into repo `config/`.

Writes (aligned with legacy 多模态数据准备):
- `config/config.json` — `llm` block + preserves `logging` / `api` / `storage` / `processing`
- `config/api_keys.json` — `openai` + `custom` slots
- `config/api_config.json` — primary source for `ConfigManager.llm_config()`

If `POST` body `api_key` is empty, the previous `api_config.json` key is kept (rotate key by sending a new value).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/config", tags=["config"])

_OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"


class SaveLlmBody(BaseModel):
    provider_mode: Literal["openai-official", "third-party"]
    model: str = Field(..., min_length=1, max_length=128)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(ge=1, le=200_000)
    api_key: str = ""
    base_url: str = ""


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default.copy()
    except (json.JSONDecodeError, OSError):
        return default.copy()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _ensure_v1_base(url: str) -> str:
    u = url.strip().rstrip("/")
    if not u:
        return _OPENAI_DEFAULT_BASE
    if u.endswith("/v1"):
        return u
    return f"{u}/v1"


@router.get("/llm")
def get_llm_for_settings(request: Request) -> dict[str, Any]:
    """Safe fields + masked key hint for the settings panel."""
    root: Path = request.app.state.config.root
    api_cfg = _load_json(root / "config" / "api_config.json", {})
    cfg = _load_json(root / "config" / "config.json", {})
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}

    provider = str(api_cfg.get("provider") or llm.get("provider") or "openai")
    base_url = str(api_cfg.get("base_url") or llm.get("api_url") or _OPENAI_DEFAULT_BASE)
    key = str(api_cfg.get("api_key") or llm.get("api_key") or "")

    # `custom` = 第三方代理；仅 config.json 旧数据时也可能只有 llm.provider
    if provider == "custom":
        provider_mode: Literal["openai-official", "third-party"] = "third-party"
    else:
        provider_mode = "openai-official"

    masked = ""
    if key and len(key) > 8:
        masked = f"{key[:4]}…{key[-4:]}"
    elif key:
        masked = "********"

    proc = cfg.get("processing") if isinstance(cfg.get("processing"), dict) else {}
    timeout = int(proc.get("timeout", 30))

    return {
        "provider_mode": provider_mode,
        "model": str(api_cfg.get("model") or llm.get("model") or "gpt-4o-mini"),
        "temperature": float(api_cfg.get("temperature", llm.get("temperature", 0.1))),
        "max_tokens": int(api_cfg.get("max_tokens", llm.get("max_tokens", 8000))),
        "base_url": base_url if provider_mode == "third-party" else _OPENAI_DEFAULT_BASE,
        "api_key_configured": bool(key),
        "api_key_masked": masked,
        "timeout": timeout,
    }


@router.post("/save-llm")
def save_llm(request: Request, body: SaveLlmBody) -> dict[str, Any]:
    root: Path = request.app.state.config.root
    config_path = root / "config" / "config.json"
    api_keys_path = root / "config" / "api_keys.json"
    api_config_path = root / "config" / "api_config.json"

    prev_api = _load_json(api_config_path, {})
    api_key = body.api_key.strip()
    if not api_key:
        api_key = str(prev_api.get("api_key") or "").strip()

    is_official = body.provider_mode == "openai-official"
    if is_official:
        active_base = _OPENAI_DEFAULT_BASE
    else:
        bu = _ensure_v1_base(body.base_url)
        if bu == _OPENAI_DEFAULT_BASE and not (body.base_url or "").strip():
            raise HTTPException(status_code=400, detail="第三方模式需要填写 Base URL")
        active_base = bu

    provider = "openai" if is_official else "custom"

    api_keys: dict[str, Any] = _load_json(
        api_keys_path,
        {
            "openai": {"api_key": "", "base_url": _OPENAI_DEFAULT_BASE},
            "custom": {"api_key": "", "base_url": ""},
        },
    )
    if not isinstance(api_keys.get("openai"), dict):
        api_keys["openai"] = {"api_key": "", "base_url": _OPENAI_DEFAULT_BASE}
    if not isinstance(api_keys.get("custom"), dict):
        api_keys["custom"] = {"api_key": "", "base_url": ""}

    oa = api_keys["openai"]
    cu = api_keys["custom"]
    if provider == "openai":
        oa["api_key"] = api_key
        oa["base_url"] = _OPENAI_DEFAULT_BASE
        cu.setdefault("base_url", "")
    else:
        cu["api_key"] = api_key
        cu["base_url"] = active_base
        oa["api_key"] = ""

    system_cfg = _load_json(config_path, {})
    proc_defaults = {"batch_size": 100, "timeout": 30, "max_retries": 3}
    storage_defaults = {"cache_path": "./cache", "output_path": "./output", "data_path": "./data"}
    if not isinstance(system_cfg.get("processing"), dict):
        system_cfg["processing"] = dict(proc_defaults)
    else:
        for k, v in proc_defaults.items():
            system_cfg["processing"].setdefault(k, v)
    if not isinstance(system_cfg.get("storage"), dict):
        system_cfg["storage"] = dict(storage_defaults)
    else:
        for k, v in storage_defaults.items():
            system_cfg["storage"].setdefault(k, v)
    if not isinstance(system_cfg.get("logging"), dict):
        system_cfg["logging"] = {"level": "INFO", "file": "logs/dataevolver.log"}
    if not isinstance(system_cfg.get("api"), dict):
        system_cfg["api"] = {
            "title": "多模态数据准备 API",
            "version": "0.1.0",
            "cors_origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
        }

    prev_llm = system_cfg.get("llm") if isinstance(system_cfg.get("llm"), dict) else {}
    max_workers = prev_llm.get("max_workers") if isinstance(prev_llm.get("max_workers"), int) else 100

    timeout = int(system_cfg["processing"].get("timeout", 30))

    system_cfg["llm"] = {
        "provider": provider,
        "model": body.model.strip(),
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        "max_workers": max_workers,
        "api_url": active_base,
        "api_key": api_key,
    }

    api_config = {
        "provider": provider,
        "base_url": active_base,
        "api_key": api_key,
        "model": body.model.strip(),
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        "timeout": timeout,
    }

    try:
        _atomic_write_json(api_keys_path, api_keys)
        _atomic_write_json(config_path, system_cfg)
        _atomic_write_json(api_config_path, api_config)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"写入配置文件失败: {e}") from e

    request.app.state.config.reload()

    return {
        "ok": True,
        "paths": {
            "config_json": "config/config.json",
            "api_keys_json": "config/api_keys.json",
            "api_config_json": "config/api_config.json",
        },
    }
