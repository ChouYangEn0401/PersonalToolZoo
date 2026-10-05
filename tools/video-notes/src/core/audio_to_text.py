from faster_whisper import WhisperModel
import time

def transcribe_to_text(input_audio: str, output_txt: str, model_size="medium", device="cuda"):
    """
    將 wav 音訊轉成文字 txt (自動 VAD 切段)
    GPU 即時運算，邊產生邊印字
    """
    start = time.time()
    print(f"開始轉錄文字: {input_audio} -> {output_txt}")

    model = WhisperModel(model_size, device=device, compute_type="float16" if device=="cuda" else "int8")

    segments, info = model.transcribe(
        input_audio,
        language="zh",
        vad_filter=True
    )

    with open(output_txt, "w", encoding="utf-8") as f:
        for seg in segments:
            # line = f"[{seg.start:.2f} - {seg.end:.2f}] {seg.text}\n"
            line = f"{seg.text}\n"
            print(line, end="")  # 🔹 即時印出
            f.write(line)

    elapsed = time.time() - start
    print(f"\n文字轉錄完成 ({elapsed:.1f} 秒)")
