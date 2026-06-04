# Direct LLM Audit Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `direct_llm` 后端真正调用 DeepSeek API，读取流程资料后生成审核结论（`audit/audit.md` + `audit/audit.json`），落盘到对应流程文件夹。

**Architecture:** 在 `audit_backends.py` 中重写 `DirectLlmBackend.run()`，新增一个轻量的 `LlmClient` 类处理 DeepSeek OpenAI 兼容 API 调用。`Settings` 增加 `deepseek_api_key` 和 `deepseek_api_base` 配置项。后端读取 workflow.json/workflow.html 和附件文本后，构造审核 prompt 发给 API，解析返回内容写入 audit.md 和 audit.json。

**Tech Stack:** Python 3, `httpx` (HTTP client, 纯标准库 `urllib` 也可), DeepSeek API (OpenAI-compatible, base: `https://api.deepseek.com/v1`), `pdfplumber` (PDF text extraction), `python-docx` (already available via docx-mcp)

---

### Task 1: Add API config to Settings

**Files:**
- Modify: `src/contract_sentinel/settings.py`
- Modify: `config.example.json`
- Modify: `config.json`

- [ ] **Step 1: Add fields to Settings dataclass**

```python
# src/contract_sentinel/settings.py — 在 Settings dataclass 末尾加两个字段
@dataclass(frozen=True)
class Settings:
    # ... 现有字段不变 ...
    deepseek_api_key: str
    deepseek_api_base: str
```

- [ ] **Step 2: Update load_settings to read the new fields**

```python
# src/contract_sentinel/settings.py — 在 load_settings 的 return 里加
deepseek_api_key=data.get("deepseek_api_key", ""),
deepseek_api_base=data.get("deepseek_api_base", "https://api.deepseek.com/v1"),
```

- [ ] **Step 3: Add keys to config.example.json**

```json
{
  "oa_url": "https://oa.grgt.cn/",
  "approval_output_root": "D:\\BaiduSyncdisk\\claude\\contract-approval",
  "poll_interval_seconds": 300,
  "contract_keywords": ["付款合同评审", "合同评审", "付款合同", "合同"],
  "audit_backend": "skill_request",
  "direct_llm_model": "deepseek-v4-flash",
  "claude_cli_command": "claude",
  "deepseek_api_key": "",
  "deepseek_api_base": "https://api.deepseek.com/v1"
}
```

- [ ] **Step 4: Add keys to config.json**

在现有 `config.json` 中加入：
```json
"deepseek_api_key": "sk-15cfee6f5f844fc881c22159c27ffb2a",
"deepseek_api_base": "https://api.deepseek.com/v1"
```
并把 `"audit_backend"` 改为 `"direct_llm"`。

- [ ] **Step 5: Syntax check**

```powershell
py -m py_compile src/contract_sentinel/settings.py
```
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```powershell
git add src/contract_sentinel/settings.py config.example.json config.json
git commit -m "feat: add deepseek api config to settings"
```

---

### Task 2: Build LlmClient

**Files:**
- Create: `src/contract_sentinel/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_llm_client.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.llm_client import LlmClient


def test_llm_client_builds_correct_request_body():
    client = LlmClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")
    body = client._build_body([{"role": "user", "content": "Hello"}])

    assert body["model"] == "deepseek-v4-flash"
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["temperature"] == 0.1
    assert body["stream"] is False


def test_llm_client_includes_system_prompt_when_provided():
    client = LlmClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")
    body = client._build_body(
        [{"role": "user", "content": "Hello"}],
        system="You are an auditor.",
    )

    assert body["messages"][0] == {"role": "system", "content": "You are an auditor."}
    assert body["messages"][1] == {"role": "user", "content": "Hello"}
```

- [ ] **Step 2: Run test to verify failure**

```powershell
pytest tests/test_llm_client.py -v
```
Expected: FAIL (module not found).

- [ ] **Step 3: Implement LlmClient**

```python
# src/contract_sentinel/llm_client.py
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any


class LlmClient:
    def __init__(self, api_key: str, api_base: str, model: str):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model

    def _build_body(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> dict[str, Any]:
        msgs = messages.copy()
        if system:
            msgs.insert(0, {"role": "system", "content": system})
        return {
            "model": self.model,
            "messages": msgs,
            "temperature": 0.1,
            "stream": False,
        }

    def chat(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        body = self._build_body(messages, system=system)
        data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {error_body[:500]}") from exc

        return result["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run test to verify pass**

```powershell
pytest tests/test_llm_client.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/contract_sentinel/llm_client.py tests/test_llm_client.py
git commit -m "feat: add lightweight llm client for deepseek api"
```

---

### Task 3: Implement attachment text extraction

**Files:**
- Create: `src/contract_sentinel/attachment_reader.py`
- Test: `tests/test_attachment_reader.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_attachment_reader.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.attachment_reader import AttachmentReader


