"""File Renamer —— 用正規表達式規則（或雜湊）批次改名：先預覽、擋下衝突、可以復原。

改名的邏輯都在 renamer.py（規則、掃描資料夾、預覽、兩段式套用與復原）；這裡只有畫面。
設定、規則組、上一批改名存在工具旁邊的 data\\（原始碼：tools\\file-renamer\\data\\；exe：exe 旁邊的 data\\）。
"""

import os
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

# 從原始碼執行時讓 import 找得到 repo 的 libs/（打包時由 tool.json 的 pathex 處理）
_LIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs")
if not getattr(sys, "frozen", False) and os.path.isdir(_LIBS):
    sys.path.insert(0, os.path.abspath(_LIBS))

from toolzoo.appdirs import tool_data_dir  # noqa: E402

import renamer  # noqa: E402
from renamer import MODE_CONTENT_HASH, MODE_NAME_HASH, MODE_REGEX, SCOPE_FULL, SCOPE_STEM, Rule  # noqa: E402
from version import __version__  # noqa: E402

MODES = {
    MODE_REGEX: "正規表達式規則",
    MODE_NAME_HASH: "檔名雜湊（SHA-256）",
    MODE_CONTENT_HASH: "檔案內容雜湊（SHA-256）",
}
EXAMPLES = (r"例：\[(1080p|720p)\]\s*  →  （留空，拿掉畫質標籤）　　^IMG_(\d+)  →  照片_$1　　\s+  →  _（空白變底線）"
            "\n取代成可以用 $1、$2 或 \\1、\\2 引用括號裡的內容；規則由上往下依序套用，前一條的結果會交給下一條。")

DATA = tool_data_dir("file-renamer")
SETTINGS_FILE = DATA / "settings.json"
PRESETS_FILE = DATA / "presets.json"
LAST_BATCH_FILE = DATA / "last_batch.json"


