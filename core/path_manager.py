"""
Project-relative path resolution. All storage paths are relative to the repository root.
"""

from __future__ import annotations

from pathlib import Path

from core.workspace import resolve_project_root


def _default_project_root() -> Path:
    """Workspace root: repo checkout, DATAEVOLVER_ROOT, or cwd after `dataevolver init`."""
    return resolve_project_root()


class PathManager:
    """Resolve and ensure standard directories under the project root."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(base_path) if base_path is not None else _default_project_root()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        relative_dirs = [
            "data/uploads",
            "data/understanding_results",
            "data/orchestration_results",
            "data/generated_pipelines",
            "data/run_pipeline_results",
            "data/quality_check_results",
            "data/trial_runs",
            "data/workflow_runs",
            "data/artifact_history",
            "data/experiences",
            "datasets",
            "logs",
            "web/upload",
            "cache",
            "temp",
        ]
        for d in relative_dirs:
            (self.base_path / d).mkdir(parents=True, exist_ok=True)

    def root(self) -> Path:
        return self.base_path

    def rel(self, *parts: str) -> Path:
        return self.base_path.joinpath(*parts)

    def get_data_path(self, sub_path: str = "") -> Path:
        p = self.base_path / "data"
        return p / sub_path if sub_path else p

    def get_datasets_path(self, sub_path: str = "") -> Path:
        p = self.base_path / "datasets"
        return p / sub_path if sub_path else p

    def get_web_upload_path(self, sub_path: str = "") -> Path:
        p = self.base_path / "web" / "upload"
        return p / sub_path if sub_path else p

    def get_log_path(self, sub_path: str = "") -> Path:
        p = self.base_path / "logs"
        return p / sub_path if sub_path else p

    def as_json_serializable_root(self) -> str:
        """Expose root as string for API responses (relative-friendly)."""
        return str(self.base_path)
