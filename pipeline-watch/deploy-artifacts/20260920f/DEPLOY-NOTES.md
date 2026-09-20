# 20260920f 累积部署件（分段发布 + 去掉总时长上限 + 并发 16）

生成：2026-09-20，分支 `feat/segmented-publish`
（worktree `/Users/maxzhl/Projects/mcp-suite-seg`；起点 `fix/p0-typeerror-20260920` 37ac85f2
= `feat/collector-next-6` f0694da7 + `feat/gap-report` 3468074a + 9-20 的 P0 修复）。

状态：**未部署**。必须由站长明确说「上线」后才可覆盖精灵正式目录。

## 0. 这个包是什么，以及它和 20260920a/c/d/e 的关系

**20260920f 取代 20260920e，不要两个一起部署，也不要再部署 c/d/e。**
精灵现役是 `20260920a`（2026-09-20 01:32 上线）；`c`/`d`/`e` **从未部署**。f 是
「a → f 一步到位」的累积包：

| 来源 | 文件数 | 说明 |
|---|---|---|
| `feat/collector-next-6`（= 20260920c 的内容） | 13 | Moka 详情缓存续采、tupu360 分页硬截断、6 处「分页谎报」修复 |
| `feat/gap-report`（= 20260920d 的内容） | 3 | 新增 `collection_gap.py`；改 `p1_meituan_public.py`、`deploy/windows_collector.py` |
| 9-20 P0 修复（= 20260920e 的内容） | 5 + 2 | 子进程解码（`portable_runtime` 等 5 个文件）+ `p1_pipeline.py` 脏 coverage 容错 + `windows_collector.py` 限时/traceback |
| **本次（分段发布）** | **1** | `deploy/windows_collector.py` 再改一次：p1 从「跑一次」变「分段循环 + 每段发布」 |

21 个文件 = 20 覆盖 + 1 新增（`qiuzhao\collector\collection_gap.py`）。
其中 20 个文件与 20260920e **逐字节相同**（已 `cmp` 逐一比对），只有
`deploy\windows_collector.py` 是新的。叠加顺序：**`20260920a`（现役）→ `20260920f`**。

## 1. 这次改了什么（只有 `deploy\windows_collector.py`）

### 1.1 分段发布（核心）

原来整条链是「全部跑完才推送服务器」：p1 跑一次 → normalize 一次 → `preserve()` +
`publish_with_rebase()` 一次。9-20 那天 11:43 崩在推送之前，958 个单元、19,619 条新岗位
全部作废。现在改成：

```
段 1:  p1 --max-run-seconds 5400 --resume-latest  → normalize → preserve + publish
段 2:  p1 --max-run-seconds 5400 --resume-latest  → normalize → preserve + publish
...
直到 <stage>\p1-status.json 的 run_finished==True 且 pending 为空
```

**没有新写任何发布逻辑**：`--resume-latest` + checkpoint + `pending` + 0/2/1 退出码契约 +
`preserve()` + `publish_with_rebase()` 的三方 rebase + `same_publication` 判重全部沿用。
p1 撞到自己的 deadline 本来就是**优雅收尾**（停止派发新单元、等在跑的单元收尾、写
`pending`、返回 2），分段只是把这个语义当成「一段的结束」。

| 常量 | 值 | 理由 |
|---|---|---|
| `P1_SEGMENT_SECONDS` | 5400（90 分钟） | 一段的采集时长；损失窗口 = 一段。调大省传输次数、调小少丢数据 |
| `P1_SCOPE_TIMEOUT` | 600 | 不变（单 scope 子进程上限） |
| `P1_SEGMENT_FINALIZE_BUDGET` | 600 | 在跑单元收尾 + merge + 写 status/缺口报告 + 本地发布 |
| `P1_SEGMENT_STEP_LIMIT` | **6600** | = 5400 + 600 + 600。**彻底消除 9-20 那个「只多 100 秒」的坑** |
| `P1_TOTAL_BUDGET_SECONDS` | 72000（20 小时） | 防失控兜底；只在**段边界**检查，超了不开新段，绝不硬杀 |
| `P1_SEGMENT_RETRY_LIMIT` | 1 | 某段返回 1（无任何可信输出）时回滚该段并重试一次 |
| `P1_MAX_STALLED_SEGMENTS` | 2 | `pending` 连续两段不下降就停（防死循环） |

每段退出码的处理（写进收据）：

* **0 / 2** → 该段成功，照常 normalize + 推送（2 = 部分成功，不再当失败）。
* **1** → 按 2026-09-18 契约**回滚该段**（staging 还原 + `reset_p1`），**重试一次**；
  再失败就停在段边界，已完成的段早已发布。
* **124**（父看门狗超时）→ **不回滚、不 reset**：p1 的每单元发布走的是原子替换 + CAS，
  硬杀不会写坏 staging；回滚等于把这一段白采。记 `step_changes.p1.result="kept"`，
  停在段边界，checkpoint 留给 `--resume-run` 或次日。
