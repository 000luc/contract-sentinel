"""
测试 Playwright 能否复用 Chrome 登录态访问 OA

使用说明：
1. 先用 Chrome 浏览器手动登录 OA（https://oa.grgt.cn/）
2. 运行此脚本：py src/test_playwright_login.py
3. 脚本会自动复制 Chrome 登录数据，打开 OA 页面并截图验证
"""

import os
import sys
import shutil
from datetime import datetime
from playwright.sync_api import sync_playwright

# 配置
OA_URL = "https://oa.grgt.cn/"
CHROME_USER_DATA = r"C:\Users\lucheng\AppData\Local\Google\Chrome\User Data"
TEMP_PROFILE = r"D:\BaiduSyncdisk\claude\Contract Sentinel\data\chrome_temp_profile"
SCREENSHOT_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel\data\logs"

def copy_profile():
    """复制 Chrome 用户数据目录（只复制关键文件，避免锁定问题）"""

    print("[准备] 正在复制 Chrome 登录数据...")

    # 清理旧数据
    if os.path.exists(TEMP_PROFILE):
        shutil.rmtree(TEMP_PROFILE, ignore_errors=True)

    os.makedirs(TEMP_PROFILE, exist_ok=True)

    # 需要复制的关键目录和文件
    key_items = [
        "Default",
        "Local State",
    ]

    copied = []
    for item in key_items:
        src = os.path.join(CHROME_USER_DATA, item)
        dst = os.path.join(TEMP_PROFILE, item)
        if os.path.exists(src):
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                        "*.lock", "LOCK", "Singleton*", "Code Cache", "GPUCache"
                    ))
                else:
                    shutil.copy2(src, dst)
                copied.append(item)
            except Exception as e:
                print(f"    复制 {item} 时跳过: {e}")

    if len(copied) == 0:
        print("警告：未能复制任何登录数据")
        return False

    print(f"    已复制: {', '.join(copied)}")
    return True

def test_login_reuse():
    """测试复用 Chrome 登录态访问 OA"""

    print("=" * 50)
    print("开始测试：Playwright 登录态复用")
    print("=" * 50)

    # 确保截图目录存在
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # 复制登录数据
    if not copy_profile():
        print("复制失败，尝试直接使用原始目录...")
        profile_to_use = CHROME_USER_DATA
    else:
        profile_to_use = TEMP_PROFILE

    with sync_playwright() as p:
        print("\n[1/4] 正在启动浏览器...")
        print(f"    使用数据目录: {profile_to_use}")

        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=profile_to_use,
                headless=False,  # 显示浏览器窗口，方便观察
                args=["--disable-blink-features=AutomationControlled"]  # 尝试隐藏自动化特征
            )
        except Exception as e:
            print(f"\n启动失败: {e}")
            print("\n可能原因：")
            print("  - Chrome 正在运行，请先关闭所有 Chrome 窗口")
            print("  - Chrome 用户数据目录路径不正确")
            return False

        print("[2/4] 浏览器已启动，正在访问 OA...")
        page = browser.new_page()

        try:
            page.goto(OA_URL, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"\n访问 OA 失败: {e}")
            browser.close()
            return False

        print("[3/4] 页面已加载，正在截图...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"oa_login_test_{timestamp}.png")
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"    截图已保存: {screenshot_path}")

        # 判断当前页面状态
        print("[4/4] 分析页面状态...")
        page_title = page.title()
        print(f"    页面标题: {page_title}")

        url = page.url
        print(f"    当前 URL: {url}")

        # 检查是否仍处于登录状态
        page_text = page.inner_text("body")

        login_indicators = ["门户", "流程", "待办", "流程中心", "e-cology", "前端用户中心"]
        login_page_indicators = ["登录", "请输入验证码", "忘记密码", "login"]

        is_logged_in = any(indicator in page_text for indicator in login_indicators)
        is_login_page = any(indicator in page_text for indicator in login_page_indicators)

        print("\n" + "=" * 50)
        if is_logged_in and not is_login_page:
            print("结果: 登录态复用成功，当前已登录 OA")
            print("=" * 50)
            browser.close()
            return True
        elif is_login_page:
            print("结果: 当前处于登录页面，登录态可能已过期")
            print("=" * 50)
            browser.close()
            return False
        else:
            print("结果: 无法判断登录状态，请查看截图确认")
            print("=" * 50)
            browser.close()
            return False

if __name__ == "__main__":
    print("注意：运行前请确保已手动登录 OA\n")

    # 检查 Chrome 用户数据目录是否存在
    if not os.path.exists(CHROME_USER_DATA):
        print(f"错误：找不到 Chrome 用户数据目录")
        print(f"路径: {CHROME_USER_DATA}")
        print("\n请确认 Chrome 安装位置，或修改脚本中的 CHROME_USER_DATA 变量")
        sys.exit(1)

    success = test_login_reuse()

    if success:
        print("\n测试通过！可以进入下一步：测试待办列表读取")
    else:
        print("\n测试未通过，请检查：")
        print("  1. 是否已先手动登录 OA（登录后保持打开状态或正常关闭均可）")
        print("  2. Chrome 用户数据目录路径是否正确")
