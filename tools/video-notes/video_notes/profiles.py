"""整理方案：可插拔、可混用的提示詞。

三種積木，全部是 prompts/ 底下的 TOML 檔，不用改程式就能新增或修改：

    profiles/   影片類型（知識、新聞、Podcast、娛樂、財經…）：決定「什麼重要、什麼略過、筆記長怎樣」
    modifiers/  加料（時間軸、行動清單、金句、名詞解釋、極簡、詳細、英文）：可以同時套好幾個
    presets/    常用組合（類型 + 加料 + 關注主題），CLI 用 --preset 一次選好

讀取順序：程式內建的 prompts/ → 使用者資料夾 %APPDATA%\\PersonalToolZoo\\video-notes\\prompts\\。
同一個 id 後讀到的覆蓋前面的，所以想改內建方案，複製一份到使用者資料夾再改就好（更新程式也不會被蓋掉）。
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

AUTO = "auto"
FALLBACK_PROFILE = "general"


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    icon: str = "📝"
    description: str = ""
    order: int = 100
    signals: str = ""          # 自動判斷時給分類器看的特徵
    goal: str = ""
    keep: tuple[str, ...] = ()
    drop: tuple[str, ...] = ()
    format: str = ""


@dataclass(frozen=True)
class Modifier:
    id: str
    name: str
    icon: str = "➕"
    description: str = ""
    order: int = 100
    instructions: tuple[str, ...] = ()
    sections: str = ""             # 加在筆記格式最後的段落
    needs_timestamps: bool = False  # 逐字稿要不要帶 [mm:ss]
    output_language: str = ""       # 例如 "English"；空白 = 繁體中文


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    description: str = ""
    profile: str = AUTO
    modifiers: tuple[str, ...] = ()
    focus: str = ""


@dataclass(frozen=True)
class Plan:
    """一次整理要用的方案（已經把 preset 展開）。"""

    profile: str = AUTO
    modifiers: tuple[str, ...] = ()
    focus: str = ""

    def slug(self, resolved_profile: str | None = None) -> str:
        """筆記檔名用：notes.<slug>.md。同一個方案重跑會覆蓋，換方案就是另一個檔案。"""
        parts = [resolved_profile or self.profile, *sorted(self.modifiers)]
        slug = "+".join(parts)
        if self.focus.strip():
            slug += "+focus-" + hashlib.sha1(self.focus.strip().encode("utf-8")).hexdigest()[:6]
        return slug


@dataclass
class Composed:
    system: str
    needs_timestamps: bool
    profile: Profile
    modifiers: list[Modifier] = field(default_factory=list)


def _load_toml(path: Path) -> dict | None:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"[prompts] 略過讀不懂的檔案 {path}: {exc}")
        return None


def _tuple(value) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    return tuple(str(v) for v in (value or ()))


class PromptLibrary:
    def __init__(self, *roots: Path):
        self.profiles: dict[str, Profile] = {}
        self.modifiers: dict[str, Modifier] = {}
        self.presets: dict[str, Preset] = {}
        for root in roots:
            self._load(root)
        if FALLBACK_PROFILE not in self.profiles:
            self.profiles[FALLBACK_PROFILE] = Profile(FALLBACK_PROFILE, "通用", goal="整理影片的重點。")

    def _load(self, root: Path) -> None:
        for path in sorted((root / "profiles").glob("*.toml")):
            if (d := _load_toml(path)) is not None:
                self.profiles[path.stem] = Profile(
                    path.stem, d.get("name", path.stem), d.get("icon", "📝"), d.get("description", ""),
                    int(d.get("order", 100)), d.get("signals", ""), d.get("goal", "").strip(),
                    _tuple(d.get("keep")), _tuple(d.get("drop")), d.get("format", "").strip(),
                )
        for path in sorted((root / "modifiers").glob("*.toml")):
            if (d := _load_toml(path)) is not None:
                self.modifiers[path.stem] = Modifier(
                    path.stem, d.get("name", path.stem), d.get("icon", "➕"), d.get("description", ""),
                    int(d.get("order", 100)), _tuple(d.get("instructions")), d.get("sections", "").strip(),
                    bool(d.get("needs_timestamps", False)), d.get("output_language", ""),
                )
        for path in sorted((root / "presets").glob("*.toml")):
            if (d := _load_toml(path)) is not None:
                self.presets[path.stem] = Preset(
                    path.stem, d.get("name", path.stem), d.get("description", ""),
                    d.get("profile", AUTO), _tuple(d.get("modifiers")), d.get("focus", ""),
                )

    # ---- 查詢 ----
    def sorted_profiles(self) -> list[Profile]:
        return sorted(self.profiles.values(), key=lambda p: (p.order, p.id))

    def sorted_modifiers(self) -> list[Modifier]:
        return sorted(self.modifiers.values(), key=lambda m: (m.order, m.id))

    def plan(self, profile: str = AUTO, modifiers=(), focus: str = "", preset: str = "") -> Plan:
        """CLI / GUI 的選項 → Plan。preset 先展開，再由明確指定的選項覆蓋 / 追加。"""
        mods: list[str] = []
        if preset:
            if preset not in self.presets:
                raise KeyError(f"沒有這個常用組合：{preset}（可用：{', '.join(self.presets) or '無'}）")
            p = self.presets[preset]
            profile = profile if profile and profile != AUTO else p.profile
            mods += list(p.modifiers)
            focus = focus or p.focus
        mods += [m for m in modifiers if m]
        if profile != AUTO and profile not in self.profiles:
            raise KeyError(f"沒有這個整理方式：{profile}（可用：auto, {', '.join(self.profiles)}）")
        unknown = [m for m in mods if m not in self.modifiers]
        if unknown:
            raise KeyError(f"沒有這些加料：{', '.join(unknown)}（可用：{', '.join(self.modifiers)}）")
        return Plan(profile or AUTO, tuple(dict.fromkeys(mods)), focus.strip())

    # ---- 組 prompt ----
    def compose(self, profile_id: str, modifier_ids=(), focus: str = "", short: bool = False) -> Composed:
        profile = self.profiles.get(profile_id) or self.profiles[FALLBACK_PROFILE]
        mods = [self.modifiers[m] for m in modifier_ids if m in self.modifiers]
        language = next((m.output_language for m in mods if m.output_language), "")

        lines = [
            "你是一位專業的影片筆記整理員。你會收到一支影片的資訊（<video_info>）和語音辨識自動產生的逐字稿"
            "（<transcript>），請整理成一份可以直接貼進 Notion 的 Markdown 筆記。",
            "",
            f"## 這支影片的整理方式：{profile.icon} {profile.name}",
            profile.goal,
        ]
        if profile.keep:
            lines += ["", "要保留：", *(f"- {k}" for k in profile.keep)]
        if profile.drop:
            lines += ["", "要略過：", *(f"- {d}" for d in profile.drop)]

        # 骨架用 <format> 包起來：裡面的 ## 是要輸出的段落，跟這份指令自己的 ## 標題分開
        lines += ["", "## 筆記格式",
                  "依照 <format> 裡的骨架撰寫。括號內是寫作說明，不要照抄進筆記；某段沒有內容時依說明省略。",
                  "<format>", profile.format or "（依內容自行安排 ## 段落標題與條列）"]
        for m in mods:
            if m.sections:
                lines += ["", m.sections]
        lines.append("</format>")

        extra = [i for m in mods for i in m.instructions]
        if focus:
            extra.append(
                f"使用者特別想知道：「{focus}」。以這個為主軸整理，相關內容要寫得完整具體；"
                "跟它無關的段落不要展開，只在筆記最後用一行「其他也談到：…」列出主題。"
            )
        if short:
            extra.append("這是一支短影音，筆記要精簡：抓 3 到 5 個重點就好，不需要每個格式段落都寫滿。")
        if extra:
            lines += ["", "## 額外要求", *(f"- {e}" for e in extra)]

        lang_rule = (f"全部用 {language} 撰寫（專有名詞保留原文）。" if language
                     else "用繁體中文與台灣慣用語；專有名詞第一次出現時可附原文，例如「輝達（NVIDIA）」。")
        lines += ["", "## 共通規則", *COMMON_RULES_TEMPLATE.format(language_rule=lang_rule).splitlines()]
        return Composed("\n".join(lines).strip(), any(m.needs_timestamps for m in mods), profile, mods)

    def compose_chunk(self, composed: Composed, focus: str, index: int, total: int) -> str:
        """長影片分段整理時，每一段用的 system prompt。"""
        p = composed.profile
        lines = [
            "你正在協助整理一支很長的影片。逐字稿分成幾段分別處理，這次只處理其中一段（"
            f"第 {index}/{total} 段），之後會把各段筆記合併成完整筆記。",
            "",
            "請把這一段整理成「詳細的條列筆記」：",
            "- 保留這一段所有可能重要的資訊：論點、步驟、數字、例子、人名、結論。寧可多留，合併時會再精簡。",
            "- 依照下面的整理重點判斷什麼重要、什麼可以略過。",
            "- 逐字稿是機器辨識的，請依上下文與影片資訊校正錯字和專有名詞。",
            "- 只輸出條列筆記，不要開場白；逐字稿有 [mm:ss] 時間碼的話，在每個重點後面保留時間碼。",
            "",
            f"## 整理重點：{p.icon} {p.name}",
            p.goal,
        ]
        if p.keep:
            lines += ["要保留：", *(f"- {k}" for k in p.keep)]
        if p.drop:
            lines += ["要略過：", *(f"- {d}" for d in p.drop)]
        if focus:
            lines += ["", f"使用者特別想知道：「{focus}」。跟它有關的內容要完整記下來。"]
        return "\n".join(lines).strip()

    def classifier_system(self) -> str:
        options = "\n".join(
            f"- {p.id}：{p.name} —— {p.description}" + (f"（常見特徵：{p.signals}）" if p.signals else "")
            for p in self.sorted_profiles()
        )
        return (
            "你是影片分類助手。根據影片資訊與逐字稿開頭，從下列整理方式中選出最適合這支影片的一個：\n"
            f"{options}\n\n"
            '只回傳一行 JSON，例如 {"profile": "news", "reason": "一句話理由"}，不要回傳其他文字。'
        )

    def parse_classification(self, text: str) -> tuple[str, str]:
        """解析分類結果；看不懂就用通用方案，不讓整個流程失敗。"""
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                pid = str(data.get("profile", "")).strip()
                if pid in self.profiles:
                    return pid, str(data.get("reason", "")).strip()
            except ValueError:
                pass
        for pid in self.profiles:  # 有些模型只回一個字，例如 news
            if re.search(rf"\b{re.escape(pid)}\b", text):
                return pid, ""
        return FALLBACK_PROFILE, "（分類結果看不懂，改用通用整理）"


COMMON_RULES_TEMPLATE = """\
1. 逐字稿是機器辨識的，常有同音錯字、專有名詞錯誤、斷句錯誤與缺少標點。請參考上下文和影片資訊（標題、說明欄、章節）判斷正確的詞——人名、公司、產品、術語尤其要校正——不要把明顯的錯字照抄進筆記。
2. 只根據影片內容整理：不要加入影片沒提到的資訊、背景知識或你自己的評論。真的不確定的地方寫「（影片中未明確說明）」，不要猜。
3. 數字、日期、價格、百分比、人名要照影片說的精確記下。具體的例子、數據、比較是重點，優先保留。
4. 業配與贊助商、訂閱按讚提醒、開場寒暄、離題閒聊、重複的內容不要寫進筆記（除非上面的整理方式另有要求）。
5. {language_rule}
6. 只輸出筆記本身，不要開場白或結語，也不要用 ``` 把整份筆記包起來。筆記最上面的影片標題與資訊程式會自己加，不要再寫 # 大標題。
7. 只用 Notion 能直接貼上的 Markdown：## / ### 標題、- 清單、1. 編號清單、**粗體**、> 引言、--- 分隔線、表格；不要用 HTML。"""
