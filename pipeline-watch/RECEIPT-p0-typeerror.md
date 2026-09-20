# 收据 · P0 2026-09-20 日更崩溃(`TypeError: 'NoneType' object is not subscriptable`)

分支 `fix/p0-typeerror-20260920`(worktree `/Users/maxzhl/Projects/mcp-suite-p0b`,起点
`feat/gap-report` 3468074a)。**未部署、未覆盖精灵正式目录、未碰阿里云、未写飞书、
未读取/打印任何令牌、未 push、未合并 main、未终止任何进程。**
SSH 只做只读诊断(读 receipt/日志/哈希/计划任务 XML + 一次无副作用的最小复现,
用不存在的 PID 999999 调 taskkill,不涉及任何真实进程)。

结论:**根因是 `qiuzhao\collector\portable_runtime.py:41` 对 `subprocess.run(...)`
返回的 `result.stderr` 取下标,而该值在精灵上确实会是 `None`**;
触发条件是外层给 p1 的限时(18100s)比 p1 自己的 5 小时上限只多 100 秒,
11:43:31 用 taskkill 收尾时 taskkill 的 GBK 中文输出把 Windows 读取线程打死。
修法见 §3,证据见 §1/§2。

---

## 1. 根因(确切行号 + 触发条件)

### 1.1 致命行

**`qiuzhao\collector\portable_runtime.py`(精灵现役/分支起点版本)第 36-41 行**:

```python
34:    try:
35:        if WINDOWS:
36:            result = subprocess.run(
37:                [os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'taskkill.exe'),
38:                 '/PID', str(process.pid), '/T', '/F'], capture_output=True, text=True,
39:                check=False, timeout=30)
40:            report.update(taskkill_exit_code=result.returncode,
41:                          taskkill_stdout=result.stdout[-1000:], taskkill_stderr=result.stderr[-1000:])
42:            report['tree_termination_confirmed'] = result.returncode == 0
```

(行号以 `git show HEAD:…` 为准:**`result.stderr[-1000:]` 在第 41 行**,
`result.stdout[-1000:]` 在第 41 行同一行前半;修复前该文件共 63 行。)

被调用的位置:**`deploy\windows_collector.py:46-52` 的 `step()`**

```python
49:        try:return child.wait(timeout=timeout)
50:        except subprocess.TimeoutExpired:
51:            stop_tree(child)          # ← 这里没有 try/except,异常直接冒泡
52:            return 124
```

以及 `qiuzhao\collector\p1_pipeline.py:618-629` 的 `collect_process()`
(`cleanup = stop_tree(process, strict=False)`,**有** try/except,所以只坏一个单元)。

### 1.2 触发条件(四个条件同时成立)

1. **进程真的还活着** → 走 `taskkill` 分支(若 `process.poll() is not None` 会先返回报告);
2. **在 Windows 上**(POSIX 分支用 `os.killpg`,不碰子进程文本)-> 只有 Windows 用
   `subprocess._readerthread` 读管道;
3. **taskkill 输出非 UTF-8**:中文 Windows 的 taskkill 用控制台代码页(GBK)输出
   —— 成功是「成功: 已终止 PID … 的进程。」(首字节 `0xb3`),失败是「错误: 没有找到进程 …」
   (首字节 `0xb4`);而采集链用 **`-X utf8`** 启动(计划任务 XML 已核:
   `<Arguments>-X utf8 C:\mcp-suite-collector\deploy\windows_collector.py</Arguments>`),
   `text=True` 于是按 UTF-8 解码 → 解码异常在读取线程里抛出;
4. **读线程死了以后 CPython 会返回 `None`**:CPython 3.12 Windows 版 `_communicate` 结尾是
   `stdout = stdout[0] if stdout else None` / `stderr = stderr[0] if stderr else None`
   (本机 3.12.13 源码 `subprocess.py:1647-1649`;精灵为 3.12.2)。
   `buffer.append(fh.read())` 没跑成 → 缓冲仍是 `[]` → **`result.stderr is None`**。

