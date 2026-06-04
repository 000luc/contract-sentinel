"""
测试验证码自动识别

使用说明：
1. 运行此脚本：py src/test_captcha_recognition.py
2. 脚本会自动打开 OA 登录页，截取验证码图片，识别验证码内容
3. 结果会显示在屏幕上并保存截图
"""

import os
from datetime import datetime
from playwright.sync_api import sync_playwright
import ddddocr

# 配置
OA_URL = "https://oa.grgt.cn/"
SCREENSHOT_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel\data\logs"


def recognize_captcha(image_path):
    """使用 ddddocr 识别验证码"""
    ocr = ddddocr.DdddOcr(show_ad=False)
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    result = ocr.classification(image_bytes)
    return result


def test_captcha():
    """测试获取并识别 OA 验证码"""

    print("=" * 50)
    print("开始测试：验证码自动识别")
    print("=" * 50)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        print("\n[1/4] 启动浏览器...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("[2/4] 访问 OA 登录页...")
        page.goto(OA_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        print("[3/4] 截取验证码...")

        # 尝试定位验证码图片
        captcha_locators = [
            'img[src*="captcha"]',
            'img[id*="captcha"]',
            'img[class*="captcha"]',
            'img[title*="验证码"]',
            'img[alt*="验证码"]',
            '//img[contains(@src, "validateCode") or contains(@src, "captcha") or contains(@src, "verify")]',
        ]

        captcha_element = None
        captcha_path = None

        for locator_str in captcha_locators:
            try:
                if locator_str.startswith('//'):
                    element = page.locator(f'xpath={locator_str}').first
                else:
                    element = page.locator(locator_str).first

                if element.count() > 0 and element.is_visible():
                    captcha_element = element
                    print(f"    找到验证码元素: {locator_str}")
                    break
            except Exception:
                continue

        # 如果按 locator 找不到，尝试截图整个页面再手动裁剪
        if captcha_element is None:
            print("    未找到标准验证码元素，尝试截图整个页面...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            full_page_path = os.path.join(SCREENSHOT_DIR, f"login_page_{timestamp}.png")
            page.screenshot(path=full_page_path)
            print(f"    页面截图已保存: {full_page_path}")
            print("    请查看截图，手动确认验证码位置")
            browser.close()
            return False

        # 截取验证码图片
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        captcha_path = os.path.join(SCREENSHOT_DIR, f"captcha_{timestamp}.png")
        captcha_element.screenshot(path=captcha_path)
        print(f"    验证码截图已保存: {captcha_path}")

        print("[4/4] 识别验证码...")
        try:
            recognized_text = recognize_captcha(captcha_path)
            print(f"\n识别结果: {recognized_text}")

            # 保存结果
            result_path = os.path.join(SCREENSHOT_DIR, f"captcha_result_{timestamp}.txt")
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write(f"验证码图片: {captcha_path}\n")
                f.write(f"识别结果: {recognized_text}\n")
            print(f"结果已保存: {result_path}")

            # 截图留证
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"captcha_page_{timestamp}.png"))

            browser.close()

            if recognized_text and len(recognized_text) >= 3:
                print("\n验证码识别成功！")
                return True
            else:
                print("\n验证码识别结果异常，请检查截图")
                return False

        except Exception as e:
            print(f"识别失败: {e}")
            browser.close()
            return False


if __name__ == "__main__":
    success = test_captcha()

    if success:
        print("\n可以进入下一步：测试自动登录")
    else:
        print("\n需要调整验证码定位或识别方式")
