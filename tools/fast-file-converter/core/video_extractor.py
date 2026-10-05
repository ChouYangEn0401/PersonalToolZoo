import os
from core.ffmpeg_utils import run_ffmpeg, get_video_duration, get_video_frame_count

FRAME_FORMATS = ["PNG", "JPEG"]
AUDIO_FORMATS = {
    "WAV":  {"ext": ".wav",  "args": ["-c:a", "pcm_s16le"]},
    "MP3":  {"ext": ".mp3",  "args": ["-c:a", "libmp3lame", "-b:a", "320k"]},
    "AAC":  {"ext": ".aac",  "args": ["-c:a", "aac", "-b:a", "256k"]},
    "FLAC": {"ext": ".flac", "args": ["-c:a", "flac"]},
}


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def extract_frames(input_path, output_dir, frame_format="PNG", progress_callback=None):
    """Extract all frames from a video into output_dir/video_name/frames/."""
    video_name = os.path.splitext(os.path.basename(input_path))[0]
    frames_dir = _ensure_dir(os.path.join(output_dir, video_name, "frames"))

    ext = ".png" if frame_format == "PNG" else ".jpg"
    pattern = os.path.join(frames_dir, f"frame_%06d{ext}")

    duration = get_video_duration(input_path)
    codec_args = ["-c:v", "png"] if frame_format == "PNG" else ["-q:v", "2"]
    args = ["-i", input_path] + codec_args + [pattern]
    run_ffmpeg(args, duration=duration, progress_callback=progress_callback)
    return frames_dir


def extract_audio(input_path, output_dir, audio_format="WAV", progress_callback=None):
    """Extract audio from a video into output_dir/video_name/audio/."""
    if audio_format not in AUDIO_FORMATS:
        raise ValueError(f"不支援的音訊格式: {audio_format}")

    video_name = os.path.splitext(os.path.basename(input_path))[0]
    audio_dir = _ensure_dir(os.path.join(output_dir, video_name, "audio"))

    fmt = AUDIO_FORMATS[audio_format]
    output_path = os.path.join(audio_dir, f"audio{fmt['ext']}")

    duration = get_video_duration(input_path)
    args = ["-i", input_path, "-vn"] + fmt["args"] + [output_path]
    run_ffmpeg(args, duration=duration, progress_callback=progress_callback)
    return output_path


def extract_all(input_path, output_dir, frame_format="PNG", audio_format="WAV", progress_callback=None):
    """Extract both frames and audio. Returns (frames_dir, audio_path)."""
    def frame_progress(p):
        if progress_callback:
            progress_callback(p * 0.8)  # Frames take ~80% of effort

    def audio_progress(p):
        if progress_callback:
            progress_callback(80 + p * 0.2)

    frames_dir = extract_frames(input_path, output_dir, frame_format, frame_progress)
    audio_path = extract_audio(input_path, output_dir, audio_format, audio_progress)
    return frames_dir, audio_path
