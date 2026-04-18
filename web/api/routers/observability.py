"""Runtime observability endpoints (token usage, etc.)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from subsystems.observability import TokenUsageTracker

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/token-stats")
def token_stats(request: Request) -> dict[str, Any]:
    tracker: TokenUsageTracker = request.app.state.token_usage_tracker
    return tracker.snapshot()
