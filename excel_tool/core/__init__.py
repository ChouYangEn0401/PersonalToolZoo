"""GUI-free core: model, operations, registry, diff, transforms.

Nothing in this package imports tkinter — it is safe to use from the CLI and
from headless tests.
"""
from .session import TableSession
from .registry import Param, Operation, REGISTRY, register, get, apply, describe
from . import operations  # noqa: F401  (registers the built-in operations)
from . import diff  # noqa: F401
from . import transforms  # noqa: F401

__all__ = [
    "TableSession",
    "Param", "Operation", "REGISTRY", "register", "get", "apply", "describe",
    "operations", "diff", "transforms",
]
