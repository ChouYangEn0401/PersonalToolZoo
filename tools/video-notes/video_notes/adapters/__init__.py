"""可換的 adapter：來源（source）、語音辨識（stt）、AI（llm）、輸出（render）。

每一層 = 一個 Protocol（同資料夾的 source.py / stt.py / llm.py / render.py）＋ 一個 Registry。
不做繼承階層：實作只要「長得像」Protocol（duck typing），註冊一個工廠函式即可：

    from video_notes.adapters import stt
    stt.REGISTRY.register("openai", lambda settings: OpenAIStt(settings), label="OpenAI 語音辨識")

每個 adapter 都要有兩個固定入口：
    capabilities() -> dict        能做什麼（UI 依此灰掉不可用的選項）；不連網、不花錢
    check() -> ToolError | None   快速自我檢查（金鑰有沒有設、套件與模型在不在）；不連網、不花錢
失敗一律丟 video_notes.errors.ToolError（見 errors.py）。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


def import_builtin(modules: tuple[str, ...]) -> None:
    """import video_notes.adapters.<名稱>（模組在 import 時自己註冊；重複呼叫沒有副作用）。"""
    for name in modules:
        importlib.import_module(f"video_notes.adapters.{name}")


@dataclass
class Entry(Generic[T]):
    name: str
    factory: Callable[..., T]
    label: str
    order: int = 100


class Registry(Generic[T]):
    """名稱 → 工廠函式。工廠收什麼參數由該層的 Protocol 文件決定（通常是 Settings）。"""

    def __init__(self, layer: str):
        self.layer = layer
        self._entries: dict[str, Entry[T]] = {}

    def register(self, name: str, factory: Callable[..., T], *, label: str = "", order: int = 100) -> None:
        self._entries[name] = Entry(name, factory, label or name, order)

    def names(self) -> list[str]:
        return [e.name for e in sorted(self._entries.values(), key=lambda e: (e.order, e.name))]

    def entries(self) -> list[Entry[T]]:
        return [self._entries[n] for n in self.names()]

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def create(self, name: str, *args: Any, **kwargs: Any) -> T:
        from video_notes.errors import Remedy, ToolError

        if name not in self._entries:
            raise ToolError("config_invalid", f"沒有這個{self.layer}：{name}",
                            remedy=Remedy("needs_config", f"可用的有：{', '.join(self.names()) or '無'}"))
        return self._entries[name].factory(*args, **kwargs)
