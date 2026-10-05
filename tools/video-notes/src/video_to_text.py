import os
import torch
from src.core.video_to_audio import extract_audio
from src.core.audio_to_text import transcribe_to_text
from src.core.text_ai_summary import summarize_text_with_ai
from src.core.youtube_downloader import download_youtube


def full_youtube_to_summary(
    url: str,
    filename: str | None = "my_meeting",
    mode: str | None = None,
):
    """
    完整流程：
        1. 下載 YouTube 影片
        2. 抽音成 wav
        3. 文字轉錄 txt
        4. AI 重點整理

    Args:
        url: video URL
        filename: base name, or ``None`` to let yt-dlp use the title
        mode: download mode used by :func:`src.core.youtube_downloader.download_youtube`
            (e.g. ``"best-video"``).  When omitted the default within the
            downloader is used.
    """
    # 絕對路徑
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data"))
    # print(BASE_DIR)
    os.makedirs(BASE_DIR, exist_ok=True)

    video_id = ""
    if "/shorts/" in url:
        video_id = "v(" + url.split("/shorts/")[-1] + ")"
    elif "watch?v=" in url:
        video_id = "s(" + url.split("watch?v=")[-1] + ")"
    else:
        video_id = "x(" + url[-11::] + ")"

    # 影片下載
    try:
        if filename is None:
            video_path, filename = download_youtube(
                url,
                output_folder=BASE_DIR,
                mode=mode if mode is not None else "best-audio",
            )
        else:
            video_path, filename = download_youtube(
                url,
                output_folder=BASE_DIR,
                filename=f"{filename}[{video_id}]",
                mode=mode if mode is not None else "best-audio",
            )
        # download_youtube already prints completion message
    except Exception as e:
        print("影片下載失敗:", e)
        return

    audio_path = os.path.join(BASE_DIR, f"{filename}[{video_id}].wav")
    txt_path   = os.path.join(BASE_DIR, f"{filename}[{video_id}].txt")
    summary_txt_path   = os.path.join(BASE_DIR, f"{filename}[{video_id}].summary.txt")

    # 1️⃣ 抽音
    print(f"開始抽音: {video_path} -> {audio_path}")
    extract_audio(video_path, audio_path)
    print("音訊抽取完成")

    # 2️⃣ 文字轉錄
    print(f"GPU 可用: {torch.cuda.is_available()}")
    print(f"開始轉錄文字: {audio_path} -> {txt_path}")
    transcribe_to_text(audio_path, txt_path)
    print("文字轉錄完成")

    # 3️⃣ AI 重點整理
    summary = summarize_text_with_ai(
        txt_path,
        api="chatgpt",
        prompt_head="以下是一段影片的逐字稿，請幫我進行重點整理，保留核心資訊並越簡潔越好：\n\n"
    )

    print(f"開始轉錄文字: {txt_path} -> {summary_txt_path}")
    print("==== AI 重點整理 ====")
    print(summary)
    with open(summary_txt_path, 'w', encoding='utf-8') as file:
        file.write(f"[{video_id}]\n")
        file.write(summary)
    return summary


if __name__ == "__main__":
    url = input("URL ------------> ").strip()
    if not url:
        print("請輸入正確 YouTube 影片 URL")
    else:
        # user could ask for different download mode here if desired
        summary = full_youtube_to_summary(url, filename="meeting")
