"""TableSession — the Model.

Holds the working DataFrame plus an original snapshot and an undo stack, and
notifies registered observers (views) on every change. No GUI, no pandas I/O
dialogs — pure state. A controller mutates it; views subscribe via ``on_change``.
"""
from __future__ import annotations

from typing import Callable, List

import pandas as pd


class TableSession:
    def __init__(self, df: pd.DataFrame | None = None, name: str = ""):
        self._df = df.copy() if df is not None else pd.DataFrame()
        self._original = self._df.copy()
        self.name = name
        self._undo: List[pd.DataFrame] = []
        self._listeners: List[Callable[[pd.DataFrame], None]] = []

    # ── observer wiring (Model → View) ────────────────────────────────
    def on_change(self, callback: Callable[[pd.DataFrame], None]) -> Callable:
        """Register a view callback ``cb(df)`` fired after every change."""
        self._listeners.append(callback)
        return callback

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb(self._df)

    # ── state ─────────────────────────────────────────────────────────
    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @property
    def empty(self) -> bool:
        return self._df.empty

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def columns(self) -> list:
        return list(self._df.columns)

    def load(self, df: pd.DataFrame, name: str = "") -> None:
        """Replace the dataset and reset the original/undo baseline."""
        self._df = df.copy()
        self._original = df.copy()
        if name:
            self.name = name
        self._undo.clear()
        self._notify()

    def apply(self, new_df: pd.DataFrame) -> None:
        """Push the current df onto the undo stack and adopt ``new_df``."""
        self._undo.append(self._df)
        self._df = new_df
        self._notify()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._df = self._undo.pop()
        self._notify()
        return True

    def reset(self) -> None:
        """Return to the original snapshot (recorded as an undo step)."""
        self.apply(self._original.copy())
