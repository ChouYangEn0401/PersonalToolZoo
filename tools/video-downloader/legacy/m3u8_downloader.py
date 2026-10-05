#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 Downloader Pro - Multi-Task Version
支援多任務並行下載、斷點續傳、動態調整的專業下載器
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


class TaskStatus(Enum):
    """任務狀態枚舉"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    MERGING = "merging"


class DownloadTask:
    """下載任務類別"""

    def __init__(self, task_id, name, ts_list, output_dir, workers=5):
        self.task_id = task_id
        self.name = name
        self.ts_list = ts_list
        self.output_dir = output_dir
        self.temp_dir = os.path.join(output_dir, f"{name}_temp")
        self.output_file = os.path.join(output_dir, f"{name}.mkv")

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
        self.pause_event.set()  # 初始為非暫停狀態

        # 下載記錄
        self.downloaded_segments = set()  # 已下載的片段索引
        self.failed_segments = []
        self.progress_file = os.path.join(self.temp_dir, "progress.json")

        # 網路錯誤計數
        self.consecutive_failures = 0
        self.max_consecutive_failures = 10

        # 創建臨時目錄並載入進度
        os.makedirs(self.temp_dir, exist_ok=True)
        self.load_progress()

    def load_progress(self):
        """載入下載進度（斷點續傳）"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                    self.downloaded_segments = set(data.get('downloaded', []))
                    self.downloaded_count = len(self.downloaded_segments)
            except Exception as e:
                print(f"載入進度失敗: {e}")

    def save_progress(self):
        """保存下載進度"""
        try:
            data = {
                'downloaded': list(self.downloaded_segments),
                'total': self.total_count,
                'timestamp': datetime.now().isoformat()
            }
            with open(self.progress_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"保存進度失敗: {e}")

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

        # 填充下載佇列（跳過已下載的）
        for i, ts_url in enumerate(self.ts_list):
            if i not in self.downloaded_segments:
                self.download_queue.put((i, ts_url))

        # 啟動 Worker
        self.worker_threads = []
        for _ in range(self.workers):
            thread = threading.Thread(target=self._download_worker, daemon=True)
            thread.start()
            self.worker_threads.append(thread)

    def pause(self):
        """暫停下載"""
        self.status = TaskStatus.PAUSED
        self.pause_event.clear()

    def resume(self):
        """繼續下載"""
        self.status = TaskStatus.DOWNLOADING
        self.pause_event.set()

    def stop(self):
        """停止下載（完全停止）"""
        self.is_running = False
        self.pause_event.set()  # 解除暫停以便 worker 退出

        # 清空佇列
        while not self.download_queue.empty():
            try:
                self.download_queue.get_nowait()
                self.download_queue.task_done()
            except queue.Empty:
                break

        self.save_progress()

    def set_workers(self, new_workers):
        """動態調整 Worker 數量"""
        old_workers = self.workers
        self.workers = new_workers

        if new_workers > old_workers and self.is_running:
            # 增加 worker
            for _ in range(new_workers - old_workers):
                thread = threading.Thread(target=self._download_worker, daemon=True)
                thread.start()
                self.worker_threads.append(thread)
        # 減少 worker 會在現有 worker 完成後自然減少

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
                success = self._download_segment(url, output_file, retries=3)

                if success:
                    self.downloaded_segments.add(index)
                    self.downloaded_count = len(self.downloaded_segments)
                    self.consecutive_failures = 0  # 重置連續失敗計數
                    self.save_progress()
                else:
                    self.failed_segments.append((index, url))
                    self.failed_count += 1
                    self.consecutive_failures += 1

                    # 檢查是否連續失敗過多
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        self.status = TaskStatus.FAILED
                        self.pause()

                self.download_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Worker 錯誤: {e}")

    def _download_segment(self, url, output_file, retries=3):
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
                    return True

            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue

        return False

    def merge_video(self):
        """合併視頻"""
        try:
            self.status = TaskStatus.MERGING

            # 創建文件列表
            file_list_path = os.path.join(self.temp_dir, "filelist.txt")

            with open(file_list_path, 'w', encoding='utf-8') as f:
                for i in sorted(self.downloaded_segments):
                    segment_file = os.path.join(self.temp_dir, f"segment_{i:04d}.ts")
                    if os.path.exists(segment_file):
                        safe_path = segment_file.replace('\\', '/')
                        f.write(f"file '{safe_path}'\n")

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

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, universal_newlines=True)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                self.status = TaskStatus.COMPLETED
                return True
            else:
                self.status = TaskStatus.FAILED
                return False

        except Exception as e:
            self.status = TaskStatus.FAILED
            return False


