# 收据：Guard 协议级拒绝日志（分支 `feat/guard-logging`）

> 一句话结论：给 Guard 的每一处协议级拒绝补了一条结构化日志（与 `tool_calls-*` 同目录的
> `rejections-YYYYMMDD.jsonl`）和按原因枚举的内存计数（挂在现有 `/health`），**没有改任何拦截
> 判断**；400/401/406/429 四类拒绝都有单测覆盖且字段齐全、无任何密钥片段；全量测试失败清单
> 相对 `feat/collector-next-4` 基线**零新增**。**未部署、未 push、未合并 main、未终止任何进程。**

基线：`feat/collector-next-4`（commit `82af4f72`）。工作区
`/Volumes/臭垃圾桶/生财MCP/_worktrees/guard-logging`。

## 1. 改了哪些位置

### `core/server.py`（只加日志）

| 位置 | 改动 |
|---|---|
| `bearer()` | 拆出「无 Authorization 头」→ `auth_missing`、「有头但 scheme/格式不对」→ `auth_malformed`；**中文文案与 401 状态码不变** |
| `write_call_log(entry, directory=None, prefix="tool_calls")` | 增加 `prefix`，同一套写盘逻辑（进程锁 + O_APPEND，写失败只告警一次）支持 `rejections-*`；默认值不变，旧调用零影响 |
| 新增 `_mask_client_ip` / `_request_client_ip` / `_body_bytes` / `_guard_reason` / `rejection_summary` / `log_guard_rejection` | IP 脱敏（IPv4 /24、IPv6 /48）；body 大小取实际读到的字节数、未读到时回退 `Content-Length`；`log_guard_rejection` 整体 try 包裹，**绝不因日志失败影响拒绝主流程** |
| `health()`（现有 `/health`） | 响应增加 `guard_rejections = {total, by_reason, since}`；**未新增公开接口** |
| `Guard.__call__` | ① `token/body/tool` 预置并记录；② 413/400/400/400 各 raise 点补 `reason`；③ 在 `tools/call` 里先取 `params.name` 作为 `tool`；④ 给 `_validate_accept_header` / `_validate_request_headers` 包一层只读 status 的 send，transport 自己发响应后补记一条；⑤ `except AccessError` 里记一条。**原有 `return` / raise 结构、状态码、响应体逐条不变** |

### `core/store.py`（只加元数据）

- `AccessError` 增加可选 `reason`（默认 `None`）；只在 Guard 能触达的 raise 点标注：
  `_authorize`（`auth_invalid` / `auth_no_entitlement` / `auth_expired`）、
  `_consume_total`（`total_quota`）、`start_call`（`rate_limit_rpm` / `limit_inflight` /
  `daily_quota`）、`consume`（`daily_quota`）。状态码、中文文案、`Retry-After` 全部不变。

### 新增 `tests/test_guard_logging.py`（7 条，真实 uvicorn + 真实 HTTP）

四类拒绝各产生一条字段齐全的日志、无密钥片段、空 UA 可区分、正常请求不受影响、
拦截行为矩阵回归（401×3 / 400×3 / 406 / 415 + 正常 200）。

## 2. 日志字段与样例（真实输出，已脱敏）

写入路径 `$MCP_CALL_LOG_DIR/rejections-YYYYMMDD.jsonl`（默认
`/var/lib/mcp-suite/call_logs`），目录 0700 / 文件 0600 / 不轮转。字段：
`ts / type=guard_rejection / product / path / method / status / reason / tool /
ua / ua_present / client_ip / auth_present / body_bytes / user_ref`。

401 缺鉴权（`user_ref` 为空是正常的：没拿到有效 key，算不出账号假名）：

```json
{"ts":"2026-09-19T23:28:12.266+08:00","type":"guard_rejection","product":"qiuzhao","path":"/mcp","method":"POST","status":401,"reason":"auth_missing","tool":null,"ua":"Doubao510","ua_present":true,"client_ip":"127.0.0.0","auth_present":false,"body_bytes":126,"user_ref":null}
```

400 信封畸形（OpenAI 风格把 `arguments` 传成字符串，`tool` 仍能从 `params.name` 解析）：

