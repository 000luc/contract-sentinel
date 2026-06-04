"""
测试合同审核流程
1. 进入合同详情页
2. 提取合同文本内容
3. 模拟AI审核（输出结构化审核意见）
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
        print("Cookie不存在")
        sys.exit(1)
    with open(COOKIE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_contract_info(page):
    """从详情页提取合同信息"""
    print("\n--- 提取合同信息 ---")

    # 提取页面文本
    page_text = page.inner_text("body")

    # 提取表格数据
    table_data = page.evaluate('''() => {
        const result = {};
        const cells = document.querySelectorAll('td');
        for (const cell of cells) {
            const text = cell.innerText.trim();
            // 查找键值对（如"合同名称：xxx"）
            if (text.includes('：') || text.includes(':')) {
                const parts = text.split(/[：:]/);
                if (parts.length >= 2) {
                    const key = parts[0].trim();
                    const value = parts.slice(1).join('：').trim();
                    if (key && value && key.length < 50 && value.length < 500) {
                        result[key] = value;
                    }
                }
            }
        }
        return result;
    }''')

    # 在Python中处理合同条款文本
    paragraphs = page_text.split('\n')
    contract_clauses = []
    keywords = ['合同', '条款', '双方', '甲方', '乙方', '权利', '义务', '违约', '赔偿']
    for p in paragraphs:
        trimmed = p.strip()
        if 50 < len(trimmed) < 2000:
            if any(kw in trimmed for kw in keywords):
                contract_clauses.append(trimmed)

    print(f"    提取到 {len(table_data)} 个字段")
    print(f"    提取到 {len(contract_clauses)} 条条款文本")

    return {
        'table_data': table_data,
        'clauses': contract_clauses,
        'full_text': page_text[:5000]
    }


def simulate_ai_review(contract_info):
    """模拟AI审核（实际应调用API）"""
    print("\n--- 模拟AI合同审核 ---")

    # 构建审核输入
    review_input = {
        'contract_type': '付款合同评审',
        'basic_info': contract_info['table_data'],
        'clauses_sample': contract_info['clauses'][:3]  # 取前3条条款
    }

    print("\n审核输入:")
    print(json.dumps(review_input, ensure_ascii=False, indent=2))

    # 模拟审核结果（实际应调用Kimi/Claude等API）
    review_result = {
        'risk_level': '待评估',
        'review_points': [
            '合同金额是否超出预算',
            '付款条款是否合理（预付款比例、付款节点）',
            '违约责任是否对等',
            '争议解决条款是否明确',
            '合同期限是否与业务需求匹配'
        ],
        'recommendations': [
            '建议核对合同金额与预算审批是否一致',
            '建议确认付款节点与项目进度匹配',
            '建议检查供应商资质和履约能力'
        ],
        'status': '需要人工复核'
    }

    print("\n模拟审核结果:")
    print(json.dumps(review_result, ensure_ascii=False, indent=2))

    return review_result


def test_contract_review():
    print("=" * 50)
    print("测试：合同审核流程")
    print("=" * 50)

    cookies = load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        # 先访问首页确保Cookie生效，再跳转到详情页
        print(f"\n先访问首页...")
        page.goto(OA_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        detail_url = "https://oa.grgt.cn/workflow/request/ViewRequestForwardSPA.jsp?requestid=3543411"
        print(f"跳转合同详情页...")

        try:
            page.goto(detail_url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"访问失败: {e}")
            browser.close()
            return False

        page.wait_for_timeout(5000)

        # 截图
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"contract_review_{timestamp}.png")
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"截图: {screenshot_path}")

        # 提取合同信息
        contract_info = extract_contract_info(page)

        # 模拟审核
        review_result = simulate_ai_review(contract_info)

        # 保存结果
        result = {
            'test_time': datetime.now().isoformat(),
            'contract_info': contract_info,
            'review_result': review_result
        }

        result_path = os.path.join(SCREENSHOT_DIR, f"contract_review_{timestamp}.json")
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {result_path}")

        browser.close()
        return True


if __name__ == "__main__":
    test_contract_review()
