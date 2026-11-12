"""0.4.0 的整合層：命令列與視窗都只呼叫這裡。

兩種模式，都是公開標準格式：

* 簡單模式（預設）＝ **age v1**（``agefmt``，自寫實作、通過 C2SP 官方測試向量）。
* PGP 模式 ＝ **OpenPGP**（``pgpmode``，呼叫系統上的 gpg）。

另外：

* 解密自動辨識 age／文字封裝的 age／OpenPGP／**ISD2 預覽格式（已停用，只能解密）**／舊 ``.isd``。
* 一個以上的輸入或資料夾先打成 tar（``packing``）；解出來是 tar 時還原成資料夾。
* 萬用鎖＝多收件人：同一份密文，每把鎖只多包一次很小的檔案金鑰。
* ``decrypt_all_layers``：剝洋蔥，解開後裡面還是加密檔（或資料夾最上層有加密檔）就用同一組鑰匙繼續解，
  解不開就停在那一層並回報看得到的資訊。
* ``rewrap``（換鎖，內容位元組不變）與 ``rekey``（換檔案金鑰、整份重新加密）。

這裡回傳的 dict 只含公開資訊（路徑、種類、數量、公鑰），不含金鑰、密語或明文。
"""

from __future__ import annotations

import os
import platform
import secrets
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from . import packing, settings
from .container import MAGIC as ISD2_MAGIC
from .container import KeyMaterial
from .errors import SealError
from .keys import MIN_PASSPHRASE_CHARS, passphrase_material
from .ops import decrypt_path as _isd2_decrypt_path
from .ops import info_path as _isd2_info_path

try:  # 測試時是 crypto_tool.sealed；視窗程式與 python <crypto_tool 資料夾> 時是頂層的 sealed
    from .. import agefmt, pgpmode
    from ..agefmt._fileio import atomic_write as _atomic_write
except ImportError:  # pragma: no cover - 依執行方式而定
    import agefmt  # type: ignore[no-redef]
    import pgpmode  # type: ignore[no-redef]
    from agefmt._fileio import atomic_write as _atomic_write  # type: ignore[no-redef]

MODE_AGE, MODE_PGP = "age", "pgp"
MODES = (MODE_AGE, MODE_PGP)
FMT_AGE, FMT_PGP, FMT_ISD2, FMT_LEGACY = "age", "openpgp", "isd2-preview", "isd-legacy"
ENCRYPTED_FORMATS = (FMT_AGE, FMT_PGP, FMT_ISD2)
FORMAT_LABELS = {
    FMT_AGE: "age（簡單模式）", FMT_PGP: "OpenPGP（PGP 模式）",
    FMT_ISD2: "ISD2 預覽格式（已停用）", FMT_LEGACY: "舊版 .isd",
}
KNOWN_SUFFIXES = (".age", ".gpg", ".pgp", ".asc", ".isd2")

MAX_LAYERS = 16       # --all-layers 最多剝幾層
MAX_LAYER_ITEMS = 256  # --all-layers 最多試解幾個內層檔案（避免一個資料夾塞滿加密檔拖垮電腦）

# age 密語（scrypt）的強度。測試會調低以免每次都花 1 秒與 256 MB 記憶體。
AGE_SCRYPT_WORK_FACTOR = agefmt.DEFAULT_SCRYPT_WORK_FACTOR
DEFAULT_IDENTITY_NAME = ".decryption_code.env"
DEFAULT_PGP_PREFIX = "encrypter-pgp"
_HEAD = 4096


# ── 辨識格式 ────────────────────────────────────────────────────────────

def _read_head(path: Path) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read(_HEAD)
    except OSError as exc:
        raise SealError("io_error", "讀不到檔案。", detail=type(exc).__name__) from None


def detect_bytes(head: bytes) -> str | None:
    if head[:4] == ISD2_MAGIC:
        return FMT_ISD2
    if agefmt.is_age(head):
        return FMT_AGE
    if pgpmode.is_pgp(head):
        return FMT_PGP
    if head.lstrip()[:8] == b"CONTENT=":
        return FMT_LEGACY
    return None


def detect_format(path) -> str | None:
    """看檔頭判斷格式：age／openpgp／isd2-preview／isd-legacy；都不是時 None。"""
    p = Path(path)
    if not p.is_file():
        raise SealError("input_missing", "找不到檔案。")
    return detect_bytes(_read_head(p))


def pgp_kind(path) -> str | None:
    return pgpmode.pgp_kind(_read_head(Path(path)))


# ── 鑰匙 ────────────────────────────────────────────────────────────────

