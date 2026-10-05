"""組提示詞時共用的小工具。

原則：「指令」放 system，「要處理的資料」放 user 並用標籤包起來。這樣模型分得清楚
哪些是任務、哪些是素材——素材裡就算出現「請忽略以上指示」之類的句子，也只會被當成
文字處理（簡易的 prompt injection 防護），長文時也不會把素材誤當成指令的一部分。
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s*```(?:markdown|md|text)?\s*\n(?P<body>.*)\n```\s*$", re.DOTALL)


def wrap(text: str, tag: str = "text", **attrs: str) -> str:
    """把素材包進 <tag> ... </tag>。attrs 會變成標籤屬性，例如 wrap(t, "part", index="2")。"""
    attr = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return f"<{tag}{attr}>\n{text.strip()}\n</{tag}>"


def strip_outer_fence(text: str) -> str:
    """模型偶爾會把整份輸出包在 ```markdown ... ``` 裡，拆掉外層。"""
    match = _FENCE.match(text)
    return match.group("body").strip() if match else text.strip()
