"""樹狀圖輸出：analysis.json → Markdown 清單／Mermaid／OPML／FreeMind／XMind。

五種格式共用同一棵樹（build_tree），各格式只負責「怎麼寫出去」與「怎麼跳脫」。
為什麼：使用者要的是「像 adapter pattern 一樣可以換不同模式」的流程圖輸出（XMind、Markdown、Flow Chart…），
格式的優缺點與選擇理由見 docs/tree-formats.md。

樹的結構：
    根 = analysis.title（沒有就 summary），備註 = summary／overview
    ├─ sections（遞迴 children）；每個 section 的 points 當葉子，section.summary 當備註
    ├─ 來源影片（只有 kind=collection）
    ├─ 重點（key_points）、名詞（terms：名詞 → 解釋）、行動（actions）、注意（caveats）
layout_hint.tree_depth 決定預設展開幾層（只有 FreeMind、XMind 支援折疊；其他格式忽略）。

安全：analysis 的文字都是不可信資料。XML 一律交給 xml.etree 跳脫並先剝掉 XML 不允許的控制字元；
連結只允許 http／https；Mermaid 節點文字一律放進雙引號並把特殊字元轉成 #code; 實體；
Markdown 把行內符號與行首符號加反斜線。截斷一律發生在「跳脫之前」，所以不會切壞跳脫序列。
"""

from __future__ import annotations

import io
import json
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse

from video_notes.adapters.render import REGISTRY, RenderContext
from video_notes.errors import ToolError

MAX_DEPTH = 8            # 防呆：超過就不再往下展（schema 本來最多 6 層）
NOTE_LIMIT = 2000        # 備註最長
DEFAULT_TREE_DEPTH = 3

BRANCH_SOURCES = "來源影片"
BRANCH_KEY_POINTS = "重點"
BRANCH_TERMS = "名詞"
BRANCH_ACTIONS = "行動"
BRANCH_CAVEATS = "注意"

# XML 1.0 不允許的字元（控制字元、孤立 surrogate、U+FFFE/FFFF）
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_WS = re.compile(r"\s+")


# ---------------------------------------------------------------- 文字處理

def clean_line(v) -> str:
    """單行文字：剝控制字元、空白（含換行）壓成一個空格。"""
    if not isinstance(v, str):
        return "" if v is None else clean_line(str(v))
    return _WS.sub(" ", _ILLEGAL.sub("", v)).strip()


def clean_note(v) -> str:
    """多行備註：保留換行，剝控制字元，限制長度。"""
    if not isinstance(v, str):
        return ""
    s = _ILLEGAL.sub("", v).replace("\r\n", "\n").replace("\r", "\n").strip()
    return s if len(s) <= NOTE_LIMIT else s[: NOTE_LIMIT - 1] + "…"


def fit(text: str, limit: int) -> tuple[str, bool]:
    """截斷到 limit 個字元（含「…」）。回傳 (顯示文字, 是否被截斷)。必須在跳脫之前呼叫。"""
    if len(text) <= limit:
        return text, False
    return text[: max(limit - 1, 1)].rstrip() + "…", True


def safe_url(v) -> str:
    """只放行 http／https 且沒有空白或控制字元的網址；其他一律回空字串。"""
    if not isinstance(v, str):
        return ""
    u = v.strip()
    if not u or _ILLEGAL.search(u) or re.search(r"\s", u):
        return ""
    try:
        p = urlparse(u)
    except ValueError:
        return ""
    return u if p.scheme in ("http", "https") and p.netloc else ""


# ---------------------------------------------------------------- 共用的樹

@dataclass
class Node:
    text: str
    note: str = ""
    url: str = ""
    children: list["Node"] = field(default_factory=list)

    def count(self) -> int:
        return 1 + sum(c.count() for c in self.children)


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _section_node(sec, depth: int) -> Node | None:
    if not isinstance(sec, dict):
        return None
    node = Node(clean_line(sec.get("title")) or "（未命名）", clean_note(sec.get("summary")))
    for p in _list(sec.get("points")):
        t = clean_line(p)
        if t:
            node.children.append(Node(t))
    if depth < MAX_DEPTH:
        for child in _list(sec.get("children")):
            c = _section_node(child, depth + 1)
            if c:
                node.children.append(c)
    return node


def _branch(label: str, items: list[Node]) -> Node | None:
    return Node(label, children=items) if items else None


