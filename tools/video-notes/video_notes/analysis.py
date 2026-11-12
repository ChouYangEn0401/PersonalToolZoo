"""analysis.json：每支影片（或多支合併）分析一次後存下來的結構化結果——v2 的核心資產。

管線：來源 → 語音辨識 → **分析（產生這份）** → 輸出（Markdown／樹狀圖／HTML 範本／未來的 PPT、Word…）。
輸出層只讀 analysis，不碰逐字稿，所以換輸出形式不用再花分析的 token；要重新分析才重呼叫 AI。

欄位說明與範例：docs/analysis-schema.md（改 schema 時兩邊一起改，並把 SCHEMA_VERSION 加一）。

設計原則：
- 乾淨、平坦、純文字：欄位裡不放 Markdown 或 HTML（輸出層自己決定怎麼排版），之後才能直接交給 pptx／docx 之類的 skills。
- AI 只負責 AI_FIELDS；其餘（來源、模式、版本、成本、品質旗標）由程式填，不讓模型抄錯。
- 所有文字都是「不可信的外部資料」（來自影片標題、逐字稿）：輸出層一律跳脫，連結只允許 http/https。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from video_notes.errors import Remedy, ToolError

SCHEMA_VERSION = 1

KIND_VIDEO = "video"
KIND_COLLECTION = "collection"

TEMPLATES = ("sheet", "longform", "tabs")    # HTML 範本；layout_hint.template 只能是這幾個

# AI 要產生的欄位（給分析 prompt 用的說明在 AI_SCHEMA_TEXT）
AI_FIELDS = ("summary", "overview", "sections", "key_points", "timeline", "terms", "actions", "quotes",
             "perspectives", "caveats", "tags", "layout_hint")
# 程式填的欄位
META_FIELDS = ("schema_version", "kind", "title", "mode", "language", "sources", "provenance", "cost",
               "quality_flags", "members")

QUALITY_FLAGS = (
    "transcript_low_confidence",   # 語音辨識品質差（例如雲端失敗退回本機的小模型）
    "schema_repair_failed",        # AI 兩次都沒給出合格 JSON，這份是降級結果
    "truncated_input",             # 逐字稿太長被截斷（理論上應分段，不該發生）
    "stt_fallback_local",          # 雲端語音辨識失敗，退回本機
    "estimated_cost",              # cost 是估計值
    "member_missing",              # 合併時有成員的 analysis 讀不到
)

MAX_DEPTH = 6   # sections 最多幾層


# --------------------------------------------------------------------------- 建立
def source_id(platform: str, video_id: str) -> str:
    return f"{platform}:{video_id}"


def source_hash(platform: str, video_id: str) -> str:
    return hashlib.sha1(source_id(platform, video_id).encode("utf-8")).hexdigest()[:16]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_analysis(*, kind: str = KIND_VIDEO, title: str = "", mode: dict | None = None, language: str = "",
                 sources: list[dict] | None = None) -> dict:
    """空的 analysis（所有欄位都在、都是空值）。AI 的結果用 merge_ai() 填進來。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "title": title,
        "mode": {"profile": "", "modifiers": [], "focus": "", **(mode or {})},
        "language": language,
        "summary": "",
        "overview": "",
        "sections": [],
        "key_points": [],
        "timeline": [],
        "terms": [],
        "actions": [],
        "quotes": [],
        "perspectives": [],
        "caveats": [],
        "tags": [],
        "layout_hint": {"template": "longform", "tree_depth": 3},
        "sources": list(sources or []),
        "members": [],      # 只有 collection 用：成員影片的 analysis 檔（相對輸出資料夾）
        "provenance": {"source_hash": "", "stt": {}, "analyzer": {}, "prompt_version": "", "created_at": now()},
        "cost": {"input_tokens": 0, "output_tokens": 0, "estimated": True, "audio_seconds": 0},
        "quality_flags": [],
    }


def source_entry(*, platform: str, video_id: str, url: str, title: str = "", channel: str = "",
                 duration: float = 0, date: str = "", folder: str = "") -> dict:
    return {"id": source_id(platform, video_id), "url": url, "title": title, "channel": channel,
            "duration": duration or 0, "date": date, "folder": folder}


def merge_ai(base: dict, ai: dict) -> dict:
    """把 AI 回傳（已通過 validate_ai）的欄位放進 base，回傳新的 dict。AI 給的 title 只在 base 沒有標題時使用。"""
    out = json.loads(json.dumps(base))
    for key in AI_FIELDS:
        if key in ai:
            out[key] = ai[key]
    if not out.get("title") and isinstance(ai.get("title"), str):
        out["title"] = ai["title"].strip()
    return normalize(out)


