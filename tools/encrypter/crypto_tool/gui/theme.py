"""Theme constants and style helpers for CryptoTool Pro."""

# ── Warm-Gold dark palette ──────────────────────────────────────────────
GOLD_BRIGHT   = "#FFD700"   # pure gold
GOLD_MID      = "#C9A84C"   # satin gold  (headers, accents)
GOLD_DARK     = "#7A5C1E"   # deep gold   (borders, separators)
AMBER         = "#F59E0B"   # amber       (encrypt CTA)
AMBER_LIGHT   = "#FCD34D"   # light amber

ACCENT_ENCRYPT = "#C9A84C"   # gold   – encrypt action
ACCENT_DECRYPT = "#4CAF50"   # green  – decrypt action
ACCENT_WARN    = "#F59E0B"   # amber
ACCENT_DANGER  = "#EF4444"   # red

BG_DARK        = "#141210"   # near-black warm background
BG_CARD        = "#1E1C16"   # dark warm card
FG_LIGHT       = "#F5EED7"   # warm off-white
FG_MUTED       = "#9A8866"   # muted warm grey

DND_ACTIVE     = "#3D3519"   # entry highlight colour while dragging

FONT_TITLE    = ("Segoe UI", 13, "bold")
FONT_SUBTITLE = ("Segoe UI", 11, "bold")
FONT_BODY     = ("Segoe UI", 10)
FONT_MONO     = ("Consolas", 10)
FONT_SMALL    = ("Segoe UI", 9)

PAD = 12   # standard padding


# ── 新介面（v0.4 起的主視窗）────────────────────────────────────────────
# 上面的暖金色常數只剩舊版工具視窗在用。新介面直接用 ttkbootstrap 內建的兩個主題，
# 只有「拖放區」這種 ttk 樣式管不到的地方才用下面的顏色。規格見 docs/ui-spec.md。
THEME_LIGHT = "flatly"
THEME_DARK = "darkly"

PALETTE = {
    THEME_LIGHT: {
        "drop_bg": "#F4F7FA",      # 拖放區底色
        "drop_fg": "#5B6B7B",      # 拖放區提示字
        "drop_active": "#D6EAF8",  # 檔案拖到上面時
        "muted": "#6C7A89",        # 次要說明文字
    },
    THEME_DARK: {
        "drop_bg": "#2B3035",
        "drop_fg": "#AEB8C2",
        "drop_active": "#375A7F",
        "muted": "#9AA5B1",
    },
}

FONT_UI = ("Microsoft JhengHei UI", 10)
FONT_UI_BOLD = ("Microsoft JhengHei UI", 10, "bold")
FONT_UI_SMALL = ("Microsoft JhengHei UI", 9)
FONT_HEADING = ("Microsoft JhengHei UI", 16, "bold")
FONT_DROP = ("Microsoft JhengHei UI", 12)
FONT_BUTTON = ("Microsoft JhengHei UI", 11, "bold")

WINDOW_SIZE = (900, 780)
WINDOW_MIN = (760, 600)
GAP = 10      # 區塊之間
PAD_X = 18    # 分頁內容左右留白
