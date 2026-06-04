from __future__ import annotations

import time
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

    def process_once_with_page(self, page) -> int:
        if not self.client.ensure_login(page):
            raise RuntimeError("OA login failed")

        items = self.client.extract_todo_list(page)
        new_items = filter_new_contract_workflows(items, self.state, self.client)
        processed_count = 0

        for item in new_items:
            material = None
            try:
                self.state.mark_processing(item.workflow_id, {"title": item.title})
                material = self.writer.prepare(item)
                attachments = self.client.download_attachments(
                    page,
                    item,
                    material.attachments_dir,
                )
                self.client.save_detail_snapshot(page, material.raw_dir)
                material.attachments.extend(attachments)
                audit_status = self.audit_runner.run(material)
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
        while True:
            with self.client.open_browser() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context()
                    context.add_cookies(self.client.load_cookies())
                    page = context.new_page()
                    self.process_once_with_page(page)
                finally:
                    browser.close()
            time.sleep(self.interval_seconds)
