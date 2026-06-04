"""
测试 Tesseract 识别验证码的不同预处理方案
"""

import os
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CAPTCHA_PATH = r"D:\BaiduSyncdisk\claude\Contract Sentinel\data\logs\login_captcha_20260511_124104.png"

def method1_grayscale_only(img):
    """方案1：仅灰度化"""
    return img.convert('L').resize((img.width * 3, img.height * 3), Image.LANCZOS)

def method2_contrast(img):
    """方案2：灰度 + 对比度增强"""
    img = img.convert('L').resize((img.width * 3, img.height * 3), Image.LANCZOS)
    enhancer = ImageEnhance.Contrast(img)
    return enhancer.enhance(2.0)

def method3_binary_low(img):
    """方案3：灰度 + 低阈值二值化"""
    img = img.convert('L').resize((img.width * 3, img.height * 3), Image.LANCZOS)
    return img.point(lambda x: 0 if x < 180 else 255, '1')

def method4_binary_high(img):
    """方案4：灰度 + 高阈值二值化"""
    img = img.convert('L').resize((img.width * 3, img.height * 3), Image.LANCZOS)
    return img.point(lambda x: 0 if x < 120 else 255, '1')

def method5_sharpen(img):
    """方案5：灰度 + 锐化 + 对比度"""
    img = img.convert('L').resize((img.width * 3, img.height * 3), Image.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    enhancer = ImageEnhance.Contrast(img)
    return enhancer.enhance(2.5)

def test_all_methods():
    img = Image.open(CAPTCHA_PATH)
    print(f"原始图片尺寸: {img.size}")
    print(f"原始图片模式: {img.mode}")
    print("\n" + "=" * 50)

    methods = [
        ("原始图", lambda x: x),
        ("灰度+放大", method1_grayscale_only),
        ("灰度+对比度", method2_contrast),
        ("二值化(阈值180)", method3_binary_low),
        ("二值化(阈值120)", method4_binary_high),
        ("锐化+对比度", method5_sharpen),
    ]

    config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'

    for name, method in methods:
        try:
            processed = method(img.copy())
            result = pytesseract.image_to_string(processed, config=config)
            result = ''.join(c for c in result if c.isdigit())
            print(f"{name:20s} -> '{result}'")
        except Exception as e:
            print(f"{name:20s} -> 错误: {e}")

    print("=" * 50)

if __name__ == "__main__":
    test_all_methods()
