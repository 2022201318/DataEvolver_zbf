"""
FastAPI application factory. Run with:

    uvicorn web.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000

Working directory must be the repository root (`GitHub_Release/多模态数据准备`).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config_manager import ConfigManager
from core.logger import setup_logging
from subsystems.observability import TokenUsageTracker
from web.api.routers import health, llm_config, observability, operators, pipeline, sessions, workflow


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cm: ConfigManager = app.state.config
    log_rel = cm.get("logging.file", "logs/dataevolver.log")
    log_path = cm.root / str(log_rel)
    setup_logging(
        level=cm.get("logging.level", "INFO"),
        log_file=str(log_path),
    )
    yield


def create_app() -> FastAPI:
    cm = ConfigManager()
    settings = cm.api_settings()
    app = FastAPI(
        title=settings.get("title", "多模态数据准备 API"),
        version=settings.get("version", "0.1.0"),
        lifespan=lifespan,
    )
    app.state.config = cm
    app.state.token_usage_tracker = TokenUsageTracker()

    origins = cm.get("api.cors_origins", ["http://localhost:5173", "http://127.0.0.1:5173"])
    if isinstance(origins, list):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": settings.get("title", "多模态数据准备 API"),
            "version": settings.get("version", "0.1.0"),
            "docs": "/docs",
        }

    app.include_router(health.router, prefix="/api")
    app.include_router(observability.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(operators.router, prefix="/api")
    app.include_router(llm_config.router, prefix="/api")
    app.include_router(pipeline.router, prefix="/api")
    app.include_router(workflow.router, prefix="/api")
    return app