@dataclass
class Keyring:
    """解密時手上有的所有鑰匙。``repr`` 不含祕密。"""

    age_identities: list = field(default_factory=list, repr=False)
    passphrase: str | None = field(default=None, repr=False)
    pgp_secret_keys: list = field(default_factory=list)
    pgp_key_passphrase: str | None = field(default=None, repr=False)
    isd2_material: KeyMaterial | None = field(default=None, repr=False)

    def age_ids(self) -> list:
        ids = list(self.age_identities)
        if self.passphrase:
            ids.append(agefmt.passphrase_identity(self.passphrase))
        return ids

    def is_empty(self) -> bool:
        return not (self.age_identities or self.passphrase or self.pgp_secret_keys
                    or self.isd2_material is not None)


def classify_key_file(path) -> str:
    """鑰匙檔是哪一種：``pgp-secret``／``pgp-public``／``age``（含密語保護的 age 身分檔）。"""
    p = Path(path)
    if not p.is_file():
        raise SealError("key_missing", "找不到金鑰檔。", action="確認路徑；金鑰若放在外接裝置，先接上再試。")
    kind = pgp_kind(p)
    if kind == "secret_key":
        return "pgp-secret"
    if kind == "public_key":
        return "pgp-public"
    return "age"


def load_identities(paths, passphrase_provider=None) -> tuple[list, list[Path]]:
    """讀鑰匙檔：age 身分檔變成私鑰清單，OpenPGP 私鑰檔原樣收集。回傳 (age 私鑰, PGP 私鑰檔)。

    ``passphrase_provider(path)`` 在身分檔有密語保護時被呼叫，回傳那個身分檔的密語。
    """
    ages: list = []
    pgps: list[Path] = []
    for raw in paths:
        p = Path(raw)
        kind = classify_key_file(p)
        if kind == "pgp-secret":
            pgps.append(p)
            continue
        if kind == "pgp-public":
            raise SealError("bad_key_format", "這是 OpenPGP 公鑰，不能用來解密。",
                            action="解密要用私鑰（.secret.asc）；公鑰是給別人加密用的。")
        provider = None if passphrase_provider is None else (lambda p=p: passphrase_provider(p))
        for ident in agefmt.load_identity_file(p, provider):
            if ident not in ages:
                ages.append(ident)
    return ages, pgps


def default_keyring_paths() -> tuple[list[Path], list[Path]]:
    """.env 設定的預設身分檔與 PGP 私鑰（只回傳存在的檔案）。"""
    age = [p for p in (settings.identity_file(),) if p is not None and p.is_file()]
    pgp = [p for p in (settings.pgp_secret_key(),) if p is not None and p.is_file()]
    return age, pgp


@dataclass
class Recipients:
    """加密（或換鎖）時的收件人，已經檢查過組合。"""

    mode: str
    age: list = field(default_factory=list)            # X25519Recipient
    pgp_keys: list = field(default_factory=list)       # OpenPGP 公鑰檔
    master_included: bool = False
    use_passphrase: bool = False

    def summary(self) -> dict:
        if self.mode == MODE_AGE:
            return {"keys": len(self.age), "passphrase": self.use_passphrase,
                    "master": self.master_included}
        return {"keys": len(self.pgp_keys), "passphrase": self.use_passphrase,
                "master": self.master_included}


def _master_age():
    value = settings.master_recipient()
    if not value:
        raise SealError("key_missing", "還沒設定萬用鎖的公鑰。",
                        action=f"在 .env 設定 {settings.MASTER_RECIPIENT}=age1…（或在視窗的「金鑰」分頁設定）。")
    try:
        return agefmt.parse_recipient(value)
    except SealError:
        raise SealError("bad_key_format", "設定裡的萬用鎖公鑰格式不對（應該是 age1 開頭）。",
                        action=f"檢查 .env 的 {settings.MASTER_RECIPIENT}。") from None


def _master_pgp() -> Path:
    path = settings.master_pgp_key()
    if path is None:
        raise SealError("key_missing", "還沒設定 PGP 模式的萬用鎖公鑰檔。",
                        action=f"在 .env 設定 {settings.MASTER_PGP_KEY}=<公鑰 .asc 檔的路徑>。")
    if not path.is_file():
        raise SealError("key_missing", "設定裡的 PGP 萬用鎖公鑰檔不存在。",
                        action=f"檢查 .env 的 {settings.MASTER_PGP_KEY}。")
    return path


