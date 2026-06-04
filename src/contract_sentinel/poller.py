from __future__ import annotations

import sys
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

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _log(self, msg: str) -> None:
        print(f"[{self._now()}] {msg}", flush=True)

    def process_once_with_page(self, page) -> int:
        if not self.client.ensure_login(page):
            self._log("OA 登录已失效，请重新登录")
            raise RuntimeError("OA login failed")

        items = self.client.extract_todo_list(page)
        self._log(f"待办列表共 {len(items)} 条")
        new_items = filter_new_contract_workflows(items, self.state, self.client)

        if new_items:
            self._log(f"发现 {len(new_items)} 个新合同流程")
        else:
            self._log("无新合同流程")
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
                    self._log(f"  ✅ 审核完成: {name}")
                elif status == "audit_failed":
                    self._log(f"  ❌ 审核失败: {audit_status.get('error', '未知错误')}")
                else:
                    self._log(f"  ⏸ 审核状态: {status}")

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
                self._log(f"  ❌ 处理失败: {exc}")
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
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context()
                    context.add_cookies(self.client.load_cookies())
                    page = context.new_page()
                    processed = self.process_once_with_page(page)
                except RuntimeError as exc:
                    self._log(f"错误: {exc}")
                    self._log("本轮跳过，等待下一轮检查...")
                finally:
                    browser.close()
            self._log(f"等待 {self.interval_seconds} 秒后再次检查...")
            time.sleep(self.interval_seconds)
