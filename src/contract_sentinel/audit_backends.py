from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workflow_models import WorkflowMaterial


class AuditBackend(ABC):
    name: str

    @abstractmethod
    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        raise NotImplementedError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(material: WorkflowMaterial, status: dict[str, Any]) -> dict[str, Any]:
    material.audit_dir.mkdir(parents=True, exist_ok=True)
    (material.audit_dir / "audit_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return status


def _attachment_lines(material: WorkflowMaterial) -> list[str]:
    lines = []
    for attachment in material.attachments:
        path = attachment.local_path or material.attachments_dir / attachment.name
        lines.append(f"- {attachment.name}: {path}")
    if not lines:
        lines.append("- 无已登记附件；仍需检查 attachments 目录下全部文件。")
    return lines


def _build_audit_prompt(material: WorkflowMaterial) -> str:
    attachment_text = "\n".join(_attachment_lines(material))
    return f"""请对以下合同审批流程材料执行审核。

流程目录：{material.workflow_dir}

要求：
- 使用并遵循 contract-approval-auditing 审核规则。
- 读取 raw/workflow.json。
- 读取 raw/workflow.html。
- 读取 attachments 目录下全部文件。
- 输出审核发现问题清单和审批批注。
- 将审核结果写入 audit/audit.md。
- 不自动提交 OA。

附件清单：
{attachment_text}
"""


class SkillRequestBackend(AuditBackend):
    name = "skill_request"

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        material.audit_dir.mkdir(parents=True, exist_ok=True)
        request_path = material.audit_dir / "audit_request.md"
        request_path.write_text(_build_audit_prompt(material), encoding="utf-8")

        status = {
            "workflow_id": material.item.workflow_id,
            "status": "audit_pending",
            "backend": self.name,
            "created_at": _utc_now(),
            "workflow_dir": str(material.workflow_dir),
            "request_path": str(request_path),
            "required_skill": "contract-approval-auditing",
        }
        return _write_status(material, status)


class DirectLlmBackend(AuditBackend):
    name = "direct_llm"

    def __init__(self, model: str):
        self.model = model

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        status = {
            "workflow_id": material.item.workflow_id,
            "status": "audit_backend_not_enabled",
            "backend": self.name,
            "created_at": _utc_now(),
            "workflow_dir": str(material.workflow_dir),
            "model": self.model,
            "reason": "Direct LLM audit backend is not enabled yet.",
        }
        return _write_status(material, status)


class ClaudeCliBackend(AuditBackend):
    name = "claude_cli"

    def __init__(self, command: str = "claude"):
        self.command = command

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        material.audit_dir.mkdir(parents=True, exist_ok=True)
        prompt = _build_audit_prompt(material)
        result = subprocess.run(
            [self.command, "-p", prompt],
            cwd=material.workflow_dir,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )

        audit_path = material.audit_dir / "audit.md"
        audit_path.write_text(result.stdout, encoding="utf-8")
        status_value = "audit_completed" if result.returncode == 0 else "audit_failed"
        status = {
            "workflow_id": material.item.workflow_id,
            "status": status_value,
            "backend": self.name,
            "created_at": _utc_now(),
            "workflow_dir": str(material.workflow_dir),
            "audit_path": str(audit_path),
            "returncode": result.returncode,
            "stderr_summary": result.stderr.strip()[:4000],
        }
        _write_status(material, status)

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI audit failed with return code {result.returncode}")
        return status


def create_audit_backend(
    name: str,
    model: str = "deepseek-chat",
    claude_command: str = "claude",
) -> AuditBackend:
    if name == "skill_request":
        return SkillRequestBackend()
    if name == "direct_llm":
        return DirectLlmBackend(model)
    if name == "claude_cli":
        return ClaudeCliBackend(claude_command)
    raise ValueError(f"Unknown audit backend: {name}")
