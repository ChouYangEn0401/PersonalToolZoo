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

import pytest

WIDGETS = []   # 每個假元件建立時記一筆 (種類, 參數)


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


@pytest.fixture
def gui(monkeypatch):
    WIDGETS.clear()
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
    for name, module in (("tkinter", tk), ("tkinter.filedialog", dialogs),
                         ("ttkbootstrap", ttk), ("tkinterdnd2", dnd)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "crypto_tool.gui.app", raising=False)
    module = importlib.import_module("crypto_tool.gui.app")
    yield types.SimpleNamespace(app_module=module, dialogs=dialogs)
    sys.modules.pop("crypto_tool.gui.app", None)


def drain(app, seconds=30.0):
    """代替 Tk 的事件迴圈：等背景工作把結果排進佇列，然後在這裡執行。"""
    tab_busy = lambda: app.encrypt_tab.busy or app.decrypt_tab.busy
    deadline = time.time() + seconds
    while time.time() < deadline:
        while not app._queue.empty():
            func, args = app._queue.get_nowait()
            func(*args)
        if not tab_busy():
            return
        time.sleep(0.01)
    raise AssertionError("background job did not finish")


def texts_on_screen():
    return [str(w.options.get("text", "")) for w in WIDGETS]


def test_window_builds_with_four_tabs_and_no_mixture_options(gui):
    from crypto_tool.gui import texts as T
    app = gui.app_module.CryptoToolApp()
    labels = [args for w in WIDGETS if w.kind == "Notebook" for args in [w]]
    assert len(labels) == 1
    for tab in (app.encrypt_tab, app.decrypt_tab, app.keys_tab, app.about_tab):
        assert tab.frame is not None
    shown = " ".join(texts_on_screen())
    for word in ("Mixture", "Layered", "Nested", "All-In-One", "XOR", "Base64", "PGP",
                 "Iterations"):
        assert word not in shown.replace(T.ABOUT_LEGACY_TEXT, "")
    assert T.DROP_HINT["encrypt"] in shown and T.KEYS_INTRO in shown
    # 進階設定預設收合
    assert app.encrypt_tab.advanced_open is False and app.encrypt_tab.advanced.packed is False
    app.encrypt_tab._toggle_advanced()
    assert app.encrypt_tab.advanced.packed is True
    app.encrypt_tab._toggle_advanced()
    assert app.encrypt_tab.advanced.packed is False
    assert app.root.after_calls, "queue polling must be scheduled"


def test_theme_toggle_repaints_drop_zone(gui):
    from crypto_tool.gui import texts as T
    from crypto_tool.gui.theme import PALETTE, THEME_DARK, THEME_LIGHT
    app = gui.app_module.CryptoToolApp()
    assert app.theme == THEME_LIGHT
    assert app.encrypt_tab.drop.options["bg"] == PALETTE[THEME_LIGHT]["drop_bg"]
    app.toggle_theme()
    assert app.style.theme == THEME_DARK
    assert app.decrypt_tab.drop.options["bg"] == PALETTE[THEME_DARK]["drop_bg"]
    assert app.theme_button_var.get() == T.THEME_TO_LIGHT
    assert app.style.configured["TButton"]["font"]
    app.toggle_theme()
    assert app.theme == THEME_LIGHT


