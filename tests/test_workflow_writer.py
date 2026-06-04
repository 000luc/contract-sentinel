import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.path_utils import build_workflow_dir_name
from src.contract_sentinel.workflow_models import WorkflowItem
from src.contract_sentinel.workflow_writer import WorkflowWriter


def test_prepare_creates_material_dirs_and_writes_workflow_json(tmp_path):
    item = WorkflowItem(
        workflow_id="11-B-SH2026-30360",
        title="场地租赁合同评审",
        creator="张三",
        raw={"amount": "100"},
    )
    writer = WorkflowWriter(tmp_path / "out")

    material = writer.prepare(item)

    workflow_dir = tmp_path / "out" / build_workflow_dir_name(item.workflow_id, item.title)
    assert material.workflow_dir == workflow_dir
    assert material.raw_dir == workflow_dir / "raw"
    assert material.attachments_dir == workflow_dir / "attachments"
    assert material.audit_dir == workflow_dir / "audit"
    assert material.attachments == []

    assert material.raw_dir.is_dir()
    assert material.attachments_dir.is_dir()
    assert material.audit_dir.is_dir()

    workflow_data = json.loads((material.raw_dir / "workflow.json").read_text(encoding="utf-8"))
    assert workflow_data["workflow_id"] == "11-B-SH2026-30360"


def test_prepare_appends_prepared_log_entry(tmp_path):
    item = WorkflowItem(workflow_id="11-B-SH2026-30360", title="场地租赁合同评审")
    writer = WorkflowWriter(tmp_path / "out")

    material = writer.prepare(item)

    lines = (material.workflow_dir / "log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    log_entry = json.loads(lines[0])
    assert log_entry["event"] == "prepared"
    assert log_entry["payload"] == {"workflow_id": "11-B-SH2026-30360"}
    assert "time" in log_entry
