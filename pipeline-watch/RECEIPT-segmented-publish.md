# 收据 · 分段发布 + 去掉时长上限 + 并发 16（20260920f）

任务：把「全跑完才推送服务器」的采集链改成分段发布；去掉 p1 全局时长上限（保留总预算兜底）；
并发提到 16；给 P0 根因补第二道防线；精灵临时目录实测（不写正式目录、不推真实服务器）。

分支 `feat/segmented-publish`，worktree `/Users/maxzhl/Projects/mcp-suite-seg`
（起点 `fix/p0-typeerror-20260920` 37ac85f2，已含 `feat/collector-next-6` f0694da7 与
`feat/gap-report` 3468074a）。

结论：**代码 + 单测 + 精灵临时目录实测全部通过；未部署、未 push、未合并 main**。
改动只有 1 个运行时文件（`deploy/windows_collector.py`）+ 2 个测试文件 + 部署件与收据。

---

## 1. 改了什么

| 文件 | 改动 |
|---|---|
| `deploy/windows_collector.py` | ①`step()` 的 `stop_tree(child)` 包成 `record_cleanup()`，清理失败只记 `state['cleanup_errors']`（含完整 traceback）并**照常返回 124**；②p1 从「跑一次」改成**分段循环**：每段 `--resume-latest` + 短 `--max-run-seconds`，段尾 normalize + `preserve()` + `publish_with_rebase()`；③去掉 18000s 全局上限，加 `P1_TOTAL_BUDGET_SECONDS=72000` 段边界兜底；④`--workers 8→16`、`--platform-workers 3→4`；⑤拿不到 `windows-runner.lock` 时仍是 75，但新增 `runner_skipped_alert()`（`data/runner-skipped.jsonl` + 有 `qiuzhao/notify.py` 时自动走飞书）；⑥收据新增 `p1_segments`/`p1_concurrency`/`p1_finished`/`p1_pending`/`p1_stopped`/`p1_budget`/`cleanup_errors` |
| `tests/test_segmented_publish.py` | 新增 18 条单测（下方第 4 节） |
| `tests/test_collector_partial_keep.py`、`tests/test_collector_next_integration.py` | 跟改：假 `step()` 兼容新签名；watchdog/并发断言改成 6600 / 16 / 4 |
| `pipeline-watch/deploy-artifacts/20260920f/` | 累积部署件（21 运行时文件 + SHA256SUMS + PROD-BACKUP-MANIFEST + DEPLOY-NOTES） |
| `pipeline-watch/segtest-jingling.py` | 精灵实测驱动（只写临时目录、只读正式目录） |

**没有**改 `qiuzhao/collector/p1_pipeline.py`：p1 的 `--resume-latest`、checkpoint、`pending`、
0/2/1 退出码契约、`publish()`（本地 staging 逐单元发布 + `_publish_thread_lock` + 文件锁 + CAS +
一次性备份）一个字节都没动。`deploy/windows_rebase.py`、`preserve()`、`publish_snapshot()` 也没动。

## 2. 分段设计：为什么这样最稳

```
段 N:  p1 --max-run-seconds 5400 --resume-latest --workers 16 --platform-workers 4
       → normalize
       → preserve() + publish_with_rebase()      ← 这一段的成果落袋
       → 读 <stage>/p1-status.json: run_finished==True 且 pending 为空 → 跳出
       否则段 N+1
```

* **复用而不是新造**：p1 撞到自己的 deadline 本来就是优雅语义（停止派发、等在跑单元收尾、
  写 `pending`、返回 2）。分段循环只用现成机制，没有一行新的发布逻辑。
* **损失窗口 = 一段**（90 分钟）。9-20 那种「跑 5 小时、崩在推送前、全部作废」不可能再来。
* **每段都判重**：`same_publication`（staging 字节 + 已发布文件 sha256 都对得上）就不重复
  上传那 358MB，收据记 `"action": "unchanged"`。