def _read_recipients_file(path) -> list:
    p = Path(path)
    if not p.is_file():
        raise SealError("key_missing", "找不到收件人清單檔。", action="確認 -R 的路徑。")
    if pgp_kind(p) is not None:
        raise SealError("bad_key_format", "這是 OpenPGP 金鑰檔，不是 age 收件人清單。",
                        action="OpenPGP 公鑰請改用 PGP 模式（--mode pgp --pgp-recipient）。")
    try:
        if p.stat().st_size > 1 << 20:
            raise SealError("bad_key_format", "收件人清單檔太大，看起來不是收件人清單。")
        blob = p.read_bytes()
    except OSError as exc:
        raise SealError("io_error", "讀不到收件人清單檔。", detail=type(exc).__name__) from None
    if agefmt.is_encrypted_identity_file(blob):
        raise SealError("bad_key_format", "這是有密語保護的身分檔，不能直接當收件人。",
                        action="改用它的公鑰（age1…，產生時有印出來，或在「金鑰」分頁檢查這個檔案）。")
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SealError("bad_key_format", "收件人清單檔不是 UTF-8 文字。") from None
    if "AGE-SECRET-KEY-" in text.upper():   # 自己的身分檔：加密給它對應的公鑰（age -e -i 的行為）
        return [ident.recipient for ident in agefmt.parse_identity_file(text)]
    return agefmt.parse_recipients(text)


def resolve_recipients(mode: str = MODE_AGE, *, recipients=(), recipient_files=(),
                       with_master: bool = False, pgp_recipient_files=(),
                       use_passphrase: bool = False) -> Recipients:
    """檢查「誰可以打開」的組合並讀進公鑰。命令列在問密語之前就呼叫它，組合不對時不必白打密語。"""
    if mode not in MODES:
        raise SealError("bad_input", "模式只能是 age（簡單模式）或 pgp。")
    result = Recipients(mode, use_passphrase=use_passphrase)
    if mode == MODE_AGE:
        if pgp_recipient_files:
            raise SealError("bad_input", "OpenPGP 公鑰只能用在 PGP 模式。",
                            action="加上 --mode pgp，或改用 age1 公鑰（-r）。")
        found: list = []
        for value in recipients:
            r = agefmt.parse_recipient(str(value).strip())
            if r not in found:
                found.append(r)
        for path in recipient_files:
            for r in _read_recipients_file(path):
                if r not in found:
                    found.append(r)
        if with_master:
            master = _master_age()
            if master not in found:
                found.append(master)
            result.master_included = True
        if use_passphrase and found:
            raise SealError(
                "bad_input",
                "簡單模式（age 規格）不允許密語跟金鑰（包括萬用鎖）放在同一個檔案。",
                action="要「密語＋萬用鎖」請改用 PGP 模式（--mode pgp）；或全部改用金鑰（age1 公鑰）。",
                detail="scrypt-not-alone",
            )
        if not found and not use_passphrase:
            raise SealError("key_missing", "沒有指定誰可以打開：至少要一把公鑰（-r／-R）、萬用鎖或密語。")
        result.age = found
        return result
    if recipients or recipient_files:
        raise SealError("bad_input", "age1 公鑰只能用在簡單模式（age）。",
                        action="PGP 模式請用 --pgp-recipient <公鑰 .asc 檔>。")
    keys: list[Path] = []
    for path in pgp_recipient_files:
        p = Path(path)
        if not p.is_file():
            raise SealError("key_missing", "找不到 OpenPGP 公鑰檔。", action="確認 --pgp-recipient 的路徑。")
        if p.resolve() not in [k.resolve() for k in keys]:
            keys.append(p)
    if with_master:
        master = _master_pgp()
        if master.resolve() not in [k.resolve() for k in keys]:
            keys.append(master)
        result.master_included = True
    if not keys and not use_passphrase:
        raise SealError("key_missing", "沒有指定誰可以打開：至少要一把 OpenPGP 公鑰、萬用鎖或密語。")
    result.pgp_keys = keys
    return result


# ── 共用：輸出位置 ──────────────────────────────────────────────────────

def _temp_beside(dst: Path, suffix: str = "") -> Path:
    return dst.with_name(f".{dst.name}.partial-{secrets.token_hex(4)}{suffix}")


def _remove(path: Path | None) -> None:
    if path is not None:
        packing.remove_tree(path)


def _check_file_target(dst: Path, force: bool) -> None:
    if not dst.parent.is_dir():
        raise SealError("input_missing", "輸出位置的資料夾不存在。", action="先建立資料夾，或換一個輸出位置。")
    if dst.is_dir():
        raise SealError("output_exists", "輸出位置是一個已存在的資料夾。", action="用 -o 指定一個檔名。")
    if dst.exists() and not force:
        raise SealError("output_exists", "輸出檔已經存在，沒有覆蓋。",
                        action="換一個輸出位置（-o），或確定要覆蓋時加 --force。")


