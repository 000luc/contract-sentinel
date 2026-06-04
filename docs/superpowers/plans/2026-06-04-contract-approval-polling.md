# Contract Approval Polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 定时轮询 OA 新审批流程，按流程编号去重，把流程资料和附件落到 `D:\BaiduSyncdisk\claude\contract-approval\`，并通过可切换的 `AuditBackend` 按单流程生成审核结论。

**Architecture:** 保留现有 Playwright 探索脚本的能力，但把流程拆成独立模块：配置、状态存储、OA 客户端、流程落盘、审核后端、轮询主程序。每个流程以 OA 流程编号为唯一主键，串行处理，失败可恢复，不自动提交 OA 审批意见。审核通过 `AuditBackend` 插件接口隔离，默认使用 `skill_request`，可切换到 `direct_llm` 或 `claude_cli`。

**Tech Stack:** Python 3, Playwright sync API, JSON/JSONL 本地状态文件, pathlib, pytest, pluggable audit backend, `contract-approval-auditing` skill rules, optional LLM API / Claude Code CLI.

---

## Scope

本计划只做本地自动化 MVP：

- 定时轮询 OA 待办。
- 只处理流程编号未出现过的新流程。
- 每个流程单独建目录。
- 下载流程详情、页面快照、附件。
- 单流程调用审核后端，默认生成 `contract-approval-auditing` 审核请求。
- 输出审核结论到对应流程目录。
- 不自动点击 OA 的同意、驳回、提交。
- 不保存明文密码，不新增验证码绕过逻辑。
- 不把审核实现绑死在某个 agent、CLI 或模型上。

## Target Directory Contract

每个新流程落盘到：

```text
D:\BaiduSyncdisk\claude\contract-approval\<流程编号>_<安全化标题>\
  raw\
    workflow.json
    workflow.html
    workflow.png
  attachments\
    <附件文件>
  audit\
    audit.md
    audit.json
    audit_request.md
    audit_status.json
  log.jsonl
```

本地处理状态放在：

```text
D:\BaiduSyncdisk\claude\contract-approval\.state\
  processed_workflows.json
  poller.log.jsonl
```

`processed_workflows.json` 只按流程编号去重，不按标题、发起人或附件 hash 去重。

## File Structure

- Create: `src/contract_sentinel/__init__.py`
  - 包标识，不放业务逻辑。
- Create: `src/contract_sentinel/settings.py`
  - 读取配置、默认路径、轮询间隔、关键词。
- Create: `src/contract_sentinel/state_store.py`
  - 读写已处理流程编号和流程状态。
- Create: `src/contract_sentinel/workflow_models.py`
  - 定义流程、附件、处理结果的数据结构。
- Create: `src/contract_sentinel/path_utils.py`
  - 安全化目录名和文件名。
- Create: `src/contract_sentinel/oa_client.py`
  - 使用 Playwright 登录态读取待办、进入详情、下载附件。
- Create: `src/contract_sentinel/workflow_writer.py`
  - 为单个流程创建目录并写入 raw、attachments、log。
- Create: `src/contract_sentinel/audit_backends.py`
  - 定义 `AuditBackend` 接口、`SkillRequestBackend`、`DirectLlmBackend`、`ClaudeCliBackend`。
- Create: `src/contract_sentinel/audit_runner.py`
  - 根据配置选择审核后端，并统一写入审核状态。
- Create: `src/contract_sentinel/poller.py`
  - 主轮询器，串起查新、落盘、审核、状态更新。
- Create: `src/run_contract_polling.py`
  - 命令行入口。
- Create: `tests/test_path_utils.py`
- Create: `tests/test_state_store.py`
- Create: `tests/test_workflow_writer.py`
- Create: `tests/test_audit_backends.py`
- Create: `tests/test_poller.py`
- Modify: `config.json`
  - 增加非敏感配置；后续应移除明文密码/API key。

---

### Task 1: Create Core Models

**Files:**
- Create: `src/contract_sentinel/__init__.py`
- Create: `src/contract_sentinel/workflow_models.py`

