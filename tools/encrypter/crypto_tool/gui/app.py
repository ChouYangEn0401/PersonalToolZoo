"""CryptoTool Pro 主視窗（新介面）：加密／解密／金鑰／關於。

這裡只管畫面：排元件、把按鈕接到 gui/logic.py、把結果顯示出來。
檢查、檔名、錯誤訊息、實際加解密都在 logic.py（有單元測試）；文案在 texts.py；
外觀規格在 docs/ui-spec.md。舊的四個分頁在 legacy_app.py，從「關於」分頁打開。
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


class JobTab:
    """「加密」與「解密」分頁共用的版面：① 選東西 ② 選鎖 ③ 存哪裡 → 按鈕 → 結果。"""

    def __init__(self, app: "CryptoToolApp", notebook, action: str):
        self.app = app
        self.action = action
        self.busy = False
        self._auto_output = ""
        self.frame = ttk.Frame(notebook, padding=(PAD_X, GAP))

        self.input_var = tk.StringVar()
        self.input_info_var = tk.StringVar(value=T.NOTHING_CHOSEN)
        self.key_mode_var = tk.StringVar(value=logic.KEY_PASSPHRASE)
        self.pass_var = tk.StringVar()
        self.confirm_var = tk.StringVar()
        self.show_pass_var = tk.BooleanVar(value=False)
        self.strength_var = tk.StringVar()
        self.keyfile_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.cipher_var = tk.StringVar(value=T.CIPHER_CHOICES[0][0])
        self.overwrite_var = tk.BooleanVar(value=False)
        self.keep_tar_var = tk.BooleanVar(value=False)
        self.progress_var = tk.IntVar(value=0)
        self.progress_text_var = tk.StringVar()

        self._build_input()
        self._build_key()
        self._build_output()
        self._build_advanced()
        self._build_action()

        self.input_var.trace_add("write", lambda *_: self._on_input_changed())
        self.key_mode_var.trace_add("write", lambda *_: self._show_key_mode())
        self.pass_var.trace_add("write", lambda *_: self._on_passphrase_changed())
        self.keep_tar_var.trace_add("write", lambda *_: self._refresh_suggestion())
        self._show_key_mode()

    # ── ① 輸入 ────────────────────────────────────────────────────────

    def _build_input(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_INPUT[self.action], padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        self.drop = tk.Label(box, text=T.DROP_HINT[self.action], font=FONT_DROP,
                             height=3, relief="flat", cursor="hand2")
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
        ttk.Entry(row, textvariable=self.input_var, font=FONT_UI).pack(
            side="left", fill="x", expand=True, padx=(GAP, 0))
        self.input_info = ttk.Label(box, textvariable=self.input_info_var, font=FONT_UI_SMALL,
                                    bootstyle="secondary", wraplength=WRAP, justify="left")
        self.input_info.pack(anchor="w", pady=(4, 0))
        self.legacy_button = ttk.Button(box, text=T.LEGACY_OPEN_BUTTON, bootstyle="warning-outline",
                                        command=self.app.open_legacy)

    def _paint_drop(self, active: bool = False) -> None:
        colors = PALETTE[self.app.theme]
        self.drop.configure(bg=colors["drop_active" if active else "drop_bg"],
                            fg=colors["drop_fg"])

    def _on_drop(self, event):
        path, _extra = logic.first_dropped(self.app.root.tk.splitlist(event.data))
        self._paint_drop(active=False)
        if path:
            self.input_var.set(path)
        return getattr(event, "action", None)

    def _pick_file(self) -> None:
        types = [("ISD2", "*.isd2"), ("*", "*.*")] if self.action == logic.DECRYPT else [("*", "*.*")]
        path = filedialog.askopenfilename(parent=self.app.root, filetypes=types)
        if path:
            self.input_var.set(path)

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(parent=self.app.root)
        if path:
            self.input_var.set(path)

    def _on_input_changed(self) -> None:
        path = self.input_var.get().strip()
        self.legacy_button.pack_forget()
        self.result.clear()
        if not path:
            self.input_info_var.set(T.NOTHING_CHOSEN)
            return
        if self.action == logic.ENCRYPT:
            self.input_info_var.set(logic.describe_input(path))
        else:
            text, info, problem = logic.inspect_sealed(path)
            self.input_info_var.set(text)
            if problem is not None:
                self.result.show(problem)
            mode = logic.key_mode_for(info)
            if mode:
                self.key_mode_var.set(mode)
            if info is not None and info.get("format") != "isd2":
                self.legacy_button.pack(anchor="w", pady=(6, 0))
        self._refresh_suggestion(force=True)

    # ── ② 金鑰 ────────────────────────────────────────────────────────

    def _build_key(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_KEY[self.action], padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        modes = ttk.Frame(box)
        modes.pack(fill="x")
        ttk.Radiobutton(modes, text=T.KEY_MODE_PASSPHRASE, variable=self.key_mode_var,
                        value=logic.KEY_PASSPHRASE).pack(side="left")
        ttk.Radiobutton(modes, text=T.KEY_MODE_KEYFILE, variable=self.key_mode_var,
                        value=logic.KEY_FILE).pack(side="left", padx=(GAP * 2, 0))

        self.key_holder = ttk.Frame(box)
        self.key_holder.pack(fill="x", pady=(GAP, 0))

        self.pass_frame = ttk.Frame(self.key_holder)
        self.pass_frame.columnconfigure(1, weight=1)
        ttk.Label(self.pass_frame, text=T.PASSPHRASE_LABEL, font=FONT_UI).grid(
            row=0, column=0, sticky="w", padx=(0, GAP))
        self.pass_entry = ttk.Entry(self.pass_frame, textvariable=self.pass_var, show="•",
                                    font=FONT_UI)
        self.pass_entry.grid(row=0, column=1, sticky="ew")
        ttk.Checkbutton(self.pass_frame, text=T.SHOW_PASSPHRASE, variable=self.show_pass_var,
                        command=self._toggle_show).grid(row=0, column=2, padx=(GAP, 0))
        self.confirm_entry = None
        if self.action == logic.ENCRYPT:
            ttk.Label(self.pass_frame, text=T.PASSPHRASE_CONFIRM_LABEL, font=FONT_UI).grid(
                row=1, column=0, sticky="w", padx=(0, GAP), pady=(6, 0))
            self.confirm_entry = ttk.Entry(self.pass_frame, textvariable=self.confirm_var,
                                           show="•", font=FONT_UI)
            self.confirm_entry.grid(row=1, column=1, sticky="ew", pady=(6, 0))
            self.strength_label = ttk.Label(self.pass_frame, textvariable=self.strength_var,
                                            font=FONT_UI_SMALL)
            self.strength_label.grid(row=2, column=1, sticky="w", pady=(4, 0))

        self.keyfile_frame = ttk.Frame(self.key_holder)
        row = ttk.Frame(self.keyfile_frame)
        row.pack(fill="x")
        ttk.Label(row, text=T.KEYFILE_LABEL, font=FONT_UI).pack(side="left", padx=(0, GAP))
        entry = ttk.Entry(row, textvariable=self.keyfile_var, font=FONT_UI)
        entry.pack(side="left", fill="x", expand=True)
        entry.drop_target_register(DND_FILES)
        entry.dnd_bind("<<Drop>>", self._on_keyfile_drop)
        ttk.Button(row, text=T.BROWSE, bootstyle="secondary-outline",
                   command=self._pick_keyfile).pack(side="left", padx=(6, 0))
        ttk.Label(self.keyfile_frame, text=T.KEYFILE_HINT, font=FONT_UI_SMALL,
                  bootstyle="secondary").pack(anchor="w", pady=(4, 0))

    def _show_key_mode(self) -> None:
        self.pass_frame.pack_forget()
        self.keyfile_frame.pack_forget()
        if self.key_mode_var.get() == logic.KEY_FILE:
            self.keyfile_frame.pack(fill="x")
        else:
            self.pass_frame.pack(fill="x")

    def _toggle_show(self) -> None:
        show = "" if self.show_pass_var.get() else "•"
        self.pass_entry.configure(show=show)
        if self.confirm_entry is not None:
            self.confirm_entry.configure(show=show)

    def _on_passphrase_changed(self) -> None:
        if self.action != logic.ENCRYPT:
            return
        level, label = logic.passphrase_strength(self.pass_var.get())
        self.strength_var.set(label)
        self.strength_label.configure(
            bootstyle=("secondary", "danger", "warning", "success")[level])

    def _on_keyfile_drop(self, event):
        path, _extra = logic.first_dropped(self.app.root.tk.splitlist(event.data))
        if path:
            self.keyfile_var.set(path)
        return getattr(event, "action", None)

    def _pick_keyfile(self) -> None:
        path = filedialog.askopenfilename(parent=self.app.root)
        if path:
            self.keyfile_var.set(path)

    # ── ③ 輸出 ────────────────────────────────────────────────────────

    def _build_output(self) -> None:
        box = ttk.Labelframe(self.frame, text=T.STEP_OUTPUT, padding=GAP)
        box.pack(fill="x", pady=(0, GAP))
        ttk.Entry(box, textvariable=self.output_var, font=FONT_UI).pack(
            side="left", fill="x", expand=True)
        ttk.Button(box, text=T.SAVE_AS, bootstyle="secondary-outline",
                   command=self._pick_output).pack(side="left", padx=(6, 0))

    def _refresh_suggestion(self, force: bool = False) -> None:
        """輸出欄還是自動填的（或空的）才更新，不蓋掉使用者自己改過的位置。"""
        current = self.output_var.get().strip()
        if not force and current and current != self._auto_output:
            return
        self._auto_output = logic.suggest_output(
            self.action, self.input_var.get().strip(), self.keep_tar_var.get())
        self.output_var.set(self._auto_output)

    def _pick_output(self) -> None:
        options = {"parent": self.app.root}
        if self.action == logic.ENCRYPT:
            options["defaultextension"] = ".isd2"
            options["filetypes"] = [("ISD2", "*.isd2")]
        current = self.output_var.get().strip()
        if current:
            options["initialfile"] = current.replace("\\", "/").rsplit("/", 1)[-1]
        path = filedialog.asksaveasfilename(**options)
        if path:
            self.output_var.set(path)

    # ── 進階 ──────────────────────────────────────────────────────────

    def _build_advanced(self) -> None:
        self.advanced_open = False
        self.advanced_toggle = ttk.Button(self.frame, text=T.ADVANCED_SHOW, bootstyle="link",
                                          command=self._toggle_advanced)
        self.advanced_toggle.pack(anchor="w")
        self.advanced = ttk.Frame(self.frame, padding=(GAP, 0, 0, GAP))
        if self.action == logic.ENCRYPT:
            row = ttk.Frame(self.advanced)
            row.pack(fill="x")
            ttk.Label(row, text=T.CIPHER_LABEL, font=FONT_UI).pack(side="left", padx=(0, GAP))
            for value, label in T.CIPHER_CHOICES:
                ttk.Radiobutton(row, text=label, variable=self.cipher_var,
                                value=value).pack(side="left", padx=(0, GAP))
            ttk.Label(self.advanced, text=T.CIPHER_NOTE, font=FONT_UI_SMALL,
                      bootstyle="secondary").pack(anchor="w", pady=(2, 6))
        else:
            ttk.Checkbutton(self.advanced, text=T.KEEP_TAR,
                            variable=self.keep_tar_var).pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(self.advanced, text=T.OVERWRITE,
                        variable=self.overwrite_var).pack(anchor="w")

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
        return logic.JobForm(
            action=self.action,
            input_path=self.input_var.get().strip(),
            output_path=self.output_var.get().strip(),
            key_mode=self.key_mode_var.get(),
            passphrase=self.pass_var.get(),
            passphrase_confirm=self.confirm_var.get(),
            key_file=self.keyfile_var.get().strip(),
            cipher=self.cipher_var.get(),
            overwrite=self.overwrite_var.get(),
            keep_tar=self.keep_tar_var.get(),
        )

    def _start(self) -> None:
        if self.busy:
            return
        form = self.form()
        problems = logic.validate(form)
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

    def _on_done(self, message: logic.Message) -> None:
        self._set_busy(False)
        self.result.show(message)
        ok = message.kind == "success"
        if ok:
            self.progress_var.set(100)
            self.pass_var.set("")
            self.confirm_var.set("")
        else:
            self.progress_var.set(0)
            self.progress_text_var.set("")
        self.app.set_status((T.STATUS_DONE if ok else T.STATUS_FAILED)[self.action])

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.go.configure(state="disabled" if busy else "normal")


class KeysTab:
    """「金鑰」分頁：產生新的金鑰檔、檢查既有的金鑰檔。"""

    def __init__(self, app: "CryptoToolApp", notebook):
        self.app = app
        self.frame = ttk.Frame(notebook, padding=(PAD_X, GAP))
        self.new_path_var = tk.StringVar()
        self.check_path_var = tk.StringVar()

        ttk.Label(self.frame, text=T.KEYS_INTRO, font=FONT_UI, wraplength=WRAP,
                  justify="left").pack(anchor="w", pady=(0, GAP))

        new_box = ttk.Labelframe(self.frame, text=T.KEYS_NEW_TITLE, padding=GAP)
        new_box.pack(fill="x", pady=(0, GAP))
        row = ttk.Frame(new_box)
        row.pack(fill="x")
        ttk.Label(row, text=T.KEYS_NEW_PATH, font=FONT_UI).pack(side="left", padx=(0, GAP))
        ttk.Entry(row, textvariable=self.new_path_var, font=FONT_UI).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row, text=T.SAVE_AS, bootstyle="secondary-outline",
                   command=self._pick_new).pack(side="left", padx=(6, 0))
        ttk.Button(new_box, text=T.KEYS_NEW_BUTTON, bootstyle="primary",
                   command=self._create).pack(anchor="w", pady=(GAP, 0))
        self.new_result = ResultBox(new_box)
        self.new_result.frame.pack(fill="x", pady=(GAP, 0))

        check_box = ttk.Labelframe(self.frame, text=T.KEYS_CHECK_TITLE, padding=GAP)
        check_box.pack(fill="x")
        row = ttk.Frame(check_box)
        row.pack(fill="x")
        entry = ttk.Entry(row, textvariable=self.check_path_var, font=FONT_UI)
        entry.pack(side="left", fill="x", expand=True)
        entry.drop_target_register(DND_FILES)
        entry.dnd_bind("<<Drop>>", self._on_drop)
        ttk.Button(row, text=T.BROWSE, bootstyle="secondary-outline",
                   command=self._pick_check).pack(side="left", padx=(6, 0))
        ttk.Button(row, text=T.KEYS_CHECK_BUTTON, bootstyle="secondary",
                   command=self._check).pack(side="left", padx=(6, 0))
        self.check_result = ResultBox(check_box)
        self.check_result.frame.pack(fill="x", pady=(GAP, 0))

    def _pick_new(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.app.root,
                                            initialfile=T.KEYS_DEFAULT_NAME)
        if path:
            self.new_path_var.set(path)

    def _create(self) -> None:
        self.new_result.show(logic.create_key_file(self.new_path_var.get()))

    def _pick_check(self) -> None:
        path = filedialog.askopenfilename(parent=self.app.root)
        if path:
            self.check_path_var.set(path)

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
        self.frame = ttk.Frame(notebook, padding=(PAD_X, GAP))
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
        self.encrypt_tab = JobTab(self, notebook, logic.ENCRYPT)
        self.decrypt_tab = JobTab(self, notebook, logic.DECRYPT)
        self.keys_tab = KeysTab(self, notebook)
        self.about_tab = AboutTab(self, notebook)
        for tab, label in ((self.encrypt_tab, T.TAB_ENCRYPT), (self.decrypt_tab, T.TAB_DECRYPT),
                           (self.keys_tab, T.TAB_KEYS), (self.about_tab, T.TAB_ABOUT)):
            notebook.add(tab.frame, text=f"  {label}  ")

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
