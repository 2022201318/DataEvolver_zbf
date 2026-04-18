"""
Load `config/config.json` and LLM settings from `config/api_config.json`.
Environment variables override API key when set (OPENAI_API_KEY / API_KEY).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class ConfigManager:
    """Unified configuration access for the open-source tree."""

    def __init__(
        self,
        config_file: str | Path = "config/config.json",
        api_config_file: str | Path = "config/api_config.json",
        project_root: str | Path | None = None,
    ) -> None:
        self.root = Path(project_root) if project_root is not None else _default_project_root()
        self.config_path = self.root / Path(config_file)
        self.api_config_path = self.root / Path(api_config_file)
        self._config: dict[str, Any] = self._load_json(self.config_path, self._default_system_config())
        self._api_config: dict[str, Any] = self._load_json(self.api_config_path, {})

    def _load_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default.copy()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else default.copy()
        except (json.JSONDecodeError, OSError):
            return default.copy()

    def _default_system_config(self) -> dict[str, Any]:
        return {
            "logging": {"level": "INFO", "file": "logs/dataevolver.log"},
            "api": {
                "title": "DataEvolver API",
                "version": "0.1.0",
                "cors_origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
            },
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-path access, e.g. logging.level."""
        cur: Any = self._config
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def llm_config(self) -> dict[str, Any]:
        """Merged LLM settings: `api_config.json` wins, then `config.json` llm, then defaults."""
        llm = self._config.get("llm") if isinstance(self._config.get("llm"), dict) else {}
        proc = self._config.get("processing") if isinstance(self._config.get("processing"), dict) else {}
        default_timeout = int(proc.get("timeout", 30))

        raw_base = self._api_config.get("base_url") or llm.get("api_url") or "https://api.openai.com/v1"
        base_url = str(raw_base).strip().rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1" if base_url else "https://api.openai.com/v1"

        t_raw = self._api_config.get("temperature")
        if t_raw is None:
            t_raw = llm.get("temperature")
        temperature = 0.1 if t_raw is None else float(t_raw)

        mt_raw = self._api_config.get("max_tokens")
        if mt_raw is None:
            mt_raw = llm.get("max_tokens")
        max_tokens = 8000 if mt_raw is None else int(mt_raw)

        to_raw = self._api_config.get("timeout")
        timeout = default_timeout if to_raw is None else int(to_raw)

        out: dict[str, Any] = {
            "provider": str(self._api_config.get("provider") or llm.get("provider") or "openai"),
            "model": str(
                self._api_config.get("model")
                or llm.get("model")
                or llm.get("model_name")
                or "gpt-4o-mini"
            ),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "base_url": base_url,
            "api_url": base_url,
            "api_key": str(self._api_config.get("api_key") or llm.get("api_key") or ""),
            "timeout": timeout,
        }

        env_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        if env_key:
            out["api_key"] = env_key
        env_base = os.getenv("OPENAI_BASE_URL") or os.getenv("BASE_URL")
        if env_base:
            eb = env_base.strip().rstrip("/")
            if not eb.endswith("/v1"):
                eb = f"{eb}/v1"
            out["base_url"] = eb
            out["api_url"] = eb
        return out

    def api_settings(self) -> dict[str, Any]:
        return dict(self.get("api", {}))

    def reload(self) -> None:
        self._config = self._load_json(self.config_path, self._default_system_config())
        self._api_config = self._load_json(self.api_config_path, {})
