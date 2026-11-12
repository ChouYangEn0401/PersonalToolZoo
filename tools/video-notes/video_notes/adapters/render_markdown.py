"""輸出 adapter「markdown」：analysis → Notion 筆記（notes.<slug>.md）。不呼叫 AI、不連網。

標頭（# 標題、> 🔗 網址 · 📺 頻道 · ⏱ 長度 · 📅 日期 · 方案）沿用舊版 NoteWriter.header 的格式，由程式產生。
analysis 裡所有文字都是不可信的外部資料（影片標題、逐字稿、AI 輸出）：一律當純文字處理——
會被 Markdown／Notion 當成語法的字元（行首的 # > - + 1. =、行內的 * ` [ ] < > ~ \\）都跳脫，
所以 `<script>`、`[點我](javascript:…)`、`# 假標題` 都只會顯示成字面文字。連結只允許 http／https。
單一欄位太長會截斷（避免一個失控的欄位塞爆筆記）。
"""

from __future__ import annotations

import re
from urllib.parse import quote

from video_notes.adapters import render
from video_notes.errors import ToolError

MAX_TEXT = 4000        # 單一文字欄位的上限（字元）
MAX_TITLE = 300
MAX_ITEMS = 500        # 單一清單最多幾項

FLAG_NOTES = {
    "schema_repair_failed": "AI 沒有給出符合格式的分析結果，這份筆記是簡化版本；可以對這支影片選「重新分析」",
    "stt_fallback_local": "雲端語音辨識失敗，逐字稿是用本機模型辨識的，品質可能較差",
    "transcript_low_confidence": "語音辨識品質可疑，專有名詞可能有誤",
    "truncated_input": "逐字稿太長被截斷，後段內容可能沒有整理到",
    "member_missing": "合併時有些影片的分析結果讀不到，已略過",
}

_INLINE = re.compile(r"([\\`*\[\]<>~])")
_LINE_START = re.compile(r"^(\s*)(#|[-+=|]|\d+[.)])")
_URL_UNSAFE = re.compile(r"[\s<>\"`\\()\[\]]")


