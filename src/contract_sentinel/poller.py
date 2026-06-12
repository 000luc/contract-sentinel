from __future__ import annotations

import json
import time
from datetime import datetime
from typing import TYPE_CHECKING

from .audit_backends import create_audit_backend
from .audit_runner import AuditRunner
from .oa_client import OAClient
from .state_store import StateStore
from .workflow_models import WorkflowItem
from .workflow_writer import WorkflowWriter

if TYPE_CHECKING:
    from .settings import Settings


def filter_new_contract_workflows(
    items: list[WorkflowItem],
    state: StateStore,
    client: OAClient,
) -> list[WorkflowItem]:
    result: list[WorkflowItem] = []
    seen: set[str] = set()
    for item in items:
        if item.workflow_id in seen:
            continue
        if not client.is_contract_workflow(item):
            continue
        if state.is_processed(item.workflow_id):
            continue
        seen.add(item.workflow_id)
        result.append(item)
    return result


class ContractApprovalPoller:
    def __init__(self, settings: Settings) -> None:
        self.approval_output_root = settings.approval_output_root
        self.state = StateStore(settings.approval_output_root / ".state")
        self.writer = WorkflowWriter(settings.approval_output_root)
        self.client = OAClient(
            settings.oa_url,
            settings.cookie_path,
            settings.contract_keywords,
        )
        self.audit_runner = AuditRunner(
            create_audit_backend(
                settings.audit_backend,
                model=settings.direct_llm_model,
                claude_command=settings.claude_cli_command,
                api_key=settings.deepseek_api_key,
                api_base=settings.deepseek_api_base,
            )
        )
        self.interval_seconds = settings.poll_interval_seconds
        self.settings = settings

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _log(self, msg: str) -> None:
        print(f"[{self._now()}] {msg}", flush=True)

    def _interactive_login(self, playwright) -> bool:
        """弹出可见浏览器让用户手动登录，成功后保存 Cookie"""
        self._log("正在打开浏览器窗口，请手动登录 OA...")
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(self.client.oa_url, wait_until="networkidle", timeout=30000)

            # 等待用户手动登录（最多 5 分钟）
            max_wait = 300  # 5 分钟
            check_interval = 3
            waited = 0

            while waited < max_wait:
                time.sleep(check_interval)
                waited += check_interval

                # 检查是否已登录
                try:
                    url = page.url
                    body = page.inner_text("body")
                    # URL 已跳转离开登录页
                    if "login" not in url.lower() and "logintype" not in url.lower():
                        self._log(f"检测到页面跳转（{url[:60]}...），正在保存 Cookie...")
                        cookies = context.cookies()
                        self.client.cookie_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(self.client.cookie_path, 'w', encoding='utf-8') as f:
                            json.dump(cookies, f, ensure_ascii=False, indent=2)
                        self._log(f"Cookie 已保存: {self.client.cookie_path}")
                        return True
                    # 页面包含登录成功标志
                    if any(indicator in body for indicator in ("门户", "流程", "待办", "流程中心", "个人门户", "前端用户中心")):
                        self._log("检测到登录成功关键词，正在保存 Cookie...")
                        cookies = context.cookies()
                        self.client.cookie_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(self.client.cookie_path, 'w', encoding='utf-8') as f:
                            json.dump(cookies, f, ensure_ascii=False, indent=2)
                        self._log(f"Cookie 已保存: {self.client.cookie_path}")
                        return True
                except Exception:
                    pass

            self._log("登录等待超时（5分钟），本轮跳过")
            return False
        finally:
            browser.close()

    def _try_login_with_cookies(self, playwright):
        """尝试用 Cookie 登录，失效则弹窗让用户手动登录"""
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            try:
                context.add_cookies(self.client.load_cookies())
            except FileNotFoundError:
                self._log("Cookie 文件不存在")
                browser.close()
                return self._interactive_login(playwright)

            page = context.new_page()
            if self.client.ensure_login(page):
                return page, browser, context

            self._log("Cookie 已失效")
            browser.close()
            return self._interactive_login(playwright)
        except Exception:
            browser.close()
            raise

    def process_once_with_page(self, page) -> int:
        if not self.client.ensure_login(page):
            self._log("OA 登录已失效，请重新登录")
            raise RuntimeError("OA login failed")

        total = self.client.count_todo_rows(page)
        items = self.client.extract_todo_list(page)
        new_items = filter_new_contract_workflows(items, self.state, self.client)
        self._log(f"OA 待办共 {total} 条，其中合同审批 {len(new_items)} 条")

        if not new_items:
            return 0

        processed_count = 0
        for item in new_items:
            name = item.title[:60]
            self._log(f"正在处理: {name}")

            material = None
            try:
                self.state.mark_processing(item.workflow_id, {"title": item.title})
                material = self.writer.prepare(item)

                self._log(f"  下载附件中...")
                attachments = self.client.download_attachments(
                    page,
                    item,
                    material.attachments_dir,
                )
                self.client.save_detail_snapshot(page, material.raw_dir)
                material.attachments.extend(attachments)
                self._log(f"  附件 {len(attachments)} 个，正在调用 AI 审核...")

                audit_status = self.audit_runner.run(material)

                status = audit_status.get("status", "")
                if status == "audit_completed":
                    self._log(f"  [OK] 审核完成: {name}")
                elif status == "audit_failed":
                    self._log(f"  [FAIL] 审核失败: {audit_status.get('error', '未知错误')}")
                else:
                    self._log(f"  [PENDING] 审核状态: {status}")

                metadata = {
                    "title": item.title,
                    "workflow_dir": str(material.workflow_dir),
                    "audit_status": audit_status,
                }
                self.state.mark_processed(item.workflow_id, metadata)
                self.writer.append_log(
                    material.workflow_dir,
                    "processed",
                    {"workflow_id": item.workflow_id, "audit_status": audit_status},
                )
                processed_count += 1
            except Exception as exc:
                self._log(f"  [FAIL] 处理失败: {exc}")
                self.state.mark_failed(item.workflow_id, str(exc))
                log_dir = (
                    material.workflow_dir
                    if material is not None
                    else self.approval_output_root / ".failed" / item.workflow_id
                )
                self.writer.append_log(
                    log_dir,
                    "failed",
                    {"workflow_id": item.workflow_id, "error": str(exc)},
                )

        return processed_count

    def run_forever(self) -> None:
        self._log("Contract Sentinel 启动")
        self._log(f"每 {self.interval_seconds} 秒检查一次 OA")
        while True:
            self._log("正在检查 OA 待办...")
            with self.client.open_browser() as playwright:
                result = self._try_login_with_cookies(playwright)
                if result is False:
                    self._log("登录失败，本轮跳过")
                    self._log(f"等待 {self.interval_seconds} 秒后再次检查...")
                    time.sleep(self.interval_seconds)
                    continue
                if result is True:
                    # 交互式登录成功，需要重新用 Cookie 登录
                    result = self._try_login_with_cookies(playwright)
                    if result is False or result is True:
                        self._log("登录后重试失败，本轮跳过")
                        self._log(f"等待 {self.interval_seconds} 秒后再次检查...")
                        time.sleep(self.interval_seconds)
                        continue

                page, browser, context = result
                try:
                    processed = self.process_once_with_page(page)
                except RuntimeError as exc:
                    self._log(f"错误: {exc}")
                    self._log("本轮跳过，等待下一轮检查...")
                finally:
                    browser.close()
            self._log(f"等待 {self.interval_seconds} 秒后再次检查...")
            time.sleep(self.interval_seconds)
