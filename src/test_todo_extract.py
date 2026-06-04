"""
用JavaScript在页面上提取待办列表结构
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


def load_cookies():
    if not os.path.exists(COOKIE_PATH):
        print("Cookie文件不存在，请先运行auto_login.py")
        sys.exit(1)
    with open(COOKIE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_with_js(page):
    """用JavaScript提取页面上的待办数据"""
    result = page.evaluate('''() => {
        const items = [];

        // 策略1: 查找流程中心区域内的列表项
        // 泛微OA常见结构：流程中心模块
        const flowCenter = document.querySelector('[id*="flow"], [id*="process"], [class*="flow-center"], [class*="process-center"]');
        if (flowCenter) {
            const rows = flowCenter.querySelectorAll('tr, .list-item, [class*="item"]');
            for (const row of rows) {
                const links = row.querySelectorAll('a');
                const texts = Array.from(row.querySelectorAll('td, span, div'))
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 0);

                if (links.length > 0 || texts.length > 0) {
                    items.push({
                        source: 'flowCenter',
                        title: links[0]?.innerText?.trim() || texts[0] || '',
                        texts: texts,
                        html: row.outerHTML.substring(0, 500)
                    });
                }
            }
        }

        // 策略2: 遍历所有包含日期的行
        const allRows = document.querySelectorAll('tr');
        for (const row of allRows) {
            const text = row.innerText;
            if (/\\d{4}-\\d{2}-\\d{2}/.test(text) && text.length > 10 && text.length < 500) {
                const cells = Array.from(row.querySelectorAll('td'))
                    .map(td => td.innerText.trim())
                    .filter(t => t.length > 0);

                if (cells.length >= 2) {
                    items.push({
                        source: 'dateRow',
                        cells: cells,
                        text: text.substring(0, 200)
                    });
                }
            }
        }

        // 策略3: 查找所有包含"2026-"的div/span/p
        const dateElements = document.querySelectorAll('div, span, p, a');
        for (const el of dateElements) {
            const text = el.innerText?.trim();
            if (text && /\\d{4}-\\d{2}-\\d{2}/.test(text) && text.length > 15 && text.length < 300) {
                // 检查是否包含看起来像流程标题的内容
                if (text.includes('-') && (text.includes('申请') || text.includes('评审') || text.includes('审批') || text.includes('请款') || text.includes('合同'))) {
                    items.push({
                        source: 'textElement',
                        text: text.substring(0, 300),
                        tag: el.tagName,
                        parentTag: el.parentElement?.tagName
                    });
                }
            }
        }

        return items;
    }''')

    return result


def main():
    print("=" * 50)
    print("提取OA待办列表结构")
    print("=" * 50)

    cookies = load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        page.goto(OA_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 截图
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"todo_extract_{timestamp}.png")
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"截图: {screenshot_path}")

        # 用JS提取
        items = extract_with_js(page)

        print(f"\n找到 {len(items)} 个候选项:\n")

        # 去重并筛选
        seen = set()
        unique_items = []
        for item in items:
            text = item.get('text', item.get('title', ''))
            if text and text not in seen and len(text) > 10:
                seen.add(text)
                unique_items.append(item)

        for i, item in enumerate(unique_items[:30], 1):
            print(f"{i}. [{item.get('source', 'unknown')}]")
            if item.get('cells'):
                print(f"   cells: {item['cells']}")
            if item.get('text'):
                print(f"   text: {item['text'][:150]}")
            if item.get('title'):
                print(f"   title: {item['title'][:150]}")
            print()

        # 保存
        result_path = os.path.join(SCREENSHOT_DIR, f"todo_extract_{timestamp}.json")
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(unique_items, f, ensure_ascii=False, indent=2)
        print(f"结果保存: {result_path}")

        browser.close()


if __name__ == "__main__":
    main()
