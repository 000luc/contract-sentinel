from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class StateStore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_path = state_dir / "processed_workflows.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        tmp_path = self.state_dir / f"{self.state_path.name}.{uuid4().hex}.tmp"
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.state_path)

    def is_processed(self, workflow_id: str) -> bool:
        record = self._load().get(workflow_id)
        return bool(record and record.get("status") == "processed")

    def get(self, workflow_id: str) -> dict[str, Any]:
        return self._load().get(workflow_id, {})

    def mark_processing(self, workflow_id: str, metadata: dict[str, Any]) -> None:
        data = self._load()
        data[workflow_id] = {
            **metadata,
            "status": "processing",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save(data)

    def mark_processed(self, workflow_id: str, metadata: dict[str, Any]) -> None:
        data = self._load()
        data[workflow_id] = {
            **metadata,
            "status": "processed",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save(data)

    def mark_failed(self, workflow_id: str, error: str) -> None:
        data = self._load()
        previous = data.get(workflow_id, {})
        data[workflow_id] = {
            **previous,
            "status": "failed",
            "error": error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save(data)
