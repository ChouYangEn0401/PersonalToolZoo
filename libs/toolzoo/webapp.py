"""本機 web app 啟動器：給「FastAPI 後端 + 瀏覽器前端」型的工具用。

    from toolzoo.webapp import run
    run(app, name="video-downloader", port=8765)

做的事：

- 同一個工具已經開著（health check 回應的 app 名稱相同）→ 直接開瀏覽器，不再開第二份。
- 偏好的 port 被別的程式占用 → 自動換一個空的 port。
- 伺服器真的開始接受連線後才開瀏覽器（不會開到一個還沒好的頁面）。
- 設環境變數 TOOLZOO_NO_BROWSER=1 可以不開瀏覽器（測試、smoke test 用）。

每個 app 必須提供 GET /api/health，回傳 {"app": <name>, ...}。
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

# 這些 uvicorn 是用字串動態 import 的，PyInstaller 靜態分析看不到，要列進工具的 tool.json hiddenimports
UVICORN_HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
]


def _probe(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=0.6) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — 沒有回應就是沒在跑
        return None


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _any_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _open_when_ready(host: str, port: int, url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex((host, port)) == 0:
                webbrowser.open(url)
                return
        time.sleep(0.2)


def run(app, *, name: str, title: str, port: int, host: str = "127.0.0.1") -> None:
    # 打包成沒有 console 的 exe 時 stdout / stderr 是 None，uvicorn 的 log formatter 會因此崩潰
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

    open_browser = os.environ.get("TOOLZOO_NO_BROWSER") != "1"
    existing = _probe(f"http://{host}:{port}/api/health")
    if existing and existing.get("app") == name:
        print(f"\n  {title} 已經在執行中：http://{host}:{port}\n")
        if open_browser:
            webbrowser.open(f"http://{host}:{port}")
        return

    if not _port_free(host, port):
        port = _any_free_port(host)
    url = f"http://{host}:{port}"
    print(f"\n  {title}  ->  {url}")
    print("  關掉這個視窗就會停止。\n")

    if open_browser:
        threading.Thread(target=_open_when_ready, args=(host, port, url), daemon=True).start()

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning", ws="none")