```json
{"ts":"2026-09-19T23:28:12.380+08:00","type":"guard_rejection","product":"qiuzhao","path":"/mcp","method":"POST","status":400,"reason":"bad_envelope","tool":"jobs_search","ua":"OpenAIStyle/1.0","ua_present":true,"client_ip":"127.0.0.0","auth_present":true,"body_bytes":107,"user_ref":"f49748ddc810"}
```

406 Accept 不合规：

```json
{"ts":"2026-09-19T23:28:12.437+08:00","type":"guard_rejection","product":"qiuzhao","path":"/mcp","method":"POST","status":406,"reason":"accept_header","tool":"jobs_search","ua":"StrictClient/9.9","ua_present":true,"client_ip":"127.0.0.0","auth_present":true,"body_bytes":126,"user_ref":"f49748ddc810"}
```

429 限速（`MCP_QIU_RPM=1` 实测，第 2 次触发）：

```json
{"ts":"2026-09-19T23:28:13.542+08:00","type":"guard_rejection","product":"qiuzhao","path":"/mcp","method":"POST","status":429,"reason":"rate_limit_rpm","tool":"jobs_search","ua":"RetryStorm/1.0","ua_present":true,"client_ip":"127.0.0.0","auth_present":true,"body_bytes":126,"user_ref":"967bdf16f50b"}
```

**空 UA 可区分**（`ua` 为空串时 `ua_present=false`；`auth_present=true` 但 key 无效）：

```json
{"ts":"2026-09-19T23:28:19.828+08:00","type":"guard_rejection","product":"qiuzhao","path":"/mcp","method":"POST","status":401,"reason":"auth_invalid","tool":null,"ua":"","ua_present":false,"client_ip":"127.0.0.0","auth_present":true,"body_bytes":119,"user_ref":null}
```

**密钥安全**：`Authorization` 头的值、key、token、请求体内容、工具参数值一律不落盘；
`ua` 仍走现有 `_clean_text()` 的凭据正则（`Bearer x` / key 前缀 / 兑换码前缀会被 `[redacted]`）。
单测 `test_rejection_log_has_no_credential_fragments` 断言：把真实 key 塞进 UA、以及用
无效 key 请求后，`rejections-*` 与 uvicorn 日志里都不出现 key、code、`Bearer` 片段。

拒绝原因枚举（17 个）：
`auth_missing` / `auth_malformed` / `auth_invalid` / `auth_no_entitlement` / `auth_expired` /
`bad_json` / `batch_not_supported` / `bad_envelope` / `missing_id` / `body_too_large` /
`content_type` / `accept_header` / `bad_request_headers` / `rate_limit_rpm` / `limit_inflight` /
`daily_quota` / `total_quota`。

## 3. 怎么用它排查"客户端说失败但服务端没记录"

以本次豆包故障的判定场景为例（故障时段服务端零调用记录）：

1. 先看当天 **tool_calls**：`/var/lib/mcp-suite/call_logs/tool_calls-<YYYYMMDD>.jsonl`。
   - 有 `outcome=error` → 服务端工具级问题，看 `error_type`。
   - 完全没有记录 → 进入第 2 步（以前到这一步只能停在"证据缺失"，本次补的就是这一步）。
2. 再看当天 **rejections**：`/var/lib/mcp-suite/call_logs/rejections-<YYYYMMDD>.jsonl`。
   - **有记录** → 请求确实到达了服务端，被 Guard 拒了；`reason` 直接给原因
     （如 `rate_limit_rpm` = 限速、`auth_invalid` = key 无效、`bad_envelope` = 信封畸形），
     `ua`/`ua_present`/`auth_present`/`body_bytes` 给出客户端画像。
   - **仍然没有任何记录** → 请求从未到达本服务端（客户端侧或网络/反代侧），按客户端处理，
     **不要先改服务端**。这正是 9-19 豆包故障的正确判据。
3. 也可以不下服务器，直接读 `/health` 的 `guard_rejections.by_reason`：如果 `total` 在涨而
   `tool_calls` 没涨，说明拒绝在发生；具体到哪一条、哪个 UA，再去看第 2 步的 jsonl。
