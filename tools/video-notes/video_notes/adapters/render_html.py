"""HTML 輸出：把 analysis 填進範本（html-sheet／html-longform／html-tabs／tree-html）。

範本契約（範本由設計師另外做，放在 templates/）：
    - 範本裡恰好一處 <script type="application/json" id="vn-data">__VN_DATA__</script>
    - 我們把 __VN_DATA__ 換成 {"analysis": ..., "meta": {profile_name, modifier_names, tool_version, generated_at}} 的 JSON
    - JSON 裡的 < > & U+2028 U+2029 一律轉成 \\uXXXX，資料區不可能出現 </script> 或 <!--
    - 範本自己用 textContent 之類的方式把資料畫出來（不用 innerHTML 塞資料）；連結只允許 http／https
範本找法：先找使用者覆蓋 user_dir()/templates/<檔名>，沒有再用 bundle_dir()/templates/<檔名>（打包後也找得到）。
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

from video_notes.adapters.render import REGISTRY, RenderContext
from video_notes.adapters.render_tree import safe_url
from video_notes.errors import Remedy, ToolError

PLACEHOLDER = "__VN_DATA__"

# 測試用：設成資料夾清單就只找這些地方（None = user_dir()/templates 再 bundle_dir()/templates）
TEMPLATE_DIRS: list[Path] | None = None

_JS_ESCAPES = {
    ord("<"): "\\u003c",
    ord(">"): "\\u003e",
    ord("&"): "\\u0026",
    0x2028: "\\u2028",
    0x2029: "\\u2029",
}


def template_dirs() -> list[Path]:
    if TEMPLATE_DIRS is not None:
        return list(TEMPLATE_DIRS)
    from video_notes.config import bundle_dir, user_dir

    dirs: list[Path] = []
    try:
        dirs.append(user_dir() / "templates")
    except OSError:
        pass
    dirs.append(bundle_dir() / "templates")
    return dirs


def find_template(filename: str) -> Path | None:
    for d in template_dirs():
        p = d / filename
        if p.is_file():
            return p
    return None


def tool_version() -> str:
    try:
        from version import __version__

        return str(__version__)
    except ImportError:
        return ""


def to_script_json(obj) -> str:
    """JSON 字串，可以安全放在 <script type="application/json"> 裡。"""
    return json.dumps(obj, ensure_ascii=False).translate(_JS_ESCAPES)


def _sanitize(analysis: dict) -> dict:
    """深拷貝後把非 http(s) 的來源網址清掉（範本也會擋，這是第二道）。"""
    data = copy.deepcopy(analysis)
    srcs = data.get("sources")
    if isinstance(srcs, list):
        for s in srcs:
            if isinstance(s, dict) and "url" in s:
                s["url"] = safe_url(s.get("url"))
    return data


class HtmlTemplateRenderer:
    binary = False
    extension = ".html"

    def __init__(self, name: str, label: str, filename: str, group: str):
        self.name, self.label, self.filename, self._group = name, label, filename, group

    def capabilities(self) -> dict:
        return {"formats": [self.extension], "needs_network": False, "needs_llm": False, "group": self._group}

    def check(self) -> ToolError | None:
        if find_template(self.filename) is None:
            where = " 或 ".join(str(d / self.filename) for d in template_dirs())
            return ToolError("dependency_missing", f"找不到 HTML 範本 {self.filename}",
                             remedy=Remedy("needs_owner", f"把範本放到：{where}"), source=self.name)
        return None

    def render(self, analysis: dict, ctx: RenderContext) -> str:
        err = self.check()
        if err:
            raise err
        path = find_template(self.filename)
        template = path.read_text(encoding="utf-8")
        if template.count(PLACEHOLDER) != 1:
            raise ToolError("config_invalid", f"範本 {self.filename} 的 {PLACEHOLDER} 必須恰好出現一次"
                            f"（目前 {template.count(PLACEHOLDER)} 次）",
                            remedy=Remedy("needs_owner", "範本裡只留 <script type=\"application/json\" id=\"vn-data\">"
                                          f"{PLACEHOLDER}</script> 一處"), source=self.name)
        payload = {
            "analysis": _sanitize(analysis),
            "meta": {
                "profile_name": ctx.profile_name,
                "modifier_names": list(ctx.modifier_names),
                "tool_version": ctx.tool_version or tool_version(),
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
        }
        return template.replace(PLACEHOLDER, to_script_json(payload), 1)


for _name, _label, _file, _group, _order in (
    ("html-sheet", "HTML：一小張", "sheet.html", "html", 30),
    ("html-longform", "HTML：長文＋目錄", "longform.html", "html", 31),
    ("html-tabs", "HTML：多分頁", "tabs.html", "html", 32),
    ("tree-html", "樹狀圖（可折疊 HTML）", "tree.html", "tree", 22),
):
    REGISTRY.register(_name, (lambda n=_name, l=_label, f=_file, g=_group: HtmlTemplateRenderer(n, l, f, g)),
                      label=_label, order=_order)
