"""Encrypter 的設定：萬用鎖公鑰、預設身分檔的「路徑」。放在專案的 .env（repo 規則 AGENTS.md 第 6 條）。

規則跟 ``libs/toolzoo/appdirs`` 一樣（Encrypter 不依賴 ``libs``，這裡用最小的等效做法照抄，
理由：接 ``libs`` 要改 ``tool.json`` 的 ``pathex``，之後改 ``libs`` 就得連 Encrypter 一起重新打包測試，
而這裡只需要「找 .env、讀幾個鍵、改一行」）：

    從原始碼執行  repo 根目錄的 .env
    打包的 exe    exe 旁邊的 .env；exe 放在 repo 的 dist/ 裡時，也讀 repo 根目錄的 .env
    TOOLZOO_DATA_DIR 有設時  <TOOLZOO_DATA_DIR>/.env（測試用）

環境變數永遠優先於 .env。以 ``...`` 結尾的值是範本佔位，當成沒填。

**這裡只放公開的東西與路徑**：萬用鎖的公鑰（``age1…``，不是祕密）、身分檔／PGP 金鑰檔的路徑。
金鑰本身（``AGE-SECRET-KEY-1…``）不能寫進 .env 的這些鍵，讀到時拒絕使用。
"""

from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path

from .errors import SealError

MASTER_RECIPIENT = "ENCRYPTER_MASTER_RECIPIENT"        # 萬用鎖公鑰 age1…（簡單模式；多把用逗號分開）
MASTER_PGP_KEY = "ENCRYPTER_MASTER_PGP_KEY"            # 萬用鎖的 OpenPGP 公鑰檔路徑（PGP 模式；多個用 ; 分開）
IDENTITY_FILE = "ENCRYPTER_IDENTITY_FILE"              # 預設 age 身分檔路徑（解密時沒給 -i 就用它）
PGP_SECRET_KEY = "ENCRYPTER_PGP_SECRET_KEY"            # 預設 OpenPGP 私鑰檔路徑（解密時沒給 --pgp-secret 就用它）

KEYS = (MASTER_RECIPIENT, MASTER_PGP_KEY, IDENTITY_FILE, PGP_SECRET_KEY)
_PATH_KEYS = (IDENTITY_FILE, PGP_SECRET_KEY)
_REPO_MARKER = Path("scripts") / "tool.spec"
_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _override() -> Path | None:
    value = os.environ.get("TOOLZOO_DATA_DIR", "").strip()
    return Path(value) if value else None


def _repo_root() -> Path | None:
    start = Path(sys.executable).resolve().parent if _is_frozen() else Path(__file__).resolve().parent
    for folder in (start, *start.parents):
        if (folder / _REPO_MARKER).is_file():
            return folder
    return None


def env_files() -> list[Path]:
    """要讀的 .env，前面的優先。"""
    override = _override()
    if override:
        return [override / ".env"]
    files: list[Path] = []
    if _is_frozen():
        files.append(Path(sys.executable).resolve().parent / ".env")
    repo = _repo_root()
    if repo:
        files.append(repo / ".env")
    return list(dict.fromkeys(files))


def env_file_for_writing() -> Path:
    """畫面上「儲存設定」時寫哪一個 .env。"""
    override = _override()
    if override:
        override.mkdir(parents=True, exist_ok=True)
        return override / ".env"
    repo = _repo_root()
    if repo:
        return repo / ".env"
    return Path(sys.executable).resolve().parent / ".env"


