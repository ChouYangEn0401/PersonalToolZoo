import ffmpeg
import time


def extract_audio(input_video: str, output_audio: str) -> None:
    """
    將影片抽取成 wav 音訊 (單聲道 16kHz)
    input_video: 影片檔路徑 (mp4)
    output_audio: 輸出音訊路徑 (wav)
    """
    start = time.time()
    print(f"開始抽音: {input_video} -> {output_audio}")

    (
        ffmpeg
        .input(input_video)
        .output(
            output_audio,
            ac=1,  # 單聲道
            ar=16000,  # 16kHz
            format="wav"
        )
        .overwrite_output()
        .run(quiet=True)
    )

    elapsed = time.time() - start
    print(f"音訊抽取完成 ({elapsed:.1f} 秒)")
