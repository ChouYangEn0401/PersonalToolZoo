"""Novel Reader —— 把小說（或任何長文）唸給你聽，像 KTV 一樣顯示目前這一段。

源自「My Internet Novel Reader」的 gui_reader.py；「My Voice Assistant」的 Google 語音併進來當第二種引擎。
"""

import json
import os
import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from reader.player import Player
from reader.segments import split_into_segments
from reader.tts import ENGINES, GoogleEngine, SapiEngine
from version import __version__


def settings_file() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home()) / "PersonalToolZoo" / "novel-reader"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def read_text_file(path: str) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp950", "utf-16", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class ReaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"Novel Reader v{__version__}")
        self.root.geometry("900x820")
        self.settings = load_settings()
        self.events: "queue.Queue" = queue.Queue()
        self.current_file = ""
        self.engine = tk.StringVar(value=self.settings.get("engine", SapiEngine.key))
        self.voice = tk.StringVar(value=self.settings.get("voice", ""))
        self.speed = tk.DoubleVar(value=self.settings.get("speed", 1.5))
        self._voices_cache: dict[str, list[str]] = {}
        self._build()
        self._refresh_voices()
        self.player = Player(lambda kind, data: self.events.put((kind, data)),
                             self.engine.get(), self.voice.get(), self.speed.get())
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._loop)

    # ------------------------------------------------------------------ UI
    def _build(self):
        bar = ttk.Frame(self.root, padding=(10, 10, 10, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="開啟 .txt", command=self._open_file).pack(side="left")
        ttk.Button(bar, text="貼上", command=self._paste).pack(side="left", padx=4)
        ttk.Button(bar, text="清除", command=self._clear).pack(side="left")
        ttk.Label(bar, text="引擎").pack(side="left", padx=(16, 4))
        engine_box = ttk.Combobox(bar, state="readonly", width=20,
                                  values=[cls.label for cls in ENGINES.values()])
        engine_box.set(ENGINES.get(self.engine.get(), SapiEngine).label)
        engine_box.bind("<<ComboboxSelected>>", lambda _e: self._on_engine(engine_box.get()))
        engine_box.pack(side="left")
        ttk.Label(bar, text="聲音").pack(side="left", padx=(10, 4))
        self.voice_box = ttk.Combobox(bar, textvariable=self.voice, state="readonly", width=34)
        self.voice_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_config())
        self.voice_box.pack(side="left")

        speed_row = ttk.Frame(self.root, padding=(10, 0))
        speed_row.pack(fill="x")
        ttk.Label(speed_row, text="語速").pack(side="left")
        ttk.Scale(speed_row, from_=0.6, to=3.0, variable=self.speed, length=300,
                  command=lambda _v: self._speed_changed()).pack(side="left", padx=6)
        self.speed_label = ttk.Label(speed_row, text="")
        self.speed_label.pack(side="left")

        ttk.Label(self.root, text="貼上或開啟文字（每個段落會分開朗讀，太長的段落會在句尾切開）",
                  padding=(10, 8, 10, 2)).pack(anchor="w")
        self.text = ScrolledText(self.root, height=7, wrap="word", font=("Microsoft JhengHei UI", 11))
        self.text.pack(fill="x", padx=10)

        controls = ttk.Frame(self.root, padding=10)
        controls.pack(fill="x")
        ttk.Button(controls, text="▶ 從頭播放", command=self._play_from_start).pack(side="left")
        ttk.Button(controls, text="⏯ 暫停 / 繼續", command=self._toggle).pack(side="left", padx=4)
        ttk.Button(controls, text="⏹ 停止", command=lambda: self.player.stop()).pack(side="left")
        ttk.Button(controls, text="⏮ 上一段", command=lambda: self.player.step(-1)).pack(side="left", padx=(16, 4))
        ttk.Button(controls, text="⏭ 下一段", command=lambda: self.player.step(1)).pack(side="left")
        ttk.Button(controls, text="刪除選取的段落", command=self._delete_selected).pack(side="right")

        list_frame = ttk.Frame(self.root, padding=(10, 0))
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Microsoft JhengHei UI", 11), activestyle="none",
                                  selectmode="extended", exportselection=False)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda _e: self._play_selected())
        self.listbox.bind("<Return>", lambda _e: self._play_selected())

        self.subtitle = tk.Label(self.root, text="貼上文字後按「▶ 從頭播放」，或雙擊清單裡的任一段從那裡開始",
                                 font=("Microsoft JhengHei UI", 18), wraplength=840, justify="center", pady=16)
        self.subtitle.pack(fill="x", padx=10)
        self.status = ttk.Label(self.root, text="", padding=(10, 0, 10, 8), foreground="#666")
        self.status.pack(anchor="w")
        self._speed_changed(save=False)

    # ------------------------------------------------------------------ 文字來源
    def _open_file(self):
        path = filedialog.askopenfilename(filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")])
        if not path:
            return
        self.current_file = path
        self.text.delete("1.0", "end")
        self.text.insert("1.0", read_text_file(path))
        self._prepare()
        last = self.settings.get("positions", {}).get(path)
        if last and 0 < last < len(self.player.segments):
            self._highlight(last)
            self.status.configure(text=f"已跳到上次讀到的第 {last + 1} 段，雙擊或按 Enter 從這裡繼續")

    def _paste(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        self.current_file = ""
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self._prepare()

    def _clear(self):
        self.player.stop()
        self.current_file = ""
        self.text.delete("1.0", "end")
        self.listbox.delete(0, "end")
        self.player.load([])

    def _prepare(self) -> bool:
        """把輸入框的文字切成段落，放進清單與播放器。"""
        segments = split_into_segments(self.text.get("1.0", "end"))
        if not segments:
            messagebox.showinfo("沒有內容", "請先貼上或開啟要朗讀的文字。")
            return False
        self.listbox.delete(0, "end")
        for i, seg in enumerate(segments, start=1):
            self.listbox.insert("end", f"{i:>4}  {seg}")
        self.player.load(segments)
        self.status.configure(text=f"共 {len(segments)} 段")
        return True

    def _delete_selected(self):
        picked = set(self.listbox.curselection())
        if not picked or not messagebox.askyesno("刪除段落", f"刪除選取的 {len(picked)} 段？"):
            return
        segments = [s for i, s in enumerate(self.player.segments) if i not in picked]
        self.listbox.delete(0, "end")
        for i, seg in enumerate(segments, start=1):
            self.listbox.insert("end", f"{i:>4}  {seg}")
        self.player.load(segments)

    # ------------------------------------------------------------------ 播放
    def _play_from_start(self):
        if self._prepare():
            self.player.play(0)

    def _play_selected(self):
        sel = self.listbox.curselection()
        if not self.player.segments:
            if not self._prepare():
                return
        self.player.play(sel[0] if sel else 0)

    def _toggle(self):
        if not self.player.segments and not self._prepare():
            return
        self.player.toggle_pause()

    def _on_engine(self, label):
        key = next(k for k, cls in ENGINES.items() if cls.label == label)
        self.engine.set(key)
        self._refresh_voices()
        self._apply_config()

    def _refresh_voices(self):
        key = self.engine.get()
        if key not in self._voices_cache:
            try:
                self._voices_cache[key] = ENGINES[key].list_voices()
            except Exception as exc:  # noqa: BLE001
                self._voices_cache[key] = []
                self.status.configure(text=f"讀不到語音清單：{exc}")
        voices = self._voices_cache[key]
        self.voice_box.configure(values=voices)
        if self.voice.get() not in voices:
            self.voice.set(SapiEngine.default_voice(voices) if key == SapiEngine.key else (voices[0] if voices else ""))

    def _speed_changed(self, save=True):
        self.speed_label.configure(text=f"{self.speed.get():.1f} 倍")
        if save and hasattr(self, "player"):
            self._apply_config()

    def _apply_config(self):
        self.player.configure(self.engine.get(), self.voice.get(), round(self.speed.get(), 1))
        self.settings.update(engine=self.engine.get(), voice=self.voice.get(), speed=round(self.speed.get(), 1))
        self._save()

    def _highlight(self, index):
        self.listbox.selection_clear(0, "end")
        if 0 <= index < self.listbox.size():
            self.listbox.selection_set(index)
            self.listbox.see(index)

    def _loop(self):
        self.player.tick()
        try:
            while True:
                kind, data = self.events.get_nowait()
                total = len(self.player.segments)
                if kind == "playing":
                    self._highlight(data)
                    self.subtitle.configure(text=self.player.segments[data])
                    self.status.configure(text=f"第 {data + 1} / {total} 段　·　{ENGINES[self.engine.get()].label}"
                                               f"　·　{self.speed.get():.1f} 倍")
                    self._remember(data)
                elif kind == "waiting":
                    self.status.configure(text=f"產生第 {data + 1} 段的語音中…")
                elif kind == "paused":
                    self.status.configure(text=f"已暫停在第 {data + 1} / {total} 段")
                elif kind == "finished":
                    self.subtitle.configure(text="讀完了 🎉")
                    self.status.configure(text=f"共 {total} 段，全部讀完")
                    self._remember(0)
                elif kind == "error":
                    self.status.configure(text=str(data))
        except queue.Empty:
            pass
        self.root.after(100, self._loop)

    def _remember(self, index):
        if self.current_file:
            self.settings.setdefault("positions", {})[self.current_file] = index
            self._save()

    def _save(self):
        try:
            settings_file().write_text(json.dumps(self.settings, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def _close(self):
        # 舊版在這裡把 root.destroy() 呼叫了兩次，關視窗時會丟例外
        self.player.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    ReaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
