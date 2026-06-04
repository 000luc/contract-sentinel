import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.audit_backends import (
    ClaudeCliBackend,
    DirectLlmBackend,
    SkillRequestBackend,
    create_audit_backend,
)
from src.contract_sentinel.audit_runner import AuditRunner
from src.contract_sentinel.workflow_models import AttachmentInfo, WorkflowItem, WorkflowMaterial


def make_material(tmp_path):
    workflow_dir = tmp_path / "workflow"
    raw_dir = workflow_dir / "raw"
    attachments_dir = workflow_dir / "attachments"
    audit_dir = workflow_dir / "audit"
    for directory in (raw_dir, attachments_dir, audit_dir):
        directory.mkdir(parents=True)

    (raw_dir / "workflow.json").write_text('{"workflow_id": "WF-001"}', encoding="utf-8")
    (raw_dir / "workflow.html").write_text("<html>detail</html>", encoding="utf-8")
    attachment_path = attachments_dir / "contract.docx"
    attachment_path.write_text("contract", encoding="utf-8")

    return WorkflowMaterial(
        item=WorkflowItem(workflow_id="WF-001", title="合同审批"),
        workflow_dir=workflow_dir,
        raw_dir=raw_dir,
        attachments_dir=attachments_dir,
        audit_dir=audit_dir,
        attachments=[AttachmentInfo(name="contract.docx", local_path=attachment_path)],
    )


def test_skill_request_backend_writes_request_and_status(tmp_path):
    material = make_material(tmp_path)
    backend = SkillRequestBackend()

    status = backend.run(material)

    request_path = material.audit_dir / "audit_request.md"
    status_path = material.audit_dir / "audit_status.json"
    request = request_path.read_text(encoding="utf-8")
    saved_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert status == saved_status
    assert saved_status["workflow_id"] == "WF-001"
    assert saved_status["status"] == "audit_pending"
    assert saved_status["backend"] == "skill_request"
    assert saved_status["workflow_dir"] == str(material.workflow_dir)
    assert saved_status["request_path"] == str(request_path)
    assert saved_status["required_skill"] == "contract-approval-auditing"
    assert "created_at" in saved_status

    assert str(material.workflow_dir) in request
    assert "contract-approval-auditing" in request
    assert "raw/workflow.json" in request
    assert "raw/workflow.html" in request
    assert "attachments" in request
    assert "contract.docx" in request
    assert "audit/audit.md" in request
    assert "不自动提交 OA" in request
    assert "审核发现问题清单" in request
    assert "审批批注" in request


def test_factory_defaults_to_skill_request_backend():
    assert isinstance(create_audit_backend("skill_request"), SkillRequestBackend)


def test_factory_creates_direct_llm_backend():
    backend = create_audit_backend("direct_llm", model="test-model")

    assert isinstance(backend, DirectLlmBackend)
    assert backend.model == "test-model"


def test_factory_creates_claude_cli_backend():
    backend = create_audit_backend("claude_cli", claude_command="custom-claude")

    assert isinstance(backend, ClaudeCliBackend)
    assert backend.command == "custom-claude"


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unknown audit backend"):
        create_audit_backend("missing")


def test_direct_llm_backend_calls_api_and_writes_audit_md_and_json(tmp_path, monkeypatch):
    material = make_material(tmp_path)
    (material.raw_dir / "workflow.json").write_text(
        '{"workflow_id":"WF-001","title":"设备采购合同"}', encoding="utf-8"
    )
    (material.raw_dir / "workflow.html").write_text(
        "<html>合同金额：100万</html>", encoding="utf-8"
    )
    attachment = material.attachments_dir / "contract.txt"
    attachment.write_text("预付款比例：30%", encoding="utf-8")

    class FakeLLM:
        def chat(self, messages, system=None):
            return """## 审核发现问题清单
1. 预付款比例过高（30%），建议不超过20%
2. 无验收条款

## 审批批注
建议增加验收节点，降低预付款比例。"""

    from src.contract_sentinel.audit_backends import DirectLlmBackend
    backend = DirectLlmBackend(model="deepseek-v4-flash", api_key="sk-test", api_base="https://api.deepseek.com/v1")
    backend.llm = FakeLLM()

    status = backend.run(material)

    assert (material.audit_dir / "audit.md").exists()
    assert (material.audit_dir / "audit.json").exists()

    audit_md = (material.audit_dir / "audit.md").read_text(encoding="utf-8")
    assert "预付款比例过高" in audit_md
    assert "审核发现问题清单" in audit_md
    assert "审批批注" in audit_md

    audit_json = json.loads((material.audit_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit_json["workflow_id"] == "WF-001"
    assert audit_json["status"] == "audit_completed"
    assert audit_json["backend"] == "direct_llm"

    assert status["status"] == "audit_completed"


def test_direct_llm_backend_handles_api_error(tmp_path, monkeypatch):
    material = make_material(tmp_path)

    class FailingLLM:
        def chat(self, messages, system=None):
            raise RuntimeError("API timeout")

    from src.contract_sentinel.audit_backends import DirectLlmBackend
    backend = DirectLlmBackend(model="deepseek-v4-flash", api_key="sk-test")
    backend.llm = FailingLLM()

    status = backend.run(material)

    assert status["status"] == "audit_failed"
    assert "API timeout" in status["error"]


def test_audit_runner_delegates_to_backend(tmp_path):
    material = make_material(tmp_path)
    backend = SkillRequestBackend()

    status = AuditRunner(backend).run(material)

    assert status["backend"] == "skill_request"


def test_claude_cli_backend_runs_command_and_writes_completed_audit(tmp_path, monkeypatch):
    material = make_material(tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="audit output", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    status = ClaudeCliBackend(command="custom-claude").run(material)

    args, kwargs = calls[0]
    assert args[0] == "custom-claude"
    assert args[1] == "-p"
    assert str(material.workflow_dir) in args[2]
    assert "contract-approval-auditing" in args[2]
    assert kwargs == {
        "cwd": material.workflow_dir,
        "capture_output": True,
        "text": True,
        "timeout": 900,
        "check": False,
    }
    assert (material.audit_dir / "audit.md").read_text(encoding="utf-8") == "audit output"
    saved_status = json.loads((material.audit_dir / "audit_status.json").read_text(encoding="utf-8"))
    assert status == saved_status
    assert saved_status["status"] == "audit_completed"
    assert saved_status["backend"] == "claude_cli"
    assert saved_status["audit_path"] == str(material.audit_dir / "audit.md")


def test_claude_cli_backend_writes_failed_status_and_raises(tmp_path, monkeypatch):
    material = make_material(tmp_path)

    def fake_run(args, **kwargs):
        return SimpleNamespace(returncode=2, stdout="partial audit", stderr="failure details")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="return code 2"):
        ClaudeCliBackend(command="custom-claude").run(material)

    assert (material.audit_dir / "audit.md").read_text(encoding="utf-8") == "partial audit"
    saved_status = json.loads((material.audit_dir / "audit_status.json").read_text(encoding="utf-8"))
    assert saved_status["status"] == "audit_failed"
    assert saved_status["backend"] == "claude_cli"
    assert saved_status["returncode"] == 2
    assert saved_status["stderr_summary"] == "failure details"
