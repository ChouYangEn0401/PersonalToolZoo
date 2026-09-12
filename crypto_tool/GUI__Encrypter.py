"""CryptoTool Pro — entry point."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so `core` and `gui` resolve.
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from gui.app import CryptoToolApp


def main():
    app = CryptoToolApp()
    app.run()


if __name__ == "__main__":
    main()
