"""逐字稿 → Notion 筆記（呼叫 LLM 的部分）。

舊版只有一句「請幫我進行重點整理」加上整份逐字稿，品質差的原因與這裡的對策：

- 模型不知道影片在講什麼 → 一起給標題、頻道、說明欄、章節（<video_info>），專有名詞也比較能校正。
- 所有影片同一套整理方式 → 依影片類型挑整理方案（profiles），可以再疊加料（modifiers）；
  選「自動」時先用一個便宜的呼叫判斷類型，結果記在 info.json，下次不用再判斷。
- 長影片一次塞進去容易漏掉中段 → 超過門檻就分段整理（每段保留細節）再合併。
- 標題、網址、長度等資訊由程式產生放在筆記最上面，不讓模型重抄（抄錯就麻煩了）。
- 多個工作同時跑時，LLM 呼叫用同一把鎖排隊，避免被限流（下載與轉錄則可以並行）。
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Callable

from toolzoo.ai import LLM
from toolzoo.ai.prompts import strip_outer_fence, wrap

from video_notes.naming import KIND_SHORT
from video_notes.profiles import AUTO, Plan, PromptLibrary
from video_notes.transcribe import Cancelled, Transcript, clock

NOTES_TEMPERATURE = 0.3      # 整理筆記要忠實，不要太有創意
CHUNK_CHARS = 15000          # 分段整理時每段的大小（字元）
DESCRIPTION_LIMIT = 1500     # 說明欄常有一長串連結與業配，截斷就好

Status = Callable[[str], None]
Token = Callable[[str], None]


@dataclass
class VideoContext:
    url: str
    kind: str
    title: str = ""
    uploader: str = ""
    duration: float = 0
    upload_date: str = ""
    description: str = ""
    chapters: list | None = None

    @classmethod
    def from_info(cls, url: str, kind: str, info: dict) -> "VideoContext":
        return cls(
            url=url, kind=kind, title=info.get("title", ""),
            uploader=info.get("uploader") or info.get("channel") or "",
            duration=info.get("duration") or 0, upload_date=info.get("upload_date") or "",
            description=info.get("description") or "", chapters=info.get("chapters"),
        )

    @property
    def date(self) -> str:
        d = self.upload_date
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else d

    def block(self, with_description: bool = True) -> str:
        lines = [f"標題：{self.title or '（未知）'}"]
        if self.uploader:
            lines.append(f"頻道：{self.uploader}")
        lines.append("類型：" + ("短影音" if self.kind == KIND_SHORT else "一般影片"))
        if self.duration:
            lines.append(f"長度：{clock(self.duration)}")
        if self.date:
            lines.append(f"發佈日期：{self.date}")
        if self.chapters:
            lines.append("章節：")
            lines += [f"- {clock(c.get('start_time', 0))} {c.get('title', '')}" for c in self.chapters]
        if with_description and self.description.strip():
            desc = self.description.strip()
            if len(desc) > DESCRIPTION_LIMIT:
                desc = desc[:DESCRIPTION_LIMIT] + "…（以下省略）"
            lines += ["說明欄：", desc]
        return wrap("\n".join(lines), "video_info")


def split_chunks(paragraphs: list[str], limit: int = CHUNK_CHARS) -> list[str]:
    """照段落切，不在段落中間切斷。"""
    chunks, current, size = [], [], 0
    for para in paragraphs:
        if current and size + len(para) > limit:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


class NoteWriter:
    def __init__(self, llm: LLM, library: PromptLibrary, *, lock: threading.Lock | None = None,
                 long_chars: int = 60000):
        self.llm = llm
        self.library = library
        self.lock = lock or threading.Lock()
        self.long_chars = long_chars

    # ---- LLM 呼叫（全部經過同一把鎖） ----
    def _ask(self, system: str, user: str, *, temperature: float, on_token: Token | None,
             cancel: threading.Event | None) -> str:
        final: dict = {}
        parts: list[str] = []
        with self.lock:
            for piece in self.llm.stream(system, user, temperature=temperature, final=final):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                parts.append(piece)
                if on_token:
                    on_token(piece)
        return final.get("text") or "".join(parts)

    # ---- 自動判斷影片類型 ----
    def classify(self, transcript: Transcript, ctx: VideoContext,
                 cancel: threading.Event | None = None) -> tuple[str, str]:
        excerpt = transcript.plain_text()[:3000]
        user = ctx.block() + "\n\n" + wrap(excerpt, "transcript_excerpt")
        answer = self._ask(self.library.classifier_system(), user, temperature=0, on_token=None, cancel=cancel)
        return self.library.parse_classification(answer)

    # ---- 寫筆記 ----
    def write(self, plan: Plan, profile_id: str, transcript: Transcript, ctx: VideoContext, *,
              on_status: Status | None = None, on_token: Token | None = None,
              cancel: threading.Event | None = None) -> str:
        status = on_status or (lambda _msg: None)
        composed = self.library.compose(profile_id, plan.modifiers, plan.focus, short=ctx.kind == KIND_SHORT)
        if composed.needs_timestamps:
            paragraphs = [f"[{clock(t)}] {text}" for t, text in transcript.paragraphs()]
        else:
            paragraphs = [text for _, text in transcript.paragraphs()]
        full = "\n\n".join(paragraphs)

        if len(full) <= self.long_chars:
            status("AI 整理筆記中…")
            user = ctx.block() + "\n\n" + wrap(full, "transcript")
            body = self._ask(composed.system, user, temperature=NOTES_TEMPERATURE, on_token=on_token, cancel=cancel)
        else:
            chunks = split_chunks(paragraphs)
            partial: list[str] = []
            for i, chunk in enumerate(chunks, start=1):
                status(f"長影片分段整理 {i}/{len(chunks)}…")
                system = self.library.compose_chunk(composed, plan.focus, i, len(chunks))
                user = ctx.block(with_description=False) + "\n\n" + wrap(chunk, "transcript", part=f"{i}/{len(chunks)}")
                partial.append(self._ask(system, user, temperature=NOTES_TEMPERATURE, on_token=None, cancel=cancel))
            status("合併各段筆記…")
            merged = "\n\n".join(wrap(p, "part", index=str(i)) for i, p in enumerate(partial, start=1))
            user = (ctx.block() + "\n\n以下是這支影片依時間順序分段整理的筆記，請依照指示合併成一份完整筆記，"
                    "刪除重複、把相關內容歸在一起：\n\n" + wrap(merged, "partial_notes"))
            body = self._ask(composed.system, user, temperature=NOTES_TEMPERATURE, on_token=on_token, cancel=cancel)

        return self.header(ctx, composed.profile.icon, composed.profile.name,
                           [m.name for m in composed.modifiers], plan.focus) + clean_body(body)

    @staticmethod
    def header(ctx: VideoContext, icon: str, profile_name: str, modifier_names: list[str], focus: str) -> str:
        meta = [f"🔗 {ctx.url}"]
        if ctx.uploader:
            meta.append(f"📺 {ctx.uploader}")
        if ctx.duration:
            meta.append(f"⏱ {clock(ctx.duration)}")
        if ctx.date:
            meta.append(f"📅 {ctx.date}")
        plan = f"{icon} {profile_name}" + "".join(f" + {n}" for n in modifier_names)
        if focus:
            plan += f"（關注：{focus}）"
        meta.append(plan)
        return f"# {ctx.title or ctx.url}\n\n> " + " · ".join(meta) + "\n\n---\n\n"


def clean_body(text: str) -> str:
    body = strip_outer_fence(text)
    # 模型偶爾還是會自己寫一個 # 大標題；標題已經由程式加在最上面了
    body = re.sub(r"\A#\s[^\n]*\n+", "", body)
    return body.strip() + "\n"


def resolve_profile(plan: Plan, cached_auto: str | None) -> str | None:
    """方案若是「自動」且之前判斷過，就沿用上次的結果；否則回傳 None 表示需要判斷。"""
    if plan.profile != AUTO:
        return plan.profile
    return cached_auto