* **normalize 失败 / `p1-status.json` 读不到 / pending 不再下降 / 总预算到** → 都在段边界
  停下并记录原因（见收据 `p1_stopped`、`p1_budget`）。

**判重**：每段推送前先算 `same_publication`（staging 字节 == 上次发布的源、且已发布文件
的 sha256 == 收据里的 `after_sha256`）。没变化就**不重复上传那 358MB**，收据里记
`"action": "unchanged"`。

**断点续跑**：`--resume-run <run>` 重入时，若 checkpoint 已经 `run_finished`，**不重跑任何
段**（不会新开 `p1-runs\<新时间戳>`），只补跑 normalize + 判重推送；整轮已 `finished` 的收据
直接返回，什么都不做。

### 1.2 去掉总时长上限

p1 不再有 5 小时全局上限，改由分段循环控制到跑完为止；`P1_TOTAL_BUDGET_SECONDS = 72000`
是唯一兜底，且**只在段边界生效**——不会杀掉正在跑的 p1，只会不开下一段。

### 1.3 并发 16

`--workers 16 --platform-workers 4 --scope-timeout 600`，`PLATFORM_MIN_INTERVAL` 保持
1.0 秒（不传 `--platform-interval`）。**并发单位是「公司」**（`run_chain` 让同公司多
scope 串行），16 路 = 同时 16 家公司；平台主机（北森/Moka 等）另受 `--platform-workers 4`
与 ≥1s 间隔约束。内存测算：**16 × 约 160MB 峰值 RSS ≈ 2.6GB**，精灵 16GB，
留 13GB 余量（basic/tencent 不与 p1 同时跑）。该测算写进每轮收据的
`p1_concurrency.memory`。

### 1.4 P0 的第二道防线（进程清理失败 ≠ 流水线失败）

`step()` 里原来裸调 `stop_tree(child)`。现在包成 `record_cleanup()`：无论 `stop_tree` 抛
什么（strict 语义下确认不了终止就会抛），都写进收据的 `cleanup_errors`（含
`cleanup_error` 与完整 `cleanup_traceback`），`step()` **照常返回 124**。
9-20 那种「清理异常冒到顶层、`steps['p1']` 根本没写、整天回滚」不可能再发生。

### 1.5 次日 06:10 重叠不再静默

拿不到 `data\windows-runner.lock` 时仍是干净退出 **75**（不双开、不崩），但现在多一步
`runner_skipped_alert()`：

* **总是**追加一条结构化记录到 `data\runner-skipped.jsonl`（含时间、模式、上一轮的
  `started_at`/`stage`/`total_jobs`、中文告警正文），内容明确「上一轮采集仍在运行，本次跳过」；
* 若本分支有 `qiuzhao/notify.py`（**本分支没有**，它在 `feat/cc-bot-notifier` 上），
  自动改走飞书告警；没有时记录里写明
  `unavailable: qiuzhao.notify is not in this branch; merge feat/cc-bot-notifier ...`。
  合并 cc-bot-notifier 后**同一处调用点自动生效，不需要再改代码**。

## 2. 部署后与现在不同的地方

1. **服务器库每约 90 分钟更新一次**，不再等整轮跑完；中途挂了最多丢一段。
2. p1 不再有 5 小时上限，跑到跑完为止（单段 90 分钟，总预算 20 小时兜底）。
3. 同时在跑的公司从 8 家变 16 家；平台主机并发从 3 变 4。
4. `runs\<日期>\receipt.json` 新增字段：`p1_segments`（每段的退出码/耗时/`step_changes`/
   推送结果与服务器前后条数）、`p1_concurrency`、`p1_finished`、`p1_pending`、
   `p1_stopped`、`p1_budget`、`cleanup_errors`；`steps.p1` 变成**最后一段**的退出码。
5. 一次运行可能跨到次日 06:10 之后 → 次日那轮拿不到锁会 exit 75，并在
   `data\runner-skipped.jsonl` 留一条告警（合并 cc-bot-notifier 后进飞书）。
6. `deploy\windows_collector.py` 之外的 20 个文件带来的变化见 20260920e / 20260920d 的
   DEPLOY-NOTES（1124 家、缺口报告、分页修复、P0 解码修复等）。

## 3. 部署步骤（需站长明确批准后由执行者做）

1. **空闲判定**（只读）：`runs\<今日>\receipt.json` 已 `completed_at`、无
   `windows_collector`/`p1_pipeline`/`lark_sync` 进程、`data\lark-sync\status.json` 非
   running、计划任务 `State=Ready`，且**距次日 06:10 有充足余量**。