def test_drop_encrypt_then_decrypt_through_the_view(gui, tmp_path):
    from crypto_tool.gui import logic, texts as T
    app = gui.app_module.CryptoToolApp()
    keyfile = tmp_path / "k.env"
    app.keys_tab.new_path_var.set(str(keyfile))
    app.keys_tab._create()
    assert keyfile.is_file()
    app.keys_tab.check_path_var.set(str(keyfile))
    app.keys_tab._check()

    src = tmp_path / "photo.jpg"
    src.write_bytes(os.urandom(50_000))
    enc = app.encrypt_tab
    enc._on_drop(types.SimpleNamespace(data=f"{src}|{tmp_path / 'ignored'}", action="copy"))
    assert enc.input_var.get() == str(src)
    assert enc.output_var.get() == str(src) + ".isd2"       # 自動填好輸出位置
    assert T.KIND_FILE in enc.input_info_var.get()

    enc.go.invoke()                                         # 還沒給金鑰
    assert enc.result._title.options["text"] == T.PROBLEMS_TITLE and not enc.busy

    enc.key_mode_var.set(logic.KEY_FILE)
    assert enc.keyfile_frame.packed and not enc.pass_frame.packed
    enc._on_keyfile_drop(types.SimpleNamespace(data=str(keyfile)))
    enc.go.invoke()
    assert enc.go.options["state"] == "disabled"
    drain(app)
    assert enc.result._title.options["text"] == T.SUCCESS_TITLE["encrypt"]
    assert enc.result._title.options["bootstyle"] == "success"
    assert enc.progress_var.get() == 100 and enc.go.options["state"] == "normal"
    assert app.status_var.get() == T.STATUS_DONE["encrypt"]

    dec = app.decrypt_tab
    gui.dialogs.picked = str(src) + ".isd2"
    dec._pick_file()
    assert dec.key_mode_var.get() == logic.KEY_FILE         # 依加密檔自動切到金鑰檔
    assert dec.output_var.get() == str(src)
    dec.keyfile_var.set(str(keyfile))
    dec.go.invoke()
    drain(app)
    assert dec.result._title.options["bootstyle"] == "warning"   # 原檔還在：不覆蓋
    dec.output_var.set(str(tmp_path / "back.jpg"))
    dec.go.invoke()
    drain(app)
    assert dec.result._title.options["text"] == T.SUCCESS_TITLE["decrypt"]
    assert (tmp_path / "back.jpg").read_bytes() == src.read_bytes()


def test_user_edited_output_is_not_overwritten_by_suggestions(gui, tmp_path):
    app = gui.app_module.CryptoToolApp()
    dec = app.decrypt_tab
    dec.input_var.set(str(tmp_path / "folder.isd2"))
    assert dec.output_var.get() == str(tmp_path / "folder")
    dec.keep_tar_var.set(True)
    assert dec.output_var.get() == str(tmp_path / "folder.tar")
    dec.output_var.set(str(tmp_path / "mine.tar"))
    dec.keep_tar_var.set(False)
    assert dec.output_var.get() == str(tmp_path / "mine.tar")


def test_legacy_file_offers_legacy_tool_and_missing_dependency_is_explained(gui, tmp_path):
    from crypto_tool.gui import texts as T
    app = gui.app_module.CryptoToolApp()
    legacy = tmp_path / "old.isd"
    legacy.write_text('CONTENT="""QUJD"""\nNOTE="""{}"""', encoding="utf-8")
    dec = app.decrypt_tab
    dec.input_var.set(str(legacy))
    assert dec.input_info_var.get() == T.SEALED_LEGACY and dec.legacy_button.packed
    dec.input_var.set("")
    assert not dec.legacy_button.packed

    # 舊分頁需要 pycryptodome（core/）；這個測試環境沒有的話，要看到人話而不是當掉
    app.open_legacy()
    try:
        import Crypto  # noqa: F401
    except ImportError:
        assert app.about_tab.legacy_result._body.options["text"] == T.LEGACY_UNAVAILABLE


def test_passphrase_fields_are_cleared_after_success(gui, tmp_path, monkeypatch):
    from crypto_tool.gui import logic, texts as T
    real = logic.encrypt_path
    monkeypatch.setattr(logic, "encrypt_path", lambda *a, **k: real(*a, scrypt_log_n=10, **k))
    app = gui.app_module.CryptoToolApp()
    src = tmp_path / "a.txt"
    src.write_bytes(b"hello")
    enc = app.encrypt_tab
    enc.input_var.set(str(src))
    enc.pass_var.set("a passphrase for the view test")
    assert enc.strength_var.get() == T.STRENGTH_LABELS[3]
    enc.confirm_var.set("not the same")
    enc.go.invoke()
    assert T.PROBLEM_MISMATCH in enc.result._body.options["text"]
    enc.confirm_var.set("a passphrase for the view test")
    enc.show_pass_var.set(True)
    enc._toggle_show()
    assert enc.pass_entry.options["show"] == ""
    enc.go.invoke()
    drain(app)
    assert enc.result._title.options["bootstyle"] == "success"
    assert enc.pass_var.get() == "" and enc.confirm_var.get() == ""
