from PIL import Image, ImageDraw
import random
import math
import os
from datetime import datetime


def generate_filename_with_datetime(seed, prefix, extension="ico"):
    # 獲取當前時間
    now = datetime.now()
    
    # 格式化日期和時間
    timestamp = now.strftime("%Y-%m-%d %H-%M-%S")
    
    # 組合成文件名
    filename = f"[{timestamp}] {prefix}({seed}).{extension}"
    
    return filename


# 生成五個不同的圖像算法（修正後）
def generate_gradient_1(width, height):
    """Algorithm 1: 平滑的水平和垂直漸變。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    for x in range(width):
        for y in range(height):
            r = int(x * 255 / width)
            g = int(y * 255 / height)
            b = (x + y) % 255
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_2(width, height):
    """Algorithm 2: 平滑的圓形漸變。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    center_x, center_y = width // 2, height // 2
    max_distance = math.sqrt(center_x**2 + center_y**2)
    for x in range(width):
        for y in range(height):
            distance = math.sqrt((x - center_x)**2 + (y - center_y)**2)
            intensity = int(255 * (1 - distance / max_distance))
            r = intensity
            g = (intensity + random.randint(-20, 20)) % 255
            b = 255 - intensity
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_3(width, height):
    """Algorithm 3: 改良的條紋漸變。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    stripe_width = 10
    for x in range(width):
        for y in range(height):
            stripe_color = ((x // stripe_width) + (y // stripe_width)) % 2
            r = (x * 255 // width if stripe_color else random.randint(100, 255)) % 255
            g = (y * 255 // height if stripe_color else random.randint(100, 255)) % 255
            b = (r + g) % 255
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_4(width, height):
    """Algorithm 4: 改良的棋盤格樣式。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    block_size = 8
    for x in range(width):
        for y in range(height):
            is_white = ((x // block_size) + (y // block_size)) % 2 == 0
            r = 255 if is_white else random.randint(50, 200)
            g = 255 if not is_white else random.randint(50, 200)
            b = (r + g) % 255
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_5(width, height):
    """Algorithm 5: 改良的放射狀漸變。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    center_x, center_y = width // 2, height // 2
    max_distance = math.sqrt(center_x**2 + center_y**2)
    for x in range(width):
        for y in range(height):
            distance = math.sqrt((x - center_x)**2 + (y - center_y)**2)
            intensity = int(255 * (1 - distance / max_distance))
            r = (intensity + (x % 50)) % 255
            g = (intensity + (y % 100)) % 255
            b = (r + g) % 255
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_1_modified_001(width, height):
    """非线性梯度，使用正弦和余弦变化。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    for x in range(width):
        for y in range(height):
            r = int(255 * math.sin(math.pi * x / width))
            g = int(255 * math.cos(math.pi * y / height))
            b = int(255 * ((x * y) % 255) / 255)
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_1_modified_002(width, height):
    """引入随机噪声的梯度。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    for x in range(width):
        for y in range(height):
            r = int(x * 255 / width) + random.randint(-20, 20)
            g = int(y * 255 / height) + random.randint(-20, 20)
            b = ((x + y) % 255) + random.randint(-20, 20)
            r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_1_modified_003(width, height):
    """对角线梯度。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    for x in range(width):
        for y in range(height):
            d = int((x + y) * 255 / (width + height))
            r = d
            g = (d * 2) % 255
            b = (d * 3) % 255
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img

def generate_gradient_1_modified_004(width, height):
    """分层梯度，叠加多个渐变效果。"""
    img = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(img)
    for x in range(width):
        for y in range(height):
            r = int((x + y) * 128 / (width + height)) % 255
            g = int((x * y) * 255 / (width * height)) % 255
            b = int(abs(128 - x * y * 255 / (width * height))) % 255
            a = 255
            draw.point((x, y), (r, g, b, a))
    return img


seed = 0
# 保存所有圖像到 .ico 文件
def save_icons():
    global seed
    havePass = False
    width, height = 64, 64
    algorithms = [
                    generate_gradient_1, generate_gradient_2, generate_gradient_3, generate_gradient_4, generate_gradient_5, 
                    generate_gradient_1_modified_001, generate_gradient_1_modified_002, generate_gradient_1_modified_003, 
                    generate_gradient_1_modified_004
                ]

    # 請求用戶輸入 seed 值
    try:
        seeds = input("請輸入 seed 值 (-1000000 到 1000000): ")
        if ', ' in seeds:
            seeds = [int(x) for x in seeds.split(', ')]
        else:
            seeds = [int(seeds)]
    except ValueError:
        seed = random.randint(-1000000, 1000000)
        print(f"輸入錯誤，已隨機選擇 seed 值：{seed}")
    
    for seed in seeds:
        if not (-1000000 <= seed <= 1000000):
            havePass = True
            print(f"輸入值({seed})超出範圍")
        else:     
            # 設定隨機種子
            random.seed(seed)

            # 生成並保存圖標
            for idx, algo in enumerate(algorithms, start=1):
                img = algo(width, height)
                filename = f"algo{idx}"
                img.save(generate_filename_with_datetime(seed, filename), format='ICO')
                print(f"Saved {filename} using seed {seed}")
    return havePass

# 調用函數保存圖像
if save_icons():
    os.system("pause")
