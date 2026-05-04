"""
ac_helper — Reusable yellow-popup autocomplete for tkinter Entry / ttk.Combobox
===============================================================================
Usage:
    from src.gui.ac_helper import attach_autocomplete

    attach_autocomplete(
        widget,           # ttk.Entry or ttk.Combobox
        var,              # tk.StringVar linked to widget
        get_items_fn,     # callable(text: str) -> list[str]  filtered suggestions
        parent_frame,     # legacy param, kept for call-site compat (not used for pos)
        max_items=8,      # max rows shown in the listbox
        on_confirm=None,  # optional callback(value) called right after an item is confirmed
    )

Keyboard:
    Tab         move selection down (wraps to top)
    Shift+Tab   move selection up   (wraps to bottom)
    Space/Enter confirm highlighted item → fill widget, close popup
    Escape      hide popup (stops event propagation so dialog Escape is NOT triggered)
    FocusOut    hide popup (delayed to allow mouse click to register)

Mouse:
    Single click on item → confirm & fill

Notes:
    - Popup does NOT auto-open on FocusIn; it only opens when the user types.
    - If get_items_fn returns exactly one item that equals the current text, popup
      is suppressed (the field is already filled with the only match).
"""

import tkinter as tk
from tkinter import ttk


def attach_autocomplete(
    widget,
    var: tk.StringVar,
    get_items_fn,
    parent_frame=None,   # kept for call-site compatibility; not used for positioning
    max_items: int = 8,
    on_confirm=None,     # optional: callback(confirmed_value) called after item is chosen
):
    """Attach a yellow autocomplete popup to *widget*.

    The popup is always positioned directly below *widget* using widget's own
    screen coordinates, so it tracks the input field regardless of layout.
    """

    s = {
        "lb": None,
        "top": None,
        "highlighted": -1,
        "ignore_trace": False,
    }

    def _show(items):
        if not items:
            _hide()
            return

        # Create popup Toplevel once; reuse on subsequent calls
        if s["top"] is None or not s["top"].winfo_exists():
            root = widget.winfo_toplevel()
            top = tk.Toplevel(root)
            top.wm_overrideredirect(True)
            top.wm_attributes("-topmost", True)
            s["top"] = top

            frame = tk.Frame(top, bg="#fffacd", bd=1, relief="solid")
            frame.pack(fill="both", expand=True)

            scrollbar = tk.Scrollbar(frame, orient="vertical")
            lb = tk.Listbox(
                frame,
                bg="#fffacd",
                fg="#222222",
                selectbackground="#3399ff",
                selectforeground="white",
                font=("Consolas", 9),
                bd=0,
                highlightthickness=0,
                yscrollcommand=scrollbar.set,
                activestyle="none",
                exportselection=False,
            )
            scrollbar.config(command=lb.yview)
            scrollbar.pack(side="right", fill="y")
            lb.pack(side="left", fill="both", expand=True)
            s["lb"] = lb
            lb.bind("<ButtonRelease-1>", _on_click)
        else:
            s["lb"].delete(0, "end")

        s["highlighted"] = -1
        lb = s["lb"]
        for item in items:
            lb.insert("end", item)

        # Position directly below the widget
        widget.update_idletasks()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()
        w = max(widget.winfo_width(), 140)
        n = min(len(items), max_items)
        popup_h = n * 18 + 4
        s["top"].geometry(f"{w}x{popup_h}+{x}+{y}")
        s["top"].deiconify()

    def _hide(*_):
        if s["top"] is not None:
            try:
                s["top"].destroy()
            except Exception:
                pass
            s["top"] = None
            s["lb"] = None
            s["highlighted"] = -1

    def _set_highlight(idx):
        lb = s["lb"]
        if lb is None:
            return
        count = lb.size()
        if count == 0:
            return
        idx = idx % count
        lb.selection_clear(0, "end")
        lb.selection_set(idx)
        lb.see(idx)
        s["highlighted"] = idx

    def _confirm(idx=None):
        lb = s["lb"]
        if lb is None:
            return
        if idx is None:
            idx = s["highlighted"]
        if idx < 0 or idx >= lb.size():
            _hide()
            return
        value = lb.get(idx)
        # Set variable and widget value inside ignore_trace block so the trace
        # callback doesn't reopen the popup during the assignment.
        s["ignore_trace"] = True
        var.set(value)
        if isinstance(widget, ttk.Combobox):
            widget.set(value)
        s["ignore_trace"] = False
        _hide()
        widget.focus_set()
        # Fire optional on_confirm callback under ignore_trace so any side-effect
        # that modifies the variable (e.g. clearing a search field) doesn't
        # trigger the popup again.
        if on_confirm is not None:
            s["ignore_trace"] = True
            try:
                on_confirm(value)
            finally:
                s["ignore_trace"] = False

    def _on_click(event):
        lb = s["lb"]
        if lb is None:
            return
        idx = lb.nearest(event.y)
        _confirm(idx)

    def _on_tab(event):
        lb = s["lb"]
        # If popup not present, attempt to fetch items and show them
        if s["top"] is None or lb is None:
            try:
                items = get_items_fn(var.get())
            except Exception:
                items = []
            # Suppress popup when the only suggestion exactly matches what's already typed
            if len(items) == 1 and items[0] == var.get():
                return None
            if items:
                _show(items)
                _set_highlight(0)
                return "break"
            return None

        cur = s["highlighted"]
        lb = s["lb"]
        count = lb.size()
        if count == 0:
            return None
        _set_highlight((cur + 1) % count)
        return "break"

    def _on_shift_tab(event):
        lb = s["lb"]
        # If popup not present, attempt to fetch items and show them (highlight last)
        if s["top"] is None or lb is None:
            try:
                items = get_items_fn(var.get())
            except Exception:
                items = []
            if len(items) == 1 and items[0] == var.get():
                return None
            if items:
                _show(items)
                _set_highlight(len(items) - 1)
                return "break"
            return None

        cur = s["highlighted"]
        lb = s["lb"]
        count = lb.size()
        if count == 0:
            return None
        _set_highlight((cur - 1) % count)
        return "break"

    def _on_space_enter(event):
        if s["lb"] is not None and s["highlighted"] >= 0:
            _confirm(s["highlighted"])
            return "break"
        return None

    def _on_escape(event):
        if s["top"] is not None:
            _hide()
            return "break"   # popup was open: consume ESC so dialog doesn't close
        # popup was not open: let ESC propagate to dialog-level handler

    def _on_focus_out(event):
        # Delay so mouse click on listbox can fire first
        widget.after(150, _hide)

    def _on_trace(*_):
        if s["ignore_trace"]:
            return
        text = var.get()
        items = get_items_fn(text)
        # Suppress popup when the only suggestion exactly matches what's already typed
        if len(items) == 1 and items[0] == text:
            _hide()
            return
        if items:
            _show(items)
        else:
            _hide()

    # Bind keys on widget
    # NOTE: FocusIn is intentionally NOT bound to _on_trace.
    # The popup only opens when the user actively types (via var trace).
    widget.bind("<Tab>", _on_tab, add=True)
    widget.bind("<Shift-Tab>", _on_shift_tab, add=True)
    widget.bind("<space>", _on_space_enter, add=True)
    widget.bind("<Return>", _on_space_enter, add=True)
    widget.bind("<Escape>", _on_escape, add=True)
    widget.bind("<FocusOut>", _on_focus_out, add=True)

    var.trace_add("write", _on_trace)
