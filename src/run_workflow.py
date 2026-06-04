"""
Contract Sentinel - 完整工作流（本地测试版）
串起所有步骤：登录 → 待办 → 合同 → 附件 → 审核 → 报告

运行方式：
    py src/run_workflow.py

输出位置：
    data/reports/   审核报告（JSON + 文本）
    data/logs/      页面截图
    data/contracts/ 下载的合同附件
"""

import json
import os
import sys
import traceback
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_DIR = r"D:\BaiduSyncdisk\claude\Contract Sentinel"
COOKIE_PATH = os.path.join(BASE_DIR, "data", "oa_cookies.json")
SCREENSHOT_DIR = os.path.join(BASE_DIR, "data", "logs")
CONTRACTS_DIR = os.path.join(BASE_DIR, "data", "contracts")
REPORTS_DIR = os.path.join(BASE_DIR, "data", "reports")
OA_URL = "https://oa.grgt.cn/"

CONTRACT_KEYWORDS = ["合同", "付款", "采购", "协议"]


def ensure_dirs():
    for d in [SCREENSHOT_DIR, CONTRACTS_DIR, REPORTS_DIR]:
        os.makedirs(d, exist_ok=True)


def load_cookies():
    if not os.path.exists(COOKIE_PATH):
        print(f"Cookie 文件不存在: {COOKIE_PATH}")
        print("请先运行: py src/auto_login.py")
        sys.exit(1)
    with open(COOKIE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def is_contract_process(title):
    return any(kw in title.lower() for kw in CONTRACT_KEYWORDS)


def ensure_login(page):
    print("\n[1/4] 检查登录状态...")
    page.goto(OA_URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    page_text = page.inner_text("body")
    indicators = ["门户", "流程", "待办", "流程中心", "个人门户", "前端用户中心"]

    if any(ind in page_text for ind in indicators):
        print("    Cookie 有效，已登录")
        return True

    print("    Cookie 已过期，请重新运行: py src/auto_login.py")
    return False


def extract_todo_list(page):
    print("\n[2/4] 提取待办列表...")

    items = page.evaluate('''() => {
        const result = [];
        const seen = new Set();
        const rows = document.querySelectorAll('tr');
        for (const row of rows) {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 3) {
                const texts = Array.from(cells).map(td => td.innerText.trim()).filter(t => t.length > 0);
                if (texts.length >= 3) {
                    const title = texts[0], creator = texts[1], date = texts[2];
                    if (/申请|评审|审批|请款|合同|报销|借款|付款/.test(title) &&
                        /^\\d{4}-\\d{2}-\\d{2}$/.test(date) &&
                        title.length < 150 && !seen.has(title)) {
                        seen.add(title);
                        const link = row.querySelector('a');
                        let detailUrl = '';
                        if (link) detailUrl = link.getAttribute('data-link') || link.href || '';
                        result.push({ title, creator, date, detailUrl });
                    }
                }
            }
        }
        return result;
    }''')

    print(f"    提取到 {len(items)} 条待办")
    contract_items = [item for item in items if is_contract_process(item['title'])]
    print(f"    其中合同类: {len(contract_items)} 条")
    return items, contract_items


def download_attachments(page, detail_url):
    print("\n--- 下载附件 ---")

    if detail_url.startswith('/'):
        detail_url = f"https://oa.grgt.cn{detail_url}"

    try:
        page.goto(detail_url, wait_until="load", timeout=60000)
    except Exception as e:
        print(f"    进入详情页失败: {e}")
        return []

    page.wait_for_timeout(5000)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"detail_{ts}.png"), full_page=True)

    attachments = page.evaluate('''() => {
        const results = [];
        document.querySelectorAll('a').forEach(link => {
            const href = link.href || '';
            if (/\\.(pdf|doc|docx|xls|xlsx|zip)$/i.test(href)) {
                results.push({ text: link.innerText.trim(), href });
            }
        });
        return results;
    }''')

    print(f"    发现 {len(attachments)} 个附件")
    for att in attachments[:5]:
        print(f"      - {att['text'][:40]}")

    downloaded = []

    # 方式1: force 强制点击（绕过 visibility 检查）
    try:
        with page.expect_download(timeout=15000) as dl_info:
            page.locator('.icon-coms-download').first.click(force=True)
        dl = dl_info.value
        save_path = os.path.join(CONTRACTS_DIR, dl.suggested_filename)
        dl.save_as(save_path)
        downloaded.append(save_path)
        print(f"    下载成功: {dl.suggested_filename}")
        return downloaded
    except Exception as e:
        print(f"    force 点击失败: {e}")

    # 方式2: JS 强制触发点击
    try:
        with page.expect_download(timeout=15000) as dl_info:
            page.evaluate('''() => {
                const btn = document.querySelector('.icon-coms-download');
                if (btn) {
                    btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                    btn.click();
                }
            }''')
        dl = dl_info.value
        save_path = os.path.join(CONTRACTS_DIR, dl.suggested_filename)
        dl.save_as(save_path)
        downloaded.append(save_path)
        print(f"    下载成功(JS): {dl.suggested_filename}")
        return downloaded
    except Exception as e2:
        print(f"    JS 点击也失败: {e2}")

    return downloaded


