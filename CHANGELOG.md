# Changelog

## 0.2.0 - 2026-06-04

- 新增一键启动脚本：`start_polling.bat`（前台窗口）和 `start_polling_hidden.vbs`（后台静默）
- 新增 `src/manual_login.py`：手动登录后保存 Cookie（解决验证码识别不准问题）
- 修复 `auto_login.py` 的项目路径错误
- 更新 `claude.md` 匹配当前 MVP 代码状态
- 更新 README 启动说明

## 0.1.0 - 2026-06-04

- 新增合同审批轮询 MVP。
- 新增流程编号去重和本地状态存储。
- 新增流程资料落盘：`raw`、`attachments`、`audit`、`log.jsonl`。
- 新增 OA 客户端：登录态检查、待办提取、详情快照、附件链接下载、下载按钮处理。
- 新增插件式审核后端：`skill_request`、`direct_llm`、`claude_cli`。
- 新增轮询 CLI：`src/run_contract_polling.py`。
- 新增测试覆盖：路径安全、状态存储、流程落盘、OA 客户端、审核后端、轮询编排。
- 新增安全忽略规则，避免提交配置、Cookie、Chrome Profile、运行日志和合同附件。

