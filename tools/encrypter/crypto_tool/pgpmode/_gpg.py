"""找系統上的 gpg、每次操作開一個暫時的專用 GNUPGHOME、安全地執行 gpg。

這裡的規則（細節與理由見 docs/pgp-mode.md）：

* **絕不碰使用者自己的金鑰環**：每次呼叫 gpg／gpgconf 都明確帶 ``--homedir <暫時資料夾>``，
  子行程環境的 ``GNUPGHOME`` 也設成同一個；用完 kill 掉這個 home 的 gpg-agent 並刪掉資料夾。
* **密語只走管線**（``--passphrase-fd 0`` + stdin），永遠不放在命令列引數或環境變數。
* **不連網路**：``--disable-dirmngr``、``--no-auto-key-retrieve``、``--no-auto-key-locate``。
* 不用 shell；有逾時；Windows 上不跳主控台視窗。
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

try:  # 測試時是 crypto_tool.pgpmode；實際執行時 crypto_tool/ 在 sys.path 上，是 pgpmode
    from ..sealed.errors import SealError
except ImportError:  # pragma: no cover - 依執行方式而定
    from sealed.errors import SealError

ENV_GPG = "ENCRYPTER_GPG"              # 指定 gpg 執行檔的完整路徑
ENV_TMPDIR = "ENCRYPTER_GPG_TMPDIR"    # 指定暫時 GNUPGHOME 放在哪個資料夾底下（選用）
MIN_VERSION = (2, 2, 0)
DEFAULT_TIMEOUT = 120.0                # 秒；大檔另外加（見 timeout_for）
_BYTES_PER_SECOND = 4 * 1024 * 1024    # 估逾時用的保守速度

# gpg-agent 在 home 裡開的 socket 最長的是 S.gpg-agent.browser；Unix socket（含 MSYS 的模擬）
# 路徑上限 108 位元組（含結尾 0），超過 agent 就起不來（實測：「socket name ... is too long」）。
_LONGEST_SOCKET = "/S.gpg-agent.browser"
_SOCKET_HOME_LEN = 107 - len(_LONGEST_SOCKET)   # 87：再長 agent 根本起不來
# 但 home 的長度還會影響另一件事：實測 Git for Windows 的 GnuPG 2.4.9，匯入「沒有密語保護」的
# Curve25519 私鑰後第一次使用，會不會「Bad secret key」取決於 home 參數（/c/… 形式）的**長度**、
# 金鑰本身、同一次匯入了哪幾把；同一個 home 裡重試也不會好，換一個長度的 home 通常就好
# （2026-11-13 實測 5 把金鑰 × 長度 43～86：43～54 有的壞、55～74 單把都正常、75 以上大多壞；
#  但「兩把一起匯入」在長度 64 也遇過必壞、在 55 正常）。
# 所以：home 一律補成指定長度（預設 HOME_LEN），需要用私鑰的操作在轉換失敗時換 HOME_LEN_CHOICES 裡的下一個長度重來
# （見 ops._session_with_keys）。上層資料夾太長、補不出名稱時換下一個候選（見 home_bases）。
HOME_LEN = 64
HOME_LEN_CHOICES = (64, 55, 70, 60, 58, 67)
MAX_HOME_LEN = min(_SOCKET_HOME_LEN, max(HOME_LEN_CHOICES))
_MIN_NAME_LEN = 8                                 # 隨機資料夾名稱至少 8 個十六進位字元
_HOME_MARKER = ".encrypter-gpg-home"   # 只有帶這個記號的資料夾才會被當成殘留清掉
_STALE_SECONDS = 24 * 3600
_PROBE_HOME = "/nonexistent/encrypter-gpg-probe"   # 只給 --version 用，gpg 不會建立它

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_VERSION_RE = re.compile(r"^gpg \(GnuPG[^)]*\)\s+(\d+)\.(\d+)(?:\.(\d+))?", re.MULTILINE)
_HOME_RE = re.compile(r"^Home:\s*(.+)$", re.MULTILINE)

_INSTALL_HINT = ("安裝 Gpg4win（https://gpg4win.org）或 Git for Windows（內附 gpg），"
                 f"或把環境變數 {ENV_GPG} 設成 gpg 執行檔的完整路徑。")


# ---------------------------------------------------------------- 找 gpg

@dataclass(frozen=True)
class GpgInfo:
    path: str
    version: str
    version_tuple: tuple[int, int, int]
    msys: bool                 # Git for Windows 附的 MSYS 版：GNUPGHOME 要用 /c/... 形式
    gpgconf: str | None        # 同一個資料夾裡的 gpgconf（用來 kill agent）
    source: str                # env / path / common

    def to_dict(self) -> dict:
        return {"path": self.path, "version": self.version, "msys": self.msys,
                "gpgconf": self.gpgconf, "source": self.source}


_cache: dict[tuple, GpgInfo] = {}


def _exe(name: str) -> str:
    return name + ".exe" if os.name == "nt" else name


def _common_locations() -> list[Path]:
    if os.name != "nt":
        return [Path("/usr/bin/gpg"), Path("/usr/local/bin/gpg"), Path("/opt/homebrew/bin/gpg")]
    found: list[Path] = []
    pf86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
    local = os.environ.get("LOCALAPPDATA")
    found.append(Path(pf86) / "GnuPG" / "bin" / "gpg.exe")     # Gpg4win
    found.append(Path(pf) / "GnuPG" / "bin" / "gpg.exe")
    found.append(Path(pf) / "Git" / "usr" / "bin" / "gpg.exe")  # Git for Windows
    if local:
        found.append(Path(local) / "Programs" / "Git" / "usr" / "bin" / "gpg.exe")  # 只裝給自己的 Git
    return found


def _candidates() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    on_path = shutil.which("gpg")
    if on_path:
        out.append(("path", Path(on_path)))
    out.extend(("common", p) for p in _common_locations())
    seen: set[str] = set()
    unique = []
    for source, path in out:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            unique.append((source, path))
    return unique


def _probe(path: Path, source: str) -> tuple[GpgInfo | None, str]:
    """跑 ``gpg --version``（指定一個不存在、也不會被建立的 home），回傳 (資訊, 不能用的原因)。"""
    if not path.is_file():
        return None, "不存在"
    try:
        proc = subprocess.run(
            [str(path), "--homedir", _PROBE_HOME, "--version"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
            env=_base_env(_PROBE_HOME), creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"無法執行（{type(exc).__name__}）"
    text = proc.stdout.decode("utf-8", "replace")
    match = _VERSION_RE.search(text)
    if proc.returncode != 0 or not match:
        return None, "不是 GnuPG"
    ver = (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))
    version = ".".join(map(str, ver))
    if ver < MIN_VERSION:
        return None, f"版本 {version} 太舊（需要 2.2 以上）"
    home = _HOME_RE.search(text)
    folder = path.parent
    msys = os.name == "nt" and (
        (folder / "msys-2.0.dll").is_file()
        or bool(home and home.group(1).strip().startswith("/"))
    )
    gpgconf = folder / _exe("gpgconf")
    return GpgInfo(
        path=str(path), version=version, version_tuple=ver, msys=msys,
        gpgconf=str(gpgconf) if gpgconf.is_file() else None, source=source,
    ), ""


def find_gpg(*, refresh: bool = False) -> GpgInfo:
    """依序找：環境變數 ENCRYPTER_GPG → PATH 上的 gpg → 常見安裝位置。版本要 2.2 以上。

    找不到時丟 ``SealError("dependency_missing")``。結果會快取（環境變數與 PATH 不變時）。
    """
    explicit = os.environ.get(ENV_GPG, "").strip().strip('"')
    key = (explicit, os.environ.get("PATH", ""))
    if not refresh and key in _cache:
        return _cache[key]

    if explicit:
        info, why = _probe(Path(explicit), "env")
        if info is None:
            raise SealError(
                "dependency_missing",
                f"環境變數 {ENV_GPG} 指定的 gpg 不能用（{why}）。",
                action=f"把 {ENV_GPG} 改成正確的 gpg 執行檔路徑，或刪掉這個設定讓工具自己找。",
                detail=f"{ENV_GPG}={explicit}",
            )
        _cache[key] = info
        return info

    problems = []
    for source, path in _candidates():
        info, why = _probe(path, source)
        if info is not None:
            _cache[key] = info
            return info
        if why != "不存在":
            problems.append(f"{path}: {why}")
    raise SealError(
        "dependency_missing",
        "找不到可用的 gpg（GnuPG 2.2 以上），PGP 模式無法使用；其他模式不受影響。",
        action=_INSTALL_HINT,
        detail="; ".join(problems),
    )


# ---------------------------------------------------------------- 暫時的 GNUPGHOME

def msys_path(path: str | os.PathLike) -> str:
    r"""Windows 路徑轉 MSYS 形式：``C:\Users\x`` → ``/c/Users/x``；UNC 變成 ``//server/share/...``。"""
    text = os.path.abspath(os.fspath(path))
    drive, rest = os.path.splitdrive(text)
    rest = rest.replace("\\", "/")
    if len(drive) == 2 and drive[1] == ":":
        return "/" + drive[0].lower() + rest
    return (drive + rest).replace("\\", "/")


