import os
import threading
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import pygame
from lib.AudioProcessingHandler import strPath__localGenAudioForNovelContent
from pydub import AudioSegment
from pydub.effects import speedup
import shutil

# Configuration
DEFAULT_SPEED = 1.5       # 預設加速倍數
WAIT_AFTER_PLAY = 3       # 播放結束後等待秒數
WAIT_BEFORE_DELETE = 2    # 刪除舊檔案前等待秒數
TEMP_DIR = Path("output/temp/output_sound")
TEMP_DIR.mkdir(exist_ok=True)


def split_into_segments(text):
    """
    將大段文字依照 200 字長度限制切分，
    在 180 字後尋找 '。' 或 '.' 做斷行，避免在 '...' 中斷。
    """
    segments = []
    for paragraph in text.splitlines():
        para = paragraph.strip()
        if not para:
            continue
        while len(para) > 200:
            # 嘗試在 180 到 len(para) 之間找標點
            break_idx = None
            for i in range(180, len(para)):
                if para[i] in ('。', '.'):
                    # 避免在 '...' 中斷
                    if not (para[i] == '.' and i+2 < len(para) and para[i+1] == '.' and para[i+2] == '.'):
                        break_idx = i + 1
                        break
            if not break_idx or break_idx > 200:
                break_idx = 200
            segments.append(para[:break_idx].strip())
            para = para[break_idx:].strip()
        if para:
            segments.append(para)
    return segments


class AudioPlayer:
    def __init__(self, subtitle_label, listbox=None):
        pygame.mixer.init()
        self.subtitle_label = subtitle_label
        self.listbox = listbox
        self.speed_factor = DEFAULT_SPEED
        self.audio_files = []
        self.temp_files = []
        self.text_lines = []
        self.current_index = 0
        self.is_paused = False
        self.after_id = None

    def generate_and_load(self, text_lines):
        """生成語音檔並準備播放列表"""
        self.cleanup_files()
        self.text_lines = text_lines
        self.audio_files.clear()
        self.temp_files.clear()
        self.current_index = 0

        for idx, line in enumerate(text_lines, start=1):
            raw = strPath__localGenAudioForNovelContent(str(TEMP_DIR), line, f"{idx}.mp3")
            if self.speed_factor != 1.0:
                accelerated = f"{TEMP_DIR}{idx}_accelerated.mp3"
                if self._accelerate(raw, self.speed_factor, str(accelerated)):
                    self.audio_files.append(str(accelerated))
                    self.temp_files.append(str(accelerated))
                else:
                    print(f"加速失敗，使用原始音訊：{raw}")
                    self.audio_files.append(raw)
            else:
                self.audio_files.append(raw)

    def _accelerate(self, inp, speed, outp):
        """加速音訊並輸出，失敗則返回 False"""
        for attempt in range(2):
            try:
                if os.path.exists(outp):
                    os.remove(outp)
                audio = AudioSegment.from_file(inp)
                sped = speedup(audio, playback_speed=speed)
                sped.export(outp, format="mp3")
                return True
            except Exception as e:
                print(f"Accelerate error (attempt {attempt+1}): {e}")
                time.sleep(0.1)
        return False

    def play(self):
        if not self.audio_files:
            messagebox.showinfo("提醒", "請先生成音訊！")
            return
        self.current_index = 0
        self.is_paused = False
        self._play_current()

    def _play_current(self):
        if self.current_index >= len(self.audio_files):
            self._on_finish_all()
            return
        file = self.audio_files[self.current_index]
        try:
            pygame.mixer.music.load(file)
        except pygame.error as e:
            print(f"跳過損壞檔案：{file}，原因：{e}")
            self._after_segment()
            return
        pygame.mixer.music.play()
        self.subtitle_label.config(text=self.text_lines[self.current_index])
        self._schedule_check()

    def _schedule_check(self):
        # 只有在播放且未暫停時才檢查
        if not self.is_paused:
            self.after_id = self.subtitle_label.after(100, self._check_playback)

    def _check_playback(self):
        if self.is_paused:
            return
        if pygame.mixer.music.get_busy():
            self._schedule_check()
        else:
            self._after_segment()

    def _after_segment(self):
        # 刪除 listbox 中 i-3 的項目
        idx = self.current_index
        if self.listbox and idx >= 3:
            # 刪除最舊的對應項目
            self.listbox.delete(0)
        self.current_index += 1
        self._play_current()

    def toggle_pause(self):
        if pygame.mixer.music.get_busy() and not self.is_paused:
            # 暫停播放並取消檢查排程
            pygame.mixer.music.pause()
            self.is_paused = True
            if self.after_id:
                self.subtitle_label.after_cancel(self.after_id)
                self.after_id = None
        elif self.is_paused:
            # 續播並重新排程檢查
            pygame.mixer.music.unpause()
            self.is_paused = False
            self._schedule_check()

    def _on_finish_all(self):
        def finish_wait():
            time.sleep(WAIT_AFTER_PLAY)
            self.reset_for_new()
        threading.Thread(target=finish_wait, daemon=True).start()

    def reset_for_new(self):
        time.sleep(WAIT_BEFORE_DELETE)
        self.cleanup_files()
        self.subtitle_label.after(0, lambda: self.subtitle_label.config(text="請貼入新文章，然後按生成並播放"))

    def cleanup_files(self):
        pygame.mixer.music.stop()
        time.sleep(0.1)
        for f in self.temp_files:
            try:
                os.remove(f)
            except:
                pass
        self.temp_files.clear()

    def destroy(self):
        pygame.mixer.music.stop()
        pygame.mixer.quit()