于是 `result.stderr[-1000:]` → `TypeError: 'NoneType' object is not subscriptable`。

### 1.3 复现(① 精灵实机,② 直接读现场)

**① 精灵实机最小复现**(只读,不涉及真实进程;PID 999999 不存在):

```
ssh … "C:\mcp-suite-collector\.venv\Scripts\python.exe -X utf8 -c \"…\""   # 实测输出
utf8_mode 1 ver 3.12.2 (tags/v3.12.2:6abddd9, Feb  6 2024, 21:26:36) [MSC v.1937 64 bit (AMD64)]
rc 128
STDOUT ''
STDERR None                      ← 正是 None,致命行必然 TypeError
Exception in thread Thread-2 (_readerthread):
  File "D:\python3.12.2\Lib\threading.py", line 1073, in _bootstrap_inner
  File "D:\python3.12.2\Lib\subprocess.py", line 1597, in _readerthread
    buffer.append(fh.read())
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb4 in position 0: invalid start byte
```

**② 同源故障当天已发生 9 次**(p1 内部,被 `except Exception` 收敛):
`p1.log` 里 9 条 `UnicodeDecodeError … byte 0xb3 in position 0`(第 32/50/65/129/178/210/
230/262/280 行起的 Traceback;`0xb3` = taskkill **成功**终止的 GBK 文案,和 ① 的「找不到进程」
`0xb4` 正好互补),对应 `runs\20260920\data\p1-runs\20260920T064151\**\timeout-cleanup.json`
里 **18 处**(9 个单元 × `timeout-cleanup.json` + `validated.json` 各一份):

```json
{"pid": 29332, "cleanup_error": "TypeError: 'NoneType' object is not subscriptable",
 "process_terminated": true}
```

### 1.4 为什么"当天零发布"(时间线,全部实测)

| 时刻 | 事实 | 证据 |
|---|---|---|
| 06:10:01 | 计划任务起跑 | `receipt.started_at` |
| 06:12 | 拉生产快照 `jobs.before.json` 358,682,591 B | 文件 mtime/大小 |
| 06:40-06:41 | basic(exit 2:added 634/updated 62491/removed 10)与 tencent(exit 0)结束 | `basic.log`/`tencent.log`/`step_changes` |
| **06:41:51** | p1 起跑 | run 目录名 `p1-runs\20260920T064151`(UTC 22:41:51 = +08 06:41:51) |
| **11:41:51** | p1 自己的 `--max-run-seconds 18000` 到期(到期后只收尾,不再开新单元) | 参数 + 起始时刻 |
| **11:43:31** | 外层 p1 步骤限时 **18100s** 触发 → `step()` → `stop_tree` → TypeError | `receipt.completed_at = 11:43:31.812050` = 06:41:51 + 18100s |
| 11:43 | 回滚:`data\jobs.json` ← `p1.before.json`(两文件都是 367,055,908 B),`reset_p1` 删 `p1-status.json`/`p1-checkpoints` | 目录清单 + 大小 |
| 11:43 | `validate-and-publish` **一步未走**:receipt 无 `total_jobs`、无 `publication`、无 `p1` 键 | `receipt.json` |

`receipt.json` 里 `steps={"basic":2,"tencent":0}`(无 p1 键)= 异常发生在
`state['steps'][name]=step(...)` 这一次调用内部;`p1.before.json` 仍留在 run 目录
= 走了内层 `except`(它只在异常路径跳过 `pre_step.unlink()`),两者互相印证。

## 2. 当天丢了什么(精确清单)

生产库 `data\jobs.json` 最后成功发布 = **2026-09-19 07:02,94,486 行**;9-20 零发布。

