"""邊播邊產生的朗讀播放器。

舊版按下「生成並播放」要先把「全部」段落轉成語音才開始播，長文要等很久。現在：
- 背景執行緒只預先產生目前段落之後的 AHEAD 段（語音引擎也在這個執行緒建立，COM 的規定）。
- 播放與切換由主執行緒每 100 ms 呼叫一次 tick() 推進（Tk 的 after），不會卡住畫面。
- 換語速、聲音、引擎時，預先產生好的檔案作廢、從目前段落重新產生。
- 播過的語音檔隨播隨刪，關閉時整個暫存資料夾清掉。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Callable

from reader.tts import ENGINES

AHEAD = 3

Notify = Callable[[str, object], None]   # (事件, 資料)；可能從背景執行緒呼叫，UI 要自己轉回主執行緒


class Player:
    def __init__(self, notify: Notify, engine: str = "sapi", voice: str = "", speed: float = 1.5):
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame

        self._mixer = pygame.mixer
        self._mixer.init()
        self.notify = notify
        self.segments: list[str] = []
        self.index = 0
        self.state = "stopped"           # stopped / playing / paused / waiting
        self._config = (engine, voice, speed)
        self._cache: dict[int, Path] = {}
        self._generation = 0
        self._cond = threading.Condition()
        self._closed = False
        self._loaded: Path | None = None
        self._tmp = Path(tempfile.mkdtemp(prefix="novel-reader-"))
        threading.Thread(target=self._produce, daemon=True, name="tts").start()

    # ------------------------------------------------------------------ 設定
    def configure(self, engine: str, voice: str, speed: float) -> None:
        with self._cond:
            if (engine, voice, round(speed, 2)) != (self._config[0], self._config[1], round(self._config[2], 2)):
                self._config = (engine, voice, speed)
                self._invalidate()

    def load(self, segments: list[str]) -> None:
        self.stop()
        with self._cond:
            self.segments = list(segments)
            self.index = 0
            self._invalidate()

    def _invalidate(self) -> None:
        self._generation += 1
        self._cache.clear()
        self._cond.notify_all()

    # ------------------------------------------------------------------ 控制（主執行緒）
    def play(self, index: int | None = None) -> None:
        if not self.segments:
            return
        if index is not None:
            self._stop_audio()
            with self._cond:
                self.index = max(0, min(index, len(self.segments) - 1))
                self._cond.notify_all()
        self._start_current()

    def toggle_pause(self) -> None:
        if self.state == "playing":
            self._mixer.music.pause()
            self.state = "paused"
            self.notify("paused", self.index)
        elif self.state == "paused":
            self._mixer.music.unpause()
            self.state = "playing"
            self.notify("playing", self.index)
        elif self.state == "stopped":
            self.play()

    def stop(self) -> None:
        self._stop_audio()
        self.state = "stopped"
        self.notify("stopped", self.index)

    def step(self, delta: int) -> None:
        if self.segments:
            self.play(self.index + delta)

    def tick(self) -> None:
        if self.state == "waiting":
            self._start_current()
        elif self.state == "playing" and not self._mixer.music.get_busy():
            if self.index + 1 >= len(self.segments):
                self._stop_audio()
                self.state = "stopped"
                self.notify("finished", self.index)
                return
            with self._cond:
                self.index += 1
                self._cond.notify_all()
            self._start_current()

    def close(self) -> None:
        self._closed = True
        with self._cond:
            self._cond.notify_all()
        self._stop_audio()
        self._mixer.quit()
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------ 內部
    def _stop_audio(self) -> None:
        self._mixer.music.stop()
        self._mixer.music.unload()     # 放掉檔案，暫存檔才刪得掉
        self._loaded = None

    def _start_current(self) -> None:
        with self._cond:
            path = self._cache.get(self.index)
            self._cond.notify_all()
        if path is None:
            if self.state != "waiting":
                self.state = "waiting"
                self.notify("waiting", self.index)
            return
        self._mixer.music.load(str(path))
        self._mixer.music.play()
        self._loaded = path
        self.state = "playing"
        self.notify("playing", self.index)
        self._prune()

    def _prune(self) -> None:
        with self._cond:
            old = [i for i in self._cache if i < self.index]
            for i in old:
                path = self._cache.pop(i)
                try:
                    path.unlink()
                except OSError:
                    pass

    def _produce(self) -> None:
        engine, engine_conf = None, None
        while not self._closed:
            with self._cond:
                end = min(len(self.segments), self.index + AHEAD)
                target = next((i for i in range(self.index, end) if i not in self._cache), None)
                if target is None:
                    self._cond.wait(0.5)
                    continue
                generation, (key, voice, speed) = self._generation, self._config
                text = self.segments[target]
            try:
                if engine is None or engine_conf != (key, voice):
                    if engine is not None:
                        engine.close()
                    engine, engine_conf = ENGINES[key](voice), (key, voice)
                path = engine.synthesize(text, self._tmp / f"{generation}_{target}", speed)
            except Exception as exc:  # noqa: BLE001 — 例如 Google 語音沒網路：通知畫面，稍後重試
                self.notify("error", f"產生第 {target + 1} 段語音失敗：{exc}")
                with self._cond:
                    self._cond.wait(3)
                continue
            with self._cond:
                if generation == self._generation and not self._closed:
                    self._cache[target] = path
                else:
                    path.unlink(missing_ok=True)
        if engine is not None:
            engine.close()
