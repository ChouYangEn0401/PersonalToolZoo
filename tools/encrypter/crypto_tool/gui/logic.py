"""新介面的「腦」：表單檢查、預設檔名、執行加解密、把結果與錯誤變成人話。

這個模組**不 import tkinter**，所以可以直接用單元測試驗證；gui/app.py 只負責把它接到畫面上。
實際的加解密都交給 sealed/workflow.py（跟命令列同一套）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import texts as T

try:  # 測試時是 crypto_tool.gui.logic；實際執行時 crypto_tool/ 在 sys.path 上，是 gui.logic
    from ..sealed import settings, workflow
    from ..sealed.errors import SealError
    from ..sealed.keys import MIN_PASSPHRASE_CHARS, key_id, load_key_file
except ImportError:
    from sealed import settings, workflow
    from sealed.errors import SealError
    from sealed.keys import MIN_PASSPHRASE_CHARS, key_id, load_key_file

agefmt = workflow.agefmt
pgpmode = workflow.pgpmode

ENCRYPT, DECRYPT = "encrypt", "decrypt"
MODE_AGE, MODE_PGP = workflow.MODE_AGE, workflow.MODE_PGP


@dataclass
class JobForm:
    """畫面上一次加密或解密要用到的所有欄位。"""

    action: str = ENCRYPT
    inputs: list = field(default_factory=list)     # 加密可以好幾個；解密只用第一個
    output_path: str = ""
    mode: str = MODE_AGE                            # 加密用
    use_passphrase: bool = False
    passphrase: str = field(default="", repr=False)
    passphrase_confirm: str = field(default="", repr=False)
    use_keys: bool = True
    recipients: list = field(default_factory=list)  # 加密：age1… 字串或公鑰檔路徑
    with_master: bool = False
    key_files: list = field(default_factory=list)   # 解密：身分檔／OpenPGP 私鑰／舊 ISD2 金鑰檔
    key_passphrase: str = field(default="", repr=False)
    all_layers: bool = False
    armor: bool = False
    overwrite: bool = False
    keep_tar: bool = False

    @property
    def input_path(self) -> str:
        return self.inputs[0] if self.inputs else ""


@dataclass
class Message:
    """要顯示在結果區的一則訊息。kind 決定顏色：success／danger／warning／info。"""

    kind: str
    title: str
    lines: list[str]
    code: str = ""


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def dropped(paths) -> list[str]:
    """拖進來的清單 -> 去掉空白與重複的路徑。"""
    out: list[str] = []
    for p in paths:
        text = str(p).strip()
        if text and text not in out:
            out.append(text)
    return out


def first_dropped(paths) -> tuple[str, int]:
    """拖進來的清單 -> (第一個路徑, 被忽略的其他項目數)。解密一次只處理一個。"""
    items = dropped(paths)
    if not items:
        return "", 0
    return items[0], len(items) - 1


def describe_inputs(paths) -> str:
    """選了要加密的東西之後，顯示在路徑下面的一行說明。"""
    paths = [p for p in paths if p]
    if not paths:
        return T.NOTHING_CHOSEN
    if any(not os.path.exists(p) for p in paths):
        return T.PROBLEM_INPUT_GONE
    if len(paths) > 1:
        return T.MANY_INPUTS.format(n=len(paths))
    p = Path(paths[0])
    if p.is_dir():
        return T.KIND_FOLDER
    return f"{T.KIND_FILE}・{human_size(p.stat().st_size)}"


def describe_input(path: str) -> str:
    return describe_inputs([path])


def gpg_available() -> bool:
    try:
        pgpmode.find_gpg()
        return True
    except SealError:
        return False


def default_key_files() -> list[str]:
    """.env 設定的預設解密鑰匙檔（只列存在的）。"""
    try:
        age, pgp = workflow.default_keyring_paths()
    except SealError:
        return []
    return [str(p) for p in age + pgp]


AGE_LIST_SEP, PGP_LIST_SEP = ", ", "; "


def masters_for(mode: str) -> list[str]:
    """設定好的萬用鎖（可以好幾把）；沒設定或設定有誤時空清單。"""
    try:
        if mode == MODE_AGE:
            return settings.master_recipients()
        return [str(p) for p in settings.master_pgp_keys()]
    except SealError:
        return []


def master_for(mode: str) -> str | None:
    """設定好的萬用鎖，寫成一個可以放進輸入欄的字串（多把用分隔符號連起來）；沒設定時 None。"""
    values = masters_for(mode)
    if not values:
        return None
    return (AGE_LIST_SEP if mode == MODE_AGE else PGP_LIST_SEP).join(values)


def master_summary(mode: str) -> str | None:
    """加密分頁上那一小行：一把就顯示（縮短的）公鑰／路徑，好幾把就顯示「N 把」。"""
    values = masters_for(mode)
    if not values:
        return None
    first = values[0] if len(values[0]) <= 24 else values[0][:12] + "…" + values[0][-6:]
    return first if len(values) == 1 else T.MASTER_MANY.format(n=len(values), first=first)


def split_master_input(mode: str, text: str) -> list[str]:
    """金鑰分頁輸入欄 -> 一把一把的萬用鎖（簡單模式：逗號／分號／空白／換行；PGP：分號／換行）。"""
    pattern = r"[\s,;，；]+" if mode == MODE_AGE else r"[;；\r\n]+"
    out: list[str] = []
    for part in re.split(pattern, text or ""):
        part = part.strip().strip('"').strip("'")
        if part and part not in out:
            out.append(part)
    return out


def _lock_text(lock: dict) -> str:
    fmt = lock.get("format")
    if fmt == workflow.FMT_AGE:
        types = lock.get("recipient_types") or {}
        if "scrypt" in types:
            return T.LOCK_PASSPHRASE
        return T.LOCK_KEYS.format(n=sum(types.values()))
    if fmt == workflow.FMT_PGP:
        if lock.get("details_unavailable"):
            return T.LOCK_UNKNOWN
        parts = []
        ids = [i for i in lock.get("recipient_key_ids", []) if i]
        if ids:
            parts.append(T.LOCK_PGP_IDS.format(ids="、".join(ids)))
        if lock.get("passphrase"):
            parts.append(T.LOCK_PGP_ALSO_PASS)
        return "・".join(parts) or T.LOCK_UNKNOWN
    return T.FORMAT_LABELS.get(fmt, str(fmt))


def inspect_sealed(path: str) -> tuple[str, dict | None, Message | None]:
    """看一個要解密的檔案。回傳 (說明文字, 資訊或 None, 錯誤訊息或 None)。不需要鑰匙。"""
    try:
        fmt = workflow.detect_format(path)
        if fmt is None:
            raise workflow._unknown_error()
        size = human_size(os.path.getsize(path))
        if fmt == workflow.FMT_LEGACY:
            return T.SEALED_LEGACY, {"format": fmt}, None
        if fmt == workflow.FMT_ISD2:
            info = workflow.inspect(path)
            return T.SEALED_ISD2.format(key=T.SEALED_KEY.get(info["kdf"], ""), size=size), info, None
        if fmt == workflow.FMT_PGP and workflow.pgp_kind(path) != "message":
            raise SealError("unsupported_format", "這是 OpenPGP 金鑰或簽章檔，不是加密檔。",
                            action="選要解密的 .gpg／.asc 加密檔。")
        lock = workflow.describe_lock(path, fmt)
        template = T.SEALED_AGE if fmt == workflow.FMT_AGE else T.SEALED_PGP
        return template.format(who=_lock_text(lock), size=size), lock, None
    except SealError as err:
        if err.code == "input_missing":  # 路徑還在打字、或檔案被移走：只在說明列提醒
            return T.PROBLEM_INPUT_GONE, None, None
        return "", None, error_message(err)


def suggest_output(action: str, inputs, keep_tar: bool = False, *, mode: str = MODE_AGE,
                   armor: bool = False) -> str:
    """選好輸入之後自動填的輸出位置；猜不出來就留空讓使用者自己選。"""
    if isinstance(inputs, str):
        inputs = [inputs] if inputs else []
    inputs = [p for p in inputs if p]
    if not inputs:
        return ""
    if action == ENCRYPT:
        if len(inputs) > 1:
            first = Path(inputs[0])
            name = "bundle.tar" + (".age" if mode == MODE_AGE else (".asc" if armor else ".gpg"))
            return str(first.with_name(name))
        src = Path(inputs[0])
        name = src.name + (".tar" if src.is_dir() else "")
        suffix = ".age" if mode == MODE_AGE else (".asc" if armor else ".gpg")
        return str(src.with_name(name + suffix))
    out = workflow.default_decrypt_output(inputs[0])
    if out is None:
        return ""
    if not keep_tar and out.name.lower().endswith(".tar") and len(out.name) > 4:
        out = out.with_name(out.name[:-4])
    return str(out)


def passphrase_strength(text: str) -> tuple[int, str]:
    """很粗的提示（0 空白、1 太短、2 還可以、3 不錯），只看長度與種類，不擋使用者。"""
    if not text:
        return 0, T.STRENGTH_LABELS[0]
    kinds = sum(bool(k) for k in (
        any(c.islower() for c in text), any(c.isupper() for c in text),
        any(c.isdigit() for c in text),
        any(not c.isalnum() for c in text),
    ))
    if len(text) < MIN_PASSPHRASE_CHARS:
        level = 1
    elif len(text) >= 20 or (len(text) >= 16 and kinds >= 3):
        level = 3
    else:
        level = 2
    return level, T.STRENGTH_LABELS[level]


_SPLIT = re.compile(r"[\s,;，；]+")


def split_recipients(text: str) -> list[str]:
    """使用者貼上的一串公鑰（空白、逗號分隔）-> 清單。不在這裡檢查格式。"""
    return [part for part in _SPLIT.split(text.strip()) if part]


def validate(form: JobForm, *, gpg: bool | None = None) -> list[str]:
    """按下按鈕前先檢查；回傳要告訴使用者的問題清單（空的表示可以開始）。"""
    problems: list[str] = []
    if not form.inputs:
        problems.append(T.PROBLEM_NO_INPUT[form.action])
    elif any(not os.path.exists(p) for p in form.inputs):
        problems.append(T.PROBLEM_INPUT_GONE)
    if form.action == ENCRYPT:
        if form.mode == MODE_PGP and gpg is False:
            problems.append(T.PROBLEM_PGP_UNAVAILABLE)
        keys = form.use_keys and (form.recipients or form.with_master)
        if form.use_passphrase:
            if not form.passphrase:
                problems.append(T.PROBLEM_NO_PASSPHRASE)
            elif form.passphrase != form.passphrase_confirm:
                problems.append(T.PROBLEM_MISMATCH)
        if not form.use_passphrase and not keys:
            problems.append(T.PROBLEM_NO_LOCK)
        if form.mode == MODE_AGE and form.use_passphrase and keys:
            problems.append(T.PROBLEM_AGE_MIX)
    elif not form.key_files and not form.passphrase:
        problems.append(T.PROBLEM_NO_DECRYPT_KEY)
    if not form.output_path.strip():
        problems.append(T.PROBLEM_NO_OUTPUT)
    return problems


def _split_recipient_items(form: JobForm) -> tuple[list[str], list[str], list[str]]:
    """畫面上的收件人清單 -> (age1 字串, age 公鑰清單檔／身分檔, OpenPGP 公鑰檔)。"""
    strings, age_files, pgp_files = [], [], []
    for item in form.recipients if form.use_keys else []:
        item = str(item).strip()
        if not item:
            continue
        if item.lower().startswith("age1"):
            strings.append(item)
        elif form.mode == MODE_PGP:
            pgp_files.append(item)
        else:
            age_files.append(item)
    return strings, age_files, pgp_files


def run_job(form: JobForm, progress=None) -> dict:
    """真的去加密或解密。失敗一律丟 SealError。在背景執行緒呼叫。"""
    if form.action == ENCRYPT:
        strings, age_files, pgp_files = _split_recipient_items(form)
        recips = workflow.resolve_recipients(
            form.mode, recipients=strings, recipient_files=age_files, pgp_recipient_files=pgp_files,
            with_master=form.use_keys and form.with_master, use_passphrase=form.use_passphrase)
        return workflow.encrypt(form.inputs, form.output_path, recipients=recips,
                                passphrase=form.passphrase if form.use_passphrase else None,
                                armor=form.armor, force=form.overwrite, progress=progress)
    ring = build_keyring(form)
    if form.all_layers:
        return workflow.decrypt_all_layers(form.input_path, form.output_path, ring,
                                           force=form.overwrite, progress=progress)
    return workflow.decrypt(form.input_path, form.output_path, ring, force=form.overwrite,
                            keep_tar=form.keep_tar, progress=progress)


def build_keyring(form: JobForm) -> workflow.Keyring:
    """解密用的鑰匙：身分檔、OpenPGP 私鑰、舊 ISD2 金鑰檔（看要解的檔案是哪一種）、密語。"""
    ring = workflow.Keyring(passphrase=form.passphrase or None,
                            pgp_key_passphrase=form.key_passphrase or None)
    files = [Path(f) for f in form.key_files if str(f).strip()]
    fmt = None
    try:
        fmt = workflow.detect_format(form.input_path) if form.input_path else None
    except SealError:
        pass
    if fmt == workflow.FMT_ISD2:   # 舊的預覽格式：用清單裡第一個「不是 age 身分檔、不是 OpenPGP 金鑰」的檔
        for f in files:
            try:
                if workflow.classify_key_file(f) != "age" or b"AGE-SECRET-KEY-" in f.read_bytes()[:1 << 16].upper():
                    continue
                if agefmt.is_encrypted_identity_file(f.read_bytes()[:2048]):
                    continue
            except OSError:
                continue
            ring.isd2_material = load_key_file(f)
            break
        return ring

    def ask(_path):
        if not form.key_passphrase:
            raise SealError("key_missing", "這個鑰匙檔有密語保護，需要密語才能讀取。",
                            action="在「鑰匙檔的密語」輸入保護它的密語。")
        return form.key_passphrase

    ring.age_identities, ring.pgp_secret_keys = workflow.load_identities(files, ask)
    return ring


def run_job_safely(form: JobForm, progress=None) -> Message:
    """run_job 的包裝：不管發生什麼都回傳一則可以直接顯示的訊息。"""
    try:
        return success_message(run_job(form, progress))
    except SealError as err:
        return error_message(err)
    except Exception as exc:  # 不把例外文字丟到畫面上
        return error_message(SealError("internal_bug", "程式發生沒預期到的錯誤。",
                                       action="把這個畫面截圖回報給維護者。",
                                       detail=type(exc).__name__))


def progress_view(done: int, total: int) -> tuple[int, str]:
    """進度 -> (0–100 的百分比, 進度列旁邊的字)。"""
    if total <= 0:
        return 0, ""
    percent = max(0, min(100, int(done * 100 / total)))
    return percent, f"{percent}%（{human_size(done)}／{human_size(total)}）"


def _who(summary: dict) -> str:
    parts = []
    if summary.get("keys"):
        parts.append(T.WHO_KEYS.format(n=summary["keys"]))
    if summary.get("passphrase"):
        parts.append(T.WHO_PASSPHRASE)
    return "、".join(parts) + (T.WHO_MASTER if summary.get("master") else "")


def success_message(result: dict) -> Message:
    action = result["action"]
    lines = [T.SUCCESS_SAVED.format(path=result["output"])]
    if result.get("format") in T.FORMAT_LABELS:
        lines.append(T.SUCCESS_FORMAT.format(label=T.FORMAT_LABELS[result["format"]]))
    if action == ENCRYPT:
        lines.append(T.SUCCESS_WHO.format(who=_who(result["recipients"])))
    if "files" in result:
        lines.append(T.SUCCESS_FILES.format(n=result["files"]))
    if result.get("skipped_links"):
        lines.append(T.SUCCESS_SKIPPED.format(n=result["skipped_links"]))
    if "passphrase_short" in result.get("warnings", []):
        lines.append(T.SUCCESS_SHORT)
    if action == ENCRYPT:
        lines += [T.SUCCESS_ORIGINAL_KEPT, T.SUCCESS_BACKUP]
        return Message("success", T.SUCCESS_TITLE[action], lines)
    if result.get("used_master"):
        lines.append(T.SUCCESS_USED_MASTER)
    if result.get("deprecated"):
        lines.append(T.SUCCESS_DEPRECATED)
    if not result.get("all_layers"):
        return Message("success", T.SUCCESS_TITLE[action], lines)
    for stop in result["stopped"]:
        if stop["reason"] == "needs_other_key":
            lines.append(T.LAYERS_STOP.format(depth=stop["depth"], path=stop["path"],
                                              lock=_lock_text(stop["lock"])))
        elif stop["reason"] == "depth_limit":
            lines.append(T.LAYERS_DEPTH.format(depth=stop["depth"], path=stop["path"]))
        else:
            lines.append(T.LAYERS_STOP_OTHER.format(depth=stop["depth"], path=stop["path"],
                                                    reason=stop.get("message", "")))
    if result["complete"]:
        lines.append(T.LAYERS_DONE.format(n=len(result["layers"])))
        return Message("success", T.SUCCESS_TITLE[action], lines)
    return Message("warning", T.LAYERS_STOPPED_TITLE, lines)


def error_message(err: SealError) -> Message:
    lines = [err.reason]
    if err.action:
        lines.append(err.action)
    if err.code not in ("legacy_format", "output_exists"):
        lines.append(T.ERROR_NOTHING_WRITTEN)
    if err.code == "internal_bug" and err.detail:
        lines.append(f"（{err.detail}）")
    kind = "warning" if err.code in ("output_exists", "legacy_format", "bad_input") else "danger"
    return Message(kind, T.ERROR_TITLES.get(err.code, T.ERROR_TITLES["internal_bug"]), lines,
                   code=err.code)


def _guard(func):
    """金鑰分頁的動作：一律回傳 Message，不讓例外跑到畫面上。"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SealError as err:
            return error_message(err)
        except Exception as exc:  # noqa: BLE001
            return error_message(SealError("internal_bug", "程式發生沒預期到的錯誤。",
                                           action="把這個畫面截圖回報給維護者。",
                                           detail=type(exc).__name__))
    return wrapper