2. **备份**：`robocopy` 只备 `deploy` 与 `qiuzhao`（命令见 `PROD-BACKUP-MANIFEST.txt`
   末尾，退出码 ≤7 为成功），**不要**整目录 robocopy（`recovery\` 约 3.4GB）。
3. **前提核对**：按 `PROD-BACKUP-MANIFEST.txt` 的 PRE-DEPLOY 列逐条比对现役 sha256
   （21 行，已由本任务在精灵上只读实测，并与 20260920a 的 SHA256SUMS / 20260920e 的
   PRE-DEPLOY 列交叉核对，零漂移；实测不同 → 停，记差异并当漂移处理）。
4. **传输**：21 个文件分片 base64（每片 ≤1300 字符）→ `C:\mcp-suite-deploy-20260920f\`，
   逐文件 `Get-FileHash` 与 `SHA256SUMS.txt` 比对后才覆盖。
5. **覆盖 21 个路径**（1 个新增；不删任何文件、不碰 `data\`/`runs\`/`.venv`/飞书/阿里云）。
   覆盖后 21/21 哈希与清单一致；再与备份全树比对，预期差异恰好 = 20 覆盖 + 1 新增。
6. **导入自检**（正式 venv，cwd=`C:\mcp-suite-collector`）：`py_compile` 全通过、
   `IMPORT_OK 1124 1124`、`LOCK True`、
   `P1_SEGMENT_SECONDS=5400 P1_SEGMENT_STEP_LIMIT=6600 P1_TOTAL_BUDGET_SECONDS=72000`、
   `P1_WORKERS=16 P1_PLATFORM_WORKERS=4`、`steps_for()['p1']` 带
   `--workers 16 --platform-workers 4 --max-run-seconds 5400`、
   `portable_runtime.CHILD_TEXT['errors']=='replace'`。
7. **不得**重启服务、改计划任务、手动补跑；首次实测 = 次日 06:10。

## 4. 回滚

按 `PROD-BACKUP-MANIFEST.txt`：20 个文件从 `C:\mcp-suite-backup-<时间戳>\` 恢复，
**删除唯一新增的 `qiuzhao\collector\collection_gap.py`**；恢复后确认
`p1_pipeline.py` 回到 `093b237e…`、`deploy\windows_collector.py` 回到 `9eaf97cc…`
（= 20260920e 的分段前版本，仍是「跑到 18000s 优雅收尾」的 P0 形态）。
回滚后仍是 1069 家现役集合 + P0 热修，次日照常能跑。

## 5. 验证（详见 `pipeline-watch/RECEIPT-segmented-publish.md`）

* 单测：新增 `tests/test_segmented_publish.py` **18 条**；`pytest tests/` =
  **3 failed / 741 passed / 55 skipped**，失败清单与基线 `fix/p0-typeerror-20260920`
  **逐条相同、无新增**（3 条既有失败；偶发 `test_codes_kind` 单独统计为基线 3/15 =
  本分支 3/15，与本次改动无关）。
* 等价目录自检（Mac，配精灵现役 `v4_fields.py` = `f74e6ab3…`）：
  `IMPORT_OK 1124 1124`、`LOCK True`、`CHILD_TEXT errors=replace`、
  `P1_SEGMENT_SECONDS 5400 / STEP_LIMIT 6600 / BUDGET 72000 / WORKERS 16 / PLATFORM 4`。
* 精灵实测（**只在 `C:\mcp-suite-seg-test` / `C:\mcp-suite-seg-test2` 两个临时目录**，
  正式目录全程只读、未推真实服务器、未调飞书、未动计划任务、未终止任何进程）。
  被验证字节自证：临时树 `deploy\windows_collector.py` sha256 =
  **`4db95ba3a953adea0b9c79255080f706fdb10b0dd5197313416b4854076717c5`**
  = 本包同名文件，mtime 13:40:29；下列各轮的 `p1-runs` 创建时间都晚于它。
  结果摘要：
  1. **多段 + 每段落袋 + 断点续跑**（3 家 × campus、`--workers 1`、段长临时 20s）：
     **3 段，退出码 2/2/0，pending 2→1→0，3 次推送**（94,486→94,487→94,488→94,489，
     段 2/3 走的是 **CAS 冲突 → 三方 rebase**）；整个运行只有 **1 个 `p1-runs` 目录、
     3 个 `validated.json`** → 续跑没有重复采集。
  2. **16 路并发**（6 家 × 3 scope）：18 个单元全部 success+complete，一段跑完即跳出，
     发布 94,486→**94,873**（+387），`p1.log` 里 `Errno 36` / `UnicodeDecodeError` /
     Traceback 均为 **0**。
  3. **完整链**（basic→tencent→p1→normalize→发布，1849s）：basic 返回 2（部分成功）仍
     正常完成发布 94,486→94,908，`error=null`、无 TypeError。
  4. **taskkill 路径**：真实 `taskkill.exe` 终止真实子进程 → `stop_tree` 不抛、
     GBK 解成 U+FFFD、`tree_termination_confirmed=true`；再把某段 `step()` 限时压到 25s
     强制 124 → 收据 `step_changes.p1={"exit":124,"result":"kept"}`、
     `cleanup_errors` 记录完整清理报告、**checkpoint 与 staging 都保留**、无 TypeError、
     仍然推送。9-20 缺的就是这条路径。
  5. **运行器锁冲突**：真实产生一条 `data\runner-skipped.jsonl`（exit 75、中文正文、
     `notified` 写明需合并 `feat/cc-bot-notifier`）。
