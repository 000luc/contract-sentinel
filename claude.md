# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Contract Sentinel — OA 合同审批自动轮询工具。定时读取泛微 e-cology OA 待办，按流程编号识别新合同审批流程，下载流程详情和附件到本地，通过可切换的审核后端生成审核结论。**只读不写**：不点击同意/驳回/提交，不修改 OA 数据。

当前状态：**MVP v0.3.1**，完整的轮询 → 落盘 → 审核链路已跑通，51 个单元测试全部通过。

## Key Architecture

```
src/run_contract_polling.py    CLI 入口（--once / 持续轮询）
src/run_workflow.py            单流程手动处理脚本（指定流程目录执行审核）

src/contract_sentinel/
  settings.py                  配置加载（config.json → Settings dataclass）
  state_store.py               已处理流程去重状态（processed_workflows.json，先写 tmp 再原子 replace）
  path_utils.py                Windows 安全文件名处理（去非法字符、保留名规避）
  workflow_models.py           WorkflowItem / WorkflowMaterial / AttachmentInfo 数据类
  oa_client.py                 Playwright OA 页面读取 + 附件下载（4 种下载策略 + 文件魔数校验 + .doc→.docx 自动转换）
  workflow_writer.py           流程目录创建、workflow.json/ log.jsonl 落盘
  llm_client.py                轻量 LLM API 客户端（纯标准库 urllib，兼容 OpenAI 接口）
  attachment_reader.py         附件文本提取（TXT/PDF/DOCX/XLSX），供 direct_llm 后端使用
  audit_backends.py            审核后端接口 + 3 种实现（factory 模式）
  audit_runner.py              审核后端调用封装
  poller.py                    轮询主流程（登录 → 待办提取 → 去重筛选 → 落盘 → 下载 → 审核 → 状态更新）

tests/                         51 个 pytest 测试，全部用 Fake/Mock，不依赖 OA 或浏览器

src/ 根目录还有一批实验性脚本：
  auto_login.py / manual_login.py      OA 登录工具
  test_captcha_*.py                    验证码识别测试
  test_attachment_download.py          附件下载测试
  test_contract_review.py              合同审核测试
```

### 轮询流程（poller.py）

1. `OAClient.ensure_login()` — 检查 Cookie 是否有效（URL 跳转 + 页面关键词）
2. `OAClient.count_todo_rows()` — 统计待办总数
3. `OAClient.extract_todo_list()` — JS evaluate 提取待办表格，按流程编号正则
4. `filter_new_contract_workflows()` — 按编号去重 + 合同关键词筛选（排除通知/请款）
5. `WorkflowWriter.prepare()` — 创建流程目录，写 `workflow.json`
6. `OAClient.download_attachments()` — 4 种下载策略依次尝试（页面列表 → iframe → 普通链接 → 兜底图标）
7. `OAClient.save_detail_snapshot()` — 保存 `workflow.html` + `workflow.png`
8. `AuditRunner.run()` — 调用配置的审核后端
9. `StateStore.mark_processed()` — 标记该流程已处理（先写 tmp 再 rename 保证原子性）

### 审核后端（audit_backends.py）

| 后端 | 说明 | 状态 |
|------|------|------|
| `skill_request` | 默认。写入 `audit/audit_request.md`，不拉起 agent | ✅ |
| `direct_llm` | 通过 DeepSeek API 逐维度审核，自动输出 `audit.md` + `audit.json` | ✅ v0.3.0 |
| `claude_cli` | 实验性，通过 `claude -p` 拉起 Claude CLI | 🧪 |

`direct_llm` 后端流程：读取 `workflow.json` + `workflow.html` + 附件内容 → 组装审核 prompt → 调用 LLM → 解析响应（提取"审核发现问题清单"和"审批批注"） → 写 `audit.md` 和 `audit.json`。

### 附件下载策略（oa_client.py）

`download_attachments()` 按顺序尝试 4 种方式，命中即返回：
1. **页面 wea-upload-list 列表** — OA SPA 直接渲染的附件列表，点击下载图标（`.icon-coms-download`）触发浏览器下载事件
2. **iframe 内文件链接** — 找到 `static4form` iframe，点击链接拦截 `window.open` 获取下载 URL
3. **普通附件链接** — 扫描页面所有 `<a>` 标签匹配附件扩展名
4. **兜底下载** — 点击所有 `.icon-coms-download` 图标

