"""主視窗（gui/app.py）在「假的」tkinter／ttkbootstrap 上跑一遍。

這不是看畫面：它不建立任何真的視窗，只確認視圖的程式碼每一行都執行得過、
按鈕有接到邏輯、而且主視窗上沒有 Mixture 之類的複雜選項。
畫面長得對不對，仍然要人實際開起來看。
"""

import importlib
import os
import sys
import time
import types
import unittest
from unittest import mock

from _support import Case

WIDGETS = []   # 每個假元件建立時記一筆


class FakeVar:
    def __init__(self, master=None, value=None, **_kw):
        self._value = "" if value is None else value
        self._callbacks = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for callback in list(self._callbacks):
            callback()

    def trace_add(self, _mode, callback):
        self._callbacks.append(callback)


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.kind = type(self).__name__
        self.options = dict(kwargs)
        self.packed = False
        WIDGETS.append(self)

    def configure(self, **kwargs):
        self.options.update(kwargs)

    config = configure

    def pack(self, **_kw):
        self.packed = True

    grid = pack

    def pack_forget(self):
        self.packed = False

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_exists(self):
        return True

    def invoke(self):
        return self.options["command"]()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


class FakeRoot(FakeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tk = types.SimpleNamespace(splitlist=lambda data: tuple(data.split("|")))
        self.after_calls = []

    def after(self, ms, func=None, *args):
        self.after_calls.append((ms, func, args))


class FakeStyle:
    def __init__(self, theme=None):
        self.theme = theme
        self.configured = {}

    def theme_use(self, name):
        self.theme = name

    def configure(self, name, **kwargs):
        self.configured.setdefault(name, {}).update(kwargs)

    def map(self, *_a, **_k):
        pass


def _widget_class(name):
    return type(name, (FakeWidget,), {})


def fake_modules():
    tk = types.ModuleType("tkinter")
    tk.StringVar = tk.BooleanVar = tk.IntVar = FakeVar
    for name in ("Label", "Toplevel", "Canvas"):
        setattr(tk, name, _widget_class(name))
    dialogs = types.ModuleType("tkinter.filedialog")
    dialogs.picked = ""
    for name in ("askopenfilename", "asksaveasfilename", "askdirectory"):
        setattr(dialogs, name, lambda **_kw: dialogs.picked)
    tk.filedialog = dialogs
    ttk = types.ModuleType("ttkbootstrap")
    for name in ("Frame", "Label", "Button", "Entry", "Radiobutton", "Checkbutton",
                 "Labelframe", "Progressbar", "Notebook", "Separator", "Scrollbar"):
        setattr(ttk, name, _widget_class(name))
    ttk.Style = FakeStyle
    dnd = types.ModuleType("tkinterdnd2")
    dnd.DND_FILES = "DND_Files"
    dnd.TkinterDnD = types.SimpleNamespace(Tk=FakeRoot)
    return {"tkinter": tk, "tkinter.filedialog": dialogs, "ttkbootstrap": ttk, "tkinterdnd2": dnd}


def drain(app, seconds=30.0):
    """代替 Tk 的事件迴圈：等背景工作把結果排進佇列，然後在這裡執行。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        while not app._queue.empty():
            func, args = app._queue.get_nowait()
            func(*args)
        if not (app.encrypt_tab.busy or app.decrypt_tab.busy):
            return
        time.sleep(0.01)
    raise AssertionError("background job did not finish")


class HeadlessViewTests(Case):
    def setUp(self):
        super().setUp()
        WIDGETS.clear()
        modules = fake_modules()
        self.dialogs = modules["tkinter.filedialog"]
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("crypto_tool.gui.app", None)
        self.addCleanup(sys.modules.pop, "crypto_tool.gui.app", None)
        self.app_module = importlib.import_module("crypto_tool.gui.app")
        from crypto_tool.gui import logic, texts
        self.logic, self.T = logic, texts

    def title_of(self, box):
        return box._title.options.get("text"), box._title.options.get("bootstyle")

    def test_window_builds_with_four_tabs_and_no_mixture_options(self):
        T = self.T
        app = self.app_module.CryptoToolApp()
        self.assertEqual(len([w for w in WIDGETS if w.kind == "Notebook"]), 1)
        shown = " ".join(str(w.options.get("text", "")) for w in WIDGETS)
        shown = shown.replace(T.ABOUT_LEGACY_TEXT, "")
        for word in ("Mixture", "Layered", "Nested", "All-In-One", "XOR", "Base64", "PGP",
                     "Iterations"):
            self.assertNotIn(word, shown)
        self.assertIn(T.DROP_HINT["encrypt"], shown)
        self.assertIn(T.DROP_HINT["decrypt"], shown)
        self.assertIn(T.KEYS_INTRO, shown)
        # 進階設定預設收合
        enc = app.encrypt_tab
        self.assertFalse(enc.advanced_open or enc.advanced.packed)
        enc._toggle_advanced()
        self.assertTrue(enc.advanced.packed)
        enc._toggle_advanced()
        self.assertFalse(enc.advanced.packed)
        self.assertTrue(app.root.after_calls, "queue polling must be scheduled")

    def test_theme_toggle_repaints_drop_zone(self):
        from crypto_tool.gui.theme import PALETTE, THEME_DARK, THEME_LIGHT
        app = self.app_module.CryptoToolApp()
        self.assertEqual(app.theme, THEME_LIGHT)
        self.assertEqual(app.encrypt_tab.drop.options["bg"], PALETTE[THEME_LIGHT]["drop_bg"])
        app.toggle_theme()
        self.assertEqual(app.style.theme, THEME_DARK)
        self.assertEqual(app.decrypt_tab.drop.options["bg"], PALETTE[THEME_DARK]["drop_bg"])
        self.assertEqual(app.theme_button_var.get(), self.T.THEME_TO_LIGHT)
        self.assertTrue(app.style.configured["TButton"]["font"])
        app.toggle_theme()
        self.assertEqual(app.theme, THEME_LIGHT)

    def test_drop_encrypt_then_decrypt_through_the_view(self):
        logic, T, tmp = self.logic, self.T, self.tmp
        app = self.app_module.CryptoToolApp()
        keyfile = tmp / "k.env"
        app.keys_tab.new_path_var.set(str(keyfile))
        app.keys_tab._create()
        self.assertTrue(keyfile.is_file())
        app.keys_tab.check_path_var.set(str(keyfile))
        app.keys_tab._check()
        self.assertEqual(self.title_of(app.keys_tab.check_result)[1], "success")

        src = tmp / "photo.jpg"
        src.write_bytes(os.urandom(50_000))
        enc = app.encrypt_tab
        enc._on_drop(types.SimpleNamespace(data=f"{src}|{tmp / 'ignored'}", action="copy"))
        self.assertEqual(enc.input_var.get(), str(src))
        self.assertEqual(enc.output_var.get(), str(src) + ".isd2")   # 自動填好輸出位置
        self.assertIn(T.KIND_FILE, enc.input_info_var.get())

        enc.go.invoke()                                              # 還沒給金鑰
        self.assertEqual(self.title_of(enc.result)[0], T.PROBLEMS_TITLE)
        self.assertFalse(enc.busy)

        enc.key_mode_var.set(logic.KEY_FILE)
        self.assertTrue(enc.keyfile_frame.packed and not enc.pass_frame.packed)
        enc._on_keyfile_drop(types.SimpleNamespace(data=str(keyfile)))
        enc.go.invoke()
        self.assertEqual(enc.go.options["state"], "disabled")
        drain(app)
        self.assertEqual(self.title_of(enc.result), (T.SUCCESS_TITLE["encrypt"], "success"))
        self.assertEqual((enc.progress_var.get(), enc.go.options["state"]), (100, "normal"))
        self.assertEqual(app.status_var.get(), T.STATUS_DONE["encrypt"])

        dec = app.decrypt_tab
        self.dialogs.picked = str(src) + ".isd2"
        dec._pick_file()
        self.assertEqual(dec.key_mode_var.get(), logic.KEY_FILE)     # 依加密檔自動切到金鑰檔
        self.assertEqual(dec.output_var.get(), str(src))
        dec.keyfile_var.set(str(keyfile))
        dec.go.invoke()
        drain(app)
        self.assertEqual(self.title_of(dec.result)[1], "warning")    # 原檔還在：不覆蓋
        self.assertEqual(app.status_var.get(), T.STATUS_FAILED["decrypt"])
        dec.output_var.set(str(tmp / "back.jpg"))
        dec.go.invoke()
        drain(app)
        self.assertEqual(self.title_of(dec.result)[0], T.SUCCESS_TITLE["decrypt"])
        self.assertEqual((tmp / "back.jpg").read_bytes(), src.read_bytes())

    def test_user_edited_output_is_not_overwritten_by_suggestions(self):
        tmp = self.tmp
        dec = self.app_module.CryptoToolApp().decrypt_tab
        dec.input_var.set(str(tmp / "folder.isd2"))
        self.assertEqual(dec.output_var.get(), str(tmp / "folder"))
        dec.keep_tar_var.set(True)
        self.assertEqual(dec.output_var.get(), str(tmp / "folder.tar"))
        dec.output_var.set(str(tmp / "mine.tar"))
        dec.keep_tar_var.set(False)
        self.assertEqual(dec.output_var.get(), str(tmp / "mine.tar"))

    def test_legacy_file_offers_legacy_tool_and_missing_dependency_is_explained(self):
        T = self.T
        app = self.app_module.CryptoToolApp()
        legacy = self.tmp / "old.isd"
        legacy.write_text('CONTENT="""QUJD"""\nNOTE="""{}"""', encoding="utf-8")
        dec = app.decrypt_tab
        dec.input_var.set(str(legacy))
        self.assertEqual(dec.input_info_var.get(), T.SEALED_LEGACY)
        self.assertTrue(dec.legacy_button.packed)
        dec.input_var.set("")
        self.assertFalse(dec.legacy_button.packed)

        # 舊分頁在這組假模組下 import 不起來：要看到一句人話，而不是當掉
        app.open_legacy()
        self.assertEqual(app.about_tab.legacy_result._body.options["text"], T.LEGACY_UNAVAILABLE)

    def test_passphrase_fields_are_cleared_after_success(self):
        logic, T = self.logic, self.T
        real = logic.encrypt_path
        self.patch(logic, "encrypt_path", lambda *a, **k: real(*a, scrypt_log_n=10, **k))
        app = self.app_module.CryptoToolApp()
        src = self.tmp / "a.txt"
        src.write_bytes(b"hello")
        enc = app.encrypt_tab
        enc.input_var.set(str(src))
        enc.pass_var.set("a passphrase for the view test")
        self.assertEqual(enc.strength_var.get(), T.STRENGTH_LABELS[3])
        enc.confirm_var.set("not the same")
        enc.go.invoke()
        self.assertIn(T.PROBLEM_MISMATCH, enc.result._body.options["text"])
        enc.confirm_var.set("a passphrase for the view test")
        enc.show_pass_var.set(True)
        enc._toggle_show()
        self.assertEqual(enc.pass_entry.options["show"], "")
        enc.go.invoke()
        drain(app)
        self.assertEqual(self.title_of(enc.result)[1], "success")
        self.assertEqual((enc.pass_var.get(), enc.confirm_var.get()), ("", ""))


if __name__ == "__main__":
    unittest.main()
