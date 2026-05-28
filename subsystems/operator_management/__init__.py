"""Operator registry: system default + user-evolved operators."""

from .manual_registry import (
    ManualOperatorError,
    add_manual_operators,
    build_operator_spec,
    load_operators_from_file,
    list_operators_summary,
    normalize_operator_name,
    remove_manual_operator,
)
from .registry_store import OperatorRegistryStore

__all__ = [
    "OperatorRegistryStore",
    "ManualOperatorError",
    "add_manual_operators",
    "remove_manual_operator",
    "list_operators_summary",
    "build_operator_spec",
    "load_operators_from_file",
    "normalize_operator_name",
]