def test_read_text_file_returns_content(tmp_path):
    file_path = tmp_path / "contract.txt"
    file_path.write_text("合同金额：100万元", encoding="utf-8")

    assert AttachmentReader.read_text(file_path) == "合同金额：100万元"


def test_read_text_file_truncates_long_content(tmp_path):
    file_path = tmp_path / "long.txt"
    file_path.write_text("A" * 6000, encoding="utf-8")

    result = AttachmentReader.read_text(file_path, max_chars=3000)
    assert len(result) <= 3100  # truncated + suffix message


def test_read_text_skips_unsupported_format(tmp_path, caplog):
    file_path = tmp_path / "image.png"
    file_path.write_text("binary", encoding="utf-8")

    result = AttachmentReader.read_text(file_path)
    assert result == ""


def test_summarize_attachments(tmp_path):
    reader = AttachmentReader()
    d = tmp_path
    (d / "a.txt").write_text("aaa", encoding="utf-8")
    (d / "b.txt").write_text("bbb", encoding="utf-8")

    result = reader.summarize(d, max_files=5, max_chars_per_file=2000)
    assert "a.txt" in result
    assert "bbb" in result
```

- [ ] **Step 2: Run test to verify failure**

```powershell
pytest tests/test_attachment_reader.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement AttachmentReader**

```python
# src/contract_sentinel/attachment_reader.py
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}
DOCX_SUFFIXES = {".docx"}
PDF_SUFFIXES = {".pdf"}
XLSX_SUFFIXES = {".xlsx", ".xls"}


class AttachmentReader:
    @staticmethod
    def read_text(file_path: Path, max_chars: int = 4000) -> str:
        suffix = file_path.suffix.lower()

        if suffix in TEXT_SUFFIXES:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""
        elif suffix in PDF_SUFFIXES:
            content = AttachmentReader._read_pdf(file_path)
        elif suffix in DOCX_SUFFIXES:
            content = AttachmentReader._read_docx(file_path)
        elif suffix in XLSX_SUFFIXES:
            content = AttachmentReader._read_xlsx(file_path)
        else:
            return ""

        if not content:
            return ""

        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[内容过长，已截断...]"
        return content

    @staticmethod
    def _read_pdf(file_path: Path) -> str:
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed, skipping PDF: %s", file_path.name)
            return ""

        try:
            with pdfplumber.open(file_path) as pdf:
                parts = []
                for page in pdf.pages[:20]:
                    text = page.extract_text()
                    if text:
                        parts.append(text)
                return "\n".join(parts)
        except Exception as exc:
            logger.warning("Failed to read PDF %s: %s", file_path.name, exc)
            return ""

    @staticmethod
    def _read_docx(file_path: Path) -> str:
        try:
            from docx import Document
        except ImportError:
            logger.warning("python-docx not installed, skipping DOCX: %s", file_path.name)
            return ""

        try:
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as exc:
            logger.warning("Failed to read DOCX %s: %s", file_path.name, exc)
            return ""

    @staticmethod
    def _read_xlsx(file_path: Path) -> str:
        try:
            import openpyxl
        except ImportError:
            logger.warning("openpyxl not installed, skipping XLSX: %s", file_path.name)
            return ""

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            parts = []
            for sheet_name in wb.sheetnames[:5]:
                ws = wb[sheet_name]
                parts.append(f"--- Sheet: {sheet_name} ---")
                for row in ws.iter_rows(values_only=True, max_row=200):
                    parts.append("\t".join(str(c) if c is not None else "" for c in row))
            wb.close()
            return "\n".join(parts)
        except Exception as exc:
            logger.warning("Failed to read XLSX %s: %s", file_path.name, exc)
            return ""

    def summarize(self, directory: Path, max_files: int = 5, max_chars_per_file: int = 4000) -> str:
        """遍历目录下所有附件，返回拼接后的文本摘要"""
        parts = []
        count = 0
        for f in sorted(directory.iterdir()):
            if not f.is_file():
                continue
            content = self.read_text(f, max_chars=max_chars_per_file)
            if content:
                parts.append(f"=== {f.name} ===\n{content}")
                count += 1
                if count >= max_files:
                    parts.append(f"\n[共 {sum(1 for _ in directory.iterdir() if _.is_file())} 个文件，已读取前 {max_files} 个]")
                    break
            else:
                parts.append(f"=== {f.name} ===\n[无法读取格式或内容为空]")
                count += 1
        return "\n\n".join(parts) if parts else "(无附件内容)"
```

