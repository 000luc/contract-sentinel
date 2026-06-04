"""
测试读取 OA 待办列表
复用已保存的 Cookie 登录，避免重复验证码流程
"""

import json
import os
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel"
COOKIE_PATH = os.path.join(BASE_DIR, "data", "oa_cookies.json")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "data", "logs")
OA_URL = "https://oa.grgt.cn/"

# 合同类关键词
CONTRACT_KEYWORDS = ["合同", "付款", "采购", "协议"]


def load_cookies():
    """读取保存的 Cookie"""
    if not os.path.exists(COOKIE_PATH):
        print(f"错误：找不到 Cookie 文件 {COOKIE_PATH}")
        print("请先运行 auto_login.py 登录并保存 Cookie")
        sys.exit(1)

    with open(COOKIE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def is_contract_process(title):
    """判断流程标题是否属于合同类"""
    title_lower = title.lower()
    return any(kw in title_lower for kw in CONTRACT_KEYWORDS)


def extract_todo_list(page):
    """从页面提取待办列表"""
    print("\n--- 提取待办列表 ---")

    # 截图保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = os.path.join(SCREENSHOT_DIR, f"todo_page_{timestamp}.png")
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"页面截图已保存: {screenshot_path}")

    # 用JavaScript提取表格数据 - 泛微OA待办是3列表格：[标题, 发起人, 日期]
    items = page.evaluate('''() => {
        const result = [];
        const seen = new Set();

        // 遍历所有表格行，找有3个单元格且包含流程关键词的行
        const rows = document.querySelectorAll('tr');
        for (const row of rows) {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 3) {
                const texts = Array.from(cells).map(td => td.innerText.trim()).filter(t => t.length > 0);
                if (texts.length >= 3) {
                    const title = texts[0];
                    const creator = texts[1];
                    const date = texts[2];

                    // 过滤：标题要包含流程相关关键词，日期要符合格式，标题不能太长（排除公告区块）
                    const hasFlowKeyword = /申请|评审|审批|请款|合同|报销|借款|付款/.test(title);
                    const hasDateFormat = /^\d{4}-\d{2}-\d{2}$/.test(date);
                    const notTooLong = title.length < 150;  // 公告区块会合并很多条

                    if (hasFlowKeyword && hasDateFormat && notTooLong && !seen.has(title)) {
                        seen.add(title);
                        result.push({ title, creator, date });
                    }
                }
            }
        }
        return result;
    }''')

    print(f"    提取到 {len(items)} 条待办")

    todo_items = []
    for item in items:
        todo_items.append({
            'title': item['title'],
            'creator': item['creator'],
            'date': item['date'],
            'is_contract': is_contract_process(item['title'])
        })

    return todo_items


def test_todo_list():
    """测试读取待办列表"""
    print("=" * 50)
    print("测试读取 OA 待办列表")
    print("=" * 50)

    cookies = load_cookies()
    print(f"\n已加载 {len(cookies)} 个 Cookie")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        print("\n[1/2] 启动浏览器并注入 Cookie...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        # 注入 Cookie
        context.add_cookies(cookies)
        page = context.new_page()

        print("[2/2] 访问 OA 首页...")
        page.goto(OA_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 检查是否登录成功
        url = page.url
        page_text = page.inner_text("body")

        login_indicators = ["门户", "流程", "待办", "流程中心", "个人门户", "前端用户中心"]
        is_logged_in = any(indicator in page_text for indicator in login_indicators)

        if not is_logged_in:
            print("\nCookie 已过期，需要重新登录")
            print("请运行: py src/auto_login.py")
            browser.close()
            sys.exit(1)

        print("Cookie 有效，已登录")

        # 提取待办列表
        todo_items = extract_todo_list(page)

        print("\n" + "=" * 50)
        print(f"待办列表（共 {len(todo_items)} 条）")
        print("=" * 50)

        contract_items = []
        for i, item in enumerate(todo_items, 1):
            marker = "[合同]" if item.get('is_contract') else "      "
            print(f"{i}. {marker} {item['title']}")
            if item.get('creator'):
                print(f"   发起人: {item['creator']} | 日期: {item['date']}")

            if item.get('is_contract'):
                contract_items.append(item)

        print("\n" + "=" * 50)
        print(f"合同类待办（共 {len(contract_items)} 条）")
        print("=" * 50)
        for item in contract_items:
            print(f"- {item['title']}")

        # 保存结果
        result_path = os.path.join(SCREENSHOT_DIR, f"todo_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump({
                'total': len(todo_items),
                'contracts': len(contract_items),
                'items': todo_items,
                'contract_items': contract_items
            }, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {result_path}")

        browser.close()
        return todo_items, contract_items


if __name__ == "__main__":
    test_todo_list()
