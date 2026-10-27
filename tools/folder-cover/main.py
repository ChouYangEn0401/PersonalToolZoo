import os
import tkinter as tk
from tkinter import filedialog, Listbox, messagebox
from pathlib import Path
import shutil
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image


GLOBAL_SELECTED_FOLDER = None
GLOBAL_SELECTED_FOLDER_INDEX = -1
GLOBAL_SELECTED_IMAGE = None


def select_folder(folder_path=None):
    if folder_path is None:
        folder_path = filedialog.askdirectory()
    if folder_path and folder_path not in folder_list.get(0, tk.END):
        folder_list.insert(tk.END, folder_path)


def on_folder_select(event):
    global GLOBAL_SELECTED_FOLDER, GLOBAL_SELECTED_FOLDER_INDEX
    selected = folder_list.curselection()
    if not selected:
        return
    GLOBAL_SELECTED_FOLDER = folder_list.get(selected[0])
    GLOBAL_SELECTED_FOLDER_INDEX = selected[0]

    image_list.delete(0, tk.END)
    for file in os.listdir(GLOBAL_SELECTED_FOLDER):
        if file.lower().endswith((".png", ".jpg", ".jpeg")):
            image_list.insert(tk.END, file)

def create_icon(image_path, icon_path):
    """將圖片轉換為 .ico 格式並儲存"""
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGBA")  # 確保圖像是 RGBA 格式
            img.save(icon_path, format="ICO")
            print(f"Icon saved at {icon_path}")
    except Exception as e:
        print(f"Error creating icon: {e}")

def set_cover_image():
    global GLOBAL_SELECTED_FOLDER, GLOBAL_SELECTED_FOLDER_INDEX
    # selected_folder = folder_list.curselection()
    selected_image = image_list.curselection()
    if not GLOBAL_SELECTED_FOLDER or not selected_image:
        return

    # folder_path = folder_list.get(selected_folder[0])
    image_name = image_list.get(selected_image[0])
    image_path = GLOBAL_SELECTED_FOLDER + "/" + image_name
    icon_path = GLOBAL_SELECTED_FOLDER + "/" + "cover-image.ico"
    create_icon(image_path, icon_path)

    desktop_ini = os.path.join(GLOBAL_SELECTED_FOLDER, "desktop.ini")
    try:
        with open(desktop_ini, "w") as f:
            f.write("[.ShellClassInfo]\n")
            f.write(f"IconResource={icon_path},0\n")

        # os.system(f"attrib +h +s \"{desktop_ini}\"")
        os.system(f"attrib +s \"{desktop_ini}\"")
        os.system(f"attrib +s \"{GLOBAL_SELECTED_FOLDER}\"")
        messagebox.showinfo("Success", "Folder cover image set successfully!")
    except Exception as e:
        error_list.insert(tk.END, GLOBAL_SELECTED_FOLDER)
        messagebox.showerror("Error", f"Failed to set cover image: {str(e)}")

    # 移除已處理的資料夾並選擇下一個
    folder_list.delete(GLOBAL_SELECTED_FOLDER_INDEX)
    image_list.delete(0, tk.END)
    GLOBAL_SELECTED_FOLDER = None
    GLOBAL_SELECTED_FOLDER_INDEX = -1
    # if folder_list.size() > 0:
    #     folder_list.select_set(0)
    #     on_folder_select(None)


def on_drop(event):
    folder_path = event.data.strip().strip('{').strip('}')
    if os.path.isdir(folder_path):
        select_folder(folder_path)


root = TkinterDnD.Tk()
root.title("Folder Cover Setter")
root.geometry("600x400")

frame_left = tk.Frame(root)
frame_left.pack(side=tk.LEFT, fill=tk.Y)
frame_middle = tk.Frame(root)
frame_middle.pack(side=tk.LEFT, fill=tk.Y)
frame_right = tk.Frame(root)
frame_right.pack(side=tk.LEFT, fill=tk.Y)

folder_list = Listbox(frame_left, width=30)
folder_list.pack()
folder_list.bind("<<ListboxSelect>>", on_folder_select)
folder_list.drop_target_register(DND_FILES)
folder_list.dnd_bind('<<Drop>>', on_drop)

btn_add_folder = tk.Button(frame_left, text="Add Folder", command=select_folder)
btn_add_folder.pack()

image_list = Listbox(frame_middle, width=30)
image_list.pack()

btn_set_cover = tk.Button(frame_middle, text="Set Cover Image", command=set_cover_image)
btn_set_cover.pack()

error_list = Listbox(frame_right, width=30)
error_list.pack()

tk.Label(frame_right, text="Failed Folders").pack()

root.mainloop()
