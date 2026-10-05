from src.core.video_to_audio import extract_audio
from src.core.audio_to_srt import transcribe_to_srt

# 1️⃣ 抽音
extract_audio("../data/meeting.mp4", "../data/meeting.wav")

# 3️⃣ 產生 SRT
transcribe_to_srt("../data/meeting.wav", "../data/meeting.srt")
