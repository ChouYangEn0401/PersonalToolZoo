"""PGP 模式：呼叫系統上的 gpg（GnuPG 2.2 以上）產生與解開**標準 OpenPGP** 檔案（.gpg／.asc）。

跟 ``core/pgp.py``（舊版、不是 OpenPGP）無關。支援多收件人（同一份密文、任一把私鑰都能解，
也就是「萬用鎖」）以及「收件人＋密語」並存。每次操作用一個暫時的專用 GNUPGHOME，
不碰使用者自己的金鑰環。說明見 ``docs/pgp-mode.md``。

錯誤一律是 ``SealError``（跟 sealed 共用同一組代碼）。
"""

from ._gpg import ENV_GPG, ENV_TMPDIR, MIN_VERSION, GpgInfo, find_gpg
from .ops import (
    KEY_TYPES, decrypt_file, encrypt_file, generate_keypair, inspect, is_pgp, pgp_kind,
)

__all__ = [
    "ENV_GPG", "ENV_TMPDIR", "MIN_VERSION", "GpgInfo", "KEY_TYPES",
    "find_gpg", "is_pgp", "pgp_kind", "generate_keypair", "encrypt_file", "decrypt_file", "inspect",
]
