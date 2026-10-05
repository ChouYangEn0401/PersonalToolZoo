"""命令列：VideoDownloader <網址> [<網址> ...] [選項]（不帶參數會開 GUI）。"""

from __future__ import annotations

import argparse
import sys
import threading
from dataclasses import replace

from toolzoo import ytdlp

from video_downloader.config import load_settings, user_dir
from video_downloader.history import History
from video_downloader.manager import DownloadManager
from video_downloader.options import DownloadRequest, parse_headers
from video_downloader.presets import PRESETS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="VideoDownloader",
        description="下載影片（yt-dlp 支援的網站，或直接的 .m3u8 / .mpd 串流）。不帶參數會開 GUI。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="預設組合（-p）：\n" + "\n".join(f"  {k:<10} {v.name}" for k, v in PRESETS.items()),
    )
    p.add_argument("urls", nargs="+", help="網址")
    p.add_argument("-p", "--preset", choices=list(PRESETS), help="畫質 / 格式")
    p.add_argument("-f", "--format", default="", help="自訂 yt-dlp format 字串（等於 -p custom）")
    p.add_argument("-o", "--out", help="存放資料夾")
    p.add_argument("--name", default="", help="檔名（只有一個網址時，不含副檔名）")
    p.add_argument("-H", "--header", action="append", default=[], help='HTTP header，例如 -H "Referer: https://…"')
    p.add_argument("--playlist", action="store_true", help="網址是播放清單時下載整份（依清單名稱建資料夾）")
    p.add_argument("--subs", action="store_true", help="下載並嵌入字幕")
    p.add_argument("--cookies-from-browser", default=None, help="用瀏覽器的登入狀態（firefox / chrome / edge）")
    p.add_argument("-j", "--jobs", type=int, help="同時下載幾支")
    return p


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace") if stream.isatty() else stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    settings = replace(load_settings())
    if args.out:
        settings.output_dir = args.out
    if args.subs:
        settings.subtitles = True
    if args.cookies_from_browser is not None:
        settings.cookies_from_browser = args.cookies_from_browser
    if not ytdlp.find_ffmpeg(settings.ffmpeg_path):
        print("提醒：找不到 ffmpeg，影像與聲音分開的影片會無法合併。", file=sys.stderr)

    lock = threading.Lock()
    last: dict[str, int] = {}

    def on_update(job, event):
        with lock:
            name = (job.title or job.request.url)[:50]
            if event == "progress":
                step = int(job.progress * 10)
                if last.get(job.id) != step:      # 每 10% 印一次，不洗版
                    last[job.id] = step
                    print(f"[{name}] {job.progress:5.0%}  {job.stage}")
            elif event == "processing" and last.get(job.id + "pp") != job.stage:
                last[job.id + "pp"] = job.stage
                print(f"[{name}] {job.stage}…")
            elif event == "finished":
                if job.status == "done":
                    print(f"✓ {name}\n    {job.filepath or job.folder}")
                else:
                    print(f"✗ {name}：{job.error or job.stage}")

    manager = DownloadManager(lambda: settings, History(user_dir() / "history.json"),
                              args.jobs or settings.concurrent_downloads, on_update=on_update)
    preset = "custom" if args.format else (args.preset or settings.preset)
    headers = parse_headers("\n".join(args.header))
    jobs = [manager.submit(DownloadRequest(
        url=url, preset=preset, custom_format=args.format, headers=headers,
        filename=args.name if len(args.urls) == 1 else "", playlist_items="all" if args.playlist else "",
    )) for url in args.urls]
    try:
        manager.wait(jobs)
    except KeyboardInterrupt:
        print("\n中斷：取消下載（已下載的部分保留，重新執行會接著下載）")
        manager.shutdown()
        return 130
    return 0 if all(j.status == "done" for j in jobs) else 1
