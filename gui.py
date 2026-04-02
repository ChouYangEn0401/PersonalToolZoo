import tkinter as tk
from tkinter import ttk, messagebox

try:
    from . import git_utils
except Exception:
    import git_utils

# ══════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════

def _fmt_bytes(n: int) -> str:
    """Format bytes with +/- sign."""
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

    s.configure("Hdr.TFrame",  background=BG_HDR)
    s.configure("Hdr.TLabel",  background=BG_HDR, foreground=TEXT_WHITE, font=FONT_TITLE)
    s.configure("HdrS.TLabel", background=BG_HDR, foreground=TEXT_SUB,   font=FONT_HDR_SUB)

    s.configure("Card.TFrame",  background=CARD_BG, relief="flat")
    s.configure("CardV.TLabel", background=CARD_BG, foreground=ACCENT,   font=FONT_STAT)
    s.configure("CardL.TLabel", background=CARD_BG, foreground=TEXT_DIM, font=FONT_STAT_LB)

    s.configure("Treeview",
                background=ROW_ODD, fieldbackground=ROW_ODD,
                foreground=TEXT_MAIN, font=FONT_BODY, rowheight=26)
    s.configure("Treeview.Heading",
                background="#e2e8f0", foreground=TEXT_MAIN,
                font=(FF, 9, "bold"), relief="flat", padding=(6, 4))
    s.map("Treeview",
          background=[("selected", SEL_BG)],
          foreground=[("selected", "#ffffff")])

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
#  Main UI builder
# ══════════════════════════════════════════════