| 阶段 | 已做、未发布的成果 | 依据 |
|---|---|---|
| basic | **新增 634** / 更新(刷新)62,491 / 标记下架 10;staging 95,120 行 | `receipt.step_changes.basic` |
| tencent | exit 0,added/updated/marked_removed 全 0(无净变化) | `receipt.step_changes.tencent` |
| p1 | **958 单元**(success/complete 744、partial 84、blocked 130)、**828 次本地 CAS 发布**、跨单元共 **44,967** 条岗位;合并后 staging **95,120 → 114,739 行**(新增 **19,619** / 更新 **13,310** / 移除 432) | `p1-runs\20260920T064151\status.json` 的 `results`/`publications` 逐条求和 |
| **线上可见影响** | 库里少 **20,253 条新岗位**(634 + 19,619),9-20 用户侧零更新;`data\jobs.json` 仍停在 9-19 07:02 | 精灵 `data\` 清单 |

**可打捞材料(未被删除,采集不必重跑)**:
`runs\20260920\data\p1-runs\20260920T064151\`(958 个单元的 `validated.json`/`result.json`、
`status.json`、`batches\<ns>\jobs.before.json.gz` 63,150,023 B = p1 开跑前快照)
与 `runs\20260920\data\jobs.json`(= `p1.before.json`,basic+tencent 之后的状态)。
打捞的坑:`p1-status.json`/`p1-checkpoints` 已被 `reset_p1` 删除,直接新起 p1 会**重新采集**;
要"不重采只补发布"需人工恢复该 run 的 checkpoint 并把单元 `published` 置回 false 再
`--resume --run-dir <该目录>` —— 属站长决策,本次未执行、未改动任何现场文件。

## 3. 修法

### 3.1 ① `UnicodeDecodeError` 根治(所有读子进程输出的地方)

| 文件 | 位置 | 改法 |
|---|---|---|
| `qiuzhao\collector\portable_runtime.py` | `stop_tree` 的 Windows 分支 | 新增 `CHILD_TEXT={'text':True,'encoding':'utf-8','errors':'replace'}` 与 `child_output(command)`:内部 `subprocess.run(..., **CHILD_TEXT)`,返回 `{'exit_code','stdout','stderr'[, 'error']}`,**读线程不可能因乱码而死** |
| `qiuzhao\collector\auto_collect.py` | basic(1800s)/tencent(600s)两处 `subprocess.run` | 加 `encoding="utf-8", errors="replace"` |
| `qiuzhao\collector\lark_sync_daemon.py` | `source_hash()` 的 ssh | 加 `encoding='utf-8',errors='replace'` |
| `qiuzhao\collector\sync_lark_multivalue.py` | `lark-cli` 调用 | 加 `errors='replace'` |
| `qiuzhao\collector\p1_sources_11_20.py` | 滴滴 `openssl verify` | 加 `encoding='utf-8',errors='replace'` |

`deploy\windows_collector.py` 的两处子进程输出本来就是二进制 + `decode('utf-8',errors='replace')`
(`pull`/`publish_snapshot`),无需改;全仓 AST 扫描后已无严格文本解码的调用点。

### 3.2 ② 可能为 `None` 的返回值收敛(绝不让它冒泡终止整段)

- `portable_runtime.child_output()`:`(result.stdout or '')[-1000:]` / `(result.stderr or '')[-1000:]`
  —— 即使将来某种实现仍返回 `None` 也不会下标失败;命令起不来/超时 → `exit_code=None` +
  `error`,不再抛出。`stop_tree` 用 `output['exit_code'] == 0` 判定 `tree_termination_confirmed`;
  **strict 语义保持不变**:确认不了终止照样 `RuntimeError`(不能让活写者继续写共享库)。
- `p1_pipeline.collect_process()`:部分 checkpoint 的 `checkpoint['coverage']` 改为类型校验,
  取不到 → `blocked('… partial checkpoint rejected: partial checkpoint carries no coverage
  mapping (NoneType) …')`,**把原因写进该单元 errors**(原来静默 `pass`,看不到为什么)。
- `p1_pipeline.any_validated()/is_full_success()/run()` 的收尾判定:容忍 `None`/非 dict 的
  coverage,保证**收尾阶段一条脏记录不会把整轮判成 exit 1(整段回滚)**。
- `auto_collect` 的 `result.stderr[-500:]`、`lark_sync_daemon` 的 `result.stdout.split()`、
  `sync_lark_multivalue` 的 `proc.stderr[:2000]`/`json.loads(proc.stdout)` 全部加 `or ''`/结构化错误。

### 3.3 ③ `receipt.json` 落完整 traceback + 让"跑到 5 小时上限"正常收尾

- **`error_traceback`**:`deploy\windows_collector.py` 外层 `except` 追加
  `state['error_traceback']=traceback.format_exc()` 与 `state['error_step']=state.get('stage')`
  (`error` 仍保留 500 字摘要)。这次就是因为只存消息才要二次排查。
- **p1 限时 18100s → 21600s**,并把算术写成常量 + `steps_for()`:

  ```python
  P1_MAX_RUN_SECONDS=18000; P1_SCOPE_TIMEOUT=600; P1_FINALIZE_BUDGET=3600
  P1_STEP_LIMIT=P1_MAX_RUN_SECONDS+P1_FINALIZE_BUDGET    # 21600
  ```
  依据:p1 只在**单元之间**检查 deadline,一个已提交的单元还能再跑最多
  `--scope-timeout 600s`(`run_unit` 用 `min(timeout, max(1, deadline-now))` 下发),
  之后还要合并、写 status/checkpoint、生成缺口报告。18100s = deadline + 100s
  **必然**在看门狗窗口里被杀;21600s 留 3600s 收尾余量。
- **deadline 仍返回 0/2**:p1 到期时 `run_unit`/`run_chain` 返回 `'deadline'`(`stop_submitting`),
  走完收尾后按契约返回 **2**(有已校验单元)→ `windows_collector` 的 `steps[name] in (0,2)`
  分支保留 staging 输出 → 照常 `validate-and-publish` → **已采成果必发布**。
  只有真·超时(>21600s,说明 p1 卡死)才走 124 + 回滚。

## 4. 单测

新增 `tests\test_p0_typeerror_20260920.py`(10 条)+ `tests\test_collector_partial_keep.py`
追加 3 条 + 改写 `tests\test_collector_next_integration.py` 1 条(原断言源码字面量
`'--scope-timeout','600'`,改为断言 `steps_for()` 的**生效值**与看门狗不变量,意图不变)。

| 单测 | 覆盖 |
|---|---|
| `test_child_output_replaces_undecodable_bytes` | 真子进程输出 GBK → 不再抛,降级成 U+FFFD |
| `test_child_output_never_returns_none_streams` | `stdout/stderr=None` → 收敛成 `''`(致命行回归) |
| `test_child_output_reports_an_unrunnable_command` | 命令起不来 → 记 `error`,不抛 |
| `test_stop_tree_windows_branch_survives_gbk_taskkill_output` | **Windows 分支 + GBK taskkill** 端到端(注入假 taskkill) |
| `test_stop_tree_windows_branch_survives_none_taskkill_output` | Windows 语义下 `None` 管道 |
| `test_stop_tree_still_refuses_unconfirmed_tree_termination` | 修正后 strict 契约未被削弱(仍抛) |
| `test_p1_collect_process_records_why_a_partial_checkpoint_was_rejected` | 取不到 coverage → 该单元失败 + 记原因 |
| `test_p1_deadline_run_exits_2_and_publishes_what_it_collected` | **deadline 到达 + 已有成功单元 → 退出码 2 + 已发布 + status/缺口报告照写** |
| `test_auto_collect_missing_stderr_still_reports_the_exit_code` | `stderr=None` 不再把真退出码顶掉 |
| `test_source_hash_rejects_a_missing_hash_line` | `stdout=None` → 既有校验错误而非 AttributeError |
| `test_windows_collector_p1_watchdog_outlasts_p1_finalisation` | 看门狗 > deadline + scope drain(18100 那个 bug 的不变量) |
| `test_windows_collector_publishes_when_p1_hits_its_deadline` | 日更链:p1=2 → 保留 + 发布 + checkpoint 不删 + 无 error |
| `test_windows_collector_receipt_records_the_full_traceback` | `error_traceback`/`error_step` 落盘 |

**A/B(证明测试真的抓得住这个 bug)**:把新测试文件放进 `git archive HEAD` 的干净树里跑,
**10 条里 9 条失败**(`test_child_output_*` 3 条、`stop_tree` 3 条、`collect_process` 1 条、
`auto_collect` 1 条、`source_hash` 1 条;剩下 1 条是 deadline 契约测试,两边都应通过);
在修复后的树上 **10 条全过**。

**全量回归**:`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/`
→ **3 failed / 723 passed / 55 skipped**,失败清单 =
`test_core::test_role_cohort_and_campaign_title_bases`、
`test_p1_pipeline::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`、
`test_schema::test_enum_check_fails_when_data_drifts`,
与 `feat/gap-report` 基线**逐条相同、新增失败 0**(实测:干净 HEAD 树跑出的失败清单同样是这 3 条)。

## 5. 部署与回滚

部署件 `pipeline-watch/deploy-artifacts/20260920e/`:**21 个运行时文件**(20 覆盖 + 1 新增)+
`SHA256SUMS.txt`(`shasum -a 256 -c` **21/21 OK**)+ `PROD-BACKUP-MANIFEST.txt`
(前提 = 精灵现役 `20260920a`,21 行 PRE-DEPLOY 哈希**本任务全部在精灵上只读实测过**,
与 20260920d 清单逐条一致、零漂移)+ `DEPLOY-NOTES.md`。

- **累积性**:e = 20260920d(collector-next-6 + gap-report)的 16 个文件**逐字节相同**的 14 个
  + 本次再改的 `p1_pipeline.py`/`windows_collector.py` + 5 个此前任何包都没带过的文件;
  14 个同名文件与 d 的 sha256 已逐个比对相同,可视为「a → e 一步到位」。
- **顺序**:`20260920a`(现役)→ `20260920e`。`20260919g/h/i`、`20260920c`、`20260920d`
  **一律不要再部署**。
- **部署前置**(需站长明确说"上线"):空闲判定 → `robocopy` 备份 `deploy`+`qiuzhao`
  → 21 行前提哈希核对 → 分片 base64 传输 + 逐文件 `Get-FileHash` → 覆盖 21 路径
  → `py_compile` + `IMPORT_OK 1124 1124` + `LOCK True` + `P1_STEP_LIMIT==21600`;
  不重启服务、不改计划任务、不手动补跑。
  (部署前已在 Mac 的等价目录里用**精灵现役 `v4_fields.py`** 做过导入闭环自检,见 DEPLOY-NOTES §5.1。)
- **回滚**:20 个文件从备份恢复 + 删除唯一新增的 `qiuzhao\collector\collection_gap.py`;
  恢复后必须确认 `p1_pipeline.py` 回到 `093b237e…`(`_publish_thread_lock` 在位)、
  `windows_collector.py` 回到 `9eaf97cc…`。
- **部署后首次实测观察项(次日 06:10)**:`receipt.json` 里 `steps` **必须有 p1 键且 ∈{0,2}**、
  `step_changes.p1.result` 不再是 `rolled_back`、无 `error`/`error_traceback`;
  `p1.log` 0 次 `UnicodeDecodeError`、`timeout-cleanup.json` 0 次 `TypeError`;
  `collection-gap.json/.md` 生成;若 p1 再次撞 5 小时上限,仍应照常发布并留下
  `run_finished=false` + `pending` 供次日续跑。

## 6. 提交与产物

- 分支 `fix/p0-typeerror-20260920`,worktree `/Users/maxzhl/Projects/mcp-suite-p0b`(本机盘)。
- 改动文件:`qiuzhao/collector/{portable_runtime,p1_pipeline,auto_collect,lark_sync_daemon,sync_lark_multivalue,p1_sources_11_20}.py`、
  `deploy/windows_collector.py`、`tests/{test_p0_typeerror_20260920.py(新),test_collector_partial_keep.py,test_collector_next_integration.py}`、
  `pipeline-watch/deploy-artifacts/20260920e/`、本收据。
- **未部署、未 push、未合并 main、未覆盖精灵正式目录、未碰阿里云/飞书/令牌、未终止任何进程。**
