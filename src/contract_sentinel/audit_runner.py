from __future__ import annotations

from typing import Any

from .audit_backends import AuditBackend
from .workflow_models import WorkflowMaterial


class AuditRunner:
    def __init__(self, backend: AuditBackend):
        self.backend = backend

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        return self.backend.run(material)
