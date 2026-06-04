from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .path_utils import build_workflow_dir_name
from .workflow_models import WorkflowItem, WorkflowMaterial


class WorkflowWriter:
    def __init__(self, output_root: str | Path):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def prepare(self, item: WorkflowItem) -> WorkflowMaterial:
        workflow_dir = self.output_root / build_workflow_dir_name(item.workflow_id, item.title)
        raw_dir = workflow_dir / "raw"
        attachments_dir = workflow_dir / "attachments"
        audit_dir = workflow_dir / "audit"

        for directory in (raw_dir, attachments_dir, audit_dir):
            directory.mkdir(parents=True, exist_ok=True)

        workflow_json = raw_dir / "workflow.json"
        workflow_json.write_text(
            json.dumps(asdict(item), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.append_log(workflow_dir, "prepared", {"workflow_id": item.workflow_id})

        return WorkflowMaterial(
            item=item,
            workflow_dir=workflow_dir,
            raw_dir=raw_dir,
            attachments_dir=attachments_dir,
            audit_dir=audit_dir,
            attachments=[],
        )

    def append_log(self, workflow_dir: str | Path, event: str, payload: dict[str, Any]) -> None:
        log_path = Path(workflow_dir) / "log.jsonl"
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
