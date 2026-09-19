# 收据：p1 并发发布 Windows 死锁热修（`Resource deadlock avoided`）

- 分支：`fix/p1-winlock`（起点 `feat/collector-next-4` `82af4f72`）
- worktree：本机 `/Users/maxzhl/Projects/mcp-suite-p1-winlock`
  （**偏差说明**：任务书指定外接盘 worktree，但执行时 `/Volumes/臭垃圾桶` 已 100% 满、
  仅剩 163Mi，`git worktree add` 在 26% 处 `No space left on device`。为不删除其它任务
  的数据，改在内部盘建 worktree；分支/提交/部署件不受影响。）
- 结论：已定位并修复；单测可在 Mac 上复现 Windows 语义；精灵临时目录真实并发 p1
  实测通过（退出码 2、5 个单元发布成功、0 次 Errno 36）。**未部署、未推、未合并 main。**

## 1. 根因

`publish()` 用文件锁 `p1-publish.lock` 做跨进程互斥；Windows 下
`portable_runtime.flock` 用 `msvcrt.locking` 模拟。`msvcrt.locking` 对**同一进程内已
持有该区域**的再次加锁直接抛 `OSError [Errno 36] Resource deadlock avoided`，而
POSIX `flock` 会阻塞等待。p1 改为 `ThreadPoolExecutor`（`--workers 8`）后，同一进程的
两个线程同时进 `publish()`，第二个线程立刻抛错；异常从 `run_unit → run_chain → run`
冒泡，`main()` 未捕获 → 整个 p1 退出码 1 → `windows_collector.py` 按契约整段回滚。

2026-09-19 06:10 首轮失败现场（精灵 `runs\20260919\`，只读复核）：

```
runs\20260919\p1.log
  File "...\p1_pipeline.py", line 1204, in <module>
  File "...\p1_pipeline.py", line 1192, in main
  File "...\p1_pipeline.py", line 1070, in run
  File "...\p1_pipeline.py", line 1042, in run_chain
  File "...\p1_pipeline.py", line 1019, in run_unit
  File "...\p1_pipeline.py", line 681, in publish
  File "...\portable_runtime.py", line 21, in flock
OSError: [Errno 36] Resource deadlock avoided

runs\20260919\receipt.json
  steps = {"basic":2,"tencent":0,"p1":1,"normalize":0}
  step_changes.p1 = {"exit":1,"result":"rolled_back"}
