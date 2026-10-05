#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 Downloader Pro - Full Featured Version
支援自動合併、持久化、任務恢復、詳細日誌
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import requests
import os
import queue
import threading
import subprocess
import time
import json
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime
from enum import Enum
import platform


class TaskStatus(Enum):
    """任務狀態枚舉"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    MERGING = "merging"
    M3U8_INVALID = "m3u8_invalid"


class DownloadTask:
    """下載任務類別"""

    def __init__(self, task_id, name, ts_list, output_dir, workers=5, m3u8_url=""):
        self.task_id = task_id
        self.name = name
        self.ts_list = ts_list
        self.output_dir = output_dir
        self.temp_dir = os.path.join(output_dir, f"{name}_temp")
        self.output_file = os.path.join(output_dir, f"{name}.mkv")
        self.m3u8_url = m3u8_url

        # 下載狀態
        self.status = TaskStatus.PENDING
        self.total_count = len(ts_list)
        self.downloaded_count = 0
        self.failed_count = 0
        self.workers = workers

        # 任務控制
        self.download_queue = queue.Queue()
        self.worker_threads = []
        self.is_running = False
        self.pause_event = threading.Event()
        self.pause_event.set()

        # 下載記錄
        self.downloaded_segments = set()
        self.failed_segments = []
        self.progress_file = os.path.join(self.temp_dir, "progress.json")
        self.task_state_file = os.path.join(self.temp_dir, "task_state.json")

        # 日誌
        self.logs = []
        self.max_logs = 1000

        # 網路錯誤計數
        self.consecutive_failures = 0
        self.max_consecutive_failures = 10

        # 自動合併標記
        self.auto_merge_enabled = True
        self.merge_attempted = False

        # 創建臨時目錄並載入進度
        os.makedirs(self.temp_dir, exist_ok=True)
        self.load_progress()

    def add_log(self, message, level="INFO"):
        """添加日誌"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message
        }
        self.logs.append(log_entry)

        # 限制日誌數量
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]

    def load_progress(self):
        """載入下載進度（斷點續傳）"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.downloaded_segments = set(data.get('downloaded', []))
                    self.downloaded_count = len(self.downloaded_segments)
                    self.failed_segments = data.get('failed', [])
                    self.failed_count = len(self.failed_segments)
                    self.consecutive_failures = data.get('consecutive_failures', 0)
                    self.merge_attempted = data.get('merge_attempted', False)

                    # 載入日誌
                    if 'logs' in data:
                        self.logs = data['logs']

                    self.add_log(f"已載入進度: {self.downloaded_count}/{self.total_count} 片段", "INFO")
            except Exception as e:
                self.add_log(f"載入進度失敗: {e}", "ERROR")

    def save_progress(self):
        """保存下載進度"""
        try:
            data = {
                'downloaded': list(self.downloaded_segments),
                'failed': self.failed_segments,
                'total': self.total_count,
                'consecutive_failures': self.consecutive_failures,
                'merge_attempted': self.merge_attempted,
                'logs': self.logs[-500:],  # 只保存最近 500 條日誌
                'timestamp': datetime.now().isoformat()
            }
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.add_log(f"保存進度失敗: {e}", "ERROR")

    def save_task_state(self):
        """保存任務狀態（用於恢復）"""
        try:
            state = {
                'task_id': self.task_id,
                'name': self.name,
                'ts_list': self.ts_list,
                'output_dir': self.output_dir,
                'workers': self.workers,
                'm3u8_url': self.m3u8_url,
                'status': self.status.value,
                'timestamp': datetime.now().isoformat()
            }
            with open(self.task_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.add_log(f"保存任務狀態失敗: {e}", "ERROR")

    @staticmethod
    def load_task_from_state(state_file):
        """從狀態文件恢復任務"""
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            task = DownloadTask(
                task_id=state['task_id'],
                name=state['name'],
                ts_list=state['ts_list'],
                output_dir=state['output_dir'],
                workers=state.get('workers', 5),
                m3u8_url=state.get('m3u8_url', '')
            )

            # 恢復狀態
            status_value = state.get('status', 'paused')
            try:
                task.status = TaskStatus(status_value)
                # 如果之前是下載中，恢復為暫停狀態
                if task.status == TaskStatus.DOWNLOADING:
                    task.status = TaskStatus.PAUSED
            except ValueError:
                task.status = TaskStatus.PAUSED

            return task
        except Exception as e:
            print(f"載入任務狀態失敗: {e}")
            return None

    def get_progress_percentage(self):
        """獲取進度百分比"""
        return (self.downloaded_count / self.total_count * 100) if self.total_count > 0 else 0

    def start(self):
        """啟動下載任務"""
        if self.is_running:
            return

        self.is_running = True
        self.status = TaskStatus.DOWNLOADING
        self.pause_event.set()
        self.save_task_state()

        self.add_log(f"開始下載，使用 {self.workers} 個 Worker", "INFO")

        # 填充下載佇列（跳過已下載的）
        pending_count = 0
        for i, ts_url in enumerate(self.ts_list):
            if i not in self.downloaded_segments:
                self.download_queue.put((i, ts_url))
                pending_count += 1

        self.add_log(f"待下載片段: {pending_count} 個", "INFO")

        # 啟動 Worker
        self.worker_threads = []
        for _ in range(self.workers):
            thread = threading.Thread(target=self._download_worker, daemon=True)
            thread.start()
            self.worker_threads.append(thread)

        # 啟動監控線程
        threading.Thread(target=self._monitor_completion, daemon=True).start()

    def pause(self):
        """暫停下載"""
        self.status = TaskStatus.PAUSED
        self.pause_event.clear()
        self.save_progress()
        self.save_task_state()
        self.add_log("任務已暫停", "WARNING")

    def resume(self):
        """繼續下載"""
        if self.status == TaskStatus.PAUSED:
            self.status = TaskStatus.DOWNLOADING
            self.pause_event.set()
            self.save_task_state()
            self.add_log("任務已繼續", "INFO")

    def stop(self):
        """停止下載（完全停止）"""
        self.is_running = False
        self.pause_event.set()

        # 清空佇列
        while not self.download_queue.empty():
            try:
                self.download_queue.get_nowait()
                self.download_queue.task_done()
            except queue.Empty:
                break

        self.save_progress()
        self.save_task_state()
        self.add_log("任務已停止", "WARNING")

    def set_workers(self, new_workers):
        """動態調整 Worker 數量"""
        old_workers = self.workers
        self.workers = new_workers
        self.save_task_state()

        if new_workers > old_workers and self.is_running:
            # 增加 worker
            for _ in range(new_workers - old_workers):
                thread = threading.Thread(target=self._download_worker, daemon=True)
                thread.start()
                self.worker_threads.append(thread)
            self.add_log(f"Worker 數量從 {old_workers} 增加到 {new_workers}", "INFO")
        elif new_workers < old_workers:
            self.add_log(f"Worker 數量從 {old_workers} 減少到 {new_workers} (現有 worker 完成後生效)", "INFO")

    def _download_worker(self):
        """下載 Worker"""
        while self.is_running:
            # 等待暫停解除
            self.pause_event.wait()

            if not self.is_running:
                break

            try:
                item = self.download_queue.get(timeout=1)
                index, url = item

                output_file = os.path.join(self.temp_dir, f"segment_{index:04d}.ts")

                # 下載片段
                success = self._download_segment(url, output_file, index, retries=3)

                if success:
                    self.downloaded_segments.add(index)
                    self.downloaded_count = len(self.downloaded_segments)
                    self.consecutive_failures = 0
                    self.save_progress()
                else:
                    # 記錄失敗
                    if (index, url) not in self.failed_segments:
                        self.failed_segments.append((index, url))
                    self.failed_count = len(self.failed_segments)
                    self.consecutive_failures += 1

                    self.add_log(f"片段 {index:04d} 下載失敗 (連續失敗: {self.consecutive_failures})", "ERROR")

                    # 檢查是否連續失敗過多
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        self.add_log(f"連續失敗 {self.consecutive_failures} 次，可能是 M3U8 失效，自動暫停", "ERROR")
                        self.status = TaskStatus.M3U8_INVALID
                        self.pause()

                self.download_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.add_log(f"Worker 錯誤: {e}", "ERROR")

    def _download_segment(self, url, output_file, index, retries=3):
        """下載單個片段"""
        # 如果文件已存在且大小正常，跳過
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            return True

        for attempt in range(retries):
            if not self.is_running:
                return False

            try:
                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()

                with open(output_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not self.is_running:
                            return False
                        if chunk:
                            f.write(chunk)

                if os.path.getsize(output_file) > 0:
                    if attempt > 0:
                        self.add_log(f"片段 {index:04d} 重試成功", "SUCCESS")
                    return True

            except Exception as e:
                if attempt < retries - 1:
                    self.add_log(f"片段 {index:04d} 下載失敗 (嘗試 {attempt + 1}/{retries}): {str(e)[:50]}", "WARNING")
                    time.sleep(1)
                    continue
                else:
                    self.add_log(f"片段 {index:04d} 所有重試均失敗: {str(e)[:50]}", "ERROR")

        return False

    def _monitor_completion(self):
        """監控下載完成"""
        self.download_queue.join()

        if not self.is_running:
            return

        # 檢查是否全部完成
        if self.downloaded_count == self.total_count:
            self.add_log(f"所有片段下載完成 ({self.total_count}/{self.total_count})", "SUCCESS")

            # 自動合併
            if self.auto_merge_enabled and not self.merge_attempted:
                self.add_log("開始自動合併視頻...", "INFO")
                self.merge_video()
        elif self.failed_count > 0:
            self.add_log(f"下載完成，但有 {self.failed_count} 個片段失敗", "WARNING")
            if self.status != TaskStatus.M3U8_INVALID:
                self.status = TaskStatus.PAUSED
                self.save_task_state()

    def merge_video(self):
        """合併視頻"""
        if self.merge_attempted:
            self.add_log("已經嘗試過合併，跳過", "WARNING")
            return False

        try:
            self.status = TaskStatus.MERGING
            self.merge_attempted = True
            self.save_progress()
            self.save_task_state()

            self.add_log("正在生成文件列表...", "INFO")

            # 創建文件列表
            file_list_path = os.path.join(self.temp_dir, "filelist.txt")

            segment_count = 0
            with open(file_list_path, 'w', encoding='utf-8') as f:
                for i in sorted(self.downloaded_segments):
                    segment_file = os.path.join(self.temp_dir, f"segment_{i:04d}.ts")
                    if os.path.exists(segment_file):
                        safe_path = segment_file.replace('\\', '/')
                        f.write(f"file '{safe_path}'\n")
                        segment_count += 1

            self.add_log(f"準備合併 {segment_count} 個片段", "INFO")

            # 使用 ffmpeg 合併
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', file_list_path,
                '-c', 'copy',
                '-y',
                self.output_file
            ]

            self.add_log(f"執行 ffmpeg: {' '.join(cmd[:6])}...", "INFO")

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, universal_newlines=True)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                self.status = TaskStatus.COMPLETED
                self.is_running = False
                self.save_task_state()
                self.add_log(f"✅ 合併成功！輸出: {self.output_file}", "SUCCESS")
                return True
            else:
                self.status = TaskStatus.FAILED
                self.save_task_state()
                error_msg = stderr[-200:] if stderr else "未知錯誤"
                self.add_log(f"❌ 合併失敗: {error_msg}", "ERROR")
                return False

        except FileNotFoundError:
            self.status = TaskStatus.FAILED
            self.save_task_state()
            self.add_log("❌ 找不到 ffmpeg，請確保已安裝", "ERROR")
            return False
        except Exception as e:
            self.status = TaskStatus.FAILED
            self.save_task_state()
            self.add_log(f"❌ 合併過程出錯: {str(e)}", "ERROR")
            return False


class LogWindow(tk.Toplevel):
    """日誌視窗"""

    def __init__(self, parent, task):
        super().__init__(parent)
        self.task = task

        self.title(f"日誌 - {task.name}")
        self.geometry("800x600")
        self.configure(bg="#1e1e1e")

        self.create_widgets()
        self.update_logs()

        # 自動更新
        self.is_active = True
        self.after(1000, self.auto_update)

    def create_widgets(self):
        """創建視窗組件"""
        # 標題
        title_frame = ttk.Frame(self)
        title_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(title_frame, text=f"任務: {self.task.name}",
                  font=("Segoe UI", 12, "bold")).pack(side="left")

        ttk.Button(title_frame, text="清除日誌",
                   command=self.clear_logs).pack(side="right", padx=5)

        ttk.Button(title_frame, text="刷新",
                   command=self.update_logs).pack(side="right")

        # 日誌文本框
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame,
                                                  bg="#2d2d2d", fg="#ffffff",
                                                  font=("Consolas", 9), wrap=tk.WORD)
        self.log_text.pack(fill="both", expand=True)

        # 配置標籤顏色
        self.log_text.tag_config("INFO", foreground="#00ff00")
        self.log_text.tag_config("ERROR", foreground="#ff4444")
        self.log_text.tag_config("SUCCESS", foreground="#00ffff")
        self.log_text.tag_config("WARNING", foreground="#ffaa00")

    def update_logs(self):
        """更新日誌顯示"""
        self.log_text.delete(1.0, tk.END)

        for log in self.task.logs:
            timestamp = log['timestamp']
            level = log['level']
            message = log['message']

            line = f"[{timestamp}] [{level}] {message}\n"
            self.log_text.insert(tk.END, line, level)

        self.log_text.see(tk.END)

    def clear_logs(self):
        """清除日誌"""
        if messagebox.askyesno("確認", "確定要清除所有日誌嗎？"):
            self.task.logs = []
            self.update_logs()

    def auto_update(self):
        """自動更新"""
        if self.is_active:
            self.update_logs()
            self.after(1000, self.auto_update)

    def destroy(self):
        """關閉視窗"""
        self.is_active = False
        super().destroy()


class TaskPanel(ttk.Frame):
    """任務面板 Widget"""

    def __init__(self, parent, task, on_remove_callback):
        super().__init__(parent)
        self.task = task
        self.on_remove_callback = on_remove_callback
        self.log_window = None

        self.configure(style="TaskPanel.TFrame", padding=10)
        self.create_widgets()

        # 啟動更新線程
        self.is_active = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    def create_widgets(self):
        """創建任務面板 UI"""
        # 標題行
        title_frame = ttk.Frame(self)
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        title_frame.grid_columnconfigure(1, weight=1)

        # 狀態指示器
        self.status_label = ttk.Label(title_frame, text="●", font=("Arial", 16))
        self.status_label.grid(row=0, column=0, padx=(0, 5))

        # 任務名稱
        ttk.Label(title_frame, text=self.task.name,
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky="w")

        # 打開位置按鈕
        ttk.Button(title_frame, text="📁", width=3,
                   command=self._open_location).grid(row=0, column=2, padx=2)

        # 日誌按鈕
        ttk.Button(title_frame, text="📋", width=3,
                   command=self._open_logs).grid(row=0, column=3, padx=2)

        # 移除按鈕
        ttk.Button(title_frame, text="✕", width=3,
                   command=self._remove_task).grid(row=0, column=4)

        # 進度條
        self.progress_bar = ttk.Progressbar(self, mode="determinate",
                                            style="Green.Horizontal.TProgressbar")
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=5)
        self.progress_bar["maximum"] = self.task.total_count

        # 進度信息
        info_frame = ttk.Frame(self)
        info_frame.grid(row=2, column=0, sticky="ew")
        info_frame.grid_columnconfigure(0, weight=1)

        self.info_label = ttk.Label(info_frame, text="", font=("Segoe UI", 9))
        self.info_label.grid(row=0, column=0, sticky="w")

        # 控制按鈕
        control_frame = ttk.Frame(self)
        control_frame.grid(row=3, column=0, sticky="ew", pady=(5, 0))

        self.pause_button = ttk.Button(control_frame, text="⏸ 暫停",
                                       command=self._toggle_pause, width=8)
        self.pause_button.grid(row=0, column=0, padx=2)

        ttk.Button(control_frame, text="🔄 重試失敗",
                   command=self._retry_failed, width=10).grid(row=0, column=1, padx=2)

        self.merge_button = ttk.Button(control_frame, text="🎬 合併",
                                       command=self._merge_video, width=8)
        self.merge_button.grid(row=0, column=2, padx=2)

        # Worker 調整
        ttk.Label(control_frame, text="Workers:").grid(row=0, column=3, padx=(10, 2))
        self.worker_spinbox = ttk.Spinbox(control_frame, from_=1, to=20, width=5,
                                          command=self._update_workers)
        self.worker_spinbox.set(self.task.workers)
        self.worker_spinbox.grid(row=0, column=4, padx=2)

        self.grid_columnconfigure(0, weight=1)

    def _update_loop(self):
        """更新循環"""
        while self.is_active:
            try:
                self._update_display()
                time.sleep(0.5)
            except Exception as e:
                print(f"更新錯誤: {e}")

    def _update_display(self):
        """更新顯示"""
        if not self.is_active:
            return

        # 更新進度條
        self.progress_bar["value"] = self.task.downloaded_count

        # 更新狀態顏色
        status_colors = {
            TaskStatus.PENDING: "#808080",
            TaskStatus.DOWNLOADING: "#4caf50",
            TaskStatus.PAUSED: "#ff9800",
            TaskStatus.COMPLETED: "#2196f3",
            TaskStatus.FAILED: "#f44336",
            TaskStatus.MERGING: "#9c27b0",
            TaskStatus.M3U8_INVALID: "#d32f2f"
        }
        self.status_label.configure(foreground=status_colors.get(self.task.status, "#808080"))

        # 更新信息文字
        percentage = self.task.get_progress_percentage()

        if self.task.status == TaskStatus.M3U8_INVALID:
            status_text = "M3U8 失效"
        else:
            status_text = self.task.status.value.upper()

        info = f"{status_text} | {self.task.downloaded_count}/{self.task.total_count} ({percentage:.1f}%)"

        if self.task.failed_count > 0:
            info += f" | 失敗: {self.task.failed_count}"

        if self.task.status == TaskStatus.COMPLETED:
            info += " | ✅ 已完成"

        self.info_label.configure(text=info)

        # 更新暫停按鈕
        if self.task.status == TaskStatus.PAUSED or self.task.status == TaskStatus.M3U8_INVALID:
            self.pause_button.configure(text="▶ 繼續")
        else:
            self.pause_button.configure(text="⏸ 暫停")

        # 更新合併按鈕狀態
        if self.task.status == TaskStatus.COMPLETED or self.task.merge_attempted:
            self.merge_button.configure(state="disabled")
        else:
            self.merge_button.configure(state="normal")

    def _toggle_pause(self):
        """切換暫停/繼續"""
        if self.task.status in [TaskStatus.PAUSED, TaskStatus.M3U8_INVALID]:
            # 如果是 M3U8 失效，詢問是否要重試
            if self.task.status == TaskStatus.M3U8_INVALID:
                if messagebox.askyesno("確認", "偵測到 M3U8 可能失效\n確定要重新開始下載嗎？"):
                    self.task.consecutive_failures = 0
                    self.task.status = TaskStatus.PAUSED
                    self.task.resume()
                    self.task.start()
            else:
                self.task.resume()
                if not self.task.is_running:
                    self.task.start()
        elif self.task.status == TaskStatus.DOWNLOADING:
            self.task.pause()

    def _retry_failed(self):
        """重試失敗的片段"""
        if self.task.failed_segments:
            count = len(self.task.failed_segments)
            self.task.add_log(f"重試 {count} 個失敗片段", "INFO")

            for index, url in self.task.failed_segments:
                self.task.download_queue.put((index, url))

            self.task.failed_segments = []
            self.task.failed_count = 0
            self.task.consecutive_failures = 0

            if self.task.status in [TaskStatus.PAUSED, TaskStatus.M3U8_INVALID]:
                self.task.status = TaskStatus.PAUSED
                self.task.resume()
                if not self.task.is_running:
                    self.task.start()
        else:
            messagebox.showinfo("提示", "沒有失敗的片段需要重試")

    def _merge_video(self):
        """合併視頻"""
        if self.task.status == TaskStatus.DOWNLOADING:
            messagebox.showwarning("警告", "請先暫停下載再進行合併")
            return

        if self.task.merge_attempted:
            messagebox.showinfo("提示", "已經嘗試過合併")
            return

        threading.Thread(target=self._do_merge, daemon=True).start()

    def _do_merge(self):
        """執行合併"""
        success = self.task.merge_video()
        if success:
            messagebox.showinfo("成功", f"視頻已合併:\n{self.task.output_file}")
        else:
            messagebox.showerror("失敗", "視頻合併失敗，請查看日誌")

    def _update_workers(self):
        """更新 Worker 數量"""
        try:
            new_workers = int(self.worker_spinbox.get())
            self.task.set_workers(new_workers)
        except ValueError:
            pass

    def _open_logs(self):
        """打開日誌視窗"""
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = LogWindow(self.winfo_toplevel(), self.task)
        else:
            self.log_window.lift()
            self.log_window.focus()

    def _open_location(self):
        """打開檔案位置"""
        # 優先打開完成的視頻，否則打開臨時目錄
        if os.path.exists(self.task.output_file):
            path = self.task.output_file
        else:
            path = self.task.temp_dir

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(os.path.dirname(path))
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", os.path.dirname(path)])
            else:  # Linux
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception as e:
            messagebox.showerror("錯誤", f"無法打開位置:\n{str(e)}")

    def _remove_task(self):
        """移除任務"""
        if self.task.status == TaskStatus.DOWNLOADING:
            if not messagebox.askyesno("確認", "任務正在下載中，確定要移除嗎？\n(已下載的檔案會保留)"):
                return

        self.is_active = False
        self.task.stop()

        # 關閉日誌視窗
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.destroy()

        self.on_remove_callback(self)

    def destroy(self):
        """銷毀面板"""
        self.is_active = False
        super().destroy()


class M3U8DownloaderMultiTask:
    """多任務 M3U8 下載器主程式"""

    def __init__(self, root):
        self.root = root
        self.root.title("M3U8 Downloader Pro - Multi-Task")
        self.root.geometry("1200x800")
        self.root.configure(bg="#1e1e1e")

        self.tasks = []
        self.task_panels = []
        self.next_task_id = 1

        # 獲取腳本目錄
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.default_downloads = os.path.join(self.script_dir, "downloads")

        self.setup_styles()
        self.create_widgets()

        # 恢復未完成的任務
        self.root.after(500, self.restore_tasks)

        # 綁定關閉事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_styles(self):
        """設置樣式"""
        style = ttk.Style()
        style.theme_use('clam')

        bg_dark = "#1e1e1e"
        bg_lighter = "#2d2d2d"
        fg_color = "#ffffff"
        accent_color = "#007acc"

        style.configure(".", background=bg_dark, foreground=fg_color, fieldbackground=bg_lighter)
        style.configure("TFrame", background=bg_dark)
        style.configure("TaskPanel.TFrame", background=bg_lighter, relief="raised", borderwidth=1)
        style.configure("TLabel", background=bg_dark, foreground=fg_color, font=("Segoe UI", 10))
        style.configure("TButton", background=accent_color, foreground=fg_color,
                        borderwidth=0, focuscolor="none", font=("Segoe UI", 9))
        style.map("TButton", background=[("active", "#005a9e")])
        style.configure("TEntry", fieldbackground=bg_lighter, foreground=fg_color, insertcolor=fg_color)
        style.configure("Green.Horizontal.TProgressbar", background="#4caf50", troughcolor="#1e1e1e")

    def create_widgets(self):
        """創建主界面"""
        # 創建 PanedWindow 支援拖拽調整
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 左側：輸入區域
        left_frame = ttk.Frame(paned, padding=10)
        paned.add(left_frame, weight=1)

        # M3U8 URL 輸入
        url_frame = ttk.LabelFrame(left_frame, text=" M3U8 URL ", padding=10)
        url_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        url_container = ttk.Frame(url_frame)
        url_container.grid(row=0, column=0, sticky="ew", pady=5)
        url_container.grid_columnconfigure(0, weight=1)

        self.url_entry = ttk.Entry(url_container)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self.load_m3u8())
        self.url_entry.config(width=50)

        ttk.Button(url_frame, text="載入 M3U8",
                   command=self.load_m3u8).grid(row=1, column=0, sticky="ew", pady=(5, 0))

        url_frame.grid_columnconfigure(0, weight=1)

        # 片段列表
        list_frame = ttk.LabelFrame(left_frame, text=" 片段列表 ", padding=10)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        list_scroll_y = ttk.Scrollbar(list_frame, orient="vertical")
        list_scroll_y.grid(row=0, column=1, sticky="ns")

        list_scroll_x = ttk.Scrollbar(list_frame, orient="horizontal")
        list_scroll_x.grid(row=1, column=0, sticky="ew")

        self.segment_listbox = tk.Listbox(list_frame,
                                          yscrollcommand=list_scroll_y.set,
                                          xscrollcommand=list_scroll_x.set,
                                          bg="#2d2d2d", fg="#ffffff",
                                          selectbackground="#007acc",
                                          font=("Consolas", 9),
                                          width=60)
        self.segment_listbox.grid(row=0, column=0, sticky="nsew")
        list_scroll_y.config(command=self.segment_listbox.yview)
        list_scroll_x.config(command=self.segment_listbox.xview)

        self.count_label = ttk.Label(list_frame, text="總計: 0")
        self.count_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))

        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # URL 修正
        modify_frame = ttk.LabelFrame(left_frame, text=" URL 修正 ", padding=10)
        modify_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(modify_frame, text="前綴:").grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.prefix_entry = ttk.Entry(modify_frame)
        self.prefix_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(modify_frame, text="後綴:").grid(row=1, column=0, sticky="w", pady=2, padx=(0, 5))
        self.suffix_entry = ttk.Entry(modify_frame)
        self.suffix_entry.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Button(modify_frame, text="套用",
                   command=self.apply_url_modification).grid(row=2, column=0,
                                                             columnspan=2, sticky="ew", pady=(5, 0))

        modify_frame.grid_columnconfigure(1, weight=1)

        # 下載設定
        config_frame = ttk.LabelFrame(left_frame, text=" 下載設定 ", padding=10)
        config_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(config_frame, text="檔名:").grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.filename_entry = ttk.Entry(config_frame)
        self.filename_entry.insert(0, f"video_{self.next_task_id}")
        self.filename_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(config_frame, text="Workers:").grid(row=1, column=0, sticky="w", pady=2, padx=(0, 5))
        self.worker_spinbox = ttk.Spinbox(config_frame, from_=1, to=20, width=10)
        self.worker_spinbox.set(5)
        self.worker_spinbox.grid(row=1, column=1, sticky="w", pady=2)

        ttk.Label(config_frame, text="輸出目錄:").grid(row=2, column=0, sticky="nw", pady=2, padx=(0, 5))

        dir_frame = ttk.Frame(config_frame)
        dir_frame.grid(row=2, column=1, sticky="ew", pady=2)
        dir_frame.grid_columnconfigure(0, weight=1)

        self.output_dir_entry = ttk.Entry(dir_frame)
        self.output_dir_entry.insert(0, self.default_downloads)
        self.output_dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        ttk.Button(dir_frame, text="...", width=3,
                   command=self.browse_output_dir).grid(row=0, column=1)

        config_frame.grid_columnconfigure(1, weight=1)

        # 創建任務按鈕
        ttk.Button(left_frame, text="🚀 創建下載任務",
                   command=self.create_task,
                   style="Accent.TButton").grid(row=4, column=0, sticky="ew", pady=(5, 0))

        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # 右側：任務列表
        right_frame = ttk.Frame(paned, padding=10)
        paned.add(right_frame, weight=2)

        ttk.Label(right_frame, text="下載任務",
                  font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # 任務容器（可滾動）
        canvas_frame = ttk.Frame(right_frame)
        canvas_frame.grid(row=1, column=0, sticky="nsew")

        self.task_canvas = tk.Canvas(canvas_frame, bg="#1e1e1e", highlightthickness=0)
        task_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical",
                                       command=self.task_canvas.yview)

        self.task_container = ttk.Frame(self.task_canvas)
        self.task_canvas_window = self.task_canvas.create_window((0, 0),
                                                                 window=self.task_container,
                                                                 anchor="nw")

        self.task_canvas.configure(yscrollcommand=task_scrollbar.set)

        self.task_canvas.grid(row=0, column=0, sticky="nsew")
        task_scrollbar.grid(row=0, column=1, sticky="ns")

        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        # 綁定滾動
        self.task_container.bind("<Configure>", self._on_task_container_configure)
        self.task_canvas.bind("<Configure>", self._on_canvas_configure)

        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # 配置主視窗
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 臨時變數
        self.current_m3u8_url = ""
        self.current_ts_list = []

    def _on_task_container_configure(self, event):
        """更新畫布滾動區域"""
        self.task_canvas.configure(scrollregion=self.task_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """調整任務容器寬度"""
        self.task_canvas.itemconfig(self.task_canvas_window, width=event.width)

    def browse_output_dir(self):
        """瀏覽輸出目錄"""
        directory = filedialog.askdirectory()
        if directory:
            self.output_dir_entry.delete(0, tk.END)
            self.output_dir_entry.insert(0, directory)

    def load_m3u8(self):
        """載入 M3U8"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("警告", "請輸入 M3U8 URL")
            return

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            content = response.text

            self.current_m3u8_url = url
            self.current_ts_list = self.parse_m3u8(content, url)

            self.segment_listbox.delete(0, tk.END)
            for i, ts_url in enumerate(self.current_ts_list, 1):
                self.segment_listbox.insert(tk.END, f"{i:04d}. {ts_url}")

            self.count_label.config(text=f"總計: {len(self.current_ts_list)} 個片段")
            messagebox.showinfo("成功", f"已載入 {len(self.current_ts_list)} 個片段")

        except Exception as e:
            messagebox.showerror("錯誤", f"載入失敗:\n{str(e)}")

    def parse_m3u8(self, content, base_url):
        """解析 M3U8"""
        ts_list = []
        base_path = base_url.rsplit('/', 1)[0] + '/'

        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('http'):
                    ts_url = line
                else:
                    ts_url = urljoin(base_path, line)
                ts_list.append(ts_url)

        return ts_list

    def apply_url_modification(self):
        """套用 URL 修正"""
        if not self.current_ts_list:
            messagebox.showwarning("警告", "請先載入 M3U8")
            return

        prefix = self.prefix_entry.get()
        suffix = self.suffix_entry.get()

        self.current_ts_list = [f"{prefix}{url}{suffix}" for url in self.current_ts_list]

        self.segment_listbox.delete(0, tk.END)
        for i, ts_url in enumerate(self.current_ts_list, 1):
            self.segment_listbox.insert(tk.END, f"{i:04d}. {ts_url}")

        messagebox.showinfo("成功", "URL 修正已套用")

    def create_task(self):
        """創建下載任務"""
        if not self.current_ts_list:
            messagebox.showwarning("警告", "請先載入 M3U8")
            return

        filename = self.filename_entry.get().strip()
        if not filename:
            messagebox.showwarning("警告", "請輸入檔名")
            return

        output_dir = self.output_dir_entry.get()
        workers = int(self.worker_spinbox.get())

        # 創建任務
        task = DownloadTask(
            task_id=self.next_task_id,
            name=filename,
            ts_list=self.current_ts_list.copy(),
            output_dir=output_dir,
            workers=workers,
            m3u8_url=self.current_m3u8_url
        )

        task.save_task_state()

        self.tasks.append(task)
        self.next_task_id += 1

        # 創建任務面板
        panel = TaskPanel(self.task_container, task, self.remove_task_panel)
        panel.pack(fill="x", pady=5, padx=5)
        self.task_panels.append(panel)

        # 自動開始下載
        task.start()

        # 更新檔名建議
        self.filename_entry.delete(0, tk.END)
        self.filename_entry.insert(0, f"video_{self.next_task_id}")

        messagebox.showinfo("成功", f"任務 '{filename}' 已創建並開始下載")

    def remove_task_panel(self, panel):
        """移除任務面板"""
        if panel in self.task_panels:
            self.task_panels.remove(panel)

            # 從任務列表中移除
            if panel.task in self.tasks:
                self.tasks.remove(panel.task)

            panel.destroy()

    def restore_tasks(self):
        """恢復未完成的任務"""
        try:
            # 搜尋所有 task_state.json 文件
            downloads_dir = self.default_downloads
            if not os.path.exists(downloads_dir):
                return

            restored_count = 0
            for root_dir, dirs, files in os.walk(downloads_dir):
                if 'task_state.json' in files:
                    state_file = os.path.join(root_dir, 'task_state.json')
                    task = DownloadTask.load_task_from_state(state_file)

                    if task:
                        # 檢查是否已完成
                        if task.status == TaskStatus.COMPLETED:
                            continue

                        self.tasks.append(task)

                        # 創建任務面板
                        panel = TaskPanel(self.task_container, task, self.remove_task_panel)
                        panel.pack(fill="x", pady=5, padx=5)
                        self.task_panels.append(panel)

                        # 更新 task_id
                        if task.task_id >= self.next_task_id:
                            self.next_task_id = task.task_id + 1

                        restored_count += 1

            if restored_count > 0:
                messagebox.showinfo("任務恢復", f"已恢復 {restored_count} 個未完成的任務")

        except Exception as e:
            print(f"恢復任務失敗: {e}")

    def on_closing(self):
        """關閉程式時的處理"""
        # 暫停所有下載中的任務
        for task in self.tasks:
            if task.status == TaskStatus.DOWNLOADING:
                task.pause()

        self.root.destroy()


def main():
    root = tk.Tk()
    app = M3U8DownloaderMultiTask(root)
    root.mainloop()


if __name__ == "__main__":
    main()