def build_tree(analysis: dict) -> Node:
    title = clean_line(analysis.get("title"))
    summary = clean_note(analysis.get("summary"))
    overview = clean_note(analysis.get("overview"))
    if title:
        root = Node(title, "\n\n".join(x for x in (summary, overview) if x))
    else:
        root = Node(clean_line(summary) or "Video Notes", overview)

    for sec in _list(analysis.get("sections")):
        n = _section_node(sec, 1)
        if n:
            root.children.append(n)

    extra: list[Node | None] = []
    if analysis.get("kind") == "collection":
        srcs = []
        for s in _list(analysis.get("sources")):
            if isinstance(s, dict):
                t = clean_line(s.get("title")) or clean_line(s.get("url")) or clean_line(s.get("id"))
                if t:
                    srcs.append(Node(t, url=safe_url(s.get("url"))))
        extra.append(_branch(BRANCH_SOURCES, srcs))
    extra.append(_branch(BRANCH_KEY_POINTS, [Node(t) for t in map(clean_line, _list(analysis.get("key_points"))) if t]))
    terms = []
    for it in _list(analysis.get("terms")):
        if isinstance(it, dict) and clean_line(it.get("term")):
            n = Node(clean_line(it.get("term")))
            d = clean_line(it.get("definition"))
            if d:
                n.children.append(Node(d))
            terms.append(n)
    extra.append(_branch(BRANCH_TERMS, terms))
    extra.append(_branch(BRANCH_ACTIONS, [Node(t) for t in map(clean_line, _list(analysis.get("actions"))) if t]))
    extra.append(_branch(BRANCH_CAVEATS, [Node(t) for t in map(clean_line, _list(analysis.get("caveats"))) if t]))
    root.children.extend(n for n in extra if n)
    return root


def tree_depth(analysis: dict) -> int:
    hint = analysis.get("layout_hint")
    d = hint.get("tree_depth") if isinstance(hint, dict) else None
    return d if isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= 6 else DEFAULT_TREE_DEPTH


def _shown(node: Node, limit: int) -> tuple[str, str]:
    """(節點標題, 備註)。標題被截斷時，完整文字放進備註（支援備註的格式才用得到）。"""
    title, cut = fit(node.text, limit)
    note = node.note
    if cut:
        note = clean_note(node.text + ("\n\n" + note if note else ""))
    return title, note


# ---------------------------------------------------------------- 基底

class _TreeRenderer:
    name = ""
    label = ""
    extension = ""
    binary = False

    def capabilities(self) -> dict:
        return {"formats": [self.extension], "needs_network": False, "needs_llm": False, "group": "tree"}

    def check(self) -> ToolError | None:
        return None

    def render(self, analysis: dict, ctx: RenderContext):  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------- Markdown

_MD_INLINE = re.compile(r"([\\`*_\[\]<>|~])")
_MD_ENTITY = re.compile(r"&(#\w+|\w+);")
_MD_START = re.compile(r"^([#+\-!>=]|\d+(?=[.)]))")


def md_escape(text: str) -> str:
    s = _MD_INLINE.sub(r"\\\1", text)
    s = _MD_ENTITY.sub(lambda m: "\\&" + m.group(0)[1:], s)
    m = _MD_START.match(s)
    if m:
        if m.group(1).isdigit():
            i = len(m.group(1))
            s = s[:i] + "\\" + s[i:]
        else:
            s = "\\" + s
    return s


class TreeMarkdown(_TreeRenderer):
    name, label, extension = "tree-md", "樹狀圖（Markdown 清單）", ".md"
    LIMIT = 500

    def _line(self, node: Node) -> str:
        t, _ = fit(node.text, self.LIMIT)
        s = md_escape(t)
        if node.url:
            s = f"[{s}](" + quote(node.url, safe=":/?#@!$&'*+,;=%~-._") + ")"
        return s

    def render(self, analysis: dict, ctx: RenderContext) -> str:
        root = build_tree(analysis)
        out = ["# " + md_escape(fit(root.text, self.LIMIT)[0]), ""]
        if root.note:
            out += ["> " + md_escape(l) if l else ">" for l in root.note.split("\n")] + [""]

        def walk(n: Node, level: int) -> None:
            out.append("  " * level + "- " + self._line(n))
            if n.note:
                out.append("  " * (level + 1) + "- *" + md_escape(clean_line(n.note)[: self.LIMIT]) + "*")
            for c in n.children:
                walk(c, level + 1)

        for c in root.children:
            walk(c, 0)
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------- Mermaid

def mermaid_escape(text: str) -> str:
    """放進 ["..."] 的文字：# 先轉（避免和實體碼衝突），再轉會破壞語法的字元。"""
    table = {"#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;", "`": "#96;", "%": "#37;",
             "\\": "#92;", "\n": " "}
    return "".join(table.get(ch, ch) for ch in text)


class TreeMermaid(_TreeRenderer):
    name, label, extension = "tree-mermaid", "樹狀圖（Mermaid mindmap）", ".mmd"
    LIMIT = 100

    def render(self, analysis: dict, ctx: RenderContext) -> str:
        root = build_tree(analysis)
        counter = [0]
        out = ["mindmap"]

        def walk(n: Node, level: int) -> None:
            text = mermaid_escape(fit(n.text, self.LIMIT)[0])
            nid = "root" if level == 1 else f"n{counter[0]}"
            counter[0] += 1
            shape = f'(("{text}"))' if level == 1 else f'["{text}"]'
            out.append("  " * level + nid + shape)
            for c in n.children:
                walk(c, level + 1)

        walk(root, 1)
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------- XML 共用

