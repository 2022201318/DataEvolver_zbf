"""Health and metadata endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta")
def meta(request: Request) -> dict[str, Any]:
    cm = request.app.state.config
    return {
        "title": cm.get("api.title", "多模态数据准备 API"),
        "version": cm.get("api.version", "0.1.0"),
    }
