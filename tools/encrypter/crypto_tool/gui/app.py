"""CryptoTool Pro 主視窗（新介面）：加密／解密／金鑰／關於。

這裡只管畫面：排元件、把按鈕接到 gui/logic.py、把結果顯示出來。
檢查、檔名、錯誤訊息、實際加解密都在 logic.py（有單元測試）；文案在 texts.py；
外觀規格在 docs/ui-spec.md。舊的四個分頁在 legacy_app.py，從「關於」分頁打開。

規則：會花時間的事（加解密、產生金鑰、找 gpg、算 scrypt）一律在背景執行緒做，
結果用 ``app.post`` 丟回主執行緒；背景執行緒不碰任何元件。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog

import ttkbootstrap as ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

from . import logic
from . import texts as T
from .theme import (
    FONT_BUTTON, FONT_DROP, FONT_HEADING, FONT_UI, FONT_UI_BOLD, FONT_UI_SMALL, GAP,
    PAD_X, PALETTE, THEME_DARK, THEME_LIGHT, WINDOW_MIN, WINDOW_SIZE,
)

try:
    from _version import __version__   # crypto_tool/ 在 sys.path 上（見 GUI__Encrypter.py）
except ImportError:  # 以 crypto_tool.gui.app 載入時（測試）
    from .._version import __version__

APP_TITLE = f"{T.APP_NAME} v{__version__}"
WRAP = WINDOW_MIN[0] - 2 * PAD_X - 40   # 長段文字的換行寬度
POLL_MS = 80
SHORT_LIST = 3                           # 清單顯示幾項，其餘用「…等 N 項」


def _short(items) -> str:
    names = [str(i).replace("\\", "/").rsplit("/", 1)[-1] if not str(i).startswith("age1") else
             str(i)[:12] + "…" for i in items]
    text = "、".join(names[:SHORT_LIST])
    return text + (f"…等 {len(names)} 項" if len(names) > SHORT_LIST else "")


class ResultBox:
    """結果區：一行粗體標題（顏色看成功或失敗）加幾行說明。"""

    def __init__(self, parent):
        self.frame = ttk.Frame(parent)
        self._title = ttk.Label(self.frame, text="", font=FONT_UI_BOLD)
        self._title.pack(anchor="w")
        self._body = ttk.Label(self.frame, text="", font=FONT_UI, wraplength=WRAP,
                               justify="left")
        self._body.pack(anchor="w", pady=(2, 0))

    def show(self, message: logic.Message) -> None:
        self._title.configure(text=message.title, bootstyle=message.kind)
        self._body.configure(text="\n".join(message.lines))

    def clear(self) -> None:
        self._title.configure(text="")
        self._body.configure(text="")


def _passphrase_row(parent, row: int, label: str, var, show_var=None, toggle=None):
    ttk.Label(parent, text=label, font=FONT_UI).grid(row=row, column=0, sticky="w", padx=(0, GAP), pady=(4, 0))
    entry = ttk.Entry(parent, textvariable=var, show="•", font=FONT_UI)
    entry.grid(row=row, column=1, sticky="ew", pady=(4, 0))
    if show_var is not None:
        ttk.Checkbutton(parent, text=T.SHOW_PASSPHRASE, variable=show_var,
                        command=toggle).grid(row=row, column=2, padx=(GAP, 0), pady=(4, 0))
    return entry


class Scrolled:
    """可以上下捲動的分頁內容：視窗比內容矮時（小螢幕、字放大）也看得到每個元件。"""

    def __init__(self, notebook):
        self.page = ttk.Frame(notebook)
        self.canvas = tk.Canvas(self.page, highlightthickness=0, borderwidth=0)
        self.bar = ttk.Scrollbar(self.page, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, padding=(PAD_X, GAP))
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")


class JobTab:
    """「加密」與「解密」分頁共用的部分：① 選東西、存哪裡、進階、按鈕、進度、結果。"""

    def __init__(self, app: "CryptoToolApp", notebook, action: str):
        self.app = app
        self.action = action
        self.busy = False
        self._auto_output = ""
        self.scroll = Scrolled(notebook)
        self.page, self.frame = self.scroll.page, self.scroll.inner
        self.input_var = tk.StringVar()
        self.extra_inputs: list[str] = []
        self.input_info_var = tk.StringVar(value=T.NOTHING_CHOSEN)
        self.output_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.progress_var = tk.IntVar(value=0)
        self.progress_text_var = tk.StringVar()

    # ── ① 輸入 ────────────────────────────────────────────────────────

    def _build_input(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_INPUT[self.action], padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        self.drop = tk.Label(box, text=T.DROP_HINT[self.action], font=FONT_DROP,
                             height=2, relief="flat", cursor="hand2")
        self.drop.pack(fill="x")
        self.drop.bind("<Button-1>", lambda _e: self._pick_file())
        self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind("<<Drop>>", self._on_drop)
        self.drop.dnd_bind("<<DragEnter>>", lambda _e: self._paint_drop(active=True))
        self.drop.dnd_bind("<<DragLeave>>", lambda _e: self._paint_drop(active=False))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=(GAP, 0))
        ttk.Button(row, text=T.PICK_FILE, bootstyle="secondary-outline",
                   command=self._pick_file).pack(side="left")
        if self.action == logic.ENCRYPT:
            ttk.Button(row, text=T.PICK_FOLDER, bootstyle="secondary-outline",
                       command=self._pick_folder).pack(side="left", padx=(6, 0))
            ttk.Button(row, text=T.ADD_MORE, bootstyle="secondary-outline",
                       command=self._add_more).pack(side="left", padx=(6, 0))
        ttk.Entry(row, textvariable=self.input_var, font=FONT_UI).pack(
            side="left", fill="x", expand=True, padx=(GAP, 0))
        self.input_info = ttk.Label(box, textvariable=self.input_info_var, font=FONT_UI_SMALL,
                                    bootstyle="secondary", wraplength=WRAP, justify="left")
        self.input_info.pack(anchor="w", pady=(4, 0))
        self.legacy_button = ttk.Button(box, text=T.LEGACY_OPEN_BUTTON, bootstyle="warning-outline",
                                        command=self.app.open_legacy)
        self.input_var.trace_add("write", lambda *_: self._on_input_changed())

    def inputs(self) -> list[str]:
        first = self.input_var.get().strip()
        return ([first] if first else []) + list(self.extra_inputs)

    def _paint_drop(self, active: bool = False) -> None:
        colors = PALETTE[self.app.theme]
        self.drop.configure(bg=colors["drop_active" if active else "drop_bg"],
                            fg=colors["drop_fg"])

    def _on_drop(self, event):
        paths = logic.dropped(self.app.root.tk.splitlist(event.data))
        self._paint_drop(active=False)
        if paths:
            if self.action == logic.ENCRYPT:
                self.extra_inputs = paths[1:]
            self.input_var.set(paths[0])
        return getattr(event, "action", None)

    def _pick_file(self) -> None:
        if self.action == logic.DECRYPT:
            types = [("age／OpenPGP", "*.age *.gpg *.asc *.pgp *.isd2"), ("*", "*.*")]
        else:
            types = [("*", "*.*")]
        path = filedialog.askopenfilename(parent=self.app.root, filetypes=types)
        if path:
            self.extra_inputs = []
            self.input_var.set(path)

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(parent=self.app.root)
        if path:
            self.extra_inputs = []
            self.input_var.set(path)

    def _add_more(self) -> None:
        path = filedialog.askopenfilename(parent=self.app.root)
        if not path:
            return
        if not self.input_var.get().strip():
            self.input_var.set(path)
        elif path not in self.inputs():
            self.extra_inputs.append(path)
            self._on_input_changed()

    def _on_input_changed(self) -> None:  # 子類別補上細節
        raise NotImplementedError

    # ── 輸出 ──────────────────────────────────────────────────────────

    def _build_output(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_OUTPUT[self.action], padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        ttk.Entry(box, textvariable=self.output_var, font=FONT_UI).pack(
            side="left", fill="x", expand=True)
        ttk.Button(box, text=T.SAVE_AS, bootstyle="secondary-outline",
                   command=self._pick_output).pack(side="left", padx=(6, 0))

    def _suggest(self) -> str:
        raise NotImplementedError

    def _refresh_suggestion(self, force: bool = False) -> None:
        """輸出欄還是自動填的（或空的）才更新，不蓋掉使用者自己改過的位置。"""
        current = self.output_var.get().strip()
        if not force and current and current != self._auto_output:
            return
        self._auto_output = self._suggest()
        self.output_var.set(self._auto_output)

    def _pick_output(self) -> None:
        options = {"parent": self.app.root}
        current = self.output_var.get().strip()
        if current:
            options["initialfile"] = current.replace("\\", "/").rsplit("/", 1)[-1]
        path = filedialog.asksaveasfilename(**options)
        if path:
            self.output_var.set(path)

    # ── 進階 ──────────────────────────────────────────────────────────

    def _build_advanced(self, extra) -> None:
        self.advanced_open = False
        self.advanced_toggle = ttk.Button(self.frame, text=T.ADVANCED_SHOW, bootstyle="link",
                                          command=self._toggle_advanced)
        self.advanced_toggle.pack(anchor="w")
        self.advanced = ttk.Frame(self.frame, padding=(GAP, 0, 0, GAP))
        for text, var in extra:
            ttk.Checkbutton(self.advanced, text=text, variable=var).pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(self.advanced, text=T.OVERWRITE, variable=self.overwrite_var).pack(anchor="w")

    def _toggle_advanced(self) -> None:
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced.pack(fill="x", after=self.advanced_toggle)
            self.advanced_toggle.configure(text=T.ADVANCED_HIDE)
        else:
            self.advanced.pack_forget()
            self.advanced_toggle.configure(text=T.ADVANCED_SHOW)

    # ── 執行 ──────────────────────────────────────────────────────────

    def _build_action(self) -> None:
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(GAP, 0))
        self.go = ttk.Button(row, text=T.GO[self.action], width=12, command=self._start,
                             bootstyle="primary" if self.action == logic.ENCRYPT else "success")
        self.go.pack(side="left")
        self.bar = ttk.Progressbar(row, variable=self.progress_var, maximum=100,
                                   mode="determinate", bootstyle="info-striped")
        self.bar.pack(side="left", fill="x", expand=True, padx=(GAP, GAP))
        ttk.Label(row, textvariable=self.progress_text_var, font=FONT_UI_SMALL,
                  bootstyle="secondary").pack(side="left")
        self.result = ResultBox(self.frame)
        self.result.frame.pack(fill="x", pady=(GAP, 0))

    def form(self) -> logic.JobForm:
        raise NotImplementedError

    def _validate(self, form: logic.JobForm) -> list[str]:
        return logic.validate(form)

    def _start(self) -> None:
        if self.busy:
            return
        form = self.form()
        problems = self._validate(form)
        if problems:
            self.result.show(logic.Message("warning", T.PROBLEMS_TITLE, problems))
            return
        self._set_busy(True)
        self.result.clear()
        self.progress_var.set(0)
        self.progress_text_var.set("")
        self.app.set_status(T.STATUS_WORKING[self.action])
        threading.Thread(target=self._work, args=(form,), daemon=True).start()

    def _work(self, form: logic.JobForm) -> None:
        """背景執行緒：不直接碰任何元件，只把結果丟回主執行緒。"""
        message = logic.run_job_safely(
            form, progress=lambda done, total: self.app.post(self._on_progress, done, total))
        self.app.post(self._on_done, message)

    def _on_progress(self, done: int, total: int) -> None:
        percent, text = logic.progress_view(done, total)
        self.progress_var.set(percent)
        self.progress_text_var.set(text)

    def _clear_secrets(self) -> None:
        raise NotImplementedError

    def _on_done(self, message: logic.Message) -> None:
        self._set_busy(False)
        self.result.show(message)
        ok = message.kind in ("success", "warning") and not message.code
        if ok:
            self.progress_var.set(100)
            self._clear_secrets()
        else:
            self.progress_var.set(0)
            self.progress_text_var.set("")
        self.app.set_status((T.STATUS_DONE if ok else T.STATUS_FAILED)[self.action])

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.go.configure(state="disabled" if busy else "normal")


class EncryptTab(JobTab):
    """① 選東西 ② 選格式 ③ 誰可以打開 ④ 存哪裡 → 加密。"""

    def __init__(self, app: "CryptoToolApp", notebook):
        super().__init__(app, notebook, logic.ENCRYPT)
        self.mode_var = tk.StringVar(value=logic.MODE_AGE)
        self.mode_note_var = tk.StringVar(value=T.MODE_NOTE[logic.MODE_AGE])
        self.use_pass_var = tk.BooleanVar(value=False)
        self.pass_var = tk.StringVar()
        self.confirm_var = tk.StringVar()
        self.show_pass_var = tk.BooleanVar(value=False)
        self.strength_var = tk.StringVar()
        self.use_keys_var = tk.BooleanVar(value=True)
        self.recipient_entry_var = tk.StringVar()
        self.recipient_label_var = tk.StringVar(value=T.RECIPIENTS_NONE)
        self.recipient_hint_var = tk.StringVar(value=T.RECIPIENT_HINT[logic.MODE_AGE])
        self.recipients: list[str] = []
        self.with_master_var = tk.BooleanVar(value=bool(logic.master_for(logic.MODE_AGE)))
        self.master_info_var = tk.StringVar()
        self.armor_var = tk.BooleanVar(value=False)

        self._build_input()
        self._build_mode()
        self._build_lock()
        self._build_output()
        self._build_advanced([(T.ARMOR, self.armor_var)])
        self._build_action()

        self.mode_var.trace_add("write", lambda *_: self._on_mode_changed())
        self.pass_var.trace_add("write", lambda *_: self._on_passphrase_changed())
        self.use_pass_var.trace_add("write", lambda *_: self._show_lock())
        self.use_keys_var.trace_add("write", lambda *_: self._show_lock())
        self.armor_var.trace_add("write", lambda *_: self._refresh_suggestion())
        self._refresh_master()
        self._show_lock()

    def _on_input_changed(self) -> None:
        self.result.clear()
        self.input_info_var.set(logic.describe_inputs(self.inputs()))
        self._refresh_suggestion(force=True)

    def _suggest(self) -> str:
        return logic.suggest_output(logic.ENCRYPT, self.inputs(), mode=self.mode_var.get(),
                                    armor=self.armor_var.get())

    # ── ② 格式 ────────────────────────────────────────────────────────

    def _build_mode(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_MODE, padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Radiobutton(row, text=T.MODE_AGE, variable=self.mode_var,
                        value=logic.MODE_AGE).pack(side="left")
        ttk.Radiobutton(row, text=T.MODE_PGP, variable=self.mode_var,
                        value=logic.MODE_PGP).pack(side="left", padx=(GAP * 2, 0))
        self.mode_note = ttk.Label(box, textvariable=self.mode_note_var, font=FONT_UI_SMALL,
                                   bootstyle="secondary", wraplength=WRAP, justify="left")
        self.mode_note.pack(anchor="w", pady=(4, 0))

    def _on_mode_changed(self) -> None:
        mode = self.mode_var.get()
        note = T.MODE_NOTE[mode]
        if mode == logic.MODE_PGP and self.app.gpg_ok is False:
            note = T.PGP_UNAVAILABLE
        self.mode_note_var.set(note)
        self.recipient_hint_var.set(T.RECIPIENT_HINT[mode])
        self.recipient_label.configure(text=T.RECIPIENT_ENTRY_LABEL[mode])
        self.recipients = []
        self._show_recipients()
        self._refresh_master(reset=True)
        self._refresh_suggestion()

    # ── ③ 誰可以打開 ──────────────────────────────────────────────────

    def _build_lock(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_KEY[self.action], padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        self.pass_check = ttk.Checkbutton(box, text=T.USE_PASSPHRASE, variable=self.use_pass_var)
        self.pass_check.pack(anchor="w")
        self.pass_frame = ttk.Frame(box, padding=(GAP * 2, 0, 0, 0))
        self.pass_frame.columnconfigure(1, weight=1)
        self.pass_entry = _passphrase_row(self.pass_frame, 0, T.PASSPHRASE_LABEL, self.pass_var,
                                          self.show_pass_var, self._toggle_show)
        self.confirm_entry = _passphrase_row(self.pass_frame, 1, T.PASSPHRASE_CONFIRM_LABEL, self.confirm_var)
        self.strength_label = ttk.Label(self.pass_frame, textvariable=self.strength_var, font=FONT_UI_SMALL)
        self.strength_label.grid(row=2, column=1, sticky="w", pady=(4, 0))

        self.keys_check = ttk.Checkbutton(box, text=T.USE_KEYS, variable=self.use_keys_var)
        self.keys_check.pack(anchor="w", pady=(GAP, 0))
        self.keys_frame = ttk.Frame(box, padding=(GAP * 2, 0, 0, 0))
        row = ttk.Frame(self.keys_frame)
        row.pack(fill="x")
        self.recipient_label = ttk.Label(row, text=T.RECIPIENT_ENTRY_LABEL[logic.MODE_AGE], font=FONT_UI)
        self.recipient_label.pack(side="left", padx=(0, GAP))
        entry = ttk.Entry(row, textvariable=self.recipient_entry_var, font=FONT_UI)
        entry.pack(side="left", fill="x", expand=True)
        entry.drop_target_register(DND_FILES)
        entry.dnd_bind("<<Drop>>", self._on_recipient_drop)
        ttk.Button(row, text=T.RECIPIENT_ADD, bootstyle="secondary-outline",
                   command=self._add_recipient_text).pack(side="left", padx=(6, 0))
        ttk.Button(row, text=T.RECIPIENT_ADD_FILE, bootstyle="secondary-outline",
                   command=self._add_recipient_file).pack(side="left", padx=(6, 0))
        ttk.Button(row, text=T.CLEAR, bootstyle="secondary-outline",
                   command=self._clear_recipients).pack(side="left", padx=(6, 0))
        self.recipients_shown = ttk.Label(self.keys_frame, textvariable=self.recipient_label_var,
                                          font=FONT_UI_SMALL, wraplength=WRAP, justify="left")
        self.recipients_shown.pack(anchor="w", pady=(4, 0))
        ttk.Label(self.keys_frame, textvariable=self.recipient_hint_var, font=FONT_UI_SMALL,
                  bootstyle="secondary", wraplength=WRAP, justify="left").pack(anchor="w", pady=(2, 0))
        master_row = ttk.Frame(self.keys_frame)
        master_row.pack(fill="x", pady=(6, 0))
        self.master_check = ttk.Checkbutton(master_row, text=T.WITH_MASTER, variable=self.with_master_var)
        self.master_check.pack(side="left")
        ttk.Label(master_row, textvariable=self.master_info_var, font=FONT_UI_SMALL,
                  bootstyle="secondary").pack(side="left", padx=(6, 0))

    def _show_lock(self) -> None:
        self.pass_frame.pack_forget()
        self.keys_frame.pack_forget()
        if self.use_pass_var.get():
            self.pass_frame.pack(fill="x", after=self.pass_check)
        if self.use_keys_var.get():
            self.keys_frame.pack(fill="x", after=self.keys_check)

    def _refresh_master(self, reset: bool = False) -> None:
        """萬用鎖的說明與預設勾選：有設定就預設勾。"""
        value = logic.master_summary(self.mode_var.get())
        if value:
            self.master_info_var.set(T.MASTER_IS.format(value=value))
        else:
            self.master_info_var.set(T.MASTER_NOT_SET)
        self.master_check.configure(state="normal" if value else "disabled")
        if reset or not value:
            self.with_master_var.set(bool(value))

    def _toggle_show(self) -> None:
        show = "" if self.show_pass_var.get() else "•"
        self.pass_entry.configure(show=show)
        self.confirm_entry.configure(show=show)

    def _on_passphrase_changed(self) -> None:
        level, label = logic.passphrase_strength(self.pass_var.get())
        self.strength_var.set(label)
        self.strength_label.configure(bootstyle=("secondary", "danger", "warning", "success")[level])

    def _add_items(self, items) -> None:
        for item in items:
            if item and item not in self.recipients:
                self.recipients.append(item)
        self._show_recipients()

    def _show_recipients(self) -> None:
        if self.recipients:
            self.recipient_label_var.set(T.RECIPIENTS_LIST.format(n=len(self.recipients),
                                                                   items=_short(self.recipients)))
        else:
            self.recipient_label_var.set(T.RECIPIENTS_NONE)

    def _add_recipient_text(self) -> None:
        text = self.recipient_entry_var.get()
        if self.mode_var.get() == logic.MODE_AGE:
            self._add_items(logic.split_recipients(text))
        elif text.strip():
            self._add_items([text.strip()])
        self.recipient_entry_var.set("")

    def _add_recipient_file(self) -> None:
        types = [("age", "*.txt *.env *.key *.pub"), ("*", "*.*")] if self.mode_var.get() == logic.MODE_AGE \
            else [("OpenPGP", "*.asc *.gpg *.pgp"), ("*", "*.*")]
        path = filedialog.askopenfilename(parent=self.app.root, filetypes=types)
        if path:
            self._add_items([path])

    def _on_recipient_drop(self, event):
        self._add_items(logic.dropped(self.app.root.tk.splitlist(event.data)))
        return getattr(event, "action", None)

    def _clear_recipients(self) -> None:
        self.recipients = []
        self._show_recipients()

    def form(self) -> logic.JobForm:
        pending = self.recipient_entry_var.get().strip()
        if pending:   # 貼了公鑰但忘了按「加入」：照樣算進去
            self._add_recipient_text()
        return logic.JobForm(
            action=logic.ENCRYPT, inputs=self.inputs(), output_path=self.output_var.get().strip(),
            mode=self.mode_var.get(), use_passphrase=self.use_pass_var.get(),
            passphrase=self.pass_var.get(), passphrase_confirm=self.confirm_var.get(),
            use_keys=self.use_keys_var.get(), recipients=list(self.recipients),
            with_master=self.with_master_var.get(), armor=self.armor_var.get(),
            overwrite=self.overwrite_var.get(),
        )

    def _validate(self, form: logic.JobForm) -> list[str]:
        return logic.validate(form, gpg=self.app.gpg_ok)

    def _clear_secrets(self) -> None:
        self.pass_var.set("")
        self.confirm_var.set("")


class DecryptTab(JobTab):
    """① 選檔案 ② 用什麼開 ③ 存哪裡 → 解密。"""

    def __init__(self, app: "CryptoToolApp", notebook):
        super().__init__(app, notebook, logic.DECRYPT)
        self.key_files: list[str] = []
        self.key_entry_var = tk.StringVar()
        self.key_label_var = tk.StringVar()
        self.pass_var = tk.StringVar()
        self.key_pass_var = tk.StringVar()
        self.show_pass_var = tk.BooleanVar(value=False)
        self.all_layers_var = tk.BooleanVar(value=False)
        self.keep_tar_var = tk.BooleanVar(value=False)

        self._build_input()
        self._build_keys()
        self._build_output()
        self._build_advanced([(T.KEEP_TAR, self.keep_tar_var)])
        self._build_action()
        self.keep_tar_var.trace_add("write", lambda *_: self._refresh_suggestion())
        self.refresh_default_keys()

    def refresh_default_keys(self) -> None:
        """把 .env 設定的預設鑰匙檔放進清單（已經在清單裡的不重複）。"""
        for path in logic.default_key_files():
            if path not in self.key_files:
                self.key_files.append(path)
        self._show_key_files()

    def _on_input_changed(self) -> None:
        path = self.input_var.get().strip()
        self.legacy_button.pack_forget()
        self.result.clear()
        if not path:
            self.input_info_var.set(T.NOTHING_CHOSEN)
        else:
            text, info, problem = logic.inspect_sealed(path)
            self.input_info_var.set(text)
            if problem is not None:
                self.result.show(problem)
            if info is not None and info.get("format") == "isd-legacy":
                self.legacy_button.pack(anchor="w", pady=(6, 0))
        self._refresh_suggestion(force=True)

    def _suggest(self) -> str:
        return logic.suggest_output(logic.DECRYPT, self.inputs()[:1], self.keep_tar_var.get())

    def _build_keys(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_KEY[self.action], padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text=T.KEYFILES_LABEL, font=FONT_UI).pack(side="left", padx=(0, GAP))
        entry = ttk.Entry(row, textvariable=self.key_entry_var, font=FONT_UI)
        entry.pack(side="left", fill="x", expand=True)
        entry.drop_target_register(DND_FILES)
        entry.dnd_bind("<<Drop>>", self._on_keyfile_drop)
        ttk.Button(row, text=T.RECIPIENT_ADD, bootstyle="secondary-outline",
                   command=self._add_typed_key).pack(side="left", padx=(6, 0))
        ttk.Button(row, text=T.RECIPIENT_ADD_FILE, bootstyle="secondary-outline",
                   command=self._pick_keyfile).pack(side="left", padx=(6, 0))
        ttk.Button(row, text=T.CLEAR, bootstyle="secondary-outline",
                   command=self._clear_keys).pack(side="left", padx=(6, 0))
        ttk.Label(box, textvariable=self.key_label_var, font=FONT_UI_SMALL, wraplength=WRAP,
                  justify="left").pack(anchor="w", pady=(4, 0))
        ttk.Label(box, text=T.KEYFILES_HINT, font=FONT_UI_SMALL, bootstyle="secondary",
                  wraplength=WRAP, justify="left").pack(anchor="w", pady=(2, 0))
        grid = ttk.Frame(box)
        grid.pack(fill="x", pady=(GAP, 0))
        grid.columnconfigure(1, weight=1)
        self.pass_entry = _passphrase_row(grid, 0, T.FILE_PASSPHRASE_LABEL, self.pass_var,
                                          self.show_pass_var, self._toggle_show)
        self.key_pass_entry = _passphrase_row(grid, 1, T.KEY_PASSPHRASE_LABEL, self.key_pass_var)
        ttk.Label(box, text=T.DECRYPT_PASSPHRASE_HINT, font=FONT_UI_SMALL, bootstyle="secondary",
                  wraplength=WRAP, justify="left").pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(box, text=T.ALL_LAYERS, variable=self.all_layers_var).pack(anchor="w", pady=(GAP, 0))

    def _show_key_files(self) -> None:
        self.key_label_var.set(T.RECIPIENTS_LIST.format(n=len(self.key_files), items=_short(self.key_files))
                               if self.key_files else T.RECIPIENTS_NONE)

    def _add_key(self, path: str) -> None:
        if path and path not in self.key_files:
            self.key_files.append(path)
        self._show_key_files()

    def _add_typed_key(self) -> None:
        self._add_key(self.key_entry_var.get().strip())
        self.key_entry_var.set("")

    def _pick_keyfile(self) -> None:
        path = filedialog.askopenfilename(parent=self.app.root)
        if path:
            self._add_key(path)

    def _on_keyfile_drop(self, event):
        for path in logic.dropped(self.app.root.tk.splitlist(event.data)):
            self._add_key(path)
        return getattr(event, "action", None)

    def _clear_keys(self) -> None:
        self.key_files = []
        self._show_key_files()

    def _toggle_show(self) -> None:
        show = "" if self.show_pass_var.get() else "•"
        self.pass_entry.configure(show=show)
        self.key_pass_entry.configure(show=show)

    def form(self) -> logic.JobForm:
        if self.key_entry_var.get().strip():
            self._add_typed_key()
        return logic.JobForm(
            action=logic.DECRYPT, inputs=self.inputs()[:1], output_path=self.output_var.get().strip(),
            key_files=list(self.key_files), passphrase=self.pass_var.get(),
            key_passphrase=self.key_pass_var.get(), all_layers=self.all_layers_var.get(),
            keep_tar=self.keep_tar_var.get(), overwrite=self.overwrite_var.get(),
        )

    def _clear_secrets(self) -> None:
        self.pass_var.set("")
        self.key_pass_var.set("")


class KeysTab:
    """「金鑰」分頁：產生 age 身分檔、產生 PGP 金鑰對、設定萬用鎖、檢查鑰匙檔。"""

    def __init__(self, app: "CryptoToolApp", notebook):
        self.app = app
        self.busy = False
        self.scroll = Scrolled(notebook)
        self.page, self.frame = self.scroll.page, self.scroll.inner
        self.age_path_var = tk.StringVar()
        self.age_pass_var = tk.StringVar()
        self.age_confirm_var = tk.StringVar()
        self.age_default_var = tk.BooleanVar(value=False)
        self.pgp_prefix_var = tk.StringVar()
        self.pgp_name_var = tk.StringVar()
        self.pgp_pass_var = tk.StringVar()
        self.pgp_confirm_var = tk.StringVar()
        self.master_age_var = tk.StringVar(value=logic.master_for(logic.MODE_AGE) or "")
        self.master_pgp_var = tk.StringVar(value=logic.master_for(logic.MODE_PGP) or "")
        self.check_path_var = tk.StringVar()

        ttk.Label(self.frame, text=T.KEYS_INTRO, font=FONT_UI, wraplength=WRAP,
                  justify="left").pack(anchor="w", pady=(0, GAP))
        self._build_age()
        self._build_pgp()
        self._build_master()
        self._build_check()

    def _path_row(self, parent, label, var, command):
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text=label, font=FONT_UI).pack(side="left", padx=(0, GAP))
        ttk.Entry(row, textvariable=var, font=FONT_UI).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=T.SAVE_AS, bootstyle="secondary-outline",
                   command=command).pack(side="left", padx=(6, 0))
        return row

    def _build_age(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.KEYS_AGE_TITLE, padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        self._path_row(box, T.KEYS_AGE_PATH, self.age_path_var, self._pick_age_path)
        grid = ttk.Frame(box)
        grid.pack(fill="x", pady=(4, 0))
        grid.columnconfigure(1, weight=1)
        ttk.Label(grid, text=T.KEYS_PROTECT, font=FONT_UI_SMALL, bootstyle="secondary").grid(
            row=0, column=0, columnspan=2, sticky="w")
        _passphrase_row(grid, 1, T.PASSPHRASE_LABEL, self.age_pass_var)
        _passphrase_row(grid, 2, T.PASSPHRASE_CONFIRM_LABEL, self.age_confirm_var)
        ttk.Checkbutton(box, text=T.KEYS_SET_DEFAULT, variable=self.age_default_var).pack(anchor="w", pady=(4, 0))
        self.age_button = ttk.Button(box, text=T.KEYS_AGE_BUTTON, bootstyle="primary", command=self._create_age)
        self.age_button.pack(anchor="w", pady=(GAP, 0))
        self.age_result = ResultBox(box)
        self.age_result.frame.pack(fill="x", pady=(GAP, 0))

    def _build_pgp(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.KEYS_PGP_TITLE, padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        self._path_row(box, T.KEYS_PGP_PREFIX, self.pgp_prefix_var, self._pick_pgp_prefix)
        grid = ttk.Frame(box)
        grid.pack(fill="x", pady=(4, 0))
        grid.columnconfigure(1, weight=1)
        ttk.Label(grid, text=T.KEYS_PGP_NAME, font=FONT_UI).grid(row=0, column=0, sticky="w", padx=(0, GAP))
        ttk.Entry(grid, textvariable=self.pgp_name_var, font=FONT_UI).grid(row=0, column=1, sticky="ew")
        _passphrase_row(grid, 1, T.PASSPHRASE_LABEL, self.pgp_pass_var)
        _passphrase_row(grid, 2, T.PASSPHRASE_CONFIRM_LABEL, self.pgp_confirm_var)
        self.pgp_button = ttk.Button(box, text=T.KEYS_PGP_BUTTON, bootstyle="primary", command=self._create_pgp)
        self.pgp_button.pack(anchor="w", pady=(GAP, 0))
        self.pgp_result = ResultBox(box)
        self.pgp_result.frame.pack(fill="x", pady=(GAP, 0))

    def _build_master(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.KEYS_MASTER_TITLE, padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        ttk.Label(box, text=T.KEYS_MASTER_INTRO, font=FONT_UI_SMALL, bootstyle="secondary",
                  wraplength=WRAP, justify="left").pack(anchor="w", pady=(0, 6))
        ttk.Label(box, text=T.KEYS_MASTER_MANY_HINT, font=FONT_UI_SMALL, bootstyle="secondary",
                  wraplength=WRAP, justify="left").pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text=T.KEYS_MASTER_AGE, font=FONT_UI).pack(side="left", padx=(0, GAP))
        ttk.Entry(row, textvariable=self.master_age_var, font=FONT_UI).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=T.KEYS_MASTER_FROM_FILE, bootstyle="secondary-outline",
                   command=self._master_from_identity).pack(side="left", padx=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text=T.KEYS_MASTER_PGP, font=FONT_UI).pack(side="left", padx=(0, GAP))
        ttk.Entry(row, textvariable=self.master_pgp_var, font=FONT_UI).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=T.RECIPIENT_ADD_FILE, bootstyle="secondary-outline",
                   command=self._master_pgp_file).pack(side="left", padx=(6, 0))
        ttk.Button(box, text=T.KEYS_MASTER_SAVE, bootstyle="secondary",
                   command=self._save_master).pack(anchor="w", pady=(GAP, 0))
        self.master_result = ResultBox(box)
        self.master_result.frame.pack(fill="x", pady=(GAP, 0))

    def _build_check(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.KEYS_CHECK_TITLE, padding=GAP)
        box.pack(fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x")
        entry = ttk.Entry(row, textvariable=self.check_path_var, font=FONT_UI)
        entry.pack(side="left", fill="x", expand=True)
        entry.drop_target_register(DND_FILES)
        entry.dnd_bind("<<Drop>>", self._on_drop)
        ttk.Button(row, text=T.RECIPIENT_ADD_FILE, bootstyle="secondary-outline",
                   command=lambda: self._browse_into(self.check_path_var)).pack(side="left", padx=(6, 0))
        ttk.Button(row, text=T.KEYS_CHECK_BUTTON, bootstyle="secondary",
                   command=self._check).pack(side="left", padx=(6, 0))
        self.check_result = ResultBox(box)
        self.check_result.frame.pack(fill="x", pady=(GAP, 0))

    # ── 動作 ──────────────────────────────────────────────────────────

    def _browse_into(self, var) -> None:
        path = filedialog.askopenfilename(parent=self.app.root)
        if path:
            var.set(path)

    def _pick_age_path(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.app.root, initialfile=T.KEYS_DEFAULT_NAME)
        if path:
            self.age_path_var.set(path)

    def _pick_pgp_prefix(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.app.root, initialfile=T.KEYS_PGP_DEFAULT_PREFIX)
        if path:
            self.pgp_prefix_var.set(path)

    def _in_background(self, button, result_box, func, *args, after=None) -> None:
        """產生金鑰要算 scrypt 或呼叫 gpg：放到背景，按鈕先變灰。"""
        if self.busy:
            return
        self.busy = True
        button.configure(state="disabled")
        result_box.clear()
        self.app.set_status(T.STATUS_WORKING["keys"])

        def work():
            message = func(*args)
            self.app.post(done, message)

        def done(message):
            self.busy = False
            button.configure(state="normal")
            result_box.show(message)
            self.app.set_status((T.STATUS_DONE if message.kind == "success" else T.STATUS_FAILED)["keys"])
            if after:
                after(message)

        threading.Thread(target=work, daemon=True).start()

    def _create_age(self) -> None:
        def after(message):
            if message.kind == "success":
                self.age_pass_var.set("")
                self.age_confirm_var.set("")
                self.app.decrypt_tab.refresh_default_keys()
        self._in_background(self.age_button, self.age_result, logic.create_age_identity,
                            self.age_path_var.get(), self.age_pass_var.get(), self.age_confirm_var.get(),
                            self.age_default_var.get(), after=after)

    def _create_pgp(self) -> None:
        def after(message):
            if message.kind == "success":
                self.pgp_pass_var.set("")
                self.pgp_confirm_var.set("")
        self._in_background(self.pgp_button, self.pgp_result, logic.create_pgp_keypair,
                            self.pgp_prefix_var.get(), self.pgp_name_var.get(), self.pgp_pass_var.get(),
                            self.pgp_confirm_var.get(), after=after)

    def _master_from_identity(self) -> None:
        path = filedialog.askopenfilename(parent=self.app.root)
        if not path:
            return
        try:
            public = logic.public_key_from_identity(path)
        except logic.SealError as err:
            self.master_result.show(logic.error_message(err))
            return
        self.master_age_var.set(logic.add_master_value(self.master_age_var.get(), public, logic.MODE_AGE))

    def _master_pgp_file(self) -> None:
        path = filedialog.askopenfilename(parent=self.app.root)
        if path:
            self.master_pgp_var.set(logic.add_master_value(self.master_pgp_var.get(), path, logic.MODE_PGP))

    def _save_master(self) -> None:
        self.master_result.show(logic.save_master(self.master_age_var.get(), self.master_pgp_var.get()))
        self.app.encrypt_tab._refresh_master(reset=True)

    def _on_drop(self, event):
        path, _extra = logic.first_dropped(self.app.root.tk.splitlist(event.data))
        if path:
            self.check_path_var.set(path)
        return getattr(event, "action", None)

    def _check(self) -> None:
        self.check_result.show(logic.check_key_file(self.check_path_var.get()))


class AboutTab:
    """「關於」分頁：版本、做法說明、舊版工具入口。"""

    def __init__(self, app: "CryptoToolApp", notebook):
        self.scroll = Scrolled(notebook)
        self.page, self.frame = self.scroll.page, self.scroll.inner
        ttk.Label(self.frame, text=APP_TITLE, font=FONT_HEADING).pack(anchor="w")
        ttk.Label(self.frame, text=T.TAGLINE, font=FONT_UI,
                  bootstyle="secondary").pack(anchor="w", pady=(0, GAP))
        for line in T.ABOUT_LINES:
            ttk.Label(self.frame, text="・" + line, font=FONT_UI, wraplength=WRAP,
                      justify="left").pack(anchor="w", pady=(0, 4))
        legacy = ttk.Labelframe(self.frame, text=T.ABOUT_LEGACY_TITLE, padding=GAP)
        legacy.pack(fill="x", pady=(GAP * 2, 0))
        ttk.Label(legacy, text=T.ABOUT_LEGACY_TEXT, font=FONT_UI, wraplength=WRAP - 2 * GAP,
                  justify="left").pack(anchor="w")
        ttk.Button(legacy, text=T.LEGACY_OPEN_BUTTON, bootstyle="warning-outline",
                   command=app.open_legacy).pack(anchor="w", pady=(GAP, 0))
        self.legacy_result = ResultBox(legacy)
        self.legacy_result.frame.pack(fill="x", pady=(GAP, 0))


class CryptoToolApp:
    def __init__(self):
        # TkinterDnD.Tk() 讓所有子元件都能接受拖放
        self.root = TkinterDnD.Tk()
        self.theme = THEME_LIGHT
        self.style = ttk.Style(theme=self.theme)
        self._queue: queue.Queue = queue.Queue()
        self._legacy_window = None
        self.gpg_ok: bool | None = None   # 背景檢查完才知道

        self.root.title(APP_TITLE)
        self.root.minsize(*WINDOW_MIN)
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - WINDOW_SIZE[0]) // 2)
        y = max(0, (self.root.winfo_screenheight() - WINDOW_SIZE[1]) // 3)
        self.root.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}+{x}+{y}")

        self.status_var = tk.StringVar(value=T.STATUS_READY)
        self.theme_button_var = tk.StringVar(value=T.THEME_TO_DARK)
        self._build_ui()
        self._apply_theme()
        self.root.after(POLL_MS, self._drain_queue)
        threading.Thread(target=lambda: self.post(self._on_gpg_checked, logic.gpg_available()),
                         daemon=True).start()

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(PAD_X, GAP, PAD_X, 6))
        header.pack(fill="x")
        ttk.Label(header, text=T.APP_NAME, font=FONT_HEADING).pack(side="left")
        ttk.Label(header, text=T.TAGLINE, font=FONT_UI_SMALL,
                  bootstyle="secondary").pack(side="left", padx=(GAP, 0), pady=(6, 0))
        ttk.Button(header, textvariable=self.theme_button_var, bootstyle="secondary-outline",
                   command=self.toggle_theme).pack(side="right")

        status = ttk.Frame(self.root, padding=(PAD_X, 4))
        status.pack(fill="x", side="bottom")
        ttk.Separator(self.root).pack(fill="x", side="bottom")
        ttk.Label(status, textvariable=self.status_var, font=FONT_UI_SMALL,
                  bootstyle="secondary").pack(side="left")
        ttk.Label(status, text=f"v{__version__}", font=FONT_UI_SMALL,
                  bootstyle="secondary").pack(side="right")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=GAP, pady=(0, GAP))
        self.encrypt_tab = EncryptTab(self, notebook)
        self.decrypt_tab = DecryptTab(self, notebook)
        self.keys_tab = KeysTab(self, notebook)
        self.about_tab = AboutTab(self, notebook)
        for tab, label in ((self.encrypt_tab, T.TAB_ENCRYPT), (self.decrypt_tab, T.TAB_DECRYPT),
                           (self.keys_tab, T.TAB_KEYS), (self.about_tab, T.TAB_ABOUT)):
            notebook.add(tab.page, text=f"  {label}  ")

    def _on_gpg_checked(self, ok: bool) -> None:
        self.gpg_ok = ok
        if self.encrypt_tab.mode_var.get() == logic.MODE_PGP:
            self.encrypt_tab._on_mode_changed()

    # ── 主題 ──────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        """切主題後要重設的東西：字型（樣式跟著主題走）與拖放區的顏色。"""
        self.style.configure("TButton", font=FONT_UI)
        self.style.configure("TRadiobutton", font=FONT_UI)
        self.style.configure("TCheckbutton", font=FONT_UI)
        self.style.configure("TLabelframe.Label", font=FONT_UI_BOLD)
        self.style.configure("TNotebook.Tab", font=FONT_UI_BOLD, padding=(16, 8))
        for name in ("primary.TButton", "success.TButton"):
            self.style.configure(name, font=FONT_BUTTON)
        self.encrypt_tab._paint_drop()
        self.decrypt_tab._paint_drop()
        background = getattr(getattr(self.style, "colors", None), "bg", None)
        if background:   # 捲動用的 Canvas 不是 ttk 元件，底色要自己跟著主題換
            for tab in (self.encrypt_tab, self.decrypt_tab, self.keys_tab, self.about_tab):
                tab.scroll.canvas.configure(bg=background)
        self.theme_button_var.set(T.THEME_TO_DARK if self.theme == THEME_LIGHT else T.THEME_TO_LIGHT)

    def set_theme(self, name: str) -> None:
        if name != self.theme:
            self.theme = name
            self.style.theme_use(name)
        self._apply_theme()

    def toggle_theme(self) -> None:
        self.set_theme(THEME_DARK if self.theme == THEME_LIGHT else THEME_LIGHT)

    # ── 舊版工具 ──────────────────────────────────────────────────────

    def open_legacy(self) -> None:
        window = self._legacy_window
        if window is not None and window.winfo_exists():
            window.lift()
            return
        try:
            from .legacy_app import LEGACY_THEME, open_legacy_window
            self.set_theme(LEGACY_THEME)
            self._legacy_window = open_legacy_window(self.root)
        except ImportError:
            self.about_tab.legacy_result.show(logic.Message(
                "danger", T.ERROR_TITLES["dependency_missing"], [T.LEGACY_UNAVAILABLE]))

    # ── 背景工作 → 主執行緒 ───────────────────────────────────────────

    def post(self, func, *args) -> None:
        """給背景執行緒用：把要在主執行緒做的事排進佇列。"""
        self._queue.put((func, args))

    def _drain_queue(self) -> None:
        try:
            while True:
                func, args = self._queue.get_nowait()
                try:
                    func(*args)
                except Exception:  # 一個回呼出錯不能讓之後的進度與結果都收不到
                    self.set_status(T.ERROR_TITLES["internal_bug"])
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain_queue)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def run(self) -> None:
        self.root.mainloop()