def _check_any_target(dst: Path, force: bool) -> None:
    """解密前的檢查：還不知道內容是檔案還是資料夾。"""
    if not dst.parent.is_dir():
        raise SealError("input_missing", "輸出位置的資料夾不存在。", action="先建立資料夾，或換一個輸出位置。")
    if dst.is_dir():
        if any(dst.iterdir()):
            raise SealError("output_exists", "輸出位置已經有一個非空的資料夾，沒有覆蓋。",
                            action="換一個輸出位置（-o）；資料夾不會被覆蓋，即使加了 --force。")
    elif dst.exists() and not force:
        raise SealError("output_exists", "輸出檔已經存在，沒有覆蓋。",
                        action="換一個輸出位置（-o），或確定要覆蓋時加 --force。")


def _commit_file(tmp: Path, dst: Path, force: bool) -> None:
    if dst.is_dir():
        if any(dst.iterdir()):
            raise SealError("output_exists", "輸出位置已經有一個非空的資料夾，沒有覆蓋。")
        dst.rmdir()
    try:
        if force:
            os.replace(tmp, dst)
        elif os.name == "nt":
            os.rename(tmp, dst)
        else:
            os.link(tmp, dst)
            tmp.unlink()
    except FileExistsError:
        raise SealError("output_exists", "輸出檔已經存在，沒有覆蓋。", action="換一個輸出位置（-o）。") from None
    except OSError as exc:
        raise SealError("io_error", "寫不了輸出檔。", detail=type(exc).__name__) from None


def _commit_dir(tmp: Path, dst: Path) -> None:
    if dst.is_dir():
        if any(dst.iterdir()):
            raise SealError("output_exists", "輸出位置已經有一個非空的資料夾，沒有覆蓋。")
        dst.rmdir()
    elif dst.exists():
        raise SealError("output_exists", "要解成資料夾，但輸出位置已經有同名的檔案。",
                        action="換一個輸出位置（-o）。")
    try:
        os.replace(tmp, dst)
    except OSError as exc:
        raise SealError("io_error", "寫不了輸出資料夾。", detail=type(exc).__name__) from None


def default_encrypt_output(p: packing.Plan, mode: str, armor: bool) -> Path:
    if len(p.inputs) != 1:
        raise SealError("bad_input", "一次加密好幾個東西時，要用 -o 指定輸出檔名。")
    src = p.inputs[0]
    name = src.name + (".tar" if p.is_archive else "")
    suffix = ".age" if mode == MODE_AGE else (".asc" if armor else ".gpg")
    return src.with_name(name + suffix)


def strip_known_suffix(name: str) -> str | None:
    lower = name.lower()
    for suffix in KNOWN_SUFFIXES:
        if lower.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return None


def default_decrypt_output(src) -> Path | None:
    p = Path(src)
    base = strip_known_suffix(p.name)
    return None if base is None else p.with_name(base)


def _strip_tar(path: Path) -> Path:
    if path.name.lower().endswith(".tar") and len(path.name) > 4:
        return path.with_name(path.name[:-4])
    return path


# ── 加密 ────────────────────────────────────────────────────────────────

def encrypt(inputs, output=None, *, recipients: Recipients, passphrase: str | None = None,
            armor: bool = False, force: bool = False, progress=None) -> dict:
    """加密一個或多個輸入。``recipients`` 由 ``resolve_recipients`` 產生。"""
    if isinstance(inputs, (str, os.PathLike)):
        inputs = [inputs]
    if recipients.use_passphrase and not passphrase:
        raise SealError("key_missing", "密語是空的。")
    p = packing.plan(inputs)
    out = Path(output) if output else default_encrypt_output(p, recipients.mode, armor)
    packing.check_output_outside(p, out)
    _check_file_target(out, force)

    result = {"action": "encrypt", "mode": recipients.mode,
              "format": FMT_AGE if recipients.mode == MODE_AGE else FMT_PGP,
              "inputs": [str(x) for x in p.inputs], "output": str(out),
              "payload": "tar" if p.is_archive else "file", "armored": bool(armor),
              "recipients": recipients.summary()}
    if p.is_archive:
        result.update(files=p.files, skipped_links=p.skipped_links)
    if recipients.mode == MODE_AGE:
        recips = list(recipients.age)
        if passphrase:
            recips = [agefmt.passphrase_recipient(passphrase, AGE_SCRYPT_WORK_FACTOR)]
        if p.is_archive:
            def work(fh):
                reader = packing.IterReader(packing.iter_tar(p, progress))
                return agefmt.encrypt_stream(reader, fh, recips, armor=armor)
            res = _atomic_write(out, force, work)
        else:
            res = agefmt.encrypt_file(p.single_file, out, recips, armor=armor, overwrite=force,
                                      progress=progress)
        result.update(bytes_in=res.plaintext_size, bytes_out=out.stat().st_size)
    else:
        tmp = None
        try:
            src = p.single_file
            if p.is_archive:
                tmp = _temp_beside(out, ".tar")
                with open(tmp, "wb") as fh:
                    packing.write_tar(p, fh, progress)
                src = tmp
            res = pgpmode.encrypt_file(src, out, recipient_key_files=recipients.pgp_keys,
                                       passphrase=passphrase, armor=armor, overwrite=force)
        except OSError as exc:
            raise SealError("io_error", "讀寫檔案失敗（權限不足、磁碟滿了，或檔案正被別的程式使用）。",
                            detail=type(exc).__name__) from None
        finally:
            _remove(tmp)
        if progress and not p.is_archive:
            progress(p.total_bytes, p.total_bytes)
        result.update(bytes_in=p.total_bytes, bytes_out=res["bytes_out"],
                      pgp_recipients=res.get("recipients", []))
    if passphrase and len(passphrase) < MIN_PASSPHRASE_CHARS:
        result["warnings"] = ["passphrase_short"]
    return result