- [ ] **Step 1: Create package file**

```python
# src/contract_sentinel/__init__.py
"""Contract Sentinel automation package."""
```

- [ ] **Step 2: Define workflow models**

```python
# src/contract_sentinel/workflow_models.py
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
```

- [ ] **Step 3: Run import smoke test**

Run:

```powershell
py -c "from src.contract_sentinel.workflow_models import WorkflowItem; print(WorkflowItem(workflow_id='1', title='x'))"
```

Expected: prints a `WorkflowItem(...)` object.

- [ ] **Step 4: Commit**

```powershell
git add src/contract_sentinel/__init__.py src/contract_sentinel/workflow_models.py
git commit -m "feat: add workflow models"
```

---

### Task 2: Add Path Utilities

**Files:**
- Create: `src/contract_sentinel/path_utils.py`
- Test: `tests/test_path_utils.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_path_utils.py
from src.contract_sentinel.path_utils import build_workflow_dir_name, safe_filename


def test_safe_filename_removes_windows_forbidden_chars():
    assert safe_filename('11/B:合同*评审?') == '11_B_合同_评审_'


def test_safe_filename_limits_length():
    value = safe_filename('A' * 200, max_length=20)
    assert len(value) == 20


def test_build_workflow_dir_name_contains_id_and_title():
    assert build_workflow_dir_name('11-B-SH2026-30360', '场地租赁合同评审') == '11-B-SH2026-30360_场地租赁合同评审'
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_path_utils.py -v
```

Expected: FAIL because `src.contract_sentinel.path_utils` does not exist.

- [ ] **Step 3: Implement path utilities**

```python
# src/contract_sentinel/path_utils.py
from __future__ import annotations

import re

WINDOWS_FORBIDDEN_CHARS = r'[<>:"/\\|?*\r\n\t]'


def safe_filename(value: str, max_length: int = 120) -> str:
    cleaned = re.sub(WINDOWS_FORBIDDEN_CHARS, "_", value).strip(" .")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length]


def build_workflow_dir_name(workflow_id: str, title: str) -> str:
    return safe_filename(f"{workflow_id}_{title}", max_length=160)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
pytest tests/test_path_utils.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/contract_sentinel/path_utils.py tests/test_path_utils.py
git commit -m "feat: add workflow path utilities"
```

---

### Task 3: Add Settings

**Files:**
- Create: `src/contract_sentinel/settings.py`
- Modify: `config.json`

- [ ] **Step 1: Add non-sensitive config keys**

Add these keys to `config.json` while keeping existing keys untouched during this task:

```json
{
  "approval_output_root": "D:\\BaiduSyncdisk\\claude\\contract-approval",
  "poll_interval_seconds": 300,
  "contract_keywords": ["付款合同评审", "合同评审", "付款合同", "合同"],
  "audit_backend": "skill_request",
  "direct_llm_model": "deepseek-chat",
  "claude_cli_command": "claude"
}
```

- [ ] **Step 2: Implement settings loader**

```python
# src/contract_sentinel/settings.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_APPROVAL_OUTPUT_ROOT = Path(r"D:\BaiduSyncdisk\claude\contract-approval")


@dataclass(frozen=True)
class Settings:
    config_path: Path
    oa_url: str
    cookie_path: Path
    approval_output_root: Path
    poll_interval_seconds: int
    contract_keywords: list[str]
    audit_backend: str
    direct_llm_model: str
    claude_cli_command: str


def load_settings(config_path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    approval_root = Path(data.get("approval_output_root") or DEFAULT_APPROVAL_OUTPUT_ROOT)
    return Settings(
        config_path=config_path,
        oa_url=data.get("oa_url", "https://oa.grgt.cn/"),
        cookie_path=PROJECT_ROOT / "data" / "oa_cookies.json",
        approval_output_root=approval_root,
        poll_interval_seconds=int(data.get("poll_interval_seconds", 300)),
        contract_keywords=list(data.get("contract_keywords", ["付款合同评审", "合同评审", "付款合同", "合同"])),
        audit_backend=data.get("audit_backend", "skill_request"),
        direct_llm_model=data.get("direct_llm_model", "deepseek-chat"),
        claude_cli_command=data.get("claude_cli_command", "claude"),
    )
```

