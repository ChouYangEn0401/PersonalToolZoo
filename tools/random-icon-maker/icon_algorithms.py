"""9 種產生圖示的演算法（源自 GeneratedImageExporter.py，數學一字不改）。

同一個種子、同一個尺寸，產生的圖跟舊版逐像素相同（tests/ 有對照舊版輸出的測試）：
- 亂數的呼叫順序不能變：舊版是 x 外圈、y 內圈，而且 9 個演算法照順序共用同一串亂數。
- 繼續用 ImageDraw.point 畫：有些演算法會算出負數（例如正弦波的綠色），point 會把它夾到 0–255，
  換成別的寫法結果就會不一樣。速度夠用（256×256 九張約 0.5 秒）。
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw


def _render(width, height, pixel):
    """依舊版的順序（x 外圈、y 內圈）算出每個像素，再一次畫上去。"""
    img = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(img)
    # 舊版直接把可能超出 0–255 的值交給 draw.point，由 Pillow 處理；這裡也交給同一個函式，結果才會一致
    for x in range(width):
        for y in range(height):
            draw.point((x, y), pixel(x, y))
    return img


def gradient_1(width, height):
    """平滑的水平和垂直漸層。"""
    return _render(width, height, lambda x, y: (int(x * 255 / width), int(y * 255 / height), (x + y) % 255, 255))


def gradient_2(width, height):
    """平滑的圓形漸層。"""
    cx, cy = width // 2, height // 2
    max_d = math.sqrt(cx ** 2 + cy ** 2)

    def px(x, y):
        intensity = int(255 * (1 - math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / max_d))
        return (intensity, (intensity + random.randint(-20, 20)) % 255, 255 - intensity, 255)
    return _render(width, height, px)


def gradient_3(width, height):
    """條紋漸層。"""
    stripe = 10

    def px(x, y):
        on = ((x // stripe) + (y // stripe)) % 2
        r = (x * 255 // width if on else random.randint(100, 255)) % 255
        g = (y * 255 // height if on else random.randint(100, 255)) % 255
        return (r, g, (r + g) % 255, 255)
    return _render(width, height, px)


def gradient_4(width, height):
    """棋盤格。"""
    block = 8

    def px(x, y):
        white = ((x // block) + (y // block)) % 2 == 0
        r = 255 if white else random.randint(50, 200)
        g = 255 if not white else random.randint(50, 200)
        return (r, g, (r + g) % 255, 255)
    return _render(width, height, px)


def gradient_5(width, height):
    """放射狀漸層。"""
    cx, cy = width // 2, height // 2
    max_d = math.sqrt(cx ** 2 + cy ** 2)

    def px(x, y):
        intensity = int(255 * (1 - math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / max_d))
        r = (intensity + (x % 50)) % 255
        g = (intensity + (y % 100)) % 255
        return (r, g, (r + g) % 255, 255)
    return _render(width, height, px)


def sine_wave(width, height):
    """非線性漸層（正弦、餘弦）。"""
    return _render(width, height, lambda x, y: (
        int(255 * math.sin(math.pi * x / width)), int(255 * math.cos(math.pi * y / height)),
        int(255 * ((x * y) % 255) / 255), 255))


def noisy(width, height):
    """加上隨機雜訊的漸層。"""
    def px(x, y):
        r = int(x * 255 / width) + random.randint(-20, 20)
        g = int(y * 255 / height) + random.randint(-20, 20)
        b = ((x + y) % 255) + random.randint(-20, 20)
        return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), 255)
    return _render(width, height, px)


def diagonal(width, height):
    """對角線漸層。"""
    def px(x, y):
        d = int((x + y) * 255 / (width + height))
        return (d, (d * 2) % 255, (d * 3) % 255, 255)
    return _render(width, height, px)


def layered(width, height):
    """疊加多個漸層效果。"""
    return _render(width, height, lambda x, y: (
        int((x + y) * 128 / (width + height)) % 255,
        int((x * y) * 255 / (width * height)) % 255,
        int(abs(128 - x * y * 255 / (width * height))) % 255, 255))


# 順序不能改：舊版的檔名 algo1…algo9 就是這個順序，亂數也照這個順序被消耗
ALGORITHMS = [
    ("algo1", "水平垂直漸層", gradient_1),
    ("algo2", "圓形漸層", gradient_2),
    ("algo3", "條紋", gradient_3),
    ("algo4", "棋盤格", gradient_4),
    ("algo5", "放射狀", gradient_5),
    ("algo6", "正弦波", sine_wave),
    ("algo7", "雜訊漸層", noisy),
    ("algo8", "對角線", diagonal),
    ("algo9", "疊加", layered),
]


def generate_all(seed: int, size: int = 64) -> list[tuple[str, str, Image.Image]]:
    """跟舊版一樣：設定一次種子，9 個演算法依序共用同一串亂數。"""
    random.seed(seed)
    return [(key, name, fn(size, size)) for key, name, fn in ALGORITHMS]