@_guard
def create_age_identity(path: str, passphrase: str = "", confirm: str = "",
                        set_default: bool = False) -> Message:
    """「金鑰」分頁：產生 age 身分檔。永遠不覆蓋既有檔案。在背景執行緒呼叫（密語保護要算 scrypt）。"""
    if not path.strip():
        return Message("warning", T.PROBLEMS_TITLE, [T.PROBLEM_NO_OUTPUT])
    if passphrase != confirm:
        return Message("warning", T.PROBLEMS_TITLE, [T.PROBLEM_MISMATCH])
    info = workflow.keygen_age(path.strip(), passphrase=passphrase or None)
    lines = [T.KEYS_PUBLIC.format(key=info["public_key"]),
             T.KEYS_PROTECTED if info["protected"] else T.KEYS_NOT_PROTECTED]
    if set_default:
        saved = settings.set_value(settings.IDENTITY_FILE, str(Path(info["path"]).resolve()))
        lines.append(T.KEYS_MASTER_SAVED.format(path=saved))
    lines.append(T.KEYS_BACKUP_WARNING)
    return Message("success", T.KEYS_AGE_CREATED.format(path=info["path"]), lines)


@_guard
def create_pgp_keypair(prefix: str, name: str, passphrase: str = "", confirm: str = "") -> Message:
    """「金鑰」分頁：產生 OpenPGP 金鑰對（呼叫 gpg，要幾秒鐘；在背景執行緒呼叫）。"""
    if not prefix.strip():
        return Message("warning", T.PROBLEMS_TITLE, [T.PROBLEM_NO_OUTPUT])
    if passphrase != confirm:
        return Message("warning", T.PROBLEMS_TITLE, [T.PROBLEM_MISMATCH])
    info = workflow.keygen_pgp(prefix.strip(), name=name.strip() or "Encrypter key",
                               passphrase=passphrase or None)
    lines = [T.KEYS_PGP_FINGERPRINT.format(fpr=info["fingerprint"]),
             T.KEYS_PROTECTED if info["protected"] else T.KEYS_NOT_PROTECTED, T.KEYS_BACKUP_WARNING]
    return Message("success", T.KEYS_PGP_CREATED.format(public=info["public_key"], secret=info["secret_key"]),
                   lines)


