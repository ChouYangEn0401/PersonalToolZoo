import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from . import git_utils
    from . import file_categories
    from . import snapshot_utils
except Exception:
    import git_utils
    import file_categories
    import snapshot_utils

# ══════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════

def _fmt_bytes(n: int) -> str:
    """Format a byte delta with +/- sign."""
    if n == 0:
        return "0 B"
    sign = "+" if n > 0 else "-"
    val = abs(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024.0:
            fmt = f"{val:.0f}" if unit == "B" else f"{val:.1f}"
            return f"{sign}{fmt} {unit}"
        val /= 1024.0
    return f"{sign}{val:.1f} TB"


def _fmt_bytes_abs(n: int) -> str:
    """Format an absolute byte count (no +/- sign)."""
    val = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024.0:
            fmt = f"{val:.0f}" if unit == "B" else f"{val:.1f}"
            return f"{fmt} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


def _fmt_net(n: int) -> str:
    """Format line net change with explicit +/- sign."""
    if n > 0:
        return f"+{n:,}"
    if n < 0:
        return f"{n:,}"
    return "0"


# ══════════════════════════════════════════════
#  Palette & Fonts
# ══════════════════════════════════════════════

BG          = "#f0f2f5"
BG_HDR      = "#1e293b"
ACCENT      = "#4f46e5"
ACCENT_HV   = "#6366f1"
ROW_ODD     = "#ffffff"
ROW_EVEN    = "#f8fafc"
SEL_BG      = "#4f46e5"
CARD_BG     = "#ffffff"
TEXT_MAIN   = "#111827"
TEXT_DIM    = "#6b7280"
TEXT_WHITE  = "#f1f5f9"
TEXT_SUB    = "#94a3b8"
TXT_BG      = "#1e293b"
TXT_FG      = "#e2e8f0"
CHIP_BG     = "#e0e7ff"
CHIP_BG_HV  = "#c7d2fe"
MINI_BG     = "#e5e7eb"
MINI_BG_HV  = "#d1d5db"
SASH_BG     = "#94a3b8"
TAB_BG      = "#e2e8f0"

FF   = "Segoe UI"
MONO = "Consolas"

FONT_TITLE   = (FF, 15, "bold")
FONT_HDR_SUB = (FF, 9)
FONT_LABEL   = (FF, 10, "bold")
FONT_BODY    = (FF, 10)
FONT_MONO    = (MONO, 9)
FONT_STAT    = (FF, 20, "bold")
FONT_STAT_LB = (FF, 8)


# ══════════════════════════════════════════════
#  Style
# ══════════════════════════════════════════════

def _apply_styles() -> None:
    s = ttk.Style()
    s.theme_use("clam")

    s.configure("TFrame",     background=BG)
    s.configure("TLabel",     background=BG, foreground=TEXT_MAIN, font=FONT_BODY)
    s.configure("TSeparator", background="#d1d5db")

    s.configure("TEntry", font=FONT_BODY, fieldbackground="#ffffff",
                foreground=TEXT_MAIN, padding=5)

    s.configure("Accent.TButton", font=(FF, 10, "bold"),
                background=ACCENT, foreground="#ffffff",
                padding=(22, 9), relief="flat", borderwidth=0)
    s.map("Accent.TButton",
          background=[("active", ACCENT_HV), ("pressed", "#3730a3"), ("disabled", "#c7d2fe")],
          foreground=[("active", "#ffffff"), ("disabled", "#a5b4fc")])

    s.configure("Preset.TButton", font=(FF, 9, "bold"),
                background=CHIP_BG, foreground=ACCENT,
                padding=(14, 6), relief="flat", borderwidth=0)
    s.map("Preset.TButton",
          background=[("active", CHIP_BG_HV), ("pressed", "#a5b4fc"), ("disabled", "#eef0f4")],
          foreground=[("disabled", "#b7bcc7")])

    s.configure("Mini.TButton", font=(FF, 8),
                background=MINI_BG, foreground=TEXT_DIM,
                padding=(6, 2), relief="flat", borderwidth=0)
    s.map("Mini.TButton", background=[("active", MINI_BG_HV)])

    s.configure("Hdr.TFrame",  background=BG_HDR)
    s.configure("Hdr.TLabel",  background=BG_HDR, foreground=TEXT_WHITE, font=FONT_TITLE)
    s.configure("HdrS.TLabel", background=BG_HDR, foreground=TEXT_SUB,   font=FONT_HDR_SUB)

    s.configure("Card.TFrame",  background=CARD_BG, relief="flat")
    s.configure("CardV.TLabel", background=CARD_BG, foreground=ACCENT,   font=FONT_STAT)
    s.configure("CardL.TLabel", background=CARD_BG, foreground=TEXT_DIM, font=FONT_STAT_LB)

    s.configure("CatHdr.TLabel",   background=BG, foreground=TEXT_MAIN, font=(FF, 9, "bold"))
    s.configure("CatCount.TLabel", background=BG, foreground=TEXT_DIM,  font=(FF, 8))

    s.configure("Treeview",
                background=ROW_ODD, fieldbackground=ROW_ODD,
                foreground=TEXT_MAIN, font=FONT_BODY, rowheight=26)
    s.configure("Treeview.Heading",
                background="#e2e8f0", foreground=TEXT_MAIN,
                font=(FF, 9, "bold"), relief="flat", padding=(6, 4))
    s.map("Treeview",
          background=[("selected", SEL_BG)],
          foreground=[("selected", "#ffffff")])

    s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(8, 8, 8, 0))
    s.configure("TNotebook.Tab", background=TAB_BG, foreground=TEXT_DIM,
                font=(FF, 10, "bold"), padding=(18, 9), borderwidth=0)
    s.map("TNotebook.Tab",
          background=[("selected", CARD_BG)],
          foreground=[("selected", ACCENT)])

    s.configure("SBar.TLabel",
                background="#e2e8f0", foreground=TEXT_DIM,
                font=(FF, 9), padding=(10, 3))


