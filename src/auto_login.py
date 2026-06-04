"""
OA 自动登录（含验证码识别）

使用说明：
1. 先在 config.json 中填写 OA 账号和密码
2. 运行此脚本：py src/auto_login.py
3. 脚本会自动识别验证码并登录
4. 登录成功后会保存 Cookie，供后续脚本复用
"""

import json
import os
import sys
from datetime import datetime
from PIL import Image, ImageEnhance
from playwright.sync_api import sync_playwright
import ddddocr

BASE_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel"
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
COOKIE_PATH = os.path.join(BASE_DIR, "data", "oa_cookies.json")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "data", "logs")


class OALoginHelper:
    """OA登录辅助类，复用OCR实例"""

    def __init__(self):
        self.ocr = ddddocr.DdddOcr(show_ad=False)

    def preprocess_captcha(self, image_path):
        """预处理验证码图片以提升识别率"""
        img = Image.open(image_path)

        # 转为灰度图
        img = img.convert('L')

        # 放大3倍（小图放大后更容易识别）
        img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)

        # 增强对比度
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # 保存预处理后的图片用于调试
        processed_path = image_path.replace('.png', '_processed.png')
        img.save(processed_path)

        return processed_path

    def recognize_captcha(self, image_path, use_preprocess=True):
        """识别验证码，可选择是否预处理"""
        if use_preprocess:
            processed_path = self.preprocess_captcha(image_path)
            with open(processed_path, 'rb') as f:
                image_bytes = f.read()
        else:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()

        result = self.ocr.classification(image_bytes)
        return ''.join(c for c in result if c.isalnum())


def load_config():
    """读取配置文件"""
    if not os.path.exists(CONFIG_PATH):
        print(f"错误：找不到配置文件 {CONFIG_PATH}")
        print("请先填写 config.json 中的账号和密码")
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def attempt_login(page, username, password, helper, attempt_num):
    """尝试一次登录流程，返回是否成功"""

    print(f"\n--- 第 {attempt_num} 次登录尝试 ---")

    # 获取验证码元素
    captcha_element = page.locator(
        'xpath=//img[contains(@src, "validateCode") or contains(@src, "captcha") or contains(@src, "verify")]'
    ).first

    if captcha_element.count() == 0:
        print("未找到验证码元素")
        return False

    # 截取验证码
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    captcha_path = os.path.join(SCREENSHOT_DIR, f"login_captcha_{timestamp}.png")
    captcha_element.screenshot(path=captcha_path)
    print(f"    验证码已保存: {os.path.basename(captcha_path)}")

    # 尝试两种识别方式：预处理 和 原图
    for method_name, use_preprocess in [("预处理", True), ("原图", False)]:
        captcha_text = helper.recognize_captcha(captcha_path, use_preprocess=use_preprocess)
        print(f"    [{method_name}] 识别结果: '{captcha_text}'")

        if len(captcha_text) >= 4:
            # 找到一个看起来有效的结果，就用它
            break
    else:
        # 两种方法都没识别出4位以上，取最长的那个
        text1 = helper.recognize_captcha(captcha_path, use_preprocess=True)
        text2 = helper.recognize_captcha(captcha_path, use_preprocess=False)
        captcha_text = text1 if len(text1) >= len(text2) else text2
        print(f"    最终选用: '{captcha_text}'")

    captcha_text = ''.join(c for c in captcha_text if c.isalnum())

    # 清空并填写所有输入框
    all_inputs = page.locator('input').all()
    username_input = None
    password_input = None
    captcha_input = None
    text_inputs = []

    for inp in all_inputs:
        try:
            input_type = inp.get_attribute('type') or ''
            if input_type == 'password':
                password_input = inp
            elif input_type == 'text':
                text_inputs.append(inp)
        except Exception:
            continue

    if len(text_inputs) >= 1:
        username_input = text_inputs[0]
    if len(text_inputs) >= 2:
        captcha_input = text_inputs[1]

    if username_input:
        username_input.fill(username)
    if password_input:
        password_input.fill(password)
    if captcha_input:
        captcha_input.fill(captcha_text)

    print(f"    已填写: 账号={username}, 验证码={captcha_text}")

    # 点击登录 - 尝试多种方式
    clicked = False

    # 方式1: button[type="submit"]
    try:
        submit_btn = page.locator('button[type="submit"]').first
        if submit_btn.count() > 0 and submit_btn.is_visible():
            submit_btn.click()
            clicked = True
            print("    通过 button[type=submit] 点击登录")
    except Exception:
        pass

    # 方式2: input[type="submit"]
    if not clicked:
        try:
            submit_input = page.locator('input[type="submit"]').first
            if submit_input.count() > 0 and submit_input.is_visible():
                submit_input.click()
                clicked = True
                print("    通过 input[type=submit] 点击登录")
        except Exception:
            pass

    # 方式3: 包含"登录"文本的按钮
    if not clicked:
        try:
            login_btn = page.get_by_role("button", name="登录").first
            if login_btn.count() > 0 and login_btn.is_visible():
                login_btn.click()
                clicked = True
                print("    通过 role=button[name=登录] 点击登录")
        except Exception:
            pass

    # 方式4: 包含"登录"文本的任何元素
    if not clicked:
        try:
            login_btn = page.locator('text=登录').first
            if login_btn.count() > 0 and login_btn.is_visible():
                login_btn.click()
                clicked = True
                print("    通过 text=登录 点击登录")
        except Exception:
            pass

    # 方式5: 在验证码框按Enter提交
    if not clicked and captcha_input:
        try:
            captcha_input.press("Enter")
            clicked = True
            print("    通过按Enter键提交登录")
        except Exception:
            pass

    if not clicked:
        print("    警告：未能找到登录按钮")
        return False

    print("    等待响应...")

    # 等待页面响应
    page.wait_for_timeout(5000)

    # 截图记录结果
    screenshot_path = os.path.join(SCREENSHOT_DIR, f"login_result_{timestamp}_try{attempt_num}.png")
    page.screenshot(path=screenshot_path, full_page=True)

    # 判断登录状态
    url = page.url
    page_text = page.inner_text("body")

    # 如果 URL 不再包含 logintype，说明已跳转，可能登录成功
    if "logintype" not in url:
        print("    页面已跳转，可能登录成功")
        return True

    # 检查页面文本中的登录成功指标
    login_indicators = ["门户", "流程", "待办", "流程中心", "个人门户", "前端用户中心", "欢迎"]
    is_logged_in = any(indicator in page_text for indicator in login_indicators)

    if is_logged_in:
        print("    检测到登录成功关键词")
        return True

    # 检查是否有错误提示
    error_keywords = ["验证码错误", "密码错误", "账号错误", "登录失败", "不正确", "错误"]
    has_error = any(keyword in page_text for keyword in error_keywords)

    if has_error:
        print("    检测到错误提示，准备重试...")
    else:
        print("    仍在登录页，可能验证码错误，准备重试...")

    return False


