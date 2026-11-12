"""CLI 的機器可讀介面：--json 信封、退出碼、--check／--status／--library／--render／--combine、VIDEO_NOTES_OUT。

全部離線：LLM／來源／語音辨識／collection 都用假的，health 不寫真的 data\\health.json。
"""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOL), str(TOOL.parents[1] / "libs")]

from video_notes import analysis, cli  # noqa: E402
from video_notes.collection import CombineEstimate  # noqa: E402
from video_notes.config import OUTPUT_CUSTOM, Settings  # noqa: E402
from video_notes.errors import Remedy, ToolError  # noqa: E402
from video_notes.naming import Artifacts, classify, new_folder  # noqa: E402
from video_notes.profiles import PromptLibrary  # noqa: E402

from test_render_tree import sample  # noqa: E402

LIB = PromptLibrary(TOOL / "prompts")
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def run_cli(*argv: str, stdin_tty: bool = False):
    """跑 main()，回傳 (退出碼, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    stdin = mock.Mock()
    stdin.isatty.return_value = stdin_tty
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch("sys.stdin", stdin):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "out"
        self.root.mkdir()
        self.settings = Settings(output=OUTPUT_CUSTOM, output_custom=str(self.root))
        for target, new in (
            (mock.patch.object(cli, "load_settings", lambda: Settings(**vars(self.settings))), None),
            (mock.patch.object(cli, "library", lambda: LIB), None),
            # health 不碰真的 data\health.json
            (mock.patch.object(cli.health_mod, "entries", lambda: {}), None),
            (mock.patch.object(cli.health_mod, "clear", mock.Mock()), None),
        ):
            target.start()
            self.addCleanup(target.stop)
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop(cli.OUT_ENV, None)

    def make_video(self, title="Me at the zoo", slug="news", vid="jNQXAC9IVRw") -> Path:
        folder = new_folder(self.root, classify(URL.replace("jNQXAC9IVRw", vid)), title)
        folder.mkdir(parents=True)
        art = Artifacts(folder)
        art.info.write_text(json.dumps({"url": URL, "video": {"title": title}}), encoding="utf-8")
        analysis.save(art.analysis(slug), sample(title=title))
        return folder


class EnvelopeTest(CliTestBase):
    def test_success_envelope_and_exit_0(self):
        code, out, _ = run_cli("--status", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "data"})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["running"], [])

    def test_failure_envelope_is_error_contract_and_exit_2(self):
        code, out, _ = run_cli("--json")     # 沒有網址 → bad_input
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(set(payload["error"]), {"code", "reason", "retryable", "remedy", "detail", "source"})
        self.assertEqual(payload["error"]["code"], "bad_input")
        self.assertEqual(set(payload["error"]["remedy"]), {"kind", "action", "doc"})

    def test_failure_in_human_mode_prints_reason_and_remedy(self):
        code, out, err = run_cli()
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("錯誤：沒有網址", err)
        self.assertIn("怎麼辦：", err)

    def test_unknown_preset_is_bad_input(self):
        code, out, _ = run_cli(URL, "--preset", "nope", "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "bad_input")

    def test_unexpected_exception_becomes_internal_bug_exit_1(self):
        with mock.patch.object(cli, "_run_status", side_effect=RuntimeError("boom")):
            code, out, _ = run_cli("--status", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "internal_bug")

    def test_exit_code_table(self):
        for code, expected in (("bad_input", 2), ("unsupported_source", 2), ("dependency_missing", 3),
                               ("config_invalid", 3), ("auth_required", 3), ("network_unreachable", 4),
                               ("rate_limited", 4), ("internal_bug", 1), ("cancelled", 1)):
            self.assertEqual(ToolError(code, "x").exit_code, expected, code)

    def test_worst_exit_code_order(self):
        def err(code):
            return ToolError(code, "x")

        self.assertEqual(cli.worst_exit_code([err("network_unreachable"), err("bad_input")]), 2)
        self.assertEqual(cli.worst_exit_code([err("bad_input"), err("internal_bug")]), 1)
        self.assertEqual(cli.worst_exit_code([err("internal_bug"), err("dependency_missing"), err("bad_input")]), 3)
        self.assertEqual(cli.worst_exit_code([err("rate_limited")]), 4)


class CheckTest(CliTestBase):
    @staticmethod
    def item(name, level, error=None):
        return {"name": name, "ok": level != "error", "level": level, "message": f"{name} 訊息", "error": error}

    def test_check_json_ok(self):
        results = [self.item("ffmpeg", "ok"), self.item("GPU", "warn")]
        with mock.patch.object(cli.doctor_mod, "run_checks", return_value=results) as run:
            code, out, _ = run_cli("--check", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["checks"], results)
        self.assertEqual(payload["data"]["summary"], {"total": 2, "error": 0, "warn": 1})
        run.assert_called_once()

    def test_check_with_error_exits_3_and_carries_the_error_contract(self):
        err = ToolError("dependency_missing", "找不到 ffmpeg", source="ffmpeg",
                        remedy=Remedy("needs_config", "安裝 ffmpeg")).to_dict()
        results = [self.item("ffmpeg", "error", err), self.item("yt-dlp", "ok")]
        with mock.patch.object(cli.doctor_mod, "run_checks", return_value=results):
            code, out, _ = run_cli("--check", "--json")
        self.assertEqual(code, 3)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], err)
        self.assertEqual(len(payload["data"]["checks"]), 2)

    def test_check_error_without_contract_still_exits_3(self):
        results = [self.item("x", "error", None)]
        with mock.patch.object(cli.doctor_mod, "run_checks", return_value=results):
            code, out, _ = run_cli("--check", "--json")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["error"]["code"], "config_invalid")

    def test_check_human_list(self):
        results = [self.item("ffmpeg", "ok")]
        with mock.patch.object(cli.doctor_mod, "run_checks", return_value=results):
            code, out, _ = run_cli("--check")
        self.assertEqual(code, 0)
        self.assertIn("ffmpeg", out)

    def test_recheck_clears_health_first(self):
        order = []
        cli.health_mod.clear.side_effect = lambda *a: order.append("clear")
        with mock.patch.object(cli.doctor_mod, "run_checks", side_effect=lambda s: order.append("check") or []):
            code, _, _ = run_cli("--recheck", "--json")
        self.assertEqual((code, order), (0, ["clear", "check"]))

    def test_check_without_recheck_does_not_clear(self):
        with mock.patch.object(cli.doctor_mod, "run_checks", return_value=[]):
            run_cli("--check", "--json")
        cli.health_mod.clear.assert_not_called()


class StatusAndLibraryTest(CliTestBase):
    def test_status_lists_degraded_sources(self):
        entries = {"yt-dlp": {"code": "dependency_outdated", "count": 3, "state": "degraded"},
                   "llm:openai": {"code": "rate_limited", "count": 1, "state": "failing"}}
        with mock.patch.object(cli.health_mod, "entries", lambda: entries):
            code, out, _ = run_cli("--status", "--json")
        data = json.loads(out)["data"]
        self.assertEqual((code, data["running"], data["health"]["degraded"]), (0, [], ["yt-dlp"]))
        self.assertEqual(set(data["health"]["entries"]), {"yt-dlp", "llm:openai"})

    def test_library_json_is_read_only_listing(self):
        folder = self.make_video()
        before = sorted(p.name for p in folder.rglob("*"))
        code, out, _ = run_cli("--library", "--json")
        data = json.loads(out)["data"]
        self.assertEqual(code, 0)
        self.assertEqual(len(data["videos"]), 1)
        self.assertEqual(data["videos"][0]["analyses"][0]["slug"], "news")
        self.assertEqual(data["collections"], [])
        self.assertEqual(before, sorted(p.name for p in folder.rglob("*")))

    def test_library_does_not_create_the_output_folder(self):
        self.settings.output_custom = str(self.root / "not-yet")
        code, out, _ = run_cli("--library", "--json")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "not-yet").exists())

    def test_status_and_library_never_build_a_pipeline(self):
        with mock.patch.object(cli, "Pipeline", side_effect=AssertionError("不該建立 Pipeline")):
            run_cli("--status", "--json")
            run_cli("--library", "--json")


class RenderTest(CliTestBase):
    def test_render_from_existing_analysis_without_ai(self):
        folder = self.make_video()
        with mock.patch.object(cli, "library", lambda: LIB):
            code, out, _ = run_cli("--render", str(folder), "--outputs", "tree-md,tree-opml", "--json")
        data = json.loads(out)["data"]
        self.assertEqual(code, 0)
        self.assertEqual(data["slug"], "news")
        self.assertEqual(set(data["outputs"]), {"tree-md", "tree-opml"})
        for path in data["outputs"].values():
            self.assertTrue(Path(path).is_file())
            self.assertEqual(Path(path).parent, Artifacts(folder).outputs_dir)

    def test_render_picks_the_newest_analysis_or_the_given_slug(self):
        folder = self.make_video(slug="old")
        newer = Artifacts(folder).analysis("new")
        analysis.save(newer, sample())
        os.utime(Artifacts(folder).analysis("old"), (1, 1))
        _, out, _ = run_cli("--render", str(folder), "--outputs", "tree-md", "--json")
        self.assertEqual(json.loads(out)["data"]["slug"], "new")
        _, out, _ = run_cli("--render", str(folder), "--outputs", "tree-md", "--slug", "old", "--json")
        self.assertEqual(json.loads(out)["data"]["slug"], "old")

    def test_render_does_not_touch_the_llm(self):
        folder = self.make_video()
        with mock.patch("toolzoo.ai.LLM", side_effect=AssertionError("不該呼叫 AI")):
            code, _, _ = run_cli("--render", str(folder), "--outputs", "all", "--json")
        self.assertEqual(code, 0)

    def test_render_all_makes_every_registered_format(self):
        folder = self.make_video()
        _, out, _ = run_cli("--render", str(folder), "--outputs", "all", "--json")
        self.assertEqual(set(json.loads(out)["data"]["outputs"]), set(cli._all_renderers()))

    def test_render_errors(self):
        folder = self.make_video()
        code, out, _ = run_cli("--render", str(folder), "--json")                     # 沒說格式
        self.assertEqual((code, json.loads(out)["error"]["code"]), (2, "bad_input"))
        code, out, _ = run_cli("--render", str(folder), "--outputs", "nope", "--json")  # 不認得的格式
        self.assertEqual((code, json.loads(out)["error"]["code"]), (2, "bad_input"))
        code, out, _ = run_cli("--render", str(self.root / "missing"), "--outputs", "tree-md", "--json")
        self.assertEqual((code, json.loads(out)["error"]["code"]), (2, "bad_input"))
        empty = self.root / "empty"
        empty.mkdir()
        code, out, _ = run_cli("--render", str(empty), "--outputs", "tree-md", "--json")
        self.assertEqual(code, 2)
        self.assertIn("--reanalyze", json.loads(out)["error"]["remedy"]["action"])

    def test_render_outputs_default_to_the_preset(self):
        folder = self.make_video()
        preset = mock.Mock(outputs=("tree-md",))
        fake_lib = mock.Mock(wraps=LIB)
        fake_lib.presets = {"p": preset}
        fake_lib.plan.return_value = LIB.plan()
        with mock.patch.object(cli, "library", lambda: fake_lib):
            _, out, _ = run_cli("--render", str(folder), "--preset", "p", "--json")
        self.assertEqual(set(json.loads(out)["data"]["outputs"]), {"tree-md"})


class ReanalyzeTest(CliTestBase):
    def test_reanalyze_passes_plan_and_outputs_to_pipeline(self):
        folder = self.make_video()
        fake = mock.Mock()
        fake.reanalyze.return_value = {"folder": str(folder), "notes_file": "n.md", "outputs": {}}
        with mock.patch.object(cli, "Pipeline", return_value=fake):
            code, out, _ = run_cli("--reanalyze", str(folder), "-p", "news", "-w", "timeline",
                                   "--focus", "AI", "--outputs", "tree-md", "--json")
        self.assertEqual(code, 0)
        args, kwargs = fake.reanalyze.call_args
        self.assertEqual(args[0], folder)
        self.assertEqual((args[1].profile, args[1].modifiers, args[1].focus), ("news", ("timeline",), "AI"))
        self.assertEqual(kwargs["outputs"], ("tree-md",))
        self.assertEqual(json.loads(out)["data"]["notes_file"], "n.md")

    def test_reanalyze_tool_error_is_reported(self):
        folder = self.make_video()
        fake = mock.Mock()
        fake.reanalyze.side_effect = ToolError("rate_limited", "被限流")
        with mock.patch.object(cli, "Pipeline", return_value=fake):
            code, out, _ = run_cli("--reanalyze", str(folder), "--json")
        self.assertEqual((code, json.loads(out)["error"]["code"]), (4, "rate_limited"))


class FakeJobPipeline:
    """假的 Pipeline：run() 依網址回結果或丟錯；不連網、不呼叫 AI。"""

    ffmpeg = "ffmpeg"

    def __init__(self, root: Path, failing: dict[str, Exception] | None = None):
        self.root, self.failing = root, failing or {}

    def run(self, url, opts, emit=None, cancel=None):
        if url in self.failing:
            raise self.failing[url]
        vid = url.rsplit("=", 1)[-1]
        folder = self.root / vid
        folder.mkdir(exist_ok=True)
        a = Artifacts(folder).analysis("news")
        analysis.save(a, sample(title=vid))
        return {"url": url, "folder": str(folder), "title": vid, "notes_file": str(folder / "n.md"),
                "analysis_file": str(a), "outputs": {}, "_opts": opts.outputs}


U1, U2, U3 = (f"https://www.youtube.com/watch?v=vid{i}" for i in (1, 2, 3))


class RunMixin:
    def run_urls(self, *argv, failing=None):
        self.fake = FakeJobPipeline(self.root, failing)
        with mock.patch.object(cli, "Pipeline", return_value=self.fake), \
                mock.patch.object(cli.notify, "load_config", lambda: {"enabled": False, "url": ""}):
            return run_cli(*argv)


class RunTest(RunMixin, CliTestBase):
    def test_single_video_data_is_the_result_dict(self):
        code, out, _ = self.run_urls(U1, "--json")
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual((payload["data"]["status"], payload["data"]["error"]), ("done", None))

    def test_batch_data_is_an_array(self):
        code, out, _ = self.run_urls(U1, U2, "--json")
        data = json.loads(out)["data"]
        self.assertEqual((code, [d["status"] for d in data]), (0, ["done", "done"]))

    def test_batch_with_failure_keeps_successes_and_uses_worst_exit_code(self):
        failing = {U2: ToolError("bad_input", "網址不對"), U3: ToolError("dependency_outdated", "yt-dlp 太舊")}
        code, out, _ = self.run_urls(U1, U2, U3, "--json", failing=failing)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(code, 3)                                       # 環境(3) 比 輸入(2) 嚴重
        self.assertEqual(payload["error"]["code"], "dependency_outdated")
        by_url = {d["url"]: d for d in payload["data"]}
        self.assertEqual(by_url[U1]["status"], "done")
        self.assertEqual(by_url[U2]["error"]["code"], "bad_input")
        self.assertEqual(by_url[U3]["error"]["code"], "dependency_outdated")

    def test_unexpected_job_exception_is_internal_bug(self):
        code, out, _ = self.run_urls(U1, "--json", failing={U1: ValueError("壞掉了")})
        self.assertEqual((code, json.loads(out)["error"]["code"]), (1, "internal_bug"))

    def test_human_mode_failure_prints_reason_and_remedy(self):
        err = ToolError("dependency_outdated", "yt-dlp 太舊", remedy=Remedy("needs_update", "升級 yt-dlp"))
        code, out, _ = self.run_urls(U1, failing={U1: err})
        self.assertEqual(code, 3)
        self.assertIn("原因：yt-dlp 太舊", out)
        self.assertIn("怎麼辦：升級 yt-dlp", out)

    def test_progress_goes_to_stderr_in_json_mode(self):
        _, out, _ = self.run_urls(U1, "--json")
        json.loads(out)     # stdout 只有一份 JSON

    def test_outputs_option_reaches_job_options(self):
        _, out, _ = self.run_urls(U1, "--outputs", "tree-md,html-tabs", "--json")
        self.assertEqual(json.loads(out)["data"]["_opts"], ["tree-md", "html-tabs"])

    def test_outputs_default_to_the_preset_then_to_settings(self):
        fake_lib = mock.Mock(wraps=LIB)
        fake_lib.presets = {"p": mock.Mock(outputs=("tree-opml",))}
        fake_lib.plan.return_value = LIB.plan()
        with mock.patch.object(cli, "library", lambda: fake_lib):
            _, out, _ = self.run_urls(U1, "--preset", "p", "--json")
        self.assertEqual(json.loads(out)["data"]["_opts"], ["tree-opml"])
        _, out, _ = self.run_urls(U1, "--json")
        self.assertIsNone(json.loads(out)["data"]["_opts"])         # None = 用 settings.outputs

    def test_missing_ffmpeg_is_an_environment_error(self):
        self.fake = FakeJobPipeline(self.root)
        self.fake.ffmpeg = None
        with mock.patch.object(cli, "Pipeline", return_value=self.fake):
            code, out, _ = run_cli(U1, "--json")
        self.assertEqual((code, json.loads(out)["error"]["code"]), (3, "dependency_missing"))


class CombineTest(RunMixin, CliTestBase):
    def setUp(self):
        super().setUp()
        self.combine = mock.Mock(return_value={"folder": "F", "analysis_file": "A", "notes_file": "N",
                                               "analysis": {"big": "x" * 10}, "outputs": {}})
        self.estimate = mock.Mock(return_value=CombineEstimate(members=2, input_chars=10, input_tokens=100, calls=1,
                                                                needs_confirm=False))
        for name, fake in (("combine", self.combine), ("estimate", self.estimate)):
            p = mock.patch.object(cli.collection_mod, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def test_combine_after_processing_urls(self):
        code, out, _ = self.run_urls(U1, U2, "--combine", "--title", "本週", "--json")
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([v["status"] for v in payload["data"]["videos"]], ["done", "done"])
        coll = payload["data"]["collection"]
        self.assertEqual(coll["folder"], "F")
        self.assertNotIn("analysis", coll)                               # 不把整份 analysis 倒進輸出
        self.assertEqual(coll["estimate"]["calls"], 1)
        members = self.combine.call_args.args[0]
        self.assertEqual([m.folder.name for m in members], ["vid1", "vid2"])
        self.assertEqual(self.combine.call_args.kwargs["title"], "本週")
        self.assertEqual(self.combine.call_args.kwargs["output_root"], self.root)

    def test_combine_existing_folders(self):
        a, b = self.make_video("A", vid="aaaaaaaaaaa"), self.make_video("B", vid="bbbbbbbbbbb")
        with mock.patch.object(cli, "Pipeline", side_effect=AssertionError("不該處理網址")):
            code, out, _ = run_cli("--combine", "--folders", f"{a},{b}", "--json")
        self.assertEqual(code, 0)
        members = self.combine.call_args.args[0]
        self.assertEqual([m.folder for m in members], [a, b])
        self.assertEqual([m.analysis.name for m in members], ["analysis.news.json"] * 2)
        self.assertEqual(json.loads(out)["data"]["videos"], [])

    def test_needs_confirm_without_yes_is_bad_input_in_json_mode(self):
        self.estimate.return_value = CombineEstimate(2, 10, 90000, 3, needs_confirm=True)
        code, out, _ = self.run_urls(U1, U2, "--combine", "--json")
        payload = json.loads(out)
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "bad_input")
        self.assertIn("--yes", payload["error"]["remedy"]["action"])
        self.combine.assert_not_called()
        self.assertEqual(len(payload["data"]["videos"]), 2)               # 影片本身還是處理好了

    def test_needs_confirm_with_yes_goes_on(self):
        self.estimate.return_value = CombineEstimate(2, 10, 90000, 3, needs_confirm=True)
        code, _, _ = self.run_urls(U1, U2, "--combine", "--yes", "--json")
        self.assertEqual(code, 0)
        self.combine.assert_called_once()

    def test_needs_confirm_non_interactive_without_yes_stops(self):
        self.estimate.return_value = CombineEstimate(2, 10, 90000, 3, needs_confirm=True)
        code, _, err = self.run_urls(U1, U2, "--combine")      # stdin 不是終端機
        self.assertEqual(code, 2)
        self.assertIn("--yes", err)
        self.combine.assert_not_called()

    def test_needs_confirm_interactive_asks(self):
        self.estimate.return_value = CombineEstimate(2, 10, 90000, 3, needs_confirm=True)
        for answer, calls, expected in (("y", 1, 0), ("n", 0, 1)):
            self.combine.reset_mock()
            with mock.patch("builtins.input", return_value=answer):
                self.fake = FakeJobPipeline(self.root)
                with mock.patch.object(cli, "Pipeline", return_value=self.fake), \
                        mock.patch.object(cli.notify, "load_config", lambda: {"enabled": False, "url": ""}):
                    code, _, _ = run_cli(U1, U2, "--combine", stdin_tty=True)
            self.assertEqual((code, self.combine.call_count), (expected, calls), answer)

    def test_combine_is_skipped_when_a_video_failed(self):
        code, out, _ = self.run_urls(U1, U2, "--combine", "--json", failing={U2: ToolError("rate_limited", "限流")})
        payload = json.loads(out)
        self.assertEqual(code, 4)
        self.assertIsNone(payload["data"]["collection"])
        self.assertEqual(payload["data"]["videos"][0]["status"], "done")
        self.combine.assert_not_called()

    def test_combine_tool_error_exit_code(self):
        self.combine.side_effect = ToolError("rate_limited", "AI 被限流")
        code, out, _ = self.run_urls(U1, U2, "--combine", "--json")
        self.assertEqual((code, json.loads(out)["error"]["code"]), (4, "rate_limited"))

    def test_combine_input_errors(self):
        code, out, _ = self.run_urls(U1, "--combine", "--json")                       # 只有一支
        self.assertEqual((code, json.loads(out)["error"]["code"]), (2, "bad_input"))
        code, out, _ = run_cli(U1, U2, "--combine", "--no-notes", "--json")
        self.assertEqual(code, 2)
        code, out, _ = run_cli("--folders", "a,b", "--json")                          # 沒有 --combine
        self.assertEqual(code, 2)

    def test_combine_outputs_override_settings(self):
        self.run_urls(U1, U2, "--combine", "--outputs", "tree-md", "--json")
        self.assertEqual(self.combine.call_args.kwargs["settings"].outputs, ["tree-md"])


class OutputLocationTest(CliTestBase):
    def test_env_is_used_when_no_out(self):
        elsewhere = Path(self.tmp.name) / "from-env"
        os.environ[cli.OUT_ENV] = str(elsewhere)
        s = cli._settings_from_args(cli.build_parser().parse_args(["x"]), Settings())
        self.assertEqual(s.output_root(), elsewhere)

    def test_out_beats_env_and_env_beats_settings(self):
        env_dir, out_dir = Path(self.tmp.name) / "env", Path(self.tmp.name) / "out2"
        os.environ[cli.OUT_ENV] = str(env_dir)
        s = cli._settings_from_args(cli.build_parser().parse_args(["x", "--out", str(out_dir)]), Settings())
        self.assertEqual(s.output_root(), out_dir)
        saved = Settings(output=OUTPUT_CUSTOM, output_custom=str(Path(self.tmp.name) / "saved"))
        s = cli._settings_from_args(cli.build_parser().parse_args(["x"]), saved)
        self.assertEqual(s.output_root(), env_dir)
        del os.environ[cli.OUT_ENV]
        s = cli._settings_from_args(cli.build_parser().parse_args(["x"]), saved)
        self.assertEqual(s.output_root(), Path(saved.output_custom))

    def test_env_applies_to_library(self):
        elsewhere = Path(self.tmp.name) / "elsewhere"
        elsewhere.mkdir()
        os.environ[cli.OUT_ENV] = str(elsewhere)
        _, out, _ = run_cli("--library", "--json")
        self.assertEqual(json.loads(out)["data"]["videos"], [])


class NoLocalPathsTest(unittest.TestCase):
    def test_source_has_no_machine_specific_absolute_paths(self):
        """repo 是公開的，程式與文件草稿裡不能出現任何一台電腦才有的絕對路徑。"""
        pattern = re.compile(r"[A-Za-z]:\\\\?(?:Users|Documents and Settings)\\\\?|/home/\w+|/Users/\w+", re.I)
        files = list((TOOL / "video_notes").rglob("*.py")) + [TOOL / "VideoNotes.py", TOOL / "docs" / "synox-pack-draft.json"]
        bad = []
        for path in files:
            if path.is_file():
                for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    # errors.py 的去敏感規則本身要寫出這個樣式；它是偵測用的，不是路徑
                    if pattern.search(line) and path.name != "errors.py":
                        bad.append(f"{path.name}:{n}: {line.strip()[:80]}")
        self.assertEqual(bad, [])

    def test_pack_draft_is_not_read_by_the_program(self):
        for path in (TOOL / "video_notes").rglob("*.py"):
            self.assertNotIn("synox", path.read_text(encoding="utf-8").lower(), path.name)


if __name__ == "__main__":
    unittest.main()