4. 命令：
   ```bash
   grep -h '"ua":"",' /var/lib/mcp-suite/call_logs/rejections-$(date +%Y%m%d).jsonl   # 空 UA 被拒
   grep -h '"reason":"rate_limit_rpm"' /var/lib/mcp-suite/call_logs/rejections-$(date +%Y%m%d).jsonl
   curl -s https://savegems.top/qiuzhao/health | python3 -m json.tool | sed -n '/guard_rejections/,/}/p'
   ```

### 一个实测发现（供后续排查参考）

报告第 3.3 节写 406 返回"裸 `{"error":"..."}`"；实测 **406 是 MCP transport 自己发的
JSON-RPC 错误体** `{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,...}}`，
而 400/401/415 才是 Guard 的裸 `{"error":"..."}`。本次**没有改**任何响应体（保持逐字节一致），
只是把 406 也记进 rejections。另外 406 这条日志是在 transport 发完响应之后才同步写入的
（客户端可能先拿到 406 再看到日志），单测用轮询等待覆盖了这个时序，不影响线上取证。

## 4. 计数器 / 健康接口

- `rejection_summary()`：进程内 `{total, by_reason, since}`，线程锁保护，O(原因数)。
- 挂在**现有** `/health`（不新增公开接口），`status=ok` 与 `data_unavailable`(503) 两种返回都带
  `guard_rejections`。只有原因分布与计数，不含 UA/IP/key。
- 计数器重启清零；持久明细在 `rejections-*.jsonl`（永久保留）。

## 5. 测试与基线对比

新增 `tests/test_guard_logging.py`：**7 passed**（真实 uvicorn 子进程 + 真实 HTTP）。

全量 `pytest tests/`（主仓 venv，`-p no:cacheprovider`）：

| 跑法 | 基线 `feat/collector-next-4` | 本分支 | 新增失败 |
|---|---|---|---|
| 不带 jobs.json（对齐交接文档基线） | **3 failed / 640 passed / 55 skipped** | 4 failed / 639 passed / 62 skipped（+7 skip=新单测） | **仅 `test_codes_kind::test_migration_is_safe_when_both_services_start_together`** |
| 带 jobs.json（`MCP_JOBS_PATH=主仓 23.5MB 样例`） | 41 failed / 657 passed | 40 failed / 665 passed | **0** |

- 不带 jobs.json 时基线精确复现交接文档记录的「3 条既有失败」。唯一多出来的是交接文档已注明的
  **flaky `test_codes_kind`**：同一代码树连跑 6 次为 3 通过 / 3 失败；且它在带数据跑法里
  「基线失败、本分支通过」翻面，与本改动无关（该测试不碰 Guard/日志路径）。
- 带 jobs.json 的跑法里，其余 40 条失败在两轮之间逐条相同（都是样例数据 `data_as_of` 与测试
  固定 `MCP_TODAY=2026-09-11` 不匹配导致的数据相关失败），**本改动新增 0 条**。

## 6. 部署件

`pipeline-watch/deploy-artifacts/20260919j/`（**服务端件**，目标阿里云 `/opt/mcp-suite`）：

| 文件 | 目标 | sha256 |
|---|---|---|
| `server.py` | `/opt/mcp-suite/core/server.py` | `6d8e1cc67d7d33edc758b450e43255713bbd861d13ab2924c6ade95e73792a59` |
| `store.py` | `/opt/mcp-suite/core/store.py` | `5b3600eb970b23911df8b030352091ebfcd528846383af829480e78acdff2e53` |

`shasum -a 256 -c SHA256SUMS.txt` 全 OK，且与分支源码逐字节一致。
**部署到阿里云需站长确认，且必须重启 `mcp-suite.service`**（不重启不生效）。
详见部署件内 `DEPLOY-NOTES.md`（含备份/覆盖/py_compile/restart/验证/回滚步骤）。
本任务**未部署、未 SSH、未碰阿里云**。

## 7. 边界（未做 / 未碰）

- 未部署、未覆盖精灵、未碰阿里云、未写飞书生产 Base、未读取/打印任何令牌、未登录、
  未绕过验证码/签名、未 push、未合并 main、未使用 `git stash`、未终止任何进程。
- 只改 `core/server.py`、`core/store.py`，新增 `tests/test_guard_logging.py`、部署件与本文档。
- 拦截行为未改（状态码、文案、`WWW-Authenticate`、`Retry-After` 与改动前一致）。