def home_argument(info: GpgInfo, folder: Path) -> str:
    """傳給 gpg 的 --homedir／GNUPGHOME 值。MSYS 版把 C:\\... 當成相對路徑，所以要轉。"""
    return msys_path(folder) if info.msys else os.path.abspath(folder)


def _tool_data_dir() -> Path:
    """跟 libs/toolzoo/appdirs.tool_data_dir("encrypter") 同一個位置（Encrypter 不依賴 libs，所以照抄規則）。"""
    override = os.environ.get("TOOLZOO_DATA_DIR", "").strip()
    if override:
        return Path(override) / "encrypter"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parents[2] / "data"   # crypto_tool/pgpmode/_gpg.py → tools/encrypter/data


def home_bases() -> list[Path]:
    """暫時 home 的候選上層資料夾，前面的優先。

    1. ENCRYPTER_GPG_TMPDIR（有設時）
    2. 工具的 data 資料夾底下的 ``g/``（repo 規則：執行時資料放 data/）
    3. 系統暫存資料夾底下的 ``egpg/``——只在前兩個路徑太長（超過 MAX_HOME_LEN，見上方說明）或不能寫時才用
    """
    bases = []
    explicit = os.environ.get(ENV_TMPDIR, "").strip()
    if explicit:
        bases.append(Path(explicit))
    bases.append(_tool_data_dir() / "g")
    bases.append(Path(tempfile.gettempdir()) / "egpg")
    return bases


