"""分段、語音引擎、播放器（不會真的發出聲音：pygame 用 dummy 音效驅動）。

    .\\tools\\novel-reader\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\novel-reader\\tests -v
"""

import os
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path

os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reader import tts  # noqa: E402
from reader.player import Player  # noqa: E402
from reader.segments import split_into_segments  # noqa: E402


class SegmentsTest(unittest.TestCase):
    def test_paragraphs_and_blank_lines(self):
        self.assertEqual(split_into_segments("第一段。\n\n  \n第二段！"), ["第一段。", "第二段！"])

    def test_long_paragraph_cut_at_last_sentence_end(self):
        text = "甲" * 120 + "。" + "乙" * 120 + "。"
        segs = split_into_segments(text, limit=200)
        self.assertEqual(segs, ["甲" * 120 + "。", "乙" * 120 + "。"])

    def test_no_cut_inside_ellipsis_and_hard_cut_fallback(self):
        text = "甲" * 150 + "..." + "乙" * 100
        segs = split_into_segments(text, limit=200)
        self.assertTrue(all(len(s) <= 200 for s in segs))
        for a, b in zip(segs, segs[1:]):                        # 任何切點都不能把 ... 拆開
            self.assertFalse(a.endswith(".") and b.startswith("."), (a[-5:], b[:5]))
        self.assertEqual("".join(segs), text)
        self.assertEqual(split_into_segments("字" * 450, limit=200), ["字" * 200, "字" * 200, "字" * 50])


class SapiTest(unittest.TestCase):
    def test_rate_mapping(self):
        self.assertEqual(tts.SapiEngine.rate_for(1.0), 0)
        self.assertEqual(tts.SapiEngine.rate_for(3.0), 10)
        self.assertEqual(tts.SapiEngine.rate_for(1.5), 4)
        self.assertEqual(tts.SapiEngine.rate_for(9.0), 10)       # 夾在 -10～10

    @unittest.skipUnless(sys.platform == "win32", "SAPI 只有 Windows")
    def test_consecutive_synthesis(self):
        """pyttsx3 2.99 第二次就卡死；直接呼叫 SAPI 要能連續產生。"""
        engine = tts.SapiEngine()
        with tempfile.TemporaryDirectory() as tmp:
            durations = []
            for i, speed in enumerate((1.0, 2.0)):
                path = engine.synthesize("這是測試的句子，看看能不能連續產生。", Path(tmp) / f"s{i}", speed)
                with wave.open(str(path)) as w:
                    durations.append(w.getnframes() / w.getframerate())
            engine.close()
        self.assertGreater(durations[0], durations[1])             # 兩倍速比較短


class FakeEngine:
    label = "假引擎"
    made = []

    def __init__(self, voice=""):
        pass

    @staticmethod
    def list_voices():
        return ["x"]

    def synthesize(self, text, base, speed):
        FakeEngine.made.append((text, speed))
        path = base.with_suffix(".wav")
        with wave.open(str(path), "wb") as w:        # 0.05 秒的靜音
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00\x00" * 1100)
        return path

    def close(self):
        pass


class PlayerTest(unittest.TestCase):
    def setUp(self):
        tts.ENGINES["fake"] = FakeEngine
        FakeEngine.made = []
        self.events = []
        self.player = Player(lambda kind, data: self.events.append((kind, data)), "fake", "", 1.5)
        self.addCleanup(self.player.close)

    def run_until(self, kind, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.player.tick()
            if any(k == kind for k, _ in self.events):
                return
            time.sleep(0.02)
        self.fail(f"等不到 {kind}：{self.events}")

    def test_plays_every_segment_in_order(self):
        self.player.load(["一", "二", "三", "四"])
        self.player.play(0)
        self.run_until("finished")
        played = [d for k, d in self.events if k == "playing"]
        self.assertEqual(played, [0, 1, 2, 3])
        self.assertEqual([t for t, _ in FakeEngine.made], ["一", "二", "三", "四"])

    def test_start_from_middle_and_speed_change(self):
        self.player.load(["一", "二", "三"])
        self.player.play(1)
        self.run_until("playing")
        self.player.configure("fake", "", 2.0)          # 換語速 → 之後的段落用新語速重新產生
        self.run_until("finished")
        self.assertEqual(FakeEngine.made[0], ("二", 1.5))
        self.assertIn(("三", 2.0), FakeEngine.made)
        self.assertNotIn("一", [t for t, _ in FakeEngine.made])


if __name__ == "__main__":
    unittest.main()