```

**关键补充事实（本次新查到）**：崩在竞态上，不是每次发布都崩。失败那次在崩溃前已经
成功跑出 **12 次 publication**（22:34:31–22:41:01 UTC，即北京 06:34–06:41），第 13 次
并发时两线程撞上才抛 Errno 36。所以 18 个单元里 12 个已经合并进 stage，随后整段回滚
全部丢弃。修复前的"没崩"只是竞态没撞上，不能视为正常。

## 2. 修法

改动文件：`qiuzhao/collector/p1_pipeline.py`（其余运行时文件不动）。

1. **进程内串行**：新增模块级 `_publish_thread_lock = threading.Lock()`；
   `publish()` 在 `open(p1-publish.lock)` + `fcntl.flock(LOCK_EX)` **外层**先
   `with _publish_thread_lock:`。这样同一进程内任何时刻只有一个线程去碰
   `msvcrt.locking`，Errno 36 不再可能发生；文件锁保留，跨进程互斥不变。
   同时在 `finally` 里显式 `fcntl.flock(lock, LOCK_UN)`，让锁生命周期对两类实现对称。
2. **单个发布失败不再炸整段**：`run_unit()` 对 `publish()` 用
   `except Exception` 收敛。失败时：
   - 该单元 `published=False`、写 `publish_error`（含异常类型与原因）、
     `publish_failed_at`；
   - 其余单元照常采集与发布；
   - 该单元写进 `p1-retry-queue.json`（`reason=publish`），次日优先重试；
     `validated.json` 已落盘，resume 时重试发布而不重采；
   - 打印行带上 `publish_error`。
3. **退出码契约不变**：`status['success']` 现在要求"全 success 且无 publish_error"；
   `any_validated` 跳过带 `publish_error` 的单元（它没有合并进库，按原语义本就不算
   "validated 且已合并"）。因此 **0=全成功 / 2=至少一个单元成功合并 / 1=没有任何
   单元成功**。`failure_reason()` 新增 `publish` 分类。

## 3. 代码位置

| 位置 | 改动 |
|---|---|
| `p1_pipeline.py` 模块级（publish 前） | 新增 `_publish_thread_lock` + 说明注释 |
| `p1_pipeline.py` `publish()` | 外层 threading 锁；`finally` 显式 `LOCK_UN` |
| `p1_pipeline.py` `run_unit()` | `try/except Exception` 收敛 publish；记录 `publish_error`；retry queue 记 `publish` |
| `p1_pipeline.py` `any_validated()` | 跳过 `publish_error` 单元 |
| `p1_pipeline.py` `failure_reason()` | `publish_error` → `'publish'` |
| `p1_pipeline.py` `run()` 末尾 | `success` 追加 `and not publish_error` |

## 4. 并发路径 `flock` 全量审计（逐处确认）

| 调用点 | 是否多线程可进入 | 处置 |
|---|---|---|
| `p1_pipeline.publish()` `p1-publish.lock` | **是**（多个 `run_unit` 线程） | **加进程内 `threading.Lock`** |
| `p1_pipeline.main()` `collector.lock`（`LOCK_NB`） | 否：进程启动时主线程取一次 | 不改（跨进程语义） |
| `p1_status_repair.apply()` `collector.lock`+`p1-publish.lock` | 否：独立 CLI `main()`，p1 链不调用 | 不改 |
| `p1_feishu_public.collect()` `QIUZHAO_BROWSER_LOCK` | 否：每个单元是独立适配器**子进程**，内部单线程 | 不改 |
| `sync_lark_multivalue` 同步锁 | 否：独立同步 CLI，单线程 | 不改 |
| `import_p1_candidates` 导入锁 | 否：一次性导入脚本 | 不改 |
| `deploy/windows_collector.main()` `windows-runner.lock` | 否：每日链主线程取一次 | 不改 |
| `deploy/windows_recover_run` 恢复锁 | 否：独立恢复工具，单线程 | 不改 |
| `deploy/windows_receiver`（服务端 POSIX `fcntl`） | 否：服务器侧，非 Windows 并发路径 | 不改 |

checkpoint / `p1-status.json` / `p1-retry-queue.json` / `p1-last-attempt.json` 的写入
本来就不用 `flock`，而是 `atomic_json`（`mkstemp` + `os.replace`），且在 `run_unit`
里受模块内 `state_lock`（`threading.Lock`）保护，无新增风险。

`portable_runtime.py` 因此**无需改动**：它只是被 `publish()` 调用，问题在调用方缺少
进程内串行层；直接改 `portable_runtime.flock` 的全局 `LOCK_NB` 语义会波及
`windows_collector` 的跨进程单例判定，风险更大。

## 5. 单测（Mac 上复现 Windows 语义）

`tests/test_p1_pipeline.py` 新增 `P1WindowsPublishLockTests`（6 条）+
`_WindowsStyleFcntl` 假锁：

- 假锁按**路径**记录"同进程已持有"，二次加锁抛
  `OSError(errno.EDEADLK, 'Resource deadlock avoided')`，`LOCK_UN` 释放——正是
  `msvcrt.locking` 的行为；并有专门用例断言该假锁确实复现重入报错。
- `test_eight_threads_publish_all_succeed_and_serialize`：8 线程同时 `publish`，
  全部成功、`max_active == 1`（串行化）、jobs.json 含全部 8 家。
- `test_concurrent_run_with_windows_style_lock_publishes_every_unit`：
  `run(..., apply=True, workers=8)` 在假锁下返回 0，`publications` 8 条。
- `test_single_publish_failure_keeps_other_units_and_returns_partial`：小米的
  publish 抛 Errno 36，其余 3 家照常成功，退出码 **2**（非 1），失败单元
  `published=False` + `publish_error`，retry queue `reason=publish`。
- `test_all_publish_failures_return_fatal_without_aborting`：全部 publish 抛错，
  退出码 **1**、`any_validated` 为假，但异常不冒泡。
- `test_publish_still_waits_for_another_process_file_lock`：另起真实进程持
  `fcntl.flock(LOCK_EX)`，本进程 `publish` 在 0.6s 内保持阻塞，释放后才完成——
  证明跨进程互斥未被削弱。

反向验证（一次性脚本，不入库）：把 `_publish_thread_lock` 换成 no-op 后，同样 8 线程
假锁下有 **7/8** 次抛 `OSError: [Errno 11] Resource deadlock avoided`——说明测试确实
能抓住该回归。

`pytest tests/`：

| 版本 | 结果 |
|---|---|
| `feat/collector-next-4` 基线（交接文档记录） | 3 failed / 640 passed / 55 skipped |
| `fix/p1-winlock` 本次 | **3 failed / 646 passed / 55 skipped** |

失败 3 条逐条相同：`test_core::test_role_cohort_and_campaign_title_bases`、
`test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、
`test_schema::test_enum_check_fails_when_data_drifts`；偶发 `test_codes_kind` 本次通过。
新增失败 **0**（passed +6 即本次新增单测）。

## 6. 精灵临时目录实测（正式目录只读）

