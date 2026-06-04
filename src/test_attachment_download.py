"""
测试进入合同流程详情页并查找附件
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


def test_attachment_explore():
    print("=" * 50)
    print("测试：进入合同流程详情页并查找附件")
    print("=" * 50)

    cookies = load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        # 访问首页
        page.goto(OA_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 检查登录状态
        page_text = page.inner_text("body")
        if "前端用户中心" not in page_text:
            print("Cookie已过期")
            browser.close()
            return False

        print("已登录，查找合同类待办...")

        # 用JavaScript找到合同类待办的链接
        contract_link = page.evaluate('''() => {
            const links = document.querySelectorAll('a');
            for (const link of links) {
                const text = link.innerText.trim();
                if (text.includes('付款合同评审') || text.includes('合同评审')) {
                    return {
                        text: text,
                        href: link.href,
                        onclick: link.getAttribute('onclick') || ''
                    };
                }
            }
            return null;
        }''')

        if not contract_link:
            print("未找到合同类待办链接")
            browser.close()
            return False

        print(f"\n找到合同待办: {contract_link['text'][:80]}")
        print(f"链接: {contract_link['href'][:100]}...")

        # 获取详情页URL并直接访问
        print("\n获取详情页URL...")
        detail_url = page.evaluate('''() => {
            const links = document.querySelectorAll('a');
            for (const link of links) {
                const text = link.innerText.trim();
                if (text.includes('付款合同评审') || text.includes('合同评审')) {
                    const dataLink = link.getAttribute('data-link');
                    if (dataLink) {
                        return dataLink;
                    }
                    return link.href;
                }
            }
            return null;
        }''')

        if not detail_url:
            print("未找到详情页URL")
            browser.close()
            return False

        # 拼接完整URL
        if detail_url.startswith('/'):
            detail_url = f"https://oa.grgt.cn{detail_url}"

        print(f"详情页URL: {detail_url[:120]}...")
        print("\n进入详情页...")

        try:
            page.goto(detail_url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"进入详情页失败: {e}")
            browser.close()
            return False

        page.wait_for_timeout(5000)

        # 截图详情页
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        detail_path = os.path.join(SCREENSHOT_DIR, f"contract_detail_{timestamp}.png")
        page.screenshot(path=detail_path, full_page=True)
        print(f"详情页截图: {detail_path}")

        # 查找附件
        print("\n--- 查找附件 ---")
        attachments = page.evaluate('''() => {
            const results = [];

            // 策略1: 查找包含"附件"关键词的区域
            const allElements = document.querySelectorAll('*');
            for (const el of allElements) {
                const text = el.innerText?.trim() || '';
                if (text.includes('附件') && text.length < 200) {
                    // 查找该区域内的链接
                    const links = el.querySelectorAll('a');
                    for (const link of links) {
                        const linkText = link.innerText.trim();
                        const href = link.href;
                        if (linkText && href && (href.includes('.pdf') || href.includes('.doc') || href.includes('.xls') || href.includes('/download') || href.includes('file'))) {
                            results.push({
                                text: linkText,
                                href: href,
                                source: 'attachment_area'
                            });
                        }
                    }
                }
            }

            // 策略2: 查找所有文件下载链接
            const allLinks = document.querySelectorAll('a[href*="download"], a[href*=".pdf"], a[href*=".doc"], a[href*=".xls"], a[href*=".zip"]');
            for (const link of allLinks) {
                results.push({
                    text: link.innerText.trim(),
                    href: link.href,
                    source: 'file_link'
                });
            }

            // 策略3: 泛微OA常见附件结构
            const fileList = document.querySelectorAll('[class*="file"], [class*="attach"], [id*="file"], [id*="attach"]');
            for (const el of fileList) {
                const links = el.querySelectorAll('a');
                for (const link of links) {
                    results.push({
                        text: link.innerText.trim(),
                        href: link.href,
                        source: 'file_class'
                    });
                }
            }

            return results;
        }''')

        print(f"找到 {len(attachments)} 个附件链接")
        for i, att in enumerate(attachments[:10], 1):
            print(f"{i}. [{att['source']}] {att['text'][:50]} -> {att['href'][:80]}...")

        # 尝试点击下载按钮
        print("\n--- 尝试下载附件 ---")
        download_path = None
        try:
            # 设置下载监听
            with page.expect_download(timeout=15000) as download_info:
                # 点击下载图标
                page.locator('.icon-coms-download').first.click()
                print("    已点击下载按钮")

            download = download_info.value
            download_path = os.path.join(BASE_DIR, "data", "contracts", download.suggested_filename)
            download.save_as(download_path)
            print(f"    下载成功: {download_path}")
        except Exception as e:
            print(f"    下载尝试失败: {e}")
            print("    尝试备用方式...")

            # 备用：用JavaScript触发点击
            try:
                with page.expect_download(timeout=15000) as download_info:
                    page.evaluate('''() => {
                        const btn = document.querySelector('.icon-coms-download');
                        if (btn) btn.click();
                    }''')
                    print("    已用JS点击下载按钮")

                download = download_info.value
                download_path = os.path.join(BASE_DIR, "data", "contracts", download.suggested_filename)
                download.save_as(download_path)
                print(f"    下载成功: {download_path}")
            except Exception as e2:
                print(f"    备用方式也失败: {e2}")

        # 保存页面HTML供分析
        html_path = os.path.join(SCREENSHOT_DIR, f"contract_detail_{timestamp}.html")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(page.content())
        print(f"\n详情页HTML: {html_path}")

        browser.close()
        return True


if __name__ == "__main__":
    test_attachment_explore()