def extract_contract_info(page):
    print("\n--- 提取合同信息 ---")

    page_text = page.inner_text("body")

    table_data = page.evaluate('''() => {
        const result = {};
        document.querySelectorAll('td').forEach(cell => {
            const text = cell.innerText.trim();
            if ((text.includes('：') || text.includes(':')) && text.length < 500) {
                const parts = text.split(/[：:]/);
                if (parts.length >= 2) {
                    const key = parts[0].trim();
                    const value = parts.slice(1).join('：').trim();
                    if (key && value && key.length < 50) result[key] = value;
                }
            }
        });
        return result;
    }''')

    paragraphs = [p.strip() for p in page_text.split('\n') if 50 < len(p.strip()) < 2000]
    clauses = [p for p in paragraphs if any(kw in p for kw in ['合同', '条款', '双方', '甲方', '乙方', '违约', '赔偿'])]

    print(f"    字段: {len(table_data)} 个, 条款: {len(clauses)} 条")

    return {
        'table_data': table_data,
        'clauses': clauses[:5],
        'full_text': page_text[:3000]
    }


def simulate_ai_review(contract_info):
    print("\n--- AI 审核（模拟）---")

    full_text = contract_info.get('full_text', '').lower()
    review_points = [
        '合同金额是否超出预算',
        '付款条款是否合理（预付款比例、付款节点）',
        '违约责任是否对等',
        '争议解决条款是否明确',
        '合同期限是否与业务需求匹配'
    ]
    recommendations = [
        '建议核对合同金额与预算审批是否一致',
        '建议确认付款节点与项目进度匹配',
        '建议检查供应商资质和履约能力'
    ]

    risk_level = '中风险'
    if '预付款' in full_text or '预付' in full_text:
        review_points.append('发现预付款条款，需重点审核比例及对应风险保障')
        risk_level = '中高风险'

    return {
        'risk_level': risk_level,
        'review_points': review_points,
        'recommendations': recommendations,
        'status': '需要人工复核'
    }


def process_contract(page, todo_item):
    title = todo_item['title'][:50]
    print(f"\n{'='*50}")
    print(f"处理合同: {title}")
    print(f"{'='*50}")

    detail_url = todo_item.get('detailUrl', '')
    if not detail_url:
        print("无详情页URL，跳过")
        return None

    try:
        attachments = download_attachments(page, detail_url)
        contract_info = extract_contract_info(page)
        review = simulate_ai_review(contract_info)

        return {
            'title': todo_item['title'],
            'creator': todo_item['creator'],
            'date': todo_item['date'],
            'attachments': [os.path.basename(a) for a in attachments],
            'contract_info': {
                'table_data': contract_info['table_data'],
                'clauses': contract_info['clauses']
            },
            'review': review
        }
    except Exception as e:
        print(f"处理失败: {e}")
        traceback.print_exc()
        return None


def save_report(results):
    print("\n[4/4] 生成审核报告...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = os.path.join(REPORTS_DIR, f"report_{ts}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': datetime.now().isoformat(),
            'count': len(results),
            'results': results
        }, f, ensure_ascii=False, indent=2)
    print(f"    JSON报告: {json_path}")

    txt_path = os.path.join(REPORTS_DIR, f"report_{ts}.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"合同审核报告\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"共处理 {len(results)} 个合同\n")
        f.write(f"{'='*50}\n\n")
        for r in results:
            f.write(f"【{r['title']}】\n")
            f.write(f"发起人: {r['creator']} | 日期: {r['date']}\n")
            f.write(f"风险等级: {r['review']['risk_level']}\n")
            f.write(f"审核要点:\n")
            for p in r['review']['review_points']:
                f.write(f"  - {p}\n")
            f.write(f"建议:\n")
            for rec in r['review']['recommendations']:
                f.write(f"  - {rec}\n")
            if r['attachments']:
                f.write(f"附件: {', '.join(r['attachments'])}\n")
            f.write(f"{'-'*50}\n\n")
    print(f"    文本报告: {txt_path}")

    return txt_path


def main():
    print("=" * 60)
    print("Contract Sentinel - 完整工作流")
    print("=" * 60)

    ensure_dirs()
    cookies = load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        if not ensure_login(page):
            browser.close()
            sys.exit(1)

        _, contract_items = extract_todo_list(page)

        if not contract_items:
            print("\n没有合同类待办，流程结束")
            browser.close()
            return

        results = []
        for item in contract_items:
            result = process_contract(page, item)
            if result:
                results.append(result)

        if results:
            save_report(results)
        else:
            print("\n没有成功处理任何合同")

        print(f"\n{'='*60}")
        print("工作流完成")
        print(f"{'='*60}")

        browser.close()


if __name__ == "__main__":
    main()