* **整个运行中断后 `--resume-run` 重入**：checkpoint 已 `run_finished` 时**不重跑任何段**
  （不会新开 `p1-runs\<新时间戳>`）、不重复推送；整轮 `finished` 的收据直接返回。
* **退出码契约**（写进收据 `p1_segments[*].attempts/exit`）：
  * `0/2` 该段成功 → 照常推送（2 = 部分成功，绝不当失败）；
  * `1` 按 2026-09-18 契约**回滚该段 + `reset_p1`**，**重试一次**，再失败停在段边界；
  * `124`（父看门狗）**不回滚、不 reset**：p1 的逐单元发布是原子替换 + CAS，硬杀不会写坏
    staging，回滚等于白采这一段；记 `result="kept"`，停在段边界，checkpoint 留给下次；
  * `normalize` 失败 / `p1-status.json` 读不到 / `pending` 连续 2 段不下降 / 总预算到 →
    都在段边界停下并记 `p1_stopped.reason`（不硬杀、不带病继续）。

### 2.1 段长 / 限时 / 预算取值理由

| 常量 | 值 | 理由 |
|---|---|---|
| `P1_SEGMENT_SECONDS` | **5400**（90 分钟） | 与方案一致。传输成本：358MB gzip，一天约 7–10 次可接受；损失窗口 90 分钟 |
| `P1_SCOPE_TIMEOUT` | 600 | 沿用线上值，不动 |
| `P1_SEGMENT_FINALIZE_BUDGET` | **600** | 覆盖「在跑单元收尾（≤600s）+ merge + 写 status/checkpoint/缺口报告 + 本地发布」 |
| `P1_SEGMENT_STEP_LIMIT` | **6600** = 5400+600+600 | 9-20 的坑正是「只多 100 秒」；现在余量 1200 秒，且**这只是单段**的上限 |
| `P1_TOTAL_BUDGET_SECONDS` | **72000**（20 小时） | 方案建议值。只在段边界检查：不会杀掉正在跑的 p1，只是不开下一段 |
| `P1_SEGMENT_RETRY_LIMIT` | 1 | 段返回 1（无任何可信输出）时重试一次；`reset_p1` 后本来就是从头再采，代价与首次相当 |
| `P1_MAX_STALLED_SEGMENTS` | 2 | `pending` 连续两段不降即停，防「段段 0 进展」的死循环 |
| `P1_WORKERS` / `P1_PLATFORM_WORKERS` | **16 / 4** | 见 §2.2 |

### 2.2 并发 16 的内存测算（写进每轮收据）

并发单位是**公司**（`run_chain` 让同公司 3 个 scope 串行），16 路 = 同时 16 家公司；
平台主机再受 `--platform-workers 4` + `PLATFORM_MIN_INTERVAL=1.0s`（未传
`--platform-interval`，保持默认）约束。

`16 × 约 160MB 峰值 RSS ≈ 2.6GB`，精灵 i5-12500H / **16GB**，basic/tencent 不与 p1 并行
→ 余量约 13GB。该字符串逐字进收据：`p1_concurrency.memory =
"16 workers x ~160MB peak RSS ~= 2.6GB of the jingling box 16GB"`。

### 2.3 次日 06:10 重叠告警

`data/windows-runner.lock` 仍是非阻塞 flock，第二个实例仍 `return 75`（不双开、不崩），
但现在先调用 `runner_skipped_alert()`：

* 总是追加 `data/runner-skipped.jsonl`：`event=runner_skipped`、`exit_code=75`、`mode`、
  `previous.{started_at,stage,finished,success,completed_at,total_jobs,sync_exit}`、
  中文正文「上一轮采集仍在运行，本次跳过（exit 75）」；
