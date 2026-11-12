"""舊版工具視窗（v0.3.0 的四個分頁：File／Text／Mixture／Large File）。

這裡原本是主視窗（gui/app.py）。新介面改用 ISD2 格式後，舊分頁整組搬到這個獨立視窗，
程式一行沒刪：`tab_file.py`、`tab_text.py`、`tab_mixture.py`、`tab_largefile.py`、`widgets.py`、
`core/` 都留在原位。留著的目的是**解開以前產生的 .isd 檔**；不建議再用它加密新東西。

為什麼下架、原本想做什麼、怎麼救回：見 docs/legacy-modes.md 與 docs/handoffs/ 的
encrypter-intent-and-redesign 交接單。
"""

from __future__ import annotations

import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from .theme import FONT_SMALL, PAD, GOLD_MID, GOLD_DARK, GOLD_BRIGHT, FG_LIGHT

LEGACY_TITLE = "舊版工具（.isd）— 實驗性，只建議用來解開舊檔"
LEGACY_SIZE = (1080, 780)
LEGACY_THEME = "darkly"   # 舊分頁的顏色是照深色主題寫死的

WARNING_TEXT = (
    "這是舊版（實驗性）功能，保留下來是為了解開以前的 .isd 檔。"
    "舊格式沒有完整性驗證，Mixture 的兩種模式也不會比單層加密更安全；"
    "要加密新的東西請回主視窗。"
)


def apply_gold_overrides(style: ttk.Style) -> None:
    """Overlay warm-gold colour tints onto the ttkbootstrap 'darkly' theme."""
    style.configure("TLabelframe.Label",
                    foreground=GOLD_MID, font=("Segoe UI", 10, "bold"))
    style.configure("TLabelframe",     bordercolor=GOLD_DARK)
    style.configure("TSeparator",      background=GOLD_DARK)
    style.configure("TNotebook",       tabmargins=[2, 4, 0, 0])
    style.configure("TNotebook.Tab",   padding=[14, 6],
                    font=("Segoe UI", 10, "bold"))
    style.map("TNotebook.Tab",
              foreground=[("selected", GOLD_BRIGHT), ("", FG_LIGHT)])


def open_legacy_window(root) -> tk.Toplevel:
    """開一個獨立視窗放舊的四個分頁。呼叫前主程式要先切到 LEGACY_THEME。

    舊分頁 import 時需要 pycryptodome；缺套件會丟 ImportError，由呼叫端用人話顯示。
    """
    # 延後 import：新介面不需要 pycryptodome，只有打開這個視窗才需要
    from .tab_file import FileTab
    from .tab_text import TextTab
    from .tab_mixture import MixtureTab
    from .tab_largefile import LargeFileTab

    win = tk.Toplevel(root)
    win.title(LEGACY_TITLE)
    win.geometry(f"{LEGACY_SIZE[0]}x{LEGACY_SIZE[1]}")
    win.minsize(900, 650)

    status_var = tk.StringVar(master=win, value="Ready")

    banner = ttk.Label(win, text=WARNING_TEXT, bootstyle="inverse-warning",
                       padding=(PAD, 8), wraplength=LEGACY_SIZE[0] - 4 * PAD, justify=LEFT)
    banner.pack(fill=X)

    container = ttk.Frame(win)
    container.pack(fill=BOTH, expand=True, padx=PAD, pady=(PAD, 0))

    canvas = tk.Canvas(container, highlightthickness=0)
    vscroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vscroll.set)
    vscroll.pack(side=RIGHT, fill=Y)
    canvas.pack(side=LEFT, fill=BOTH, expand=True)

    nb = ttk.Notebook(canvas, bootstyle="dark")
    nb.add(FileTab(nb, status_var), text="  File  ")
    nb.add(TextTab(nb, status_var), text="  Text  ")
    nb.add(MixtureTab(nb, status_var), text="  Mixture (experimental)  ")
    nb.add(LargeFileTab(nb, status_var), text="  Large File  --UNTESTED")

    nb_window = canvas.create_window((0, 0), window=nb, anchor="nw")
    nb.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(nb_window, width=e.width))

    def on_mousewheel(event):
        delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
        canvas.yview_scroll(delta, "units")

    # 只綁在這個視窗，不影響主視窗
    win.bind("<MouseWheel>", on_mousewheel)

    status = ttk.Frame(win, padding=(PAD, 4))
    status.pack(fill=X, side=BOTTOM)
    ttk.Separator(win).pack(fill=X, side=BOTTOM)
    ttk.Label(status, textvariable=status_var, font=FONT_SMALL,
              bootstyle="secondary").pack(side=LEFT)
    return win
