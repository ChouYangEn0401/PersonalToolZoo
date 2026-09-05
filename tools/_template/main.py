"""__TOOL_NAME__ —— 進入點。

打包後要讀外部資料檔，一律走 resource_path()，不要用相對路徑，
否則在 .exe 裡會找不到檔案（PyInstaller 會把資料解到 sys._MEIPASS）。
"""
import os
import sys
import tkinter as tk
from tkinter import ttk


def resource_path(*parts):
    """回傳打包後也正確的資料檔路徑。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("__TOOL_NAME__")
        self.root.geometry("900x600")

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="__TOOL_NAME__", font=("Segoe UI", 16, "bold")).pack(anchor="w")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
