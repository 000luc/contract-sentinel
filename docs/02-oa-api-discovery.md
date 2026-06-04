# 阶段 2：OA 待办数据获取方式探索 —— 接口方式

## 2.1 探索目标

检查泛微 e-cology OA 是否有后端接口可以直接返回待办列表数据。

## 2.2 已发现信息

- OA 系统：泛微 e-cology 新一代协同融合平台
- 外网地址：https://oa.grgt.cn/
- 内网地址：http://172.18.0.17:8088/
- 登录后页面：`/wui/index.html#/main/...`

## 2.3 泛微常见接口（待验证）

泛微 e-cology 常见后端接口路径：

```
/api/hrm/login/getLoginInfo          # 获取登录信息
/api/workflow/reqlist/getUserRequest   # 获取待办列表
/api/workflow/request/getCreateRequest # 获取可创建流程
/api/workflow/request/getRequestBase   # 获取流程详情
/api/workflow/request/getRequestDetail # 获取流程详细信息
/api/workflow/request/getRequestLog    # 获取流程审批记录
/api/doc/interface/getDocList          # 获取文档列表
/api/doc/interface/getDocDetail        # 获取文档详情
```

## 2.4 探索步骤

1. 用浏览器登录 OA
2. 按 F12 打开开发者工具 → Network 面板
3. 刷新待办事宜页面
4. 筛选 XHR / Fetch 请求
5. 查找包含以下关键词的请求：
   - todo / task / workflow / process / pending / approve
   - 待办 / 流程 / 审批 / 请求
6. 记录：请求 URL、方法、参数、响应格式

## 2.5 记录模板

| 发现时间 | 接口 URL | 请求方法 | 请求参数 | 响应格式 | 是否包含待办列表 | 备注 |
|---------|---------|---------|---------|---------|---------------|------|
| | | | | | | |

## 2.6 判断标准

- [ ] 接口返回 JSON 且包含待办列表 → **优先走接口路线**
- [ ] 接口加密严重或签名复杂 → **暂缓接口路线**
- [ ] 接口返回 HTML 片段 → **仍可解析，但稳定性中等**
- [ ] 完全看不到有效接口 → **转 Playwright 页面路线**

## 2.7 探索结果

（待填写）
