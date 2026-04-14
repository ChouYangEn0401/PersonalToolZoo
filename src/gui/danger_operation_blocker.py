import tkinter as tk
from tkinter import ttk
import time
from src.core.language_manager import lm

# ==========================================
# ConfirmationManager (危險操作管理模組)
# ==========================================
class ConfirmationManager:
    def __init__(self, root):
        self.root = root
        self.danger_confirm_timestamp = 0

    def confirm(self, action_name, callback):
        """
        處理危險操作確認，包含 1 分鐘內免打擾邏輯
        :param action_name: 操作名稱 (顯示用)
        :param callback: 確認後要執行的函數
        :return: Boolean (是否執行)
        """
        current_time = time.time()

        # 檢查是否在 1 分鐘內
        if current_time - self.danger_confirm_timestamp < 60:
            if callback:
                callback()
            return True

        # 建立彈窗
        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.danger.title', default='⚠️ 危險操作確認'))
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # 置中
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        result = {'confirmed': False}
        no_ask_var = tk.BooleanVar()

        # UI 內容
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text=lm.t('dialog.danger.icon', default='⚠️'), font=("Arial", 32), foreground="red").pack(pady=10)
        ttk.Label(main_frame, text=lm.t('dialog.danger.prompt', default=f"確定要執行危險操作嗎？\n\n操作: {action_name}").format(action=action_name),
              font=("Arial", 11), justify="center").pack(pady=10)

        ttk.Checkbutton(main_frame, text=lm.t('dialog.danger.no_ask', default='1 分鐘內不再詢問'), variable=no_ask_var).pack(pady=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)

        def on_confirm():
            result['confirmed'] = True
            if no_ask_var.get():
                self.danger_confirm_timestamp = time.time()
            dialog.destroy()
            if callback:
                callback()

        def on_cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text=lm.t('dialog.danger.confirm_btn', default='✓ 確定執行'), command=on_confirm, width=12).pack(side="left", padx=5)
        ttk.Button(btn_frame, text=lm.t('dialog.danger.cancel_btn', default='✗ 取消'), command=on_cancel, width=12).pack(side="left", padx=5)

        self.root.wait_window(dialog)
        return result['confirmed']