def build_ui(root: tk.Tk) -> tk.Tk:
    root.title("diff_showcaser — Git Diff Statistics")
    root.configure(bg=BG)
    root.minsize(1060, 740)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    _apply_styles()

    # ── Header bar ──────────────────────────────────
    hdr = ttk.Frame(root, style="Hdr.TFrame", padding=(24, 14))
    hdr.grid(row=0, column=0, sticky="ew")
    ttk.Label(hdr, text="🔍  diff_showcaser", style="Hdr.TLabel"
              ).grid(row=0, column=0, sticky="w")
    ttk.Label(hdr,
              text="Compare two Git commits · see line changes & byte deltas per file type",
              style="HdrS.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ── Main content ────────────────────────────────
    main = ttk.Frame(root, padding=(20, 14))
    main.grid(row=1, column=0, sticky="nsew")
    main.columnconfigure(0, weight=1)
    main.rowconfigure(3, weight=3)
    main.rowconfigure(4, weight=1)

    # ── Input row ───────────────────────────────────
    inp = ttk.Frame(main)
    inp.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    ttk.Label(inp, text="Init commit", font=FONT_LABEL
              ).grid(row=0, column=0, sticky="w", padx=(0, 6))
    init_e = ttk.Entry(inp, width=36, font=(MONO, 10))
    init_e.grid(row=0, column=1, sticky="w", padx=(0, 20))

    ttk.Label(inp, text="Latest commit", font=FONT_LABEL
              ).grid(row=0, column=2, sticky="w", padx=(0, 6))
    latest_e = ttk.Entry(inp, width=36, font=(MONO, 10))
    latest_e.grid(row=0, column=3, sticky="w", padx=(0, 20))

    btn = ttk.Button(inp, text="▶  Compute", style="Accent.TButton")
    btn.grid(row=0, column=4)

    # ── Filter panel (checkbox list populated after compute) ─────
    filter_panel = ttk.Frame(main)
    filter_panel.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    ttk.Label(filter_panel, text="Extensions (uncheck to exclude)", font=FONT_LABEL).grid(row=0, column=0, sticky="w")
    # horizontal scroll area for many extensions (full-width)
    filter_panel.columnconfigure(0, weight=1)
    cb_canvas = tk.Canvas(filter_panel, height=32, bg=BG, highlightthickness=0)
    cb_frame = ttk.Frame(cb_canvas)
    cb_hsb = ttk.Scrollbar(filter_panel, orient="horizontal", command=cb_canvas.xview)
    win_id = cb_canvas.create_window((0, 0), window=cb_frame, anchor="nw")
    cb_canvas.grid(row=1, column=0, sticky="ew")
    cb_canvas.configure(xscrollcommand=cb_hsb.set)
    cb_hsb.grid(row=2, column=0, sticky="ew")
    cb_frame.bind("<Configure>", lambda e: cb_canvas.configure(scrollregion=cb_canvas.bbox("all")))
    # make inner window width follow content when wider than canvas, otherwise fill canvas
    def _on_canvas_config(e):
        try:
            reqw = cb_frame.winfo_reqwidth()
            target = reqw if reqw > e.width else e.width
            cb_canvas.itemconfig(win_id, width=target)
        except Exception:
            pass
    cb_canvas.bind("<Configure>", _on_canvas_config)
    ext_vars = {}  # ext -> BooleanVar

    ttk.Separator(main, orient="horizontal").grid(
        row=2, column=0, sticky="ew", pady=10)

    # ── Stat cards ──────────────────────────────────
    cards_frm = ttk.Frame(main)
    cards_frm.grid(row=2, column=0, sticky="ew", pady=(0, 12))

    v_total   = tk.StringVar(value="—")
    v_types   = tk.StringVar(value="—")
    v_added   = tk.StringVar(value="—")
    v_deleted = tk.StringVar(value="—")
    v_net     = tk.StringVar(value="—")
    v_bytes   = tk.StringVar(value="—")
    v_binary  = tk.StringVar(value="—")

    card_defs = [
        ("總檔案數",    v_total),
        ("副檔名種類",  v_types),
        ("新增行（+）", v_added),
        ("刪除行（-）", v_deleted),
        ("淨變動行",    v_net),
        ("位元組變動",  v_bytes),
        ("Binary 檔數", v_binary),
    ]
    for col, (lbl, var) in enumerate(card_defs):
        c = _make_card(cards_frm, lbl, var)
        c.grid(row=0, column=col, padx=(0, 8), sticky="nsew")
        cards_frm.columnconfigure(col, weight=1)
        cards_frm.rowconfigure(0, weight=0)

    # ── Treeview ────────────────────────────────────
    tv_frm = ttk.Frame(main)
    tv_frm.grid(row=3, column=0, sticky="nsew")
    tv_frm.columnconfigure(0, weight=1)
    tv_frm.rowconfigure(0, weight=1)

    cols = ("ext", "files", "binary_f", "added", "deleted", "net", "bytes", "sample")
    hdrs = {
        "ext":      "副檔名",
        "files":    "檔案總數",
        "binary_f": "Binary",
        "added":    "＋新增行",
        "deleted":  "－刪除行",
        "net":      "淨變動",
        "bytes":    "位元組差異",
        "sample":   "範例檔案",
    }
    widths = {
        "ext": 105, "files": 70, "binary_f": 68,
        "added": 88, "deleted": 88, "net": 88,
        "bytes": 118, "sample": 0,
    }
    anchors = {
        "ext": "w", "files": "e", "binary_f": "e",
        "added": "e", "deleted": "e", "net": "e",
        "bytes": "e", "sample": "w",
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

    # ── Summary text ────────────────────────────────
    sum_frm = ttk.Frame(main)
    sum_frm.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
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

    # ── Status bar ──────────────────────────────────
    status_var = tk.StringVar(value="Ready")
    ttk.Label(root, textvariable=status_var, style="SBar.TLabel", anchor="w"
              ).grid(row=2, column=0, sticky="ew")

    # ── Compute logic ───────────────────────────────
    last_agg = {}

    def render_from_selection(selected_exts: set):
        """Render cards, table and summary using filtered ext set (no new git calls)."""
        by_ext_local = {k: v for k, v in last_agg["by_ext"].items() if k in selected_exts}

        # compute totals
        total_added  = sum(v["added"]       for v in by_ext_local.values())
        total_del    = sum(v["deleted"]      for v in by_ext_local.values())
        total_bytes  = sum(v["bytes_change"] for v in by_ext_local.values())
        total_binary = sum(v["binary"]       for v in by_ext_local.values())
        net_lines    = total_added - total_del

        # update cards
        v_total  .set(str(last_agg["total_files"]))
        v_types  .set(str(len(by_ext_local)))
        v_added  .set(f"+{total_added:,}")
        v_deleted.set(f"-{total_del:,}")
        v_net    .set(_fmt_net(net_lines))
        v_bytes  .set(_fmt_bytes(total_bytes))
        v_binary .set(str(total_binary))

        # fill table
        tree.delete(*tree.get_children())
        for i, (ext, v) in enumerate(sorted(by_ext_local.items(), key=lambda x: -x[1]["files"])):
            net = v["added"] - v["deleted"]
            tag = "odd" if i % 2 == 0 else "even"
            tree.insert("", "end", tags=(tag,), values=(
                ext,
                v["files"],
                v["binary"] if v["binary"] else "",
                v["added"],
                v["deleted"],
                _fmt_net(net),
                _fmt_bytes(v["bytes_change"]),
                ", ".join(v["sample"]),
            ))

        # update summary text
        summary_txt.configure(state="normal")
        summary_txt.delete("1.0", "end")
        def w(text, tag=""):
            summary_txt.insert("end", text, tag)
        DIV = "─" * 78 + "\n"
        w(DIV, "dim")
        w("  diff  ", "bold")
        w(last_agg.get("init_ref", ""), "acc"); w("  →  ", "dim"); w(last_agg.get("latest_ref", "") + "\n", "acc")

        # time range if available
        init_iso   = last_agg.get("init_time") or ""
        latest_iso = last_agg.get("latest_time") or ""
        dur_h      = last_agg.get("duration_human") or ""
        if init_iso and latest_iso:
            w(DIV, "dim")
            w(f"  時間範圍      ", "dim"); w(f"{init_iso}  →  {latest_iso}\n", "acc")
            w(f"  持續時間      ", "dim"); w(f"{dur_h}\n", "bold")

        w(DIV, "dim")
        w(f"  總共變動檔案   ", "dim"); w(f"{last_agg['total_files']}\n", "bold")
        w(f"  副檔名種類     ", "dim"); w(f"{len(by_ext_local)}\n", "bold")
        w(f"  Binary 檔案    ", "dim"); w(f"{total_binary}\n", "bold")
        w("\n")
        w(f"  新增行（+）    ", "dim"); w(f"+{total_added:,}\n", "grn")
        w(f"  刪除行（-）    ", "dim"); w(f"-{total_del:,}\n",   "red")
        w(f"  淨變動         ", "dim")
        w(f"{_fmt_net(net_lines)}\n", "grn" if net_lines >= 0 else "red")
        w("\n")
        w(f"  位元組變動合計  ", "dim"); w(f"{_fmt_bytes(total_bytes)}\n", "bold")

        # show excluded extensions
        all_exts = set(last_agg["by_ext"].keys())
        excluded = sorted(list(all_exts - selected_exts))
        if excluded:
            exs = ", ".join(excluded[:12]) + ("..." if len(excluded) > 12 else "")
            w("\n")
            w(f"  Excluded ({len(excluded)}): {exs}\n", "acc")

        w(DIV, "dim")
        summary_txt.configure(state="disabled")

    def run():
        init   = init_e.get().strip()
        latest = latest_e.get().strip()
        if not init or not latest:
            messagebox.showwarning("Input missing",
                                   "請輸入 Init 與 Latest commit hash 或 ref")
            return

        btn.state(["disabled"])
        status_var.set("Computing …")
        root.update_idletasks()

        try:
            agg = git_utils.aggregate_by_extension(init, latest)
        except Exception as exc:
            status_var.set("Error")
            messagebox.showerror("Error", str(exc))
            btn.state(["!disabled"])
            return

        # cache aggregation
        last_agg.clear()
        last_agg.update(agg)
        last_agg["init_ref"] = init
        last_agg["latest_ref"] = latest

        # rebuild checkbox list
        for wdg in cb_frame.winfo_children():
            wdg.destroy()
        ext_vars.clear()
        for i, (ext, v) in enumerate(sorted(agg["by_ext"].items(), key=lambda x: -x[1]["files"])):
            var = tk.BooleanVar(value=True)
            cb = ttk.Checkbutton(cb_frame, text=f"{ext}  ({v['files']})", variable=var)
            cb.grid(row=0, column=i, padx=(6, 4), pady=4)
            ext_vars[ext] = var

        # initial full render
        render_from_selection(set(ext_vars.keys()))

        # live update on checkbox change
        def on_cb_change(*_):
            render_from_selection(set(k for k, var in ext_vars.items() if var.get()))
        for var in ext_vars.values():
            var.trace_add("write", on_cb_change)

        btn.state(["!disabled"])
        total_added = sum(v["added"]   for v in agg["by_ext"].values())
        total_del   = sum(v["deleted"] for v in agg["by_ext"].values())
        total_bytes = sum(v["bytes_change"] for v in agg["by_ext"].values())
        status_var.set(
            f"Done — {agg['total_files']} files  |  "
            f"+{total_added:,} / -{total_del:,} lines  |  "
            f"{_fmt_bytes(total_bytes)}"
        )

    btn.configure(command=run)
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