def public_key_from_identity(path: str, passphrase: str = "") -> str:
    """從身分檔讀出公鑰（設定萬用鎖用）。只回傳公鑰。失敗丟 SealError。"""
    ids = agefmt.load_identity_file(path, (lambda: passphrase) if passphrase else None)
    return ids[0].public_key


@_guard
def save_master(age_value: str, pgp_path: str) -> Message:
    """「金鑰」分頁：把萬用鎖公鑰（與 PGP 萬用鎖公鑰檔路徑）寫進 .env。空白＝清除。

    兩欄都可以放好幾把：簡單模式用逗號分開，PGP 模式的檔案路徑用分號分開。一把不對就整個不寫。
    """
    ages = split_master_input(MODE_AGE, age_value)
    for value in ages:
        agefmt.parse_recipient(value)            # 格式不對就在寫入前擋下
    pgps = split_master_input(MODE_PGP, pgp_path)
    for path in pgps:
        if workflow.classify_key_file(path) != "pgp-public":
            raise SealError("bad_key_format", "PGP 萬用鎖要選 OpenPGP「公鑰」檔（.public.asc）。")
    saved = settings.set_value(settings.MASTER_RECIPIENT, AGE_LIST_SEP.join(ages))
    settings.set_value(settings.MASTER_PGP_KEY, PGP_LIST_SEP.join(pgps))
    if not ages and not pgps:
        return Message("info", T.KEYS_MASTER_TITLE, [T.KEYS_MASTER_CLEARED])
    return Message("success", T.KEYS_MASTER_TITLE,
                   [T.KEYS_MASTER_COUNT.format(age=len(ages), pgp=len(pgps)),
                    T.KEYS_MASTER_SAVED.format(path=saved)])


