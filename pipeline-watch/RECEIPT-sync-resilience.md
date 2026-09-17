# RECEIPT — 精灵→飞书同步可靠性恢复(sync-resilience)

日期:2026-09-17。目标:今天的 jobs.json 进飞书;网络抖动不再让整个同步失败;失败有人能看见。

## 1. 传输重试(代码)

- 分支 `feat/sync-resilience`(worktree `../mcp-suite-sync`,基于 main HEAD `9533ff0`,已含续表2 登记 `3112763`)。
- 改动 `qiuzhao/collector/sync_lark_multivalue.py` 的 `cli()`:
  - lark-cli 非 ok 且 `error.type == "network"`(stdout ok:false 或 stderr JSON 两种通道都解析),或 `subprocess.TimeoutExpired` → 最多重试 3 次,退避 5/15/45 秒,每次重试 `print` 一行 JSON(`cli_retry`/`delay_seconds`/`command`/`error_subtype`/`error_message`)。
  - 非网络错误不重试,直接 `RuntimeError`,错误体 JSON 进消息(原来只有固定文案,丢错误细节;`800010401`/`only one option` 的 schema_pending 重试判定不受影响,已验证)。
  - CAS/一致性断言(`assert_current_values`、"写前再读、值变即失败"、backup 完整性)未动。
- commit `33d7e04`,主仓 `git merge --no-ff` → `770c281`,未 push。

## 2. 监控去误报(服务器)

- `deploy/freshness_watch.sh`:`/health` 读取改为最多 3 次、间隔 10 秒;三次都失败记 `status: "unreachable"`(与 `stale` 区分),并从上一份 freshness.json 带出 `last_known_data_as_of`。
- 部署:旧文件备份 `/opt/mcp-suite/deploy/freshness_watch.sh.bak-20260917`,新文件属主 mcp-suite:mcp-suite、755;`su mcp-suite` 手动跑一次 → `freshness.json` 恢复 `ok`(data_as_of 2026-09-17T06:43:09+08:00,91403 条,jobs_sha256 `fdb3735d…`)。未重启 mcp-suite.service,未跑 deploy.sh。

## 3. 同步可见性(Mac 侧)

- `deploy/freshness_notify_mac.sh` 增加第二段:SSH 读精灵 `C:\mcp-suite-collector\data\lark-sync\status.json`(192.168.31.204,HostKeyAlias 192.168.1.52);精灵不可达时跳过并写 stderr 日志(launchd 落 `~/Library/Logs/mcp-suite/qiuzhao-freshness.stderr.log`);`status==failed` 或 `status!=success 且距 last_success_at >30h` 时向留言板发一句话(`【kimi→max】` 开头),正常不发。

## 4. 测试

- 新增 3 个用例于 `tests/test_sync_lark_multivalue.py`:network 错误第 1 次失败第 2 次成功(断言 sleep==[5]、重试日志一行);非网络错误(800010401)不重试直接抛;stderr 通道 network JSON + subprocess 超时混合重试,4 次调用后抛、sleep==[5,15,45]。
- `pytest -q tests/test_sync_lark_multivalue.py tests/test_lark_sync_index.py tests/test_incremental_lifecycle.py` → **35 passed**(worktree 内运行,后两个测试文件为主仓未跟踪文件,仅拷贝运行未提交)。

## 5. 部署到精灵(拷贝部署,无 git)

比对 sha256 后决定:

| 文件 | 精灵原 sha256 | main sha256 | 动作 |
|---|---|---|---|
| sync_lark_multivalue.py | `8e98febd…`(= 续表2 登记前的版本) | `5c77cde8…` | 已备份 `.bak-20260917` 并替换 |
| lark_sync_daemon.py | `f34b9d90…`(仅差 error/finished_at 残留清理) | `6a52a641…` | 已备份 `.bak-20260917` 并替换 |
| lark_sync_enrichment.py | `0558ced2…` | `0558ced2…` | 一致,不动 |
| lark_sync_index.py | **不存在**(精灵版 windows_collector.py 不引用它) | `a5de4e6e…` | 不复制(远端管线未使用) |

