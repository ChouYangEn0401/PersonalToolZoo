"""
danger_operation_blocker — Per-type danger confirmation dialogs
===============================================================
Each dangerous operation type (rebase, reset, delete_branch, force_push)
has its own confirmation dialog with:
  - Specific warning text
  - A Combobox to choose how long to skip the dialog (1/5/15/30 minutes)
  - Dialog centred on the parent root window (not the screen)
  - Individual bypass timestamps so types don't share the timer
"""

import tkinter as tk
from tkinter import ttk
import time
from src.core.language_manager import lm

# ─── time option mapping ─────────────────────────────────────────────────────
_TIME_KEYS = [
    "dialog.danger.time_1min",
    "dialog.danger.time_5min",
    "dialog.danger.time_15min",
    "dialog.danger.time_30min",
]
_TIME_SECS = [60, 300, 900, 1800]


def _time_options():
    return [lm.t(k, default=k.split(".")[-1]) for k in _TIME_KEYS]


def _secs_for_index(idx: int) -> int:
    return _TIME_SECS[idx] if 0 <= idx < len(_TIME_SECS) else 60


# ==========================================
# ConfirmationManager (危險操作管理模組)
# ==========================================
class ConfirmationManager:
    def __init__(self, root):
        self.root = root
        # Generic bypass (kept for backward compat with confirm())
        self._generic_ts: float = 0
        self._generic_bypass_secs: int = 60
        # Per-type bypass data: {op_type: {'ts': float, 'secs': int}}
        self._typed: dict = {}

    # ── Helpers ────────────────────────────────────────────────────────────
    def _centre_on_root(self, dialog: tk.Toplevel, w: int, h: int):
        dialog.update_idletasks()
        rx = self.root.winfo_rootx()
        ry = self.root.winfo_rooty()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        x = rx + (rw - w) // 2
        y = ry + (rh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _bypass_active(self, op_type: str) -> bool:
        entry = self._typed.get(op_type)
        if entry is None:
            return False
        return (time.time() - entry["ts"]) < entry["secs"]

    def _record_bypass(self, op_type: str, secs: int):
        self._typed[op_type] = {"ts": time.time(), "secs": secs}

    def _typed_confirm(self, op_type, title, warn_text, action_name, callback) -> bool:
        if self._bypass_active(op_type):
            if callback:
                callback()
            return True

        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        self._centre_on_root(dialog, 440, 310)

        result = {"confirmed": False}
        main = ttk.Frame(dialog, padding=18)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="⚠️", font=("Arial", 26), foreground="#cc4400").pack()
        ttk.Label(
            main, text=warn_text, font=("Arial", 10),
            justify="center", wraplength=400,
        ).pack(pady=6)

        op_frame = ttk.Frame(main)
        op_frame.pack(fill="x", pady=(2, 4))
        ttk.Label(op_frame,
                  text=lm.t("dialog.danger.operation_label", default="操作："),
                  font=("Arial", 10, "bold")).pack(side="left")
        ttk.Label(op_frame, text=action_name, font=("Arial", 10)).pack(side="left")

        time_frame = ttk.Frame(main)
        time_frame.pack(fill="x", pady=(2, 6))
        ttk.Label(time_frame,
                  text=lm.t("dialog.danger.time_label", default="確認後暫時跳過："),
                  font=("Arial", 9)).pack(side="left", padx=(0, 6))
        time_var = tk.StringVar()
        opts = _time_options()
        time_var.set(opts[0])
        ttk.Combobox(time_frame, textvariable=time_var, values=opts,
                     state="readonly", width=10).pack(side="left")

        btn_frame = ttk.Frame(main)
        btn_frame.pack(pady=4)

        def on_confirm():
            result["confirmed"] = True
            idx = opts.index(time_var.get()) if time_var.get() in opts else 0
            self._record_bypass(op_type, _secs_for_index(idx))
            dialog.destroy()
            if callback:
                callback()

        def on_cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text=lm.t("dialog.danger.confirm_btn", default="✓ 確定執行"),
                   command=on_confirm, width=14).pack(side="left", padx=5)
        ttk.Button(btn_frame, text=lm.t("dialog.danger.cancel_btn", default="✗ 取消"),
                   command=on_cancel, width=10).pack(side="left", padx=5)

        dialog.bind("<Return>", lambda e: on_confirm())
        dialog.bind("<Escape>", lambda e: on_cancel())
        self.root.wait_window(dialog)
        return result["confirmed"]

    # ── Typed public methods ───────────────────────────────────────────────
    def confirm_rebase(self, action_name: str, callback) -> bool:
        return self._typed_confirm(
            "rebase",
            lm.t("dialog.danger.rebase_title", default="⚠️ Rebase 危險操作確認"),
            lm.t("dialog.danger.rebase_warn",
                 default="Rebase 將重寫提交歷史，此操作難以完全撤銷。\n確保你了解影響範圍，且遠端尚未有其他人使用此分支。"),
            action_name, callback,
        )

    def confirm_reset(self, action_name: str, callback) -> bool:
        return self._typed_confirm(
            "reset",
            lm.t("dialog.danger.reset_title", default="⚠️ Reset 危險操作確認"),
            lm.t("dialog.danger.reset_warn",
                 default="Hard Reset 將永久丟棄所有未提交的工作區變更與暫存內容。\n此操作無法撤銷，請確認你已備份重要資料。"),
            action_name, callback,
        )

    def confirm_delete_branch(self, action_name: str, callback) -> bool:
        return self._typed_confirm(
            "delete_branch",
            lm.t("dialog.danger.delete_branch_title", default="⚠️ 刪除分支確認"),
            lm.t("dialog.danger.delete_branch_warn",
                 default="刪除分支後，相關的提交記錄可能難以找回。\n請確認分支不再需要或已合併至目標分支。"),
            action_name, callback,
        )

    def confirm_force_push(self, action_name: str, callback) -> bool:
        return self._typed_confirm(
            "force_push",
            lm.t("dialog.danger.force_push_title", default="⚠️ Force Push 確認"),
            lm.t("dialog.danger.force_push_warn",
                 default="Force Push 將強制覆蓋遠端提交歷史，可能使其他協作者的本地分支失效。\n建議優先使用 --force-with-lease 以降低風險。"),
            action_name, callback,
        )

    # ── Generic confirm (backward compatible) ─────────────────────────────
    def confirm(self, action_name: str, callback) -> bool:
        """Generic danger confirmation (shared timer). Kept for backward compat."""
        if (time.time() - self._generic_ts) < self._generic_bypass_secs:
            if callback:
                callback()
            return True

        dialog = tk.Toplevel(self.root)
        dialog.title(lm.t("dialog.danger.title", default="⚠️ 危險操作確認"))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        self._centre_on_root(dialog, 420, 280)

        result = {"confirmed": False}
        main = ttk.Frame(dialog, padding=20)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text=lm.t("dialog.danger.icon", default="⚠️"),
                  font=("Arial", 30), foreground="red").pack(pady=6)
        ttk.Label(
            main,
            text=lm.t("dialog.danger.prompt",
                       default="確定要執行危險操作嗎？\n\n操作: {action}",
                       action=action_name),
            font=("Arial", 11), justify="center", wraplength=380,
        ).pack(pady=8)

        time_frame = ttk.Frame(main)
        time_frame.pack(fill="x", pady=(2, 6))
        ttk.Label(time_frame,
                  text=lm.t("dialog.danger.time_label", default="確認後暫時跳過："),
                  font=("Arial", 9)).pack(side="left", padx=(0, 6))
        time_var = tk.StringVar()
        opts = _time_options()
        time_var.set(opts[0])
        ttk.Combobox(time_frame, textvariable=time_var, values=opts,
                     state="readonly", width=10).pack(side="left")

        btn_frame = ttk.Frame(main)
        btn_frame.pack(pady=8)

        def on_confirm():
            result["confirmed"] = True
            idx = opts.index(time_var.get()) if time_var.get() in opts else 0
            self._generic_ts = time.time()
            self._generic_bypass_secs = _secs_for_index(idx)
            dialog.destroy()
            if callback:
                callback()

        def on_cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text=lm.t("dialog.danger.confirm_btn", default="✓ 確定執行"),
                   command=on_confirm, width=14).pack(side="left", padx=5)
        ttk.Button(btn_frame, text=lm.t("dialog.danger.cancel_btn", default="✗ 取消"),
                   command=on_cancel, width=10).pack(side="left", padx=5)

        dialog.bind("<Return>", lambda e: on_confirm())
        dialog.bind("<Escape>", lambda e: on_cancel())
        self.root.wait_window(dialog)
        return result["confirmed"]