下载后执行：魔数校验 → `.doc`→`.docx` 自动转换（LibreOffice 优先，Word COM fallback）。

### 输出目录结构

```
D:\BaiduSyncdisk\claude\contract-approval\<日期>_<流程编号>_<标题>/
  raw/workflow.json        # 流程元数据
  raw/workflow.html        # 详情页 HTML 快照
  raw/workflow.png         # 详情页截图
  attachments/             # 下载的合同附件（自动转换 .doc→.docx）
  audit/audit_request.md   # 审核请求（skill_request 后端）
  audit/audit.md            # AI 审核结论（direct_llm 后端）
  audit/audit.json          # 结构化审核结果（direct_llm 后端）
  audit/audit_status.json  # 审核状态
  log.jsonl                 # 操作日志
```

状态目录：`<output_root>/.state/processed_workflows.json`

## Commands

### 运行轮询

```powershell
# 一次性轮询
$env:PYTHONPATH="D:\BaiduSyncdisk\claude\contract-sentinel\src"
py src/run_contract_polling.py --once

# 持续轮询（默认间隔 300 秒）
$env:PYTHONPATH="D:\BaiduSyncdisk\claude\contract-sentinel\src"
py src/run_contract_polling.py
```

### 登录 OA

推荐手动方式（弹窗浏览器手动输入账号密码）：
```powershell
py src/manual_login.py
```
自动验证码方式（准确率一般）：
```powershell
py src/auto_login.py
```

### 测试

```powershell
pytest tests -v
```

### 单流程手动处理

```powershell
$env:PYTHONPATH="src"
py src/run_workflow.py <流程目录路径>
```

## Configuration

`config.json`（已 gitignore）的完整可配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `oa_url` | OA 系统地址 | `https://oa.grgt.cn/` |
| `approval_output_root` | 流程资料输出根目录 | `D:\...\contract-approval` |
| `poll_interval_seconds` | 轮询间隔（秒） | 300 |
| `contract_keywords` | 匹配合同流程的关键词 | `["付款合同评审","合同评审","付款合同","合同"]` |
| `audit_backend` | 审核后端类型 | `skill_request` |
| `direct_llm_model` | AI 审核模型名 | `deepseek-chat` |
| `deepseek_api_key` | DeepSeek API Key（direct_llm 后端必填） | `""` |
| `deepseek_api_base` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `claude_cli_command` | Claude CLI 命令路径 | `claude` |

## Key Constraints

- **只读 OA**：不点击同意/驳回/提交，不修改 OA 数据
- **不留明文密码**：登录态通过 Cookie 复用；Cookie 过期弹窗引导手动登录
- **不绕过验证码**：遇到验证码停止
- **留痕要求**：每次运行写 `log.jsonl`（时间、流程编号、状态、错误）
- **异常即停**：登录失效、页面结构变化、附件下载失败均停止并报错
- **高风险仅写本地**：审核发现高风险只写 `audit.md`，不回填 OA

## Data directory conventions

- `data/` — 运行时产生的 Cookie、Chrome Profile、截图、日志，已 gitignore
- `.gitignore` 已排除：`config.json`、`data/`、`__pycache__/`、`*.pyc`、`*.pytest_cache/`
- 流程目录写到 `approval_output_root`（默认 `D:\...\contract-approval\`），不在本仓库内
- `src/` 下的实验测试脚本不在单元测试范围内

## Key Dependencies

- **playwright** — 浏览器自动化（OA 页面读取、附件下载）
- **pytest** — 测试框架
- **openpyxl**（可选） — XLSX 附件读取（direct_llm 后端用）
- **python-docx**（可选） — DOCX 附件读取（direct_llm 后端用）
- **pdfplumber**（可选） — PDF 附件读取（direct_llm 后端用）
- **pillow + ddddocr**（可选） — 自动验证码识别

## Exploration Docs

`docs/` 记录了早期 OA 环境摸底、API 接口探索、Playwright 可行性和架构设计决策，供参考。