- [ ] **Step 3: Run settings smoke test**

Run:

```powershell
py -c "from src.contract_sentinel.settings import load_settings; s=load_settings(); print(s.approval_output_root); print(s.poll_interval_seconds); print(s.audit_backend)"
```

Expected: prints `D:\BaiduSyncdisk\claude\contract-approval`, `300`, and `skill_request`.

- [ ] **Step 4: Commit**

```powershell
git add config.json src/contract_sentinel/settings.py
git commit -m "feat: add polling settings"
```

---

### Task 4: Add Local State Store

**Files:**
- Create: `src/contract_sentinel/state_store.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state_store.py
from src.contract_sentinel.state_store import StateStore


def test_state_store_marks_workflow_processed(tmp_path):
    store = StateStore(tmp_path / ".state")
    assert not store.is_processed("11-B-SH2026-30360")

    store.mark_processed("11-B-SH2026-30360", {"title": "场地租赁"})

    assert store.is_processed("11-B-SH2026-30360")


def test_state_store_records_status(tmp_path):
    store = StateStore(tmp_path / ".state")
    store.mark_failed("11-B-SH2026-30360", "download failed")

    record = store.get("11-B-SH2026-30360")
    assert record["status"] == "failed"
    assert record["error"] == "download failed"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_state_store.py -v
```

Expected: FAIL because `state_store` does not exist.

- [ ] **Step 3: Implement state store**

```python
# src/contract_sentinel/state_store.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


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
        tmp_path = self.state_path.with_suffix(".tmp")
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
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
pytest tests/test_state_store.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/contract_sentinel/state_store.py tests/test_state_store.py
git commit -m "feat: add workflow state store"
```

---

### Task 5: Add Workflow Writer

**Files:**
- Create: `src/contract_sentinel/workflow_writer.py`
- Test: `tests/test_workflow_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workflow_writer.py
import json

from src.contract_sentinel.workflow_models import WorkflowItem
from src.contract_sentinel.workflow_writer import WorkflowWriter


def test_prepare_workflow_dirs_creates_expected_layout(tmp_path):
    writer = WorkflowWriter(tmp_path)
    item = WorkflowItem(
        workflow_id="11-B-SH2026-30360",
        title="场地租赁合同评审",
        creator="张三",
        created_at="2026-06-04",
    )

    material = writer.prepare(item)

    assert material.workflow_dir.exists()
    assert material.raw_dir.exists()
    assert material.attachments_dir.exists()
    assert material.audit_dir.exists()
    assert (material.raw_dir / "workflow.json").exists()

    payload = json.loads((material.raw_dir / "workflow.json").read_text(encoding="utf-8"))
    assert payload["workflow_id"] == "11-B-SH2026-30360"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_workflow_writer.py -v
```

Expected: FAIL because `workflow_writer` does not exist.

- [ ] **Step 3: Implement writer**

```python
# src/contract_sentinel/workflow_writer.py
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .path_utils import build_workflow_dir_name
from .workflow_models import WorkflowItem, WorkflowMaterial


class WorkflowWriter:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    def prepare(self, item: WorkflowItem) -> WorkflowMaterial:
        workflow_dir = self.output_root / build_workflow_dir_name(item.workflow_id, item.title)
        raw_dir = workflow_dir / "raw"
        attachments_dir = workflow_dir / "attachments"
        audit_dir = workflow_dir / "audit"
        for path in (raw_dir, attachments_dir, audit_dir):
            path.mkdir(parents=True, exist_ok=True)

        payload = asdict(item)
        (raw_dir / "workflow.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
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

    def append_log(self, workflow_dir: Path, event: str, payload: dict) -> None:
        row = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": payload,
        }
        log_path = workflow_dir / "log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
pytest tests/test_workflow_writer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/contract_sentinel/workflow_writer.py tests/test_workflow_writer.py
git commit -m "feat: add workflow directory writer"
```

