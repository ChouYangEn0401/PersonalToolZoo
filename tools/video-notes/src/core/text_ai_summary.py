import re
from typing import Literal
from ntu_easy_llm import ask_chatgpt, ask_gemini

def summarize_text_with_ai(input_txt_path: str, api: Literal["chatgpt", "gemini"] = "chatgpt", prompt_head: str = None) -> str:
    """
    1️⃣ 讀取文字檔
    2️⃣ 將多行合併成完整段落
    3️⃣ 呼叫指定 AI API 做重點整理
    input_txt_path: TXT 檔路徑
    api: "chatgpt" 或 "gemini"
    return: AI 回傳的摘要文字
    """

    # 1️⃣ 讀檔
    with open(input_txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 2️⃣ 合併成段落
    # 移除空行，並把斷行的文字接成完整段落
    paragraphs = []
    current_para = ""
    for line in lines:
        line = line.strip()
        if not line:
            if current_para:
                paragraphs.append(current_para)
                current_para = ""
        else:
            # 移除開頭的時間戳 [0.00 - 5.23]
            line = re.sub(r"^\[\d+\.\d+ - \d+\.\d+\]\s*", "", line)
            current_para += line + " "
    if current_para:
        paragraphs.append(current_para)

    # 3️⃣ 組成完整文章
    full_text = "\n".join(paragraphs)

    # 4️⃣ 呼叫 AI
    prompt = (
        # "以下是一段會議記錄文字，請幫我整理成簡明重點清單，保留核心資訊，不需要逐字稿：\n\n"
        (prompt_head or "以下是一段影片的逐字稿，請幫我整理成簡明重點清單，保留核心資訊，越簡潔明瞭越好：\n\n")
        + full_text
    )

    if api.lower() == "chatgpt":
        summary = ask_chatgpt(prompt)
    elif api.lower() == "gemini":
        summary = ask_gemini(prompt)
    else:
        raise ValueError("API 參數只能是 'chatgpt' 或 'gemini'")

    return summary
