"""把長文切成適合朗讀的段落（每段一個語音檔、一行字幕）。

規則（源自 gui_reader.py 的 split_into_segments）：
- 一個段落（換行分隔）至少是一段，空行略過。
- 超過 LIMIT 字的段落再切：在 LIMIT 以內找最後一個句尾符號（。！？；…）切開；
  找不到就硬切在 LIMIT。不會在「...」的中間切。
"""

from __future__ import annotations

LIMIT = 200
MIN_CUT = 40               # 句尾符號太前面的話不在那裡切（會切出很短的一段）
SENTENCE_ENDS = "。！？；!?;"


def _cut_point(text: str, limit: int) -> int:
    for i in range(min(limit, len(text)) - 1, MIN_CUT - 1, -1):
        ch = text[i]
        if ch in SENTENCE_ENDS or ch == "…":
            return i + 1
        if ch == "." and not (text[i - 1:i] == "." or text[i + 1:i + 2] == "."):
            return i + 1
    return limit


def split_into_segments(text: str, limit: int = LIMIT) -> list[str]:
    segments = []
    for paragraph in text.splitlines():
        para = paragraph.strip()
        while len(para) > limit:
            cut = _cut_point(para, limit)
            segments.append(para[:cut].strip())
            para = para[cut:].strip()
        if para:
            segments.append(para)
    return segments