---

### Task 6: Extract OA Client from Prototype

**Files:**
- Create: `src/contract_sentinel/oa_client.py`
- Reference: `src/run_workflow.py`
- Reference: `src/auto_login.py`

- [ ] **Step 1: Create OA client skeleton**

```python
# src/contract_sentinel/oa_client.py
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

from .path_utils import safe_filename
from .workflow_models import AttachmentInfo, WorkflowItem


class OAClient:
    def __init__(self, oa_url: str, cookie_path: Path, contract_keywords: list[str]):
        self.oa_url = oa_url
        self.cookie_path = cookie_path
        self.contract_keywords = contract_keywords

    def load_cookies(self) -> list[dict]:
        if not self.cookie_path.exists():
            raise FileNotFoundError(f"Cookie 文件不存在，请先人工登录并保存 Cookie: {self.cookie_path}")
        return json.loads(self.cookie_path.read_text(encoding="utf-8"))

    def is_contract_workflow(self, item: WorkflowItem) -> bool:
        return any(keyword in item.title for keyword in self.contract_keywords)

    def open_browser(self):
        return sync_playwright()
```

- [ ] **Step 2: Implement login state check**

Add this method to `OAClient`:

```python
    def ensure_login(self, page: Page) -> bool:
        page.goto(self.oa_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        body = page.inner_text("body")
        indicators = ["门户", "流程", "待办", "流程中心", "个人门户", "前端用户中心"]
        return any(indicator in body for indicator in indicators)
```

- [ ] **Step 3: Implement todo extraction**

Add this method to `OAClient`:

```python
    def extract_todo_list(self, page: Page) -> list[WorkflowItem]:
        rows = page.evaluate(
            """() => {
                const result = [];
                const seen = new Set();
                for (const row of document.querySelectorAll('tr')) {
                    const cells = Array.from(row.querySelectorAll('td')).map(td => td.innerText.trim());
                    const texts = cells.filter(Boolean);
                    const joined = texts.join(' ');
                    const idMatch = joined.match(/[0-9]{2}-[A-Z]-[A-Z]{2}[0-9]{4}-[0-9]+/);
                    if (!idMatch) continue;

                    const workflowId = idMatch[0];
                    if (seen.has(workflowId)) continue;
                    seen.add(workflowId);

                    const link = row.querySelector('a');
                    result.push({
                        workflow_id: workflowId,
                        title: texts[0] || workflowId,
                        creator: texts[1] || '',
                        created_at: texts.find(t => /^\\d{4}-\\d{2}-\\d{2}/.test(t)) || '',
                        detail_url: link ? (link.getAttribute('data-link') || link.href || '') : '',
                        raw: { texts }
                    });
                }
                return result;
            }"""
        )
        return [WorkflowItem(**row) for row in rows]
```

- [ ] **Step 4: Implement attachment download**

Add this method to `OAClient`:

```python
    def download_attachments(self, page: Page, item: WorkflowItem, output_dir: Path) -> list[AttachmentInfo]:
        detail_url = item.detail_url
        if detail_url.startswith("/"):
            detail_url = self.oa_url.rstrip("/") + detail_url
        if detail_url:
            page.goto(detail_url, wait_until="load", timeout=60000)
            page.wait_for_timeout(5000)

        attachments: list[AttachmentInfo] = []
        links = page.locator("a").all()
        for link in links:
            href = link.get_attribute("href") or ""
            text = (link.inner_text() or "").strip()
            if not href.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
                continue
            attachments.append(AttachmentInfo(name=text or safe_filename(href), href=href))

        download_buttons = page.locator(".icon-coms-download")
        for index in range(download_buttons.count()):
            with page.expect_download(timeout=20000) as download_info:
                download_buttons.nth(index).click(force=True)
            download = download_info.value
            target = output_dir / safe_filename(download.suggested_filename, max_length=180)
            download.save_as(target)
            attachments.append(AttachmentInfo(name=download.suggested_filename, local_path=target))

        return attachments
```

