import subprocess
import shutil
import re


def check_ffmpeg():
    """Check if ffmpeg is available in PATH."""
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_path():
    path = shutil.which("ffmpeg")
    if path is None:
        raise FileNotFoundError(
            "找不到 FFmpeg，請先安裝 FFmpeg 並加入系統 PATH。\n"
            "下載地址: https://ffmpeg.org/download.html"
        )
    return path


def get_ffprobe_path():
    path = shutil.which("ffprobe")
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
    cmd = [ffmpeg, "-y", "-progress", "pipe:1", "-nostats"] + args

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

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
    stderr_output = process.stderr.read()
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg 錯誤:\n{stderr_output}")
    return stderr_output
