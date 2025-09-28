#!/usr/bin/env python3
"""
創建 chips 模板佔位符 - 用於讓系統正常運行
"""
import os
from PIL import Image, ImageDraw, ImageFont

def create_chip_template(value, color, filename):
    """創建籌碼模板佔位符"""
    # 創建 50x50 的圓形籌碼模板
    size = (50, 50)
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 畫圓形籌碼
    draw.ellipse([2, 2, 47, 47], fill=color, outline='white', width=2)

    # 添加數字 (簡單字體)
    try:
        # 嘗試使用系統字體
        font = ImageFont.truetype("arial.ttf", 12)
    except:
        # 後備字體
        font = ImageFont.load_default()

    # 計算文字位置 (居中)
    text = str(value)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (size[0] - text_width) // 2
    text_y = (size[1] - text_height) // 2

    draw.text((text_x, text_y), text, fill='white', font=font)

    # 保存檔案
    img.save(filename, 'PNG')
    print(f"Created chip template: {filename}")

def main():
    """主函數"""
    os.makedirs("templates/chips", exist_ok=True)

    # 創建基本的籌碼模板
    chips = [
        (100, (0, 128, 0), "templates/chips/chip_100.png"),      # 綠色
        (1000, (0, 0, 255), "templates/chips/chip_1k.png"),     # 藍色
        (5000, (255, 0, 0), "templates/chips/chip_5k.png"),     # 紅色
        (10000, (128, 0, 128), "templates/chips/chip_10k.png"), # 紫色
        (50000, (255, 215, 0), "templates/chips/chip_50k.png")  # 金色
    ]

    for value, color, filename in chips:
        create_chip_template(value, color, filename)

    print(f"\nCreated {len(chips)} chip template placeholders")
    print("Note: These are placeholder templates for testing.")
    print("Replace with real game screenshots for production use.")

if __name__ == "__main__":
    main()