# --------------------------------------------------------------------------- 驗證
def _err(errors: list[str], path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def _str(errors, path, v, *, required=False) -> None:
    if not isinstance(v, str):
        _err(errors, path, "要是字串")
    elif required and not v.strip():
        _err(errors, path, "不可以是空字串")


def _num_or_null(errors, path, v) -> None:
    if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
        _err(errors, path, "要是 >= 0 的秒數或 null")


def _str_list(errors, path, v) -> None:
    if not isinstance(v, list):
        _err(errors, path, "要是字串陣列")
        return
    for i, item in enumerate(v):
        _str(errors, f"{path}[{i}]", item)


def _obj_list(errors, path, v, spec: dict[str, str]) -> None:
    """spec：欄位 → 'str!'（必填字串）／'str'（可省略字串）／'time'（秒數或 null，可省略）。"""
    if not isinstance(v, list):
        _err(errors, path, "要是陣列")
        return
    for i, item in enumerate(v):
        p = f"{path}[{i}]"
        if not isinstance(item, dict):
            _err(errors, p, "要是物件")
            continue
        for key, kind in spec.items():
            if kind == "str!":
                _str(errors, f"{p}.{key}", item.get(key), required=True)
            elif kind == "str" and key in item:
                _str(errors, f"{p}.{key}", item[key])
            elif kind == "time" and key in item:
                _num_or_null(errors, f"{p}.{key}", item[key])


def _sections(errors, path, v, depth=1) -> None:
    if not isinstance(v, list):
        _err(errors, path, "要是陣列")
        return
    if depth > MAX_DEPTH:
        _err(errors, path, f"最多 {MAX_DEPTH} 層")
        return
    for i, sec in enumerate(v):
        p = f"{path}[{i}]"
        if not isinstance(sec, dict):
            _err(errors, p, "要是物件")
            continue
        _str(errors, f"{p}.title", sec.get("title"), required=True)
        if "summary" in sec:
            _str(errors, f"{p}.summary", sec["summary"])
        if "points" in sec:
            _str_list(errors, f"{p}.points", sec["points"])
        if "start" in sec:
            _num_or_null(errors, f"{p}.start", sec["start"])
        if "children" in sec:
            _sections(errors, f"{p}.children", sec["children"], depth + 1)


def validate_ai(data: Any) -> list[str]:
    """檢查 AI 回傳的部分。回傳錯誤訊息清單（空 = 合格）；訊息要能直接回給 AI 請它修正。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["最外層要是 JSON 物件"]
    _str(errors, "summary", data.get("summary"), required=True)
    if "overview" in data:
        _str(errors, "overview", data["overview"])
    if "title" in data:
        _str(errors, "title", data["title"])
    _sections(errors, "sections", data.get("sections"))
    if isinstance(data.get("sections"), list) and not data["sections"]:
        _err(errors, "sections", "至少要有一個段落")
    for key in ("key_points", "actions", "caveats", "tags"):
        if key in data:
            _str_list(errors, key, data[key])
    if "timeline" in data:
        _obj_list(errors, "timeline", data["timeline"], {"label": "str!", "detail": "str", "time": "time"})
    if "terms" in data:
        _obj_list(errors, "terms", data["terms"], {"term": "str!", "definition": "str!"})
    if "quotes" in data:
        _obj_list(errors, "quotes", data["quotes"], {"text": "str!", "speaker": "str", "time": "time"})
    if "perspectives" in data:
        _obj_list(errors, "perspectives", data["perspectives"], {"who": "str!", "stance": "str!"})
    hint = data.get("layout_hint")
    if hint is not None:
        if not isinstance(hint, dict):
            _err(errors, "layout_hint", "要是物件")
        else:
            if "template" in hint and hint["template"] not in TEMPLATES:
                _err(errors, "layout_hint.template", f"只能是 {', '.join(TEMPLATES)}")
            depth = hint.get("tree_depth")
            if depth is not None and (not isinstance(depth, int) or isinstance(depth, bool)
                                      or not 1 <= depth <= MAX_DEPTH):
                _err(errors, "layout_hint.tree_depth", f"要是 1~{MAX_DEPTH} 的整數")
    return errors


def validate(data: Any) -> list[str]:
    """完整 analysis（含程式填的欄位）。"""
    if not isinstance(data, dict):
        return ["最外層要是 JSON 物件"]
    errors = validate_ai(data)
    if data.get("schema_version") != SCHEMA_VERSION:
        _err(errors, "schema_version", f"要是 {SCHEMA_VERSION}")
    if data.get("kind") not in (KIND_VIDEO, KIND_COLLECTION):
        _err(errors, "kind", "要是 video 或 collection")
    _str(errors, "title", data.get("title"))
    _obj_list(errors, "sources", data.get("sources"), {"id": "str!", "url": "str", "title": "str"})
    _str_list(errors, "quality_flags", data.get("quality_flags", []))
    for key in ("mode", "provenance", "cost"):
        if not isinstance(data.get(key), dict):
            _err(errors, key, "要是物件")
    return errors


# --------------------------------------------------------------------------- 正規化
def _clean_text(v: Any) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def _clean_sections(v: Any, depth: int = 1) -> list[dict]:
    out = []
    for sec in v if isinstance(v, list) else []:
        if not isinstance(sec, dict) or not str(sec.get("title", "")).strip():
            continue
        item = {"title": _clean_text(sec["title"]),
                "summary": _clean_text(sec.get("summary", "")),
                "points": [_clean_text(p) for p in sec.get("points") or [] if str(p).strip()],
                "start": sec.get("start") if isinstance(sec.get("start"), (int, float))
                and not isinstance(sec.get("start"), bool) else None,
                "children": _clean_sections(sec.get("children"), depth + 1) if depth < MAX_DEPTH else []}
        out.append(item)
    return out


def normalize(data: dict) -> dict:
    """補齊缺的欄位、去掉多餘空白，讓輸出層不用到處判斷 None。不改變語意。"""
    base = new_analysis(kind=data.get("kind") or KIND_VIDEO)
    for key, default in base.items():
        if key not in data or data[key] is None:
            data[key] = default
    data["summary"] = _clean_text(data["summary"])
    data["overview"] = str(data.get("overview") or "").strip()
    data["sections"] = _clean_sections(data["sections"])
    for key in ("key_points", "actions", "caveats", "tags", "quality_flags"):
        data[key] = [_clean_text(x) for x in data[key] if str(x).strip()] if isinstance(data[key], list) else []
    hint = data["layout_hint"] if isinstance(data["layout_hint"], dict) else {}
    data["layout_hint"] = {"template": hint.get("template") if hint.get("template") in TEMPLATES else "longform",
                           "tree_depth": hint.get("tree_depth") if isinstance(hint.get("tree_depth"), int)
                           and 1 <= hint["tree_depth"] <= MAX_DEPTH else 3}
    return data


def add_flag(data: dict, flag: str) -> None:
    flags = data.setdefault("quality_flags", [])
    if flag not in flags:
        flags.append(flag)


# --------------------------------------------------------------------------- 讀寫
def save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load(path: Path) -> dict:
    """讀 analysis.json。讀不到、不是 JSON、或 schema 版本比程式新 → ToolError（明確報錯，不默默亂讀）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ToolError("bad_input", "讀不到分析結果檔", detail=str(exc), source="analysis") from exc
    except ValueError as exc:
        raise ToolError("bad_input", "分析結果檔不是有效的 JSON（可能寫到一半），請重新分析",
                        detail=str(exc), source="analysis",
                        remedy=Remedy("auto_fixable", "對這支影片選「重新分析」")) from exc
    version = data.get("schema_version") if isinstance(data, dict) else None
    if not isinstance(version, int):
        raise ToolError("bad_input", "分析結果檔缺少 schema_version", source="analysis",
                        remedy=Remedy("auto_fixable", "對這支影片選「重新分析」"))
    if version > SCHEMA_VERSION:
        raise ToolError("dependency_outdated", f"分析結果檔是較新的格式（v{version}），這個版本的程式看不懂",
                        source="analysis", remedy=Remedy("needs_update", "更新 Video Notes 到最新版"))
    return normalize(data)


# --------------------------------------------------------------------------- 給 AI 的格式說明
AI_SCHEMA_TEXT = """\
只輸出一個 JSON 物件（不要 ``` 包起來、不要任何其他文字），欄位如下。所有文字都是純文字：不要 Markdown 符號（# * ** ` >）、不要 HTML。
{
  "summary": "一句話結論（必填）",
  "overview": "2~4 句的概述，可省略",
  "sections": [            // 筆記主體（必填，至少一個）。依「筆記格式」的段落排列；可以有子段落（children），最多 6 層
    {"title": "段落標題", "summary": "這段一兩句話（可省略）", "points": ["條列重點", "..."],
     "start": 秒數或 null,   // 這段在影片中的開始時間；逐字稿有 [mm:ss] 才填
     "children": [ ...同樣格式... ]}
  ],
  "key_points": ["全片最重要的 3~7 點"],
  "timeline": [{"time": 秒數或 null, "label": "發生什麼", "detail": "補充（可省略）"}],
  "terms": [{"term": "名詞", "definition": "解釋"}],
  "actions": ["可以執行的行動"],
  "quotes": [{"text": "原話", "speaker": "誰說的（可省略）", "time": 秒數或 null}],
  "perspectives": [{"who": "誰", "stance": "立場或說法"}],
  "caveats": ["風險、未證實、影片沒說清楚的地方"],
  "tags": ["3~8 個主題標籤"],
  "layout_hint": {"template": "sheet|longform|tabs", "tree_depth": 1~6}
}
規則：
- 沒有內容的欄位給空陣列 []，不要硬湊。timeline／terms／actions／quotes 只放在對應欄位，不要在 sections 裡重複寫一次。
- layout_hint 是你依內容選的呈現方式：內容少、一眼看完用 sheet；一般長度用 longform；主題很多、像課綱一樣需要分頁用 tabs。
  tree_depth 是做成樹狀圖時建議展開幾層。
- 時間一律用「秒數」數字（例如 95），不要寫 "01:35"。"""
