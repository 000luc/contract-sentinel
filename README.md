# Contract Sentinel

合同审批流程自动轮询与审核工具。

## 这个项目解决什么问题？

财务/法务人员每天需要在 OA 系统中手动检查有没有新的合同审批流到自己的待办，然后逐条点开、下载合同附件、审核条款、写审核意见。

Contract Sentinel 把这个过程自动化了：**定时自动检查 OA 待办 → 识别合同类流程 → 下载合同附件和页面截图 → 调用 AI 生成审核结论**。审核意见直接写到流程文件夹里，你只需打开确认即可。

## 工作流程

```
定时轮询（每5分钟）
    │
    ├─ 1. 检查 OA 登录是否有效
    │     └─ 无效 → 停止本轮，提示重新登录
    │
    ├─ 2. 读取待办列表
    │
    ├─ 3. 筛选合同类流程（按关键词匹配标题）
    │
    ├─ 4. 去重（按流程编号，已处理的不再处理）
    │
    └─ 对每个新流程：
          ├─ 创建流程目录
          ├─ 保存流程元数据（workflow.json）
          ├─ 进入详情页，保存页面 HTML 和截图
          ├─ 下载所有附件（Word/PDF/Excel…）
          ├─ 生成审核请求或调用 AI 审核
          └─ 写入审核结论（audit/audit.md + audit/audit.json）
```

整个过程**只读不写**：只查看和下载，不点击同意、驳回、提交，不修改 OA 数据。审核结论由 AI 分析后写入本地，不会自动回填 OA。

## 目录结构

```
contract-sentinel/
├── start_polling.bat               # 一键启动（前台窗口）
├── start_polling_hidden.vbs        # 一键启动（后台静默）
├── config.example.json             # 配置模板
├── config.json                     # 实际配置（已 .gitignore，不提交）
├── README.md
├── CHANGELOG.md
├── claude.md                       # Claude Code 项目指引
│
├── src/                            # 源码
│   ├── run_contract_polling.py     # 命令行入口
│   ├── manual_login.py             # 手动登录获取 Cookie
│   ├── auto_login.py               # 自动识别验证码登录（准确率一般）
│   │
│   └── contract_sentinel/          # 核心模块
│       ├── settings.py             # 读取 config.json 配置
│       ├── workflow_models.py      # 流程/附件/资料的数据结构
│       ├── path_utils.py           # Windows 安全文件名处理
│       ├── state_store.py          # 已处理流程去重
│       ├── oa_client.py            # OA 页面读取、附件下载（Playwright）
│       ├── workflow_writer.py      # 流程目录创建、文件落盘
│       ├── audit_backends.py       # 审核后端接口与实现
│       ├── audit_runner.py         # 审核后端调用封装
│       └── poller.py               # 轮询主流程
│
├── tests/                          # 单元测试
│   ├── test_poller.py
│   ├── test_oa_client.py
│   ├── test_audit_backends.py
│   ├── test_path_utils.py
│   ├── test_state_store.py
│   └── test_workflow_writer.py
│
└── data/                           # 运行时数据（已 gitignore）
    ├── oa_cookies.json             # OA 登录 Cookie
    ├── chrome_temp_profile/        # 浏览器临时配置
    └── logs/                       # 登录截图等
```

每个被处理的流程输出到外部目录（可在 config.json 中配置）：

```
D:\BaiduSyncdisk\claude\contract-approval\
├── <流程编号>_<标题>/
│   ├── raw/
│   │   ├── workflow.json       # 流程元数据
│   │   ├── workflow.html       # 详情页 HTML
│   │   └── workflow.png        # 详情页截图
│   ├── attachments/            # 下载的合同附件
│   ├── audit/
│   │   ├── audit_request.md    # 审核请求
│   │   ├── audit.md             # AI 审核结论
│   │   ├── audit.json           # 结构化审核结果
│   │   └── audit_status.json   # 审核状态
│   └── log.jsonl               # 操作日志
│
└── .state/
    └── processed_workflows.json  # 已处理流程记录
```

## 前置条件

- Windows 10/11
- Python 3.12+
- Chrome 或 Edge 浏览器

## 安装

### 1. 安装 Python 依赖

```powershell
py -m pip install pytest playwright
```

（如果要用自动验证码登录还需要 `ddddocr`：`py -m pip install pillow ddddocr`）

### 2. 配置

```powershell
Copy-Item config.example.json config.json
```