def _sweep_stale(base: Path) -> None:
    """清掉以前沒刪成功、超過一天的暫時 home（只動帶記號的資料夾）。"""
    try:
        entries = list(base.iterdir())
    except OSError:
        return
    now = time.time()
    for entry in entries:
        try:
            if (entry.is_dir() and (entry / _HOME_MARKER).is_file()
                    and now - entry.stat().st_mtime > _STALE_SECONDS):
                remove_tree(entry, attempts=2)
        except OSError:
            pass


def make_home(info: GpgInfo, length: int = HOME_LEN) -> tuple[Path, str]:
    """建一個新的、空的、名字隨機的 home（gpg 看到的路徑剛好 ``length`` 個字元）。回傳 (資料夾, 給 gpg 的路徑字串)。"""
    reasons = []
    for base in home_bases():
        # 資料夾名稱補長，讓整個 home 參數剛好 length 個字元（為什麼見檔案開頭 HOME_LEN 的說明）
        name_len = length - len(home_argument(info, base)) - 1
        if name_len < _MIN_NAME_LEN:
            reasons.append(f"{base}: 路徑太長")
            continue
        folder = base / secrets.token_hex((name_len + 1) // 2)[:name_len]
        arg = home_argument(info, folder)
        if len(arg) > MAX_HOME_LEN:
            reasons.append(f"{base}: 路徑太長")
            continue
        try:
            base.mkdir(parents=True, exist_ok=True)
            _sweep_stale(base)
            folder.mkdir(mode=0o700)
            (folder / _HOME_MARKER).write_bytes(b"")
        except OSError as exc:
            reasons.append(f"{base}: {type(exc).__name__}")
            continue
        return folder, arg
    raise SealError(
        "io_error", "找不到可以放 gpg 暫存資料的資料夾（路徑太長或沒有寫入權限）。",
        action=f"把環境變數 {ENV_TMPDIR} 設成一個路徑短、可寫入的資料夾，例如 C:\\gpgtmp。",
        detail="; ".join(reasons),
    )


def remove_tree(folder: Path, attempts: int = 8) -> bool:
    """刪資料夾；Windows 上檔案可能短暫被鎖住（agent 剛結束、防毒掃描），所以重試幾次。"""
    def _onerror(func, path, _exc):
        try:
            os.chmod(path, 0o700)
            func(path)
        except OSError:
            pass

    for i in range(attempts):
        if not folder.exists():
            return True
        try:
            shutil.rmtree(folder, onerror=_onerror)
        except OSError:
            pass
        if not folder.exists():
            return True
        time.sleep(0.15 * (i + 1))
    return not folder.exists()


# ---------------------------------------------------------------- 執行 gpg

def _base_env(home_arg: str) -> dict[str, str]:
    env = dict(os.environ)
    for name in ("GPG_AGENT_INFO", "GPG_TTY", "GNUPGHOME"):
        env.pop(name, None)
    env["GNUPGHOME"] = home_arg
    return env


def timeout_for(*paths: str | os.PathLike) -> float:
    """逾時：基本 120 秒，檔案大時依大小加長。"""
    total = 0
    for p in paths:
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return DEFAULT_TIMEOUT + total / _BYTES_PER_SECOND


def check_passphrase(value: str, what: str = "密語") -> None:
    if not isinstance(value, str) or not value:
        raise SealError("bad_input", f"{what}不能是空的。")
    if any(ch in value for ch in "\r\n\x00"):
        raise SealError("bad_input", f"{what}不能包含換行或 NUL 字元。",
                        action="換一個只有一行的密語。")


@dataclass
class GpgResult:
    returncode: int
    status: list[tuple[str, list[str]]] = field(default_factory=list)
    output: str = ""     # stdout 裡不是狀態行的部分（例如 --list-packets 的輸出）
    stderr: str = ""

    def has(self, keyword: str) -> bool:
        return any(k == keyword for k, _ in self.status)

    def args_of(self, keyword: str) -> list[list[str]]:
        return [a for k, a in self.status if k == keyword]

    def error_codes(self) -> list[tuple[str, int]]:
        """``ERROR <location> <code>`` 狀態行 → (位置, gpg-error 代碼的低 16 位元)。"""
        found = []
        for args in self.args_of("ERROR"):
            if len(args) >= 2:
                code = args[1].split("_", 1)[0]
                try:
                    found.append((args[0], int(code) & 0xFFFF))
                except ValueError:
                    pass
        return found

    def summary(self, secrets_to_hide: tuple[str, ...] = ()) -> str:
        """給 SealError.detail 用的摘要：狀態關鍵字＋stderr 最後幾行。不含明文與密語。"""
        keep = {"NO_SECKEY", "BADMDC", "DECRYPTION_FAILED", "NODATA", "INV_RECP", "IMPORT_PROBLEM",
                "MISSING_PASSPHRASE", "BAD_PASSPHRASE", "FAILURE", "ERROR", "KEY_NOT_CREATED",
                "NO_RECP", "UNEXPECTED", "DECRYPTION_INFO"}
        parts = [" ".join([k, *a]) for k, a in self.status if k in keep]
        tail = [line.strip() for line in self.stderr.splitlines() if line.strip()][-3:]
        text = f"gpg exit {self.returncode}; " + "; ".join(parts + tail)
        for value in secrets_to_hide:
            if value:
                text = text.replace(value, "***")
        return text[:600]


class GpgSession:
    """一次操作：一個暫時的專用 GNUPGHOME。用 ``with``，離開時一定 kill agent 並刪資料夾。"""

    def __init__(self, info: GpgInfo | None = None, *, home_len: int = HOME_LEN):
        self.info = info or find_gpg()
        self.home_len = home_len
        self.folder: Path | None = None
        self.home = ""
        self.env: dict[str, str] = {}
        self.cleanup_ok = True

    def __enter__(self) -> "GpgSession":
        self.folder, self.home = make_home(self.info, self.home_len)
        self.env = _base_env(self.home)
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def common_args(self) -> list[str]:
        args = [
            "--homedir", self.home,
            "--batch", "--no-tty", "--pinentry-mode", "loopback",
            "--trust-model", "always", "--no-auto-check-trustdb",
            "--disable-dirmngr", "--no-auto-key-retrieve", "--no-auto-key-locate",
            "--no-greeting", "--no-permission-warning",
            "--utf8-strings", "--display-charset", "utf-8",
            "--keyid-format", "long",
            "--status-fd", "1",
        ]
        if self.info.version_tuple >= (2, 2, 7):
            args.append("--no-symkey-cache")   # 密語不要留在 agent 的快取裡
        return args

    def run(self, args: list[str], *, passphrase: str | None = None,
            timeout: float = DEFAULT_TIMEOUT) -> GpgResult:
        """執行 gpg。``passphrase`` 不是 None 時走 ``--passphrase-fd 0``（stdin），不進命令列。"""
        if self.folder is None:
            raise RuntimeError("GpgSession is not open")
        argv = [self.info.path, *self.common_args()]
        stdin = b""
        if passphrase is not None:
            argv += ["--passphrase-fd", "0"]
            stdin = passphrase.encode("utf-8") + b"\n"
        argv += args
        try:
            proc = subprocess.run(
                argv, input=stdin, capture_output=True, timeout=timeout, env=self.env,
                cwd=str(self.folder), creationflags=_CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            raise SealError("io_error", "gpg 太久沒有回應，已經中止。",
                            action="確認檔案沒有被其他程式鎖住；檔案很大時請稍後再試。") from None
        except OSError as exc:
            raise SealError("dependency_missing", "無法執行 gpg。", action=_INSTALL_HINT,
                            detail=type(exc).__name__) from None
        status: list[tuple[str, list[str]]] = []
        other: list[str] = []
        for line in proc.stdout.decode("utf-8", "replace").splitlines():
            if line.startswith("[GNUPG:] "):
                fields = line[9:].split(" ")
                status.append((fields[0], fields[1:]))
            else:
                other.append(line)
        return GpgResult(proc.returncode, status, "\n".join(other),
                         proc.stderr.decode("utf-8", "replace"))

    def kill_agent(self) -> None:
        tools = []
        if self.info.gpgconf:
            tools.append([self.info.gpgconf, "--homedir", self.home, "--kill", "all"])
            if not self.info.msys:
                # 原生 Windows／Linux 的 gpg 可能把 socket 放在 home 外面（LOCALAPPDATA 或 /run/user）；
                # MSYS 版放在 home 裡（實測），不需要這一步。
                tools.append([self.info.gpgconf, "--homedir", self.home, "--remove-socketdir"])
        else:
            connect = Path(self.info.path).with_name(_exe("gpg-connect-agent"))
            if connect.is_file():
                tools.append([str(connect), "--homedir", self.home, "--no-autostart",
                              "KILLAGENT", "/bye"])
        for argv in tools:
            try:
                subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                               env=self.env, cwd=str(self.folder), creationflags=_CREATE_NO_WINDOW)
            except (OSError, subprocess.SubprocessError):
                pass

    def close(self) -> None:
        if self.folder is None:
            return
        try:
            self.kill_agent()
        finally:
            folder, self.folder = self.folder, None
            self.cleanup_ok = remove_tree(folder)
