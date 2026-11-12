"""CryptoTool Pro — entry point."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so `core` and `gui` resolve.
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# 帶了參數 = 命令列用法（encrypt／decrypt／info／keygen），不載入視窗相關套件。
_CLI = __name__ == "__main__" and len(sys.argv) > 1

if not _CLI:
    from gui.app import CryptoToolApp


def main():
    if _CLI:
        from sealed.cli import main as cli_main
        sys.exit(cli_main())
    app = CryptoToolApp()
    app.run()


if __name__ == "__main__":
    main()
