"""Folder Cover —— 把資料夾在檔案總管裡的圖示換成裡面的一張圖（相簿、漫畫、影集資料夾一眼就認得）。

前身是 Python Projects\\Change Folder Cover (failes)。做法與失敗原因見 cover.py；這裡只有畫面。
"""

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

import cover
from version import __version__

PREVIEW = 160


class FolderCoverApp:
    def __init__(self, root, confirm=messagebox.askyesno, notify=messagebox.showinfo):
        self.root = root
        self.confirm = confirm
        self.notify = notify
        root.title(f"Folder Cover v{__version__}")
        root.geometry("1000x600")
        root.minsize(820, 480)
        self.folders: list[Path] = []
        self.choice: dict[str, Path] = {}       # 資料夾 → 選的圖片
        self.images: list[Path] = []
        self.mode = tk.StringVar(value=cover.MODE_CROP)
        self._preview_img = None
        self._build()
        root.drop_target_register(DND_FILES)
        root.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------------------ 畫面
    def _build(self):
        top = ttk.Frame(self.root, padding=(10, 10, 10, 0))
        top.pack(fill="x")
        ttk.Button(top, text="＋ 加入資料夾", command=self._browse).pack(side="left")
        ttk.Button(top, text="移除選取", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(top, text="清空", command=self.clear).pack(side="left")
        ttk.Label(top, text="（也可以把資料夾拖進來；把圖片拖進來就是選它當目前資料夾的封面）",
                  foreground="#777").pack(side="left", padx=10)

        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(left, columns=("folder", "current", "status"), show="headings", selectmode="browse")
        for col, text, width in (("folder", "資料夾", 300), ("current", "目前圖示", 110), ("status", "狀態", 200)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.tag_configure("bad", foreground="#c62828")
        self.tree.tag_configure("ok", foreground="#2e7d32")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_folder())

        right = ttk.LabelFrame(body, text="封面", padding=10)
        right.pack(side="left", fill="y", padx=(10, 0))
        self.folder_label = ttk.Label(right, text="（先在左邊選一個資料夾）", wraplength=300)
        self.folder_label.pack(anchor="w")
        ttk.Label(right, text="資料夾裡的圖片").pack(anchor="w", pady=(8, 2))
        self.image_list = tk.Listbox(right, height=8, width=40, exportselection=False)
        self.image_list.pack(fill="x")
        self.image_list.bind("<<ListboxSelect>>", lambda _e: self._pick_from_list())
        ttk.Button(right, text="選其他圖片…", command=self._browse_image).pack(anchor="w", pady=(6, 0))

        self.preview = tk.Canvas(right, width=PREVIEW, height=PREVIEW, highlightthickness=1,
                                 highlightbackground="#bbb", background="#f4f4f4")
        self.preview.pack(pady=8)
        ttk.Radiobutton(right, text="裁成正方形（取中間）", value=cover.MODE_CROP, variable=self.mode,
                        command=self._update_preview).pack(anchor="w")
        ttk.Radiobutton(right, text="整張保留（旁邊補透明）", value=cover.MODE_FIT, variable=self.mode,
                        command=self._update_preview).pack(anchor="w")
        ttk.Button(right, text="設成這個資料夾的封面", command=self.apply_selected).pack(fill="x", pady=(10, 2))
        ttk.Button(right, text="移除封面（恢復預設圖示）", command=self.remove_selected_cover).pack(fill="x")

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="每個資料夾自動套用（用選好的圖；沒選的用 cover／folder 開頭或第一張圖）",
                   command=self.apply_all).pack(side="left")
        self.summary = ttk.Label(bottom, text="")
        self.summary.pack(side="right")

    # ------------------------------------------------------------------ 資料夾清單
    def add_folders(self, paths):
        known = {os.path.normcase(str(p)) for p in self.folders}
        for p in paths:
            p = Path(p)
            if p.is_dir() and os.path.normcase(str(p)) not in known:
                self.folders.append(p)
                known.add(os.path.normcase(str(p)))
                self.tree.insert("", "end", iid=str(len(self.folders) - 1),
                                 values=(str(p), self._current_label(p), ""))
        if self.folders and not self.tree.selection():
            self.tree.selection_set("0")
            self._show_folder()
        self._update_summary()

    def _current_label(self, folder: Path) -> str:
        try:
            return "自訂" if cover.current_cover(folder) else "預設"
        except OSError:
            return "?"

    def _browse(self):
        folder = filedialog.askdirectory(title="選擇要換封面的資料夾")
        if folder:
            self.add_folders([folder])

    def _on_drop(self, event):
        paths = [Path(p) for p in self.root.tk.splitlist(event.data)]
        images = [p for p in paths if p.is_file() and p.suffix.lower() in cover.IMAGE_EXTS]
        self.add_folders([p for p in paths if p.is_dir()])
        folder = self._selected_folder()
        if images and folder is not None:
            self.choice[str(folder)] = images[0]
            self._show_folder()

    def _remove_selected(self):
        index = self._selected_index()
        if index is None:
            return
        folder = self.folders.pop(index)
        self.choice.pop(str(folder), None)
        self._rebuild_tree()

    def clear(self):
        self.folders, self.choice = [], {}
        self._rebuild_tree()

    def _rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, folder in enumerate(self.folders):
            self.tree.insert("", "end", iid=str(i), values=(str(folder), self._current_label(folder), ""))
        if self.folders:
            self.tree.selection_set("0")
        self._show_folder()
        self._update_summary()

    def _selected_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _selected_folder(self):
        index = self._selected_index()
        return self.folders[index] if index is not None else None

    # ------------------------------------------------------------------ 圖片與預覽
    def _show_folder(self):
        folder = self._selected_folder()
        self.image_list.delete(0, "end")
        if folder is None:
            self.folder_label.configure(text="（先在左邊選一個資料夾）")
            self.images = []
            self._update_preview()
            return
        self.folder_label.configure(text=str(folder))
        self.images = cover.find_images(folder)
        chosen = self.choice.get(str(folder))
        if chosen and chosen not in self.images:
            self.images.insert(0, chosen)          # 從別的地方選的圖也列出來
        for img in self.images:
            self.image_list.insert("end", img.name if img.parent == folder else str(img))
        if self.images:
            index = self.images.index(chosen) if chosen in self.images else 0
            self.image_list.selection_set(index)
            self.choice.setdefault(str(folder), self.images[index])
        self._update_preview()

    def _pick_from_list(self):
        folder = self._selected_folder()
        sel = self.image_list.curselection()
        if folder is not None and sel:
            self.choice[str(folder)] = self.images[sel[0]]
            self._update_preview()

    def _browse_image(self):
        folder = self._selected_folder()
        if folder is None:
            return
        path = filedialog.askopenfilename(title="選擇封面圖片", initialdir=str(folder),
                                          filetypes=[("圖片", " ".join(f"*{e}" for e in cover.IMAGE_EXTS))])
        if path:
            self.choice[str(folder)] = Path(path)
            self._show_folder()

    def _update_preview(self):
        self.preview.delete("all")
        folder = self._selected_folder()
        image = self.choice.get(str(folder)) if folder is not None else None
        if not image:
            self.preview.create_text(PREVIEW // 2, PREVIEW // 2, text="沒有圖片", fill="#888")
            return
        try:
            sq = cover.load_square(image, self.mode.get()).resize((PREVIEW, PREVIEW))
        except OSError as exc:
            self.preview.create_text(PREVIEW // 2, PREVIEW // 2, text=f"讀不到圖片\n{exc}", fill="#c62828",
                                     width=PREVIEW - 10)
            return
        self._preview_img = ImageTk.PhotoImage(sq)
        self.preview.create_image(0, 0, anchor="nw", image=self._preview_img)

    # ------------------------------------------------------------------ 套用
    def _set_status(self, index, text, tag=""):
        folder = self.folders[index]
        self.tree.item(str(index), values=(str(folder), self._current_label(folder), text), tags=(tag,) if tag else ())

    def _apply_one(self, index, image):
        try:
            cover.apply_cover(self.folders[index], image, self.mode.get())
            self._set_status(index, f"✓ 已套用 {image.name}", "ok")
            return True
        except (OSError, ValueError) as exc:
            self._set_status(index, f"失敗：{exc}", "bad")
            return False

    def apply_selected(self):
        index = self._selected_index()
        if index is None:
            return
        image = self.choice.get(str(self.folders[index]))
        if not image:
            self.notify("沒有圖片", "這個資料夾裡沒有圖片，請按「選其他圖片…」。")
            return
        self._apply_one(index, image)
        self._update_summary()

    def apply_all(self):
        if not self.folders:
            return
        if not self.confirm("自動套用", f"要幫 {len(self.folders)} 個資料夾換封面嗎？"):
            return
        done = 0
        for i, folder in enumerate(self.folders):
            image = self.choice.get(str(folder)) or next(iter(cover.find_images(folder)), None)
            if image is None:
                self._set_status(i, "沒有圖片，略過", "bad")
                continue
            done += self._apply_one(i, image)
        self._update_summary(f"套用了 {done} 個資料夾")

    def remove_selected_cover(self):
        index = self._selected_index()
        if index is None:
            return
        try:
            cover.remove_cover(self.folders[index])
            self._set_status(index, "已恢復預設圖示", "ok")
        except OSError as exc:
            self._set_status(index, f"失敗：{exc}", "bad")
        self._update_summary()

    def _update_summary(self, text=""):
        self.summary.configure(text=text or f"{len(self.folders)} 個資料夾")


def main():
    if sys.platform != "win32":
        print("Folder Cover 只支援 Windows")
        return
    root = TkinterDnD.Tk()
    FolderCoverApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
