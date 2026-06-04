"""
验证码识别测试（增强版）

对验证码图片进行预处理（灰度化、二值化、去噪），提高识别准确率
"""

import os
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
from playwright.sync_api import sync_playwright
import ddddocr

OA_URL = "https://oa.grgt.cn/"
SCREENSHOT_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel\data\logs"


def preprocess_captcha(image_path):
    """预处理验证码图片：灰度化 -> 增强对比度 -> 二值化"""
    img = Image.open(image_path)

    # 转为灰度图
    img = img.convert('L')

    # 增强对比度
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # 二值化：根据阈值将图片转为黑白
    threshold = 128
    img = img.point(lambda x: 0 if x < threshold else 255, '1')

    # 保存预处理后的图片
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processed_path = os.path.join(SCREENSHOT_DIR, f"captcha_processed_{timestamp}.png")
    img.save(processed_path)

    return processed_path


def recognize_captcha(image_path):
    """使用 ddddocr 识别验证码"""
    ocr = ddddocr.DdddOcr(show_ad=False)
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    result = ocr.classification(image_bytes)
    return result


def test_captcha():
    print("=" * 50)
    print("开始测试：验证码识别（增强版）")
    print("=" * 50)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        print("\n[1/3] 启动浏览器并访问 OA 登录页...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(OA_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        print("[2/3] 截取验证码...")
        captcha_element = page.locator('xpath=//img[contains(@src, "validateCode") or contains(@src, "captcha") or contains(@src, "verify")]').first

        if captcha_element.count() == 0:
            print("未找到验证码元素")
            browser.close()
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        captcha_path = os.path.join(SCREENSHOT_DIR, f"captcha_raw_{timestamp}.png")
        captcha_element.screenshot(path=captcha_path)
        print(f"    原始验证码已保存: {captcha_path}")

        print("[3/3] 预处理后识别...")
        processed_path = preprocess_captcha(captcha_path)
        print(f"    预处理后图片: {processed_path}")

        # 分别识别原始图和预处理图
        raw_result = recognize_captcha(captcha_path)
        processed_result = recognize_captcha(processed_path)

        print(f"\n原始图识别结果: {raw_result}")
        print(f"预处理识别结果: {processed_result}")

        browser.close()
        return True


if __name__ == "__main__":
    test_captcha()