def _read(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, value = line.split("=", 1)
        data[name.strip()] = value.strip().strip('"').strip("'")
    return data


def _lookup(name: str) -> tuple[str, Path | None]:
    """(值, 來源 .env；來自環境變數時是 None)。沒設定時值是空字串。"""
    value = os.environ.get(name, "").strip()
    if value:
        return value, None
    for path in env_files():
        value = _read(path).get(name, "").strip()
        if value and not value.endswith("..."):
            return value, path
    return "", None


def get(name: str) -> str:
    return _lookup(name)[0]


def _looks_secret(value: str) -> bool:
    return value.upper().startswith("AGE-SECRET-KEY-") or "PRIVATE KEY" in value.upper()


def _checked(name: str) -> tuple[str, Path | None]:
    value, origin = _lookup(name)
    if value and _looks_secret(value):
        raise SealError(
            "bad_key_format",
            f"設定 {name} 裡放的是私鑰本身；這個設定只能放公鑰或檔案路徑。",
            action="把私鑰存成身分檔（keygen），設定裡改寫那個檔案的路徑；並把 .env 裡的私鑰刪掉。",
        )
    return value, origin


def _as_path(name: str) -> Path | None:
    value, origin = _checked(name)
    if not value:
        return None
    path = Path(os.path.expandvars(value))
    if not path.is_absolute() and origin is not None:
        path = origin.parent / path   # 相對路徑以那個 .env 所在的資料夾為準
    return path


_AGE_LIST_SPLIT = re.compile(r"[\s,;，；]+")


def master_recipients() -> list[str]:
    """設定好的萬用鎖公鑰（age1…），可以好幾把；沒設定時是空清單。格式由 agefmt 檢查。

    一個值裡放多把：用逗號、分號、空白或換行分開（.env 一行寫不下換行，用逗號）。
    重複的只算一次，順序照寫的順序。
    """
    value, _origin = _checked(MASTER_RECIPIENT)
    parts = [p for p in _AGE_LIST_SPLIT.split(value) if p]
    return list(dict.fromkeys(parts))


def master_pgp_keys() -> list[Path]:
    """PGP 模式的萬用鎖公鑰檔，可以好幾個：路徑之間用分號 ``;`` 或換行分開（路徑本身可能有逗號與空白）。"""
    value, origin = _checked(MASTER_PGP_KEY)
    out: list[Path] = []
    for raw in re.split(r"[;；\r\n]+", value):
        raw = raw.strip().strip('"').strip("'")
        if not raw:
            continue
        path = Path(os.path.expandvars(raw))
        if not path.is_absolute() and origin is not None:
            path = origin.parent / path   # 相對路徑以那個 .env 所在的資料夾為準
        if path not in out:
            out.append(path)
    return out


def identity_file() -> Path | None:
    return _as_path(IDENTITY_FILE)


def pgp_secret_key() -> Path | None:
    return _as_path(PGP_SECRET_KEY)


def describe() -> dict:
    """給 --check 與畫面看的設定摘要（只有公鑰與路徑，沒有祕密）。"""
    out = {"env_files": [str(p) for p in env_files()]}
    for name in KEYS:
        try:
            value, origin = _checked(name)
        except SealError:
            out[name] = {"set": True, "valid": False}
            continue
        out[name] = {"set": bool(value), "value": value or None,
                     "from": "environment" if value and origin is None else (str(origin) if origin else None)}
    for name, func in ((MASTER_RECIPIENT, master_recipients), (MASTER_PGP_KEY, master_pgp_keys)):
        if "valid" not in out[name]:        # 萬用鎖可以好幾把：多給一個數量
            out[name]["count"] = len(func())
    return out


def load_into_environ() -> None:
    """把 .env 裡 ENCRYPTER_ 開頭的設定載入環境變數（已設定的不覆蓋）。

    pgpmode 讀的 ENCRYPTER_GPG／ENCRYPTER_GPG_TMPDIR 也因此可以寫在 .env。只載入這個工具的鍵，
    不把同一個 .env 裡別的工具的金鑰帶進這個行程。
    """
    for path in env_files():
        for name, value in _read(path).items():
            if (name.startswith("ENCRYPTER_") and _NAME_RE.match(name) and value
                    and not value.endswith("...") and name not in os.environ):
                os.environ[name] = value


def set_value(name: str, value: str) -> Path:
    """改 .env 裡的一個設定（沒有就加在最後；value 空字串＝刪掉那一行），其他行原封不動。

    只允許這個模組認得的鍵，而且不接受私鑰。回傳寫入的 .env 路徑。
    """
    if name not in KEYS:
        raise SealError("bad_input", "不認得的設定名稱。")
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise SealError("bad_input", "設定值不能有換行。")
    if value and _looks_secret(value):
        raise SealError("bad_key_format", "這個設定只能放公鑰或檔案路徑，不能放私鑰。",
                        action="私鑰請存成身分檔，這裡填它的路徑。")
    path = env_file_for_writing()
    try:
        text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise SealError("io_error", "讀不到 .env，沒有修改。", detail=type(exc).__name__) from None
    lines = text.splitlines()
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
    kept = [ln for ln in lines if not pattern.match(ln)]
    replaced = len(kept) != len(lines)
    if value:
        entry = f"{name}={value}"
        if replaced:   # 放回原本第一次出現的位置
            index = next(i for i, ln in enumerate(lines) if pattern.match(ln))
            kept.insert(min(index, len(kept)), entry)
        else:
            kept.append(entry)
    body = "\n".join(kept) + ("\n" if kept else "")
    tmp = path.with_name(f".{path.name}.partial-{secrets.token_hex(4)}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise SealError("io_error", "寫不了 .env。", detail=type(exc).__name__) from None
    if name in os.environ:      # 讓這個行程接下來看到新值
        if value:
            os.environ[name] = value
        else:
            del os.environ[name]
    return path
