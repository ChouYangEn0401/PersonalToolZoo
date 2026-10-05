#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Better Prompt — AI Text Transformer
A beautiful GUI tool to transform text using the OpenAI API.
"""

import threading
import json
import os
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox
from tkinter import simpledialog

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from model_strategies import run_completion

# ─── Appearance ───────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ─── Persistent Settings ──────────────────────────────────────────────────────
SETTINGS_FILE = Path.home() / ".better_prompt_settings.json"
RECO_FILE = Path(__file__).parent / "model_recommendations.json"

# ─── Mode & Prompt Definitions ────────────────────────────────────────────────
MODES: dict = {
    "✨ 文字精練": {
        "color": "#4A9EFF",
        "submodes": {
            "基本整理": {
                "desc": "整理語句，讓文字更流暢有條理",
                "prompt": (
                    "你是一位專業的文字編輯。"
                    "請將以下文字整理得更精練、有條理，"
                    "保留所有重要資訊，語句更流暢自然。"
                    "不要增加原本沒有的內容，只做整理優化。\n\n"
                    "待整理文字：\n{text}"
                ),
            },
            "商務風格": {
                "desc": "轉換為專業商務文字表達",
                "prompt": (
                    "你是一位專業的商業文書編輯。"
                    "請將以下文字改寫成專業的商務風格，語言精練正式，"
                    "適合在商業場合使用。\n\n原文：\n{text}"
                ),
            },
            "學術風格": {
                "desc": "轉換為嚴謹的學術語言",
                "prompt": (
                    "你是一位學術寫作專家。"
                    "請將以下文字改寫成嚴謹的學術風格，"
                    "用詞精準，邏輯清晰，適合學術論文使用。\n\n原文：\n{text}"
                ),
            },
            "口語化": {
                "desc": "轉換為自然親切的口語風格",
                "prompt": (
                    "你是一位擅長溝通的寫作者。"
                    "請將以下文字改寫成自然流暢的口語風格，"
                    "親切易讀，就像在跟朋友說話一樣。\n\n原文：\n{text}"
                ),
            },
        },
    },
    "📋 精要摘要": {
        "color": "#FF6B9D",
        "submodes": {
            "重點摘要": {
                "desc": "提取文字的核心重點",
                "prompt": (
                    "你是一位專業的內容摘要專家。"
                    "請將以下文字整理成清楚的重點摘要，"
                    "提取最核心的資訊，去除冗餘內容。\n\n原文：\n{text}"
                ),
            },
            "一句話摘要": {
                "desc": "用 1-2 句話總結核心意思",
                "prompt": (
                    "請用最精簡的 1 到 2 句話，"
                    "總結以下文字的核心意思，要能抓住最關鍵的訊息。\n\n原文：\n{text}"
                ),
            },
            "條列式重點": {
                "desc": "整理成清楚的條列式重點",
                "prompt": (
                    "請將以下文字整理成清楚的條列式重點（使用 • 符號），"
                    "每點簡潔有力，涵蓋所有重要資訊。\n\n原文：\n{text}"
                ),
            },
            "執行摘要": {
                "desc": "適合給主管閱讀的執行摘要",
                "prompt": (
                    "請將以下內容整理成專業的執行摘要（Executive Summary），"
                    "格式包含：核心結論、主要重點（條列）、建議行動。"
                    "適合給決策者快速閱讀。\n\n原文：\n{text}"
                ),
            },
        },
    },
    "🚀 Prompt 優化": {
        "color": "#FF9F43",
        "submodes": {
            "ChatGPT Prompt": {
                "desc": "優化成更有效的 AI Prompt",
                "prompt": (
                    "你是一位 Prompt 工程專家。"
                    "請將以下描述優化成一個結構清晰、指令明確、效果更好的 ChatGPT/AI Prompt。"
                    "要包含角色定義、任務說明、輸出要求等要素。\n\n原始描述：\n{text}"
                ),
            },
            "程式碼說明": {
                "desc": "優化技術和程式碼說明文字",
                "prompt": (
                    "你是一位資深軟體工程師。"
                    "請將以下技術說明或程式碼描述優化成更清楚、結構更完整的技術文件，"
                    "包含必要的細節和說明。\n\n原始說明：\n{text}"
                ),
            },
            "AI 繪圖 Prompt": {
                "desc": "轉換為 AI 繪圖專用英文 Prompt",
                "prompt": (
                    "You are an expert at creating prompts for AI image generation tools "
                    "like Midjourney and Stable Diffusion. "
                    "Convert the following description into an effective English image generation prompt. "
                    "Include: subject details, art style, lighting, composition, quality modifiers "
                    "(e.g. highly detailed, 8k, masterpiece). Output ONLY the prompt.\n\n"
                    "Description: {text}"
                ),
            },
            "技術規格說明": {
                "desc": "整理成清楚的技術規格文件",
                "prompt": (
                    "你是一位技術專案管理專家。"
                    "請將以下需求描述整理成清楚的技術規格說明，"
                    "包含：功能說明、技術要求、驗收標準，適合給開發團隊使用。\n\n需求描述：\n{text}"
                ),
            },
        },
    },
    "💡 發散思考": {
        "color": "#A29BFE",
        "submodes": {
            "腦力激盪": {
                "desc": "發散思考，列出多個可能方向",
                "prompt": (
                    "你是一位創意思考教練。"
                    "請根據以下主題，進行發散性腦力激盪，"
                    "列出 10 個以上不同方向的想法和可能性，鼓勵跳脫框架。\n\n主題：\n{text}"
                ),
            },
            "文章發想": {
                "desc": "發想文章結構、論點和內容方向",
                "prompt": (
                    "你是一位內容策略師。"
                    "請根據以下主題，提供完整的文章結構建議："
                    "包含引言角度、主要論點、支持論據、結論方向，"
                    "以及可以增加深度的延伸觀點。\n\n主題：\n{text}"
                ),
            },
            "繪圖 Prompt 發散": {
                "desc": "發想多種繪圖風格和場景概念",
                "prompt": (
                    "你是一位視覺創意總監。"
                    "根據以下描述，發想 6 到 8 個不同風格和構圖方向的 AI 繪圖概念，"
                    "每個包含：場景描述、藝術風格、色調氛圍、構圖方式。\n\n原始概念：\n{text}"
                ),
            },
            "創意點子": {
                "desc": "提供創新解決方案和創意點子",
                "prompt": (
                    "你是一位創新顧問。"
                    "針對以下問題，提供多個創新、有趣且實際可行的解決方案，"
                    "從不同維度切入，鼓勵創意思考。\n\n問題 / 挑戰：\n{text}"
                ),
            },
        },
    },
    "🔍 研究討論": {
        "color": "#00CEC9",
        "submodes": {
            "多角度分析": {
                "desc": "從多個角度深入分析主題",
                "prompt": (
                    "你是一位資深分析師。"
                    "請從多個不同角度（支持方、反對方、中立方、各面向影響）"
                    "深入分析以下主題，提供平衡且全面的觀點。\n\n分析主題：\n{text}"
                ),
            },
            "資料補充": {
                "desc": "補充背景知識和相關重要資訊",
                "prompt": (
                    "你是一位知識淵博的研究員。"
                    "請根據以下內容，補充相關的背景知識、重要概念、成功案例和關鍵資訊，"
                    "讓內容更完整豐富。\n\n原始內容：\n{text}"
                ),
            },
            "反駁辯證": {
                "desc": "提出反駁觀點，深化思考",
                "prompt": (
                    "你是一位批判性思考專家。"
                    "針對以下論點，提出有力的反駁意見和不同觀點，"
                    "幫助全面檢視這個論點的合理性與局限性。\n\n論點：\n{text}"
                ),
            },
            "深度討論": {
                "desc": "深入探討，提供專業見解與延伸",
                "prompt": (
                    "你是一位各領域通才專家。"
                    "請針對以下主題進行深度討論："
                    "提供專業見解、具體案例、延伸思考，以及對未來的啟示。\n\n討論主題：\n{text}"
                ),
            },
        },
    },
    "📝 文件改寫": {
        "color": "#FD79A8",
        "submodes": {
            "全面改寫": {
                "desc": "保留意思，換全新表達方式",
                "prompt": (
                    "你是一位資深文字工作者。"
                    "請將以下文字全面改寫，使用完全不同的表達方式，"
                    "但保留所有核心意思和重要資訊，讓文字煥然一新。\n\n原文：\n{text}"
                ),
            },
            "正式化": {
                "desc": "提升文字的正式與專業程度",
                "prompt": (
                    "請將以下文字改寫成更正式、專業的版本，"
                    "適合在正式場合、官方文件或職場環境中使用，語言精準莊重。\n\n原文：\n{text}"
                ),
            },
            "簡化": {
                "desc": "用更簡單易懂的語言表達",
                "prompt": (
                    "你是一位擅長化繁為簡的寫作者。"
                    "請將以下文字改寫得更簡單易懂，使用日常語言表達，"
                    "讓一般人都能輕鬆理解，不改變核心意思。\n\n原文：\n{text}"
                ),
            },
            "擴展豐富": {
                "desc": "增加細節和深度，豐富內容",
                "prompt": (
                    "你是一位內容創作專家。"
                    "請將以下文字擴展豐富，增加相關細節、具體例子、背景說明和深度分析，"
                    "讓內容更完整充實，保持主題聚焦。\n\n原文：\n{text}"
                ),
            },
        },
    },
}

DEFAULT_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]


# ─── Settings Helpers ─────────────────────────────────────────────────────────

def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"api_key": "", "model": "gpt-4o-mini", "temperature": 0.7}


def load_recommendations() -> dict:
    try:
        if RECO_FILE.exists():
            with open(RECO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_recommendations(recs: dict) -> None:
    try:
        with open(RECO_FILE, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def read_dotenv(dotenv_path: Path) -> dict:
    data = {}
    if not dotenv_path.exists():
        return data
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                data[k] = v
    except Exception:
        pass
    return data


def save_settings(settings: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─── Main Application ─────────────────────────────────────────────────────────

class BetterPromptApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.recommendations = load_recommendations()
        # try to read .env in project root and merge API key if present
        project_env = Path(__file__).parent / ".env"
        env_vals = read_dotenv(project_env)
        self._env_loaded_from: str | None = None
        for key_name in ("OPENAI_API_KEY", "OPENAI_KEY", "API_KEY", "OPENAI_APIKEY", "OPENAIKEY"):
            if key_name in env_vals and env_vals[key_name]:
                if not self.settings.get("api_key"):
                    self.settings["api_key"] = env_vals[key_name]
                self._env_loaded_from = str(project_env)
                break
        self.client: "OpenAI | None" = None
        self.available_models: list[str] = DEFAULT_MODELS.copy()
        self.is_processing = False
        self.current_mode: str = list(MODES.keys())[0]
        self.current_submode: str = list(MODES[self.current_mode]["submodes"].keys())[0]

        self._setup_window()
        self._build_ui()
        # Attempt auto-connect if a key was saved
        self._try_connect_api()

    # ── Window Setup ──────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.title("Better Prompt  ✦  AI Text Transformer")
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
        first_mode = list(MODES.keys())[0]
        self._toggle_mode(first_mode)
        first_sub = list(MODES[first_mode]["submodes"].keys())[0]
        self._select_submode(first_mode, first_sub)

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

        ctk.CTkLabel(api, text="🔑", font=ctk.CTkFont(size=14)).pack(side="left")
        self.api_key_var = ctk.StringVar(value=self.settings.get("api_key", ""))
        self.api_key_entry = ctk.CTkEntry(
            api, textvariable=self.api_key_var,
            width=210, show="•", placeholder_text="sk-...",
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
        ctk.CTkButton(
            api, text="👁", width=30, height=28,
            fg_color="transparent", hover_color="#222",
            command=self._toggle_key_visibility,
            font=ctk.CTkFont(size=14),
        ).pack(side="left", padx=(0, 6))

        # show small env-loaded indicator if key loaded from .env
        if getattr(self, "_env_loaded_from", None):
            self.env_label = ctk.CTkLabel(api, text="已自 .env 載入", font=ctk.CTkFont(size=10), text_color="#A3BE8C")
            self.env_label.pack(side="left", padx=(0, 8))

        self.connect_btn = ctk.CTkButton(
            api, text="連接 API", width=82, height=28,
            fg_color="#4A9EFF", hover_color="#2979DD",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._connect_api,
        )
        self.connect_btn.pack(side="left", padx=(0, 14))

        self.api_status_lbl = ctk.CTkLabel(
            api, text="● 未連接",
            font=ctk.CTkFont(size=12), text_color="#FF6B6B",
        )
        self.api_status_lbl.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(api, text="模型:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 5))
        self.model_var = ctk.StringVar(value=self.settings.get("model", "gpt-4o-mini"))
        self.model_menu = ctk.CTkOptionMenu(
            api, values=DEFAULT_MODELS, variable=self.model_var,
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
            color = mode_data["color"]

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

            for sub_name, sub_data in mode_data["submodes"].items():
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
        first_mode = list(MODES.keys())[0]
        first_subs = list(MODES[first_mode]["submodes"].keys())
        mode_var = ctk.StringVar(value=first_mode)
        submode_var = ctk.StringVar(value=first_subs[0])

        submode_menu = ctk.CTkOptionMenu(
            hdr, variable=submode_var, values=first_subs,
            width=160, height=28, font=ctk.CTkFont(size=12),
            fg_color="#0d1628", button_color="#1a2a40",
            button_hover_color="#1e3050",
        )

        def _on_mode_change(m: str, sm=submode_menu, sv=submode_var) -> None:
            subs = list(MODES[m]["submodes"].keys())
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
        if not self.client:
            job["status_lbl"].configure(text="⚠️ 未連接", text_color="#FF9F43")
            return

        mode = job["mode_var"].get()
        submode = job["submode_var"].get()
        submodes = MODES[mode]["submodes"]
        if submode not in submodes:
            submode = list(submodes.keys())[0]
        prompt = submodes[submode]["prompt"].replace("{text}", text)
        model = self.model_var.get()
        temperature = self.settings.get("temperature", 0.7)

        job["status_lbl"].configure(text="⏳ 執行中…", text_color="#FF9F43")
        job["run_btn"].configure(state="disabled")
        job["output_box"].delete("1.0", "end")

        def worker() -> None:
            ob = job["output_box"]
            run_completion(
                client=self.client,
                model_id=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                on_token=lambda tok, _ob=ob: self.after(0, lambda t=tok, b=_ob: (b.insert("end", t), b.see("end"))),
                on_done=lambda: self.after(0, lambda: job["status_lbl"].configure(text="✓ 完成", text_color="#4CAF50")),
                on_error=lambda exc: self.after(0, lambda e=exc: job["status_lbl"].configure(text="❌ 錯誤", text_color="#FF6B6B")),
            )
            self.after(0, lambda: job["run_btn"].configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _run_batch_all(self) -> None:
        if self._batch_running:
            return
        if not self.client:
            messagebox.showwarning("未連接", "請先連接 API")
            return

        # Collect all data on the main thread before spawning background thread
        job_payloads: list[dict] = []
        for job in self._batch_jobs:
            text = job["input_box"].get("1.0", "end-1c").strip()
            if not text:
                continue
            mode = job["mode_var"].get()
            submode = job["submode_var"].get()
            submodes = MODES[mode]["submodes"]
            if submode not in submodes:
                submode = list(submodes.keys())[0]
            prompt = submodes[submode]["prompt"].replace("{text}", text)
            job_payloads.append({"job": job, "prompt": prompt})

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
        model = self.model_var.get()
        temperature = self.settings.get("temperature", 0.7)
        self.batch_run_btn.configure(
            text="⏳ 執行中…", state="disabled",
            fg_color="#152236", text_color="#4A9EFF",
        )
        self.batch_status_lbl.configure(text=f"0 / {total}", text_color="#FF9F43")

        def run_all() -> None:
            for i, payload in enumerate(job_payloads):
                job = payload["job"]
                prompt = payload["prompt"]
                self.after(0, lambda j=job: j["status_lbl"].configure(text="⏳ 執行中…", text_color="#FF9F43"))
                ob = job["output_box"]
                run_completion(
                    client=self.client,
                    model_id=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    on_token=lambda tok, _ob=ob: self.after(0, lambda t=tok, b=_ob: (b.insert("end", t), b.see("end"))),
                    on_done=lambda j=job: self.after(0, lambda _j=j: _j["status_lbl"].configure(text="✓ 完成", text_color="#4CAF50")),
                    on_error=lambda exc, j=job: self.after(0, lambda e=exc, _j=j: _j["status_lbl"].configure(text="❌ 錯誤", text_color="#FF6B6B")),
                )
                self.after(0, lambda j=job: j["run_btn"].configure(state="normal"))
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
            if self.current_submode not in MODES[mode_name]["submodes"]:
                first_sub = list(MODES[mode_name]["submodes"].keys())[0]
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
        sub_data = MODES[mode_name]["submodes"][sub_name]
        self.banner_mode_lbl.configure(text=f"{mode_name}  ›  {sub_name}")
        self.banner_desc_lbl.configure(text=sub_data["desc"])
        self._update_status_info()
        self._update_recommendations_display()

    # ── API Key Entry ─────────────────────────────────────────────────────────

    def _toggle_key_visibility(self) -> None:
        self._show_key = not self._show_key
        self.api_key_entry.configure(show="" if self._show_key else "•")

    # ── Settings callbacks ────────────────────────────────────────────────────

    def _on_model_change(self, _val: str) -> None:
        self.settings["model"] = self.model_var.get()
        save_settings(self.settings)
        self._update_status_info()

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
        if self.settings.get("api_key"):
            self._connect_api()

    def _connect_api(self) -> None:
        if not OPENAI_AVAILABLE:
            self.api_status_lbl.configure(text="● openai 未安裝", text_color="#FF9F43")
            messagebox.showerror(
                "缺少套件",
                "找不到 openai 套件。\n請執行：pip install openai",
            )
            return
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("API Key", "請先輸入 OpenAI API Key")
            return

        self.connect_btn.configure(text="連接中…", state="disabled")
        self.api_status_lbl.configure(text="● 連接中…", text_color="#FF9F43")

        def worker() -> None:
            try:
                client = OpenAI(api_key=api_key)
                resp = client.models.list()
                gpt_models = sorted(
                    [m.id for m in resp.data if "gpt" in m.id],
                    reverse=True,
                )
                self.client = client
                self.available_models = gpt_models or DEFAULT_MODELS.copy()
                self.settings["api_key"] = api_key
                save_settings(self.settings)
                self.after(0, self._on_connect_ok)
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_connect_fail(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connect_ok(self) -> None:
        self.api_status_lbl.configure(text="● 已連接", text_color="#4CAF50")
        self.connect_btn.configure(text="重新連接", state="normal")
        self.model_menu.configure(values=self.available_models)
        if self.model_var.get() not in self.available_models:
            self.model_var.set(self.available_models[0])
        self.status_lbl.configure(text="● API 已連接", text_color="#4CAF50")
        self._update_status_info()

    def _on_connect_fail(self, msg: str) -> None:
        self.api_status_lbl.configure(text="● 連接失敗", text_color="#FF6B6B")
        self.connect_btn.configure(text="重試", state="normal")
        self.status_lbl.configure(text="● API 連接失敗", text_color="#FF6B6B")
        messagebox.showerror("連接錯誤", f"無法連接到 OpenAI API：\n\n{msg}")

    # ── Processing ────────────────────────────────────────────────────────────

    def _process(self) -> None:
        if self.is_processing:
            return
        text = self.input_box.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("輸入為空", "請先在輸入框中貼上要轉換的文字。")
            return

        submodes = MODES[self.current_mode]["submodes"]
        if self.current_submode not in submodes:
            self.current_submode = list(submodes.keys())[0]
        sub_data = submodes[self.current_submode]
        prompt = sub_data["prompt"].replace("{text}", text)

        if not self.client:
            self._show_offline(sub_data["prompt"])
            return

        self._start_stream(prompt)

    def _show_offline(self, prompt_template: str) -> None:
        preview = prompt_template.replace("{text}", "（您的文字）")
        msg = (
            "⚠️  API 尚未連接 — 離線模式\n\n"
            "請在上方輸入 OpenAI API Key 並點擊「連接 API」。\n"
            "連接後即可開始轉換。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"目前選擇：{self.current_mode}  ›  {self.current_submode}\n\n"
            "將使用以下 Prompt 呼叫 API：\n\n"
            f"{preview}"
        )
        self._set_output(msg)

    def _start_stream(self, prompt: str) -> None:
        self.is_processing = True
        self.transform_btn.configure(
            text="⏳ 運算中…", state="disabled",
            fg_color="#152236", text_color="#4A9EFF",
        )
        self.progress.grid()
        self.progress.start()
        self.status_lbl.configure(text="● 處理中…", text_color="#FF9F43")

        self._set_output("")

        def worker() -> None:
            run_completion(
                client=self.client,
                model_id=self.model_var.get(),
                messages=[{"role": "user", "content": prompt}],
                temperature=self.settings.get("temperature", 0.7),
                on_token=lambda tok: self.after(0, lambda t=tok: self._append_output(t)),
                on_done=lambda: self.after(0, self._finish_ok),
                on_error=lambda exc: self.after(0, lambda e=exc: self._finish_err(str(e))),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _append_output(self, token: str) -> None:
        self.output_box.insert("end", token)
        self.output_box.see("end")
        self._update_out_count()

    def _finish_ok(self) -> None:
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
