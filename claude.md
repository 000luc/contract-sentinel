# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Contract Sentinel（合同审批自动审核 Agent）是一个探索中的自动化系统，目标为：定期检查办公 OA 中的待办流程，识别合同审批类待办，自动下载合同附件并进行风险审核，最后将审核意见推送到企业微信或微信。

当前处于**探索阶段**，技术路线尚未确定。核心原则：先摸清楚 OA 系统的真实可自动化边界，再决定最终架构。

## Repository Structure

```
Contract Sentinel/
├── docs/              # 探索阶段文档（待创建）
│   ├── 01-oa-environment.md
│   ├── 02-oa-api-discovery.md
│   ├── 03-playwright-feasibility.md
│   ├── 04-attachment-download-feasibility.md
│   ├── 05-contract-review-rules.md
│   ├── 06-notification-feasibility.md
│   ├── 07-architecture-comparison.md
│   └── 08-mvp-plan.md
├── src/               # 探索脚本和 MVP 代码（待创建）
└── data/              # 合同附件、日志、审核报告（运行时生成）
    ├── contracts/
    ├── logs/
    └── reports/
```

## Development Commands

当前项目尚无固定的构建/测试命令。探索阶段以 Python 脚本为主，后续可能引入依赖管理。

运行探索脚本：
```bash
py src/<script>.py
```

环境变量注意（Windows PowerShell）：
```powershell
$env:PYTHONIOENCODING = "utf-8"
```

## Architecture Decisions

### 技术路线未定，按以下优先级探索

1. **接口优先**：优先检查 OA 是否有公开的后端接口（XHR/Fetch）返回待办列表和附件信息
2. **Playwright 兜底**：若接口不可行，评估页面 DOM 是否可被 Playwright 稳定操作
3. **视觉/OCR 最后手段**：仅当页面为 Canvas/图片流/DOM 不可读时考虑

### 各组件角色边界

- **Claude Code**：开发者、调试者、代码生成者、日志分析者。不担任长期无人值守执行器，不直接操作生产 OA。
- **Playwright**：浏览器自动化执行器，负责打开 OA、读取待办、点击详情、下载附件、截图留证。不负责复杂法律判断或自动审批。
- **Hermes Agent**（若引入）：定时任务入口、消息通知入口、多渠道指挥中心。不直接全权控制 OA。
- **GenericAgent**（若引入）：仅作为实验性备选，不作为主生产方案。

### 合同审核规则

审核基于结构化规则清单，不是自由发挥：
- 审核维度：合同主体、金额、付款条款、发票条款、履约期限、违约责任、争议解决、解除条款、保密条款、知识产权、验收条款、担保/保证金、签署页、附件齐全性、金额大小写一致性等
- 风险等级：高/中/低/未发现明显风险，按预定义规则定级，不让模型随意定级
- 输出格式：固定模板（合同名称、流程编号、风险等级、主要风险、建议审核意见、需人工确认事项、无法判断事项）

### 数据目录规范

```
data/contracts/YYYY-MM-DD/OA流程ID_合同名称/
  ├── 原始附件/
  ├── 审核结果/
  └── 日志.json
```

## Security & Compliance Constraints

以下限制为硬约束，不可绕过：

- **只读 OA**：只读取待办和下载附件，不自动提交审批意见，不点击同意/驳回，不修改 OA 数据
- **不保存密码**：禁止保存明文密码或 token；登录态通过浏览器 Profile 或 Cookie 复用
- **不绕过验证码**：遇到验证码停止并通知人工
- **文件隔离**：合同文件、日志、审核结果分目录存放；敏感文件不上传到不可信服务
- **留痕要求**：每次运行必须记录日志（运行时间、OA 账号、待办数量、合同待办数量、流程编号、合同名称、附件名称、下载状态、审核状态、通知状态、错误信息、截图路径）
- **异常即停**：登录失效、页面结构变化、附件下载失败、合同无法读取、审核模型报错、发现高风险合同、附件格式不支持，均停止并通知人工
- **通知脱敏**：合同全文不直接发送到微信，只发送摘要、风险点和审核建议；高风险合同必须标记为人工确认

## Notification Priority

通知方式优先级（由高到低）：
1. 企业微信机器人（推荐，需确认公司是否允许）
2. Server酱 / PushPlus
3. 邮件
4. 个人微信机器人（不推荐，风险较高）

## Exploration Deliverables

探索阶段需要产出的文档和脚本见 `合同审批自动化.md` 第「十一、最终探索输出物」节。

每次完成一个探索方向后，更新对应的 `docs/` 文档，记录发现、判断标准和风险点，不要提前下最终结论。
