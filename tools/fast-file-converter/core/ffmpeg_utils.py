import os
import subprocess
import shutil
import threading

# PATH 上找不到時再看這些常見的安裝位置
_COMMON_DIRS = (r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin")


def _find(name):
    path = shutil.which(name)
    if path:
        return path
    for folder in _COMMON_DIRS:
        candidate = os.path.join(folder, name + ".exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def check_ffmpeg():
    """Check if ffmpeg is available."""
    return _find("ffmpeg") is not None


def get_ffmpeg_path():
    path = _find("ffmpeg")
    if path is None:
        raise FileNotFoundError(
            "找不到 FFmpeg，請先安裝 FFmpeg 並加入系統 PATH。\n"
            "下載地址: https://ffmpeg.org/download.html"
        )
    return path


def get_ffprobe_path():
    path = _find("ffprobe")
    if path is None:
        raise FileNotFoundError("找不到 FFprobe，請確認 FFmpeg 安裝完整。")
    return path


def get_video_duration(input_path):
    """Get video duration in seconds using ffprobe."""
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0


def get_video_frame_count(input_path):
    """Get total frame count of a video."""
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-count_packets",
        "-show_entries", "stream=nb_read_packets",
        "-of", "csv=p=0",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        return int(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0


def run_ffmpeg(args, duration=0, progress_callback=None):
    """Run ffmpeg with optional progress tracking via -progress pipe:1."""
    ffmpeg = get_ffmpeg_path()
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "warning", "-progress", "pipe:1", "-nostats"] + args

    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    ) as process:
        # stderr 要另外開執行緒同時讀：原本等 stdout 讀完才讀 stderr，ffmpeg 的警告一多（超過管線緩衝區）
        # 它就會卡在寫 stderr、我們卡在等 stdout，兩邊互等永遠不會結束
        stderr_chunks = []
        reader = threading.Thread(target=lambda: stderr_chunks.append(process.stderr.read()), daemon=True)
        reader.start()

        if progress_callback and duration > 0:
            for line in process.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        time_us = int(line.split("=")[1])
                        current_sec = time_us / 1_000_000
                        progress = min(current_sec / duration * 100, 100)
                        progress_callback(progress)
                    except (ValueError, IndexError):
                        pass
        else:
            process.stdout.read()

        process.wait()
        reader.join()
    stderr_output = "".join(stderr_chunks)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg 錯誤:\n{stderr_output}")
    return stderr_output
