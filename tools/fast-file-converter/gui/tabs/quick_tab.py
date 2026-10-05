"""⚡ 快速拖放：選好轉換規則後把檔案或資料夾拖進來，結果產生在原檔案旁邊。

源自獨立的 GUI__QuickConverter.py（Quick Converter）；現在是主視窗的第一個分頁，
主題切換由主視窗統一處理。轉換邏輯在 core/quick.py。
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from collections import defaultdict

from core.quick import PRESETS, _CATEGORY_LABELS, _get_output_ext, convert_single
from gui.tabs.base_tab import BaseTab

# ── Drag-and-drop support via tkinterdnd2 ────────────────────────────────────
try:
    from tkinterdnd2 import DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

# ═════════════════════════════════════════════════════════════════════════════
# Mismatch Dialog — shown when dropped files don't match any current rule
# ═════════════════════════════════════════════════════════════════════════════


class MismatchDialog(tk.Toplevel):
    """
    Parameters
    ----------
    ext_info : { ".xlsx": (file_count, [preset_name, ...]), ... }
        Compatible presets grouped by the unmatched file extension.
    """

    def __init__(self, parent, ext_info: dict[str, tuple[int, list[str]]]):
        super().__init__(parent)
        self.title("發現不符合規則的檔案")
        self.resizable(True, True)
        self.grab_set()

        # result: (list[preset_name], add_to_rules: bool) or None (skip)
        self.result = None
        self._checks: dict[str, tk.BooleanVar] = {}
        self._add_var = tk.BooleanVar(value=True)

        self._build(ext_info)
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = 480, 420
        self.geometry(f"{w}x{h}+{pw - w // 2}+{ph - h // 2}")

    def _build(self, ext_info: dict):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="拖入的部分檔案不符合目前任何規則。\n請選擇要套用的轉換方式（可多選）：",
            justify="left",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 8))

        # ── Scrollable checkbox area ──────────────────────────────────
        wrapper = ttk.Frame(outer)
        wrapper.pack(fill="both", expand=True)

        canvas = tk.Canvas(wrapper, highlightthickness=0)
        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        def _scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _scroll)
        inner.bind("<MouseWheel>", _scroll)

        for ext, (count, preset_names) in ext_info.items():
            grp = ttk.LabelFrame(inner, text=f"{ext}  ─  {count} 個檔案", padding=6)
            grp.pack(fill="x", padx=4, pady=(4, 2))
            grp.bind("<MouseWheel>", _scroll)

            by_cat: dict[str, list[str]] = defaultdict(list)
            for pname in preset_names:
                cat_label = _CATEGORY_LABELS.get(PRESETS[pname]["category"], "其他")
                by_cat[cat_label].append(pname)

            for cat_label, names in by_cat.items():
                ttk.Label(grp, text=cat_label, font=("Segoe UI", 9, "bold")).pack(anchor="w")
                for pname in names:
                    var = tk.BooleanVar(value=False)
                    self._checks[pname] = var
                    cb = ttk.Checkbutton(grp, text=pname, variable=var)
                    cb.pack(anchor="w", padx=16)
                    cb.bind("<MouseWheel>", _scroll)

        # ── Bottom bar ────────────────────────────────────────────────
        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=(8, 6))

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")

        ttk.Checkbutton(
            bottom, text="同時加入規則列表（下次自動套用）", variable=self._add_var,
        ).pack(side="left")

        ttk.Button(bottom, text="跳過這些檔案", command=self._skip).pack(side="right", padx=(4, 0))
        ttk.Button(bottom, text="確認轉換", command=self._confirm).pack(side="right")

    def _confirm(self):
        selected = [n for n, v in self._checks.items() if v.get()]
        if not selected:
            messagebox.showinfo("提示", "請至少選擇一種轉換方式。", parent=self)
            return
        self.result = (selected, self._add_var.get())
        self.destroy()

    def _skip(self):
        self.result = None
        self.destroy()


# ═════════════════════════════════════════════════════════════════════════════
# Main App
# ═════════════════════════════════════════════════════════════════════════════


class QuickTab(BaseTab):
    """⚡ 快速拖放分頁。"""

    def __init__(self, parent, root):
        super().__init__(parent, root)
        self._overwrite = tk.BooleanVar(value=False)
        self._conflict_ask = tk.BooleanVar(value=True)
        self._rules: list[str] = []  # ordered list of active preset names

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        body = self

        # ── Rules list ──────────────────────────────────────────────────
        rules_frm = ttk.LabelFrame(body, text="轉換規則（可加入多條，同時對不同格式生效）", padding=8)
        rules_frm.pack(fill="x")

        add_row = ttk.Frame(rules_frm)
        add_row.pack(fill="x")

        self._preset_var = tk.StringVar()
        preset_names = list(PRESETS.keys())
        self._preset_var.set(preset_names[0])
        self._preset_combo = ttk.Combobox(
            add_row, textvariable=self._preset_var,
            values=preset_names, state="readonly", width=34,
        )
        self._preset_combo.pack(side="left")
        ttk.Button(add_row, text="＋ 加入", command=self._add_rule, width=8).pack(side="left", padx=(6, 0))

        list_row = ttk.Frame(rules_frm)
        list_row.pack(fill="both", expand=True, pady=(6, 0))

        lb_frame = ttk.Frame(list_row)
        lb_frame.pack(side="left", fill="both", expand=True)
        lb_sb = ttk.Scrollbar(lb_frame)
        lb_sb.pack(side="right", fill="y")
        self._rules_lb = tk.Listbox(
            lb_frame, height=4, yscrollcommand=lb_sb.set, selectmode=tk.EXTENDED,
        )
        self._rules_lb.pack(fill="both", expand=True)
        lb_sb.config(command=self._rules_lb.yview)

        btn_col = ttk.Frame(list_row)
        btn_col.pack(side="right", padx=(8, 0), anchor="n")
        ttk.Button(btn_col, text="移除選取", command=self._remove_rules, width=9).pack(pady=(0, 4))
        ttk.Button(btn_col, text="清空全部", command=self._clear_rules, width=9).pack()

        ttk.Label(
            rules_frm,
            text="💡 同一來源格式可加多條規則（例如圖片同時轉 PNG 和 ICO）；拖整個資料夾時每種檔案自動比對對應規則。",
            foreground="gray",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(6, 0))

        # ── Conflict options ─────────────────────────────────────────────
        opt_frm = ttk.LabelFrame(body, text="檔名衝突處理", padding=8)
        opt_frm.pack(fill="x", pady=(8, 0))

        ttk.Radiobutton(
            opt_frm, text="每次詢問", variable=self._conflict_ask, value=True,
            command=self._on_conflict_radio,
        ).pack(side="left", padx=4)
        ttk.Radiobutton(
            opt_frm, text="自動處理 ↓", variable=self._conflict_ask, value=False,
            command=self._on_conflict_radio,
        ).pack(side="left", padx=4)
        self._overwrite_cb = ttk.Checkbutton(
            opt_frm, text="強制覆蓋（否則加後綴）", variable=self._overwrite,
        )
        self._overwrite_cb.pack(side="left", padx=(12, 0))
        self._overwrite_cb.config(state="disabled")

        # ── Drop zone ────────────────────────────────────────────────────
        drop_frm = ttk.LabelFrame(body, text="拖放區域", padding=4)
        drop_frm.pack(fill="both", expand=True, pady=(8, 0))

        self._drop_label = tk.Label(
            drop_frm,
            text="🗂️  將檔案或資料夾拖放至此\n\n支援批次拖放多個檔案或整個資料夾\n格式不符時會自動彈出轉換選項",
            font=("Segoe UI", 11),
            relief="groove",
            bd=2,
            padx=20,
            pady=28,
        )
        self._drop_label.pack(fill="both", expand=True)

        try:
            if not _DND_AVAILABLE:
                raise tk.TclError("tkinterdnd2 not installed")
            # 主視窗是 TkinterDnD.Tk() 才有拖放（它會把 tkdnd 載入 Tcl）；一般的 tk.Tk() 會丟 TclError
            self._drop_label.drop_target_register(DND_FILES)
            self._drop_label.dnd_bind("<<Drop>>", self._on_drop)
            self._drop_label.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self._drop_label.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        except tk.TclError:
            self._drop_label.config(
                text="⚠️  未安裝 tkinterdnd2\n\n請執行: pip install tkinterdnd2\n\n安裝後重啟即可使用拖放功能",
                fg="red",
            )

        # ── Log area ─────────────────────────────────────────────────────
        log_frm = ttk.LabelFrame(body, text="轉換紀錄", padding=4)
        log_frm.pack(fill="x", pady=(8, 0))

        self._log_text = tk.Text(log_frm, height=5, state="disabled", wrap="word")
        log_sb = ttk.Scrollbar(log_frm, command=self._log_text.yview)
        self._log_text.config(yscrollcommand=log_sb.set)
        log_sb.pack(side="right", fill="y")
        self._log_text.pack(fill="x", expand=True)

    # ── Rules management ──────────────────────────────────────────────────

    def _add_rule(self, name: str | None = None, *, silent: bool = False):
        if name is None:
            name = self._preset_var.get()
        if name in self._rules:
            if not silent:
                self._log(f"ℹ️  規則「{name}」已存在。")
            return
        self._rules.append(name)
        self._rules_lb.insert(tk.END, name)

    def _remove_rules(self):
        for idx in reversed(self._rules_lb.curselection()):
            self._rules.pop(idx)
            self._rules_lb.delete(idx)

    def _clear_rules(self):
        self._rules.clear()
        self._rules_lb.delete(0, tk.END)

    # ── Misc helpers ──────────────────────────────────────────────────────

    def _on_conflict_radio(self):
        self._overwrite_cb.config(state="disabled" if self._conflict_ask.get() else "normal")

    def _log(self, msg: str):
        self._log_text.config(state="normal")
        self._log_text.insert(tk.END, msg + "\n")
        self._log_text.see(tk.END)
        self._log_text.config(state="disabled")

    def _on_drag_enter(self, event):
        self._drop_label.config(relief="sunken")

    def _on_drag_leave(self, event):
        self._drop_label.config(relief="groove")

    # ── Drop / path parsing ───────────────────────────────────────────────

    def _parse_drop_data(self, data: str) -> list[str]:
        """Parse tkdnd drop data (handles paths with spaces wrapped in braces)."""
        paths = []
        i = 0
        while i < len(data):
            if data[i] == "{":
                end = data.index("}", i)
                paths.append(data[i + 1:end])
                i = end + 2
            elif data[i] == " ":
                i += 1
            else:
                end = data.find(" ", i)
                if end == -1:
                    end = len(data)
                paths.append(data[i:end])
                i = end + 1
        return paths

    def _collect_files(self, paths: list[str]) -> list[str]:
        """Expand directories into their files recursively."""
        files = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, fnames in os.walk(p):
                    for fn in fnames:
                        files.append(os.path.join(root, fn))
            elif os.path.isfile(p):
                files.append(p)
        return files

    # ── Drop handler ──────────────────────────────────────────────────────

    def _on_drop(self, event):
        if self._running:
            self._log("⏳ 尚有轉換進行中，請稍候…")
            return

        self._drop_label.config(relief="groove")
        all_files = self._collect_files(self._parse_drop_data(event.data))

        if not all_files:
            self._log("⚠️  未偵測到有效檔案。")
            return

        # ── Match each file against the active rules ──────────────────
        # tasks: [(file_path, [rule_name, ...])]
        tasks: list[tuple[str, list[str]]] = []
        # unmatched_files: { ext: [file_path, ...] }  (no rule matched)
        unmatched_files: dict[str, list[str]] = {}

        for f in all_files:
            ext = os.path.splitext(f)[1].lower()
            matching = [r for r in self._rules if ext in PRESETS[r]["input_ext"]]
            if matching:
                tasks.append((f, matching))
            else:
                # Only track if at least one preset exists for this extension
                compatible = [n for n, p in PRESETS.items() if ext in p["input_ext"]]
                if compatible:
                    unmatched_files.setdefault(ext, []).append(f)

        # ── Show mismatch dialog for unrecognised extensions ──────────
        if unmatched_files:
            ext_info = {
                ext: (
                    len(files),
                    [n for n, p in PRESETS.items() if ext in p["input_ext"]],
                )
                for ext, files in unmatched_files.items()
            }
            dlg = MismatchDialog(self.root, ext_info)
            self.root.wait_window(dlg)

            if dlg.result:
                selected_names, add_to_rules = dlg.result
                if add_to_rules:
                    for name in selected_names:
                        self._add_rule(name, silent=True)
                # Add the previously-unmatched files using the user's selection
                for ext, files in unmatched_files.items():
                    applicable = [n for n in selected_names if ext in PRESETS[n]["input_ext"]]
                    if applicable:
                        for f in files:
                            tasks.append((f, applicable))

        if not tasks:
            if not self._rules:
                self._log("⚠️  規則列表為空，請先加入至少一條規則。")
            else:
                self._log("⚠️  沒有符合規則的檔案。")
            return

        # ── Launch conversion thread ──────────────────────────────────
        overwrite = self._overwrite.get()
        ask_each = self._conflict_ask.get()
        self._running = True

        total_ops = sum(len(rs) for _, rs in tasks)
        unique_rules = len({r for _, rs in tasks for r in rs})
        self._log(
            f"── 開始轉換：{len(tasks)} 個檔案 × {unique_rules} 種規則 = {total_ops} 個任務 ──"
        )

        def do_convert():
            success = 0
            fail = 0
            for file_path, rule_names in tasks:
                fname = os.path.basename(file_path)
                for rule_name in rule_names:
                    preset = PRESETS[rule_name]
                    try:
                        effective_overwrite = overwrite
                        if ask_each:
                            ext_out = _get_output_ext(preset)
                            if ext_out:
                                potential = os.path.splitext(file_path)[0] + ext_out
                                if os.path.exists(potential):
                                    answer = [None]
                                    done_evt = threading.Event()

                                    def ask(pot=potential, rn=rule_name):
                                        answer[0] = messagebox.askyesnocancel(
                                            "檔案已存在",
                                            f"「{os.path.basename(pot)}」已存在。\n"
                                            f"規則：{rn}\n\n"
                                            f"是 = 覆蓋　否 = 加後綴保留兩者　取消 = 跳過",
                                            parent=self.root,
                                        )
                                        done_evt.set()

                                    self.root.after(0, ask)
                                    done_evt.wait()

                                    if answer[0] is None:
                                        self.root.after(
                                            0,
                                            lambda fn=fname, rn=rule_name:
                                                self._log(f"⏭️  跳過: {fn}  [{rn}]"),
                                        )
                                        continue
                                    effective_overwrite = answer[0]

                        results = convert_single(file_path, preset, effective_overwrite)
                        out_names = ", ".join(os.path.basename(r) for r in results)
                        self.root.after(
                            0,
                            lambda fn=fname, rn=rule_name, o=out_names:
                                self._log(f"✅  {fn} → {o}  [{rn}]"),
                        )
                        success += 1
                    except Exception as e:
                        self.root.after(
                            0,
                            lambda fn=fname, rn=rule_name, err=str(e):
                                self._log(f"❌  {fn}  [{rn}]: {err}"),
                        )
                        fail += 1

            self.root.after(0, lambda: self._log(f"── 完成: {success} 成功, {fail} 失敗 ──\n"))
            self._running = False

        threading.Thread(target=do_convert, daemon=True).start()
