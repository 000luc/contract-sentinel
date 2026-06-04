# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Contract Sentinel — OA 合同审批自动轮询工具。定时读取泛微 e-cology OA 待办，按流程编号识别新合同审批流程，下载流程详情和附件到本地，通过可切换的审核后端生成审核结论。

当前状态：**MVP 阶段**，已实现完整的轮询、落盘、审核后端链路，不自动提交或回填 OA。

## Key Architecture

```
src/contract_sentinel/
  settings.py       配置加载（config.json）
  state_store.py    已处理流程去重状态（processed_workflows.json）
  path_utils.py     Windows 安全文件名处理
  workflow_models.py   WorkflowItem / WorkflowMaterial / AttachmentInfo 数据类
  oa_client.py      Playwright OA 页面读取 + 附件下载
  workflow_writer.py   流程目录创建、JSON/HTML/截图/日志落盘
  audit_backends.py    审核后端接口 + SkillRequest/DirectLlm/ClaudeCli 实现
  audit_runner.py      审核后端调用封装
  poller.py            轮询主流程（去重 → 落盘 → 下载 → 审核 → 状态更新）
src/run_contract_polling.py    CLI 入口（--once / 持续轮询）
tests/                         pytest 测试（全部用 Fake/Mock，不需 Playwright）
```

### 轮询流程

1. `OAClient.ensure_login()` — 检查 Cookie 是否有效
2. `OAClient.extract_todo_list()` — 读取待办表格，按流程编号正则提取
3. `filter_new_contract_workflows()` — 按编号去重 + 合同关键词筛选
4. `WorkflowWriter.prepare()` — 创建流程目录，写入 `workflow.json`
5. `OAClient.download_attachments()` — 下载附件 + 按钮触发下载
6. `OAClient.save_detail_snapshot()` — 保存 `workflow.html` + `workflow.png`
7. `AuditRunner.run()` — 调用配置的审核后端
8. `StateStore.mark_processed()` — 标记该流程已处理

### 审核后端

- `skill_request`（默认）：只写入 `audit/audit_request.md`，不拉起 agent
- `direct_llm`：预留，当前只写未启用状态
- `claude_cli`：实验性，通过 `claude -p` 拉起 Claude Code CLI

### 输出目录结构

```
D:\BaiduSyncdisk\claude\contract-approval\<流程编号>_<标题>\
  raw/workflow.json    # 流程元数据
  raw/workflow.html    # 详情页 HTML
  raw/workflow.png     # 详情页截图
  attachments/         # 下载的附件文件
  audit/audit_request.md   # 审核请求（skill_request 后端）
  audit/audit_status.json  # 审核状态
  log.jsonl            # 操作日志
```

状态目录：
```
D:\BaiduSyncdisk\claude\contract-approval\.state\
  processed_workflows.json   # 已处理流程记录
```

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

### 测试

```powershell
pytest tests -v

# 语法检查所有模块
$files = @('src\run_contract_polling.py') + (Get-ChildItem src\contract_sentinel -Filter *.py | ForEach-Object { $_.FullName })
py -m py_compile @files
```

### 登录

OA 有图形验证码，不自动登录。先人工登录后复用 Cookie：
```powershell
py src/auto_login.py
```

### 配置

```powershell
Copy-Item config.example.json config.json
```
然后修改 `config.json`，主要是 `oa_url` 和关键词。

## Key Constraints

- **只读 OA**：不点击同意/驳回/提交，不修改 OA 数据
- **不保存明文密码**：登录态通过 Cookie 复用；Cookie 过期则停止并通知人工
- **不绕过验证码**：遇到验证码停止
- **留痕要求**：每次运行写 `log.jsonl`（时间、流程编号、状态、错误）
- **异常即停**：登录失效、页面结构变化、附件下载失败均停止
- **高风险仅写结论**：审核发现高风险只写本地 `audit.md`，不回填 OA

## Data directory conventions

- `data/` — 运行时产生的 Cookie、Chrome Profile、截图、合同附件
- `.gitignore` 已排除 `config.json`、`data/`、`__pycache__/`、`*.pyc`
- 流程输出到 `D:\BaiduSyncdisk\claude\contract-approval\`（可配置）

## Exploration Docs

`docs/` 目录记录了早期探索阶段的发现（OA 环境摸底、API 接口探索、Playwright 可行性），供参考但不代表当前代码状态。