# ── 解密（一層）─────────────────────────────────────────────────────────

def _legacy_error() -> SealError:
    return SealError("legacy_format", "這是舊版格式（.isd）的檔案，命令列不處理舊格式。",
                     action="用視窗程式的「關於 → 開啟舊版工具」解密。")


def _unknown_error() -> SealError:
    return SealError("unsupported_format",
                     "這不是 age、OpenPGP 或這個工具認得的加密檔。",
                     action="確認選對了檔案；舊版 .isd 請用視窗程式的舊版工具。")


def _isd2_material(keyring: Keyring) -> KeyMaterial:
    if keyring.isd2_material is not None:
        return keyring.isd2_material
    if keyring.passphrase:
        return passphrase_material(keyring.passphrase)
    raise SealError("key_missing", "這是 ISD2 預覽格式（已停用）的檔案，需要當初的金鑰檔或密語。",
                    action="用 --key-file（舊的金鑰檔）或 --passphrase 解密。")


def decrypt(src, output=None, keyring: Keyring | None = None, *, force: bool = False,
            keep_tar: bool = False, progress=None) -> dict:
    """解開一層。內容是 tar 時（除非 keep_tar）還原成資料夾。失敗不留下任何輸出。"""
    keyring = keyring or Keyring()
    src_p = Path(src)
    fmt = detect_format(src_p)
    if fmt is None:
        raise _unknown_error()
    if fmt == FMT_LEGACY:
        raise _legacy_error()
    if fmt == FMT_ISD2:
        res = _isd2_decrypt_path(src_p, output, _isd2_material(keyring), force=force,
                                 keep_tar=keep_tar, progress=progress)
        res.update(format=FMT_ISD2, deprecated=True)
        return res
    if fmt == FMT_PGP:
        kind = pgp_kind(src_p)
        if kind != "message":
            raise SealError("unsupported_format", "這是 OpenPGP 金鑰或簽章檔，不是加密檔。",
                            action="選要解密的 .gpg／.asc 加密檔。")
        if not keyring.pgp_secret_keys and not keyring.passphrase:
            raise SealError("key_missing", "這是 OpenPGP 加密檔，需要 OpenPGP 私鑰或密語。",
                            action="用 -i／--pgp-secret 指定私鑰檔（.asc），或用 --passphrase。")

    explicit = output is not None and str(output) != ""
    out = Path(output) if explicit else default_decrypt_output(src_p)
    if out is None:
        raise SealError("bad_input", "加密檔的副檔名不是 .age／.gpg／.asc，無法決定輸出檔名。",
                        action="用 -o 指定輸出位置。")
    if out.resolve() == src_p.resolve():
        raise SealError("bad_input", "輸出位置不能跟輸入是同一個。")
    _check_any_target(out, force)

    tmp = _temp_beside(out)
    tmp_dir = None
    result = {"action": "decrypt", "format": fmt, "input": str(src_p)}
    try:
        if fmt == FMT_AGE:
            res = agefmt.decrypt_file(src_p, tmp, keyring.age_ids(), progress=progress)
            result["matched"] = res.matched
            master = settings.master_recipient()
            result["used_master"] = bool(master) and res.matched == "X25519 " + master
        else:
            res = pgpmode.decrypt_file(src_p, tmp, secret_key_files=keyring.pgp_secret_keys,
                                       key_passphrase=keyring.pgp_key_passphrase,
                                       passphrase=keyring.passphrase)
            result["used"] = res.get("used")
            if progress:
                size = src_p.stat().st_size
                progress(size, size)
        if packing.is_tar(tmp) and not keep_tar:
            final = out if explicit else _strip_tar(out)
            if final != out:
                _check_any_target(final, False)
            if final.exists() and not final.is_dir():
                raise SealError("output_exists", "要解成資料夾，但輸出位置已經有同名的檔案。",
                                action="換一個輸出位置（-o）。")
            tmp_dir = _temp_beside(final)
            try:
                result["files"] = packing.extract_tar(tmp, tmp_dir)
            except tarfile.TarError as exc:
                raise SealError("corrupt", "解開後的資料夾封存內容不正確。", detail=type(exc).__name__) from None
            _commit_dir(tmp_dir, final)
            tmp_dir = None
            result.update(output=str(final), payload="folder")
        else:
            payload = "tar" if packing.is_tar(tmp) else "file"
            size = tmp.stat().st_size
            _commit_file(tmp, out, force)
            result.update(output=str(out), payload=payload, bytes_out=size)
    except OSError as exc:
        raise SealError("io_error", "讀寫檔案失敗（權限不足、磁碟滿了，或檔案正被別的程式使用）。",
                        detail=type(exc).__name__) from None
    finally:
        _remove(tmp)
        _remove(tmp_dir)
    return result


