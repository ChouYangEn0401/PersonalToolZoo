"""GUI layer (View + Controller). Imports tkinter; not used by the CLI."""
from .app import AdvancedExcelApp
from .colored_table import ColoredTable

__all__ = ["AdvancedExcelApp", "ColoredTable"]
