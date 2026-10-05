"""Video Notes —— 進入點。

    VideoNotes                → 開 GUI（本機網頁，會自動開瀏覽器）
    VideoNotes <網址> [選項]   → CLI（VideoNotes --help 看全部選項）
"""

import os
import sys

# 從原始碼執行時讓 import 找得到 repo 的 libs/（打包時由 tool.json 的 pathex 處理）
_LIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs")
if not getattr(sys, "frozen", False) and os.path.isdir(_LIBS):
    sys.path.insert(0, os.path.abspath(_LIBS))


def main() -> None:
    args = sys.argv[1:]
    if args and args != ["--gui"]:
        from video_notes.cli import main as cli_main

        sys.exit(cli_main(args))

    from video_notes.web.server import run_gui

    run_gui()


if __name__ == "__main__":
    main()
