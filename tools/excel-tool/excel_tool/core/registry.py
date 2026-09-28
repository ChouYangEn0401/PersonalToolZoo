"""Operation registry — the single source of truth shared by GUI and CLI.

Each :class:`Operation` wraps a *pure* function ``fn(df, **params) -> df`` (or
a read-only "query" that returns a result table) plus a list of :class:`Param`
describing its inputs. From that spec the GUI can auto-build a parameter dialog
and the CLI can auto-build arguments — neither re-implements the logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


# Parameter kinds understood by both the GUI dialog builder and the CLI:
#   "columns" — multi-select from the table's columns (list[str])
#   "column"  — single column name (str)
#   "text"    — free text (str)
#   "int"     — integer
#   "bool"    — checkbox (bool)
#   "choice"  — one of ``choices`` (str)
@dataclass
class Param:
    name: str
    kind: str
    label: str = ""
    default: Any = None
    choices: List[str] = field(default_factory=list)
    required: bool = True

    def __post_init__(self):
        if not self.label:
            self.label = self.name


@dataclass
class Operation:
    name: str
    fn: Callable
    label: str
    params: List[Param] = field(default_factory=list)
    result: str = "table"   # "table" replaces the session df; "query" is read-only display
    group: str = "general"
    help: str = ""


REGISTRY: Dict[str, Operation] = {}


def register(op: Operation) -> Operation:
    if op.name in REGISTRY:
        raise ValueError(f"operation '{op.name}' already registered")
    REGISTRY[op.name] = op
    return op


def get(name: str) -> Operation:
    return REGISTRY[name]


def apply(name: str, df, **params):
    """Run a registered operation. Used identically by GUI controllers and CLI."""
    return REGISTRY[name].fn(df, **params)


def describe() -> List[Dict[str, Any]]:
    """Machine-readable listing of every operation (for CLI ``list`` / help)."""
    out = []
    for op in REGISTRY.values():
        out.append({
            "name": op.name,
            "label": op.label,
            "group": op.group,
            "result": op.result,
            "params": [{"name": p.name, "kind": p.kind, "required": p.required,
                        "default": p.default, "choices": p.choices} for p in op.params],
        })
    return out