- [ ] **Step 5: Add page snapshot helpers**

Add this method to `OAClient`:

```python
    def save_detail_snapshot(self, page: Page, raw_dir: Path) -> None:
        (raw_dir / "workflow.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(raw_dir / "workflow.png"), full_page=True)
```

- [ ] **Step 6: Run syntax check**

Run:

```powershell
py -m py_compile src/contract_sentinel/oa_client.py
```

Expected: no output and exit code 0.

- [ ] **Step 7: Commit**

```powershell
git add src/contract_sentinel/oa_client.py
git commit -m "feat: add OA workflow client"
```

---

### Task 7: Add Audit Backends

**Files:**
- Create: `src/contract_sentinel/audit_backends.py`
- Create: `src/contract_sentinel/audit_runner.py`
- Test: `tests/test_audit_backends.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_audit_backends.py
import json

from src.contract_sentinel.audit_backends import SkillRequestBackend, create_audit_backend
from src.contract_sentinel.workflow_models import WorkflowItem
from src.contract_sentinel.workflow_writer import WorkflowWriter


def test_skill_request_backend_writes_request_and_status(tmp_path):
    writer = WorkflowWriter(tmp_path)
    material = writer.prepare(WorkflowItem(workflow_id="11-B-SH2026-30360", title="场地租赁合同评审"))

    result = SkillRequestBackend().run(material)

    assert result["status"] == "audit_pending"
    assert (material.audit_dir / "audit_request.md").exists()
    assert (material.audit_dir / "audit_status.json").exists()
    payload = json.loads((material.audit_dir / "audit_status.json").read_text(encoding="utf-8"))
    assert payload["backend"] == "skill_request"


def test_create_audit_backend_defaults_to_skill_request():
    backend = create_audit_backend("skill_request")
    assert isinstance(backend, SkillRequestBackend)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_audit_backends.py -v
```

Expected: FAIL because `audit_backends` does not exist.

- [ ] **Step 3: Implement audit backend interface and default backend**

```python
# src/contract_sentinel/audit_backends.py
from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from .workflow_models import WorkflowMaterial


AUDIT_PROMPT_TEMPLATE = """请使用 contract-approval-auditing 审核规则审核以下单个 OA 审批流程。

流程目录：{workflow_dir}

必须执行：
1. 先确认目录和附件存在。
2. 读取 raw/workflow.json、raw/workflow.html 和 attachments 下全部文件。
3. 对流程单、合同正文、附件做金额、付款节点、主体、税率、期限、文字错误和合规风险交叉核对。
4. 输出两个部分：审核发现问题清单、审批批注。
5. 把最终结果写入 audit/audit.md。

注意：不要自动提交 OA 审批意见。
"""


class AuditBackend(ABC):
    name: str

    @abstractmethod
    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        raise NotImplementedError


class SkillRequestBackend(AuditBackend):
    name = "skill_request"

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        request_path = material.audit_dir / "audit_request.md"
        request_path.write_text(
            AUDIT_PROMPT_TEMPLATE.format(workflow_dir=material.workflow_dir),
            encoding="utf-8",
        )
        status = {
            "workflow_id": material.item.workflow_id,
            "status": "audit_pending",
            "backend": self.name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "workflow_dir": str(material.workflow_dir),
            "request_path": str(request_path),
            "required_skill": "contract-approval-auditing",
        }
        (material.audit_dir / "audit_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return status


class DirectLlmBackend(AuditBackend):
    name = "direct_llm"

    def __init__(self, model: str):
        self.model = model

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        status = {
            "workflow_id": material.item.workflow_id,
            "status": "audit_backend_not_enabled",
            "backend": self.name,
            "model": self.model,
            "reason": "direct_llm 需要后续任务实现附件解析、API 调用和输出校验",
        }
        (material.audit_dir / "audit_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return status


class ClaudeCliBackend(AuditBackend):
    name = "claude_cli"

    def __init__(self, command: str = "claude"):
        self.command = command

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        prompt = AUDIT_PROMPT_TEMPLATE.format(workflow_dir=material.workflow_dir)
        audit_path = material.audit_dir / "audit.md"
        result = subprocess.run(
            [self.command, "-p", prompt],
            cwd=str(material.workflow_dir),
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
        audit_path.write_text(result.stdout, encoding="utf-8")
        status = {
            "workflow_id": material.item.workflow_id,
            "status": "audit_completed" if result.returncode == 0 else "audit_failed",
            "backend": self.name,
            "returncode": result.returncode,
            "stderr": result.stderr[-2000:],
            "audit_path": str(audit_path),
        }
        (material.audit_dir / "audit_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude cli audit failed: {result.stderr[-500:]}")
        return status


def create_audit_backend(name: str, *, model: str = "deepseek-chat", claude_command: str = "claude") -> AuditBackend:
    if name == "skill_request":
        return SkillRequestBackend()
    if name == "direct_llm":
        return DirectLlmBackend(model=model)
    if name == "claude_cli":
        return ClaudeCliBackend(command=claude_command)
    raise ValueError(f"Unsupported audit backend: {name}")
```