def add_master_value(current: str, new_value: str, mode: str = MODE_AGE) -> str:
    """「從身分檔讀…」「選檔案…」：把新的一把接在已經填的後面（不是取代），重複的不再加。"""
    values = split_master_input(mode, current)
    if new_value and new_value not in values:
        values.append(new_value)
    return (AGE_LIST_SEP if mode == MODE_AGE else PGP_LIST_SEP).join(values)


@_guard
def check_key_file(path: str) -> Message:
    """「金鑰」分頁的檢查按鈕：說是哪一種、能做什麼；只顯示公鑰，不顯示私鑰。"""
    if not path.strip():
        return Message("warning", T.ERROR_TITLES["key_missing"], [T.PROBLEM_NO_DECRYPT_KEY])
    p = Path(path.strip())
    kind = workflow.classify_key_file(p)
    if kind == "pgp-secret":
        return Message("success", T.KEYS_CHECK_TITLE, [T.KEYS_CHECK_PGP_SECRET])
    if kind == "pgp-public":
        return Message("success", T.KEYS_CHECK_TITLE, [T.KEYS_CHECK_PGP_PUBLIC])
    data = p.read_bytes()[: 1 << 20]
    if agefmt.is_encrypted_identity_file(data):
        return Message("success", T.KEYS_CHECK_TITLE, [T.KEYS_CHECK_AGE_LOCKED])
    if b"AGE-SECRET-KEY-" in data.upper():
        ids = agefmt.parse_identity_file(data)
        return Message("success", T.KEYS_CHECK_TITLE,
                       [T.KEYS_CHECK_AGE.format(n=len(ids), keys="、".join(i.public_key for i in ids))])
    try:
        recips = agefmt.parse_recipients(data.decode("utf-8-sig"))
        return Message("info", T.KEYS_CHECK_TITLE,
                       [T.KEYS_CHECK_RECIPIENTS.format(keys="、".join(str(r) for r in recips))])
    except (SealError, UnicodeDecodeError):
        pass
    try:
        material = load_key_file(p)
    except SealError:
        return Message("warning", T.KEYS_CHECK_TITLE, [T.KEYS_CHECK_UNKNOWN])
    if material.raw is not None:
        return Message("info", T.KEYS_CHECK_TITLE, [T.KEYS_CHECK_ISD2.format(key_id=key_id(material.raw))])
    return Message("warning", T.KEYS_CHECK_TITLE, [T.KEYS_CHECK_UNKNOWN])
