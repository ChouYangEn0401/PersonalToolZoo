import os
from core.ffmpeg_utils import run_ffmpeg, get_video_duration

VIDEO_FORMATS = {
    "MP4":  {"ext": ".mp4",  "args": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k"]},
    "AVI":  {"ext": ".avi",  "args": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "mp3", "-b:a", "192k"]},
    "MKV":  {"ext": ".mkv",  "args": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k"]},
    "MOV":  {"ext": ".mov",  "args": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k"]},
    "WEBM": {"ext": ".webm", "args": ["-c:v", "libvpx-vp9", "-crf", "20", "-b:v", "0", "-c:a", "libopus", "-b:a", "192k"]},
    "FLV":  {"ext": ".flv",  "args": ["-c:v", "flv1", "-q:v", "2", "-c:a", "mp3", "-b:a", "192k"]},
    "WMV":  {"ext": ".wmv",  "args": ["-c:v", "wmv2", "-q:v", "2", "-c:a", "wmav2", "-b:a", "192k"]},
    "TS":   {"ext": ".ts",   "args": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k"]},
    "GIF":  {"ext": ".gif",  "args": ["-vf", "fps=15,scale=480:-1:flags=lanczos"]},
    "MP3":  {"ext": ".mp3",  "args": ["-vn", "-c:a", "libmp3lame", "-b:a", "320k"]},
    "WAV":  {"ext": ".wav",  "args": ["-vn", "-c:a", "pcm_s16le"]},
    "FLAC": {"ext": ".flac", "args": ["-vn", "-c:a", "flac"]},
    "AAC":  {"ext": ".aac",  "args": ["-vn", "-c:a", "aac", "-b:a", "256k"]},
}

INPUT_VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
    ".ts", ".m4v", ".3gp", ".mpg", ".mpeg", ".vob", ".ogv",
    ".m2ts", ".mts",
}


def convert_video(input_path, output_dir, output_format, progress_callback=None):
    """Convert a video file. Returns output path."""
    if output_format not in VIDEO_FORMATS:
        raise ValueError(f"不支援的格式: {output_format}")

    fmt = VIDEO_FORMATS[output_format]
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(output_dir, base_name + fmt["ext"])

    duration = get_video_duration(input_path)
    args = ["-i", input_path] + fmt["args"] + [output_path]
    run_ffmpeg(args, duration=duration, progress_callback=progress_callback)
    return output_path