def _xml_bytes(root: ET.Element) -> bytes:
    if hasattr(ET, "indent"):
        ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


# ---------------------------------------------------------------- OPML

class TreeOpml(_TreeRenderer):
    name, label, extension, binary = "tree-opml", "樹狀圖（OPML）", ".opml", True
    LIMIT = 160

    def render(self, analysis: dict, ctx: RenderContext) -> bytes:
        tree = build_tree(analysis)
        opml = ET.Element("opml", {"version": "2.0"})
        head = ET.SubElement(opml, "head")
        ET.SubElement(head, "title").text = fit(tree.text, self.LIMIT)[0]
        body = ET.SubElement(opml, "body")

        def walk(parent: ET.Element, n: Node) -> None:
            text, note = _shown(n, self.LIMIT)
            attrs = {"text": text}
            if note:
                attrs["_note"] = note
            if n.url:
                attrs.update({"type": "link", "url": n.url})
            el = ET.SubElement(parent, "outline", attrs)
            for c in n.children:
                walk(el, c)

        walk(body, tree)
        return _xml_bytes(opml)


# ---------------------------------------------------------------- FreeMind

class TreeFreemind(_TreeRenderer):
    name, label, extension, binary = "tree-freemind", "樹狀圖（FreeMind .mm）", ".mm", True
    LIMIT = 160

    def render(self, analysis: dict, ctx: RenderContext) -> bytes:
        tree = build_tree(analysis)
        depth = tree_depth(analysis)
        m = ET.Element("map", {"version": "1.0.1"})

        def walk(parent: ET.Element, n: Node, level: int) -> None:
            text, note = _shown(n, self.LIMIT)
            attrs = {"TEXT": text}
            if n.url:
                attrs["LINK"] = n.url
            if n.children and level >= depth:
                attrs["FOLDED"] = "true"
            el = ET.SubElement(parent, "node", attrs)
            if note:
                rc = ET.SubElement(el, "richcontent", {"TYPE": "NOTE"})
                html = ET.SubElement(rc, "html")
                ET.SubElement(html, "head")
                body = ET.SubElement(html, "body")
                for line in note.split("\n"):
                    ET.SubElement(body, "p").text = line
            for c in n.children:
                walk(el, c, level + 1)

        walk(m, tree, 0)
        return _xml_bytes(m)


# ---------------------------------------------------------------- XMind

class TreeXmind(_TreeRenderer):
    name, label, extension, binary = "tree-xmind", "樹狀圖（XMind .xmind）", ".xmind", True
    LIMIT = 120
    # 固定時間戳：同樣的輸入產生完全相同的位元組
    ZIP_TIME = (2026, 1, 1, 0, 0, 0)

    def render(self, analysis: dict, ctx: RenderContext) -> bytes:
        tree = build_tree(analysis)
        depth = tree_depth(analysis)
        ns = uuid.UUID("6f1c1c52-0b0e-4a43-9f0e-0d6e6b6f7a01")

        def tid(path: str) -> str:
            return uuid.uuid5(ns, path).hex[:26]

        def topic(n: Node, level: int, path: str) -> dict:
            text, note = _shown(n, self.LIMIT)
            t: dict = {"id": tid(path), "class": "topic", "title": text}
            if n.url:
                t["href"] = n.url
            if note:
                t["notes"] = {"plain": {"content": note}}
            if n.children:
                t["children"] = {"attached": [topic(c, level + 1, f"{path}/{i}") for i, c in enumerate(n.children)]}
                if level >= depth:
                    t["branch"] = "folded"
            return t

        root_topic = topic(tree, 0, "root")
        root_topic["structureClass"] = "org.xmind.ui.map.clockwise"
        sheet_id = tid("sheet")
        content = [{
            "id": sheet_id,
            "class": "sheet",
            "title": fit(tree.text, self.LIMIT)[0],
            "rootTopic": root_topic,
            "topicOverlapping": "overlap",
        }]
        metadata = {
            "dataStructureVersion": "2",
            "creator": {"name": "Video Notes", "version": ctx.tool_version or ""},
            "layoutEngineVersion": "3",
            "activeSheetId": sheet_id,
        }
        manifest = {"file-entries": {"content.json": {}, "metadata.json": {}}}

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in (("content.json", content), ("metadata.json", metadata), ("manifest.json", manifest)):
                zi = zipfile.ZipInfo(name, self.ZIP_TIME)   # 不放資料夾；檔案直接在 zip 根目錄
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        return buf.getvalue()


# ---------------------------------------------------------------- 註冊

for _cls, _order in ((TreeMarkdown, 20), (TreeMermaid, 21), (TreeOpml, 23), (TreeFreemind, 24), (TreeXmind, 25)):
    REGISTRY.register(_cls.name, _cls, label=_cls.label, order=_order)
