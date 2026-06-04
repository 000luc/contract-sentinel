from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AttachmentInfo:
    name: str
    href: str = ""
    local_path: Path | None = None


@dataclass(frozen=True)
class WorkflowItem:
    workflow_id: str
    title: str
    creator: str = ""
    created_at: str = ""
    detail_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowMaterial:
    item: WorkflowItem
    workflow_dir: Path
    raw_dir: Path
    attachments_dir: Path
    audit_dir: Path
    attachments: list[AttachmentInfo]