- [ ] **Step 4: Implement audit runner**

```python
# src/contract_sentinel/audit_runner.py
from __future__ import annotations

from .audit_backends import AuditBackend
from .workflow_models import WorkflowMaterial


class AuditRunner:
    def __init__(self, backend: AuditBackend):
        self.backend = backend

    def run(self, material: WorkflowMaterial) -> dict:
        return self.backend.run(material)
```

- [ ] **Step 5: Run tests to verify pass**

Run:

```powershell
pytest tests/test_audit_backends.py -v
```

Expected: PASS.

- [ ] **Step 6: Run syntax check**

Run:

```powershell
py -m py_compile src/contract_sentinel/audit_backends.py
py -m py_compile src/contract_sentinel/audit_runner.py
```

Expected: no output and exit code 0.

- [ ] **Step 7: Commit**

```powershell
git add src/contract_sentinel/audit_backends.py src/contract_sentinel/audit_runner.py tests/test_audit_backends.py
git commit -m "feat: add pluggable audit backends"
```

Note: 默认 `skill_request` 不直接拉起 agent，只生成审核请求。`direct_llm` 作为后续生产化方向，需另行实现附件解析、API 调用和输出校验。`claude_cli` 可实验性拉起 Claude Code CLI，但必须先做端到端兼容性测试。

---

### Task 8: Add Poller Orchestration

**Files:**
- Create: `src/contract_sentinel/poller.py`
- Test: `tests/test_poller.py`

- [ ] **Step 1: Write failing unit test for dedupe**

```python
# tests/test_poller.py
from src.contract_sentinel.poller import filter_new_contract_workflows
from src.contract_sentinel.workflow_models import WorkflowItem


class FakeState:
    def __init__(self, processed):
        self.processed = set(processed)

    def is_processed(self, workflow_id):
        return workflow_id in self.processed


class FakeClient:
    def is_contract_workflow(self, item):
        return "合同" in item.title


def test_filter_new_contract_workflows_uses_workflow_id_only():
    items = [
        WorkflowItem(workflow_id="A-1", title="付款合同评审"),
        WorkflowItem(workflow_id="A-2", title="付款合同评审"),
        WorkflowItem(workflow_id="A-3", title="普通报销"),
    ]

    result = filter_new_contract_workflows(items, FakeState({"A-1"}), FakeClient())

    assert [item.workflow_id for item in result] == ["A-2"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
pytest tests/test_poller.py -v
```

Expected: FAIL because `poller` does not exist.

- [ ] **Step 3: Implement poller functions**

