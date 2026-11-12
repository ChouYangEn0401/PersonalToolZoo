"""多片合併（Collection）：好幾支影片各自的 analysis.json → 一份合併的 analysis（kind = "collection"）。

吃的是每支影片已經做好的 analysis（不是逐字稿），所以便宜；每支影片自己的筆記照舊保留。
怎麼合併由 AI 依「模式」決定（新聞 → 依事件去重歸類；課程 → 依課綱排序；電影解說 → 連貫敘事）。

存放：naming.collection_folder(...)，裡面 analysis.<slug>.json、notes.<slug>.md、outputs/、collection.json。

介面（第 0 波契約；第 2 波實作）：
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Member:
    folder: Path          # 影片資料夾
    analysis: Path        # 這支影片要用哪一份 analysis.<slug>.json


@dataclass
class CombineEstimate:
    members: int
    input_chars: int
    input_tokens: int     # 粗估（中文約 1 字 ≈ 1 token、英文約 4 字元 ≈ 1 token）
    calls: int            # 預計呼叫 AI 幾次（成員太多會分批合併）
    needs_confirm: bool   # 超過 settings.combine_confirm_tokens
    missing: list[str] = field(default_factory=list)   # 讀不到 analysis 的成員


def estimate(members: list[Member], settings) -> CombineEstimate:
    raise NotImplementedError("第 2 波實作")


def combine(members: list[Member], *, plan, settings, library, llm_factory=None, output_root: Path,
            title: str = "", lock: threading.Lock | None = None, emit: Callable[[str, dict], None] | None = None,
            cancel: threading.Event | None = None) -> dict:
    """合併並寫檔。回傳 {"folder", "analysis_file", "notes_file", "analysis", "outputs": {renderer: path}}。
    失敗丟 ToolError；成員讀不到時略過並在 analysis 標 quality flag "member_missing"（全部讀不到才失敗）。"""
    raise NotImplementedError("第 2 波實作")
