"""Random Icon Maker —— 用種子產生 9 種演算法的隨機圖示，預覽後存成 ICO / PNG。

同一個種子永遠產生同一組圖（跟舊版的 GeneratedImageExporter.py 逐像素相同），
所以喜歡的圖示只要記下種子，之後隨時可以用別的尺寸重新產生。
"""

import os
import random
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from icon_algorithms import generate_all
from version import __version__

PREVIEW = 112              # 預覽格子的大小（放大顯示時用最近鄰，像素邊緣才清楚）
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def default_output() -> Path:
    return Path.home() / "Pictures" / "Random Icons"


def file_name(key: str, seed: int, ext: str) -> str:
    """跟舊版一樣的命名：[時間] algoN(種子).ico"""
    return f"[{datetime.now():%Y-%m-%d %H-%M-%S}] {key}({seed}).{ext}"


class IconMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Random Icon Maker v{__version__}")
        self.root.resizable(False, False)
        self.images = []        # [(key, name, PIL.Image)]
        self.photos = []        # 要留著參照，不然 Tk 會把圖回收掉
        self.checks = []
        self.seed = tk.StringVar(value=str(random.randint(-1000000, 1000000)))
        self.size = tk.StringVar(value="64")
        self.fmt = tk.StringVar(value="ICO")
        self.out = tk.StringVar(value=str(default_output()))
        self._build()
        self._generate()

    def _build(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="種子").pack(side="left")
        seed_entry = ttk.Entry(top, textvariable=self.seed, width=12)
        seed_entry.pack(side="left", padx=4)
        seed_entry.bind("<Return>", lambda _e: self._generate())
        ttk.Button(top, text="🎲 隨機", command=self._random_seed).pack(side="left")
        ttk.Label(top, text="尺寸").pack(side="left", padx=(16, 4))
        ttk.Combobox(top, textvariable=self.size, values=["32", "64", "128", "256"], width=5,
                     state="readonly").pack(side="left")
        ttk.Button(top, text="產生", command=self._generate).pack(side="left", padx=8)

        self.grid = ttk.Frame(self.root, padding=(10, 0))
        self.grid.pack()
        self.cells = []
        for i in range(9):
            cell = ttk.Frame(self.grid, padding=6)
            cell.grid(row=i // 3, column=i % 3)
            img = ttk.Label(cell)
            img.pack()
            var = tk.BooleanVar(value=True)
            chk = ttk.Checkbutton(cell, variable=var)
            chk.pack()
            self.cells.append((img, chk))
            self.checks.append(var)

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")
        ttk.Label(bottom, text="存到").grid(row=0, column=0, sticky="w")
        ttk.Entry(bottom, textvariable=self.out, width=40).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(bottom, text="…", width=3, command=self._pick_folder).grid(row=0, column=2)
        ttk.Button(bottom, text="開啟資料夾", command=self._open_folder).grid(row=0, column=3, padx=4)
        row = ttk.Frame(bottom)
        row.grid(row=1, column=0, columnspan=4, sticky="we", pady=(8, 0))
        ttk.Label(row, text="格式").pack(side="left")
        ttk.Combobox(row, textvariable=self.fmt, values=["ICO", "PNG"], width=5, state="readonly").pack(side="left", padx=4)
        ttk.Label(row, text="（ICO 會內含 16–256 的多種尺寸）", foreground="#777").pack(side="left")
        ttk.Button(row, text="全部儲存", command=lambda: self._save(all_=True)).pack(side="right")
        ttk.Button(row, text="儲存勾選的", command=self._save).pack(side="right", padx=6)
        bottom.columnconfigure(1, weight=1)

    def _random_seed(self):
        self.seed.set(str(random.randint(-1000000, 1000000)))
        self._generate()

    def _seed_value(self):
        try:
            seed = int(self.seed.get().strip())
        except ValueError:
            messagebox.showwarning("種子不正確", "種子要是整數，例如 596481。")
            return None
        if not -1000000 <= seed <= 1000000:
            messagebox.showwarning("種子不正確", "種子範圍是 -1000000 到 1000000。")
            return None
        return seed

    def _generate(self):
        seed = self._seed_value()
        if seed is None:
            return
        self.images = generate_all(seed, int(self.size.get()))
        self.photos = []
        for (img_label, chk), (key, name, img) in zip(self.cells, self.images):
            preview = img.resize((PREVIEW, PREVIEW), Image.NEAREST)
            photo = ImageTk.PhotoImage(preview)
            self.photos.append(photo)
            img_label.configure(image=photo)
            chk.configure(text=f"{key}　{name}")

    def _pick_folder(self):
        folder = filedialog.askdirectory(initialdir=self.out.get() or None)
        if folder:
            self.out.set(folder)

    def _open_folder(self):
        folder = Path(self.out.get())
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _save(self, all_=False):
        seed = self._seed_value()
        if seed is None or not self.images:
            return
        picked = [item for item, var in zip(self.images, self.checks) if all_ or var.get()]
        if not picked:
            messagebox.showinfo("沒有勾選", "先勾選要儲存的圖示。")
            return
        folder = Path(self.out.get())
        folder.mkdir(parents=True, exist_ok=True)
        ext = self.fmt.get().lower()
        size = int(self.size.get())
        for key, _name, img in picked:
            path = folder / file_name(key, seed, ext)
            if ext == "ico":
                img.save(path, format="ICO", sizes=[s for s in ICO_SIZES if s[0] <= size])
            else:
                img.save(path, format="PNG")
        messagebox.showinfo("已儲存", f"存了 {len(picked)} 個圖示到\n{folder}")


def main():
    root = tk.Tk()
    IconMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
