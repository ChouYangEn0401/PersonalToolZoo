import tkinter as tk
from remake.M2E1.GUI_ExcelFastEditor.ui import ExcelEditorUI

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1400x800")
    app = ExcelEditorUI(root)
    root.mainloop()