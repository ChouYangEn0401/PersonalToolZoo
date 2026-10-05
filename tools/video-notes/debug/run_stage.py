"""單獨跑某一個階段，除錯時不用每次從頭來。

    python debug\\run_stage.py info <網址>                       # 只抓影片資訊（JSON）
    python debug\\run_stage.py download <網址> <資料夾> [--video]
    python debug\\run_stage.py audio <影音檔> <輸出.wav>
    python debug\\run_stage.py transcribe <音訊.wav> [--model small] [--device cpu] [--language zh]
    python debug\\run_stage.py prompt <transcript.json> [--profile news] [--with timeline] [--focus …]
        # 印出會送給 AI 的 system 與 user 訊息，不呼叫 API
    python debug\\run_stage.py notes <transcript.json> [--profile news] …
        # 真的呼叫 AI（用設定裡的服務與模型），把筆記印出來

（python 指的是 tools\\video-notes\\.venv\\Scripts\\python.exe）
"""

import argparse
import json
import sys
import time
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from toolzoo import ytdlp  # noqa: E402
from toolzoo.ai.prompts import wrap  # noqa: E402

from video_notes import media  # noqa: E402
from video_notes.config import load_settings  # noqa: E402
from video_notes.profiles import AUTO  # noqa: E402
from video_notes.service import library  # noqa: E402
from video_notes.summarize import NoteWriter, VideoContext  # noqa: E402
from video_notes.transcribe import Transcriber, Transcript, clock  # noqa: E402


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", choices=("info", "download", "audio", "transcribe", "prompt", "notes"))
    p.add_argument("inputs", nargs="+")
    p.add_argument("--video", action="store_true")
    p.add_argument("--model", default="medium")
    p.add_argument("--device", default="auto")
    p.add_argument("--language", default="auto")
    p.add_argument("--profile", default="general")
    p.add_argument("--with", dest="mods", default="")
    p.add_argument("--focus", default="")
    a = p.parse_args()
    ffmpeg = ytdlp.find_ffmpeg()
    t0 = time.time()

    if a.stage == "info":
        print(json.dumps(media.fetch_info(a.inputs[0], ffmpeg), ensure_ascii=False, indent=2))
    elif a.stage == "download":
        folder = Path(a.inputs[1])
        folder.mkdir(parents=True, exist_ok=True)
        media.download(a.inputs[0], folder, keep_video=a.video, ffmpeg=ffmpeg,
                       on_progress=lambda f, d: print(f"\r{f:6.1%}  {d}", end=""))
        print("\n", sorted(x.name for x in folder.iterdir()))
    elif a.stage == "audio":
        media.extract_audio(Path(a.inputs[0]), Path(a.inputs[1]), ffmpeg)
    elif a.stage == "transcribe":
        t = Transcriber(a.model, a.device, a.language)
        print(f"device={t.device}")
        tr = t.transcribe(Path(a.inputs[0]), on_progress=lambda f, text: print(f"{f:6.1%}  {text}"))
        print(f"\nlanguage={tr.language} duration={clock(tr.duration)} segments={len(tr.segments)}")
    else:
        lib = library()
        plan = lib.plan(a.profile, [m for m in a.mods.split(",") if m], a.focus)
        transcript = Transcript.load(Path(a.inputs[0]))
        ctx = VideoContext(url="(debug)", kind="video", title=Path(a.inputs[0]).parent.name)
        profile = plan.profile if plan.profile != AUTO else "general"
        if a.stage == "prompt":
            composed = lib.compose(profile, plan.modifiers, plan.focus)
            body = transcript.timed_text() if composed.needs_timestamps else transcript.plain_text()
            print("=== system ===\n" + composed.system)
            print("\n=== user ===\n" + ctx.block() + "\n\n" + wrap(body[:2000], "transcript") + "\n…")
        else:
            from toolzoo.ai import LLM

            s = load_settings()
            writer = NoteWriter(LLM(s.provider, s.model or None), lib)
            print(writer.write(plan, profile, transcript, ctx, on_status=print))
    print(f"\n({time.time() - t0:.1f} 秒)")


if __name__ == "__main__":
    main()
