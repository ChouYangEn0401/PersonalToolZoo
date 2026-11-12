"""外部程式（ffmpeg、Deno）：檢查有沒有、一鍵從官方下載到工具旁邊的 data\\bin\\、讓程式找得到。

為什麼不把它們打包進 exe／installer：ffmpeg 約 109 MB（GPLv3）、Deno 約 100 MB，打包會讓 exe 變很大、
每次上游更新都要重發，散布 GPL 的 ffmpeg 還要附授權與原始碼。改成第一次用時從官方下載：

    ffmpeg  https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip（.sha256 是校驗檔）
    Deno    https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip（.sha256sum）

安全規則：
- 只接受 https；先下載官方的 SHA-256 校驗檔，下載完逐位元組比對，不符就刪掉並回報。
- 壓縮檔裡只取需要的 exe（只看檔名、不照壓縮檔內的路徑寫檔，所以惡意的 ../ 路徑寫不出去）。
- 安裝過程不執行任何下載來的程式。
- 下載前一定要使用者同意（GUI 的按鈕、CLI 的 --install-deps 會先問）；程式不會自己偷偷下載。

找得到：activate() 把 data\\bin\\<名稱>\\ 加到 PATH 最前面；libs/toolzoo/ytdlp 的 find_ffmpeg／find_js_runtimes
與 yt-dlp 本身都是從 PATH 找，所以不用改共用程式。程式啟動時（VideoNotes.py）與安裝完都會呼叫。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from video_notes.config import user_dir
from video_notes.errors import Remedy, ToolError, short

Progress = Callable[[float, str], None]
CHUNK = 1 << 16
USER_AGENT = "VideoNotes-deps"      # 不帶任何使用者資訊


@dataclass(frozen=True)
class Component:
    name: str
    label: str
    purpose: str
    url: str
    checksum_url: str
    exes: tuple[str, ...]          # 要從壓縮檔裡取出的檔案（只比對檔名）
    main_exe: str                  # 用來判斷「裝好了沒」
    homepage: str
    winget: str
    license: str
    size_hint: str


COMPONENTS: dict[str, Component] = {
    "ffmpeg": Component(
        name="ffmpeg", label="ffmpeg", purpose="下載時合併影音、抽出音訊給語音辨識",
        url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        checksum_url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
        exes=("ffmpeg.exe", "ffprobe.exe"), main_exe="ffmpeg.exe",
        homepage="https://www.gyan.dev/ffmpeg/builds/", winget="winget install Gyan.FFmpeg",
        license="GPLv3（gyan.dev 的 Windows 版）", size_hint="約 110 MB",
    ),
    "deno": Component(
        name="deno", label="Deno", purpose="yt-dlp 抓 YouTube 時要用的 JavaScript 執行環境（有 Node 22 以上就不需要）",
        url="https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
        checksum_url="https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip.sha256sum",
        exes=("deno.exe",), main_exe="deno.exe",
        homepage="https://deno.com/", winget="winget install DenoLand.Deno",
        license="MIT", size_hint="約 45 MB（解壓後約 100 MB）",
    ),
}

_lock = threading.Lock()


def bin_root() -> Path:
    return user_dir() / "bin"


def bin_dir(name: str) -> Path:
    return bin_root() / name


def local_exe(name: str) -> Path | None:
    """工具自己下載的那一份（不管 PATH 上有沒有別的）。"""
    comp = COMPONENTS[name]
    path = bin_dir(name) / comp.main_exe
    return path if path.is_file() else None


def activate() -> list[str]:
    """把已經下載好的 data\\bin\\<名稱>\\ 放到 PATH 最前面（重複呼叫不會重複加）。回傳加了哪些。"""
    added = []
    parts = os.environ.get("PATH", "").split(os.pathsep)
    norm = {os.path.normcase(os.path.normpath(p)) for p in parts if p}
    for name in COMPONENTS:
        if local_exe(name) is None:
            continue
        d = str(bin_dir(name))
        if os.path.normcase(os.path.normpath(d)) not in norm:
            parts.insert(0, d)
            added.append(name)
    if added:
        os.environ["PATH"] = os.pathsep.join(parts)
    return added


def _found(name: str) -> str | None:
    if name == "ffmpeg":
        from toolzoo import ytdlp

        return ytdlp.find_ffmpeg()
    return shutil.which(name)


def status() -> list[dict]:
    """每個元件：有沒有找到、在哪、是不是工具自己下載的、手動安裝的方法。不連網、不執行任何程式。"""
    activate()
    out = []
    for name, comp in COMPONENTS.items():
        found = _found(name)
        if name == "deno" and not found and shutil.which("node"):
            note = "沒有 Deno，但找到 Node（版本要 22 以上才夠用，見自我檢查）"
        else:
            note = ""
        local = local_exe(name)
        out.append({
            "name": name, "label": comp.label, "purpose": comp.purpose,
            "found": bool(found), "path": found or "",
            # 需要補：找不到，而且（Deno 的話）也沒有 Node 可以代替
            "needed": not found and not (name == "deno" and shutil.which("node")),
            "managed": bool(local and found and Path(found).resolve() == local.resolve()),
            "note": note, "size_hint": comp.size_hint, "license": comp.license,
            "homepage": comp.homepage, "winget": comp.winget, "source": comp.url,
            "installed_at": _read_source(name).get("installed_at", ""),
        })
    return out


def missing() -> list[str]:
    """需要補的元件。Deno：有 Node 也算不缺（版本夠不夠由自我檢查判斷）。"""
    return [item["name"] for item in status() if item["needed"]]


def _read_source(name: str) -> dict:
    try:
        return json.loads((bin_dir(name) / "source.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- 下載
def _open(url: str, opener):
    if not url.startswith("https://"):
        raise ToolError("config_invalid", "只允許從 https 網址下載", source="deps")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return opener(req, timeout=60)


def _http_error(exc: BaseException, comp: Component, what: str) -> ToolError:
    manual = Remedy("needs_owner", f"稍後再試，或自己下載安裝：{comp.homepage}（或在終端機執行 {comp.winget}）",
                    comp.homepage)
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return ToolError("upstream_changed", f"{comp.label} 的官方下載位置找不到（{what}），可能改網址了",
                             detail=short(exc), source=f"deps:{comp.name}", remedy=manual)
        if exc.code == 429:
            return ToolError("rate_limited", f"下載 {comp.label} 被限流", detail=short(exc),
                             source=f"deps:{comp.name}", remedy=manual)
        return ToolError("network_unreachable", f"下載 {comp.label} 失敗（伺服器回 {exc.code}）", detail=short(exc),
                         source=f"deps:{comp.name}", remedy=manual)
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return ToolError("network_unreachable", f"連不上 {comp.label} 的下載網站", detail=short(exc),
                         source=f"deps:{comp.name}", remedy=manual)
    if isinstance(exc, OSError):
        return ToolError("resource_exhausted", f"寫入 {comp.label} 失敗（磁碟空間或權限）", detail=short(exc),
                         source=f"deps:{comp.name}", remedy=Remedy("needs_owner", "確認工具旁邊的 data 資料夾可以寫入、空間足夠"))
    return ToolError("internal_bug", f"安裝 {comp.label} 時發生未預期的錯誤", detail=short(exc),
                     source=f"deps:{comp.name}", remedy=manual)


def parse_checksum(text: str) -> str:
    """校驗檔的格式各家不同（只有雜湊、`雜湊  檔名`、PowerShell 的表格…），取第一個 64 位十六進位字串。"""
    match = re.search(r"\b[0-9a-fA-F]{64}\b", text or "")
    if not match:
        raise ToolError("upstream_changed", "官方校驗檔的格式看不懂", detail=(text or "")[:200], source="deps")
    return match.group(0).lower()


def install(name: str, *, opener=urllib.request.urlopen, on_progress: Progress | None = None,
            cancel: threading.Event | None = None) -> Path:
    """下載、校驗、解出 exe 到 data\\bin\\<名稱>\\。回傳主程式路徑。失敗丟 ToolError（不留下半套檔案）。"""
    from video_notes.transcribe import Cancelled

    if name not in COMPONENTS:
        raise ToolError("bad_input", f"不認得的元件：{name}", source="deps",
                        remedy=Remedy("none", f"可用：{', '.join(COMPONENTS)}"))
    comp = COMPONENTS[name]
    progress = on_progress or (lambda _f, _t: None)
    if not _lock.acquire(blocking=False):
        raise ToolError("rate_limited", "已經有一個下載在進行中，等它結束再試", source=f"deps:{name}")
    target = bin_dir(name)
    staging = bin_root() / f".{name}.staging"
    archive = bin_root() / f".{name}.zip.part"
    try:
        bin_root().mkdir(parents=True, exist_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        progress(0.0, "取得官方校驗碼…")
        try:
            with _open(comp.checksum_url, opener) as resp:
                expected = parse_checksum(resp.read(4096).decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001 — 全部轉成錯誤合約
            raise _http_error(exc, comp, "校驗檔") from exc

        digest = hashlib.sha256()
        try:
            with _open(comp.url, opener) as resp, open(archive, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    mb = f"{done / 1048576:.1f} MB" + (f" / {total / 1048576:.1f} MB" if total else "")
                    progress(min(done / total, 0.99) if total else 0.0, f"下載 {comp.label}：{mb}")
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _http_error(exc, comp, "主檔") from exc

        if digest.hexdigest() != expected:
            raise ToolError("network_unreachable", f"下載的 {comp.label} 跟官方校驗碼不符（可能下載不完整或被竄改），已刪除",
                            source=f"deps:{name}", detail=f"expected {expected[:12]}… got {digest.hexdigest()[:12]}…",
                            remedy=Remedy("none", "再試一次；一直不符就改用官方網站手動下載", comp.homepage))

        progress(0.99, "解壓縮…")
        staging.mkdir(parents=True)
        wanted = {e.lower() for e in comp.exes}
        got: set[str] = set()
        try:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    base = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
                    if info.is_dir() or base.lower() not in wanted or base.lower() in got:
                        continue
                    with zf.open(info) as src, open(staging / base.lower(), "wb") as dst:   # 只用檔名，不照壓縮檔內路徑
                        shutil.copyfileobj(src, dst)
                    got.add(base.lower())
        except zipfile.BadZipFile as exc:
            raise ToolError("upstream_changed", f"{comp.label} 的壓縮檔打不開", detail=short(exc),
                            source=f"deps:{name}", remedy=Remedy("needs_owner", f"改用官方網站手動下載：{comp.homepage}")) from exc
        if comp.main_exe.lower() not in got:
            raise ToolError("upstream_changed", f"{comp.label} 的壓縮檔裡找不到 {comp.main_exe}，官方可能改了打包方式",
                            source=f"deps:{name}", remedy=Remedy("needs_owner", f"改用官方網站手動下載：{comp.homepage}"))
        (staging / "source.json").write_text(json.dumps({
            "url": comp.url, "sha256": expected, "files": sorted(got),
            "installed_at": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        # 全部成功才換上：舊的整個換掉（中途失敗不會留下半套）
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
        activate()
        progress(1.0, f"{comp.label} 安裝完成")
        return target / comp.main_exe.lower()
    except OSError as exc:
        raise _http_error(exc, comp, "寫檔") from exc
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        _lock.release()


def uninstall(name: str) -> bool:
    """刪掉工具自己下載的那一份（不碰使用者自己裝在別處的）。"""
    if name not in COMPONENTS:
        return False
    d = bin_dir(name)
    if not d.is_dir():
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True
