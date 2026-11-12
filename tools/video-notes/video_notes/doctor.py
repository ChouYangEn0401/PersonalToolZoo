"""啟動前自我檢查（不連網、不花錢）：run_checks(settings) → 清單；as_text／as_json 輸出。

每項：{name, ok, level("ok"/"warn"/"error"), message, error(錯誤合約 dict 或 None)}。
金鑰只回「有沒有設」，不印內容；路徑經過 redact。測試用 Env 注入假環境。
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from toolzoo import ytdlp

from video_notes import health as health_mod
from video_notes.errors import Remedy, ToolError, redact, short
from video_notes.media import DOC, UPGRADE_ACTION

MIN_DENO = (2, 3)
MIN_NODE = (22, 0)
YTDLP_WARN_DAYS = 60
YTDLP_ERROR_DAYS = 180


def _version_output(cmd: list[str]) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=8, errors="replace",
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or "") if done.returncode == 0 else ""


def _keys() -> dict[str, bool]:
    from toolzoo.ai import PROVIDERS, claude_code, find_key, needs_key

    out: dict[str, bool] = {}
    for p in PROVIDERS:
        if not needs_key(p):
            try:
                out[p] = bool(claude_code.available()[0]) if p == claude_code.KEY else True
            except Exception:  # noqa: BLE001 —— 找不到就當沒有
                out[p] = False
        else:
            out[p] = bool(find_key(p)[0])
    return out


def _cuda() -> tuple[bool, str]:
    from video_notes.transcribe import cuda_status

    return cuda_status()




@dataclass
class Env:
    find_ffmpeg: Callable[[], str | None] = ytdlp.find_ffmpeg
    find_js: Callable[[], list[str]] = ytdlp.find_js_runtimes
    version_output: Callable[[list[str]], str] = _version_output   # 子行程 --version
    ytdlp_version: Callable[[], str] = ytdlp.version
    today: Callable[[], date] = date.today
    cuda: Callable[[], tuple[bool, str]] = _cuda
    keys: Callable[[], dict[str, bool]] = _keys
    health_entries: Callable[[], dict] = health_mod.entries
    providers: dict[str, str] = field(default_factory=dict)       # 空 = 用 toolzoo.ai.PROVIDERS
    adapter_checks: Callable[[object], list] | None = None          # None = 用真的 registry（STT／輸出）


def _item(name: str, level: str, message: str, error: ToolError | None = None) -> dict:
    return {"name": name, "ok": level != "error", "level": level, "message": redact(message),
            "error": error.to_dict() if error else None}


def _parse_version(text: str) -> tuple[int, ...] | None:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else None


def _check_ffmpeg(env: Env) -> dict:
    path = env.find_ffmpeg()
    if path:
        return _item("ffmpeg", "ok", f"找到：{path}")
    err = ToolError("dependency_missing", "找不到 ffmpeg，下載合併與抽音訊會失敗", source="ffmpeg",
                    remedy=Remedy("auto_fixable", "在 GUI 頂端的提醒按「一鍵下載 ffmpeg」，或執行 VideoNotes --install-deps ffmpeg；"
                                  "也可以自己裝：winget install Gyan.FFmpeg",
                                  "https://www.gyan.dev/ffmpeg/builds/"))
    return _item("ffmpeg", "error", err.reason, err)


def _check_js(env: Env) -> dict:
    found = [n for n in env.find_js() if n in ("deno", "node")]   # Bun 上游已標淘汰，不算
    need = {"deno": MIN_DENO, "node": MIN_NODE}
    notes, good = [], False
    for name in found:
        ver = _parse_version(env.version_output([name, "--version"]))
        if ver is None:
            notes.append(f"{name}（版本不明）")
        elif ver[:2] >= need[name]:
            good = True
            notes.append(f"{name} {'.'.join(map(str, ver))}")
        else:
            notes.append(f"{name} {'.'.join(map(str, ver))}（太舊，需要 {'.'.join(map(str, need[name]))} 以上）")
    if good:
        return _item("JavaScript 執行環境", "ok", "、".join(notes))
    if not found:
        err = ToolError("dependency_missing", "找不到 JavaScript 執行環境（YouTube 需要 Deno 2.3 以上或 Node 22 以上）",
                        source="yt-dlp", remedy=Remedy(
                            "auto_fixable", "在 GUI 頂端的提醒按「一鍵下載 Deno」，或執行 VideoNotes --install-deps deno；"
                            "也可以自己裝：winget install DenoLand.Deno（或 Node.js 22 以上）",
                            "https://github.com/yt-dlp/yt-dlp/wiki/EJS"))
        return _item("JavaScript 執行環境", "error", err.reason, err)
    if all("版本不明" in n for n in notes):
        return _item("JavaScript 執行環境", "warn", "、".join(notes) + "；無法確認版本夠不夠新")
    err = ToolError("dependency_outdated", "JavaScript 執行環境版本太舊（需要 Deno 2.3 以上或 Node 22 以上）",
                    detail="、".join(notes), source="yt-dlp",
                    remedy=Remedy("needs_update", "升級 Node.js，或在 GUI 頂端的提醒按「一鍵下載 Deno」"
                                  "（VideoNotes --install-deps deno）", "https://github.com/yt-dlp/yt-dlp/wiki/EJS"))
    return _item("JavaScript 執行環境", "error", "、".join(notes), err)


def _check_ytdlp(env: Env) -> dict:
    ver = env.ytdlp_version()
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", ver or "")
    if not m:
        if ver and ver != "?":
            return _item("yt-dlp", "warn", f"版本 {ver}（看不懂版本號，無法算天數）")
        err = ToolError("dependency_missing", "沒有安裝 yt-dlp 套件", source="yt-dlp",
                        remedy=Remedy("needs_config", UPGRADE_ACTION, DOC))
        return _item("yt-dlp", "error", err.reason, err)
    try:
        days = (env.today() - date(int(m[1]), int(m[2]), int(m[3]))).days
    except ValueError:
        return _item("yt-dlp", "warn", f"版本 {ver}（日期不合理）")
    text = f"版本 {ver}，距今 {days} 天"
    if days >= YTDLP_ERROR_DAYS:
        err = ToolError("dependency_outdated", f"yt-dlp 已經 {days} 天沒更新，YouTube 很可能抓不到", source="yt-dlp",
                        detail=text, remedy=Remedy("needs_update", UPGRADE_ACTION, DOC))
        return _item("yt-dlp", "error", text, err)
    if days >= YTDLP_WARN_DAYS:
        err = ToolError("dependency_outdated", f"yt-dlp 已經 {days} 天沒更新，建議升級", source="yt-dlp", detail=text,
                        remedy=Remedy("needs_update", UPGRADE_ACTION, DOC))
        return _item("yt-dlp", "warn", text + "（建議升級）", err)
    return _item("yt-dlp", "ok", text)


def _check_gpu(env: Env) -> dict:
    try:
        ok, text = env.cuda()
    except Exception as exc:  # noqa: BLE001 —— 偵測失敗不影響其他檢查
        return _item("GPU／CUDA", "warn", f"無法偵測：{short(exc)}")
    return _item("GPU／CUDA", "ok" if ok else "warn", text)


def _check_keys(env: Env, settings) -> list[dict]:
    try:
        keys = env.keys()
    except Exception as exc:  # noqa: BLE001
        return [_item("AI 服務金鑰", "warn", f"無法檢查：{short(exc)}")]
    chosen = getattr(settings, "provider", "")
    names = env.providers
    if not names:
        try:
            from toolzoo.ai import PROVIDERS

            names = PROVIDERS
        except Exception:  # noqa: BLE001
            names = {}
    out = []
    for key, have in keys.items():
        label = f"AI：{names.get(key, key)}"
        if have:
            out.append(_item(label, "ok", "已設定"))
        elif key == chosen:
            err = ToolError("auth_required", f"目前選用的 {names.get(key, key)} 沒有金鑰或不可用", source=f"llm:{key}",
                            remedy=Remedy("needs_config", "在 .env 設定金鑰，或到設定頁換一個 AI 服務"))
            out.append(_item(label, "error", err.reason, err))
        else:
            out.append(_item(label, "ok", "未設定（目前沒選用）"))
    return out


def _check_adapters(settings) -> list[dict]:
    """STT／輸出格式的 adapter：registry 裡有就呼叫 check()，沒有就略過。"""
    out = []
    layers = []
    for mod_name, label, selected in (("stt", "語音辨識", getattr(settings, "stt_provider", "")), ("render", "輸出", None)):
        try:
            mod = __import__(f"video_notes.adapters.{mod_name}", fromlist=["REGISTRY"])
            mod.load_builtin()
            layers.append((label, mod.REGISTRY, selected, mod_name))
        except Exception:  # noqa: BLE001 —— 還沒實作或載入失敗：略過，不影響其他項目
            continue
    for label, registry, selected, mod_name in layers:
        for name in registry.names():
            try:
                obj = registry.create(name, settings) if mod_name == "stt" else registry.create(name)
                check = getattr(obj, "check", None)
                err = check() if callable(check) else None
            except ToolError as exc:
                err = exc
            except Exception as exc:  # noqa: BLE001
                out.append(_item(f"{label}：{name}", "warn", f"檢查時出錯：{short(exc)}"))
                continue
            title = f"{label}：{name}"
            if err is None:
                out.append(_item(title, "ok", "可用"))
            else:
                level = "error" if name == selected else "warn"
                out.append(_item(title, level, err.reason, err))
    return out


def _check_health(env: Env) -> list[dict]:
    out = []
    try:
        entries = env.health_entries()
    except Exception as exc:  # noqa: BLE001
        return [_item("health.json", "warn", f"讀不到：{short(exc)}")]
    for source, entry in entries.items():
        if entry.get("state") == "degraded":
            err = health_mod.HealthBook._to_error(source, entry)
            out.append(_item(f"已標記壞掉：{source}", "error", err.reason, err))
    return out


def run_checks(settings, env: Env | None = None) -> list[dict]:
    env = env or Env()
    results = [_check_ffmpeg(env), _check_js(env), _check_ytdlp(env), _check_gpu(env)]
    results += _check_keys(env, settings)
    results += (env.adapter_checks or _check_adapters)(settings)
    results += _check_health(env)
    return results


_MARK = {"ok": "[OK]  ", "warn": "[注意]", "error": "[錯誤]"}


def as_text(results: list[dict]) -> str:
    lines = []
    for r in results:
        lines.append(f"{_MARK.get(r['level'], '[?]')} {r['name']}：{r['message']}")
        err = r.get("error")
        if err and r["level"] != "ok" and err["remedy"].get("action"):
            lines.append(f"       → {err['remedy']['action']}")
    bad = sum(1 for r in results if r["level"] == "error")
    warn = sum(1 for r in results if r["level"] == "warn")
    lines.append(f"\n共 {len(results)} 項：{bad} 個錯誤、{warn} 個注意")
    return "\n".join(lines)


def as_json(results: list[dict]) -> str:
    return json.dumps(results, ensure_ascii=False, indent=2)
