"""新測試共用的小工具。只用標準庫的 unittest，不需要另外裝 pytest：

    .\\tools\\encrypter\\.venv\\Scripts\\python.exe -m unittest discover -s tools\\encrypter\\tests -v
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:   # 讓 `import crypto_tool...` 不管從哪個目錄執行都找得到
    sys.path.insert(0, str(TOOL_DIR))

from crypto_tool.sealed.errors import SealError  # noqa: E402

FAST = {"scrypt_log_n": 10}   # 只給測試用的低成本 scrypt


class Case(unittest.TestCase):
    """每個測試一個自己的暫存資料夾 ``self.tmp``，結束時刪掉。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="crypto-tool-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def code_of(self, func, *args, **kwargs) -> str:
        """呼叫應該失敗的函式，回傳錯誤代碼。"""
        with self.assertRaises(SealError) as caught:
            func(*args, **kwargs)
        return caught.exception.code

    def patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)
