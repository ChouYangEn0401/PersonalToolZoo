"""``python -m crypto_tool ...``（在 tools/encrypter 底下）或 ``python <路徑>/crypto_tool ...``。

只載入命令列需要的東西，不載入視窗相關套件。
"""

import sys
from pathlib import Path

_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)

from sealed.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
