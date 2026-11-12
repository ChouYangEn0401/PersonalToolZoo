"""輸出（render）adapter：analysis.json → 各種格式。不呼叫 AI、不連網（needs_llm=False 的都一樣）。

內建名稱（第 1 波實作，名字固定，UI／CLI／設定都用它）：

    markdown        Notion 筆記（就是原本的 notes.<slug>.md）
    tree-md         樹狀圖：Markdown 巢狀清單（可直接貼 Notion）
    tree-mermaid    樹狀圖：Mermaid mindmap（.mmd）
    tree-html       樹狀圖：可折疊的單檔 HTML
    tree-opml       樹狀圖：OPML（XMind、各種大綱軟體可匯入）
    tree-freemind   樹狀圖：FreeMind .mm（XMind 可匯入）
    tree-xmind      樹狀圖：.xmind（XMind 原生；zip + content.json）
    html-sheet      HTML 範本：一小張
    html-longform   HTML 範本：長文＋目錄
    html-tabs       HTML 範本：多分頁（課綱式）

輸出檔放在影片（或合併）資料夾的 outputs/ 底下：outputs/<slug>.<renderer>.<extension>
（markdown 例外：維持 notes.<slug>.md，舊資料夾與 socket 模式才相容）。見 naming.Artifacts.output()。

安全：analysis 裡的文字都是不可信的外部資料。HTML 一律跳脫或用 textContent；連結只允許 http/https；
不載入外部資源；不產生可執行內容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from video_notes.adapters import Registry
from video_notes.errors import ToolError


@dataclass
class RenderContext:
    """輸出時除了 analysis 以外的資訊。"""

    profile_name: str = ""      # 例如「📰 新聞快訊」（Markdown 標頭用）
    modifier_names: list[str] = field(default_factory=list)
    tool_version: str = ""


class Renderer(Protocol):
    name: str           # 上面的固定名稱
    label: str          # 給人看的，例如「樹狀圖（XMind）」
    extension: str      # 含點，例如 ".md"、".xmind"
    binary: bool        # True：render() 回傳 bytes

    def capabilities(self) -> dict:
        """{formats: [副檔名], needs_network: False, needs_llm: False, group: "notes"|"tree"|"html"}"""

    def check(self) -> ToolError | None: ...

    def render(self, analysis: dict, ctx: RenderContext) -> str | bytes: ...


REGISTRY: Registry[Renderer] = Registry("輸出格式")

BUILTIN_MODULES = ("render_markdown", "render_tree", "render_html")


def load_builtin() -> None:
    """import 內建實作（各自在 import 時註冊）。"""
    from video_notes.adapters import import_builtin

    import_builtin(BUILTIN_MODULES)


def get(name: str) -> Renderer:
    load_builtin()
    return REGISTRY.create(name)
