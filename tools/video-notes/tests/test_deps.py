"""一鍵下載 ffmpeg／Deno（deps.py）＋ CLI --install-deps ＋ 網頁 /api/deps。完全離線：用假的下載伺服器。"""

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes import deps  # noqa: E402
from video_notes.errors import ToolError  # noqa: E402


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeOpener:
    """網址 → 回應內容（bytes）或例外。記錄被要求的網址。"""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requested: list[str] = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.requested.append(url)
        value = self.routes.get(url)
        if value is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)


def routes_for(name: str, archive: bytes, checksum: str | None = None) -> dict:
    comp = deps.COMPONENTS[name]
    digest = checksum or hashlib.sha256(archive).hexdigest()
    return {comp.checksum_url: f"{digest}  {comp.url.rsplit('/', 1)[-1]}\n".encode(), comp.url: archive}


class DepsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(deps, "user_dir", lambda: self.tmp)
        self.patch.start()
        self.old_path = os.environ.get("PATH", "")

    def tearDown(self):
        self.patch.stop()
        os.environ["PATH"] = self.old_path
        shutil.rmtree(self.tmp, ignore_errors=True)


class Install(DepsBase):
    def test_ffmpeg_installs_only_the_exes_and_activates_path(self):
        archive = make_zip({"ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe": b"FF",
                            "ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe": b"FP",
                            "ffmpeg-9.0.2-essentials_build/bin/ffplay.exe": b"PLAY",
                            "ffmpeg-9.0.2-essentials_build/README.txt": b"readme"})
        opener = FakeOpener(routes_for("ffmpeg", archive))
        seen = []
        path = deps.install("ffmpeg", opener=opener, on_progress=lambda f, t: seen.append(f))
        target = self.tmp / "bin" / "ffmpeg"
        self.assertEqual(path, target / "ffmpeg.exe")
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["ffmpeg.exe", "ffprobe.exe", "source.json"])
        self.assertEqual((target / "ffmpeg.exe").read_bytes(), b"FF")
        self.assertEqual(json.loads((target / "source.json").read_text(encoding="utf-8"))["sha256"],
                         hashlib.sha256(archive).hexdigest())
        self.assertIn(str(target), os.environ["PATH"].split(os.pathsep)[0])
        self.assertEqual(seen[-1], 1.0)
        self.assertFalse(list((self.tmp / "bin").glob(".*")), "暫存檔要清掉")
        # 只連官方網址（https）
        self.assertTrue(all(u.startswith("https://") for u in opener.requested))

    def test_checksum_mismatch_deletes_everything(self):
        archive = make_zip({"deno.exe": b"D"})
        opener = FakeOpener(routes_for("deno", archive, checksum="0" * 64))
        with self.assertRaises(ToolError) as cm:
            deps.install("deno", opener=opener)
        self.assertEqual(cm.exception.code, "network_unreachable")
        self.assertIn("校驗", cm.exception.reason)
        self.assertFalse((self.tmp / "bin" / "deno").exists())
        self.assertEqual(list((self.tmp / "bin").iterdir()), [])

    def test_zip_slip_paths_cannot_escape(self):
        archive = make_zip({"../../evil/deno.exe": b"D", "..\\..\\x\\other.dll": b"X"})
        deps.install("deno", opener=FakeOpener(routes_for("deno", archive)))
        self.assertTrue((self.tmp / "bin" / "deno" / "deno.exe").is_file())
        self.assertFalse((self.tmp / "evil").exists())
        self.assertFalse(any(p.name == "other.dll" for p in self.tmp.rglob("*")))

    def test_missing_main_exe_is_upstream_changed(self):
        archive = make_zip({"something-else.exe": b"x"})
        with self.assertRaises(ToolError) as cm:
            deps.install("deno", opener=FakeOpener(routes_for("deno", archive)))
        self.assertEqual(cm.exception.code, "upstream_changed")
        self.assertFalse((self.tmp / "bin" / "deno").exists())

    def test_404_and_network_errors_are_classified(self):
        with self.assertRaises(ToolError) as cm:
            deps.install("ffmpeg", opener=FakeOpener({}))
        self.assertEqual(cm.exception.code, "upstream_changed")
        self.assertIn("winget", cm.exception.remedy.action)
        comp = deps.COMPONENTS["ffmpeg"]
        with self.assertRaises(ToolError) as cm:
            deps.install("ffmpeg", opener=FakeOpener({comp.checksum_url: urllib.error.URLError("getaddrinfo failed")}))
        self.assertEqual(cm.exception.code, "network_unreachable")

    def test_failed_reinstall_keeps_the_old_copy(self):
        good = make_zip({"deno.exe": b"OLD"})
        deps.install("deno", opener=FakeOpener(routes_for("deno", good)))
        bad = make_zip({"deno.exe": b"NEW"})
        with self.assertRaises(ToolError):
            deps.install("deno", opener=FakeOpener(routes_for("deno", bad, checksum="f" * 64)))
        self.assertEqual((self.tmp / "bin" / "deno" / "deno.exe").read_bytes(), b"OLD")

    def test_cancel(self):
        from video_notes.transcribe import Cancelled

        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            deps.install("deno", opener=FakeOpener(routes_for("deno", make_zip({"deno.exe": b"D"}))), cancel=cancel)
        self.assertEqual(list((self.tmp / "bin").iterdir()), [])

    def test_unknown_and_non_https(self):
        with self.assertRaises(ToolError):
            deps.install("python")
        with self.assertRaises(ToolError) as cm:
            deps._open("http://example.com/x.zip", FakeOpener({}))
        self.assertEqual(cm.exception.code, "config_invalid")

    def test_parse_checksum_formats(self):
        h = "a" * 64
        self.assertEqual(deps.parse_checksum(h), h)
        self.assertEqual(deps.parse_checksum(f"{h.upper()}  file.zip"), h)
        self.assertEqual(deps.parse_checksum(f"Algorithm Hash Path\n--------- ---- ----\nSHA256 {h} C:\\x.zip"), h)
        with self.assertRaises(ToolError):
            deps.parse_checksum("<html>not found</html>")