# ── 一路解到底（剝洋蔥）───────────────────────────────────────────────

def describe_lock(path, fmt: str | None = None) -> dict:
    """不需要鑰匙就看得到的「這一層要什麼」。"""
    p = Path(path)
    fmt = fmt or detect_format(p)
    info: dict = {"format": fmt}
    try:
        if fmt == FMT_AGE:
            a = agefmt.inspect(p)
            info.update(recipient_types=dict(a.stanza_counts), passphrase=a.passphrase_protected,
                        armored=a.armored)
        elif fmt == FMT_PGP:
            d = pgpmode.inspect(p)
            info.update(recipient_key_ids=[r.get("key_id") for r in d.get("recipients", [])],
                        passphrase=bool(d.get("has_passphrase")), armored=bool(d.get("armor")))
        elif fmt == FMT_ISD2:
            d = _isd2_info_path(p)
            info.update(kdf=d.get("kdf"), payload=d.get("payload"))
    except SealError as err:
        info["details_unavailable"] = err.code
    return info


def _free_name(path: Path) -> Path:
    """path 已存在時改成「名稱 (2)」「名稱 (3)」…"""
    candidate = path
    n = 1
    while candidate.exists() or candidate.is_symlink():
        n += 1
        if n > 1000:
            raise SealError("io_error", "找不到可以用的輸出名稱。")
        candidate = path.with_name(f"{path.name} ({n})")
    return candidate


def _inner_target(path: Path) -> Path:
    base = strip_known_suffix(path.name) or (path.name + ".decrypted")
    return _free_name(path.with_name(base))


def decrypt_all_layers(src, output=None, keyring: Keyring | None = None, *, force: bool = False,
                       progress=None, max_layers: int = MAX_LAYERS) -> dict:
    """解開後若結果仍是加密檔（或資料夾最上層有加密檔），用同一組鑰匙繼續解，直到解不開為止。

    第一層解不開就是一般的錯誤；內層解不開不算失敗，結果的 ``complete`` 是 False，
    ``stopped`` 列出停在哪一層、哪個檔案、看得到的資訊。
    """
    keyring = keyring or Keyring()
    first = decrypt(src, output, keyring, force=force, progress=progress)
    top = Path(first["output"])
    layers = [{"depth": 1, "path": ".", "format": first["format"], "payload": first["payload"]}]
    stopped: list[dict] = []
    budget = [MAX_LAYER_ITEMS]

    def rel(p: Path) -> str:
        if p == top:
            return "."
        try:
            return p.relative_to(top).as_posix()
        except ValueError:
            return p.name

    def stop(path: Path, depth: int, fmt: str, reason: str, err: SealError | None = None) -> None:
        entry = {"depth": depth, "path": rel(path), "reason": reason, "lock": describe_lock(path, fmt)}
        if err is not None:
            entry.update(code=err.code, message=err.reason)
        stopped.append(entry)

    def peel_file(path: Path, depth: int, replace_in_place: bool) -> None:
        try:
            fmt = detect_format(path)
        except SealError:
            return
        if fmt not in ENCRYPTED_FORMATS:
            return
        if fmt == FMT_PGP and pgp_kind(path) != "message":
            return
        if depth > max_layers:
            stop(path, depth, fmt, "depth_limit")
            return
        if budget[0] <= 0:
            stop(path, depth, fmt, "too_many_items")
            return
        budget[0] -= 1
        target = _temp_beside(path) if replace_in_place else _inner_target(path)
        try:
            res = decrypt(path, target, keyring)
        except SealError as err:
            reason = "needs_other_key" if err.code in ("wrong_key", "key_missing") else "error"
            stop(path, depth, fmt, reason, err)
            return
        made = Path(res["output"])
        try:
            _remove(path)              # 這是我們自己解出來的中間檔，原始輸入不會被動到
            if replace_in_place:
                os.replace(made, path)
                made = path
            elif res["payload"] == "folder" and _strip_tar(made) != made:
                nicer = _free_name(_strip_tar(made))   # 「L2.tar.age」解開後叫「L2」
                os.replace(made, nicer)
                made = nicer
        except OSError as exc:
            stop(made if made.exists() else path, depth, fmt, "error",
                 SealError("io_error", "解開後整理檔名失敗（檔案可能正被別的程式使用）。",
                           detail=type(exc).__name__))
            return
        layers.append({"depth": depth, "path": rel(made), "format": fmt, "payload": res["payload"]})
        peel(made, depth + 1)

    def peel(path: Path, depth: int) -> None:
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda c: c.name):
                if child.is_file() and not child.is_symlink():
                    peel_file(child, depth, replace_in_place=False)
        elif path.is_file():
            peel_file(path, depth, replace_in_place=True)

    peel(top, 2)
    first.update(all_layers=True, layers=layers, stopped=stopped, complete=not stopped,
                 depth=max(layer["depth"] for layer in layers))
    return first


