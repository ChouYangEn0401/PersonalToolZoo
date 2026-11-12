"""命令列介面。

    VideoNotes <網址> [<網址> ...] [選項]
    VideoNotes --file urls.txt --preset stock-show --post
    VideoNotes --list
    VideoNotes --check --json        # 自我檢查（機器可讀）
    VideoNotes --render <資料夾> --outputs tree-md,html-tabs

不帶任何參數執行時開 GUI（見 VideoNotes.py）。完整說明：VideoNotes --help

機器可讀（--json）：成功 {"ok": true, "data": ...}；失敗 {"ok": false, "error": <錯誤合約>}。
退出碼：0 成功、2 輸入有問題、3 依賴或環境問題、4 暫時性可重試、1 其他（errors.exit_code）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from dataclasses import asdict, replace
from pathlib import Path

from toolzoo.ai import PROVIDERS, provider_for_model

from video_notes import collection as collection_mod
from video_notes import doctor as doctor_mod
from video_notes import health as health_mod
from video_notes import library as library_mod
from video_notes import notify
from video_notes.adapters import render as render_mod
from video_notes.adapters.llm import COMPAT
from video_notes.collection import Member
from video_notes.config import OUTPUT_CUSTOM, OUTPUT_DATA, OUTPUT_DOWNLOADS, Settings, load_settings
from video_notes.errors import Remedy, ToolError, as_tool_error, exit_code
from video_notes.jobs import JobManager
from video_notes.naming import Artifacts, classify, find_folder
from video_notes.pipeline import REDOABLE, JobOptions, Locks, Pipeline, _read_json
from video_notes.profiles import AUTO
from video_notes.service import library
from video_notes.summarize import VideoContext
from video_notes.transcribe import Cancelled

STAGE_NAMES = {"info": "影片資訊", "download": "下載", "audio": "抽音訊", "transcribe": "語音辨識",
               "notes": "AI 筆記", "outputs": "其他輸出", "notify": "通知"}

OUT_ENV = "VIDEO_NOTES_OUT"      # 預設輸出位置（優先序：--out > 這個環境變數 > 設定）
CLOUD_STT = {"openai": "OpenAI", "gemini": "Google Gemini"}
# 批次裡有多個失敗時，退出碼取「最嚴重」的：環境(3) > 其他(1) > 輸入(2) > 暫時性(4)
EXIT_SEVERITY = (3, 1, 2, 4)


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
    p.add_argument("-o", "--out", help="輸出位置：downloads（預設）、data（工具旁邊的 data\\videos\\）或任何資料夾路徑")
    p.add_argument("-p", "--profile", help="整理方式：auto（自動判斷）或 --list 列出的 id")
    p.add_argument("-w", "--with", dest="modifiers", default="", help="加料，逗號分隔，例如 timeline,actions")
    p.add_argument("--preset", default="", help="常用組合（--list 看有哪些）")
    p.add_argument("--focus", default="", help="特別想知道的主題；無關的內容會被濃縮成一行")
    p.add_argument("--provider", choices=[*PROVIDERS, COMPAT],
                   help="AI 服務：claude-sub（Claude 訂閱，預設，不需要金鑰）、openai、gemini、anthropic（Claude API）、"
                        "openai-compat（設定裡的相容端點，例如 Ollama）")
    p.add_argument("--model", help="AI 模型（例如 sonnet、haiku、gpt-5.1、gemini-2.5-flash、claude-opus-5-5）；"
                                   "只給模型時從名稱判斷服務")
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
    p.add_argument("--json", action="store_true",
                   help='機器可讀輸出：成功 {"ok":true,"data":…}、失敗 {"ok":false,"error":{code,reason,retryable,remedy,detail}}；'
                        "進度與提醒改印到 stderr，stdout 只有一份 JSON")
    p.add_argument("--list", action="store_true", help="列出整理方式、加料與常用組合")
    p.add_argument("--dry-run", action="store_true", help="不下載也不呼叫 AI，只印出會送給 AI 的 system prompt")
    # ---- v2 ----
    p.add_argument("--outputs", default="",
                   help="這次額外產生哪些輸出，逗號分隔，或 all（例如 tree-md,html-tabs）；不給 = 常用組合／設定值。"
                        "Markdown 筆記一律會產生")
    p.add_argument("--stt", choices=("local", "openai", "gemini"),
                   help="這次用哪個語音辨識服務（不改存檔設定）；openai／gemini 會把音訊上傳")
    p.add_argument("--stt-model", help="雲端語音辨識的模型（空白 = 該服務的預設）")
    p.add_argument("--check", action="store_true", help="自我檢查（ffmpeg、JS 環境、yt-dlp、金鑰、壞掉記帳…）；有錯誤退出碼 3")
    p.add_argument("--recheck", action="store_true", help="先清掉「壞掉」記帳再檢查（等於 --check，並重新給依賴一次機會）")
    p.add_argument("--install-deps", metavar="名稱", nargs="?", const="missing",
                   help="從官方下載 ffmpeg／Deno 到工具旁邊的 data\\bin\\：ffmpeg、deno、all，或不給 = 缺的才裝。"
                        "會先問你；非互動或 --json 時必須加 --yes")
    p.add_argument("--status", action="store_true", help="目前有哪些工作＋依賴健康狀態（只讀；配 --json）")
    p.add_argument("--library", action="store_true", help="列出輸出資料夾裡的筆記庫：影片與合併（只讀；配 --json）")
    p.add_argument("--render", metavar="資料夾", help="只從既有的分析結果產生輸出，不呼叫 AI（要配 --outputs）")
    p.add_argument("--slug", default="", help="配 --render：用哪一份分析（analysis.<slug>.json 的 slug）；不給 = 最新的")
    p.add_argument("--reanalyze", metavar="資料夾", help="沿用該資料夾的逐字稿重新分析（配 -p / -w / --preset / --focus）")
    p.add_argument("--combine", action="store_true", help="把這次處理的影片（或 --folders 指定的）合併成一份")
    p.add_argument("--folders", default="", help="配 --combine：直接合併這些既有的影片資料夾，逗號分隔")
    p.add_argument("--title", default="", help="配 --combine：合併後的標題")
    p.add_argument("-y", "--yes", action="store_true", help="合併規模較大需要確認時，視為同意（非互動／--json 時必須加）")
    return p


def _settings_from_args(args, base: Settings) -> Settings:
    s = replace(base)
    out = args.out or os.environ.get(OUT_ENV, "").strip()
    if out:
        if out in (OUTPUT_DOWNLOADS, OUTPUT_DATA):
            s.output = out
        else:
            s.output, s.output_custom = OUTPUT_CUSTOM, out
    for attr, value in (("provider", args.provider), ("model", args.model), ("whisper_model", args.whisper_model),
                        ("whisper_device", args.device), ("language", args.language),
                        ("stt_provider", getattr(args, "stt", None)), ("stt_model", getattr(args, "stt_model", None))):
        if value:
            setattr(s, attr, value)
    if getattr(args, "stt", None) and not getattr(args, "stt_model", None):
        s.stt_model = ""   # 換了語音辨識服務但沒指定模型 → 用該服務的預設
    if args.provider and not args.model:
        s.model = ""  # 換了服務但沒指定模型 → 用該服務的預設模型
    elif args.model and not args.provider:
        s.provider = provider_for_model(args.model) or s.provider  # 只給模型（例如 haiku）→ 從名稱判斷服務
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


# ---------------------------------------------------------------------------- 輸出格式（人 / 機器）
def _emit_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def error_text(err: ToolError) -> str:
    """給人看的錯誤：原因 ＋「怎麼辦」（remedy.action）。"""
    text = f"錯誤：{err.reason}"
    if err.remedy.action:
        text += f"\n怎麼辦：{err.remedy.action}"
    return text


def _ok(args, data, text: str = "") -> int:
    if args.json:
        _emit_json({"ok": True, "data": data})
    elif text:
        print(text)
    return 0


def _fail(args, err: ToolError, data=None) -> int:
    """失敗：--json 印 {"ok": false, "error": …}（有成功的部分就一起附在 data）；否則印人話到 stderr。"""
    if args.json:
        payload = {"ok": False, "error": err.to_dict()}
        if data is not None:
            payload["data"] = data
        _emit_json(payload)
    else:
        print(error_text(err), file=sys.stderr)
    return err.exit_code


def worst_exit_code(errors: list[ToolError]) -> int:
    """多個失敗時取最嚴重的退出碼（順序見 EXIT_SEVERITY）。"""
    codes = {exit_code(e.code) for e in errors}
    for code in EXIT_SEVERITY:
        if code in codes:
            return code
    return 1


def _worst(errors: list[ToolError]) -> ToolError:
    target = worst_exit_code(errors)
    return next(e for e in errors if exit_code(e.code) == target)


def _info(args, message: str) -> None:
    """進度與提醒：--json 時走 stderr，讓 stdout 只剩一份 JSON。"""
    print(message, file=sys.stderr if args.json else sys.stdout)


def _bad_input(reason: str, action: str = "") -> ToolError:
    return ToolError("bad_input", reason, source="cli", remedy=Remedy("auto_fixable" if action else "none", action))


# ---------------------------------------------------------------------------- 參數解析
def _all_renderers() -> list[str]:
    render_mod.load_builtin()
    return render_mod.REGISTRY.names()


def _parse_outputs(text: str) -> tuple[str, ...] | None:
    """--outputs 的值 → 名稱 tuple；沒給回 None；'all' = 全部已登記的輸出；不認得的名稱 → bad_input。"""
    names = [n.strip() for n in (text or "").split(",") if n.strip()]
    if not names:
        return None
    known = _all_renderers()
    if "all" in names:
        return tuple(known)
    unknown = [n for n in names if n not in known]
    if unknown:
        raise _bad_input(f"沒有這些輸出格式：{', '.join(unknown)}", f"可用：{', '.join(known)}（或 all）")
    return tuple(dict.fromkeys(names))


def _effective_outputs(args, lib) -> tuple[str, ...] | None:
    """--outputs > 常用組合的 outputs > None（pipeline 用設定值）。"""
    given = _parse_outputs(args.outputs)
    if given is not None:
        return given
    preset = lib.presets.get(args.preset) if args.preset else None
    from_preset = tuple(getattr(preset, "outputs", ()) or ())
    return from_preset or None


def _stt_notice(args, settings: Settings) -> None:
    if getattr(args, "stt", None) in CLOUD_STT:
        _info(args, f"提醒：音訊會上傳到 {CLOUD_STT[args.stt]}（雲端語音辨識）。")


def _latest_analysis(folder: Path) -> Path | None:
    files = Artifacts(folder).all_analyses()
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _slug_of(path: Path) -> str:
    return path.name[len("analysis."):-len(".json")]


def _need_dir(text: str, root: Path | None = None) -> Path:
    path = Path(text).expanduser()
    if not path.is_dir() and root is not None and (root / text).is_dir():
        path = root / text
    if not path.is_dir():
        raise _bad_input("找不到這個資料夾", "確認路徑，或用 --library 看筆記庫裡有哪些影片")
    return path


def _pick_analysis(folder: Path, plan) -> Path:
    """合併時用這支影片的哪一份分析：方案對得上就用它，否則最新的；都沒有就回一個不存在的路徑（讓 estimate 報 missing）。"""
    art = Artifacts(folder)
    if plan.profile != AUTO:
        exact = art.analysis(plan.slug(plan.profile))
        if exact.exists():
            return exact
    return _latest_analysis(folder) or art.analysis("missing")


# ---------------------------------------------------------------------------- 子功能
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


def _run_check(args, settings: Settings) -> int:
    if args.recheck:
        health_mod.clear()
    results = doctor_mod.run_checks(settings)
    errors = [r for r in results if r["level"] == "error"]
    data = {"checks": results,
            "summary": {"total": len(results), "error": len(errors),
                        "warn": sum(1 for r in results if r["level"] == "warn")}}
    if not errors:
        return _ok(args, data, doctor_mod.as_text(results))
    if not args.json:
        print(doctor_mod.as_text(results))
    first = errors[0]
    err_dict = first.get("error")
    if err_dict:
        err = ToolError(err_dict["code"], err_dict["reason"], err_dict.get("retryable"),
                        Remedy(**err_dict.get("remedy") or {}), err_dict.get("detail", ""), err_dict.get("source", ""))
    else:
        err = ToolError("config_invalid", f"{first['name']}：{first['message']}", source="doctor")
    if args.json:
        _fail(args, err, data)
    return 3    # 檢查有錯誤一律 3（文字模式清單已經印過了）


def _run_status(args) -> int:
    entries = health_mod.entries()
    degraded = sorted(k for k, v in entries.items() if v.get("state") == "degraded")
    data = {"running": [], "message": "沒有進行中的工作（命令列版沒有常駐行程；網頁 GUI 的工作請看 GUI）",
            "health": {"entries": entries, "degraded": degraded}}
    lines = [data["message"]]
    if not entries:
        lines.append("依賴健康：沒有失敗記錄")
    for source, entry in entries.items():
        lines.append(f"依賴 {source}：{'已標記壞掉' if entry.get('state') == 'degraded' else '失敗中'}"
                     f"（{entry.get('code', '')}，連續 {entry.get('count', 0)} 次）")
    if degraded:
        lines.append("排除原因後用 --recheck 重新檢查。")
    return _ok(args, data, "\n".join(lines))


def _run_library(args, settings: Settings) -> int:
    data = library_mod.list_library(settings.output_root())
    lines = [f"影片 {len(data['videos'])} 支、合併 {len(data['collections'])} 份"]
    for kind, items in (("影片", data["videos"]), ("合併", data["collections"])):
        for item in items:
            slugs = ", ".join(a["slug"] for a in item["analyses"]) or "無分析"
            lines.append(f"[{kind}] {item['title']}  ({slugs})\n      {item['folder']}")
    return _ok(args, data, "\n".join(lines))


def _run_render(args, lib, settings: Settings) -> int:
    folder = _need_dir(args.render, settings.output_root())
    outputs = _effective_outputs(args, lib) or tuple(settings.outputs) or None
    if not outputs:
        raise _bad_input("沒說要產生哪些格式", f"加上 --outputs，例如 --outputs tree-md,html-tabs（可用：{', '.join(_all_renderers())}）")
    if args.slug:
        slug = args.slug
    else:
        latest = _latest_analysis(folder)
        if latest is None:
            raise _bad_input("這個資料夾還沒有分析結果", "先用 --reanalyze 對這支影片分析一次")
        slug = _slug_of(latest)
    pipeline = Pipeline(settings, lib, Locks.from_settings(settings))
    made = pipeline.render(folder, slug, outputs)    # 不呼叫 AI
    data = {"folder": str(folder), "slug": slug, "outputs": made}
    text = "\n".join(f"{name}：{path}" for name, path in made.items())
    return _ok(args, data, text)


def _printer(args, label: str):
    """reanalyze 用的簡單進度：只印 log 與筆記階段訊息。"""
    def on_event(name: str, data: dict) -> None:
        if name == "log":
            _info(args, f"[{label}] {data['message']}")
        elif name == "stage" and data.get("stage") == "notes" and data.get("state") == "running" and data.get("detail"):
            _info(args, f"[{label}] {data['detail']}")
    return on_event


def _run_reanalyze(args, lib, settings: Settings, plan) -> int:
    folder = _need_dir(args.reanalyze, settings.output_root())
    _stt_notice(args, settings)
    pipeline = Pipeline(settings, lib, Locks.from_settings(settings))
    try:
        result = pipeline.reanalyze(folder, plan, outputs=_effective_outputs(args, lib),
                                    emit=_printer(args, folder.name[:40]))
    except Cancelled:
        raise ToolError("cancelled", "已取消", source="cli") from None
    text = f"完成：{result.get('notes_file', folder)}"
    return _ok(args, result, text)


class _Recording:
    """包住 Pipeline：把每支影片失敗時的 ToolError 留下來（JobManager 只留字串）。其餘介面原樣轉交。"""

    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline
        self.errors: dict[str, ToolError] = {}

    def run(self, url, opts, emit=None, cancel=None):
        try:
            return self._pipeline.run(url, opts, emit, cancel)
        except Cancelled:
            self.errors[url.strip()] = ToolError("cancelled", "已取消", source="cli")
            raise
        except Exception as exc:    # noqa: BLE001 —— 轉成錯誤合約後原例外照丟
            self.errors[url.strip()] = as_tool_error(exc, where="處理影片")
            raise

    def __getattr__(self, name):
        return getattr(self._pipeline, name)


def _combine(args, lib, settings: Settings, plan, root: Path, members: list[Member]) -> dict:
    """先估規模、必要時確認，再合併。回傳可放進 JSON 的結果（不含整份 analysis）。"""
    if len(members) < 2:
        raise _bad_input("合併至少需要兩支影片", "用 --folders 補上其他影片資料夾，或給更多網址")
    est = collection_mod.estimate(members, settings)
    if est.missing:
        _info(args, "注意：這些影片讀不到分析結果，會略過：" + "、".join(est.missing))
    if est.needs_confirm and not args.yes:
        summary = f"合併 {est.members} 支影片，約 {est.input_tokens} tokens、要呼叫 AI {est.calls} 次"
        if args.json or not sys.stdin.isatty():
            raise _bad_input(f"{summary}，規模較大需要確認", "確定要做的話加上 --yes")
        if not _ask(f"{summary}，要繼續嗎？"):
            raise ToolError("cancelled", "你選擇不合併", source="cli")
    run_settings = settings
    outputs = _effective_outputs(args, lib)
    if outputs is not None:
        run_settings = replace(settings, outputs=list(outputs))
    result = collection_mod.combine(members, plan=plan, settings=run_settings, library=lib, output_root=root,
                                    title=args.title, emit=_printer(args, "合併"))
    out = {k: v for k, v in result.items() if k != "analysis"}
    out["estimate"] = asdict(est)
    return out


def _run_install_deps(args) -> int:
    """--install-deps：從官方下載 ffmpeg／Deno（先列出要下載什麼、從哪裡、多大，經過同意才下載）。"""
    from video_notes import deps

    want = args.install_deps.strip().lower()
    if want == "missing":
        names = deps.missing()
    elif want == "all":
        names = list(deps.COMPONENTS)
    else:
        names = [n.strip() for n in want.split(",") if n.strip()]
        unknown = [n for n in names if n not in deps.COMPONENTS]
        if unknown:
            raise _bad_input(f"不認得：{', '.join(unknown)}", f"可用：{', '.join(deps.COMPONENTS)}、all")
    if not names:
        return _ok(args, {"installed": {}, "status": deps.status()}, "ffmpeg 與 JavaScript 執行環境都已經有了，不用下載。")

    plan_lines = [f"- {deps.COMPONENTS[n].label}（{deps.COMPONENTS[n].size_hint}，{deps.COMPONENTS[n].license}）"
                  f"：{deps.COMPONENTS[n].url}" for n in names]
    _info(args, "要從官方下載（下載後會核對 SHA-256，放在工具旁邊的 data\\bin\\）：\n" + "\n".join(plan_lines))
    if not args.yes:
        if args.json or not sys.stdin.isatty():
            raise _bad_input("下載前需要同意", "確定要下載的話加上 --yes")
        if not _ask("要下載嗎？"):
            raise ToolError("cancelled", "你選擇不下載", source="cli")

    installed: dict[str, str] = {}
    errors: list[ToolError] = []
    for name in names:
        last = [-1]

        def progress(frac: float, text: str, _last=last) -> None:
            pct = int(frac * 100)
            if pct // 10 != _last[0] // 10:     # 每 10% 印一次，不洗版
                _info(args, f"  {text}")
                _last[0] = pct

        try:
            installed[name] = str(deps.install(name, on_progress=progress))
            _info(args, f"  ✓ {deps.COMPONENTS[name].label}：{installed[name]}")
        except ToolError as err:
            errors.append(err)
            _info(args, f"  ✗ {deps.COMPONENTS[name].label}：{err.reason}")
    data = {"installed": installed, "status": deps.status()}
    if errors:
        return _fail(args, _worst(errors), data)
    return _ok(args, data, "完成。用 --check 確認環境。")


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
    try:
        return _dispatch(args)
    except ToolError as err:
        return _fail(args, err)
    except KeyboardInterrupt:
        print("\n中斷：取消所有工作…（已產生的檔案都會保留）", file=sys.stderr)
        return 130
    except Exception as exc:    # noqa: BLE001 —— CLI 最外層：什麼例外都轉成錯誤合約，不丟 traceback 給呼叫端
        return _fail(args, as_tool_error(exc, where="執行"))


def _dispatch(args) -> int:
    if args.list:
        _list()
        return 0

    base = load_settings()
    settings = _settings_from_args(args, base)
    if args.install_deps:
        return _run_install_deps(args)
    if args.check or args.recheck:
        return _run_check(args, settings)
    if args.status:
        return _run_status(args)
    if args.library:
        return _run_library(args, settings)

    lib = library()
    try:
        plan = lib.plan(args.profile or AUTO, [m.strip() for m in args.modifiers.split(",")], args.focus, args.preset)
    except KeyError as exc:
        raise _bad_input(str(exc.args[0])) from None

    if args.render:
        return _run_render(args, lib, settings)
    if args.reanalyze:
        return _run_reanalyze(args, lib, settings, plan)

    if args.dry_run:
        profile = plan.profile if plan.profile != AUTO else "general"
        composed = lib.compose(profile, plan.modifiers, plan.focus)
        print(composed.system)
        print("\n--- user 訊息的開頭 ---")
        print(VideoContext(url="https://example.com/video", kind="video", title="（影片標題）").block())
        return 0

    urls = _read_urls(args)
    folders = [f.strip() for f in args.folders.split(",") if f.strip()]
    if args.combine and args.no_notes:
        raise _bad_input("--combine 要用分析結果，不能和 --no-notes 一起用")
    if folders and not args.combine:
        raise _bad_input("--folders 要配 --combine 一起用")
    if not urls and not (args.combine and folders):
        raise _bad_input("沒有網址", "用法：VideoNotes <網址>（或不帶參數開啟 GUI；--help 看完整說明）")

    root = settings.output_root()
    root.mkdir(parents=True, exist_ok=True)
    outputs = _effective_outputs(args, lib)
    entries: list[dict] = []
    failures: list[ToolError] = []
    members: list[Member] = [Member(_need_dir(f, root), _pick_analysis(_need_dir(f, root), plan)) for f in folders]

    if urls:
        entries, failures, done_members = _process_urls(args, lib, settings, plan, root, urls, outputs)
        members = done_members + members

    collection = None
    if args.combine and not failures:
        try:
            collection = _combine(args, lib, settings, plan, root, members)
        except ToolError as err:
            if not args.json:
                print(error_text(err), file=sys.stderr)
            failures.append(err)
    elif args.combine and failures:
        _info(args, "有影片處理失敗，所以沒有合併。修好後可用 --combine --folders <資料夾,資料夾> 只做合併。")

    if args.json:
        if args.combine:
            data = {"videos": entries, "collection": collection}
        else:
            data = entries[0] if len(urls) == 1 else entries
        if failures:
            return _fail(args, _worst(failures), data)
        return _ok(args, data)

    print()
    if collection:
        print(f"✓ 合併完成\n    {collection.get('notes_file') or collection.get('folder', '')}")
    return worst_exit_code(failures) if failures else 0


def _process_urls(args, lib, settings: Settings, plan, root: Path, urls: list[str], outputs):
    """處理網址（和舊版相同的流程）。回傳 (每支的結果, 失敗的錯誤, 可合併的成員)。"""
    config = notify.load_config()
    post_url = ""
    if args.post is True or (args.post is None and config.get("enabled")):
        post_url = config["url"]
    elif isinstance(args.post, str):
        post_url = args.post

    _stt_notice(args, settings)
    pipeline = Pipeline(settings, lib, Locks.from_settings(settings))
    if not pipeline.ffmpeg:
        raise ToolError("dependency_missing", "找不到 ffmpeg，沒辦法抽音訊", source="ffmpeg",
                        remedy=Remedy("needs_config", "安裝 ffmpeg 並加入 PATH，或在設定裡指定 ffmpeg.exe 的位置；"
                                                      "--check 可以確認", "https://ffmpeg.org/download.html"))

    single = len(urls) == 1
    print_lock = threading.Lock()
    streamed: dict[str, bool] = {}

    def on_update(job, name, data):
        with print_lock:
            label = (job.title or job.url)[:40]
            if name == "stage" and data["state"] in ("running", "done", "reused", "failed"):
                if data["stage"] == "notes" and data["state"] == "running" and data.get("detail"):
                    _info(args, f"[{label}] {data['detail']}")
                elif data["state"] != "running":
                    word = {"done": "完成", "reused": "沿用既有檔案", "failed": "失敗"}[data["state"]]
                    _info(args, f"[{label}] {STAGE_NAMES[data['stage']]}：{word}"
                                + (f"（{data['detail']}）" if data.get("detail") else ""))
                else:
                    _info(args, f"[{label}] {STAGE_NAMES[data['stage']]}…")
            elif name == "log":
                _info(args, f"[{label}] {data['message']}")
            elif name == "token" and single and not args.json:
                if not streamed.get(job.id):
                    streamed[job.id] = True
                    print("\n" + "─" * 60)
                print(data["text"], end="", flush=True)
            elif name == "finished":
                if streamed.get(job.id):
                    print("\n" + "─" * 60)
                if data["status"] == "failed":
                    _info(args, f"[{label}] 失敗：{job.error}")

    recorder = _Recording(pipeline)
    manager = JobManager(recorder, settings.parallel_jobs, on_update=on_update)
    jobs = []
    for url in urls:
        redo = _decide_redo(url, root, plan, args)
        options = JobOptions(plan=plan, output_root=root, redo=redo, notes=not args.no_notes,
                             keep_video=args.video or settings.keep_video, notify_url=post_url, outputs=outputs)
        jobs.append(manager.submit(url, options))
    try:
        manager.wait(jobs)
    except KeyboardInterrupt:
        manager.shutdown()
        raise

    entries, failures, members = [], [], []
    for j in jobs:
        err = None
        if j.status != "done":
            err = recorder.errors.get(j.url) or ToolError("internal_bug", j.error or "處理失敗", source="cli")
            failures.append(err)
        elif j.result.get("analysis_file"):
            members.append(Member(Path(j.result["folder"]), Path(j.result["analysis_file"])))
        entries.append({"url": j.url, "title": j.title, "folder": j.folder} | j.result
                       | {"status": j.status, "error": err.to_dict() if err else None})
        if not args.json:
            mark = "✓" if err is None else "✗"
            where = j.result.get("notes_file") or j.folder or j.url
            text = f"{mark} {j.title or j.url}\n    {where}"
            if err:
                text += f"\n    原因：{err.reason}" + (f"\n    怎麼辦：{err.remedy.action}" if err.remedy.action else "")
            print(("\n" if j is jobs[0] else "") + text)
    return entries, failures, members