* 若 `qiuzhao/notify.py` 存在（**本分支没有**）→ 自动 `notifier.notify('runner_skipped', text=...)`
  走飞书；不存在时记录 `notified = "unavailable: qiuzhao.notify is not in this branch; merge
  feat/cc-bot-notifier to deliver this over Feishu"`。合并 `feat/cc-bot-notifier` 后同一处
  调用点自动生效，**不需要再改代码**；两处都是 best-effort，告警失败不会让 runner 失败。

### 2.4 P0 第二道防线

`record_cleanup()` 把 `stop_tree()` 的任何异常（strict 语义下「确认不了进程树终止」本来就会抛
`RuntimeError`）收敛成收据里的 `cleanup_errors` 条目（`cleanup_error` + 完整
`cleanup_traceback`），`step()` 仍返回 **124**。`run_stage_step()` 在 `step()` 返回后**立刻**
`atomic_json(statepath, state)`，保证这条证据不会因为后续异常而丢——9-20 的收据里连
`steps['p1']` 都没有，就是因为写得太晚。

## 3. 部署件 20260920f

* 相对**精灵现役 20260920a**：**21 个运行时文件 = 20 覆盖 + 1 新增**（`collection_gap.py`）。
  其中 20 个与未部署的 `20260920e` 逐字节相同（`cmp` 逐一比对），只有 `windows_collector.py`
  是本次新改的。`20260920f` **取代 20260920e**，不要叠加部署。
* `SHA256SUMS.txt`：macOS `shasum -a 256 -c` **21/21 OK**，且 21 个文件与分支源码**逐字节一致**。
* `PROD-BACKUP-MANIFEST.txt`：21 行 PRE-DEPLOY 哈希**全部在精灵上只读实测**（不是照抄），
  再交叉核对——11 个对 `git show feat/collector-next-5:.../20260920a/SHA256SUMS.txt`，
  10 个（a 从未带过的文件）对 `20260920e` 的 PRE-DEPLOY 列，`collection_gap.py` 仍 ABSENT。
  **21/21 一致、零漂移**。另附 7 + 6 + 4 行 VERIFY-ONLY（本次不覆盖、只核对，全部匹配）。
* `DEPLOY-NOTES.md`：部署 7 步、回滚步骤、行为变化清单。

## 4. 单测

新增 `tests/test_segmented_publish.py`（18 条）：

| # | 断言 |
|---|---|
| 1 | 假 `taskkill` 输出 **GBK 字节**（真实子进程 + 真实 `taskkill` 替身）→ `stop_tree()` 不抛、`tree_termination_confirmed=True`、`\ufffd` 落在 report 里 |
| 2 | GBK + taskkill 退出码 3 → report 有 `cleanup_error`（`process cleanup incomplete`），`step()` **返回 124** |
| 3 | `stop_tree` 抛任意异常（含 `TypeError: 'NoneType' ...`）→ `step()` 仍 124、`cleanup_traceback` 完整；无 receipt 的调用点（base-sync）同样不抛 |
| 4 | p1 连续返回 2（有 pending）→ **每段都调 `publish_with_rebase`**、每段都跑 normalize、`server_rows_before/after` 正确 |
| 5 | 返回 `run_finished=True` → 立刻跳出，不再开段 |
| 6 | 段内无变化 → **不重复推送**（`action="unchanged"`，只上传 1 次） |
| 7 | `--resume-run` 重入且 checkpoint 已完成 → **不重采、不重推**；整轮 finished 再重入是空操作 |
| 8 | 段内 124 → `result="kept"`、checkpoint 与 staging 都在、仍推送、`p1_stopped` 记录 |
| 9 | 段内 1 → 回滚 + `reset_p1` + **重试一次**，回滚的段不会泄漏进已发布库 |
| 10 | `p1-status.json` 读不到 → 停止而不是空转 |
| 11 | 限时算术：`P1_SEGMENT_STEP_LIMIT == 5400+600+600 == 6600`，p1 argv 带 `--workers 16 --platform-workers 4 --scope-timeout 600 --resume-latest --apply`，不传 `--platform-interval` |
| 12 | 总预算到 → **停在段边界**、已完成段全部已推送、`p1_budget.exhausted=true`、`p1_pending` 记录 |
| 13 | `pending` 连续不降 → 停止（`P1_MAX_STALLED_SEGMENTS+1` 段后） |
| 14 | 清理失败发生在整轮里 → 收据有 `cleanup_errors`、basic 记 124 回滚、**p1 段仍然采集并发布**、全程没有 TypeError |
| 15 | 拿不到运行器锁 → `main()` 返回 **75** 且 `data/runner-skipped.jsonl` 有一条含中文正文的记录 |
| 16 | 有 `qiuzhao/notify.py` 时 → 同一调用点走 notifier（`runner_skipped` + 正文），记录 `notified` |
| 17 | 连 `data/` 都不存在时告警也不炸 |
| 18 | 推送抛异常时，**该段的记录已经落在收据里**（退出码 / `step_changes` / `pending_count` / `finished_at` / `elapsed_seconds`），不会像 9-20 那样「跑过但收据里查不到」 |