```python
# src/contract_sentinel/poller.py
from __future__ import annotations

import time
from typing import Protocol

from playwright.sync_api import Page

from .audit_backends import create_audit_backend
from .audit_runner import AuditRunner
from .oa_client import OAClient
from .settings import Settings
from .state_store import StateStore
from .workflow_models import WorkflowItem
from .workflow_writer import WorkflowWriter


class StateLike(Protocol):
    def is_processed(self, workflow_id: str) -> bool: ...


class ClientLike(Protocol):
    def is_contract_workflow(self, item: WorkflowItem) -> bool: ...


def filter_new_contract_workflows(
    items: list[WorkflowItem],
    state: StateLike,
    client: ClientLike,
) -> list[WorkflowItem]:
    return [
        item
        for item in items
        if client.is_contract_workflow(item) and not state.is_processed(item.workflow_id)
    ]


class ContractApprovalPoller:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state = StateStore(settings.approval_output_root / ".state")
        self.writer = WorkflowWriter(settings.approval_output_root)
        audit_backend = create_audit_backend(
            settings.audit_backend,
            model=settings.direct_llm_model,
            claude_command=settings.claude_cli_command,
        )
        self.audit_runner = AuditRunner(audit_backend)
        self.client = OAClient(settings.oa_url, settings.cookie_path, settings.contract_keywords)

    def process_once_with_page(self, page: Page) -> int:
        if not self.client.ensure_login(page):
            raise RuntimeError("OA 登录态失效，请人工重新登录后再运行")

        items = self.client.extract_todo_list(page)
        new_items = filter_new_contract_workflows(items, self.state, self.client)

        processed_count = 0
        for item in new_items:
            self.state.mark_processing(item.workflow_id, {"title": item.title})
            material = self.writer.prepare(item)
            try:
                attachments = self.client.download_attachments(page, item, material.attachments_dir)
                self.client.save_detail_snapshot(page, material.raw_dir)
                material.attachments.extend(attachments)
                audit_status = self.audit_runner.run(material)
                self.state.mark_processed(
                    item.workflow_id,
                    {"title": item.title, "workflow_dir": str(material.workflow_dir), "audit_status": audit_status},
                )
                self.writer.append_log(material.workflow_dir, "processed", {"workflow_id": item.workflow_id})
                processed_count += 1
            except Exception as exc:
                self.state.mark_failed(item.workflow_id, str(exc))
                self.writer.append_log(material.workflow_dir, "failed", {"error": str(exc)})
        return processed_count

    def run_forever(self) -> None:
        while True:
            with self.client.open_browser() as playwright:
                browser = playwright.chromium.launch(headless=False)
                context = browser.new_context()
                context.add_cookies(self.client.load_cookies())
                page = context.new_page()
                try:
                    self.process_once_with_page(page)
                finally:
                    browser.close()
            time.sleep(self.settings.poll_interval_seconds)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
pytest tests/test_poller.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/contract_sentinel/poller.py tests/test_poller.py
git commit -m "feat: add contract approval poller"
```

---

### Task 9: Add CLI Entrypoint

**Files:**
- Create: `src/run_contract_polling.py`

- [ ] **Step 1: Implement CLI**

```python
# src/run_contract_polling.py
from __future__ import annotations

import argparse

from contract_sentinel.poller import ContractApprovalPoller
from contract_sentinel.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll OA contract approval workflows.")
    parser.add_argument("--once", action="store_true", help="Run one polling cycle and exit.")
    args = parser.parse_args()

    settings = load_settings()
    poller = ContractApprovalPoller(settings)

    if args.once:
        with poller.client.open_browser() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            context.add_cookies(poller.client.load_cookies())
            page = context.new_page()
            try:
                count = poller.process_once_with_page(page)
                print(f"processed={count}")
            finally:
                browser.close()
        return

    poller.run_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run syntax check**

Run:

```powershell
py -m py_compile src/run_contract_polling.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run one-cycle command after Cookie exists**

Run:

```powershell
$env:PYTHONPATH="D:\BaiduSyncdisk\claude\contract-sentinel\src"
py src/run_contract_polling.py --once
```

Expected:

```text
processed=<number>
```

If login state expired, expected failure:

