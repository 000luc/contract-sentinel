from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workflow_models import WorkflowMaterial

SYSTEM_PROMPT = """你是一名专业的财务审计人员，负责审核公司合同审批流程。
你的任务是仔细检查合同文件、流程信息和附件材料，找出任何金额、付款条款、主体信息、税率、违约责任、验收条款、文字错误和合规风险方面的问题。

请务必：
- 每个发现标注风险等级【高/中/低】
- 批注意见简洁专业，适合直接用于OA审批
- 不要推测没有证据的问题
- 金额、日期、编号精确引用原文数据"""


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

    def __init__(self, model: str, api_key: str = "", api_base: str = "https://api.deepseek.com/v1"):
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.llm: Any = None

    def _get_llm(self):
        if self.llm is None:
            from .llm_client import LLMClient
            self.llm = LLMClient(
                api_key=self.api_key,
                api_base=self.api_base,
                model=self.model,
            )
        return self.llm

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        material.audit_dir.mkdir(parents=True, exist_ok=True)

        try:
            workflow_json = (material.raw_dir / "workflow.json").read_text(encoding="utf-8")
            workflow_html = ""
            html_path = material.raw_dir / "workflow.html"
            if html_path.exists():
                workflow_html = html_path.read_text(encoding="utf-8", errors="replace")

            from .attachment_reader import AttachmentReader
            reader = AttachmentReader()
            attachments_text = reader.summarize(material.attachments_dir)

            user_prompt = self._build_audit_prompt(
                workflow_json=workflow_json,
                workflow_html=workflow_html,
                attachments_text=attachments_text,
            )

            llm = self._get_llm()
            response = llm.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system=SYSTEM_PROMPT,
            )

            audit_md_path = material.audit_dir / "audit.md"
            audit_md_path.write_text(response, encoding="utf-8")

            findings, comment = self._parse_response(response)
            audit_json: dict[str, Any] = {
                "workflow_id": material.item.workflow_id,
                "title": material.item.title,
                "status": "audit_completed",
                "backend": self.name,
                "model": self.model,
                "created_at": _utc_now(),
                "workflow_dir": str(material.workflow_dir),
                "findings": findings,
                "comment": comment,
            }
            (material.audit_dir / "audit.json").write_text(
                json.dumps(audit_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            status: dict[str, Any] = {
                "workflow_id": material.item.workflow_id,
                "status": "audit_completed",
                "backend": self.name,
                "model": self.model,
                "created_at": _utc_now(),
                "workflow_dir": str(material.workflow_dir),
            }
            return _write_status(material, status)

        except Exception as exc:
            status: dict[str, Any] = {
                "workflow_id": material.item.workflow_id,
                "status": "audit_failed",
                "backend": self.name,
                "model": self.model,
                "created_at": _utc_now(),
                "error": str(exc),
            }
            return _write_status(material, status)

    def _build_audit_prompt(
        self,
        workflow_json: str,
        workflow_html: str,
        attachments_text: str,
    ) -> str:
        html_snippet = workflow_html[:3000] if workflow_html else "(无)"
        return f"""请审核以下合同审批流程。

## 流程信息（workflow.json）
{workflow_json[:2000]}

## 详情页面内容（workflow.html 摘要）
{html_snippet}

## 合同附件内容
{attachments_text}

## 审核要求
请按以下维度逐一检查：
1. 合同金额是否合理、大小写是否一致
2. 付款条款是否合理（预付款比例、付款节点是否与交付匹配）
3. 签订主体是否与流程信息一致
4. 税率和发票条款是否明确
5. 违约责任是否对等
6. 履约期限和验收条款是否明确
7. 文字错误或逻辑矛盾
8. 其他合规风险

请输出两个部分：
## 审核发现问题清单
（逐条列出发现的问题，按严重程度排序。每条标注【高/中/低】风险等级）

## 审批批注
（给出可直接用于OA审批的建议文字，控制在200字以内）"""

    def _parse_response(self, response: str) -> tuple[list[dict], str]:
        findings: list[dict] = []
        comment = ""

        parts = response.split("## ")
        for part in parts:
            if part.startswith("审核发现问题清单") or part.startswith("审核发现"):
                lines = part.strip().split("\n")[1:]
                for line in lines:
                    line = line.strip()
                    if line and (line.startswith("-") or line.startswith("*") or line[0].isdigit()):
                        findings.append({"text": line.lstrip("-* 0123456789.")})
            elif part.startswith("审批批注"):
                comment = "\n".join(part.strip().split("\n")[1:]).strip()

        return findings, comment


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
    api_key: str = "",
    api_base: str = "https://api.deepseek.com/v1",
) -> AuditBackend:
    if name == "skill_request":
        return SkillRequestBackend()
    if name == "direct_llm":
        return DirectLlmBackend(model=model, api_key=api_key, api_base=api_base)
    if name == "claude_cli":
        return ClaudeCliBackend(claude_command)
    raise ValueError(f"Unknown audit backend: {name}")