- scp/sftp 均被服务端拒绝(Connection closed),改用 base64 → powershell `[IO.File]::WriteAllBytes` 通道(先探针校验 sha256 一致)。
- 复制后 certutil 校验:`sync_lark_multivalue.py=5c77cde8…`、`lark_sync_daemon.py=6a52a641…`,与本地逐字节一致;`.venv\Scripts\python.exe -X utf8 -m py_compile` 两文件通过。
- 未动 `data\`、`runs\`、`keys\`、`.venv`、计划任务。

## 6. 补跑今天(9-17)同步

- 触发方式与精灵 `windows_collector.py:180` 的 sync 阶段一致(cwd=`C:\mcp-suite-collector`,env `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`,`-X utf8`):
  `python -m qiuzhao.collector.lark_sync_daemon --source-path C:\mcp-suite-collector\data\jobs.json --state-dir C:\mcp-suite-collector\data\lark-sync --runs-dir C:\mcp-suite-collector\data\lark-sync\runs --apply`,输出落 `runs\20260917\sync-rerun.log`。
- 补跑前状态:status.json `failed`,phase=business,error=`network/transport … records/batch_update … EOF`(tblX7rOpjWaRArng);jobs.json sha256=`fdb3735d…`。
- 过程观察(13:46 启动,run_dir `data\lark-sync\runs\20260917T134605188879`):
  - snapshot 完成 8 表备份,续表2(tblZOCFHBraQThw9)备份 0 条;plan 显示互联网科技岗主表 272 条 unmatched(与已知一致),各表 select 字段无 record_updates。
  - **重试机制实战生效**:business 阶段至少 4 次 `network/transport` EOF(tbl0xkmJUMmLqZ1W batch_update/batch_get、tbl0gDcxEaIOYERw、tblcrBAi0ld7uej8 batch_update),均第一次重试(5s)即恢复,同步未中断。
  - 45 分钟时本地 ssh 监视通道超时断开,远端 python 进程存活继续跑(Windows OpenSSH 未杀进程树,status.json 持续 running/business)。

### 补跑结果

（本节由 `TASK-url-delta-fix.md` 任务在 2026-09-17 补全,均为只读查证,未新触发同步。）

- **business 阶段**:已完成。`runs\20260917T134605188879\business-sync.json` = `{"changed": 92722, "conflicting_ids": [], "finished": true}`。事后查明这 92722 条里绝大多数是 `原链接`/`投递入口` 的 markdown-vs-纯url 比较口径 bug 导致的假阳性(见 `RECEIPT-url-delta-fix.md`),补跑本身按当时代码正确执行、成功写入,口径 bug 已在后续任务修复。
- **append 阶段**:已完成,已写入互联网科技岗·续表2(`tblZOCFHBraQThw9`)。`sync-rerun.log` 显示 13 个批次连续无重试地成功,`total_created` 从 50 累加到 **597**,与 `append-status.json` 的 `finished: true`(`capacity_blocked` 为空)一致。续表2 当前 597 行;续表1(`tblu0nsYjntEOCGY`)19993 行不变。
- **note/status 阶段**:已完成。`note_sync` 对 8 张表逐一 `matched`(如 `tblX7rOpjWaRArng` 19430、`tblu0nsYjntEOCGY` 19993 等);`source-status-sync.json` = `{"changed": 0, "human_values_preserved": [], "conflicting_ids": [], "finished": true}`。
- **deduplicate 阶段**:**截至 2026-09-17 21:48 CST(13:48:40Z)仍在 running**,尚未结束,不编造终态。观察到的中间进度:已生成 650+ 个重复分组、删除记录数从任务开始时查证的 853 条持续涨到 **1049 条**(过程中多次复核均在增长,说明进程存活、非卡死);`duplicate-reconciliation.json`(dedup 收尾时写入的汇总)尚未出现。已用只读证据核实这批重复**不是**今天 `+record-batch-create` 盲重试造成(详见 `RECEIPT-url-delta-fix.md` 第 C 节),不需要为此打断或重跑。
- **`status.json` 终态**:截至 2026-09-17 21:48 CST 仍为
  ```json
  {"status": "running", "last_attempt_at": "2026-09-17T05:46:02+00:00",
   "source": "C:\\mcp-suite-collector\\data\\jobs.json",
   "observed_source_sha256": "fdb3735d8b5709e8235a6b54aa72bd3700a74c0a0d1d32467389317cc31865d0",
   "run_dir": "C:\\mcp-suite-collector\\data\\lark-sync\\runs\\20260917T134605188879",
   "phase": "deduplicate", "error": null, "finished_at": null}
  ```
  dedup 结束后的真正终态(`finished_at`、`duplicate-reconciliation.json` 最终数字)留给 9-18 早间验证时一并核对,不在本收据补齐。