# ══════════════════════════════════════════════
#  Card widget
# ══════════════════════════════════════════════

def _make_card(parent, label: str, var: tk.StringVar) -> ttk.Frame:
    f = ttk.Frame(parent, style="Card.TFrame", padding=(10, 5))
    cv = tk.Canvas(f, width=4, bg=ACCENT, highlightthickness=0)
    cv.pack(side="left", fill="y", padx=(0, 10))
    inner = ttk.Frame(f, style="Card.TFrame")
    inner.pack(side="left", fill="both", expand=True)
    ttk.Label(inner, textvariable=var, style="CardV.TLabel").pack(anchor="w")
    ttk.Label(inner, text=label,       style="CardL.TLabel").pack(anchor="w")
    return f


# ══════════════════════════════════════════════
#  Compute panel (shared by the Git tab and the Snapshot tab)
# ══════════════════════════════════════════════

def _build_compute_panel(parent: ttk.Frame, status_var: tk.StringVar, mode: str) -> None:
    """Build one full tab's content: input row, filters, cards, split view.

    mode == "git": diff between two commits in a git repo (git_utils) —
                   shows added/deleted/net lines and byte deltas.
    mode == "fs":  census of a single folder on disk right now
                   (snapshot_utils) — for projects with no version control,
                   so there is no "before" to diff against. Shows total
                   lines and total bytes per category instead of deltas.
    """
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)

    main = ttk.Frame(parent, padding=(20, 14))
    main.grid(row=0, column=0, sticky="nsew")
    main.columnconfigure(0, weight=1)
    main.rowconfigure(5, weight=1)

    # ── Input row ───────────────────────────────────
    inp = ttk.Frame(main)
    inp.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    if mode == "git":
        ttk.Label(inp, text="Repository", font=FONT_LABEL).grid(row=0, column=0, sticky="w", padx=(0, 6))
        repo_e = ttk.Entry(inp, width=40, font=(MONO, 10))
        repo_e.grid(row=0, column=1, sticky="w", padx=(0, 8))
        def _browse_repo():
            path = filedialog.askdirectory(title="Select Git repository")
            if path:
                repo_e.delete(0, "end")
                repo_e.insert(0, path)
        ttk.Button(inp, text="Browse", command=_browse_repo).grid(row=0, column=2, padx=(0, 12))

        ttk.Label(inp, text="Init commit", font=FONT_LABEL
                  ).grid(row=0, column=3, sticky="w", padx=(0, 6))
        init_e = ttk.Entry(inp, width=36, font=(MONO, 10))
        init_e.grid(row=0, column=4, sticky="w", padx=(0, 20))

        ttk.Label(inp, text="Latest commit", font=FONT_LABEL
                  ).grid(row=0, column=5, sticky="w", padx=(0, 6))
        latest_e = ttk.Entry(inp, width=36, font=(MONO, 10))
        latest_e.grid(row=0, column=6, sticky="w", padx=(0, 20))

        btn = ttk.Button(inp, text="▶  Compute", style="Accent.TButton")
        btn.grid(row=0, column=7)
    else:
        ttk.Label(inp, text="資料夾", font=FONT_LABEL).grid(row=0, column=0, sticky="w", padx=(0, 6))
        folder_e = ttk.Entry(inp, width=70, font=(MONO, 10))
        folder_e.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        inp.columnconfigure(1, weight=1)
        def _browse_folder():
            path = filedialog.askdirectory(title="選擇要統計的資料夾")
            if path:
                folder_e.delete(0, "end")
                folder_e.insert(0, path)
        ttk.Button(inp, text="Browse", command=_browse_folder).grid(row=0, column=2, padx=(0, 16))

        btn = ttk.Button(inp, text="▶  Compute", style="Accent.TButton")
        btn.grid(row=0, column=3)

    # ── Preset filter buttons ───────────────────────
    preset_row = ttk.Frame(main)
    preset_row.grid(row=1, column=0, sticky="ew", pady=(0, 6))
    ttk.Label(preset_row, text="快速篩選：", font=FONT_LABEL).pack(side="left", padx=(0, 8))

    DEFAULT_PRESET = "code"
    preset_btns = []  # enabled once a result has been computed

    # ── Filter panel (categorised checkbox list, populated after compute) ──
    filter_panel = ttk.Frame(main)
    filter_panel.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    ttk.Label(filter_panel, text="檔案篩選（依類別勾選，取消勾選以排除）", font=FONT_LABEL
              ).grid(row=0, column=0, sticky="w")
    filter_panel.columnconfigure(0, weight=1)

    FILTER_HEIGHT = 190
    filt_canvas = tk.Canvas(filter_panel, height=FILTER_HEIGHT, bg=BG, highlightthickness=0)
    filt_inner = ttk.Frame(filt_canvas)
    filt_vsb = ttk.Scrollbar(filter_panel, orient="vertical", command=filt_canvas.yview)
    filt_win = filt_canvas.create_window((0, 0), window=filt_inner, anchor="nw")
    filt_canvas.grid(row=1, column=0, sticky="ew")
    filt_canvas.configure(yscrollcommand=filt_vsb.set)
    filt_vsb.grid(row=1, column=1, sticky="ns")
    filt_inner.bind("<Configure>",
                     lambda _e: filt_canvas.configure(scrollregion=filt_canvas.bbox("all")))
    def _on_filt_canvas_config(e):
        filt_canvas.itemconfig(filt_win, width=e.width)
    filt_canvas.bind("<Configure>", _on_filt_canvas_config)

    def _filt_mousewheel(e):
        filt_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    filt_canvas.bind("<Enter>", lambda _e: filt_canvas.bind_all("<MouseWheel>", _filt_mousewheel))
    filt_canvas.bind("<Leave>", lambda _e: filt_canvas.unbind_all("<MouseWheel>"))

    ext_vars = {}  # bucket_key -> BooleanVar
    _suspend = {"on": False}

    def _current_checked() -> set:
        return set(k for k, v in ext_vars.items() if v.get())

    def _apply_selection(keys_to_check) -> None:
        """Bulk-set checkbox state and re-render exactly once."""
        keys_to_check = set(keys_to_check)
        _suspend["on"] = True
        for k, var in ext_vars.items():
            var.set(k in keys_to_check)
        _suspend["on"] = False
        render_from_selection(keys_to_check & set(ext_vars.keys()))

    def _make_preset_handler(preset_key):
        def _handler():
            if not ext_vars:
                return
            _apply_selection(file_categories.resolve_preset(preset_key, ext_vars.keys()))
        return _handler

    for preset_key, preset_label in file_categories.PRESETS:
        b = ttk.Button(preset_row, text=preset_label, style="Preset.TButton",
                       command=_make_preset_handler(preset_key))
        b.pack(side="left", padx=(0, 6))
        b.state(["disabled"])
        preset_btns.append(b)

    ttk.Separator(main, orient="horizontal").grid(
        row=3, column=0, sticky="ew", pady=10)

    # ── Stat cards ──────────────────────────────────
    cards_frm = ttk.Frame(main)
    cards_frm.grid(row=4, column=0, sticky="ew", pady=(0, 12))

    v_total   = tk.StringVar(value="—")
    v_types   = tk.StringVar(value="—")
    v_binary  = tk.StringVar(value="—")

    if mode == "git":
        v_added   = tk.StringVar(value="—")
        v_deleted = tk.StringVar(value="—")
        v_net     = tk.StringVar(value="—")
        v_bytes   = tk.StringVar(value="—")
        card_defs = [
            ("總檔案數",    v_total),
            ("副檔名種類",  v_types),
            ("新增行（+）", v_added),
            ("刪除行（-）", v_deleted),
            ("淨變動行",    v_net),
            ("位元組變動",  v_bytes),
            ("Binary 檔數", v_binary),
        ]
    else:
        v_lines = tk.StringVar(value="—")
        v_size  = tk.StringVar(value="—")
        card_defs = [
            ("總檔案數",    v_total),
            ("副檔名種類",  v_types),
            ("總行數",      v_lines),
            ("總大小",      v_size),
            ("Binary 檔數", v_binary),
        ]
    for col, (lbl, var) in enumerate(card_defs):
        c = _make_card(cards_frm, lbl, var)
        c.grid(row=0, column=col, padx=(0, 8), sticky="nsew")
        cards_frm.columnconfigure(col, weight=1)
        cards_frm.rowconfigure(0, weight=0)

    # ── Treeview + Summary (draggable split) ────────
    split = tk.PanedWindow(main, orient="vertical", sashrelief="raised",
                            sashwidth=10, sashpad=2, bg=SASH_BG,
                            showhandle=True, handlesize=16,
                            bd=0, opaqueresize=True)
    split.grid(row=5, column=0, sticky="nsew")

    tv_frm = ttk.Frame(split)
    tv_frm.columnconfigure(0, weight=1)
    tv_frm.rowconfigure(0, weight=1)

    if mode == "git":
        cols = ("ext", "cat", "files", "binary_f", "added", "deleted", "net", "bytes", "sample")
        hdrs = {
            "ext": "副檔名", "cat": "分類", "files": "檔案總數", "binary_f": "Binary",
            "added": "＋新增行", "deleted": "－刪除行", "net": "淨變動",
            "bytes": "位元組差異", "sample": "範例檔案",
        }
        widths = {
            "ext": 95, "cat": 110, "files": 68, "binary_f": 60,
            "added": 82, "deleted": 82, "net": 82, "bytes": 110, "sample": 0,
        }
        anchors = {
            "ext": "w", "cat": "w", "files": "e", "binary_f": "e",
            "added": "e", "deleted": "e", "net": "e", "bytes": "e", "sample": "w",
        }
    else:
        cols = ("ext", "cat", "files", "binary_f", "lines", "bytes", "sample")
        hdrs = {
            "ext": "副檔名", "cat": "分類", "files": "檔案總數", "binary_f": "Binary",
            "lines": "總行數", "bytes": "總大小", "sample": "範例檔案",
        }
        widths = {
            "ext": 95, "cat": 110, "files": 68, "binary_f": 60,
            "lines": 90, "bytes": 100, "sample": 0,
        }
        anchors = {
            "ext": "w", "cat": "w", "files": "e", "binary_f": "e",
            "lines": "e", "bytes": "e", "sample": "w",
        }

    tree = ttk.Treeview(tv_frm, columns=cols, show="headings",
                        height=8, selectmode="browse")
    for c in cols:
        tree.heading(c, text=hdrs[c])
        stretch = c == "sample"
        tree.column(c, width=widths[c], anchor=anchors[c], stretch=stretch,
                    minwidth=widths[c] if widths[c] else 200)

    tree.tag_configure("odd",  background=ROW_ODD)
    tree.tag_configure("even", background=ROW_EVEN)

    vsb = ttk.Scrollbar(tv_frm, orient="vertical",   command=tree.yview)
    hsb = ttk.Scrollbar(tv_frm, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    split.add(tv_frm, minsize=160, height=320, stretch="always")

    # ── Summary text ────────────────────────────────
    sum_frm = ttk.Frame(split)
    sum_frm.columnconfigure(0, weight=1)
    sum_frm.rowconfigure(0, weight=1)

    summary_txt = tk.Text(
        sum_frm, height=4, font=FONT_MONO,
        bg=TXT_BG, fg=TXT_FG, insertbackground=TXT_FG,
        relief="flat", padx=12, pady=8, wrap="word",
    )
    txt_vsb = ttk.Scrollbar(sum_frm, orient="vertical", command=summary_txt.yview)
    summary_txt.configure(yscrollcommand=txt_vsb.set)
    summary_txt.grid(row=0, column=0, sticky="nsew")
    txt_vsb.grid(row=0, column=1, sticky="ns")

    summary_txt.tag_configure("grn",  foreground="#4ade80")
    summary_txt.tag_configure("red",  foreground="#f87171")
    summary_txt.tag_configure("dim",  foreground="#475569")
    summary_txt.tag_configure("bold", font=(MONO, 9, "bold"), foreground="#e2e8f0")
    summary_txt.tag_configure("acc",  foreground="#818cf8")

    split.add(sum_frm, minsize=90, height=170, stretch="always")

    # ── Compute logic ───────────────────────────────
    last_agg = {}

    def render_from_selection(selected_exts: set):
        """Render cards, table and summary using filtered ext set (no new calls)."""
        by_ext_local = {k: v for k, v in last_agg["by_ext"].items() if k in selected_exts}

        shown_files  = sum(v["files"]  for v in by_ext_local.values())
        total_binary = sum(v["binary"] for v in by_ext_local.values())

        v_total .set(str(shown_files))
        v_types .set(str(len(by_ext_local)))
        v_binary.set(str(total_binary))

        if mode == "git":
            total_added = sum(v["added"]       for v in by_ext_local.values())
            total_del   = sum(v["deleted"]      for v in by_ext_local.values())
            total_bytes = sum(v["bytes_change"] for v in by_ext_local.values())
            net_lines   = total_added - total_del
            v_added  .set(f"+{total_added:,}")
            v_deleted.set(f"-{total_del:,}")
            v_net    .set(_fmt_net(net_lines))
            v_bytes  .set(_fmt_bytes(total_bytes))
        else:
            total_lines = sum(v["lines"] for v in by_ext_local.values())
            total_size  = sum(v["bytes"] for v in by_ext_local.values())
            v_lines.set(f"{total_lines:,}")
            v_size .set(_fmt_bytes_abs(total_size))

        # fill table
        tree.delete(*tree.get_children())
        for i, (ext, v) in enumerate(sorted(by_ext_local.items(), key=lambda x: -x[1]["files"])):
            tag = "odd" if i % 2 == 0 else "even"
            cat_label = file_categories.CATEGORIES[file_categories.categorize(ext)]["label"]
            if mode == "git":
                net = v["added"] - v["deleted"]
                values = (ext, cat_label, v["files"], v["binary"] if v["binary"] else "",
                          v["added"], v["deleted"], _fmt_net(net),
                          _fmt_bytes(v["bytes_change"]), ", ".join(v["sample"]))
            else:
                values = (ext, cat_label, v["files"], v["binary"] if v["binary"] else "",
                          f"{v['lines']:,}", _fmt_bytes_abs(v["bytes"]), ", ".join(v["sample"]))
            tree.insert("", "end", tags=(tag,), values=values)

        # update summary text
        summary_txt.configure(state="normal")
        summary_txt.delete("1.0", "end")
        def w(text, tag=""):
            summary_txt.insert("end", text, tag)
        DIV = "─" * 78 + "\n"
        w(DIV, "dim")
        if mode == "git":
            w("  diff  ", "bold")
            w(last_agg.get("init_ref", ""), "acc"); w("  →  ", "dim"); w(last_agg.get("latest_ref", "") + "\n", "acc")

            init_iso   = last_agg.get("init_time") or ""
            latest_iso = last_agg.get("latest_time") or ""
            dur_h      = last_agg.get("duration_human") or ""
            if init_iso and latest_iso:
                w(DIV, "dim")
                w(f"  時間範圍      ", "dim"); w(f"{init_iso}  →  {latest_iso}\n", "acc")
                w(f"  持續時間      ", "dim"); w(f"{dur_h}\n", "bold")
        else:
            w("  snapshot  ", "bold")
            w(last_agg.get("folder_ref", "") + "\n", "acc")

            scan_time = last_agg.get("scan_time") or ""
            if scan_time:
                w(DIV, "dim")
                w(f"  掃描時間      ", "dim"); w(f"{scan_time}\n", "acc")

        w(DIV, "dim")
        w(f"  總共檔案數     ", "dim"); w(f"{shown_files}\n", "bold")
        w(f"  副檔名種類     ", "dim"); w(f"{len(by_ext_local)}\n", "bold")
        w(f"  Binary 檔案    ", "dim"); w(f"{total_binary}\n", "bold")
        w("\n")
        if mode == "git":
            w(f"  新增行（+）    ", "dim"); w(f"+{total_added:,}\n", "grn")
            w(f"  刪除行（-）    ", "dim"); w(f"-{total_del:,}\n",   "red")
            w(f"  淨變動         ", "dim")
            w(f"{_fmt_net(net_lines)}\n", "grn" if net_lines >= 0 else "red")
            w("\n")
            w(f"  位元組變動合計  ", "dim"); w(f"{_fmt_bytes(total_bytes)}\n", "bold")
        else:
            w(f"  總行數         ", "dim"); w(f"{total_lines:,}\n", "bold")
            w(f"  總大小         ", "dim"); w(f"{_fmt_bytes_abs(total_size)}\n", "bold")

        # show excluded extensions
        all_exts = set(last_agg["by_ext"].keys())
        excluded = sorted(list(all_exts - selected_exts))
        if excluded:
            exs = ", ".join(excluded[:12]) + ("..." if len(excluded) > 12 else "")
            w("\n")
            w(f"  Excluded ({len(excluded)}): {exs}\n", "acc")

        w(DIV, "dim")
        summary_txt.configure(state="disabled")

    def _rebuild_filter_panel(agg):
        for wdg in filt_inner.winfo_children():
            wdg.destroy()
        ext_vars.clear()
        filt_inner.columnconfigure(0, weight=1)

        cat_groups = file_categories.group_by_category(agg["by_ext"])
        ncols = max(4, (filt_canvas.winfo_width() or 1000) // 130)

        for r, (_cat_key, ginfo) in enumerate(cat_groups):
            block = ttk.Frame(filt_inner, padding=(4, 4))
            block.grid(row=r, column=0, sticky="ew")

            hdr_row = ttk.Frame(block)
            hdr_row.pack(fill="x", anchor="w")
            ttk.Label(hdr_row, text=ginfo["label"], style="CatHdr.TLabel").pack(side="left")
            ttk.Label(hdr_row, text=f"  {len(ginfo['members'])} 種．{ginfo['files']} 檔案",
                      style="CatCount.TLabel").pack(side="left")

            members = list(ginfo["members"])
            def _select_all(members=members):
                _apply_selection(_current_checked() | set(members))
            def _select_none(members=members):
                _apply_selection(_current_checked() - set(members))
            ttk.Button(hdr_row, text="全選", style="Mini.TButton",
                       command=_select_all).pack(side="left", padx=(10, 2))
            ttk.Button(hdr_row, text="清空", style="Mini.TButton",
                       command=_select_none).pack(side="left")

            grid_frm = ttk.Frame(block)
            grid_frm.pack(fill="x", anchor="w", pady=(2, 4))
            for i, ext in enumerate(sorted(members, key=lambda e: -agg["by_ext"][e]["files"])):
                var = tk.BooleanVar(value=True)
                cnt = agg["by_ext"][ext]["files"]
                cb = ttk.Checkbutton(grid_frm, text=f"{ext} ({cnt})", variable=var)
                cb.grid(row=i // ncols, column=i % ncols, sticky="w", padx=(2, 14), pady=1)
                ext_vars[ext] = var

        def on_cb_change(*_):
            if _suspend["on"]:
                return
            render_from_selection(_current_checked())
        for var in ext_vars.values():
            var.trace_add("write", on_cb_change)

    def run():
        if mode == "git":
            init   = init_e.get().strip()
            latest = latest_e.get().strip()
            repo = repo_e.get().strip() or None
            if not init or not latest:
                messagebox.showwarning("Input missing",
                                       "請輸入 Init 與 Latest commit hash 或 ref")
                return
        else:
            folder = folder_e.get().strip()
            if not folder or not os.path.isdir(folder):
                messagebox.showwarning("Input missing", "請選擇有效的資料夾路徑")
                return

        btn.state(["disabled"])
        status_var.set("Computing …")
        main.update_idletasks()

        try:
            if mode == "git":
                agg = git_utils.aggregate_by_extension(init, latest, repo_path=repo)
            else:
                agg = snapshot_utils.scan_by_extension(folder)
        except Exception as exc:
            status_var.set("Error")
            messagebox.showerror("Error", str(exc))
            btn.state(["!disabled"])
            return

        # cache aggregation
        last_agg.clear()
        last_agg.update(agg)
        if mode == "git":
            last_agg["init_ref"] = init
            last_agg["latest_ref"] = latest
        else:
            last_agg["folder_ref"] = folder

        _rebuild_filter_panel(agg)

        # apply the default preset instead of "select everything"
        default_keys = file_categories.resolve_preset(DEFAULT_PRESET, ext_vars.keys())
        _apply_selection(default_keys)

        for b in preset_btns:
            b.state(["!disabled"])

        btn.state(["!disabled"])
        if mode == "git":
            total_added = sum(v["added"]   for v in agg["by_ext"].values())
            total_del   = sum(v["deleted"] for v in agg["by_ext"].values())
            total_bytes = sum(v["bytes_change"] for v in agg["by_ext"].values())
            status_var.set(
                f"Done — {agg['total_files']} files  |  "
                f"+{total_added:,} / -{total_del:,} lines  |  "
                f"{_fmt_bytes(total_bytes)}"
            )
        else:
            total_lines = sum(v["lines"] for v in agg["by_ext"].values())
            total_size  = sum(v["bytes"] for v in agg["by_ext"].values())
            status_var.set(
                f"Done — {agg['total_files']} files  |  "
                f"{total_lines:,} lines  |  "
                f"{_fmt_bytes_abs(total_size)}"
            )

    btn.configure(command=run)


# ══════════════════════════════════════════════
#  Main UI builder
# ══════════════════════════════════════════════

def build_ui(root: tk.Tk) -> tk.Tk:
    root.title("diff_showcaser — Git Diff Statistics — v1.3.0")
    root.configure(bg=BG)
    root.minsize(1120, 860)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    _apply_styles()

    # ── Header bar ──────────────────────────────────
    hdr = ttk.Frame(root, style="Hdr.TFrame", padding=(24, 14))
    hdr.grid(row=0, column=0, sticky="ew")
    ttk.Label(hdr, text="🔍  diff_showcaser", style="Hdr.TLabel"
              ).grid(row=0, column=0, sticky="w")
    ttk.Label(hdr,
              text="Git diff between two commits, or census a single folder · line & byte stats per file type",
              style="HdrS.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ── Status bar (shared across tabs) ─────────────
    status_var = tk.StringVar(value="Ready")
    ttk.Label(root, textvariable=status_var, style="SBar.TLabel", anchor="w"
              ).grid(row=2, column=0, sticky="ew")

    # ── Tabs ─────────────────────────────────────────
    notebook = ttk.Notebook(root)
    notebook.grid(row=1, column=0, sticky="nsew")

    tab_git = ttk.Frame(notebook)
    tab_fs  = ttk.Frame(notebook)
    notebook.add(tab_git, text="Git 版控比較")
    notebook.add(tab_fs,  text="資料夾快照（當下統計）")

    _build_compute_panel(tab_git, status_var, mode="git")
    _build_compute_panel(tab_fs,  status_var, mode="fs")

    return root


# ══════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════

def main() -> None:
    root = tk.Tk()
    build_ui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