# ── 看資訊 ──────────────────────────────────────────────────────────────

def inspect(src) -> dict:
    p = Path(src)
    fmt = detect_format(p)
    base = {"action": "inspect", "input": str(p), "size": p.stat().st_size, "format": fmt}
    if fmt is None:
        raise _unknown_error()
    if fmt in (FMT_ISD2, FMT_LEGACY):
        data = _isd2_info_path(p)
        data.update(action="inspect", format=fmt)
        if fmt == FMT_ISD2:
            data["deprecated"] = True
            data["note"] = "ISD2 預覽格式（已停用）：只能解密，不能再產生。"
        return data
    if fmt == FMT_AGE:
        base.update(agefmt.inspect(p).to_dict())
        base.pop("path", None)
        return base
    try:
        data = pgpmode.inspect(p)
    except SealError as err:
        if err.code != "dependency_missing":
            raise
        base.update(kind=pgp_kind(p), details_unavailable="gpg_missing",
                    note="找不到 gpg，只能看出是 OpenPGP；收件人等細節要裝了 gpg 才看得到。")
        return base
    data.update(action="inspect", format=FMT_PGP)
    return data


# ── 產生金鑰 ────────────────────────────────────────────────────────────

def keygen_age(path=None, *, passphrase: str | None = None, force: bool = False) -> dict:
    """產生 age 身分檔（與 age-keygen 相同格式；可用密語保護）。回傳公鑰，不回傳私鑰。"""
    p = Path(path) if path else Path(DEFAULT_IDENTITY_NAME)
    ident = agefmt.generate_identity()
    agefmt.write_identity_file(p, [ident], passphrase=passphrase, overwrite=force,
                               work_factor=AGE_SCRYPT_WORK_FACTOR)
    return {"action": "keygen", "mode": MODE_AGE, "path": str(p), "public_key": ident.public_key,
            "protected": passphrase is not None}


def keygen_pgp(prefix=None, *, name: str = "Encrypter key", email: str | None = None,
               passphrase: str | None = None, key_type: str = "ed25519", force: bool = False) -> dict:
    base = Path(prefix) if prefix else Path(DEFAULT_PGP_PREFIX)
    public = base.with_name(base.name + ".public.asc")
    secret = base.with_name(base.name + ".secret.asc")
    res = pgpmode.generate_keypair(name, email, out_public=public, out_secret=secret,
                                   passphrase=passphrase, overwrite=force, key_type=key_type)
    res.update(action="keygen", mode=MODE_PGP)
    return res


# ── 換鎖與換檔案金鑰 ────────────────────────────────────────────────────

def _require_age_or_pgp(src: Path, what: str) -> str:
    fmt = detect_format(src)
    if fmt is None:
        raise _unknown_error()
    if fmt == FMT_LEGACY:
        raise _legacy_error()
    if fmt == FMT_ISD2:
        raise SealError("unsupported_format", f"ISD2 預覽格式（已停用）不能{what}。",
                        action="先 decrypt 解開，再用簡單模式或 PGP 模式重新加密。")
    return fmt