def refresh_captcha(page):
    """点击验证码图片刷新，比reload页面更快"""
    captcha_img = page.locator(
        'xpath=//img[contains(@src, "validateCode") or contains(@src, "captcha") or contains(@src, "verify")]'
    ).first

    if captcha_img.count() > 0:
        try:
            captcha_img.click()
            page.wait_for_timeout(1500)  # 等待验证码刷新
            return True
        except Exception as e:
            print(f"    点击刷新验证码失败: {e}")

    return False


def auto_login():
    """自动登录 OA（带重试）"""
    print("=" * 50)
    print("开始自动登录 OA")
    print("=" * 50)

    config = load_config()
    username = config.get("oa_username", "")
    password = config.get("oa_password", "")
    oa_url = config.get("oa_url", "https://oa.grgt.cn/")

    if not username or not password or username == "你的OA账号":
        print("\n错误：config.json 中未填写账号或密码")
        print(f"请编辑文件: {CONFIG_PATH}")
        sys.exit(1)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    helper = OALoginHelper()

    with sync_playwright() as p:
        print("\n[1/3] 启动浏览器...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("[2/3] 访问 OA 登录页...")
        page.goto(oa_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        max_attempts = 10  # 增加到10次
        print(f"[3/3] 开始登录尝试（最多{max_attempts}次）...")
        success = False

        for attempt in range(1, max_attempts + 1):
            success = attempt_login(page, username, password, helper, attempt)

            if success:
                break

            if attempt < max_attempts:
                print("    刷新验证码，准备下一次尝试...")
                refreshed = refresh_captcha(page)
                if not refreshed:
                    print("    点击刷新失败，重新加载页面...")
                    page.reload(wait_until="networkidle")
                    page.wait_for_timeout(2000)

        print("\n" + "=" * 50)
        if success:
            print("登录成功！")

            # 保存 Cookie
            cookies = page.context.cookies()
            with open(COOKIE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print(f"Cookie 已保存: {COOKIE_PATH}")

            # 保存登录成功截图
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            success_path = os.path.join(SCREENSHOT_DIR, f"login_success_{timestamp}.png")
            page.screenshot(path=success_path, full_page=True)
            print(f"成功截图: {success_path}")

            print("=" * 50)
            browser.close()
            return True
        else:
            print(f"登录失败，{max_attempts}次尝试均未成功")
            print("=" * 50)

            # 保存最后一张截图用于人工确认
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback_path = os.path.join(SCREENSHOT_DIR, f"login_failed_{timestamp}.png")
            page.screenshot(path=fallback_path, full_page=True)
            print(f"失败截图已保存: {fallback_path}")
            print("建议：查看截图确认验证码，或稍后重试")

            browser.close()
            return False


if __name__ == "__main__":
    success = auto_login()

    if success:
        print("\n可以进入下一步：测试待办列表读取")
    else:
        print("\n登录失败，可能原因：")
        print("  1. 验证码识别错误（可重新运行再试）")
        print("  2. 账号或密码错误")
        print("  3. 页面结构变化")
