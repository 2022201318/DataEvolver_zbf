"""In-process LLM token usage counters (wired into LLMService later)."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class TokenUsageTracker:
    """Thread-safe token counters for observability endpoints."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    api_calls: int = 0
    model_usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str | None = None,
        **_: Any,
    ) -> None:
        with self._lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.api_calls += 1
            if model:
                bucket = self.model_usage.setdefault(
                    model,
                    {"total_tokens": 0, "api_calls": 0},
                )
                bucket["total_tokens"] += input_tokens + output_tokens
                bucket["api_calls"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total = self.total_input_tokens + self.total_output_tokens
            return {
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": total,
                "api_calls": self.api_calls,
                "model_usage": dict(self.model_usage),
            }

    def reset(self) -> None:
        with self._lock:
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.api_calls = 0
            self.model_usage.clear()
