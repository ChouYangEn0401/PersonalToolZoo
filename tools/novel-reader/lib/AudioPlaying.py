import subprocess

vlc_path = "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"

def VLCPlayAudio(mp3_path):
    global vlc_path
    # 使用 VLC 播放音頻，隱藏界面並在播放完成後關閉
    print("[DEBUG] Playing audio with VLC in background...")
    subprocess.Popen(
        [vlc_path, mp3_path, "--intf", "dummy", "--play-and-exit"],
        stdout=subprocess.DEVNULL,  # 靜音 VLC 的輸出
        stderr=subprocess.DEVNULL  # 靜音 VLC 的錯誤輸出
    )
    print("[DEBUG] VLC started in background.")

