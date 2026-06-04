# Contract Sentinel

Contract Sentinel 是一个本地 OA 合同审批轮询工具。它定时读取 OA 待办，按流程编号识别新的合同审批流程，下载流程详情和附件到本地目录，并通过可切换的审核后端生成审核请求或审核结论。

## 功能

- 按 OA 流程编号去重，避免重复处理同一流程。
- 每个流程单独落盘到 `D:\BaiduSyncdisk\claude\contract-approval\`。
- 保存流程原始 JSON、页面 HTML、页面截图和附件。
- 默认使用 `skill_request` 后端生成 `contract-approval-auditing` 审核请求。
- 预留 `direct_llm` 和 `claude_cli` 审核后端。
- 只读取 OA 和下载附件，不自动提交、同意或驳回审批。

## 目录结构

```text
src/contract_sentinel/
  audit_backends.py      审核后端接口和实现
  audit_runner.py        审核后端调用封装
  oa_client.py           OA 页面读取和附件下载
  poller.py              轮询主流程
  settings.py            配置读取
  state_store.py         本地处理状态
  workflow_writer.py     流程资料落盘
src/run_contract_polling.py
tests/
```

流程资料输出目录：

```text
D:\BaiduSyncdisk\claude\contract-approval\<流程编号>_<标题>\
  raw\workflow.json
  raw\workflow.html
  raw\workflow.png
  attachments\
  audit\audit_request.md
  audit\audit_status.json
  log.jsonl
```

## 安装

```powershell
py -m pip install pytest playwright
py -m playwright install chromium
```

如果需要自动登录验证码识别，旧探索脚本还依赖 `Pillow` 和 `ddddocr`：

```powershell
py -m pip install pillow ddddocr
```

## 配置

复制示例配置：

```powershell
Copy-Item config.example.json config.json
```

`config.json` 包含本机账号、Cookie 路径和运行偏好，已被 `.gitignore` 忽略，不要提交。

主要配置：

```json
{
  "oa_url": "https://oa.grgt.cn/",
  "approval_output_root": "D:\\BaiduSyncdisk\\claude\\contract-approval",
  "poll_interval_seconds": 300,
  "contract_keywords": ["付款合同评审", "合同评审", "付款合同", "合同"],
  "audit_backend": "skill_request",
  "direct_llm_model": "deepseek-chat",
  "claude_cli_command": "claude"
}
```

## 运行

先准备 OA 登录 Cookie。现阶段可以沿用探索脚本：

```powershell
py src/auto_login.py
```

运行一次轮询：

```powershell
$env:PYTHONPATH="D:\BaiduSyncdisk\claude\contract-sentinel\src"
py src/run_contract_polling.py --once
```

持续轮询：

```powershell
$env:PYTHONPATH="D:\BaiduSyncdisk\claude\contract-sentinel\src"
py src/run_contract_polling.py
```

## 审核后端

- `skill_request`：默认后端。生成 `audit/audit_request.md`，由 Codex 使用 `contract-approval-auditing` 规则复核。
- `direct_llm`：预留后端。当前只写入未启用状态，不直接调用模型 API。
- `claude_cli`：实验后端。通过 `claude -p` 拉起 Claude Code CLI，必须先做本机端到端兼容测试。

## 测试

```powershell
pytest tests -v
$files = @('src\run_contract_polling.py') + (Get-ChildItem src\contract_sentinel -Filter *.py | ForEach-Object { $_.FullName })
py -m py_compile @files
```

## 安全边界

- 不自动点击 OA 的同意、驳回、提交。
- 不绕过短信、扫码或强验证码。
- 不提交 `config.json`、Cookie、Chrome Profile、日志、合同附件或审核产物。
- 审核发现高风险时只写本地结论，不自动回填 OA。

