"""改名引擎：規則、掃描資料夾、預覽、兩段式套用、復原、規則組存檔。畫面在 main.py。

規則（正規表達式）：
- 一次可以有很多條，由上往下依序套用；每條可以單獨停用、單獨設定不分大小寫。
- 「取代成」可以用 \\1、\\g<名稱>，也接受 $1、${名稱}（$$ 代表 $ 本身）。
- 預設只改主檔名、保留副檔名，避免把 .mp4 改壞；也可以選「連副檔名一起」。

套用分兩段：先把這一批全部改成暫時名稱，再改成目標名稱。所以 A↔B 互換、或 1→2、2→3
這種一串改名，都不會撞到還沒改的檔案；任何一步失敗就把這一批全部還原。
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

MODE_REGEX = "regex"
MODE_NAME_HASH = "name_hash"
MODE_CONTENT_HASH = "content_hash"

SCOPE_STEM = "stem"     # 只改主檔名，保留副檔名
SCOPE_FULL = "full"     # 整個檔名（含副檔名）

STATUS_SAME = "不變"
STATUS_NO_MATCH = "沒有符合的規則"

ILLEGAL_CHARS = set('<>:"/\\|?*') | {chr(i) for i in range(32)}
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
SKIP_FILES = {"desktop.ini", "thumbs.db"}   # Windows 的系統檔，掃資料夾時略過


# ---------------------------------------------------------------- 規則
@dataclass
class Rule:
    find: str = ""
    replace: str = ""
    ignore_case: bool = False
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        return cls(**{k: data[k] for k in ("find", "replace", "ignore_case", "enabled") if k in data})


class RuleError(ValueError):
    def __init__(self, index: int, message: str):
        super().__init__(f"第 {index + 1} 條規則寫錯：{message}")
        self.index = index


@dataclass
class CompiledRule:
    rule: Rule
    regex: re.Pattern
    replacement: str


_DOLLAR = re.compile(r"\$\$|\$\{(\w+)\}|\$(\d+)")


def to_python_replacement(text: str) -> str:
    """把 $1、${名稱} 轉成 Python 的 \\g<1>、\\g<名稱>；$$ 變成 $。原本的 \\1 寫法不動。"""
    def repl(m: re.Match) -> str:
        if m.group(0) == "$$":
            return "$"
        return f"\\g<{m.group(1) or m.group(2)}>"
    return _DOLLAR.sub(repl, text)


def compile_rules(rules: list[Rule]) -> list[CompiledRule]:
    """編譯啟用中的規則；寫錯的那一條丟 RuleError（含第幾條）。"""
    compiled: list[CompiledRule] = []
    for index, rule in enumerate(rules):
        if not rule.enabled or not rule.find:
            continue
        try:
            regex = re.compile(rule.find, re.IGNORECASE if rule.ignore_case else 0)
            replacement = to_python_replacement(rule.replace)
            regex.sub(replacement, "")   # 取代成裡引用不存在的群組（例如 \3）會在這裡就報錯
        except (re.error, IndexError) as exc:
            raise RuleError(index, str(exc)) from exc
        compiled.append(CompiledRule(rule, regex, replacement))
    return compiled


def apply_rules(name: str, compiled: list[CompiledRule], scope: str = SCOPE_STEM) -> tuple[str, int]:
    """回傳 (新檔名, 總共取代了幾處)。"""
    if scope == SCOPE_STEM:
        stem, ext = os.path.splitext(name)
    else:
        stem, ext = name, ""
    hits = 0
    for c in compiled:
        stem, n = c.regex.subn(c.replacement, stem)
        hits += n
    return stem + ext, hits


# ---------------------------------------------------------------- 掃描資料夾
def parse_filter(text: str) -> list[str]:
    """「*.mp4;*.mkv」→ ["*.mp4", "*.mkv"]（分號或逗號隔開，不分大小寫）。"""
    return [p.strip().lower() for p in re.split(r"[;,]", text) if p.strip()]


def scan_folder(folder: str | Path, recursive: bool = True, name_filter: str = "") -> list[str]:
    """列出資料夾裡的檔案（略過 . 開頭的資料夾，例如 .git，以及 desktop.ini 這類系統檔）。"""
    patterns = parse_filter(name_filter)
    found: list[str] = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")) if recursive else []
        for name in sorted(files):
            low = name.lower()
            if low in SKIP_FILES:
                continue
            if patterns and not any(fnmatch.fnmatch(low, p) for p in patterns):
                continue
            found.append(os.path.join(root, name))
    return found


# ---------------------------------------------------------------- 預覽
@dataclass
class PlanRow:
    path: str
    new_name: str
    status: str = ""      # 空字串 = 會改名；其他是不改的原因
    hits: int = 0

    @property
    def ok(self) -> bool:
        return self.status == ""


def content_hash(path: str, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def name_problem(new_name: str) -> str:
    """新檔名在 Windows 上能不能用；可以就回傳空字串。"""
    if not new_name or new_name in (".", ".."):
        return "新檔名是空的"
    if any(c in ILLEGAL_CHARS for c in new_name):
        return '新檔名有不能用的字元（\\ / : * ? " < > |）'
    if new_name.endswith((" ", ".")):
        return "新檔名不能以空白或句點結尾"
    if new_name.split(".")[0].strip().upper() in RESERVED_NAMES:
        return f"「{new_name.split('.')[0]}」是 Windows 保留的名稱"
    if len(new_name) > 255:
        return "新檔名太長（超過 255 個字元）"
    return ""


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def plan(paths: list[str], mode: str = MODE_REGEX, rules: list[Rule] | None = None,
         scope: str = SCOPE_STEM) -> list[PlanRow]:
    """算出每個檔案的新檔名與能不能改。不會動到任何檔案。"""
    compiled: list[CompiledRule] = []
    if mode == MODE_REGEX:
        try:
            compiled = compile_rules(rules or [])
        except RuleError as exc:
            return [PlanRow(p, os.path.basename(p), str(exc)) for p in paths]
    rows: list[PlanRow] = []
    for path in paths:
        name = os.path.basename(path)
        stem, ext = os.path.splitext(name)
        try:
            if mode == MODE_REGEX:
                if not compiled:
                    rows.append(PlanRow(path, name, "還沒有規則"))
                    continue
                new, hits = apply_rules(name, compiled, scope)
                if hits == 0:
                    rows.append(PlanRow(path, name, STATUS_NO_MATCH))
                    continue
            elif mode == MODE_NAME_HASH:
                new, hits = hashlib.sha256(name.encode("utf-8")).hexdigest() + ext, 1
            else:
                new, hits = content_hash(path) + ext, 1
        except OSError as exc:
            rows.append(PlanRow(path, name, f"讀不到檔案：{exc}"))
            continue
        rows.append(PlanRow(path, new, "", hits))
    return _check_conflicts(rows)


def _check_conflicts(rows: list[PlanRow]) -> list[PlanRow]:
    """檔名不合法、不變、同一批重複、跟不會移走的既有檔案撞名。重複檢查到穩定為止：
    某個檔案因為衝突不改了，原本要改成「它的名字」的其他檔案也得跟著擋下。"""
    for row in rows:
        if row.ok:
            row.status = name_problem(row.new_name) or (STATUS_SAME if row.new_name == os.path.basename(row.path) else "")
    while True:
        moving = {_key(r.path) for r in rows if r.ok}
        seen: dict[str, str] = {}
        changed = False
        for row in rows:
            if not row.ok:
                continue
            target = _key(os.path.join(os.path.dirname(row.path), row.new_name))
            problem = ""
            if target in seen:
                problem = f"跟「{os.path.basename(seen[target])}」的新檔名重複"
            elif target != _key(row.path) and os.path.exists(target) and target not in moving:
                problem = "目標檔名已經有別的檔案"
            if problem:
                row.status = problem
                changed = True
            else:
                seen[target] = row.path
        if not changed:
            return rows


# ---------------------------------------------------------------- 套用與復原
class RenameError(OSError):
    pass


def move_all(pairs: list[tuple[str, str]]) -> None:
    """兩段式改名：[(原路徑, 新路徑)]。全部成功才算數；中途失敗就全部還原並丟 RenameError。"""
    staged: list[tuple[str, str, str]] = []    # (原路徑, 暫時路徑, 新路徑)
    finished: list[tuple[str, str, str]] = []
    try:
        for src, dst in pairs:
            temp = os.path.join(os.path.dirname(src), f".renaming-{uuid.uuid4().hex[:12]}.tmp")
            os.rename(src, temp)
            staged.append((src, temp, dst))
        for item in staged:
            os.rename(item[1], item[2])
            finished.append(item)
    except OSError as exc:
        problems = []
        for src, temp, dst in reversed(finished):     # 先把已經到位的改回暫時名稱
            try:
                os.rename(dst, temp)
            except OSError as undo_exc:
                problems.append(f"{dst}：{undo_exc}")
        for src, temp, dst in reversed(staged):       # 再全部改回原名
            try:
                os.rename(temp, src)
            except OSError as undo_exc:
                problems.append(f"{temp}：{undo_exc}")
        detail = f"（還原時也有問題：{'；'.join(problems)}）" if problems else "，已全部改回原名"
        raise RenameError(f"改名失敗：{exc}{detail}") from exc


def apply(rows: list[PlanRow]) -> list[tuple[str, str]]:
    """套用預覽裡可以改的那些，回傳 [(原路徑, 新路徑)]（給復原用）。"""
    pairs = [(r.path, os.path.join(os.path.dirname(r.path), r.new_name)) for r in rows if r.ok]
    move_all(pairs)
    return pairs


def undo(pairs: list[tuple[str, str]]) -> None:
    """把 apply() 回傳的那一批改回去。檔案不在了（被移走、被刪）就整批不動並丟 RenameError。"""
    missing = [new for _, new in pairs if not os.path.exists(new)]
    if missing:
        raise RenameError("下列檔案已經不在原處，無法復原：\n" + "\n".join(missing[:10]))
    move_all([(new, old) for old, new in pairs])


# ---------------------------------------------------------------- 存檔（規則組、上一批改名）
def load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rules_to_data(rules: list[Rule]) -> list[dict]:
    return [asdict(r) for r in rules]


def rules_from_data(data) -> list[Rule]:
    return [Rule.from_dict(d) for d in data if isinstance(d, dict)] if isinstance(data, list) else []
