import os.path
from os import remove
import subprocess
import pygame
import tkinter as tk
from lib.AudioProcessingHandler import strPath__localGenAudioForNovelContent
import time
import pygame
import tkinter as tk
from pydub.utils import mediainfo

from pydub import AudioSegment
from pydub.effects import speedup


def accelerate_audio(input_file, speed_factor, output_file):
    """
    利用 pydub 將 input_file 加速後保存到 output_file。
    """
    try:
        sound = AudioSegment.from_file(input_file)
    except Exception as e:
        print(f"加載音頻文件 {input_file} 出錯: {e}")
        return False
    try:
        accelerated = speedup(sound, playback_speed=speed_factor)
        accelerated.export(output_file, format="mp3")
        return True
    except Exception as e:
        print(f"加速音頻出錯: {e}")
        return False

class AudioPlayer:
    def __init__(self, audios, text_lines, text_label, speed_factor=1.5):
        self.audios = audios  # 每個段落的音頻文件
        self.text_lines = text_lines  # 每個音頻對應的字幕
        self.text_label = text_label  # 顯示字幕的標籤
        self.is_playing = False
        self.is_paused = False
        self.current_subtitle_index = 0
        self.speed_factor = speed_factor  # 播放速度
        self.curPlayIndex = 0
        pygame.mixer.init()  # 初始化 pygame 音頻
        self.accelerate_audios = []


    def get_audio_duration(self, audio_file):
        """
        利用 pydub 獲取音頻時長（單位秒）。
        """
        try:
            sound = AudioSegment.from_file(audio_file)
            return len(sound) / 1000.0
        except Exception as e:
            print(f"獲取時長出錯: {e}")
            return 0

    def _play_audio_and_update_subtitles(self):
        """
        播放當前音頻並更新字幕：
         - 如果 speed_factor != 1，則先生成加速後的音頻文件；
         - 播放音頻，顯示對應字幕，並啟動輪詢檢測播放完畢。
        """
        if self.current_subtitle_index < len(self.audios):
            original_audio_file = self.audios[self.current_subtitle_index]
            subtitle = self.text_lines[self.current_subtitle_index]

            # 默認播放原始文件；如果需要加速，則生成加速後的文件
            audio_file = original_audio_file
            if self.speed_factor != 1.0:
                # 生成加速後的臨時文件名
                audio_file = original_audio_file.replace(".mp3", f"_accelerated.mp3")
                if not os.path.exists(audio_file):
                    success = accelerate_audio(original_audio_file, self.speed_factor, audio_file)
                    if not success:
                        print("使用原始音頻播放")
                        audio_file = original_audio_file
                    else:
                        self.accelerate_audios.append(audio_file)

            print(f"Playing: {audio_file}")
            try:
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.play(loops=0)
            except Exception as e:
                print(f"播放音頻出錯: {e}")
                return

            # 更新字幕
            self.text_label.config(text=subtitle)
            # 開始輪詢檢測當前音頻是否播放結束
            self._check_audio_finished()
        else:
            print("所有音頻播放完畢。")
            self.text_label.config(text="播放完畢！")

    def _check_audio_finished(self):
        """
        輪詢檢查當前音頻是否播放完畢。如果播放完畢，則調用 _next_subtitle()；否則每隔 100 毫秒檢查一次。
        """
        if self.is_paused:
            return

        if not pygame.mixer.music.get_busy():
            self._next_subtitle()
        else:
            self.after_id = self.text_label.after(100, self._check_audio_finished)

    def _next_subtitle(self):
        """
        當前音頻播放完畢後，切換到下一段音頻和字幕。
        """
        # 清除當前計時器 id
        if self.after_id:
            self.text_label.after_cancel(self.after_id)
            self.after_id = None

        self.current_subtitle_index += 1
        if self.current_subtitle_index < len(self.audios):
            self._play_audio_and_update_subtitles()
        else:
            print("所有音頻播放完畢。")
            self.text_label.config(text="播放完畢！")

    def toggle_play(self):
        """
        切換播放/暫停狀態：
         - 若正在播放且未暫停，則暫停音頻並取消輪詢；
         - 若處於暫停狀態，則恢復播放並重新啟動輪詢；
         - 若未播放，則從頭開始播放。
        """
        if pygame.mixer.music.get_busy() and not self.is_paused:
            print("暫停播放")
            self.is_paused = True
            pygame.mixer.music.pause()
            if self.after_id:
                self.text_label.after_cancel(self.after_id)
                self.after_id = None
        elif self.is_paused:
            print("恢復播放")
            self.is_paused = False
            pygame.mixer.music.unpause()
            self._check_audio_finished()
        else:
            print("開始播放")
            self.is_paused = False
            self.current_subtitle_index = 0
            self._play_audio_and_update_subtitles()

# 示例建立 GUI 視窗
def create_ui():
    root = tk.Tk()
    root.title("音頻播放器")

    # 你的音頻文件和字幕文本
    text_lines = [
        "第一行小說內容：書名。",
        "第二行小說內容。第二行小說內容第二行小說內容。",
        "第三行小說內容。內容是：小說內容",
        "第四行小說內容。即將結束。",
    ]
    audios = [strPath__localGenAudioForNovelContent("output\\", text_line, f"{index+1}.mp3") for index, text_line in enumerate(text_lines)]

    # 標籤顯示字幕
    text_label = tk.Label(root, text="", font=("Arial", 20))
    text_label.pack(pady=20)

    # 建立音頻播放器實例
    player = AudioPlayer(audios, text_lines, text_label, speed_factor=1.5)  # 假設播放速度是 1.5 倍

    # 播放按鈕
    play_button = tk.Button(root, text="播放/暂停", command=player.toggle_play, font=("Arial", 14))
    play_button.pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    create_ui()
