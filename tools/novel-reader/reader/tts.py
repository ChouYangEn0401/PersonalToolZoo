"""語音引擎：把一段文字變成一個音訊檔。

- SapiEngine：Windows 內建語音（離線、免費、很快）。直接呼叫 SAPI 的 COM 物件，不經過 pyttsx3——
  pyttsx3 2.99 在 Windows 上第二次 runAndWait() 就會永遠卡住（舊版不穩定的原因）。
- GoogleEngine：Google 線上語音（gTTS，需要網路，比較自然）。源自 My Voice Assistant。
  加速用 ffmpeg 的 atempo 濾鏡（變速不變調）；沒有 ffmpeg 就用原速。

引擎物件只能在建立它的那個執行緒使用（COM 的規定），由 player 的產生執行緒負責建立。
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in (r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"):
        if os.path.isfile(candidate):
            return candidate
    return None


class SapiEngine:
    key = "sapi"
    label = "Windows 內建語音（離線）"

    def __init__(self, voice: str = ""):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        self._dispatch = win32com.client.Dispatch
        self._voice = win32com.client.Dispatch("SAPI.SpVoice")
        tokens = self._voice.GetVoices()
        self._tokens = {tokens.Item(i).GetDescription(): tokens.Item(i) for i in range(tokens.Count)}
        chosen = voice if voice in self._tokens else self.default_voice(list(self._tokens))
        if chosen:
            self._voice.Voice = self._tokens[chosen]

    @staticmethod
    def default_voice(names: list[str]) -> str:
        """優先選台灣中文的聲音。"""
        for hint in ("Taiwan", "台灣", "Chinese", "中文"):
            for name in names:
                if hint in name:
                    return name
        return names[0] if names else ""

    @staticmethod
    def list_voices() -> list[str]:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        tokens = win32com.client.Dispatch("SAPI.SpVoice").GetVoices()
        return [tokens.Item(i).GetDescription() for i in range(tokens.Count)]

    @staticmethod
    def rate_for(speed: float) -> int:
        """SAPI 的 Rate 是 -10～10，每 10 級約快 3 倍：speed = 3 ** (rate / 10)。"""
        return max(-10, min(10, round(10 * math.log(max(speed, 0.1)) / math.log(3))))

    def synthesize(self, text: str, base: Path, speed: float) -> Path:
        path = base.with_suffix(".wav")
        stream = self._dispatch("SAPI.SpFileStream")
        stream.Open(str(path), 3, False)          # SSFMCreateForWrite
        try:
            self._voice.AudioOutputStream = stream
            self._voice.Rate = self.rate_for(speed)
            self._voice.Speak(text, 0)            # 同步：講完（寫完）才回來
        finally:
            stream.Close()
        return path

    def close(self) -> None:
        import pythoncom

        self._voice = None
        pythoncom.CoUninitialize()


class GoogleEngine:
    key = "google"
    label = "Google 語音（需要網路）"
    LANGS = {"中文（台灣）": "zh-TW", "English": "en"}

    def __init__(self, voice: str = ""):
        self.lang = self.LANGS.get(voice, "zh-TW")
        self.ffmpeg = find_ffmpeg()

    @classmethod
    def list_voices(cls) -> list[str]:
        return list(cls.LANGS)

    def synthesize(self, text: str, base: Path, speed: float) -> Path:
        from gtts import gTTS

        raw = base.with_suffix(".raw.mp3")
        gTTS(text=text, lang=self.lang, slow=False).save(str(raw))
        if abs(speed - 1.0) < 0.05 or not self.ffmpeg:
            return raw
        fast = base.with_suffix(".mp3")
        result = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
             "-filter:a", f"atempo={speed:.2f}", str(fast)],
            capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return fast if result.returncode == 0 and fast.exists() else raw

    def close(self) -> None:
        pass


ENGINES = {SapiEngine.key: SapiEngine, GoogleEngine.key: GoogleEngine}
