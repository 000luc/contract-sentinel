"""
测试 ddddocr 对 OA 验证码的识别准确率
连续获取10个验证码，对比识别结果和实际值
"""

import os
from datetime import datetime
from playwright.sync_api import sync_playwright
import ddddocr

OA_URL = "https://oa.grgt.cn/"
SCREENSHOT_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel\data\logs"


def recognize_captcha(image_path):
    """使用 ddddocr 识别验证码"""
    ocr = ddddocr.DdddOcr(show_ad=False)
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    result = ocr.classification(image_bytes)
    return ''.join(c for c in result if c.isalnum())


def test_accuracy():
    print("=" * 50)
    print("测试 ddddocr 验证码识别准确率")
    print("=" * 50)
    print("\n我会连续截取10个验证码，保存图片并显示识别结果。")
    print("请你对照图片，告诉我每个验证码的实际值，我统计准确率。\n")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(OA_URL, wait_until="networkidle", timeout=30000)

        for i in range(10):
            page.wait_for_timeout(1500)

            # 刷新验证码（点击验证码图片通常会刷新）
            captcha_img = page.locator(
                'xpath=//img[contains(@src, "validateCode") or contains(@src, "captcha") or contains(@src, "verify")]'
            ).first

            if captcha_img.count() > 0:
                # 点击验证码刷新
                try:
                    captcha_img.click()
                    page.wait_for_timeout(1000)
                except Exception:
                    pass

                # 重新获取验证码元素
                captcha_img = page.locator(
                    'xpath=//img[contains(@src, "validateCode") or contains(@src, "captcha") or contains(@src, "verify")]'
                ).first

            if captcha_img.count() == 0:
                print(f"第 {i+1}/10: 未找到验证码")
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            captcha_path = os.path.join(SCREENSHOT_DIR, f"accuracy_test_{i+1}_{timestamp}.png")
            captcha_img.screenshot(path=captcha_path)

            recognized = recognize_captcha(captcha_path)
            results.append({
                'index': i + 1,
                'path': captcha_path,
                'recognized': recognized
            })

            print(f"第 {i+1}/10: 识别结果 = '{recognized}'  (图片: {captcha_path})")

        browser.close()

    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)
    print("\n请告诉我每张图片的实际验证码值，我统计准确率。")
    print("（你可以直接按顺序回复10个数字，如：1234 5678 9012 ...）")

    return results


if __name__ == "__main__":
    test_accuracy()
