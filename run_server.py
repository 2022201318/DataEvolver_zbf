#!/usr/bin/env python3
"""
Development server entry. From repository root:

    python run_server.py

Or:

    uvicorn web.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="DataEvolver API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent
    # Keep reload focused on source directories to avoid OS watcher limit.
    reload_dirs = [
        str(project_root / "web"),
        str(project_root / "subsystems"),
    ]
    uvicorn.run(
        "web.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=reload_dirs if args.reload else None,
        reload_excludes=[
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "datasets",
            "output",
        ]
        if args.reload
        else None,
    )


if __name__ == "__main__":
    main()