def main():
    root = tk.Tk()
    root.title("帶滑桿與段落清單的小說語音播放器")
    root.geometry("800x800")

    # 文字輸入
    tk.Label(root, text="請輸入小說內容（每行一段，可自動切分）", font=("Arial", 14)).pack(pady=10)
    text_input = tk.Text(root, height=8, width=80, font=("Arial", 12))
    text_input.pack()

    # 滑桿
    tk.Label(root, text="加速倍速：", font=("Arial", 12)).pack(pady=(10,0))
    speed_slider = tk.Scale(root, from_=1.0, to=3.0, resolution=0.1, orient=tk.HORIZONTAL,
                             length=500, label="倍速", font=("Arial", 10))
    speed_slider.set(DEFAULT_SPEED)
    speed_slider.pack()

    # 生成文本分段並顯示到 listbox
    def on_generate_play():
        content = text_input.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提醒", "請先輸入內容！")
            return
        segments = split_into_segments(content)
        listbox.delete(0, tk.END)
        for seg in segments:
            listbox.insert(tk.END, seg)
        player.speed_factor = speed_slider.get()
        player.generate_and_load(segments)
        player.play()

    # listbox 及操作按鈕
    tk.Label(root, text="字幕清單", font=("Arial", 14)).pack(pady=(20,5))
    list_frame = tk.Frame(root)
    list_frame.pack()
    listbox = tk.Listbox(list_frame, height=10, width=80, font=("Arial", 12))
    listbox.pack(side=tk.LEFT)
    scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    listbox.config(yscrollcommand=scrollbar.set)

    def on_list_generate_play():
        items = listbox.get(0, tk.END)
        if not items:
            messagebox.showwarning("提醒", "清單為空，無法播放！")
            return
        player.speed_factor = speed_slider.get()
        player.generate_and_load(list(items))
        player.play()

    def delete_selected():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("提醒", "請先選擇要刪除的段落！")
            return
        idx = sel[0]
        if messagebox.askyesno("刪除段落", "確定要刪除此段文本？"):
            listbox.delete(idx)

    def on_closing():
        player.destroy()
        root.destroy()
        clear_temp_folder()
        root.destroy()

    def clear_temp_folder():
        folder = 'output/temp/'
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f'無法刪除 {file_path}：{e}')

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="生成並播放", font=("Arial", 14), command=on_generate_play).grid(row=0, column=0, padx=5)
    tk.Button(btn_frame, text="播放／暫停", font=("Arial", 14), command=lambda: player.toggle_pause()).grid(row=0, column=1, padx=5)
    tk.Button(btn_frame, text="清單生成並播放", font=("Arial", 14), command=on_list_generate_play).grid(row=0, column=2, padx=5)
    tk.Button(btn_frame, text="刪除此段", font=("Arial", 14), command=delete_selected).grid(row=0, column=3, padx=5)

    # 字幕顯示
    subtitle_label = tk.Label(root, text="尚未開始播放", font=("Arial", 18), wraplength=700)
    subtitle_label.pack(pady=20)

    root.protocol("WM_DELETE_WINDOW", lambda: (on_closing(), player.destroy(), root.destroy()))
    player = AudioPlayer(subtitle_label, listbox)

    root.mainloop()

if __name__ == "__main__":
    main()

