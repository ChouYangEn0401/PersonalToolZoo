from faster_whisper import WhisperModel
import time

def srt_time(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def transcribe_to_srt(input_audio: str, output_srt: str, model_size="medium", device="cuda"):
    """
    將 wav 音訊轉成 SRT 字幕，GPU 即時運算，邊跑邊印字
    """
    start = time.time()
    print(f"開始轉錄 SRT: {input_audio} -> {output_srt}")

    model = WhisperModel(model_size, device=device, compute_type="float16" if device=="cuda" else "int8")

    segments, info = model.transcribe(
        input_audio,
        language="zh",
        vad_filter=True
    )

    with open(output_srt, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            print(f"[{seg.start:.2f} - {seg.end:.2f}] {seg.text}")  # 🔹 即時印出
            f.write(f"{i}\n")
            f.write(f"{srt_time(seg.start)} --> {srt_time(seg.end)}\n")
            f.write(f"{seg.text.strip()}\n\n")

    elapsed = time.time() - start
    print(f"SRT 產生完成 ({elapsed:.1f} 秒)")
