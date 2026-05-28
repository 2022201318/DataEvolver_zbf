"""Core services: configuration, paths, logging."""

from .config_manager import ConfigManager
from .logger import LoggerService
from .path_manager import PathManager
from .workspace import materialize_workspace, resolve_project_root

__version__ = "0.1.0"

__all__ = [
    "ConfigManager",
    "LoggerService",
    "PathManager",
    "__version__",
    "materialize_workspace",
    "resolve_project_root",
]