# --------------------------------------------------------------------------- 跳脫
def clip(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def esc_line(text: str) -> str:
    """一行純文字 → 不會被當成 Markdown 語法的一行（不含換行）。"""
    line = " ".join(str(text).split())
    line = _INLINE.sub(r"\\\1", line)
    return _LINE_START.sub(lambda m: m.group(1) + "\\" + m.group(2), line, count=1)


def esc(text, limit: int = MAX_TEXT) -> str:
    """單行：換行與連續空白壓成一個空格，截斷後跳脫。"""
    return esc_line(clip(" ".join(str(text or "").split()), limit))


def esc_paragraphs(text, limit: int = MAX_TEXT) -> str:
    """多行文字（概述）：保留段落與換行，每一行各自跳脫。"""
    lines = [esc_line(ln) for ln in clip(str(text or "").strip(), limit).splitlines()]
    return "\n".join(ln for ln in lines)


def safe_url(url) -> str:
    """只允許 http／https；其餘（javascript:、file:、空字串）回傳空字串。"""
    url = str(url or "").strip()
    if not re.match(r"(?i)^https?://[^\s]+$", url):
        return ""
    return _URL_UNSAFE.sub(lambda m: quote(m.group()), url)[:2000]


def clock(seconds) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
        return ""
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _items(value) -> list:
    return list(value)[:MAX_ITEMS] if isinstance(value, list) else []


# --------------------------------------------------------------------------- 標頭
def _plan_text(analysis: dict, ctx) -> str:
    mode = analysis.get("mode") or {}
    name = ctx.profile_name or mode.get("profile", "")
    mods = list(ctx.modifier_names) or list(mode.get("modifiers") or [])
    text = esc(name, 80) + "".join(f" + {esc(m, 40)}" for m in mods)
    if str(mode.get("focus", "")).strip():
        text += f"（關注：{esc(mode['focus'], 120)}）"
    return text.strip()


def _video_meta(src: dict) -> list[str]:
    meta = []
    url = safe_url(src.get("url"))
    if url:
        meta.append(f"🔗 {url}")
    if str(src.get("channel", "")).strip():
        meta.append(f"📺 {esc(src['channel'], 100)}")
    if clock(src.get("duration")) and src.get("duration"):
        meta.append(f"⏱ {clock(src['duration'])}")
    if str(src.get("date", "")).strip():
        meta.append(f"📅 {esc(src['date'], 30)}")
    return meta


def header(analysis: dict, ctx) -> list[str]:
    sources = [s for s in _items(analysis.get("sources")) if isinstance(s, dict)]
    title = esc(analysis.get("title") or (sources[0].get("url") if sources else "") or "untitled", MAX_TITLE)
    out = [f"# {title}", ""]
    plan = _plan_text(analysis, ctx)
    if analysis.get("kind") == "collection":
        meta = [f"📚 合併 {len(sources)} 支影片"] + ([plan] if plan else [])
        out += ["> " + " · ".join(meta), ""]
    else:
        meta = _video_meta(sources[0]) if sources else []
        if plan:
            meta.append(plan)
        if meta:
            out += ["> " + " · ".join(meta), ""]
    flags = [FLAG_NOTES[f] for f in _items(analysis.get("quality_flags")) if f in FLAG_NOTES]
    if flags:
        out += ["> ⚠ " + "；".join(flags), ""]
    out += ["---", ""]
    if analysis.get("kind") == "collection" and sources:
        out += ["## 來源影片", ""]
        for s in sources:
            bits = [esc(s.get("title") or s.get("id") or "", 120)]
            if str(s.get("channel", "")).strip():
                bits.append(esc(s["channel"], 60))
            if s.get("duration"):
                bits.append("⏱ " + clock(s["duration"]))
            if safe_url(s.get("url")):
                bits.append(safe_url(s["url"]))
            out.append("- " + " · ".join(b for b in bits if b))
        out.append("")
    return out


# --------------------------------------------------------------------------- 內容
def _sections(sections, depth: int = 1) -> list[str]:
    out: list[str] = []
    for sec in _items(sections):
        if not isinstance(sec, dict):
            continue
        title = esc(sec.get("title", ""), MAX_TITLE) or "（未命名）"
        when = clock(sec.get("start")) if sec.get("start") is not None else ""
        suffix = f"（{when}）" if when else ""
        if depth <= 2:
            out += [f"{'#' * (depth + 1)} {title}{suffix}", ""]
            if str(sec.get("summary", "")).strip():
                out += [esc(sec["summary"]), ""]
            out += [f"- {esc(p)}" for p in _items(sec.get("points")) if str(p).strip()]
            if out and out[-1] != "":
                out.append("")
        else:   # Notion 只有三層標題：更深的改用巢狀清單
            pad = "  " * (depth - 3)
            out.append(f"{pad}- **{title}**{suffix}" + (f"：{esc(sec['summary'])}" if str(sec.get("summary", "")).strip() else ""))
            out += [f"{pad}  - {esc(p)}" for p in _items(sec.get("points")) if str(p).strip()]
        out += _sections(sec.get("children"), depth + 1)
    return out


def _block(title: str, lines: list[str]) -> list[str]:
    return [f"## {title}", "", *lines, ""] if lines else []


def body(analysis: dict) -> list[str]:
    out: list[str] = []
    if str(analysis.get("summary", "")).strip():
        out += [f"**摘要**：{esc(analysis['summary'])}", ""]
    if str(analysis.get("overview", "")).strip():
        out += [esc_paragraphs(analysis["overview"]), ""]
    sec_lines = _sections(analysis.get("sections"))
    out += sec_lines
    if sec_lines and out[-1] != "":
        out.append("")

    out += _block("關鍵重點", [f"- {esc(p)}" for p in _items(analysis.get("key_points")) if str(p).strip()])

    timeline = []
    for t in _items(analysis.get("timeline")):
        if isinstance(t, dict) and str(t.get("label", "")).strip():
            when = clock(t.get("time"))
            line = f"- {'**' + when + '** ' if when else ''}{esc(t['label'])}"
            if str(t.get("detail", "")).strip():
                line += f"：{esc(t['detail'])}"
            timeline.append(line)
    out += _block("時間軸", timeline)

    terms = [f"- **{esc(t['term'], 120)}**：{esc(t.get('definition', ''))}"
             for t in _items(analysis.get("terms")) if isinstance(t, dict) and str(t.get("term", "")).strip()]
    out += _block("名詞解釋", terms)

    out += _block("行動清單", [f"- [ ] {esc(a)}" for a in _items(analysis.get("actions")) if str(a).strip()])

    quotes = []
    for q in _items(analysis.get("quotes")):
        if isinstance(q, dict) and str(q.get("text", "")).strip():
            who = " ".join(x for x in (esc(q.get("speaker", ""), 80), clock(q.get("time"))) if x)
            quotes.append(f"> {esc(q['text'])}" + (f" —— {who}" if who else ""))
            quotes.append("")
    out += _block("金句", quotes[:-1] if quotes else [])

    persp = [f"- **{esc(p['who'], 120)}**：{esc(p.get('stance', ''))}"
             for p in _items(analysis.get("perspectives")) if isinstance(p, dict) and str(p.get("who", "")).strip()]
    out += _block("各方說法", persp)

    out += _block("注意事項", [f"- {esc(c)}" for c in _items(analysis.get("caveats")) if str(c).strip()])

    tags = [esc(t, 40) for t in _items(analysis.get("tags")) if str(t).strip()]
    if tags:
        out += ["標籤：" + "、".join(tags), ""]
    return out


def render_markdown(analysis: dict, ctx) -> str:
    lines = header(analysis, ctx) + body(analysis)
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- adapter
class MarkdownRenderer:
    name = "markdown"
    label = "Notion 筆記（Markdown）"
    extension = ".md"
    binary = False

    def capabilities(self) -> dict:
        return {"formats": [".md"], "needs_network": False, "needs_llm": False, "group": "notes"}

    def check(self) -> ToolError | None:
        return None

    def render(self, analysis: dict, ctx: render.RenderContext) -> str:
        return render_markdown(analysis, ctx)


render.REGISTRY.register("markdown", lambda *args, **kwargs: MarkdownRenderer(), label=MarkdownRenderer.label, order=10)