方法（与 `C:\mcp-suite-partial-test\` 同法）：

1. `robocopy C:\mcp-suite-collector\qiuzhao C:\mcp-suite-winlock-test\qiuzhao /E /XD __pycache__`
   + 同法复制 `deploy`（54 + 4 个真实文件；正式目录 `C:\mcp-suite-collector` 全程只读）。
2. 覆盖 `C:\mcp-suite-winlock-test\qiuzhao\collector\p1_pipeline.py` 为
   **20260918k + 修复**（gzip+base64 分片上传），精灵侧 SHA256
   `13A5EC53A2B934809482A44F683BEC6C5B2774BF96964CF57FB1DF2D4CDDACDA` 与 Mac 本地
   逐字节一致；`py_compile`/import 通过，模块解析到临时目录
   `C:\mcp-suite-winlock-test\qiuzhao\collector\p1_pipeline.py`，`REGISTRY_COUNT=948`，
   6 家公司全部注册（OPPO/vivo/商汤科技/大华股份 走硬编码源，中信建投 走 beisen，
   小天才 走 moka），`_publish_thread_lock` 存在。
3. `--data-dir` = `C:\mcp-suite-winlock-test\data`，其 `jobs.json` 从
   `runs\20260919\jobs.before.json` 复制（343,047,764 字节，**未用正式 `data\jobs.json`**）。
4. 用**正式 venv** `C:\mcp-suite-collector\.venv\Scripts\python.exe`（Python 3.12.2），
   `PYTHONPATH=C:\mcp-suite-winlock-test`，跑
   `-m qiuzhao.collector.p1_pipeline --companies OPPO,vivo,商汤科技,大华股份,中信建投,小天才
   --scopes campus --workers 4 --apply --scope-timeout 600 --max-run-seconds 2400`。

结果：

```
exit = 2
run_finished = True, success = False, pending = [], publications = 5
grep Errno 36 / deadlock（run-concurrent 全部 .log + stdout）= 无命中
```

| 单元 | coverage | collected_jobs | published | publish_error |
|---|---|---|---|---|
| 商汤科技/campus | blocked | 0 | True（跳过发布） | 无 |
| 中信建投/campus | success | 29 | True | 无 |
| OPPO/campus | success | 141 | True | 无 |
| 大华股份/campus | success | 146 | True | 无 |
| 小天才/campus | success | 12 | True | 无 |
| vivo/campus | success | 166 | True | 无 |

5 次 publication（CAS 链式，同一 `batches/<ns>/`）：

```
中信建投 15:32:24 before=1da0252e after=a43b925b total=93548
OPPO     15:33:02 before=a43b925b after=e3941769 total=93548
大华股份 15:33:20 before=e3941769 after=2dff1ef3 total=93548
小天才   15:33:38 before=2dff1ef3 after=c27c3250 total=93560
vivo     15:33:57 before=c27c3250 after=ffa2d646 total=93560
```

- **确为并发**：`--workers 4`，启动即见 4 个单元目录（`01`–`04`）同时采集；
  第一次 publish（15:32:24）发生时 OPPO/大华 仍在采集（checked_at 15:32:45/15:33:03）。
- 合并后 `data\jobs.json` = 93,560 行，末次 `after_sha256 = ffa2d64609bde7…`
  与 publication 回执一致；5 家 campus 新数据均在库内。
- 退出码 2 的唯一原因：**商汤科技** 两个官网 `hr-jobs.sensetime.com` 的
  Playwright `Page.goto` 均 45s 超时（站点问题，与锁无关），进
  `p1-retry-queue.json`（`reason=timeout`）。
- 原始输出：`pipeline-watch/p1-winlock-evidence/{status.json,stdout.log,exit.txt,summary.json}`。

**未发布到服务器、未触发飞书、未改计划任务、未碰正式目录、未终止任何进程。**

## 7. 部署件 `pipeline-watch/deploy-artifacts/20260919k/`

**只含 1 个运行时文件**（本次唯一被改的运行时文件）：

| 文件 | 目标 | 本包 sha256 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | `13a5ec53a2b934809482a44f683bec6c5b2774bf96964cf57fb1df2d4cddacda` |

包内另有 `SHA256SUMS.txt`、`PROD-BACKUP-MANIFEST.txt`、`DEPLOY-NOTES.md`。
`20260919k/p1_pipeline.py` = `20260918k/p1_pipeline.py` 逐字节 + 本修复；
其 `def publish` 之后与分支源码**逐字节相同**（`diff` 为空）。相对 k 共 121 行变化。

### 两种部署路径

**路径 A（推荐，当前实际状态）**：精灵现役 = `20260918k`，`20260919g` **未部署**。
直接用本包覆盖 `qiuzhao/collector/p1_pipeline.py` 一个文件即可。
- 部署前应有：`ff96be4d772847a0273003e2db0466d3ad698dc5cd719d968f40fb96abc8dc76`
  （本次已在精灵实测，与 k 清单一致）。
- 部署后应为：`13a5ec53…`。
- 覆盖后跑 `python -c "import qiuzhao.collector.p1_pipeline as P; print(P._publish_thread_lock is not None)"`
  应为 `True`；次日 `runs\<日期>\p1.log` 不再出现 Errno 36。

**路径 B（若站长先部署了 `20260919g`）**：本包的 `p1_pipeline.py` **不可用于 g**
（缺 g 的全部注册块与新适配器）。需把同一修复合入 g 后重出一份；等价做法是用
`fix/p1-winlock` 分支的 `qiuzhao/collector/p1_pipeline.py`
（= g + 同一修复，sha256 `093b237e852ba1d15717e97adc6b7de66f412c84c4005b3a72e79b4a108de12d`）
覆盖已部署 g 树的同名文件，其余 g 文件不动。回滚到 g 的
`5852f4973e10d872736a7ca72550f6fb1a2889a9736ab8ee0bc0c08af93f856b`。

### 回滚

- 路径 A：还原 `qiuzhao/collector/p1_pipeline.py` 为 k 版（备份
  `C:\mcp-suite-backup-20260918-2020\qiuzhao\collector\p1_pipeline.py`，或
  `pipeline-watch/deploy-artifacts/20260918k/p1_pipeline.py`），校验回 `ff96be4d…`。
- 路径 B：还原为 g 版 `5852f497…`。
- 回滚只影响该一个文件；`run.py`/`windows_collector.py`/配置/适配器本次均未动。

## 8. 今天丢了哪些数据（2026-09-19 06:10 首轮 p1 回滚）

失败运行 `runs\20260919\data\p1-runs\20260919T063349\status.json` 记录：
**18 个单元（11 success / 6 blocked / 1 partial）**，其中 **12 个已合并进 stage
（94486→94493）**，随后 p1 退出码 1 → `windows_collector.py` 用 `jobs.before.json`
整段回滚，18 个单元的成果**全部丢弃**，且 `reset_p1` 清掉 checkpoint/retry-queue，
次日只能从头重采。明细：

| 单元 | coverage | 采集条数 | 是否已合并后才回滚 |
|---|---|---|---|
| 拼多多/campus | success | 36 | 是 |
| 拼多多/intern | success | 2 | 是 |
| 拼多多/social | partial | 0 | 是 |
| OPPO/campus | success | 141 | 是 |
| OPPO/intern | success | 105 | 是 |
| OPPO/social | success | 149 | 是 |
| vivo/campus | success | 166 | 是 |
| vivo/intern | success | 89 | 是 |
| vivo/social | success | 137 | 是 |
| 小红书/campus | blocked | 0 | 否 |
| 小红书/intern | success | 295 | 是 |
| 小红书/social | blocked | 0 | 否 |
| 快手/campus | success | 476 | 是 |
| 快手/intern | blocked | 0 | 否 |
| 快手/social | blocked | 0 | 否 |
| 比亚迪/campus | blocked | 0 | 否 |
| 比亚迪/intern | success | 6 | 是 |
| 比亚迪/social | blocked | 0 | 否 |

12 次 publication 时间线（UTC；北京 +8）：拼多多 campus 22:34:31 / intern 22:34:56 /
social 22:35:26 → OPPO campus 22:35:45 → 比亚迪 intern 22:36:04 → vivo campus 22:36:32
→ OPPO intern 22:37:26 → 小红书 intern 22:38:07 → vivo intern 22:38:26 → OPPO social
22:39:28 → vivo social 22:40:39 → 快手 campus 22:41:01；之后并发发布撞上 Errno 36，
整段回滚。**这 18 个单元的当日增量（含 OPPO 141、vivo 166、快手 476、小红书 295）
没有任何一条进入线上库**；basic/tencent/normalize 的 93519→94486 不受影响。

## 9. 产物

- 分支：`fix/p1-winlock`（commit 见文末）。
- 源码：`qiuzhao/collector/p1_pipeline.py`；单测：`tests/test_p1_pipeline.py`。
- 部署件：`pipeline-watch/deploy-artifacts/20260919k/`（1 运行时文件 + SHA256SUMS +
  PROD-BACKUP-MANIFEST + DEPLOY-NOTES）。
- 实测证据：`pipeline-watch/p1-winlock-evidence/`（成功 run 的 status/stdout/exit/summary
  + 失败 run 的 status/receipt）。
- 本收据：`pipeline-watch/RECEIPT-p1-winlock.md`。

## 10. 硬约束声明

未部署、未覆盖精灵正式目录、未碰阿里云、未写飞书、未读取/打印任何令牌、
未 push、未合并 main、未终止任何进程。精灵临时目录实测只读正式目录，使用正式 venv
但 `PYTHONPATH` 指向临时目录、`--data-dir` 指向临时 jobs 副本，未调用服务器发布与飞书同步。
