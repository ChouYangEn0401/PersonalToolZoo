"""命令列介面。

    VideoNotes <網址> [<網址> ...] [選項]
    VideoNotes --file urls.txt --preset stock-show --post
    VideoNotes --list

不帶任何參數執行時開 GUI（見 VideoNotes.py）。完整說明：VideoNotes --help
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import replace
from pathlib import Path

from video_notes import notify
from video_notes.config import OUTPUT_CUSTOM, OUTPUT_DATA, OUTPUT_DOWNLOADS, Settings, load_settings
from video_notes.jobs import JobManager
from video_notes.naming import Artifacts, classify, find_folder
from video_notes.pipeline import REDOABLE, JobOptions, Locks, Pipeline, _read_json
from video_notes.profiles import AUTO
from video_notes.service import library
from video_notes.summarize import VideoContext

STAGE_NAMES = {"info": "影片資訊", "download": "下載", "audio": "抽音訊", "transcribe": "語音辨識",
               "notes": "AI 筆記", "notify": "通知"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="VideoNotes",
        description="影片網址 → 下載 → 逐字稿 → AI 整理成 Notion 筆記。不帶參數執行會開啟 GUI。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="範例：\n"
               "  VideoNotes https://youtu.be/xxxx\n"
               "  VideoNotes https://youtu.be/xxxx -p finance --with actions,timeline --focus \"AI 伺服器\"\n"
               "  VideoNotes --file urls.txt --preset daily-news --reuse --post\n"
               "  VideoNotes --list",
    )
    p.add_argument("urls", nargs="*", help="影片網址（可以一次給很多個）")
    p.add_argument("-f", "--file", help="從文字檔讀網址，一行一個（# 開頭的行忽略）")
    p.add_argument("-o", "--out", help="輸出位置：downloads（預設）、data（工具資料夾的 data\\）或任何資料夾路徑")
    p.add_argument("-p", "--profile", help="整理方式：auto（自動判斷）或 --list 列出的 id")
    p.add_argument("-w", "--with", dest="modifiers", default="", help="加料，逗號分隔，例如 timeline,actions")
    p.add_argument("--preset", default="", help="常用組合（--list 看有哪些）")
    p.add_argument("--focus", default="", help="特別想知道的主題；無關的內容會被濃縮成一行")
    p.add_argument("--provider", choices=("openai", "gemini", "anthropic"), help="AI 服務")
    p.add_argument("--model", help="AI 模型（例如 gpt-5.1、gemini-2.5-flash、claude-opus-5-5）")
    p.add_argument("--whisper-model", help="語音辨識模型：tiny / base / small / medium / large-v3 / large-v3-turbo")
    p.add_argument("--device", choices=("auto", "cuda", "cpu"), help="語音辨識用 GPU 或 CPU")
    p.add_argument("--language", help="影片語言，例如 zh、en；auto 讓 Whisper 自己判斷")
    p.add_argument("--video", action="store_true", help="連影片一起下載保留（預設只下載音訊，比較快）")
    p.add_argument("--no-notes", action="store_true", help="只下載＋產生逐字稿，不呼叫 AI")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--reuse", action="store_true", help="已經有的檔案一律沿用，不詢問")
    g.add_argument("--redo", default="", help=f"指定重做的階段，逗號分隔：{','.join(REDOABLE)} 或 all")
    p.add_argument("--post", nargs="?", const=True, default=None, metavar="URL",
                   help="socket 模式：處理完用 HTTP POST 把結果送出（網址預設讀 socket/config.json）")
    p.add_argument("-j", "--jobs", type=int, help="同時處理幾支影片")
    p.add_argument("--json", action="store_true", help="結束時把結果以 JSON 印到 stdout（給其他程式串接）")
    p.add_argument("--list", action="store_true", help="列出整理方式、加料與常用組合")
    p.add_argument("--dry-run", action="store_true", help="不下載也不呼叫 AI，只印出會送給 AI 的 system prompt")
    return p


def _settings_from_args(args, base: Settings) -> Settings:
    s = replace(base)
    if args.out:
        if args.out in (OUTPUT_DOWNLOADS, OUTPUT_DATA):
            s.output = args.out
        else:
            s.output, s.output_custom = OUTPUT_CUSTOM, args.out
    for attr, value in (("provider", args.provider), ("model", args.model), ("whisper_model", args.whisper_model),
                        ("whisper_device", args.device), ("language", args.language)):
        if value:
            setattr(s, attr, value)
    if args.provider and not args.model:
        s.model = ""  # 換了服務但沒指定模型 → 用該服務的預設模型
    if args.jobs:
        s.parallel_jobs = args.jobs
    return s


def _read_urls(args) -> list[str]:
    urls = list(args.urls)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return list(dict.fromkeys(urls))


def _ask(question: str) -> bool:
    try:
        return input(f"  {question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _decide_redo(url: str, root: Path, plan, args) -> frozenset[str]:
    """已經處理過的影片：依參數決定，或在互動模式下逐項詢問（規格：名稱重複要問要不要重做）。"""
    if args.redo:
        stages = {s.strip() for s in args.redo.split(",") if s.strip()}
        return frozenset(REDOABLE) if "all" in stages else frozenset(stages & set(REDOABLE))
    folder = find_folder(root, classify(url))
    if folder is None or args.reuse or not sys.stdin.isatty():
        return frozenset()
    art = Artifacts(folder)
    status = art.status()
    record = _read_json(art.info)
    profile = plan.profile if plan.profile != AUTO else record.get("auto_profile")
    note_exists = bool(profile) and art.notes(plan.slug(profile)).exists()
    print(f"\n這支影片處理過了：{folder}")
    print(f"  已有：影音 {'✓' if status['media'] else '✗'}　逐字稿 {'✓' if status['transcript'] else '✗'}"
          f"　筆記 {', '.join(status['notes']) or '無'}")
    redo = set()
    if status["media"] and _ask("重新下載？（逐字稿與筆記也會跟著重做）"):
        return frozenset(REDOABLE)
    if status["transcript"] and _ask("重新產生逐字稿？（筆記也會跟著重做）"):
        return frozenset({"transcribe", "notes"})
    if note_exists and not args.no_notes and _ask("這個方案的筆記已經有了，要重新整理嗎？"):
        redo.add("notes")
    return frozenset(redo)


def _list() -> None:
    lib = library()
    print("整理方式（-p / --profile）：")
    print("  auto          自動判斷影片類型")
    for p in lib.sorted_profiles():
        print(f"  {p.id:<13} {p.icon} {p.name}：{p.description}")
    print("\n加料（-w / --with，可以多個）：")
    for m in lib.sorted_modifiers():
        print(f"  {m.id:<13} {m.icon} {m.name}：{m.description}")
    print("\n常用組合（--preset）：")
    for pr in lib.presets.values():
        mods = "+".join(pr.modifiers)
        print(f"  {pr.id:<13} {pr.name}：{pr.profile}{'+' + mods if mods else ''}  {pr.description}")


def main(argv: list[str] | None = None) -> int:
    # 主控台：Windows 會用 Unicode API 寫出，什麼字都能顯示。被導到管線 / 檔案時（例如 --json 給別的程式讀）
    # 統一用 UTF-8；打包後的 exe 不吃 PYTHONIOENCODING，不這樣做就會變成 cp950，emoji 與簡體字會壞掉。
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    lib = library()
    if args.list:
        _list()
        return 0

    try:
        plan = lib.plan(args.profile or AUTO, [m.strip() for m in args.modifiers.split(",")], args.focus, args.preset)
    except KeyError as exc:
        print(f"錯誤：{exc.args[0]}", file=sys.stderr)
        return 2

    if args.dry_run:
        profile = plan.profile if plan.profile != AUTO else "general"
        composed = lib.compose(profile, plan.modifiers, plan.focus)
        print(composed.system)
        print("\n--- user 訊息的開頭 ---")
        print(VideoContext(url="https://example.com/video", kind="video", title="（影片標題）").block())
        return 0

    urls = _read_urls(args)
    if not urls:
        print("沒有網址。用法：VideoNotes <網址>（或不帶參數開啟 GUI；--help 看完整說明）", file=sys.stderr)
        return 2

    settings = _settings_from_args(args, load_settings())
    root = settings.output_root()
    root.mkdir(parents=True, exist_ok=True)
    config = notify.load_config()
    post_url = ""
    if args.post is True or (args.post is None and config.get("enabled")):
        post_url = config["url"]
    elif isinstance(args.post, str):
        post_url = args.post

    pipeline = Pipeline(settings, lib, Locks())
    if not pipeline.ffmpeg:
        print("錯誤：找不到 ffmpeg（請安裝並加入 PATH）", file=sys.stderr)
        return 2

    single = len(urls) == 1
    print_lock = threading.Lock()
    streamed: dict[str, bool] = {}

    def on_update(job, name, data):
        with print_lock:
            label = (job.title or job.url)[:40]
            if name == "stage" and data["state"] in ("running", "done", "reused", "failed"):
                if data["stage"] == "notes" and data["state"] == "running" and data.get("detail"):
                    print(f"[{label}] {data['detail']}")
                elif data["state"] != "running":
                    word = {"done": "完成", "reused": "沿用既有檔案", "failed": "失敗"}[data["state"]]
                    print(f"[{label}] {STAGE_NAMES[data['stage']]}：{word}"
                          + (f"（{data['detail']}）" if data.get("detail") else ""))
                else:
                    print(f"[{label}] {STAGE_NAMES[data['stage']]}…")
            elif name == "log":
                print(f"[{label}] {data['message']}")
            elif name == "token" and single and not args.json:
                if not streamed.get(job.id):
                    streamed[job.id] = True
                    print("\n" + "─" * 60)
                print(data["text"], end="", flush=True)
            elif name == "finished":
                if streamed.get(job.id):
                    print("\n" + "─" * 60)
                if data["status"] == "failed":
                    print(f"[{label}] 失敗：{job.error}")

    manager = JobManager(pipeline, settings.parallel_jobs, on_update=on_update)
    jobs = []
    for url in urls:
        redo = _decide_redo(url, root, plan, args)
        options = JobOptions(plan=plan, output_root=root, redo=redo, notes=not args.no_notes,
                             keep_video=args.video or settings.keep_video, notify_url=post_url)
        jobs.append(manager.submit(url, options))
    try:
        manager.wait(jobs)
    except KeyboardInterrupt:
        print("\n中斷：取消所有工作…（已產生的檔案都會保留）")
        manager.shutdown()
        return 130

    failed = [j for j in jobs if j.status != "done"]
    if args.json:
        out = [j.result | {"status": j.status, "error": j.error} for j in jobs]
        print(json.dumps(out[0] if single else out, ensure_ascii=False, indent=2))
    else:
        print()
        for j in jobs:
            mark = "✓" if j.status == "done" else "✗"
            where = j.result.get("notes_file") or j.folder or j.url
            print(f"{mark} {j.title or j.url}\n    {where}" + (f"\n    {j.error}" if j.error else ""))
    return 1 if failed else 0
