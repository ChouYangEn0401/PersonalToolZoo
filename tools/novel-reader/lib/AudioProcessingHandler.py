from gtts import gTTS
from pydub import AudioSegment
import pyttsx3
import os
import subprocess

# 文字轉語音並保存為 MP3
def strPath__localGenAudioForNovelContent(global__CurrentSavingPath, text, output_filename_without_path):
    mp3_path = f"{global__CurrentSavingPath}{output_filename_without_path}"
    # 初始化 pyttsx3 引擎
    engine = pyttsx3.init()
    # 设置语音参数（可选）
    engine.setProperty('rate', 150)  # 设置语速
    engine.setProperty('volume', 1)  # 设置音量，范围是 [0.0, 1.0]
    # 将文本转换成语音并保存为文件
    engine.save_to_file(text, mp3_path)
    engine.runAndWait()
    print(f"语音文件已保存：{mp3_path}")
    return mp3_path

# 文字轉語音並保存為 MP3
def strPath__gttsGenAudioForNovelContent(global__CurrentSavingPath, text, output_filename_without_path, lang="zh-TW"):
    # 使用 gTTS 生成語音
    tts = gTTS(text=text, lang=lang, slow=False)
    mp3_path = f"{global__CurrentSavingPath}{output_filename_without_path}_.mp3"
    tts.save(mp3_path)
    mp3_path = gttsIncaseAudioRepair(mp3_path, f"{global__CurrentSavingPath}{output_filename_without_path}")
    print(f"語音檔已儲存：{mp3_path}")
    return mp3_path

def gttsIncaseAudioRepair(mp3_path, new_name):
    absolute_audio_path = os.path.abspath(mp3_path)
    absolute_new_name = os.path.abspath(new_name)
    command = f"ffmpeg -y -i \"{absolute_audio_path}\" -c:a libmp3lame -b:a 192k \"{absolute_new_name}\""
    try:
        subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"File converted successfully: {new_name}")
        os.remove(mp3_path)
        return new_name
    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")
        return mp3_path

# 文字轉語音並保存為 MP3
def strPath__gttsGenAudioForNovelContentWithSegementControl(global__CurrentSavingPath, stringList, output_filename_without_path, lang="zh-TW", max_chunk_length=1000):
    # Init Check
    len_ = len(stringList)
    if stringList is None:
        return ""
    elif len_==0:
        return ""

    # Chunk Split Gen
    mp3_paths = []
    text = ""
    index = 0
    while index < len_:
        if len(text) + len(stringList[index]) + 1 < max_chunk_length:
            text = text + "\n" + stringList[index]
        else:
            mp3_path = strPath__gttsGenAudioForNovelContent(global__CurrentSavingPath, text, output_filename_without_path.replace(".mp3", f"_{len(mp3_paths) + 1}.mp3"), lang)
            mp3_paths.append(global__CurrentSavingPath + '\\' + mp3_path)
            text = stringList[index]
        index = index + 1
    if text:
        mp3_path = strPath__gttsGenAudioForNovelContent(global__CurrentSavingPath, text, output_filename_without_path.replace(".mp3", f"_{len(mp3_paths) + 1}.mp3"), lang)
        mp3_paths.append(global__CurrentSavingPath + '\\' + mp3_path)
        text = ""

    # Combine MP3s To Final One
    final_audio = AudioSegment.empty()
    for path in mp3_paths:
        audio = AudioSegment.from_mp3(path)
        final_audio += audio
        os.remove(path)

    # Save File And Return Path
    final_mp3_path = f"{global__CurrentSavingPath}{output_filename_without_path}.mp3"
    final_audio.export(final_mp3_path, format="mp3")
    print(f"合併後的語音檔已儲存：{final_mp3_path}")
    return final_mp3_path


def SpeedUpAudio(ori_mp3_path, out_mp3_path, speed_factor):
    print(f"[DEBUG] Loading and speeding up (x{speed_factor}) audio with pydub...")
    # 使用 pydub 加速音頻
    sound = AudioSegment.from_mp3(ori_mp3_path)
    print(f"音频时长: {len(sound) / 1000} 秒")
    sound = sound.speedup(playback_speed=speed_factor)  # 加速播放
    sound.export(out_mp3_path, format="mp3")
    print(f"[DEBUG] Exported accelerated audio to {out_mp3_path}")

