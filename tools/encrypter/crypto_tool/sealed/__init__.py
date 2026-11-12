"""ISD2：這個工具現行的加密方式（標準認證加密）。

跟 ``core/``（舊版 .isd、Mixture）完全分開：這裡只依賴 ``cryptography``，不 import ``core``。
套件內部一律用相對 import，所以不管是 ``crypto_tool.sealed`` 還是把 ``crypto_tool/`` 放進
``sys.path`` 後的 ``sealed`` 都能用。
"""

from .container import EXTENSION, KeyMaterial
from .errors import SealError
from .keys import (
    generate_key_file, load_key_env, load_key_file, passphrase_material, parse_secret_value,
)
from .ops import (
    decrypt_path, default_decrypt_output, default_encrypt_output, encrypt_path, info_path,
)

__all__ = [
    "EXTENSION", "KeyMaterial", "SealError",
    "generate_key_file", "load_key_env", "load_key_file", "passphrase_material",
    "parse_secret_value", "decrypt_path", "default_decrypt_output",
    "default_encrypt_output", "encrypt_path", "info_path",
]