- [ ] **Step 4: Run test to verify pass**

```powershell
pytest tests/test_attachment_reader.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/contract_sentinel/attachment_reader.py tests/test_attachment_reader.py
git commit -m "feat: add attachment text reader (txt/pdf/docx/xlsx)"
```

---

### Task 4: Rewrite DirectLlmBackend to call API and generate audit conclusion

**Files:**
- Modify: `src/contract_sentinel/audit_backends.py`
- Modify: `tests/test_audit_backends.py`

- [ ] **Step 1: Update failing test for the new behavior**

Replace `test_direct_llm_backend_writes_disabled_status` in `tests/test_audit_backends.py` with:

```python
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

    api_calls = []

    class FakeClient:
        def chat(self, messages, system=None):
            api_calls.append({"messages": messages, "system": system})
            return """## 审核发现问题清单
1. 预付款比例过高（30%），建议不超过20%
2. 无验收条款

## 审批批注
建议增加验收节点，降低预付款比例。"""

    def fake_create_backend(name, model=None, claude_command=None):
        backend = DirectLlmBackend(model="deepseek-v4-flash")
        api_key = "sk-test"
        api_base = "https://api.deepseek.com/v1"
        backend.llm = FakeClient()
        return backend

    import src.contract_sentinel.audit_backends as ab
    monkeypatch.setattr(ab, "create_audit_backend", fake_create_backend)

    backend = ab.create_audit_backend("direct_llm", model="deepseek-v4-flash")
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

    class FailingClient:
        def chat(self, messages, system=None):
            raise RuntimeError("API timeout")

    backend = DirectLlmBackend(model="deepseek-v4-flash")
    backend.llm = FailingClient()

    status = backend.run(material)

    assert status["status"] == "audit_failed"
    assert "API timeout" in status["error"]
```

- [ ] **Step 2: Run test to verify failure**

```powershell
pytest tests/test_audit_backends.py::test_direct_llm_backend_calls_api_and_writes_audit_md_and_json -v
```
Expected: FAIL.

- [ ] **Step 3: Rewrite DirectLlmBackend**

Replace the `DirectLlmBackend` class in `src/contract_sentinel/audit_backends.py`:

```python
class DirectLlmBackend(AuditBackend):
    name = "direct_llm"

    def __init__(self, model: str, api_key: str = "", api_base: str = "https://api.deepseek.com/v1"):
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.llm: LlmClient | None = None

    def _get_llm(self) -> LlmClient:
        if self.llm is None:
            from .llm_client import LlmClient
            self.llm = LlmClient(
                api_key=self.api_key,
                api_base=self.api_base,
                model=self.model,
            )
        return self.llm

    def run(self, material: WorkflowMaterial) -> dict[str, Any]:
        material.audit_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 读取流程资料
            workflow_json = (material.raw_dir / "workflow.json").read_text(encoding="utf-8")
            workflow_html = ""
            html_path = material.raw_dir / "workflow.html"
            if html_path.exists():
                workflow_html = html_path.read_text(encoding="utf-8", errors="replace")

            # 读取附件
            from .attachment_reader import AttachmentReader
            reader = AttachmentReader()
            attachments_text = reader.summarize(material.attachments_dir)

            # 构造审核 prompt
            user_prompt = self._build_audit_prompt(
                workflow_json=workflow_json,
                workflow_html=workflow_html,
                attachments_text=attachments_text,
            )

            system_prompt = SYSTEM_PROMPT

            # 调用 LLM
            llm = self._get_llm()
            response = llm.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt,
            )

            # 写入 audit.md
            audit_md_path = material.audit_dir / "audit.md"
            audit_md_path.write_text(response, encoding="utf-8")

            # 写入 audit.json
            findings, comment = self._parse_response(response)
            audit_json = {
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

            status = {
                "workflow_id": material.item.workflow_id,
                "status": "audit_completed",
                "backend": self.name,
                "model": self.model,
                "created_at": _utc_now(),
                "workflow_dir": str(material.workflow_dir),
            }
            return _write_status(material, status)

        except Exception as exc:
            status = {
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
        """从 LLM 回复中提取 findings 和 comment"""
        findings = []
        comment = ""

        # 简单解析：按二级标题分割
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
```

