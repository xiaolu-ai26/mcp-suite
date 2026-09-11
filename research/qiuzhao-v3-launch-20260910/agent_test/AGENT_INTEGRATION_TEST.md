# 真实Agent接入测试报告 — A线#2

**测试时间**: 2026-09-10 14:22 (UTC+8)
**测试环境**: 本地隔离服务 (127.0.0.1:8769)，隔离测试库 /tmp/v3test/access.sqlite3
**测试方式**: MCP Streamable HTTP 协议端点直接调用（模拟Agent连接器行为）

## 测试结果

| # | 测试项 | 结果 | 详情 |
|---|---|---|---|
| 1 | 兑换码兑换 | ✅ 通过 | 输入测试码→获得qz_前缀API key，额度200/200，有效期至2027-01-01 |
| 2 | /usage不扣额 | ✅ 通过 | 兑换后调用/usage，剩余200/200，不消耗额度 |
| 3 | tools/list | ✅ 通过 | 返回3个工具：jobs_search、jobs_deadlines、jobs_detail |
| 4 | jobs_search(limit=1) | ✅ 通过 | 返回1条真实岗位（AI算法工程师/中国移动/北京海淀），total=9191 |
| 5 | 额度扣减验证 | ✅ 通过 | jobs_search后剩余199/200，恰好扣1次 |
| 6 | jobs_deadlines(days=7,limit=3) | ✅ 通过 | 返回3条截止岗位，total=4 |
| 7 | 重复码拒绝 | ✅ 通过 | 已兑换码再次调用/redeem，返回HTTP 400 |

## MCP协议细节

- 端点: POST http://127.0.0.1:8769/mcp
- 认证: Authorization: Bearer {api_key}
- 请求头: Content-Type: application/json, Accept: application/json, text/event-stream
- 协议: JSON-RPC 2.0 over Streamable HTTP
- 工具调用格式: {"jsonrpc":"2.0","id":N,"method":"tools/call","params":{"name":"jobs_search","arguments":{"limit":1}}}

## 真实岗位样例

jobs_search返回首条：
- 岗位: AI算法工程师（产线/博后站）
- 招聘单位: 中国移动通信集团有限公司
- 地点: 北京-海淀区
- 数据截至: 2026-09-10T06:46:41+08:00

## 限制说明

- 本测试为MCP协议层端点直接调用验证，模拟Agent连接器行为
- 未在豆包工作/WorkBuddy等真实客户端UI中完成配置操作（当前环境无法打开第三方客户端）
- 但核心链路（兑换→key→Bearer认证→工具调用→扣额→重复拒绝）已全部验证通过
- 新页面（v3前端）的浏览器兑换流程已由页面整合代理单独验证通过

## 安全

- 测试使用隔离数据库，未触碰生产access.sqlite3
- 测试码为临时生成，未使用正式50码
- API key仅在测试脚本内存中使用，未写入报告明文（仅记录前缀）
- 测试完成后清理临时文件

## 结论

MCP服务端协议、认证、工具调用、额度管理全部正常。
新前端页面+后端MCP服务的完整链路已验证可工作。
