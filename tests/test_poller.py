import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.poller import ContractApprovalPoller, filter_new_contract_workflows
from src.contract_sentinel.workflow_models import AttachmentInfo, WorkflowItem, WorkflowMaterial


class RecordingState:
    def __init__(self, processed: set[str] | None = None) -> None:
        self.processed = processed or set()
        self.calls: list[tuple] = []

    def is_processed(self, workflow_id: str) -> bool:
        self.calls.append(("is_processed", workflow_id))
        return workflow_id in self.processed

    def mark_processing(self, workflow_id: str, metadata: dict) -> None:
        self.calls.append(("mark_processing", workflow_id, metadata))

    def mark_processed(self, workflow_id: str, metadata: dict) -> None:
        self.calls.append(("mark_processed", workflow_id, metadata))

    def mark_failed(self, workflow_id: str, error: str) -> None:
        self.calls.append(("mark_failed", workflow_id, error))


class FakeClient:
    def __init__(self, contract_ids: set[str], attachments=None, login_ok: bool = True) -> None:
        self.contract_ids = contract_ids
        self.attachments = attachments or []
        self.login_ok = login_ok
        self.calls: list[tuple] = []
        self.todo_items: list[WorkflowItem] = []

    def is_contract_workflow(self, item: WorkflowItem) -> bool:
        self.calls.append(("is_contract_workflow", item.workflow_id))
        return item.workflow_id in self.contract_ids

    def ensure_login(self, page) -> bool:
        self.calls.append(("ensure_login", page))
        return self.login_ok

    def extract_todo_list(self, page):
        self.calls.append(("extract_todo_list", page))
        return self.todo_items

    def count_todo_rows(self, page) -> int:
        self.calls.append(("count_todo_rows", page))
        return len(self.todo_items)

    def download_attachments(self, page, item, output_dir: Path):
        self.calls.append(("download_attachments", item.workflow_id, output_dir))
        return list(self.attachments)

    def save_detail_snapshot(self, page, raw_dir: Path) -> None:
        self.calls.append(("save_detail_snapshot", raw_dir))


class FakeWriter:
    def __init__(self, material: WorkflowMaterial) -> None:
        self.material = material
        self.calls: list[tuple] = []

    def prepare(self, item: WorkflowItem) -> WorkflowMaterial:
        self.calls.append(("prepare", item.workflow_id))
        return self.material

    def append_log(self, workflow_dir: Path, event: str, payload: dict) -> None:
        self.calls.append(("append_log", workflow_dir, event, payload))


class FakeAuditRunner:
    def __init__(self, status: dict | None = None, fail: bool = False) -> None:
        self.status = status or {"status": "ok"}
        self.fail = fail
        self.calls: list[tuple] = []

    def run(self, material: WorkflowMaterial) -> dict:
        self.calls.append(("run", material.item.workflow_id))
        if self.fail:
            raise RuntimeError("audit failed")
        return self.status


def make_material(tmp_path, item: WorkflowItem) -> WorkflowMaterial:
    return WorkflowMaterial(
        item=item,
        workflow_dir=tmp_path / item.workflow_id,
        raw_dir=tmp_path / item.workflow_id / "raw",
        attachments_dir=tmp_path / item.workflow_id / "attachments",
        audit_dir=tmp_path / item.workflow_id / "audit",
        attachments=[],
    )


def make_poller(state, writer, client, audit_runner) -> ContractApprovalPoller:
    poller = ContractApprovalPoller.__new__(ContractApprovalPoller)
    poller.approval_output_root = Path("approval-root")
    poller.state = state
    poller.writer = writer
    poller.client = client
    poller.audit_runner = audit_runner
    poller.interval_seconds = 1
    return poller


def test_filter_new_contract_workflows_keeps_contracts_and_skips_processed_only_by_workflow_id():
    items = [
        WorkflowItem(workflow_id="WF-1", title="合同审批"),
        WorkflowItem(workflow_id="WF-1", title="合同审批重复"),
        WorkflowItem(workflow_id="WF-2", title="普通审批"),
        WorkflowItem(workflow_id="WF-3", title="合同审批"),
    ]
    state = RecordingState(processed={"WF-3"})
    client = FakeClient(contract_ids={"WF-1", "WF-3"})

    result = filter_new_contract_workflows(items, state, client)

    assert [item.workflow_id for item in result] == ["WF-1"]
    assert ("is_processed", "WF-1") in state.calls
    assert ("is_processed", "WF-3") in state.calls
    assert ("is_processed", "WF-2") not in state.calls


