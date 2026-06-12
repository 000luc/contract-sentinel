from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urljoin, urlparse

from .path_utils import safe_filename
from .workflow_models import AttachmentInfo, WorkflowItem

if TYPE_CHECKING:
    from playwright.sync_api import Page
else:
    Page = Any


WORKFLOW_ID_PATTERN = re.compile(r"[0-9]{2}-[A-Z]-[A-Z]{2}[0-9]{4}-[0-9]+")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
ATTACHMENT_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")
LOGIN_INDICATORS = ("门户", "流程", "待办", "流程中心", "个人门户", "前端用户中心")


class OAClient:
    def __init__(self, oa_url: str, cookie_path: Path, contract_keywords: list[str]) -> None:
        self.oa_url = oa_url
        self.cookie_path = cookie_path
        self.contract_keywords = contract_keywords

    def load_cookies(self) -> list[dict]:
        if not self.cookie_path.exists():
            raise FileNotFoundError(self.cookie_path)
        return json.loads(self.cookie_path.read_text(encoding="utf-8"))

    def is_contract_workflow(self, item: WorkflowItem) -> bool:
        """判断是否为合同审批流程（排除通知公告、请款申请类页面）"""
        title = item.title
        # 排除 OA 通知公告（"关于...通知" 格式），非合同审批流程
        if title.startswith("关于") and "通知" in title:
            return False
        # 排除请款申请（无合同附件，不属于合同审批）
        if "请款申请" in title:
            return False
        title_lower = title.lower()
        return any(keyword.lower() in title_lower for keyword in self.contract_keywords)

    def open_browser(self):
        from playwright.sync_api import sync_playwright

        return sync_playwright()

    def ensure_login(self, page: Page) -> bool:
        page.goto(self.oa_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        body = page.inner_text("body")
        return any(indicator in body for indicator in LOGIN_INDICATORS)

    def count_todo_rows(self, page: Page) -> int:
        """统计待办表格总行数（含非合同流程），用于实时显示"""
        return page.evaluate(
            """() => {
                let count = 0;
                const datePattern = /\\d{4}-\\d{2}-\\d{2}/;
                for (const row of document.querySelectorAll("tr")) {
                    const cells = Array.from(row.querySelectorAll("td")).map(
                        td => td.innerText.trim()
                    );
                    if (cells.length >= 3 && datePattern.test(cells[cells.length - 1])) {
                        count++;
                    }
                }
                return count;
            }"""
        )

    def extract_todo_list(self, page: Page) -> list[WorkflowItem]:
        rows = page.evaluate(
            """() => {
                const result = [];
                const seenIds = new Set();
                const seenTitles = new Set();
                const workflowPattern = /[A-Z]{1,4}\\d{5,8}|[0-9]{2}-[A-Z]-[A-Z]{2}[0-9]{4}-[0-9]+/;
                const datePattern = /\\d{4}-\\d{2}-\\d{2}/;

                for (const row of document.querySelectorAll("tr")) {
                    const texts = Array.from(row.querySelectorAll("td"))
                        .map(td => td.innerText.trim())
                        .filter(Boolean);
                    if (!texts.length) continue;
                    const title = texts[0];
                    if (title.length > 120 || seenTitles.has(title)) continue;
                    seenTitles.add(title);

                    // 尝试提取流程编号，没有也不跳过
                    const joined = texts.join(" ");
                    const idMatch = joined.match(workflowPattern);
                    const workflowId = idMatch ? idMatch[0] : title.replace(/[^0-9a-zA-Z\\u4e00-\\u9fff]/g, "_").substring(0, 60);
                    if (seenIds.has(workflowId)) continue;
                    seenIds.add(workflowId);

                    const link = row.querySelector("a");
                    result.push({
                        workflow_id: workflowId,
                        title: title,
                        creator: texts[1] || "",
                        created_at: texts.find(text => datePattern.test(text)) || "",
                        detail_url: link ? (link.getAttribute("data-link") || link.getAttribute("href") || "") : "",
                        raw: { texts }
                    });
                }
                return result;
            }"""
        )
        return [WorkflowItem(**row) for row in rows]

    def _get_main_iframe(self, page: Page):
        """找到 SPA 详情页的主 iframe"""
        frames = getattr(page, "frames", None)
        if frames is None:
            return None
        for f in frames:
            if "static4form" in f.url:
                return f
        return None

    def _find_file_links_on_page(self, page: Page) -> list[dict]:
        """在页面本身查找附件列表（OA SPA 页面直接渲染附件）"""
        return page.evaluate("""() => {
            const items = document.querySelectorAll('.wea-upload-list-item');
            return Array.from(items).map((item, index) => {
                const link = item.querySelector('a.wea-field-link');
                const name = link ? link.innerText.trim() : '';
                const title = link ? link.getAttribute('title') : '';
                return {
                    index: index,
                    name: name || title || ('附件' + index),
                    visible: item.offsetParent !== null,
                };
            }).filter(f => f.name && f.visible);
        }""")

    def _find_file_links_in_iframe(self, iframe) -> list[dict]:
        """在 iframe 内查找文件链接列表"""
        return iframe.evaluate("""() => {
            const items = document.querySelectorAll('.wea-upload-list-item a');
            return Array.from(items).map((a, index) => ({
                index: index,
                name: a.innerText.trim(),
                visible: a.offsetParent !== null,
            })).filter(f => f.name);
        }""")

    def _click_and_capture_download_urls(
        self, page: Page, iframe, file_links: list[dict]
    ) -> list[dict]:
        """点击文件链接，拦截 window.open 获取下载 URL"""
        results = []
        for fl in file_links:
            captured = iframe.evaluate("""() => {
                window.__dlUrl = null;
                const origOpen = window.open;
                window.open = function(url) {
                    window.__dlUrl = url || null;
                    return null;  // 阻止弹窗
                };
            }""")

            try:
                link = iframe.locator('.wea-upload-list-item a').nth(
                    file_links.index(fl)
                )
                link.click()
                page.wait_for_timeout(2000)
            except Exception as exc:
                print(f"   点击文件链接失败: {fl['name']}: {exc}")
                continue

            dl_url = iframe.evaluate("() => window.__dlUrl")
            if dl_url:
                full_url = self._absolute_url(dl_url)
                results.append({"name": fl["name"], "url": full_url})

        return results

    @staticmethod
    def _validate_downloaded_file(file_path: Path, expected_name: str = "") -> tuple[bool, str]:
        """校验下载的文件是否完整有效。返回 (是否通过, 错误信息)"""
        if not file_path.exists():
            return False, "文件不存在"

        size = file_path.stat().st_size
        if size == 0:
            return False, "文件大小为 0"

        # 读取文件头进行魔数校验
        with open(file_path, "rb") as f:
            header = f.read(8)

        ext = file_path.suffix.lower()

        # 定义魔数映射
        magic_map = {
            ".pdf": (b"%PDF", "PDF"),
            ".doc": (b"\xd0\xcf\x11\xe0", "OLE (DOC/XLS)"),
            ".xls": (b"\xd0\xcf\x11\xe0", "OLE (DOC/XLS)"),
            ".docx": (b"PK\x03\x04", "ZIP (DOCX/XLSX)"),
            ".xlsx": (b"PK\x03\x04", "ZIP (DOCX/XLSX)"),
            ".zip": (b"PK\x03\x04", "ZIP"),
        }

        if ext in magic_map:
            expected_magic, type_name = magic_map[ext]
            if not header.startswith(expected_magic):
                return False, f"文件头不匹配: 期望 {type_name}, 实际头字节: {header[:4].hex()}"

        # 文件大小合理性检查（小于 100 字节视为异常）
        if size < 100:
            return False, f"文件过小 ({size} 字节)，可能下载不完整"

        return True, ""

    @staticmethod
    def _convert_doc_to_docx(doc_path: Path) -> Path | None:
        """将 .doc 转换为 .docx：优先 LibreOffice 命令行，其次 Word COM"""
        if doc_path.suffix.lower() != ".doc":
            return doc_path

        docx_path = doc_path.with_suffix(".docx")

        # 方式一：LibreOffice 命令行
        libreoffice_paths = [
            r"D:\1111\app\LibreOffice\program\soffice.exe",
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
        for soffice in libreoffice_paths:
            if Path(soffice).exists():
                try:
                    import subprocess

                    # LibreOffice 必须 cd 到输出目录，否则中文路径会乱码
                    cwd = str(doc_path.parent)
                    cmd = [
                        soffice,
                        "--headless",
                        "--convert-to", "docx",
                        str(doc_path.name),
                        "--outdir", ".",
                    ]
                    result = subprocess.run(
                        cmd, cwd=cwd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=30
                    )
                    if docx_path.exists() and docx_path.stat().st_size > 0:
                        doc_path.unlink()
                        print(f"   [OK] 已转换: {doc_path.name} -> {docx_path.name}")
                        return docx_path
                except Exception as exc:
                    print(f"   LibreOffice 转换失败: {exc}")
                break

        # 方式二：Word COM（fallback）
        try:
            import win32com.client as win32

            word = win32.Dispatch("Word.Application")
            try:
                word.Visible = False
            except Exception:
                pass
            try:
                word.DisplayAlerts = False
            except Exception:
                pass

            doc = word.Documents.Open(str(doc_path.resolve()))
            doc.SaveAs(str(docx_path.resolve()), FileFormat=16)
            doc.Close()
            word.Quit()

            if docx_path.exists() and docx_path.stat().st_size > 0:
                doc_path.unlink()
                print(f"   [OK] 已转换: {doc_path.name} -> {docx_path.name}")
                return docx_path
        except Exception:
            pass

        print(f"   转换失败: {doc_path.name}")
        return doc_path

    def _download_via_http(
        self, page: Page, file_info: dict, output_dir: Path
    ) -> Path | None:
        """通过 HTTP 请求下载文件并校验完整性"""
        try:
            response = page.context.request.get(file_info["url"])
            if not response.ok:
                print(f"   HTTP {response.status}: {file_info['url']}")
                return None
            content = response.body()
            if not content:
                return None
            target = self._unique_target_path(output_dir, file_info["name"])
            target.write_bytes(content)

            # 校验下载完整性
            valid, err = self._validate_downloaded_file(target, file_info["name"])
            if not valid:
                print(f"   校验失败: {file_info['name']}: {err}")
                target.unlink(missing_ok=True)
                return None

            # 自动转换 .doc -> .docx
            target = self._convert_doc_to_docx(target)

            print(f"   [OK] 下载完成: {target.name} ({target.stat().st_size} 字节)")
            return target
        except Exception as exc:
            print(f"   下载失败: {exc}")
            return None

    def _wait_for_content_loaded(self, page: Page, timeout_ms: int = 20000) -> bool:
        """等待 SPA 页面内容加载完成"""
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            try:
                body_text = page.inner_text("body")
            except Exception:
                # 页面可能正在导航或暂不可读，继续等待
                time.sleep(1)
                continue
            # 检测到表单内容或附件列表相关元素说明加载完成
            if len(body_text) > 500 and (
                "流程" in body_text
                or "申请" in body_text
                or "附件" in body_text
                or "上传" in body_text
            ):
                return True
            time.sleep(1)
        return False

    def _download_upload_list_items(
        self, page: Page, file_links: list[dict], output_dir: Path
    ) -> list[AttachmentInfo]:
        """点击 wea-upload-list 中的下载图标来下载附件"""
        attachments: list[AttachmentInfo] = []
        seen_paths: set[Path] = set()

        for fl in file_links:
            name = fl["name"]
            index = fl.get("index", 0)
            print(f"   正在下载: {name}")

            try:
                # 使用 JavaScript 点击下载图标（绕过可见性检查）
                # 先找到第 index 个 wea-upload-list-item，再找到其中的下载图标
                js_click = f"""() => {{
                    const items = document.querySelectorAll('.wea-upload-list-item');
                    if (items.length <= {index}) return null;
                    const icon = items[{index}].querySelector('.icon-coms-download');
                    if (icon) {{
                        icon.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                        icon.click();
                        return true;
                    }}
                    return null;
                }}"""

                with page.expect_download(timeout=30000) as download_info:
                    clicked = page.evaluate(js_click)
                    if not clicked:
                        print(f"   未找到下载图标: {name}")
                        continue
                download = download_info.value

                # 使用原始文件名或建议文件名
                filename = name if name.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")) else download.suggested_filename
                target = self._unique_target_path(output_dir, filename)
                download.save_as(target)

                # 校验完整性
                valid, err = self._validate_downloaded_file(target, filename)
                if not valid:
                    print(f"   校验失败: {filename}: {err}")
                    target.unlink(missing_ok=True)
                    continue

                # 自动转换 .doc -> .docx
                target = self._convert_doc_to_docx(target)

                print(f"   [OK] 下载完成: {target.name} ({target.stat().st_size} 字节)")

                if target not in seen_paths:
                    seen_paths.add(target)
                    attachments.append(
                        AttachmentInfo(
                            name=target.name,
                            href=download.url or "",
                            local_path=target,
                        )
                    )
            except Exception as exc:
                print(f"   下载失败: {name}: {exc}")
                continue

        return attachments

    def download_attachments(
        self,
        page: Page,
        item: WorkflowItem,
        output_dir: Path,
    ) -> list[AttachmentInfo]:
        if not item.detail_url:
            raise ValueError("Workflow detail_url is required for attachment download")

        output_dir.mkdir(parents=True, exist_ok=True)
        page.goto(self._absolute_url(item.detail_url), wait_until="networkidle", timeout=60000)

        # 等待 SPA 内容加载（OA 的 React 页面渲染很慢）
        loaded = self._wait_for_content_loaded(page, timeout_ms=25000)
        if not loaded:
            print("   警告：页面内容加载超时，继续尝试下载...")
        page.wait_for_timeout(3000)  # 额外等待附件列表渲染

        attachments: list[AttachmentInfo] = []
        seen_paths: set[Path] = set()

        # 方式一：页面本身的 wea-upload-list 附件（OA SPA 直接渲染）
        file_links = self._find_file_links_on_page(page)
        if file_links:
            print(f"   发现 {len(file_links)} 个附件（页面列表）")
            items = self._download_upload_list_items(page, file_links, output_dir)
            for a in items:
                if a.local_path and a.local_path not in seen_paths:
                    seen_paths.add(a.local_path)
                    attachments.append(a)
            if attachments:
                return self._dedupe_attachments(attachments)

        # 方式二：尝试从 SPA iframe 内点击文件链接捕获下载
        iframe = self._get_main_iframe(page)
        if iframe:
            file_links = self._find_file_links_in_iframe(iframe)
            if file_links:
                print(f"   发现 {len(file_links)} 个附件（iframe 内）")
                download_infos = self._click_and_capture_download_urls(
                    page, iframe, file_links
                )
                for info in download_infos:
                    local_path = self._download_via_http(page, info, output_dir)
                    if local_path and local_path not in seen_paths:
                        seen_paths.add(local_path)
                        attachments.append(
                            AttachmentInfo(
                                name=info["name"],
                                href=info["url"],
                                local_path=local_path,
                            )
                        )
                if attachments:
                    return self._dedupe_attachments(attachments)

        # 方式三：尝试普通链接下载（页面本身也可能直接包含附件链接）
        attachments_from_links = self._download_attachment_links(page, output_dir)
        for a in attachments_from_links:
            if a.local_path and a.local_path not in seen_paths:
                seen_paths.add(a.local_path)
                attachments.append(a)

        # 方式四：兜底 - 尝试点击所有下载图标
        if not attachments:
            print("   尝试兜底下载（点击所有下载图标）...")
            download_buttons = page.locator(".icon-coms-download")
            for index in range(download_buttons.count()):
                try:
                    with page.expect_download(timeout=20000) as download_info:
                        download_buttons.nth(index).click(force=True)
                    download = download_info.value
                    target = self._unique_target_path(output_dir, download.suggested_filename)
                    download.save_as(target)

                    valid, err = self._validate_downloaded_file(target, download.suggested_filename)
                    if not valid:
                        print(f"   校验失败: {download.suggested_filename}: {err}")
                        target.unlink(missing_ok=True)
                        continue

                    print(f"   [OK] 下载完成: {target.name} ({target.stat().st_size} 字节)")
                except Exception:
                    continue

                if target in seen_paths:
                    continue
                seen_paths.add(target)
                attachments.append(
                    AttachmentInfo(
                        name=download.suggested_filename,
                        href=download.url or "",
                        local_path=target,
                    )
                )

        return self._dedupe_attachments(attachments)

    def _download_attachment_links(self, page: Page, output_dir: Path) -> list[AttachmentInfo]:
        attachments: list[AttachmentInfo] = []
        for attachment in self._extract_attachment_links(page):
            filename = attachment.name or self._filename_from_url(attachment.href)
            target = self._unique_target_path(output_dir, filename)
            try:
                response = page.context.request.get(attachment.href)
                if not response.ok:
                    raise RuntimeError(f"HTTP {response.status}")
                target.write_bytes(response.body())

                # 校验完整性
                valid, err = self._validate_downloaded_file(target, filename)
                if not valid:
                    print(f"   校验失败: {filename}: {err}")
                    target.unlink(missing_ok=True)
                    continue

                # 自动转换 .doc -> .docx
                target = self._convert_doc_to_docx(target)

                print(f"   [OK] 下载完成: {target.name} ({target.stat().st_size} 字节)")
            except Exception as exc:
                print(f"   下载失败: {attachment.href}: {exc}")
                continue

            attachments.append(
                AttachmentInfo(
                    name=attachment.name,
                    href=attachment.href,
                    local_path=target,
                )
            )
        return attachments

    def save_detail_snapshot(self, page: Page, raw_dir: Path) -> None:
        raw_dir.mkdir(parents=True, exist_ok=True)
        # 等待页面内容加载后再保存
        self._wait_for_content_loaded(page, timeout_ms=15000)
        page.wait_for_timeout(2000)
        (raw_dir / "workflow.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(raw_dir / "workflow.png"), full_page=True)

    def _absolute_url(self, url: str) -> str:
        return urljoin(self.oa_url, url)

    def _extract_attachment_links(self, page: Page) -> list[AttachmentInfo]:
        links = page.evaluate(
            """() => Array.from(document.querySelectorAll("a")).map(link => ({
                text: link.innerText.trim(),
                href: link.getAttribute("href") || "",
                absoluteHref: link.href || ""
            }))"""
        )

        attachments: list[AttachmentInfo] = []
        seen_hrefs: set[str] = set()
        for link in links:
            href = link.get("absoluteHref") or link.get("href") or ""
            if not self._looks_like_attachment(href):
                continue

            absolute_href = self._absolute_url(href)
            if absolute_href in seen_hrefs:
                continue
            seen_hrefs.add(absolute_href)

            text = (link.get("text") or "").strip()
            attachments.append(
                AttachmentInfo(
                    name=text or self._filename_from_url(absolute_href),
                    href=absolute_href,
                )
            )

        return attachments

    @staticmethod
    def _looks_like_attachment(href: str) -> bool:
        path = unquote(urlparse(href).path).lower()
        return path.endswith(ATTACHMENT_SUFFIXES)

    @staticmethod
    def _filename_from_url(url: str) -> str:
        name = Path(unquote(urlparse(url).path)).name
        return safe_filename(name or url, max_length=180)

    @staticmethod
    def _unique_target_path(output_dir: Path, filename: str) -> Path:
        target = output_dir / safe_filename(filename, max_length=180)
        if not target.exists():
            return target

        stem = target.stem
        suffix = target.suffix
        index = 2
        while True:
            candidate = output_dir / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _dedupe_attachments(attachments: list[AttachmentInfo]) -> list[AttachmentInfo]:
        result: list[AttachmentInfo] = []
        seen: set[tuple[str, str, str]] = set()
        for attachment in attachments:
            key = (
                attachment.href,
                str(attachment.local_path) if attachment.local_path else "",
                attachment.name,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(attachment)
        return result
