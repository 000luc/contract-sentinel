from __future__ import annotations

import json
import re
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
        title = item.title.lower()
        return any(keyword.lower() in title for keyword in self.contract_keywords)

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

    def download_attachments(
        self,
        page: Page,
        item: WorkflowItem,
        output_dir: Path,
    ) -> list[AttachmentInfo]:
        if not item.detail_url:
            raise ValueError("Workflow detail_url is required for attachment download")

        output_dir.mkdir(parents=True, exist_ok=True)
        page.goto(self._absolute_url(item.detail_url), wait_until="load", timeout=60000)
        page.wait_for_timeout(5000)

        attachments = self._download_attachment_links(page, output_dir)
        seen_downloads: set[Path] = {
            attachment.local_path for attachment in attachments if attachment.local_path
        }

        download_buttons = page.locator(".icon-coms-download")
        for index in range(download_buttons.count()):
            try:
                with page.expect_download(timeout=20000) as download_info:
                    download_buttons.nth(index).click(force=True)
                download = download_info.value
                target = self._unique_target_path(output_dir, download.suggested_filename)
                download.save_as(target)
            except Exception as exc:
                raise RuntimeError(f"Download button {index} failed: {exc}") from exc

            if target in seen_downloads:
                continue
            seen_downloads.add(target)
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
            except Exception as exc:
                raise RuntimeError(f"Attachment link download failed: {attachment.href}: {exc}") from exc

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
