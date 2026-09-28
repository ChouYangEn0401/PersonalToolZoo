"""Advanced Excel Tool — a tabbed Excel utility built on infinity_treeview.

Layering (MVC + a shared operation registry so GUI and a future CLI reuse the
same logic):

    core/   — no GUI. TableSession (Model), pure operations, the operation
              registry (param specs), diff computation, cleaning transforms.
    gui/    — View + Controller. The ttk.Notebook shell, tabs, the coloured
              InfinityTable layer. Buttons call controller callbacks which call
              core operations; the model notifies views via observers.
    cli.py  — dispatches the *same* registry operations from the command line.

Phase 1 delivers the skeleton + empty-shell tabs only; each tab's controls are
filled in on later phases.
"""

__version__ = "0.1.0"
