import traceback
from gtts import gTTS
from pydub import AudioSegment
import subprocess
import os

# 確保臨時目錄存在
temp_dir = "temp"
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir, exist_ok=True)

# VLC 可執行文件的路徑（如果需要，請替換為 VLC 的安裝路徑）
vlc_path = "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"

# 文字轉語音並保存為 MP3
def text_to_speech_with_vlc_in_background(text, lang="zh", speed_factor=1.5):
    try:
        print("[DEBUG] Generating speech with gTTS...")
        # 使用 gTTS 生成語音
        tts = gTTS(text=text, lang=lang, slow=False)
        mp3_path = f"{temp_dir}/output.mp3"
        tts.save(mp3_path)
        
        print("[DEBUG] Loading and speeding up audio with pydub...")
        # 使用 pydub 加速音頻
        sound = AudioSegment.from_mp3(mp3_path)
        sound = sound.speedup(playback_speed=speed_factor)  # 加速播放
        fast_mp3_path = f"{temp_dir}/output_fast.mp3"
        sound.export(fast_mp3_path, format="mp3")
        print(f"[DEBUG] Exported accelerated audio to {fast_mp3_path}")

        print("[DEBUG] Playing audio with VLC in background...")
        # 使用 VLC 播放音頻，隱藏界面並在播放完成後關閉
        subprocess.Popen(
            [vlc_path, fast_mp3_path, "--intf", "dummy", "--play-and-exit"],
            stdout=subprocess.DEVNULL,  # 靜音 VLC 的輸出
            stderr=subprocess.DEVNULL  # 靜音 VLC 的錯誤輸出
        )
        print("[DEBUG] VLC started in background.")
    except Exception as e:
        print("\n[Error Occurred]")
        traceback.print_exc()
    finally:
        print(f"[DEBUG] Finished processing text: {text}")

if __name__ == "__main__":
    try:
        # 使用示例
        text = "你好, 默默搭，我是你的機器人助理."
        text_to_speech_with_vlc_in_background(text)
    except Exception as e:
        # 捕獲並顯示詳細錯誤資訊
        print("\n[Error Occurred]")
        traceback.print_exc()
    finally:
        # 確保程序結束時提供緩衝時間
        input("\n程序已結束。按 Enter 鍵退出...")
