# 20260919j —— Guard 协议级拒绝日志（服务端件；不部署，等站长确认）

本部署件只给服务端**加结构化日志**，不改任何拦截判断。目标是阿里云 MCP 服务
`/opt/mcp-suite`（uvicorn `core.server:app`）。
**部署到阿里云需要站长确认，且必须重启 `mcp-suite.service`**（改的是进程加载的代码，
不重启不生效）。本任务未部署、未连服务器。

## 1. 文件与目标路径

| 部署件文件 | 目标路径 | 方式 | 说明 |
|---|---|---|---|
| `server.py` | `/opt/mcp-suite/core/server.py` | 覆盖 | Guard 拒绝日志、计数器、`/health` 暴露 |
| `store.py` | `/opt/mcp-suite/core/store.py` | 覆盖 | `AccessError` 增加只读 `reason` 元数据 |

`SHA256SUMS.txt` 是这两个文件的 sha256；在部署件目录里 `shasum -a 256 -c SHA256SUMS.txt`
应输出 `server.py: OK` / `store.py: OK`。

- `server.py` sha256 `6d8e1cc67d7d33edc758b450e43255713bbd861d13ab2924c6ade95e73792a59`
- `store.py`  sha256 `5b3600eb970b23911df8b030352091ebfcd528846383af829480e78acdff2e53`

## 2. 改了什么（只有日志，没有行为变化）

`core/server.py`：

- 新增 `rejections-YYYYMMDD.jsonl`：与 `tool_calls-*.jsonl` **同一个日志目录**
  （`$MCP_CALL_LOG_DIR`，默认 `/var/lib/mcp-suite/call_logs`），目录 0700、文件 0600、
  不轮转（和 tool_calls 一样永久保留）。写入函数复用 `write_call_log()`（同进程锁 + O_APPEND，
  写失败只告警一次，绝不影响主流程）。
- 每条拒绝字段：`ts / type=guard_rejection / product / path / method / status / reason /
  tool / ua / ua_present / client_ip / auth_present / body_bytes / user_ref`。
  - 空 UA 能区分：`ua=""` 且 `ua_present=false`（豆包这类无 UA 客户端的特征桶）。
  - `client_ip` 只保留网络段：IPv4 /24（如 `114.215.188.0`）、IPv6 /48。
  - `auth_present` 只记 Authorization 头的**有无**；**绝不记 header 值、key/token、
    请求体内容或工具参数值**。UA 仍走现有 `_clean_text()` 凭据正则脱敏。
- `/health` 增加 `guard_rejections = {total, by_reason, since}`：进程内按原因枚举计数，
  重启清零（明细在 jsonl 里）。**没有新增任何公开接口**；计数只有原因分布，不含 UA/IP/key。
- Guard 里对 `_validate_accept_header` / `_validate_request_headers` 这两条 transport
  自己发响应的分支，包一层只记录 status 的 send，再原样转交——响应逐字节不变。

`core/store.py`：

- `AccessError(message, status, retry_after, reason=None)` 增加可选 `reason`；
  只在鉴权/限速/额度各 raise 点标上枚举，**状态码、中文文案、`Retry-After` 全部不变**。

拦截行为未改：状态码、错误文案、`WWW-Authenticate: Bearer`、`Retry-After` 与改动前一致
（`tests/test_guard_logging.py::test_interception_matrix_unchanged` 锁死）。

## 3. 拒绝原因枚举（`reason`）

`auth_missing` / `auth_malformed` / `auth_invalid` / `auth_no_entitlement` / `auth_expired` /
`bad_json` / `batch_not_supported` / `bad_envelope` / `missing_id` / `body_too_large` /
`content_type` / `accept_header` / `bad_request_headers` /
`rate_limit_rpm` / `limit_inflight` / `daily_quota` / `total_quota`。

## 4. 部署步骤（需站长确认）

1. 备份现役两文件（`cp -a core/server.py core/store.py` 到带时间戳目录）。
2. 用本目录两份文件覆盖 `/opt/mcp-suite/core/server.py`、`/opt/mcp-suite/core/store.py`，
   覆盖后 `shasum -a 256 -c` 与 `SHA256SUMS.txt` 对齐。
3. `python -m py_compile core/server.py core/store.py` + import 检查。
4. `systemctl restart mcp-suite.service`（**必须**）。
5. 验证：`curl -s https://savegems.top/qiuzhao/health | python3 -m json.tool` 应能看到
   `guard_rejections`；再故意发一个不带 key 的 `POST /mcp`，`/var/lib/mcp-suite/call_logs/`
   应出现 `rejections-<当天>.jsonl`，且里面**没有**任何 key 片段。
6. 回滚：还原备份两文件，再次 restart。

## 5. 依赖与配置

无新增依赖、无新增环境变量。日志目录沿用 `MCP_CALL_LOG_DIR`；计数器仅内存。日志量很小：
只有被拒请求才写一行（正常调用不写这个文件）。