**全量对比**（`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/ -q -p no:randomly`）：

| 分支 | 结果 | 失败清单 |
|---|---|---|
| 基线 `fix/p0-typeerror-20260920` @37ac85f2 | **3 failed / 723 passed / 55 skipped** | `test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts` |
| 本分支 | **3 failed / 741 passed / 55 skipped** | **逐条相同，无新增**（741 = 723 + 18 新增） |

偶发 `tests/test_codes_kind.py::test_migration_is_safe_when_both_services_start_together`
（4 个进程同时迁移同一个 sqlite 文件）：**基线 3/15 失败、本分支 3/15 失败**（各跑 15 次），
失败信息都是 `sqlite3.OperationalError: database is locked` —— 与本次改动无关的既有 flake。
因此本分支全量单测有两个稳定读数：**3 failed / 741 passed**（flake 通过）与
**4 failed / 740 passed**（flake 命中），两者失败清单都 = 基线 3 条 + 该 flake。

## 5. 精灵实测（临时目录，未写正式目录、未推真实服务器）

### 5.1 隔离方式（怎么做到"不推真实服务器"）

驱动 `pipeline-watch/segtest-jingling.py` 在临时目录里跑，做法逐条：

1. **树**：`C:\mcp-suite-collector\{qiuzhao,deploy}` 只读复制到
   `C:\mcp-suite-seg-test\`（第二个并行验证用 `C:\mcp-suite-seg-test2\`），再把 20260920f
   的 21 个文件覆盖进去；子进程实测 `qiuzhao.__file__ = C:\mcp-suite-seg-test\qiuzhao\__init__.py`
   （`PYTHONPATH=临时目录` + `cwd=临时目录`）。
2. **venv**：用**正式 venv** `C:\mcp-suite-collector\.venv\Scripts\python.exe`（3.12.2）。
3. **数据**：`--data-dir` 指向临时目录；`jobs.before.json` 是
   `runs\20260920\jobs.before.json` 的**副本**（342.1MB），正式 `runs\` 只读。
4. **不推服务器**：`windows_collector.pull` / `publish_snapshot` 在驱动里被替换成
   `deploy\windows_receiver.py` 的**同语义本地替身**——同样的 CAS 前提校验
   （`digest(server) != expected` → `raise CASConflict('production changed: pull and recollect')`）、
   同样的 `already_published` 短路、上传后 hash 校验；落盘目标是
   `C:\mcp-suite-seg-test2\fake-server\segfast.jobs.json`。**真实 SSH 一次都没发**
   （`publish_snapshot` 里的 ssh 调用被整个替换，`SSH` 常量里的私钥路径在临时 ROOT 下也不存在）。
5. **不调飞书**：`--no-sync`。
6. **不碰计划任务、不碰正式 `data\`/`runs\`**；段长临时调小（下面写明）。
7. `PYTHON` 指向正式 venv、`--companies`/`--scopes` 由驱动注入 p1 argv（链上没有这两个开关），
   这两处注入都在收据里写明。

### 5.2 被验证的确切字节（自证）

精灵上 `C:\mcp-suite-seg-test2\deploy\windows_collector.py` 的 sha256 =
**`4db95ba3a953adea0b9c79255080f706fdb10b0dd5197313416b4854076717c5`** = 本包
`deploy-artifacts/20260920f/windows_collector.py`，mtime **13:40:29**；同树
`p1_pipeline.py`=`cd2d22c8…`、`portable_runtime.py`=`62afa7bd…`、`collection_gap.py`=`34351a1c…`
全部与本包逐字节一致。**下列每一轮的 `p1-runs` 目录创建时间都晚于 13:40:29**，即都跑的是
将要下发的字节（另外 `p1_segments[*].p1_seconds` 这个字段本身只存在于最终版，
它出现在收据里即为直接证据）：

| 运行 | 段长/并发/公司 | p1-runs 创建时间 | steps |
|---|---|---|---|
| A `segtest`（完整链） | 300s / 16 / 6 家×3 scope | 13:54:41 | basic 2、tencent 0、p1 0、normalize 0 |
| B `segfast2` | 300s / 16 / 6 家×3 scope | 13:40:23 | p1 0、normalize 0 |
| C `segmulti` | 120s / 2 / 6 家×campus | 13:47:29 | p1 0、normalize 0 |
| D `segfinal-multi` | 20s / 1 / 3 家×campus | 13:51:24 | p1 0、normalize 0 |
| E `segfinal-16` | 300s / 16 / 6 家×3 scope | 13:59:03 | p1 0、normalize 0 |
| F `segfinal-timeout` | 300s（step-limit 25s）/ 16 / 1 家×3 scope | 14:06:28 | p1 **124**、normalize 0 |
| G `taskkill`（独立） | — | — | — |

### 5.3 实测 D：多段 + 每段落袋 + 断点续跑（核心证据）

`--workers 1 --scopes campus --segment-seconds 20`，3 家公司，最终字节，`--apply`：

| 段 | 退出码 | p1 耗时 | 段总耗时 | pending | run_finished | 推送 | 服务器条数 |
|---|---|---|---|---|---|---|---|
| 1 | 2 | 42.9s | 114.9s | 2 | False | `published`（direct，CAS 直推） | 94,486 → 94,487 |
| 2 | 2 | 42.9s | 163.0s | 1 | False | `published`（**CAS 冲突 → rebase 2 次**，`added_rows=1`） | 94,487 → 94,488 |
| 3 | 0 | 45.1s | 165.9s | 0 | **True** | `published`（rebase） | 94,488 → 94,489 |

* **每段都走了完整发布链路**：`normalize` + `preserve()` + `publish_with_rebase()`，
  段 2/3 还真触发了 CAS 冲突→三方 rebase（`direct=false, rebase_attempts=2`）。
* **没有重复采集**：整个运行只有 **一个** `p1-runs\20260920T135124` 目录、
  **3 个 `validated.json`**（= 3 个单元），`p1_status.results=3` 且每个 `attempted=true`、
  `publish_errors=[]`。若续跑是「重开一轮」，会出现第二个时间戳目录并多出 `validated.json`。
* `receipt.json` 里三段齐全（退出码 / `p1_seconds` / `elapsed_seconds` / `pending_count` /
  `step_changes` / `server_rows_before|after`）。
* 整轮 450.1s、`exit_code=0`、`success=true`、无 error、无 TypeError。

### 5.4 实测 E / A：16 路并发 + 完整链

* **E `segfinal-16`**（6 家×3 scope，`--workers 16`）：18 个单元全部 `success+complete`，
  一个段内跑完（`run_finished=True` → 循环立即跳出），推送 94,486 → **94,873**（+387），
  本地镜像同步 94,873 行；段耗时 430.4s（p1 355.1s）；`p1.log` 里
  **`Errno 36` 0 次、`UnicodeDecodeError` 0 次、Traceback 0 次**；
  `p1_concurrency` 逐字记录了 16 / 4 / 1.0s / 2.6GB 内存测算。
* **A `segtest`**（完整每日链，早于最终字节）：basic **2**（+35 / 更新 62,497 / 下架 4）、
  tencent 0、p1 0（18 单元）、normalize 0，发布 94,486 → **94,908**，整轮 **1849s**，
  `error=null`、`typeerror_in_receipt=false`。说明分段改造没有破坏 basic/tencent 之后
  的一次性发布收尾。

### 5.5 实测 F + G：taskkill 路径不再崩（9-20 复现形状）

* **G（独立、真实 taskkill）**：临时树里起一个真实子进程，直接调
  `portable_runtime.stop_tree(child)`，用 **精灵真实的 `C:\WINDOWS\System32\taskkill.exe`**：

  ```json
  {"pid": 17280, "raised": null,
   "report": {"already_exited": false, "tree_termination_confirmed": true,
              "taskkill_exit_code": 0,
              "taskkill_stdout": "\ufffd\ufffd\ufffd: \ufffd\ufffd\ufffd\ufffd PID 22940 (\ufffd\ufffd\ufffd PID 17280 \ufffd\ufffd\ufffd\ufffd)...",
              "process_terminated": true},
   "child_exited": true}
  ```

  即：GBK 字节被 `errors='replace'` 解成 U+FFFD、**不抛异常**、进程树确认终止。
  （顺带：本次一个诊断脚本自己踩了同一个坑——`subprocess.run(text=True)` 读 PowerShell 的
  GBK 输出抛 `UnicodeDecodeError`——正好复现了 9-20 的根因形状。）

* **F（整轮里的 124）**：把该段的 `step()` 限时临时压到 25s，强制父看门狗在 p1 收尾前开火：

  ```
  steps            = {"p1": 124, "normalize": 0}
  step_changes.p1  = {"exit": 124, "result": "kept"}          ← 不回滚、不 reset_p1
  p1_stopped       = "p1 watchdog fired; staging and checkpoint kept for the next segment or resume"
  cleanup_errors   = [{"step":"p1","pid":29912,"already_exited":false,
                       "tree_termination_confirmed":true,"taskkill_exit_code":0,
                       "taskkill_stdout":"<GBK→U+FFFD>","taskkill_stderr":"",
                       "process_terminated":true}]
  typeerror_in_receipt = False
  p1_checkpoint_exists = True   p1_status_file_exists = True
  ```

  收据里**没有 TypeError**、p1 的 checkpoint 与 staging 都保留、仍然走完了 normalize + 推送。
  这正是 9-20 那天缺的那条路径。

### 5.6 运行器锁冲突告警（真实产生的一条记录）

验证期间意外制造了一次真实的锁冲突（两个运行共用同一个临时 ROOT），第二个实例立刻
`return 75` 并写下 `C:\mcp-suite-seg-test\data\runner-skipped.jsonl`：

```json
{"ts": "2026-09-20T13:32:16.547053+08:00", "event": "runner_skipped", "exit_code": 75,
 "mode": "daily", "previous": {"status_file": "missing or unreadable"},
 "reason": "another windows_collector run still holds data/windows-runner.lock; this invocation exited 75 without collecting, publishing or syncing",
 "message": "上一轮采集仍在运行，本次跳过（exit 75）。\nmode=daily\nprevious.started_at=None\nprevious.stage=None\nno second collector was started, nothing was collected or published.",
 "notified": "unavailable: qiuzhao.notify is not in this branch; merge feat/cc-bot-notifier to deliver this over Feishu"}