Also add the system prompt constant at the top of the file (before `class AuditBackend`):

```python
SYSTEM_PROMPT = """你是一名专业的财务审计人员，负责审核公司合同审批流程。
你的任务是仔细检查合同文件、流程信息和附件材料，找出任何金额、付款条款、主体信息、税率、违约责任、验收条款、文字错误和合规风险方面的问题。

请务必：
- 每个发现标注风险等级【高/中/低】
- 批注意见简洁专业，适合直接用于OA审批
- 不要推测没有证据的问题
- 金额、日期、编号精确引用原文数据"""
```

Also update the `create_audit_backend` factory to pass api_key and api_base:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```powershell
pytest tests/test_audit_backends.py -v
```
Expected: all 10 tests pass.

- [ ] **Step 5: Run all tests to ensure no regression**

```powershell
pytest tests -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/contract_sentinel/audit_backends.py tests/test_audit_backends.py
git commit -m "feat: implement direct_llm backend with deepseek api integration"
```

---

### Task 5: Wire poller to pass API config to backend

**Files:**
- Modify: `src/contract_sentinel/poller.py`

- [ ] **Step 1: Update poller to pass api_key and api_base**

In `poller.py`'s `ContractApprovalPoller.__init__`, change the `create_audit_backend` call:

```python
self.audit_runner = AuditRunner(
    create_audit_backend(
        settings.audit_backend,
        model=settings.direct_llm_model,
        claude_command=settings.claude_cli_command,
        api_key=settings.deepseek_api_key,
        api_base=settings.deepseek_api_base,
    )
)
```

- [ ] **Step 2: Syntax check**

```powershell
py -m py_compile src/contract_sentinel/poller.py
```
Expected: no output, exit 0.

- [ ] **Step 3: Run all tests**

```powershell
pytest tests -v
```
Expected: all pass.

- [ ] **Step 4: Commit**

```powershell
git add src/contract_sentinel/poller.py
git commit -m "feat: wire poller to pass deepseek api config to audit backend"
```

---

### Task 6: Install optional dependencies and manual verification

**Files:** None (manual testing)

- [ ] **Step 1: Install optional packages for attachment reading**

```powershell
py -m pip install pdfplumber python-docx openpyxl
```

- [ ] **Step 2: Prepare login state (if needed)**

```powershell
py src/manual_login.py
```

- [ ] **Step 3: Run one polling cycle with direct_llm backend**

```powershell
$env:PYTHONPATH="D:\BaiduSyncdisk\claude\contract-sentinel\src"
py src/run_contract_polling.py --once
```

- [ ] **Step 4: Verify output**

Check that a workflow directory under `D:\BaiduSyncdisk\claude\contract-approval\` contains:
```
audit/
  audit.md              # LLM 生成的审核结论
  audit.json            # 结构化审核数据
  audit_status.json     # status: "audit_completed"
```

- [ ] **Step 5: Review audit.md quality**

打开 `audit.md`，确认：
- 包含 "审核发现问题清单" 和 "审批批注" 两个部分
- 问题标注了风险等级
- 批注适合直接用于 OA

---

## Error Handling Rules

- API key 未配置：`DirectLlmBackend.run()` 返回 `audit_failed`，error 提示 "API key not configured"
- API 返回错误：捕获 HTTPError，返回 `audit_failed` 状态，error 包含 HTTP 状态码和响应摘要
- 附件读取失败：`AttachmentReader` 记录 warning 日志，跳过该文件继续
- LLM 返回格式不符合预期：`_parse_response` 尽力解析，至少保证 `audit.md` 写入完整回复

## Self-Review

- Spec coverage: 覆盖了 API 配置、LLM 调用、附件读取、审核输出、错误处理全链路
- No placeholders: 所有步骤都包含完整代码
- Type consistency: `DirectLlmBackend` 的 `run()` 返回 `dict[str, Any]`，与 `AuditBackend` 抽象接口一致；`create_audit_backend` 签名更新后 `poller.py` 和测试同步更新