```text
RuntimeError: OA 登录态失效，请人工重新登录后再运行
```

- [ ] **Step 4: Commit**

```powershell
git add src/run_contract_polling.py
git commit -m "feat: add contract polling CLI"
```

---

### Task 10: Manual End-to-End Verification

**Files:**
- Read: `D:\BaiduSyncdisk\claude\contract-approval\`
- Read: `D:\BaiduSyncdisk\claude\contract-approval\.state\processed_workflows.json`

- [ ] **Step 1: Prepare login state**

Run the existing login helper if Cookie is missing or expired:

```powershell
py src/auto_login.py
```

Expected: `data\oa_cookies.json` exists.

- [ ] **Step 2: Run one polling cycle**

```powershell
$env:PYTHONPATH="D:\BaiduSyncdisk\claude\contract-sentinel\src"
py src/run_contract_polling.py --once
```

Expected: at least one of:

```text
processed=0
processed=1
processed=<N>
```

- [ ] **Step 3: Verify output directory**

Run:

```powershell
Get-ChildItem D:\BaiduSyncdisk\claude\contract-approval -Directory
```

Expected: new workflow directories named like `<流程编号>_<流程标题>`.

- [ ] **Step 4: Verify one workflow contents**

Run:

```powershell
Get-ChildItem "D:\BaiduSyncdisk\claude\contract-approval\<流程编号>_<流程标题>" -Recurse
```

Expected:

```text
raw\workflow.json
raw\workflow.html
raw\workflow.png
attachments\<附件文件>
audit\audit_request.md
audit\audit_status.json
log.jsonl
```

- [ ] **Step 5: Verify default audit backend output**

Default backend is `skill_request`. It should generate:

```text
audit\audit_request.md
audit\audit_status.json
```

`audit_status.json` should contain:

```json
{
  "status": "audit_pending",
  "backend": "skill_request",
  "required_skill": "contract-approval-auditing"
}
```

- [ ] **Step 6: Run contract approval auditing manually per workflow**

Open `audit\audit_request.md` for one workflow and run the Codex task using `contract-approval-auditing`.

Expected generated files:

```text
audit\audit.md
audit\audit.json
```

`audit.md` must contain:

```markdown
## 审核发现问题清单
## 审批批注
```

- [ ] **Step 6: Commit verification notes**

```powershell
git add D:\BaiduSyncdisk\claude\contract-sentinel\docs\superpowers\plans\2026-06-04-contract-approval-polling.md
git commit -m "docs: add contract approval polling implementation plan"
```

---

## Error Handling Rules

- Cookie 不存在：停止，提示先人工登录或运行 `src/auto_login.py`。
- 登录态失效：停止本轮，不继续下载，不标记为已处理。
- 流程编号为空：跳过该行并写入 poller 日志。
- 详情页打不开：该流程标记为 `failed`，下次允许人工清理状态后重跑。
- 附件下载失败：该流程标记为 `failed`，不进入审核。
- `skill_request` 未实际执行：流程可以标记为资料已落盘，但 `audit_status.json` 保持 `audit_pending`。
- `direct_llm` 未配置 API 或附件解析失败：该流程标记为 `audit_backend_not_enabled` 或 `audit_failed`，不自动回填 OA。
- `claude_cli` 返回非 0：写入 stderr 摘要，标记为 `audit_failed`；这台机器的 DeepSeek 兼容链路必须先单独实测。
- 审核发现高风险：只写结论，不自动回填 OA。

## Self-Review

- Spec coverage: 已覆盖定时轮询、新流程识别、流程编号去重、流程目录落盘、附件下载、插件式单流程审核、失败恢复。
- Placeholder scan: 未发现未决占位语句。
- Type consistency: `WorkflowItem.workflow_id`、`WorkflowMaterial.workflow_dir`、`StateStore.mark_processed`、`AuditBackend.run` 在所有任务中命名一致。
- Scope check: 本计划只做本地 MVP，不包含 OA 自动提交、企业微信通知、后台服务安装。