def resource_path(*parts):
    """打包後也正確的資料檔路徑（PyInstaller 會把資料解到 sys._MEIPASS）。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


class FileRenamerApp:
    def __init__(self, root, confirm=messagebox.askyesno):
        self.root = root
        self.confirm = confirm            # 測試時換成永遠回答「是」
        self.root.title(f"File Renamer v{__version__}")
        self.root.geometry("1120x720")
        self.root.minsize(900, 560)
        try:
            self.root.iconbitmap(resource_path("assets", "FileRenamer.ico"))
        except tk.TclError:
            pass

        settings = renamer.load_json(SETTINGS_FILE, {})
        self.paths: list[str] = []
        self.rows: list[renamer.PlanRow] = []
        self.item_path: dict[str, str] = {}
        self.rules: list[Rule] = renamer.rules_from_data(settings.get("rules")) or [Rule()]
        self.presets: dict = renamer.load_json(PRESETS_FILE, {})
        self.last_batch: dict = renamer.load_json(LAST_BATCH_FILE, {})
        self.mode = tk.StringVar(value=settings.get("mode", MODE_REGEX))
        self.scope = tk.StringVar(value=settings.get("scope", SCOPE_STEM))
        self.recursive = tk.BooleanVar(value=settings.get("recursive", True))
        self.name_filter = tk.StringVar(value=settings.get("filter", ""))
        self.only_changes = tk.BooleanVar(value=False)
        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.case_var = tk.BooleanVar()
        self.preset_var = tk.StringVar()
        self._loading_editor = False
        self._refresh_job = None

        self._build()
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self._on_drop)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._show_rules(select=0)
        self._mode_changed(save=False)
        self._update_undo()
        self.refresh()

    # ------------------------------------------------------------------ 畫面
    def _build(self):
        top = ttk.Frame(self.root, padding=(10, 10, 10, 0))
        top.pack(fill="x")
        ttk.Button(top, text="＋ 加入檔案", command=self._browse_files).pack(side="left")
        ttk.Button(top, text="＋ 加入資料夾", command=self._browse_folder).pack(side="left", padx=6)
        ttk.Checkbutton(top, text="包含子資料夾", variable=self.recursive,
                        command=self._save_settings).pack(side="left")
        ttk.Label(top, text="資料夾裡只加入").pack(side="left", padx=(14, 4))
        ttk.Entry(top, textvariable=self.name_filter, width=16).pack(side="left")
        ttk.Label(top, text="（例如 *.mp4;*.mkv，空白 = 全部；也可以把檔案或資料夾拖進來）",
                  foreground="#777").pack(side="left", padx=4)
        ttk.Button(top, text="清空", command=self.clear).pack(side="right")
        ttk.Button(top, text="移除選取", command=self._remove_selected).pack(side="right", padx=6)

        opts = ttk.Frame(self.root, padding=(10, 8, 10, 0))
        opts.pack(fill="x")
        ttk.Label(opts, text="改名方式").pack(side="left")
        for key, label in MODES.items():
            ttk.Radiobutton(opts, text=label, value=key, variable=self.mode,
                            command=self._mode_changed).pack(side="left", padx=4)
        ttk.Label(opts, text="套用到").pack(side="left", padx=(24, 4))
        ttk.Radiobutton(opts, text="主檔名（保留副檔名）", value=SCOPE_STEM, variable=self.scope,
                        command=self._changed).pack(side="left")
        ttk.Radiobutton(opts, text="整個檔名", value=SCOPE_FULL, variable=self.scope,
                        command=self._changed).pack(side="left", padx=4)

        # 規則
        self.rule_frame = ttk.LabelFrame(self.root, text="規則（由上往下依序套用）", padding=10)
        self.rule_frame.pack(fill="x", padx=10, pady=8)
        rf = self.rule_frame
        self.rule_tree = ttk.Treeview(rf, columns=("on", "find", "replace", "case"), show="headings",
                                      height=4, selectmode="browse")
        for col, text, width in (("on", "啟用", 50), ("find", "尋找（regex）", 360),
                                 ("replace", "取代成", 260), ("case", "不分大小寫", 80)):
            self.rule_tree.heading(col, text=text)
            self.rule_tree.column(col, width=width, anchor="w", stretch=col in ("find", "replace"))
        self.rule_tree.grid(row=0, column=0, rowspan=5, sticky="nsew")
        self.rule_tree.bind("<<TreeviewSelect>>", self._on_rule_select)
        self.rule_tree.bind("<Double-1>", lambda _e: self.toggle_rule())
        buttons = ttk.Frame(rf)
        buttons.grid(row=0, column=1, rowspan=5, sticky="n", padx=(8, 0))
        for text, cmd in (("＋ 新增規則", self.add_rule), ("↑ 上移", lambda: self.move_rule(-1)),
                          ("↓ 下移", lambda: self.move_rule(1)), ("停用 / 啟用", self.toggle_rule),
                          ("刪除", self.delete_rule)):
            ttk.Button(buttons, text=text, command=cmd, width=12).pack(fill="x", pady=1)

        editor = ttk.Frame(rf)
        editor.grid(row=5, column=0, columnspan=2, sticky="we", pady=(8, 0))
        ttk.Label(editor, text="尋找").pack(side="left")
        self.find_entry = ttk.Entry(editor, textvariable=self.find_var, width=42)
        self.find_entry.pack(side="left", padx=(4, 12), fill="x", expand=True)
        ttk.Label(editor, text="取代成").pack(side="left")
        ttk.Entry(editor, textvariable=self.replace_var, width=30).pack(side="left", padx=(4, 12), fill="x",
                                                                         expand=True)
        ttk.Checkbutton(editor, text="不分大小寫", variable=self.case_var,
                        command=self._editor_changed).pack(side="left")
        for var in (self.find_var, self.replace_var):
            var.trace_add("write", lambda *_: self._editor_changed())

        presets = ttk.Frame(rf)
        presets.grid(row=6, column=0, columnspan=2, sticky="we", pady=(8, 0))
        ttk.Label(presets, text="規則組").pack(side="left")
        self.preset_box = ttk.Combobox(presets, textvariable=self.preset_var, state="readonly", width=24)
        self.preset_box.pack(side="left", padx=4)
        ttk.Button(presets, text="載入", command=self.load_preset).pack(side="left")
        ttk.Button(presets, text="把目前的規則另存為…", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(presets, text="刪除規則組", command=self.delete_preset).pack(side="left")
        self._update_presets()
        ttk.Label(rf, text=EXAMPLES, foreground="#666", justify="left").grid(row=7, column=0, columnspan=2,
                                                                             sticky="w", pady=(8, 0))
        rf.columnconfigure(0, weight=1)

        # 預覽
        self.preview = ttk.Frame(self.root, padding=(10, 0))
        self.preview.pack(fill="both", expand=True)
        bar = ttk.Frame(self.preview)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Label(bar, text="預覽（還沒改任何檔案）").pack(side="left")
        ttk.Checkbutton(bar, text="只顯示會改名的", variable=self.only_changes,
                        command=self._render).pack(side="right")
        table = ttk.Frame(self.preview)
        table.pack(fill="both", expand=True)
        cols = ("status", "old", "new", "hits", "folder")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended")
        for col, text, width in (("status", "狀態", 190), ("old", "原檔名", 290), ("new", "新檔名", 290),
                                 ("hits", "命中", 50), ("folder", "資料夾", 260)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.tag_configure("bad", foreground="#c62828")
        self.tree.tag_configure("same", foreground="#888")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")
        self.summary = ttk.Label(bottom, text="")
        self.summary.pack(side="left")
        self.undo_btn = ttk.Button(bottom, text="↩ 復原上次改名", command=self.undo, state="disabled")
        self.undo_btn.pack(side="right")
        ttk.Button(bottom, text="套用改名", command=self.apply).pack(side="right", padx=6)

    # ------------------------------------------------------------------ 檔案清單
    def add_paths(self, paths):
        known = {os.path.normcase(p) for p in self.paths}
        for p in paths:
            found = renamer.scan_folder(p, self.recursive.get(), self.name_filter.get()) if os.path.isdir(p) else [p]
            for f in found:
                if os.path.isfile(f) and os.path.normcase(f) not in known:
                    self.paths.append(f)
                    known.add(os.path.normcase(f))
        self._save_settings()
        self.refresh()

    def _on_drop(self, event):
        self.add_paths(self.root.tk.splitlist(event.data))

    def _browse_files(self):
        self.add_paths(filedialog.askopenfilenames(title="選擇要改名的檔案"))

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="選擇資料夾（裡面的檔案都會加入）")
        if folder:
            self.add_paths([folder])

    def _remove_selected(self):
        drop = {os.path.normcase(self.item_path[i]) for i in self.tree.selection() if i in self.item_path}
        self.paths = [p for p in self.paths if os.path.normcase(p) not in drop]
        self.refresh()

    def clear(self):
        self.paths = []
        self.refresh()

    # ------------------------------------------------------------------ 規則
    def _show_rules(self, select=None):
        self.rule_tree.delete(*self.rule_tree.get_children())
        for i, rule in enumerate(self.rules):
            self.rule_tree.insert("", "end", iid=str(i), values=("✓" if rule.enabled else "—", rule.find,
                                                                 rule.replace, "✓" if rule.ignore_case else ""))
        if select is not None and self.rules:
            index = max(0, min(select, len(self.rules) - 1))
            self.rule_tree.selection_set(str(index))
            self.rule_tree.see(str(index))
            self._load_editor(index)

    def _selected_rule(self):
        sel = self.rule_tree.selection()
        return int(sel[0]) if sel else None

    def _load_editor(self, index):
        self._loading_editor = True
        rule = self.rules[index]
        self.find_var.set(rule.find)
        self.replace_var.set(rule.replace)
        self.case_var.set(rule.ignore_case)
        self._loading_editor = False

    def _on_rule_select(self, _event=None):
        index = self._selected_rule()
        if index is not None:
            self._load_editor(index)

    def _editor_changed(self):
        if self._loading_editor:
            return
        index = self._selected_rule()
        if index is None:
            return
        rule = self.rules[index]
        rule.find, rule.replace, rule.ignore_case = self.find_var.get(), self.replace_var.get(), self.case_var.get()
        self.rule_tree.item(str(index), values=("✓" if rule.enabled else "—", rule.find, rule.replace,
                                                "✓" if rule.ignore_case else ""))
        self._changed()

    def add_rule(self):
        self.rules.append(Rule())
        self._show_rules(select=len(self.rules) - 1)
        self.find_entry.focus_set()
        self._changed()

    def move_rule(self, delta):
        index = self._selected_rule()
        if index is None or not 0 <= index + delta < len(self.rules):
            return
        self.rules[index], self.rules[index + delta] = self.rules[index + delta], self.rules[index]
        self._show_rules(select=index + delta)
        self._changed()

    def toggle_rule(self):
        index = self._selected_rule()
        if index is not None:
            self.rules[index].enabled = not self.rules[index].enabled
            self._show_rules(select=index)
            self._changed()

    def delete_rule(self):
        index = self._selected_rule()
        if index is None:
            return
        del self.rules[index]
        if not self.rules:
            self.rules = [Rule()]
        self._show_rules(select=index)
        self._changed()

    # ------------------------------------------------------------------ 規則組
    def _update_presets(self):
        names = sorted(self.presets)
        self.preset_box.configure(values=names)
        if self.preset_var.get() not in names:
            self.preset_var.set(names[0] if names else "")

    def load_preset(self):
        name = self.preset_var.get()
        if name in self.presets:
            self.rules = renamer.rules_from_data(self.presets[name]) or [Rule()]
            self._show_rules(select=0)
            self._changed()

    def save_preset(self, name=None):
        name = name or simpledialog.askstring("另存規則組", "規則組的名稱：", parent=self.root)
        if not name or not name.strip():
            return
        self.presets[name.strip()] = renamer.rules_to_data([r for r in self.rules if r.find])
        renamer.save_json(PRESETS_FILE, self.presets)
        self.preset_var.set(name.strip())
        self._update_presets()

    def delete_preset(self):
        name = self.preset_var.get()
        if name in self.presets and self.confirm("刪除規則組", f"要刪除規則組「{name}」嗎？"):
            del self.presets[name]
            renamer.save_json(PRESETS_FILE, self.presets)
            self._update_presets()

    # ------------------------------------------------------------------ 預覽
    def _mode_changed(self, save=True):
        regex = self.mode.get() == MODE_REGEX
        if regex and not self.rule_frame.winfo_ismapped():
            self.rule_frame.pack(fill="x", padx=10, pady=8, before=self.preview)
        elif not regex:
            self.rule_frame.pack_forget()
        if save:
            self._changed()

    def _changed(self):
        self._save_settings()
        if self._refresh_job:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(150, self.refresh)   # 打字時不要每個字都重算

    def refresh(self):
        self._refresh_job = None
        if self.mode.get() == MODE_CONTENT_HASH and len(self.paths) > 200:
            self.summary.configure(text="計算內容雜湊中…")
            self.root.update_idletasks()
        self.rows = renamer.plan(self.paths, self.mode.get(), self.rules, self.scope.get())
        self._render()

    def _render(self):
        self.tree.delete(*self.tree.get_children())
        self.item_path = {}
        for row in self.rows:
            if self.only_changes.get() and not row.ok:
                continue
            quiet = row.status in (renamer.STATUS_SAME, renamer.STATUS_NO_MATCH, "還沒有規則")
            tag = "" if row.ok else ("same" if quiet else "bad")
            item = self.tree.insert("", "end", values=(row.status or "✓ 會改名", os.path.basename(row.path),
                                                       row.new_name, row.hits or "", os.path.dirname(row.path)),
                                    tags=(tag,))
            self.item_path[item] = row.path
        ok = sum(1 for r in self.rows if r.ok)
        bad = sum(1 for r in self.rows if not r.ok and r.status not in
                  (renamer.STATUS_SAME, renamer.STATUS_NO_MATCH, "還沒有規則"))
        text = f"共 {len(self.rows)} 個檔案：{ok} 個會改名"
        self.summary.configure(text=text + (f"、{bad} 個有問題（紅字）" if bad else ""))

    # ------------------------------------------------------------------ 套用與復原
    def apply(self):
        self.refresh()
        todo = [r for r in self.rows if r.ok]
        if not todo:
            messagebox.showinfo("沒有要改的", "目前沒有可以套用的改名（看「狀態」欄）。")
            return
        if not self.confirm("確認改名", f"要把 {len(todo)} 個檔案改名嗎？（之後可以按「復原上次改名」改回來）"):
            return
        try:
            pairs = renamer.apply(self.rows)
        except renamer.RenameError as exc:
            messagebox.showerror("改名失敗", str(exc))
            self.refresh()
            return
        self.last_batch = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "pairs": pairs}
        renamer.save_json(LAST_BATCH_FILE, self.last_batch)
        moved = {os.path.normcase(old): new for old, new in pairs}
        self.paths = [moved.get(os.path.normcase(p), p) for p in self.paths]
        self._update_undo()
        self.refresh()

    def undo(self):
        pairs = [tuple(p) for p in self.last_batch.get("pairs", [])]
        if not pairs:
            return
        try:
            renamer.undo(pairs)
        except renamer.RenameError as exc:
            messagebox.showerror("無法復原", str(exc))
            return
        back = {os.path.normcase(new): old for old, new in pairs}
        self.paths = [back.get(os.path.normcase(p), p) for p in self.paths]
        self.last_batch = {}
        try:
            LAST_BATCH_FILE.unlink()
        except OSError:
            pass
        self._update_undo()
        self.refresh()

    def _update_undo(self):
        pairs = self.last_batch.get("pairs", [])
        if pairs:
            self.undo_btn.configure(state="normal",
                                    text=f"↩ 復原上次改名（{self.last_batch.get('time', '')}，{len(pairs)} 個）")
        else:
            self.undo_btn.configure(state="disabled", text="↩ 復原上次改名")

    # ------------------------------------------------------------------ 設定
    def _save_settings(self):
        renamer.save_json(SETTINGS_FILE, {
            "rules": renamer.rules_to_data(self.rules), "mode": self.mode.get(), "scope": self.scope.get(),
            "recursive": self.recursive.get(), "filter": self.name_filter.get(),
        })

    def close(self):
        self._save_settings()
        self.root.destroy()


def main():
    root = TkinterDnD.Tk()   # 拖放要用 TkinterDnD 的視窗
    FileRenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
