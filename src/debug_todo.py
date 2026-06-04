"""诊断：查看 OA 待办表格结构"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "src"))

cookies = json.loads((BASE / "data" / "oa_cookies.json").read_text(encoding="utf-8"))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    context.add_cookies(cookies)
    page = context.new_page()
    page.goto("https://oa.grgt.cn/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    # 看待办事宜区域的所有行
    rows = page.evaluate("""() => {
        const result = [];
        const seen = new Set();
        const datePat = /\\d{4}-\\d{2}-\\d{2}/;
        for (const tr of document.querySelectorAll('tr')) {
            const tds = Array.from(tr.querySelectorAll('td'));
            const texts = tds.map(td => td.innerText.trim()).filter(Boolean);
            if (texts.length < 2) continue;
            const date = texts.find(t => datePat.test(t));
            if (!date) continue;
            const title = texts[0];
            if (title.length > 120 || seen.has(title)) continue;
            seen.add(title);

            // 每列的原始HTML（找流程编号）
            const cols = tds.map((td, i) => ({
                i, text: td.innerText.trim().substring(0, 80),
                html: td.innerHTML.substring(0, 120)
            }));

            result.push({ title: title.substring(0, 60), cols });
        }
        return result;
    }""")

    print(f"共 {len(rows)} 条待办")
    for r in rows:
        kw = [k for k in ["付款合同评审", "合同评审", "付款合同", "合同"] if k in r["title"]]
        tag = " \\U0001f7e2 合同" if kw else "    "
        print(f"{tag} {r['title']}")
        for c in r["cols"]:
            print(f"    列{c['i']}: {c['text'][:60]}")
            if "workflow" in c["html"].lower() or "流程" in c["html"] or "id" in c["html"].lower():
                print(f"        HTML: {c['html'][:100]}")
    browser.close()
