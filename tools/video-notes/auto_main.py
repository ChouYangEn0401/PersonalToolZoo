from src.video_to_text import full_youtube_to_summary


if __name__ == "__main__":
    url = input("URL ------------> ").strip()
    if not url:
        print("請輸入正確 YouTube 影片 URL")
    else:
        summary = full_youtube_to_summary(url, filename=None)

