#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Better Prompt — AI Text Transformer
貼上文字、選一個轉換模式，交給 LLM（OpenAI / Gemini / Claude）改寫。

模式庫（MODES）與 LLM 呼叫層在 repo 的 libs/toolzoo/ai/，Video Notes 也用同一份。
"""

import json
import os
import sys
import threading
from pathlib import Path

# 從原始碼執行時讓 import 找得到 repo 的 libs/（打包時由 tool.json 的 pathex 處理）
_LIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs")
if not getattr(sys, "frozen", False) and os.path.isdir(_LIBS):
    sys.path.insert(0, os.path.abspath(_LIBS))

import customtkinter as ctk  # noqa: E402
from tkinter import messagebox  # noqa: E402
from tkinter import simpledialog  # noqa: E402

from toolzoo.ai import (DEFAULT_MODELS, DEFAULT_PROVIDER, LLM, PROVIDERS, find_key, keys_file,  # noqa: E402
                        needs_key, save_key)
from toolzoo.ai.text_modes import MODES, build_messages, first_mode, preview  # noqa: E402
from toolzoo.appdirs import tool_data_dir  # noqa: E402
from version import __version__  # noqa: E402

# ─── Appearance ───────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ─── Paths ────────────────────────────────────────────────────────────────────

def resource_path(*parts):
    """打包後也正確的資料檔路徑（PyInstaller 會把資料解到 sys._MEIPASS）。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _app_dir() -> Path:
    """exe（或腳本）所在的資料夾——使用者會把 .env 放在這裡。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# 設定與「推薦模型」的編輯都寫到使用者資料夾：onefile exe 旁邊或 _MEIPASS 裡的檔案，關掉程式就沒了
DATA_DIR = tool_data_dir("better-prompt")
SETTINGS_FILE = DATA_DIR / "settings.json"
RECO_FILE = DATA_DIR / "model_recommendations.json"
DEFAULT_RECO_FILE = Path(resource_path("model_recommendations.json"))
# v1 把設定（含明文 OpenAI 金鑰）存在家目錄；讀得到就沿用，不會刪它
LEGACY_SETTINGS_FILE = Path.home() / ".better_prompt_settings.json"
KEY_FILES = (_app_dir() / ".env",)

# 還沒連上 API（拿不到帳號可用的模型清單）時，下拉選單先顯示這些
FALLBACK_MODELS: dict[str, list[str]] = {
    "claude-sub": ["sonnet", "haiku", "opus"],
    "openai": ["gpt-5.1", "gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini"],
    "gemini": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"],
}


# ─── Settings Helpers ─────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_settings() -> dict:
    # 沒存過設定的人預設用 Claude 訂閱；存過的照原本的選擇。
    # v1 的舊設定檔不算「選過服務」——那時只有 OpenAI 可選，只沿用它的模型與 temperature。
    settings: dict = {"provider": DEFAULT_PROVIDER, "models": {}, "temperature": 0.7}
    legacy = _read_json(LEGACY_SETTINGS_FILE)
    if legacy.get("model"):
        settings["models"]["openai"] = legacy["model"]
    if "temperature" in legacy:
        settings["temperature"] = legacy["temperature"]
    settings.update({k: v for k, v in _read_json(SETTINGS_FILE).items() if k != "api_key"})
    return settings


def save_settings(settings: dict) -> None:
    # 金鑰不放設定檔：統一由 toolzoo.ai.save_key 存到共用金鑰檔
    _write_json(SETTINGS_FILE, {k: v for k, v in settings.items() if k != "api_key"})


def legacy_api_key() -> str:
    return str(_read_json(LEGACY_SETTINGS_FILE).get("api_key", "")).strip()


def load_recommendations() -> dict:
    return _read_json(RECO_FILE) if RECO_FILE.exists() else _read_json(DEFAULT_RECO_FILE)


def save_recommendations(recs: dict) -> None:
    _write_json(RECO_FILE, recs)


def run_completion(llm: LLM, system: str, user: str, temperature: float,
                   on_token, on_done, on_error) -> None:
    """在背景執行緒呼叫 LLM。callback 也在背景執行緒被呼叫，更新 UI 請自己 self.after(0, ...)。

    on_done 會拿到權威的完整輸出（Claude 拒答改由 fallback 模型接手時，跟串流內容可能不同）。
    """
    final: dict = {}
    try:
        for piece in llm.stream(system, user, temperature=temperature, final=final):
            on_token(piece)
    except Exception as exc:  # noqa: BLE001 — 任何錯誤都要顯示在畫面上，不能讓背景執行緒默默死掉
        on_error(exc)
        return
    on_done(final.get("text"))


# ─── Main Application ─────────────────────────────────────────────────────────

class BetterPromptApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.recommendations = load_recommendations()
        self.provider: str = self.settings.get("provider", DEFAULT_PROVIDER)
        if self.provider not in PROVIDERS:
            self.provider = DEFAULT_PROVIDER
        self._initial_key, self._key_source = self._find_key(self.provider)
        self.llm: LLM | None = None
        self.available_models: list[str] = FALLBACK_MODELS[self.provider].copy()
        self.is_processing = False
        self.current_mode, self.current_submode = first_mode()

        self._setup_window()
        self._build_ui()
        # Attempt auto-connect if a key was saved
        self._try_connect_api()

    # ── Window Setup ──────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.title(f"Better Prompt  ✦  AI Text Transformer  v{__version__}")
        self.geometry("1260x820")
        self.minsize(960, 680)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 1260) // 2
        y = max(0, (self.winfo_screenheight() - 820) // 2)
        self.geometry(f"1260x820+{x}+{y}")

    # ── Master Layout ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=0)   # sidebar
        self.grid_columnconfigure(1, weight=1)   # main
        self.grid_rowconfigure(0, weight=0)      # top bar
        self.grid_rowconfigure(1, weight=1)      # content
        self.grid_rowconfigure(2, weight=0)      # status bar

        self._build_topbar()
        self._build_sidebar()
        self._build_main_area()
        self._build_statusbar()
        # Initialize first mode and submode now that main widgets (banner) exist
        mode, sub = first_mode()
        self._toggle_mode(mode)
        self._select_submode(mode, sub)

    # ── Top Bar ───────────────────────────────────────────────────────────────

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(
            self, height=68, corner_radius=0,
            fg_color=("#111827", "#0d1117"),
            border_width=0,
        )
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        bar.grid_propagate(False)

        # Brand
        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=22, pady=0, sticky="w")
        ctk.CTkLabel(
            brand, text="✦ Better Prompt",
            font=ctk.CTkFont(size=22, weight="bold"), text_color="#4A9EFF",
        ).pack(side="left")
        ctk.CTkLabel(
            brand, text="  AI Text Transformer",
            font=ctk.CTkFont(size=13), text_color="#555",
        ).pack(side="left", pady=(5, 0))

        # API controls — right side
        api = ctk.CTkFrame(bar, fg_color="transparent")
        api.grid(row=0, column=2, padx=22, pady=12, sticky="e")

        self.provider_var = ctk.StringVar(value=PROVIDERS[self.provider])
        ctk.CTkOptionMenu(
            api, values=list(PROVIDERS.values()), variable=self.provider_var,
            width=200, height=28, font=ctk.CTkFont(size=12),
            command=self._on_provider_change,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(api, text="🔑", font=ctk.CTkFont(size=14)).pack(side="left")
        self.api_key_var = ctk.StringVar(value=self._initial_key)
        self.api_key_entry = ctk.CTkEntry(
            api, textvariable=self.api_key_var,
            width=210, show="•", placeholder_text="API Key",
            font=ctk.CTkFont(size=12),
        )
        self.api_key_entry.pack(side="left", padx=(6, 4))
        self.api_key_entry.bind("<Return>", lambda _e: self._connect_api())

        # Prevent copying from the API key entry; allow paste and typing
        def _block_copy(e=None):
            return "break"

        # Block common copy shortcuts and selection-based copying
        for seq in ("<Control-c>", "<Control-C>", "<Control-Insert>", "<Button-3>", "<Double-Button-1>", "<Triple-Button-1>", "<Control-a>"):
            self.api_key_entry.bind(seq, _block_copy)

        # After any mouse release, clear any selection to avoid accidental copy
        def _clear_selection_after_click(e=None):
            try:
                self.api_key_entry.selection_clear()
            except Exception:
                pass

        self.api_key_entry.bind("<ButtonRelease-1>", lambda e: self.after(1, _clear_selection_after_click))

        self._show_key = False
        self.eye_btn = ctk.CTkButton(
            api, text="👁", width=30, height=28,
            fg_color="transparent", hover_color="#222",
            command=self._toggle_key_visibility,
            font=ctk.CTkFont(size=14),
        )
        self.eye_btn.pack(side="left", padx=(0, 6))

        # 金鑰是從哪裡讀到的（環境變數 / keys.env / .env / v1 設定檔）
        self.key_source_lbl = ctk.CTkLabel(api, text="", font=ctk.CTkFont(size=10), text_color="#A3BE8C")
        self.key_source_lbl.pack(side="left", padx=(0, 8))
        self._show_key_source()

        self.connect_btn = ctk.CTkButton(
            api, text="連接 API", width=82, height=28,
            fg_color="#4A9EFF", hover_color="#2979DD",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._connect_api,
        )
        self.connect_btn.pack(side="left", padx=(0, 14))
        self._apply_key_ui()

        self.api_status_lbl = ctk.CTkLabel(
            api, text="● 未連接",
            font=ctk.CTkFont(size=12), text_color="#FF6B6B",
        )
        self.api_status_lbl.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(api, text="模型:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.model_var = ctk.StringVar(value=self._saved_model(self.provider))
        self.model_menu = ctk.CTkOptionMenu(
            api, values=self.available_models, variable=self.model_var,
            width=150, height=28, font=ctk.CTkFont(size=12),
            command=self._on_model_change,
        )
        self.model_menu.pack(side="left")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        self.sidebar = ctk.CTkScrollableFrame(
            self, width=242,
            fg_color=("#0a0f1e", "#080c18"),
            corner_radius=0,
            scrollbar_button_color="#1e2a3a",
            scrollbar_button_hover_color="#2a3a52",
        )
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.sidebar, text="  轉換模式",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#444", anchor="w",
        ).grid(row=0, column=0, padx=10, pady=(16, 8), sticky="w")

        self.mode_btns: dict = {}
        self.sub_frames: dict = {}
        self.sub_btns: dict = {}

        row = 1
        for mode_name, mode_data in MODES.items():
            color = mode_data.color

            # Category header button
            hdr = ctk.CTkButton(
                self.sidebar, text=f"  {mode_name}",
                anchor="w", height=40,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="transparent",
                hover_color=("#111d2e", "#111d2e"),
                text_color="#bbb", corner_radius=8,
                command=lambda m=mode_name: self._toggle_mode(m),
            )
            hdr.grid(row=row, column=0, padx=6, pady=(3, 0), sticky="ew")
            self.mode_btns[mode_name] = hdr
            row += 1

            # Sub-mode container (hidden by default)
            sub_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
            sub_frame.grid(row=row, column=0, sticky="ew")
            sub_frame.grid_columnconfigure(0, weight=1)
            sub_frame.grid_remove()
            self.sub_frames[mode_name] = sub_frame
            self.sub_btns[mode_name] = {}

            for sub_name in mode_data.submodes:
                btn = ctk.CTkButton(
                    sub_frame, text=f"    • {sub_name}",
                    anchor="w", height=32,
                    font=ctk.CTkFont(size=12),
                    fg_color="transparent",
                    hover_color=("#0f1e33", "#0f1e33"),
                    text_color="#888", corner_radius=6,
                    command=lambda m=mode_name, s=sub_name: self._select_submode(m, s),
                )
                btn.grid(padx=(10, 6), pady=1, sticky="ew")
                self.sub_btns[mode_name][sub_name] = btn

            row += 1

        # ── Temperature Control ──────────────────────────────────────────────
        sep = ctk.CTkFrame(self.sidebar, height=1, fg_color="#1a2436")
        sep.grid(row=row, column=0, padx=14, pady=(18, 0), sticky="ew")
        row += 1

        ctk.CTkLabel(
            self.sidebar, text="  🌡  Temperature",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#555", anchor="w",
        ).grid(row=row, column=0, padx=10, pady=(12, 4), sticky="w")
        row += 1

        self.temp_var = ctk.DoubleVar(value=self.settings.get("temperature", 0.7))
        ctk.CTkSlider(
            self.sidebar, from_=0.0, to=2.0,
            variable=self.temp_var, number_of_steps=40,
            command=self._on_temp_change,
        ).grid(row=row, column=0, padx=14, sticky="ew")
        row += 1

        self.temp_lbl = ctk.CTkLabel(
            self.sidebar,
            text=f"  {self.temp_var.get():.1f}  —  {'低' if self.temp_var.get() < 0.6 else ('中' if self.temp_var.get() < 1.2 else '高')}創意",
            font=ctk.CTkFont(size=11), text_color="#555", anchor="w",
        )
        self.temp_lbl.grid(row=row, column=0, padx=10, pady=(2, 16), sticky="w")

        # initial selection is done after main area is built (banner widgets exist)

    # ── Main Content Area ─────────────────────────────────────────────────────

    def _build_main_area(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        self.tab_view = ctk.CTkTabview(
            main,
            fg_color=("#f0f0f0", "#0d1117"),
            segmented_button_fg_color=("#0a0f1e", "#060a14"),
            segmented_button_selected_color="#4A9EFF",
            segmented_button_selected_hover_color="#2979DD",
            segmented_button_unselected_color="#0a0f1e",
            segmented_button_unselected_hover_color="#111d2e",
            text_color="#ccc",
            text_color_disabled="#555",
        )
        self.tab_view.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        self.tab_view.add("  ✦ 單一轉換  ")
        self.tab_view.add("  📚 批次筆記本  ")

        self._build_single_tab(self.tab_view.tab("  ✦ 單一轉換  "))
        self._build_batch_tab(self.tab_view.tab("  📚 批次筆記本  "))

    def _build_single_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=0)   # mode banner
        parent.grid_rowconfigure(1, weight=1)   # input
        parent.grid_rowconfigure(2, weight=0)   # action bar
        parent.grid_rowconfigure(3, weight=1)   # output

        # ── Mode Banner ──────────────────────────────────────────────────────
        banner = ctk.CTkFrame(
            parent, height=88, corner_radius=0,
            fg_color=("#0f2040", "#0a1528"),
        )
        banner.grid(row=0, column=0, sticky="ew")
        banner.grid_propagate(False)
        banner.grid_columnconfigure(0, weight=1)
        banner.grid_rowconfigure(0, weight=0)
        banner.grid_rowconfigure(1, weight=0)

        # Row 0: mode name + desc
        inner = ctk.CTkFrame(banner, fg_color="transparent")
        inner.grid(row=0, column=0, padx=18, pady=(10, 0), sticky="w")

        self.banner_mode_lbl = ctk.CTkLabel(
            inner, text="", font=ctk.CTkFont(size=15, weight="bold"), text_color="#4A9EFF",
        )
        self.banner_mode_lbl.pack(side="left")
        self.banner_desc_lbl = ctk.CTkLabel(
            inner, text="", font=ctk.CTkFont(size=12), text_color="#666",
        )
        self.banner_desc_lbl.pack(side="left", padx=(10, 0), pady=(3, 0))

        # Row 1: recommendation badges
        reco_outer = ctk.CTkFrame(banner, fg_color="transparent")
        reco_outer.grid(row=1, column=0, padx=18, pady=(4, 0), sticky="ew")

        ctk.CTkLabel(
            reco_outer, text="推薦模型",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#A3BE8C",
        ).pack(side="left", padx=(0, 10))

        self.reco_row = ctk.CTkFrame(reco_outer, fg_color="transparent")
        self.reco_row.pack(side="left", fill="x", expand=True)

        self.reco_edit_btn = ctk.CTkButton(
            reco_outer, text="✎", width=26, height=22,
            fg_color="transparent", hover_color="#111d2e",
            font=ctk.CTkFont(size=12), command=self._edit_recommendation_for_current,
        )
        self.reco_edit_btn.pack(side="left", padx=(10, 0))

        # ── Input Section ──────────────────────────────────────────────────
        in_wrap = ctk.CTkFrame(parent, fg_color="transparent")
        in_wrap.grid(row=1, column=0, sticky="nsew", padx=16, pady=(14, 0))
        in_wrap.grid_columnconfigure(0, weight=1)
        in_wrap.grid_rowconfigure(1, weight=1)

        in_hdr = ctk.CTkFrame(in_wrap, fg_color="transparent")
        in_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(
            in_hdr, text="📥  輸入文字",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#ccc",
        ).pack(side="left")
        self.in_count_lbl = ctk.CTkLabel(
            in_hdr, text="0 字", font=ctk.CTkFont(size=11), text_color="#555",
        )
        self.in_count_lbl.pack(side="right")
        ctk.CTkButton(
            in_hdr, text="清除", width=52, height=24,
            fg_color="transparent", hover_color="#1a2030",
            border_width=1, border_color="#2a3a52", text_color="#777",
            font=ctk.CTkFont(size=11),
            command=self._clear_input,
        ).pack(side="right", padx=(0, 8))

        self.input_box = ctk.CTkTextbox(
            in_wrap, wrap="word",
            font=ctk.CTkFont(size=14),
            fg_color="#0d1117", border_color="#1e2e45",
            border_width=1, text_color="#dde",
            scrollbar_button_color="#1a2436",
        )
        self.input_box.grid(row=1, column=0, sticky="nsew")
        self.input_box.bind("<KeyRelease>", lambda _e: self._update_in_count())
        self.input_box.bind("<Control-Return>", lambda _e: self._process())

        # ── Action Bar ────────────────────────────────────────────────────────
        act = ctk.CTkFrame(parent, height=58, fg_color="transparent")
        act.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        act.grid_columnconfigure(0, weight=1)
        act.grid_propagate(False)

        self.progress = ctk.CTkProgressBar(
            act, mode="indeterminate", height=2, progress_color="#4A9EFF",
        )
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.progress.grid_remove()

        self.transform_btn = ctk.CTkButton(
            act, text="▶  立即轉換   (Ctrl+Enter)",
            height=38, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#4A9EFF", hover_color="#2266CC",
            command=self._process,
        )
        self.transform_btn.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        side_btns = ctk.CTkFrame(act, fg_color="transparent")
        side_btns.grid(row=1, column=1)

        _btn_cfg = dict(
            height=38, fg_color="transparent",
            hover_color="#0f1e33", border_width=1,
            border_color="#1e2e45", text_color="#999",
            font=ctk.CTkFont(size=12),
        )
        ctk.CTkButton(
            side_btns, text="📋 複製結果", width=100,
            command=self._copy_output, **_btn_cfg,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            side_btns, text="⬇ 移至輸入", width=100,
            command=self._move_to_input, **_btn_cfg,
        ).pack(side="left")

        # ── Output Section ────────────────────────────────────────────────────
        out_wrap = ctk.CTkFrame(parent, fg_color="transparent")
        out_wrap.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 14))
        out_wrap.grid_columnconfigure(0, weight=1)
        out_wrap.grid_rowconfigure(1, weight=1)

        out_hdr = ctk.CTkFrame(out_wrap, fg_color="transparent")
        out_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(
            out_hdr, text="📤  輸出結果",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#ccc",
        ).pack(side="left")
        self.out_count_lbl = ctk.CTkLabel(
            out_hdr, text="0 字", font=ctk.CTkFont(size=11), text_color="#555",
        )
        self.out_count_lbl.pack(side="right")

        self.output_box = ctk.CTkTextbox(
            out_wrap, wrap="word",
            font=ctk.CTkFont(size=14),
            fg_color="#080e1c", border_color="#1e2e45",
            border_width=1, text_color="#a8c8ff",
            scrollbar_button_color="#1a2436",
        )
        self.output_box.grid(row=1, column=0, sticky="nsew")

    # ── Batch Notebook Tab ────────────────────────────────────────────────────

    def _build_batch_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=0)   # toolbar
        parent.grid_rowconfigure(1, weight=1)   # job list

        # Toolbar
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))

        self.batch_run_btn = ctk.CTkButton(
            toolbar, text="▶▶  全部執行",
            height=32, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#4A9EFF", hover_color="#2266CC",
            command=self._run_batch_all,
        )
        self.batch_run_btn.pack(side="left")

        ctk.CTkButton(
            toolbar, text="＋  新增項目",
            height=32, font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="#111d2e",
            border_width=1, border_color="#1e2e45", text_color="#999",
            command=self._add_batch_job,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            toolbar, text="清除全部",
            height=32, font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="#2a0a0a",
            border_width=1, border_color="#3a1a1a", text_color="#888",
            command=self._clear_batch_jobs,
        ).pack(side="left", padx=(8, 0))

        self.batch_status_lbl = ctk.CTkLabel(
            toolbar, text="",
            font=ctk.CTkFont(size=12), text_color="#555",
        )
        self.batch_status_lbl.pack(side="right")

        # Scrollable job list
        self.batch_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color="#1e2a3a",
            scrollbar_button_hover_color="#2a3a52",
        )
        self.batch_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.batch_scroll.grid_columnconfigure(0, weight=1)

        # Batch state
        self._batch_jobs: list[dict] = []
        self._batch_running = False
        self._batch_job_counter = 0

        # Start with one empty job
        self._add_batch_job()

    def _add_batch_job(self) -> None:
        self._batch_job_counter += 1
        row = len(self._batch_jobs)

        job_outer = ctk.CTkFrame(
            self.batch_scroll,
            fg_color="#0d1117", border_width=1, border_color="#1e2e45",
            corner_radius=8,
        )
        job_outer.grid(row=row, column=0, sticky="ew", padx=4, pady=(0, 10))
        job_outer.grid_columnconfigure(0, weight=1)

        # Header row
        hdr = ctk.CTkFrame(job_outer, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            hdr, text=f"#{self._batch_job_counter}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#4A9EFF",
        ).pack(side="left")

        # Mode & submode dropdowns
        first, _ = first_mode()
        first_subs = list(MODES[first].submodes)
        mode_var = ctk.StringVar(value=first)
        submode_var = ctk.StringVar(value=first_subs[0])

        submode_menu = ctk.CTkOptionMenu(
            hdr, variable=submode_var, values=first_subs,
            width=160, height=28, font=ctk.CTkFont(size=12),
            fg_color="#0d1628", button_color="#1a2a40",
            button_hover_color="#1e3050",
        )

        def _on_mode_change(m: str, sm=submode_menu, sv=submode_var) -> None:
            subs = list(MODES[m].submodes)
            sm.configure(values=subs)
            sv.set(subs[0])

        mode_menu = ctk.CTkOptionMenu(
            hdr, variable=mode_var, values=list(MODES.keys()),
            width=180, height=28, font=ctk.CTkFont(size=12),
            fg_color="#0d1628", button_color="#1a2a40",
            button_hover_color="#1e3050",
            command=_on_mode_change,
        )
        mode_menu.pack(side="left", padx=(10, 4))
        submode_menu.pack(side="left", padx=(0, 8))

        status_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=11), text_color="#555",
        )
        status_lbl.pack(side="left")

        del_btn = ctk.CTkButton(
            hdr, text="✕", width=28, height=26,
            fg_color="transparent", hover_color="#3a0a0a",
            border_width=1, border_color="#2a1a1a", text_color="#666",
            font=ctk.CTkFont(size=11),
        )
        del_btn.pack(side="right")

        run_btn = ctk.CTkButton(
            hdr, text="▶  執行", width=72, height=26,
            fg_color="#1e3a5c", hover_color="#1a3050",
            text_color="#4A9EFF", font=ctk.CTkFont(size=12),
        )
        run_btn.pack(side="right", padx=(0, 6))

        # Input textbox
        in_box = ctk.CTkTextbox(
            job_outer, height=100, wrap="word",
            font=ctk.CTkFont(size=13),
            fg_color="#080d1a", border_color="#1e2e45",
            border_width=1, text_color="#dde",
            scrollbar_button_color="#1a2436",
        )
        in_box.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 4))

        # Output textbox
        out_box = ctk.CTkTextbox(
            job_outer, height=90, wrap="word",
            font=ctk.CTkFont(size=13),
            fg_color="#05090f", border_color="#1a2840",
            border_width=1, text_color="#a8c8ff",
            scrollbar_button_color="#1a2436",
        )
        out_box.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        job: dict = {
            "frame": job_outer,
            "mode_var": mode_var,
            "submode_var": submode_var,
            "run_btn": run_btn,
            "status_lbl": status_lbl,
            "input_box": in_box,
            "output_box": out_box,
        }
        self._batch_jobs.append(job)

        run_btn.configure(command=lambda j=job: self._run_single_batch_job(j))
        del_btn.configure(command=lambda j=job: self._delete_batch_job(j))

    def _delete_batch_job(self, job: dict) -> None:
        job["frame"].destroy()
        if job in self._batch_jobs:
            self._batch_jobs.remove(job)

    def _clear_batch_jobs(self) -> None:
        for job in list(self._batch_jobs):
            job["frame"].destroy()
        self._batch_jobs.clear()
        self._add_batch_job()

    def _run_single_batch_job(self, job: dict) -> None:
        text = job["input_box"].get("1.0", "end-1c").strip()
        if not text:
            return
        if not self.llm:
            job["status_lbl"].configure(text="⚠️ 未連接", text_color="#FF9F43")
            return

        system, user = build_messages(job["mode_var"].get(), job["submode_var"].get(), text)
        llm = self.llm
        temperature = self.settings.get("temperature", 0.7)

        job["status_lbl"].configure(text="⏳ 執行中…", text_color="#FF9F43")
        job["run_btn"].configure(state="disabled")
        job["output_box"].delete("1.0", "end")

        def worker() -> None:
            run_completion(
                llm, system, user, temperature,
                on_token=lambda tok: self.after(0, lambda t=tok: self._job_append(job, t)),
                on_done=lambda final: self.after(0, lambda f=final: self._job_done(job, f)),
                on_error=lambda exc: self.after(0, lambda e=exc: self._job_failed(job, e)),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _run_batch_all(self) -> None:
        if self._batch_running:
            return
        if not self.llm:
            messagebox.showwarning("未連接", "請先連接 API")
            return

        # Collect all data on the main thread before spawning background thread
        job_payloads: list[dict] = []
        for job in self._batch_jobs:
            text = job["input_box"].get("1.0", "end-1c").strip()
            if not text:
                continue
            system, user = build_messages(job["mode_var"].get(), job["submode_var"].get(), text)
            job_payloads.append({"job": job, "system": system, "user": user})

        if not job_payloads:
            messagebox.showwarning("無任務", "請先在至少一個項目中輸入文字")
            return

        # Pre-clear outputs on main thread
        for payload in job_payloads:
            payload["job"]["output_box"].delete("1.0", "end")
            payload["job"]["status_lbl"].configure(text="⏳ 等待…", text_color="#555")
            payload["job"]["run_btn"].configure(state="disabled")

        self._batch_running = True
        total = len(job_payloads)
        llm = self.llm
        temperature = self.settings.get("temperature", 0.7)
        self.batch_run_btn.configure(
            text="⏳ 執行中…", state="disabled",
            fg_color="#152236", text_color="#4A9EFF",
        )
        self.batch_status_lbl.configure(text=f"0 / {total}", text_color="#FF9F43")

        def run_all() -> None:
            for i, payload in enumerate(job_payloads):
                job = payload["job"]
                self.after(0, lambda j=job: j["status_lbl"].configure(text="⏳ 執行中…", text_color="#FF9F43"))
                run_completion(
                    llm, payload["system"], payload["user"], temperature,
                    on_token=lambda tok, j=job: self.after(0, lambda t=tok, _j=j: self._job_append(_j, t)),
                    on_done=lambda final, j=job: self.after(0, lambda f=final, _j=j: self._job_done(_j, f)),
                    on_error=lambda exc, j=job: self.after(0, lambda e=exc, _j=j: self._job_failed(_j, e)),
                )
                done = i + 1
                self.after(0, lambda d=done, t=total: self.batch_status_lbl.configure(
                    text=f"{d} / {t}", text_color="#4A9EFF",
                ))

            self._batch_running = False
            self.after(0, lambda: self.batch_run_btn.configure(
                text="▶▶  全部執行", state="normal",
                fg_color="#4A9EFF", text_color="white",
            ))
            self.after(0, lambda: self.batch_status_lbl.configure(
                text=f"✓ 全部完成 ({total})", text_color="#4CAF50",
            ))

        threading.Thread(target=run_all, daemon=True).start()

    # 下面三個都在 UI 執行緒被呼叫；工作列可能在執行中被使用者刪掉，所以先確認還在
    def _job_append(self, job: dict, token: str) -> None:
        if job["frame"].winfo_exists():
            job["output_box"].insert("end", token)
            job["output_box"].see("end")

    def _job_done(self, job: dict, final_text: str | None) -> None:
        if not job["frame"].winfo_exists():
            return
        box = job["output_box"]
        if final_text is not None and final_text != box.get("1.0", "end-1c"):
            box.delete("1.0", "end")
            box.insert("end", final_text)
        job["status_lbl"].configure(text="✓ 完成", text_color="#4CAF50")
        job["run_btn"].configure(state="normal")

    def _job_failed(self, job: dict, exc: Exception) -> None:
        if not job["frame"].winfo_exists():
            return
        job["output_box"].delete("1.0", "end")
        job["output_box"].insert("end", f"❌ API 呼叫失敗：\n{exc}")
        job["status_lbl"].configure(text="❌ 錯誤", text_color="#FF6B6B")
        job["run_btn"].configure(state="normal")

    # ── Status Bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(
            self, height=28, corner_radius=0,
            fg_color=("#060a14", "#060a14"),
        )
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        self.status_lbl = ctk.CTkLabel(
            bar, text="● 就緒",
            font=ctk.CTkFont(size=11), text_color="#4CAF50",
        )
        self.status_lbl.grid(row=0, column=0, padx=14, pady=4, sticky="w")

        self.status_info_lbl = ctk.CTkLabel(
            bar, text="",
            font=ctk.CTkFont(size=11), text_color="#444",
        )
        self.status_info_lbl.grid(row=0, column=1, padx=10, pady=4, sticky="w")

        ctk.CTkLabel(
            bar, text="Ctrl+Enter 快速轉換",
            font=ctk.CTkFont(size=10), text_color="#2a3a50",
        ).grid(row=0, column=2, padx=14, pady=4, sticky="e")

    # ── Sidebar Interaction ───────────────────────────────────────────────────

    def _toggle_mode(self, mode_name: str) -> None:
        frame = self.sub_frames[mode_name]
        btn = self.mode_btns[mode_name]
        if frame.winfo_ismapped():
            frame.grid_remove()
            btn.configure(text_color="#888")
        else:
            frame.grid()
            btn.configure(text_color="#eee")
            self.current_mode = mode_name
            # auto-select first submode if current one doesn't belong to this mode
            if self.current_submode not in MODES[mode_name].submodes:
                first_sub = next(iter(MODES[mode_name].submodes))
                self._select_submode(mode_name, first_sub)

    def _select_submode(self, mode_name: str, sub_name: str) -> None:
        # Deselect all
        for m_btns in self.sub_btns.values():
            for b in m_btns.values():
                b.configure(fg_color="transparent", text_color="#777")
        # Select chosen
        self.sub_btns[mode_name][sub_name].configure(
            fg_color=("#112240", "#0f1e38"), text_color="#ddd",
        )
        # Make parent mode header bright
        self.mode_btns[mode_name].configure(text_color="#eee")

        self.current_mode = mode_name
        self.current_submode = sub_name

        # Update banner
        sub_data = MODES[mode_name].submodes[sub_name]
        self.banner_mode_lbl.configure(text=f"{mode_name}  ›  {sub_name}")
        self.banner_desc_lbl.configure(text=sub_data.desc)
        self._update_status_info()
        self._update_recommendations_display()

    # ── API Key Entry ─────────────────────────────────────────────────────────

    def _toggle_key_visibility(self) -> None:
        self._show_key = not self._show_key
        self.api_key_entry.configure(show="" if self._show_key else "•")

    # ── Settings callbacks ────────────────────────────────────────────────────

    def _on_model_change(self, _val: str) -> None:
        model = self.model_var.get()
        self.settings.setdefault("models", {})[self.provider] = model
        save_settings(self.settings)
        if self.llm:
            self.llm.model = model
        self._update_status_info()

    # ── Provider / API key ────────────────────────────────────────────────────

    def _find_key(self, provider: str) -> tuple[str, str]:
        if not needs_key(provider):
            return "", ""
        key, source = find_key(provider, KEY_FILES)
        if not key and provider == "openai":
            key = legacy_api_key()
            source = str(LEGACY_SETTINGS_FILE) if key else ""
        return key, source

    def _saved_model(self, provider: str) -> str:
        return self.settings.get("models", {}).get(provider) or DEFAULT_MODELS[provider]

    def _show_key_source(self) -> None:
        src = self._key_source
        if not needs_key(self.provider):
            text = "用 Claude Code 登入的帳號，不需要金鑰"
        elif not src:
            text = ""
        elif src.startswith("環境變數"):
            text = f"已自{src}載入"
        else:
            text = f"已自 {Path(src).name} 載入"
        self.key_source_lbl.configure(text=text)

    def _apply_key_ui(self) -> None:
        """Claude 訂閱不需要金鑰：金鑰欄停用，「連接」改成檢查電腦上的 Claude Code（不花錢）。"""
        keyless = not needs_key(self.provider)
        state = "disabled" if keyless else "normal"
        self.api_key_entry.configure(state=state)
        self.eye_btn.configure(state=state)
        self.connect_btn.configure(text="檢查 Claude Code" if keyless else "連接 API", width=120 if keyless else 82)
        self._show_key_source()

    def _on_provider_change(self, label: str) -> None:
        provider = next(k for k, v in PROVIDERS.items() if v == label)
        if provider == self.provider:
            return
        self.provider = provider
        self.settings["provider"] = provider
        save_settings(self.settings)
        self.llm = None
        key, self._key_source = self._find_key(provider)
        self.api_key_entry.configure(state="normal")   # 停用中的欄位改不了內容，先打開再設
        self.api_key_var.set(key)
        self.available_models = FALLBACK_MODELS[provider].copy()
        self.model_menu.configure(values=self.available_models)
        self.model_var.set(self._saved_model(provider))
        self.api_status_lbl.configure(text="● 未連接", text_color="#FF6B6B")
        self.connect_btn.configure(state="normal")
        self._apply_key_ui()
        self._update_status_info()
        if key or not needs_key(provider):
            self._connect_api()

    def _on_temp_change(self, val: float) -> None:
        t = round(float(val), 1)
        self.settings["temperature"] = t
        label = "低" if t < 0.6 else ("中" if t < 1.2 else "高")
        self.temp_lbl.configure(text=f"  {t:.1f}  —  {label}創意")
        save_settings(self.settings)

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _update_in_count(self) -> None:
        n = len(self.input_box.get("1.0", "end-1c"))
        self.in_count_lbl.configure(text=f"{n} 字")

    def _update_out_count(self) -> None:
        n = len(self.output_box.get("1.0", "end-1c"))
        self.out_count_lbl.configure(text=f"{n} 字")

    def _update_status_info(self) -> None:
        m = self.model_var.get()
        mode = self.current_mode.split(" ", 1)[-1]
        sub = self.current_submode
        self.status_info_lbl.configure(text=f"模型: {m}  |  {mode} › {sub}")

    def _update_recommendations_display(self) -> None:
        import re
        # Clear old widgets
        for w in self.reco_row.winfo_children():
            w.destroy()

        try:
            rec_str: str = self.recommendations.get(self.current_mode, {}).get(self.current_submode, "") or ""
        except Exception:
            rec_str = ""

        if not rec_str.strip():
            ctk.CTkLabel(
                self.reco_row, text="暫無測評",
                font=ctk.CTkFont(size=12), text_color="#333",
            ).pack(side="left")
            return

        # -- Operator display labels ---------------------------------------
        _OP_DISPLAY = {
            ">>": (u"\u226b", "#FF9F43"),
            ">" : (u"\u203a",  "#FFD166"),
            ">=": (u"\u2265", "#A3BE8C"),
            "=" : (u"\u2248", "#74B9FF"),
        }

        # Split into (model | operator) tokens, keeping operators
        tokens = re.split(r'(\s*(?:>>|>=|>|=)\s*)', rec_str)

        rank = 0  # track model rank for badge colour
        _RANK_COLORS = [
            ("#4A9EFF", "#0d2240", "#4A9EFF"),   # 1st -- vivid blue
            ("#A3BE8C", "#0d2218", "#A3BE8C"),   # 2nd -- green
            ("#74B9FF", "#0a1a2e", "#4a80cc"),   # 3rd -- soft blue
        ]
        _DEFAULT_COLORS = ("#888", "#1a1a2e", "#555")

        for tok in tokens:
            stripped = tok.strip()
            if not stripped:
                continue

            if stripped in _OP_DISPLAY:
                sym, color = _OP_DISPLAY[stripped]
                ctk.CTkLabel(
                    self.reco_row, text=f" {sym} ",
                    font=ctk.CTkFont(size=16, weight="bold"), text_color=color,
                    anchor="center",
                ).pack(side="left")
            else:
                tc, fg, bc = _RANK_COLORS[rank] if rank < len(_RANK_COLORS) else _DEFAULT_COLORS
                model_id = stripped
                btn = ctk.CTkButton(
                    self.reco_row, text=model_id,
                    height=26, font=ctk.CTkFont(size=12, weight="bold"),
                    fg_color=fg, hover_color="#1e3a62",
                    border_width=1, border_color=bc,
                    text_color=tc, corner_radius=6,
                    command=lambda m=model_id: self._pick_model(m),
                )
                btn.pack(side="left", padx=(0, 2))
                rank += 1

    def _pick_model(self, model_id: str) -> None:
        self.model_var.set(model_id)
        self._on_model_change(model_id)
        prev_color = self.status_lbl.cget("text_color")
        self.status_lbl.configure(text=f"● 已切換模型 → {model_id}", text_color="#4A9EFF")
        self.after(2500, lambda: self.status_lbl.configure(
            text="● 就緒", text_color="#4CAF50",
        ))

    def _edit_recommendation_for_current(self) -> None:
        cur = self.recommendations.get(self.current_mode, {}).get(self.current_submode, "")
        ans = simpledialog.askstring(
            "編輯推薦模型",
            "用比較符號連接模型（>> 明顯優於 | > 優於 | >= 不亞於 | = 相當）\n\n範例：gpt-5.1 >> gpt-5.2 = gpt-5.4",
            initialvalue=cur,
            parent=self,
        )
        if ans is None:
            return
        if self.current_mode not in self.recommendations:
            self.recommendations[self.current_mode] = {}
        self.recommendations[self.current_mode][self.current_submode] = ans.strip()
        save_recommendations(self.recommendations)
        self._update_recommendations_display()

    def _clear_input(self) -> None:
        self.input_box.delete("1.0", "end")
        self._update_in_count()

    # ── API Connection ────────────────────────────────────────────────────────

    def _try_connect_api(self) -> None:
        # 有金鑰、或是不需要金鑰的 Claude 訂閱（只檢查 Claude Code 在不在，不花錢）就自動連接
        if self.api_key_var.get().strip() or not needs_key(self.provider):
            self._connect_api(silent=True)

    def _connect_api(self, silent: bool = False) -> None:
        api_key = self.api_key_var.get().strip()
        if needs_key(self.provider) and not api_key:
            messagebox.showwarning("API Key", f"請先輸入 {PROVIDERS[self.provider]} 的 API Key")
            return

        provider, model = self.provider, self.model_var.get()
        busy = "連接中…" if needs_key(provider) else "檢查中…"
        self.connect_btn.configure(text=busy, state="disabled")
        self.api_status_lbl.configure(text=f"● {busy}", text_color="#FF9F43")

        def worker() -> None:
            try:
                llm = LLM(provider, model, api_key=api_key or None)
                models = llm.list_models()
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda e=exc: self._on_connect_fail(provider, str(e), silent))
                return
            self.after(0, lambda: self._on_connect_ok(llm, models, api_key))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connect_ok(self, llm: LLM, models: list[str], api_key: str) -> None:
        if llm.provider != self.provider:  # 連線途中使用者換了服務，這個結果已經過時
            return
        self.llm = llm
        self.available_models = models or FALLBACK_MODELS[llm.provider].copy()
        # 手動輸入的新金鑰（或 v1 設定檔裡的舊金鑰）存進共用金鑰檔，其他工具也讀得到；
        # 本來就從環境變數 / keys.env / .env 讀到的就不重複存
        keyless = not needs_key(llm.provider)
        if not keyless and find_key(llm.provider, KEY_FILES)[0] != api_key:
            save_key(llm.provider, api_key)
            self._key_source = str(keys_file())
            self._show_key_source()
        self.api_status_lbl.configure(text="● Claude Code 可用" if keyless else "● 已連接", text_color="#4CAF50")
        self.connect_btn.configure(text="重新檢查" if keyless else "重新連接", state="normal")
        self.model_menu.configure(values=self.available_models)
        if self.model_var.get() not in self.available_models:
            default = DEFAULT_MODELS[llm.provider]
            self.model_var.set(default if default in self.available_models else self.available_models[0])
        llm.model = self.model_var.get()
        self.status_lbl.configure(text="● Claude Code 可用" if keyless else "● API 已連接", text_color="#4CAF50")
        self._update_status_info()

    def _on_connect_fail(self, provider: str, msg: str, silent: bool = False) -> None:
        if provider != self.provider:
            return
        self.api_status_lbl.configure(text="● 連接失敗", text_color="#FF6B6B")
        self.connect_btn.configure(text="重試", state="normal")
        if silent:   # 啟動時的自動連線：只顯示在狀態列，不要每次開程式都跳視窗；按「重試」才看完整原因
            first = (msg.strip().splitlines() or ["連接失敗"])[0][:90]
            self.status_lbl.configure(text=f"● {first}（按「重試」看完整說明）", text_color="#FF6B6B")
            return
        self.status_lbl.configure(text="● API 連接失敗", text_color="#FF6B6B")
        messagebox.showerror("連接錯誤", f"無法連接到 {PROVIDERS[provider]}：\n\n{msg}")

    # ── Processing ────────────────────────────────────────────────────────────

    def _process(self) -> None:
        if self.is_processing:
            return
        text = self.input_box.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("輸入為空", "請先在輸入框中貼上要轉換的文字。")
            return

        system, user = build_messages(self.current_mode, self.current_submode, text)
        if not self.llm:
            self._show_offline()
            return

        self._start_stream(system, user)

    def _show_offline(self) -> None:
        how = ("請先安裝並登入 Claude Code（見 README），再按上方「檢查 Claude Code」。\n"
               if not needs_key(self.provider) else
               "請在上方選擇服務、輸入 API Key 並點擊「連接 API」。\n")
        msg = (
            "⚠️  API 尚未連接 — 離線模式\n\n"
            f"{how}"
            "連接後即可開始轉換。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"目前選擇：{self.current_mode}  ›  {self.current_submode}\n\n"
            "將使用以下 Prompt 呼叫 API：\n\n"
            f"{preview(self.current_mode, self.current_submode)}"
        )
        self._set_output(msg)

    def _start_stream(self, system: str, user: str) -> None:
        self.is_processing = True
        self.transform_btn.configure(
            text="⏳ 運算中…", state="disabled",
            fg_color="#152236", text_color="#4A9EFF",
        )
        self.progress.grid()
        self.progress.start()
        self.status_lbl.configure(text="● 處理中…", text_color="#FF9F43")

        self._set_output("")

        llm = self.llm
        temperature = self.settings.get("temperature", 0.7)

        def worker() -> None:
            run_completion(
                llm, system, user, temperature,
                on_token=lambda tok: self.after(0, lambda t=tok: self._append_output(t)),
                on_done=lambda final: self.after(0, lambda f=final: self._finish_ok(f)),
                on_error=lambda exc: self.after(
                    0, lambda e=exc: self._finish_err(f"[{llm.provider} | {llm.model}]\n{e}")),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _append_output(self, token: str) -> None:
        self.output_box.insert("end", token)
        self.output_box.see("end")
        self._update_out_count()

    def _finish_ok(self, final_text: str | None = None) -> None:
        # Claude 拒答改由 fallback 模型接手時，串流內容會混到前一個模型的片段，以最終結果為準
        if final_text is not None and final_text != self.output_box.get("1.0", "end-1c"):
            self._set_output(final_text)
        self._done_processing()
        self.status_lbl.configure(text="● 轉換完成 ✓", text_color="#4CAF50")
        self._update_out_count()

    def _finish_err(self, msg: str) -> None:
        self._done_processing()
        self.status_lbl.configure(text="● 發生錯誤", text_color="#FF6B6B")
        self._set_output(f"❌  API 呼叫失敗：\n\n{msg}")

    def _done_processing(self) -> None:
        self.is_processing = False
        self.transform_btn.configure(
            text="▶  立即轉換   (Ctrl+Enter)", state="normal",
            fg_color="#4A9EFF", text_color="white",
        )
        self.progress.stop()
        self.progress.grid_remove()

    # ── Output Helpers ────────────────────────────────────────────────────────

    def _set_output(self, text: str) -> None:
        self.output_box.delete("1.0", "end")
        if text:
            self.output_box.insert("end", text)
        self._update_out_count()

    def _copy_output(self) -> None:
        text = self.output_box.get("1.0", "end-1c")
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        prev = self.status_lbl.cget("text")
        prev_color = self.status_lbl.cget("text_color")
        self.status_lbl.configure(text="● 已複製到剪貼板 ✓", text_color="#4A9EFF")
        self.after(2000, lambda: self.status_lbl.configure(text=prev, text_color=prev_color))

    def _move_to_input(self) -> None:
        text = self.output_box.get("1.0", "end-1c")
        if not text:
            return
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", text)
        self._set_output("")
        self._update_in_count()
        self.status_lbl.configure(text="● 已移至輸入框", text_color="#4A9EFF")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    app = BetterPromptApp()
    app.mainloop()


if __name__ == "__main__":
    main()