class Status(DepsBase):
    def test_status_and_missing_respect_node(self):
        with mock.patch.object(deps.shutil, "which", lambda n: None), \
                mock.patch("toolzoo.ytdlp.find_ffmpeg", lambda *a: None):
            self.assertEqual(deps.missing(), ["ffmpeg", "deno"])
        with mock.patch.object(deps.shutil, "which", lambda n: "C:/node/node.exe" if n == "node" else None), \
                mock.patch("toolzoo.ytdlp.find_ffmpeg", lambda *a: None):
            self.assertEqual(deps.missing(), ["ffmpeg"])
            item = next(i for i in deps.status() if i["name"] == "deno")
            self.assertFalse(item["needed"])

    def test_activate_is_idempotent(self):
        deps.install("deno", opener=FakeOpener(routes_for("deno", make_zip({"deno.exe": b"D"}))))
        deps.activate()
        deps.activate()
        entries = [p for p in os.environ["PATH"].split(os.pathsep) if p == str(self.tmp / "bin" / "deno")]
        self.assertEqual(len(entries), 1)


class Cli(DepsBase):
    def run_cli(self, *argv):
        from video_notes import cli

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_json_without_yes_refuses_and_downloads_nothing(self):
        with mock.patch.object(deps, "install") as install, mock.patch.object(deps, "missing", lambda: ["ffmpeg"]):
            code, out, _ = self.run_cli("--install-deps", "--json")
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])
        install.assert_not_called()

    def test_json_with_yes_installs(self):
        with mock.patch.object(deps, "install", return_value=Path("X/ffmpeg.exe")) as install, \
                mock.patch.object(deps, "status", return_value=[]):
            code, out, err = self.run_cli("--install-deps", "ffmpeg", "--json", "--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["data"]["installed"], {"ffmpeg": str(Path("X/ffmpeg.exe"))})
        install.assert_called_once()

    def test_nothing_missing(self):
        with mock.patch.object(deps, "missing", lambda: []), mock.patch.object(deps, "status", return_value=[]):
            code, out, _ = self.run_cli("--install-deps", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["installed"], {})

    def test_unknown_name(self):
        code, _, err = self.run_cli("--install-deps", "python", "--yes")
        self.assertEqual(code, 2)
        self.assertIn("不認得", err)


class Web(DepsBase):
    def setUp(self):
        super().setUp()
        try:
            from fastapi.testclient import TestClient
        except Exception:  # noqa: BLE001
            self.skipTest("沒有 fastapi testclient")
        from video_notes.web import server

        self.server = server
        self.client = TestClient(server.create_app(), base_url="http://127.0.0.1")
        self.h = {"X-Video-Notes": "1"}

    def test_install_runs_in_background_and_reports_progress(self):
        def fake_install(name, on_progress=None, **_):
            on_progress(0.5, "下載 ffmpeg：1 MB")
            return Path("X/ffmpeg.exe")

        with mock.patch.object(deps, "install", fake_install):
            r = self.client.post("/api/deps/install", json={"name": "ffmpeg"}, headers=self.h)
            self.assertEqual(r.status_code, 200)
            for _ in range(50):
                job = self.client.get("/api/deps").json()["job"]
                if job["state"] != "running":
                    break
                time.sleep(0.02)
        self.assertEqual(job["state"], "done")
        self.assertIn("items", self.client.get("/api/deps").json())

    def test_failure_is_error_contract(self):
        def boom(name, **_):
            raise ToolError("network_unreachable", "連不上 ffmpeg 的下載網站")

        with mock.patch.object(deps, "install", boom):
            self.client.post("/api/deps/install", json={"name": "ffmpeg"}, headers=self.h)
            for _ in range(50):
                job = self.client.get("/api/deps").json()["job"]
                if job["state"] != "running":
                    break
                time.sleep(0.02)
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["error"]["code"], "network_unreachable")

    def test_write_needs_header_and_known_name(self):
        self.assertEqual(self.client.post("/api/deps/install", json={"name": "ffmpeg"}).status_code, 403)
        r = self.client.post("/api/deps/install", json={"name": "python"}, headers=self.h)
        self.assertEqual(r.status_code, 400)

    def test_state_has_deps(self):
        data = self.client.get("/api/state").json()
        self.assertEqual({d["name"] for d in data["deps"]}, {"ffmpeg", "deno"})
        self.assertIn("deps_job", data)


if __name__ == "__main__":
    unittest.main()