def test_process_once_with_page_marks_success_after_download_snapshot_and_audit(tmp_path):
    item = WorkflowItem(workflow_id="WF-1", title="合同审批")
    material = make_material(tmp_path, item)
    attachment = AttachmentInfo(name="contract.docx", local_path=tmp_path / "contract.docx")
    state = RecordingState()
    client = FakeClient(contract_ids={"WF-1"}, attachments=[attachment])
    client.todo_items = [item]
    writer = FakeWriter(material)
    audit_runner = FakeAuditRunner({"status": "passed"})
    poller = make_poller(state, writer, client, audit_runner)

    processed = poller.process_once_with_page(page="page")

    assert processed == 1
    assert material.attachments == [attachment]
    assert state.calls[0][0:2] == ("is_processed", "WF-1")
    assert state.calls[1][0:2] == ("mark_processing", "WF-1")
    assert writer.calls[0] == ("prepare", "WF-1")
    assert client.calls[-2:] == [
        ("download_attachments", "WF-1", material.attachments_dir),
        ("save_detail_snapshot", material.raw_dir),
    ]
    assert audit_runner.calls == [("run", "WF-1")]
    processed_call = state.calls[2]
    assert processed_call[0:2] == ("mark_processed", "WF-1")
    assert processed_call[2] == {
        "title": "合同审批",
        "workflow_dir": str(material.workflow_dir),
        "audit_status": {"status": "passed"},
    }
    assert writer.calls[-1] == (
        "append_log",
        material.workflow_dir,
        "processed",
        {"workflow_id": "WF-1", "audit_status": {"status": "passed"}},
    )


def test_process_once_with_page_marks_failed_and_continues_other_workflows(tmp_path):
    failing = WorkflowItem(workflow_id="WF-1", title="合同审批1")
    succeeding = WorkflowItem(workflow_id="WF-2", title="合同审批2")
    materials = {
        "WF-1": make_material(tmp_path, failing),
        "WF-2": make_material(tmp_path, succeeding),
    }

    class PerItemWriter:
        def __init__(self) -> None:
            self.calls = []

        def prepare(self, item):
            self.calls.append(("prepare", item.workflow_id))
            return materials[item.workflow_id]

        def append_log(self, workflow_dir, event, payload):
            self.calls.append(("append_log", workflow_dir, event, payload))

    class PerItemAuditRunner:
        def __init__(self) -> None:
            self.calls = []

        def run(self, material):
            self.calls.append(("run", material.item.workflow_id))
            if material.item.workflow_id == "WF-1":
                raise RuntimeError("audit failed")
            return {"status": "passed"}

    state = RecordingState()
    client = FakeClient(contract_ids={"WF-1", "WF-2"})
    client.todo_items = [failing, succeeding]
    writer = PerItemWriter()
    audit_runner = PerItemAuditRunner()
    poller = make_poller(state, writer, client, audit_runner)

    processed = poller.process_once_with_page(page="page")

    assert processed == 1
    assert ("mark_failed", "WF-1", "audit failed") in state.calls
    assert any(call[0:2] == ("mark_processed", "WF-2") for call in state.calls)
    assert any(call[2] == "failed" for call in writer.calls if call[0] == "append_log")


def test_process_once_with_page_logs_prepare_failure_to_stable_failed_dir_and_continues(tmp_path):
    failing = WorkflowItem(workflow_id="WF-1", title="合同审批1")
    succeeding = WorkflowItem(workflow_id="WF-2", title="合同审批2")
    success_material = make_material(tmp_path, succeeding)

    class PrepareFailingWriter:
        def __init__(self) -> None:
            self.calls = []

        def prepare(self, item):
            self.calls.append(("prepare", item.workflow_id))
            if item.workflow_id == "WF-1":
                raise RuntimeError("prepare failed")
            return success_material

        def append_log(self, workflow_dir, event, payload):
            self.calls.append(("append_log", workflow_dir, event, payload))

    state = RecordingState()
    client = FakeClient(contract_ids={"WF-1", "WF-2"})
    client.todo_items = [failing, succeeding]
    writer = PrepareFailingWriter()
    poller = make_poller(state, writer, client, FakeAuditRunner({"status": "passed"}))
    poller.approval_output_root = tmp_path / "approval"

    processed = poller.process_once_with_page(page="page")

    assert processed == 1
    assert ("mark_failed", "WF-1", "prepare failed") in state.calls
    assert (
        "append_log",
        tmp_path / "approval" / ".failed" / "WF-1",
        "failed",
        {"workflow_id": "WF-1", "error": "prepare failed"},
    ) in writer.calls
    assert any(call[0:2] == ("mark_processed", "WF-2") for call in state.calls)


def test_process_once_with_page_raises_when_login_fails():
    poller = make_poller(
        state=RecordingState(),
        writer=SimpleNamespace(),
        client=FakeClient(contract_ids=set(), login_ok=False),
        audit_runner=SimpleNamespace(),
    )

    with pytest.raises(RuntimeError, match="OA login failed"):
        poller.process_once_with_page(page="page")