修改 `config.json` 中的配置项（大部分已有默认值，可直接使用）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `oa_url` | OA 系统地址 | `https://oa.grgt.cn/` |
| `contract_keywords` | 匹配合同流程的关键词 | `["付款合同评审", "合同评审"]` |
| `poll_interval_seconds` | 轮询间隔（秒） | `300`（5分钟） |
| `audit_backend` | 审核后端类型（skill_request / direct_llm / claude_cli） | `skill_request`|`audit_backend` | 审核后端类型（skill_request / direct_llm / claude_cli） | `skill_request`|`audit_backend` | 审核后端类型（skill_request / direct_llm / claude_cli） | `skill_request` |
| `approval_output_root` | 流程资料输出根目录 | `D:\...\contract-approval` |

| `direct_llm_model` | AI 审核模型名 | `deepseek-v4-flash` |`n| `deepseek_api_key` | DeepSeek API Key（使用 direct_llm 后端时必填） | `""` |`n| `deepseek_api_base` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |`n`n注意：`config.json` 包含敏感信息，已被 `.gitignore` 排除，不要提交到 Git。

## 使用

### 第一步：获取 OA 登录态

OA 登录页有图片验证码，首次运行前需要先保存一次登录 Cookie。推荐手动方式：

```powershell
py src\manual_login.py
```

会弹出一个浏览器窗口，你手动输入账号密码登录 OA，登录后回到命令行按 Enter，Cookie 会自动保存到 `data/oa_cookies.json`。Cookie 有效期约 1-2 小时，过期后重新执行此步骤。

### 第二步：启动轮询

**前台运行（可以看到日志输出）：**
双击 `start_polling.bat`

**后台静默运行（无窗口，不干扰工作）：**
双击 `start_polling_hidden.vbs`

或者用命令行：

```powershell
# 一次性检查
$env:PYTHONPATH="src"
py src\run_contract_polling.py --once

# 持续轮询
$env:PYTHONPATH="src"
py src\run_contract_polling.py
```

### 如何停止

- 前台窗口：直接关掉命令行窗口
- 后台静默：打开任务管理器（Ctrl+Shift+Esc），结束 `python.exe` 进程

### 注意事项

- **Cookie 过期**：OA 登录态约 1-2 小时过期，过期后轮询会报 `OA login failed`，需要重新执行 `py src\manual_login.py`
- **只读模式**：脚本只查看和下载，不会自动审批或提交意见
- **首次运行**：如果当前 OA 待办中没有匹配关键词的流程，会输出 `processed=0`，这是正常结果

## 审核后端

系统预留了三种审核方式，可在 `config.json` 中切换 `audit_backend` | 审核后端类型（skill_request / direct_llm / claude_cli） | `skill_request`字段：

| 后端 | 说明 | 状态 |
|------|------|------|
|`audit_backend` | 审核后端类型（skill_request / direct_llm / claude_cli） | `skill_request` | 默认。自动生成 `audit/audit_request.md`，再由人工或 AI 按规则审核 | ✅ 可用 |
| `direct_llm` | 调用 DeepSeek API 读取流程附件，自动生成 audit.md 和 audit.json 审核结论 | ✅ 可用|`direct_llm` | 调用 DeepSeek API 读取流程附件，自动生成 audit.md 和 audit.json 审核结论 | ✅ 可用|`direct_llm` | 调用 DeepSeek API 读取流程附件，自动生成 audit.md 和 audit.json 审核结论 | ✅ 可用 |
| `claude_cli` | 实验性，通过 Claude Code CLI 执行审核 | 🧪 实验 |

## 测试

```powershell
pytest tests -v
```

51 个单元测试覆盖了路径处理、状态存储、OA 客户端、审核后端、轮询编排等核心逻辑，全部使用 Fake/Mock，不依赖真实 OA 或浏览器，可放心运行。

## 安全边界

- **不自动提交 OA**：不点击同意、驳回、提交，不修改 OA 数据
- **不绕过验证码**：验证码识别失败则停止，不尝试暴力破解
- **不保存明文密码**：通过 Cookie 复用登录态
- **敏感文件不提交**：`config.json`、Cookie、Chrome Profile、日志、合同附件和审核产物全部在 `.gitignore` 中排除
- **异常即停**：登录失效、附件下载失败、页面结构变化均会停止并报错
- **高风险仅写本地**：审核发现风险只写入本地文件，不回填 OA 系统