class TaskPanel(ttk.Frame):
    """任務面板 Widget"""

    def __init__(self, parent, task, on_remove_callback):
        super().__init__(parent)
        self.task = task
        self.on_remove_callback = on_remove_callback

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

        # 移除按鈕
        ttk.Button(title_frame, text="✕", width=3,
                   command=self._remove_task).grid(row=0, column=2)

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

        ttk.Button(control_frame, text="🎬 合併",
                   command=self._merge_video, width=8).grid(row=0, column=2, padx=2)

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
            TaskStatus.MERGING: "#9c27b0"
        }
        self.status_label.configure(foreground=status_colors.get(self.task.status, "#808080"))

        # 更新信息文字
        percentage = self.task.get_progress_percentage()
        status_text = self.task.status.value.upper()
        info = f"{status_text} | {self.task.downloaded_count}/{self.task.total_count} ({percentage:.1f}%)"

        if self.task.failed_count > 0:
            info += f" | 失敗: {self.task.failed_count}"

        self.info_label.configure(text=info)

        # 更新暫停按鈕
        if self.task.status == TaskStatus.PAUSED:
            self.pause_button.configure(text="▶ 繼續")
        else:
            self.pause_button.configure(text="⏸ 暫停")

    def _toggle_pause(self):
        """切換暫停/繼續"""
        if self.task.status == TaskStatus.PAUSED:
            self.task.resume()
        elif self.task.status == TaskStatus.DOWNLOADING:
            self.task.pause()

    def _retry_failed(self):
        """重試失敗的片段"""
        if self.task.failed_segments:
            for index, url in self.task.failed_segments:
                self.task.download_queue.put((index, url))
            self.task.failed_segments = []
            self.task.failed_count = 0

            if self.task.status == TaskStatus.PAUSED:
                self.task.resume()

    def _merge_video(self):
        """合併視頻"""
        if self.task.status == TaskStatus.DOWNLOADING:
            messagebox.showwarning("警告", "請先暫停下載再進行合併")
            return

        threading.Thread(target=self._do_merge, daemon=True).start()

    def _do_merge(self):
        """執行合併"""
        success = self.task.merge_video()
        if success:
            messagebox.showinfo("成功", f"視頻已合併: {self.task.output_file}")
        else:
            messagebox.showerror("失敗", "視頻合併失敗，請查看日誌")

    def _update_workers(self):
        """更新 Worker 數量"""
        try:
            new_workers = int(self.worker_spinbox.get())
            self.task.set_workers(new_workers)
        except ValueError:
            pass

    def _remove_task(self):
        """移除任務"""
        if self.task.status == TaskStatus.DOWNLOADING:
            if not messagebox.askyesno("確認", "任務正在下載中，確定要移除嗎？\n(已下載的檔案會保留)"):
                return

        self.is_active = False
        self.task.stop()
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

        self.setup_styles()
        self.create_widgets()

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
        # 左側：輸入區域
        left_frame = ttk.Frame(self.root, padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # M3U8 URL 輸入
        url_frame = ttk.LabelFrame(left_frame, text=" M3U8 URL ", padding=10)
        url_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.grid(row=0, column=0, sticky="ew", pady=5)
        self.url_entry.bind("<Return>", lambda e: self.load_m3u8())

        ttk.Button(url_frame, text="載入 M3U8",
                   command=self.load_m3u8).grid(row=1, column=0, sticky="ew")

        url_frame.grid_columnconfigure(0, weight=1)

        # 片段列表
        list_frame = ttk.LabelFrame(left_frame, text=" 片段列表 ", padding=10)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        list_scroll = ttk.Scrollbar(list_frame)
        list_scroll.grid(row=0, column=1, sticky="ns")

        self.segment_listbox = tk.Listbox(list_frame, yscrollcommand=list_scroll.set,
                                          bg="#2d2d2d", fg="#ffffff",
                                          selectbackground="#007acc", font=("Consolas", 9))
        self.segment_listbox.grid(row=0, column=0, sticky="nsew")
        list_scroll.config(command=self.segment_listbox.yview)

        self.count_label = ttk.Label(list_frame, text="總計: 0")
        self.count_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # URL 修正
        modify_frame = ttk.LabelFrame(left_frame, text=" URL 修正 ", padding=10)
        modify_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(modify_frame, text="前綴:").grid(row=0, column=0, sticky="w", pady=2)
        self.prefix_entry = ttk.Entry(modify_frame)
        self.prefix_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(modify_frame, text="後綴:").grid(row=1, column=0, sticky="w", pady=2)
        self.suffix_entry = ttk.Entry(modify_frame)
        self.suffix_entry.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Button(modify_frame, text="套用",
                   command=self.apply_url_modification).grid(row=2, column=0,
                                                             columnspan=2, sticky="ew", pady=(5, 0))

        modify_frame.grid_columnconfigure(1, weight=1)

        # 下載設定
        config_frame = ttk.LabelFrame(left_frame, text=" 下載設定 ", padding=10)
        config_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(config_frame, text="檔名:").grid(row=0, column=0, sticky="w", pady=2)
        self.filename_entry = ttk.Entry(config_frame)
        self.filename_entry.insert(0, f"video_{self.next_task_id}")
        self.filename_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(config_frame, text="Workers:").grid(row=1, column=0, sticky="w", pady=2)
        self.worker_spinbox = ttk.Spinbox(config_frame, from_=1, to=20)
        self.worker_spinbox.set(5)
        self.worker_spinbox.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(config_frame, text="輸出目錄:").grid(row=2, column=0, sticky="w", pady=2)

        dir_frame = ttk.Frame(config_frame)
        dir_frame.grid(row=2, column=1, sticky="ew", pady=2)
        dir_frame.grid_columnconfigure(0, weight=1)

        self.output_dir_entry = ttk.Entry(dir_frame)
        self.output_dir_entry.insert(0, os.path.join(os.getcwd(), "downloads"))
        self.output_dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        ttk.Button(dir_frame, text="...", width=3,
                   command=self.browse_output_dir).grid(row=0, column=1)

        config_frame.grid_columnconfigure(1, weight=1)

        # 創建任務按鈕
        ttk.Button(left_frame, text="🚀 創建下載任務",
                   command=self.create_task,
                   style="Accent.TButton").grid(row=4, column=0, sticky="ew")

        left_frame.grid_rowconfigure(1, weight=1)

        # 右側：任務列表
        right_frame = ttk.Frame(self.root, padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

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
        self.root.grid_columnconfigure(0, weight=0, minsize=400)
        self.root.grid_columnconfigure(1, weight=1)

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
            workers=workers
        )

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
            panel.destroy()


def main():
    root = tk.Tk()
    app = M3U8DownloaderMultiTask(root)
    root.mainloop()


if __name__ == "__main__":
    main()