```

未双开、未采集、未发布，告警落地。（本分支确实没有 `qiuzhao/notify.py`，记录如实写明；
合并 `feat/cc-bot-notifier` 后同一处自动走飞书。）

### 5.7 隔离方式的自查

* 全程 `C:\mcp-suite-collector` **只读**：只复制 `qiuzhao`/`deploy`、只读
  `runs\20260920\jobs.before.json`；未写、未改任何正式文件（事后核对 21 个正式路径
  sha256 仍与部署前一致，见 §3 与 `PROD-BACKUP-MANIFEST.txt`）。
* **真实 SSH 发布 0 次**：`pull`/`publish_snapshot` 是本地替身，`SSH` 常量指向的私钥在临时
  ROOT 下根本不存在；`receiver_pulls`/`receiver_publications` 都落在
  `C:\mcp-suite-seg-test*\fake-server\*.jobs.json`（94,486 → 94,908 行的变化只发生在该文件）。
* **飞书 0 次调用**（`--no-sync`）、**计划任务 0 次触碰**、**未终止任何进程**。
* 期间精灵上另有一个与本任务无关的 `C:\mcp-recovery-20260920-codex-candidate\recover.py`
  在跑（14:07 前后可见）；本任务没有触碰它，特此记录。

### 5.8 等价目录自检（Mac 侧，用**精灵现役的** `v4_fields.py`）

把 21 个文件覆盖进一棵工作区副本、并用精灵现役 `qiuzhao\v4_fields.py`
（`f74e6ab3…`，与分支不同的既有分叉）替换后导入：

```
V4_SHA f74e6ab3b0020a0b     WC_SHA 4db95ba3a953adea
IMPORT_OK 1124 1124 True    LOCK True
CHILD_TEXT replace | SEG 5400 6600 72000 16 4
P1 -m qiuzhao.collector.p1_pipeline --data-dir /stage --apply --resume-latest --scope-timeout 600 --workers 16 --platform-workers 4 --max-run-seconds 5400  LIMIT 6600
GAP collection_gap.py
```

即：本包与现役 `v4_fields.py` 兼容（只用到 live 已有的
`iter_json_file`/`graduation_of`/`graduation_constraints_of`）。

## 6. 遗留与提醒

1. **真正的规模瓶颈是 `p1_pipeline.publish()` 的「每单元重写整库」**，不是段长：9-20 实测
   828 次本地发布 / 18000s ≈ **21.7s 一次**，而 `_publish_thread_lock` + 文件锁让发布串行。
   1124 家 × 3 scope ≈ 3300 个单元 → 光本地发布 I/O 就约 **19 小时**，与 20 小时总预算同量级。
   首次真实运行要盯 `p1_segments[*].p1_seconds` 与段数：**若在段边界撞上总预算，先把
   `P1_TOTAL_BUDGET_SECONDS` 调大（如 36 小时），不要缩短段长**；要根治得改
   `publish()` 的增量落盘（另开任务）。
2. `feat/cc-bot-notifier` 合并后飞书告警自动生效（`qiuzhao/notify.py` 存在即走它）。
   本次只落 `data\runner-skipped.jsonl`。
3. 本包同时带着 `feat/collector-next-6` + `feat/gap-report` + P0（都从未部署）；
   部署 20260920f 一步到位，**不要再叠 20260920c/d/e**。
4. `basic` / `tencent` 仍是「一次跑完」的整段（分别约 30 分钟 / 几分钟），没有分段；
   它们失败仍是回滚该段但**不阻塞 p1 与发布**（§5.4 的 A 实测就是 basic 返回 2 仍完成发布）。
5. 总预算在段边界停下时，未完成的单元不会带进次日那一轮（次日从新的服务器快照 + 默认全集
   重跑），等于次日重采，这是可接受的取舍，已写进 `p1_stopped`/`p1_pending`。
6. `preserve()` 现在每段跑一次（约 2 遍 350MB 读 + 1 遍写），是分段换来的固定成本。