def rewrap(src, output, keyring: Keyring, recipients: Recipients, *, new_passphrase: str | None = None,
           armor: bool | None = None, force: bool = False) -> dict:
    """換鎖（只限 age）：用手上能開的鑰匙取出檔案金鑰，換一組收件人；內容位元組原封不動。

    誠實限制：檔案金鑰沒換，已經被複製走的舊檔仍然打得開；要讓舊鑰匙真的失效請用 rekey 並刪掉舊副本。
    """
    src_p = Path(src)
    fmt = _require_age_or_pgp(src_p, "換鎖")
    if fmt == FMT_PGP:
        raise SealError("unsupported_format", "OpenPGP 檔不能只換鎖（gpg 沒有這個功能）。",
                        action="改用 rekey：解開後用新的收件人整份重新加密。")
    if recipients.mode != MODE_AGE:
        raise SealError("bad_input", "age 檔的新收件人要用 age1 公鑰（-r／-R／--with-master）。")
    new = list(recipients.age)
    if new_passphrase:
        new = [agefmt.passphrase_recipient(new_passphrase, AGE_SCRYPT_WORK_FACTOR)]
    res = agefmt.rewrap(src_p, Path(output), keyring.age_ids(), new, armor=armor, overwrite=force)
    data = res.to_dict()
    data.update(action="rewrap", format=FMT_AGE, input=str(src_p), recipients=recipients.summary())
    return data


def rekey(src, output, keyring: Keyring, recipients: Recipients, *, new_passphrase: str | None = None,
          armor: bool | None = None, force: bool = False) -> dict:
    """換檔案金鑰：解開後用新的檔案金鑰與新的收件人整份重新加密。之後只有新收件人打得開新檔；
    已經流出去的舊檔副本，舊鑰匙仍然打得開。"""
    src_p = Path(src)
    out = Path(output)
    fmt = _require_age_or_pgp(src_p, "換檔案金鑰")
    expected = MODE_AGE if fmt == FMT_AGE else MODE_PGP
    if recipients.mode != expected:
        raise SealError("bad_input", "rekey 不換格式：age 檔的新收件人用 age1 公鑰，OpenPGP 檔用 OpenPGP 公鑰。",
                        action="要換格式請先 decrypt，再用另一種模式 encrypt。")
    if fmt == FMT_AGE:
        new = list(recipients.age)
        if new_passphrase:
            new = [agefmt.passphrase_recipient(new_passphrase, AGE_SCRYPT_WORK_FACTOR)]
        res = agefmt.rekey(src_p, out, keyring.age_ids(), new, armor=armor, overwrite=force)
        data = res.to_dict()
    else:
        if not keyring.pgp_secret_keys and not keyring.passphrase:
            raise SealError("key_missing", "這是 OpenPGP 加密檔，需要 OpenPGP 私鑰或密語才能先解開。")
        _check_file_target(out, force)
        plain = _temp_beside(out, ".plain")
        try:
            pgpmode.decrypt_file(src_p, plain, secret_key_files=keyring.pgp_secret_keys,
                                 key_passphrase=keyring.pgp_key_passphrase,
                                 passphrase=keyring.passphrase)
            use_armor = bool(armor) if armor is not None else _read_head(src_p).lstrip().startswith(b"-----BEGIN")
            data = pgpmode.encrypt_file(plain, out, recipient_key_files=recipients.pgp_keys,
                                        passphrase=new_passphrase, armor=use_armor, overwrite=force)
        finally:
            _remove(plain)
    data.update(action="rekey", format=fmt, input=str(src_p), output=str(out),
                recipients=recipients.summary())
    return data


# ── 自我檢查 ────────────────────────────────────────────────────────────

def self_check() -> dict:
    """離線自我檢查：cryptography、age 往返（金鑰與密語）、gpg 是否可用。不碰任何真資料。"""
    data: dict = {"action": "check", "python": platform.python_version()}
    try:
        import cryptography
        data["cryptography"] = cryptography.__version__
    except ImportError:
        data["cryptography"] = None
    try:
        ident = agefmt.generate_identity()
        sample = os.urandom(70_000)
        blob = agefmt.encrypt_bytes(sample, [ident.recipient, agefmt.generate_identity().recipient])
        data["age_roundtrip"] = agefmt.decrypt_bytes(blob, [ident]) == sample
        pblob = agefmt.encrypt_bytes(b"check", [agefmt.passphrase_recipient("self-check", 10)], armor=True)
        data["age_passphrase_roundtrip"] = agefmt.decrypt_bytes(pblob, [agefmt.passphrase_identity("self-check")]) == b"check"
    except SealError as err:
        data["age_roundtrip"] = False
        data["age_error"] = err.code
    try:
        info = pgpmode.find_gpg()
        data["gpg"] = {"available": True, "version": info.version, "path": str(info.path),
                       "msys": bool(info.msys)}
    except SealError as err:
        data["gpg"] = {"available": False, "reason": err.reason}
    data["settings"] = settings.describe()
    data["ok"] = bool(data.get("cryptography") and data.get("age_roundtrip")
                      and data.get("age_passphrase_roundtrip"))
    data["modes"] = {"age": data["ok"], "pgp": data["gpg"]["available"]}
    return data
