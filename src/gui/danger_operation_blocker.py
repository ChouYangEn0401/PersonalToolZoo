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
        self.category_expiry = {} # {category: expiry_timestamp}

    def confirm(self, action_name, callback, category="default"):
        """
        處理危險操作確認，支援分類免打擾
        :param action_name: 操作名稱 (顯示用)
        :param callback: 確認後要執行的函數
        :param category: 操作分類 (例如: delete_branch, reset_hard)
        :return: Boolean (是否執行)
        """
        current_time = time.time()

        # 檢查該分類是否還在免打擾期間
        if category in self.category_expiry:
            if current_time < self.category_expiry[category]:
                if callback:
                    callback()
                return True
            else:
                # 已過期，移除
                del self.category_expiry[category]

        # 建立彈窗
        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t('dialog.danger.title', default='⚠️ 危險操作確認'))
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # 改進置中：相對於主視窗
        dialog.update_idletasks()
        pw, ph, px, py = self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{px + (pw // 2) - (dw // 2)}+{py + (ph // 2) - (dh // 2)}")

        result = {'confirmed': False}
        
        # 免打擾時長選項 (分鐘)
        # 1分/5分/15分/30分/重啟之前/永久
        duration_options = [
            ("1 " + lm.t('unit.minute', default='Min'), 60),
            ("5 " + lm.t('unit.minute', default='Min'), 300),
            ("15 " + lm.t('unit.minute', default='Min'), 900),
            ("30 " + lm.t('unit.minute', default='Min'), 1800),
            (lm.t('duration.until_restart', default='Until Restart'), -1),
            (lm.t('duration.permanent', default='Permanent'), -2)
        ]
        
        duration_var = tk.StringVar(value=duration_options[0][0])

        # UI 內容
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text=lm.t('dialog.danger.icon', default='⚠️'), font=("Arial", 32), foreground="red").pack(pady=10)
        ttk.Label(main_frame, text=lm.t('dialog.danger.prompt', default=f"確定要執行危險操作嗎？\n\n操作: {action_name}").format(action=action_name),
              font=("Arial", 11), justify="center").pack(pady=10)

        ttk.Label(main_frame, text=lm.t('dialog.danger.no_ask_hint', default='免打擾時長 (選中後此分類暫不詢問)：'), 
                  font=("Arial", 9)).pack(pady=(5, 2))
        
        duration_cb = ttk.Combobox(main_frame, textvariable=duration_var, 
                                   values=[opt[0] for opt in duration_options], state="readonly", width=20)
        duration_cb.pack(pady=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)

        def on_confirm():
            result['confirmed'] = True
            
            # 取得選中的秒數
            selected_text = duration_var.get()
            seconds = next((opt[1] for opt in duration_options if opt[0] == selected_text), 60)
            
            if seconds == -1: # Until Restart
                self.category_expiry[category] = time.time() + 999999999 # 模擬永久但僅限此次執行
            elif seconds == -2: # Permanent
                self.category_expiry[category] = time.time() + 9999999999 # 模擬永久 (實務上需存檔，但這裡先照做)
            else:
                self.category_expiry[category] = time.time() + seconds
                
            dialog.destroy()
            if callback:
                callback()

        def on_cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text=lm.t('dialog.danger.confirm_btn', default='✓ 確定執行'), command=on_confirm, width=12).pack(side="left", padx=5)
        ttk.Button(btn_frame, text=lm.t('dialog.danger.cancel_btn', default='✗ 取消'), command=on_cancel, width=12).pack(side="left", padx=5)

        self.root.wait_window(dialog)
        return result['confirmed']