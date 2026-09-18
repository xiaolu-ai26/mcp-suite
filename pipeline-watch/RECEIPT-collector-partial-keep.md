# RECEIPT: collector-partial-keep(修复"每天在跑、但产出几乎全被回滚")

分支:`fix/collector-partial-keep`(从 main HEAD 59dca7b 开出,本地 commit,未 push、未合并)
日期:2026-09-18 执行:Kimi(执行者) 范围:A 诊断补全 / B 最小修复 / C 测试 / D 精灵离线验证。**未部署**:未覆盖精灵正式代码、未触发计划任务、未碰阿里云服务器、未调飞书。

---

## A. 诊断结论(只读,证据来自精灵 `C:\mcp-suite-collector\runs\2026091x\`)

### A1. 9-17 basic 各来源状态(`runs\20260917\data\source_state.json` / `alerts.json` / `collector.log`)

| 来源 | status | complete | 条数 | 说明 |
|---|---|---|---|---|
| postal | success | true | 2647(源记录 2650，排除 3 条非岗位） | 27 页全部抓完 |
| chnenergy | failed | — | — | `<urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] ...>`,06:30 详情抓到 126/422 时连接被掐，瞬时网络错误，非数据问题 |
| telecom | success | false（设计如此） | 10 | 最新校园页+历史已导入岗 |
| boc | success | true | 14 | |
| ccb | success | true | 39(=expected) | |
| guopin | failed（整体被拒） | — | 5/6 专场成功 | 见 A2 |

### A2. 国聘 errors 原文与专场明细

`alerts.json` 全文只有三条:chnenergy 的 SSL 错、**`guopin:cgnpc` —— "Current official directory no longer advertises this 2027 campaign"**(06:36:36)、以及 06:42:14 整体拒收的 `guopin —— "source did not return a validated successful/partial snapshot"`。

`collector.log` 逐页记录证明 **6 个专场里 5 个完整抓完**(全部 `page x/y` 到尾页、无残缺报错):

- zgyd 中国移动：约 45 个公司分区、逐页抓完（06:32:47–06:35:58)
- ceec 中国能建：`all` 7 页 × 100，共 654 条源记录（06:36:07–06:36:36)
- **cgnpc 中国广核：失败**，官方广告目录里已无其 2027 专场横幅（专场下线/未续，属专场级事件）
- cam2027 机械总院：81 条（1 页）
- casicjob 航天科工：`all` 13 页，1232 条（06:36:53–06:37:51)
- zglt 中国联通：约 45 个公司分区逐页抓完（06:38:08–06:42:14)

`guopin_excluded_records.json` 仅 14 条，全部是 `nature_cn=社招/社会招聘` 的正常过滤，无异常。

**结论:cgnpc 的 error 是个别专场事件（官方目录不再展示该 2027 专场），不是全局性列表残缺；其余 5 个专场 success+complete，符合"部分成功接收"条件。** 整体被拒的根因是 `guopin.py` 把任一专场失败标成 `partial_failure`,而 `run.py:233` 校验门只接受 `success/partial`。

附带发现：`run.py` 的 catch 用一行 error **覆盖**了 guopin 已记录好的 per-campaign state，导致 `source_state.json` 里看不到专场细节（本次只能从 collector.log 还原）。修复中已保留原 state 细节。

### A3. p1 的判定与原子性

`p1_pipeline.py:455`:`status['success'] = 所有 company/scope 的 coverage.status=='success' 且 complete==True`，末尾 `return 0 if success else 1`。p1 内部**已是按 company/scope 原子合并**:`run()` 逐 scope 调 `publish()`(带 p1-publish.lock、写前备份、CAS 复查、原子替换）,`merge_records` 只对 `complete+success` 的 scope 做"缺席即下线";blocked 的 scope 直接跳过、旧记录保留。9-17 多数公司 success、少数 partial/blocked(SSLError 14、HTTP 400 9、ReadTimeout 5),5 小时的产出已写进 stage 的 jobs.json，但退出码 1 → 外层 `windows_collector.py` 整段回滚 + `reset_p1`。

### A4. 9-14 的 49746 条是怎么入库的，回滚从哪天开始吃数据

- 9-14 receipt:`steps={basic:0, tencent:0, p1:1, normalize:0}` → **basic 当天全成功，49746 条是日常流程正常刷新的 reviewed_at**;p1 退出 1 被回滚。
- 9-15 receipt:`{basic:1, tencent:1, p1:1}` → "all collection stages failed"，什么都没发布。
- 9-16 receipt:`{basic:1, tencent:0, p1:1}` → 只发布了 tencent 的增量（+2 条）。
- 9-17 同 9-16。

**结论:9-14 是日常流程入库（非一次性全量）;9-15 起 basic 天天退出 1(cgnpc 专场下线 + chnenergy 偶发 SSL),basic 与 p1 的产出天天被整段回滚——回滚逻辑从迁到精灵后的第一次来源失败（9-15）起就一直在吃数据。**

---

## B. 最小修复(每个文件一句话 + 关键 diff)

退出码契约：**0=全部成功；2=部分成功（至少一个来源/scope 通过校验并已合并，且有失败）;1=致命（没有任何可信产出）**。按来源原子合并、校验门、`removed` 判定一律未放松。

### B1. `qiuzhao/collector/run.py`
`run()` 从"有 alert 就返回 1"改为返回 0/1/2；被回退的来源在 `source_state.json` 里保留其自报的明细（如 guopin campaigns)，不再被一行 error 覆盖。

```python
# 通过校验门并完成合并后:
                write_json(self.out/'jobs.json',list(merged.values()))
                succeeded.append(name)
            except Exception as error:
                merged=source_before
                self.alert(name,error)
                prior=self.states.get(name) or {}
                self.states[name]={**prior,'status':'failed','checked_at':now(),'error':str(error)[:300]}
# 末尾:
        if not self.alerts: return 0
        return 2 if succeeded else 1
# main(): raise SystemExit(Collector(...).run(...))
```

### B2. `qiuzhao/collector/guopin.py`
有专场 success 但整体不全时，整体状态从 `partial_failure` 改为 `partial`（失败专场明细仍在 `campaigns[].error` 和 alerts 里；全部专场失败仍 `partial_failure` 被拒）。

```python
    overall='success' if complete else ('partial' if any(x['status']=='success' for x in states.values()) else 'partial_failure')
```

接收侧（run.py）未改：`status='partial'` 过校验门；guopin 的"缺席即下线"本来就只取 `campaigns` 里 `success+complete` 且有行的专场（`complete_groups`),cgnpc 旧记录原样保留。

### B3. `qiuzhao/collector/p1_pipeline.py`
新增 `any_validated(status)`，两处返回改为 0/1/2。注意"通过校验并已合并"的口径:`success`(complete 快照，可能增/改/下线）或**带行的 partial**(`available_job_count`/`pending_count` > 0);**空 partial 与 blocked 不算**——这是既有测试 `test_p1_timeout_cleanup_failure_records_failure_and_continues_scope`(timeout blocked + 空 partial → 必须返回 1）钉死的语义，第一版"status 非 blocked 即算"被该测试抓出回归后收紧。

```python
def any_validated(status):
    for entry in status.get('results', {}).values():
        coverage = entry.get('coverage', {})
        if coverage.get('status') == 'success':
            return True
        if (coverage.get('status') == 'partial'
                and (coverage.get('available_job_count') or coverage.get('pending_count'))):
            return True
    return False
# 预算暂停处: return 2 if any_validated(status) else 1
# 末尾: 0 if success else (2 if any_validated(status) else 1)
```

### B4. `deploy/windows_collector.py`
退出码 2 保留阶段产出（不回滚、p1 不 reset)，只有 1/124/异常回滚；"all collection stages failed" 改为"没有任何阶段是 0 或 2";receipt 新增 `step_changes`，逐阶段记录新增/更新/标记下线/消失条数（新增 `diff_counts`，与 `preserve()` 同款流式指纹，全量 350MB 可承受）。

```python
                    if state['steps'][name] not in (0,2):
                        shutil.copyfile(pre_step,stage/'jobs.json')
                        if name=='p1':
                            reset_p1(stage)
                        state.setdefault('step_changes',{})[name]={'exit':state['steps'][name],'result':'rolled_back'}
                    else:
                        state.setdefault('step_changes',{})[name]=dict(
                            {'exit':state['steps'][name],'result':'ok' if state['steps'][name]==0 else 'partial'},
                            **diff_counts(pre_step,stage/'jobs.json'))
...
            if all(state['steps'][name] not in (0,2) for name in state['steps'] if name!='normalize'):raise ValueError('all collection stages failed; production retained')
```

`finished/success` 语义未动（全 0 才算 success)，部分成功当天 receipt 的 `steps` 会如实出现 `2`，主流程返回 1——与"部分但已发布"一致。

### B5. 旧调用方兼容性(检查结论，未改）

- `deploy/collector-daily.sh`(Linux 服务器 cron)：每步独立跑、**无回滚逻辑**，任何非 0 只写 `Partial failure` 告警并退出 → 退出码 2 天然走"告警但不回滚",STEPS 原样记录。兼容。
- `qiuzhao/collector/auto_collect.py::run_basic_collectors`：对非 0 只记日志返回 None，不做回滚；windows 日常链本来就以 `--skip-basic-collectors` 调它，不走这段。兼容。
- `deploy/windows_rebase.py` / `windows_recover_run.py`：只用 `p1_pipeline.atomic_json`，不消费退出码。兼容。

---

## C. 测试

新增 `tests/test_collector_partial_keep.py`(16 个用例，全过）:

- run.py：全成功→0 且六来源都进 jobs.json；一失败→2 且成功来源已合并、失败来源 state=failed；全失败→1；单来源失败→1；被拒来源保留 campaigns 明细；guopin partial→2 且"缺席即下线"只命中 complete 专场（zgyd 旧岗 removed、cgnpc 旧岗原样保留）。
- guopin.py(mock public_api):cgnpc 缺席→整体 `partial`、5 专场 success、alerts 记 `guopin:cgnpc`；六专场全灭→`partial_failure` 仍被拒。
- p1_pipeline:success+blocked→2；全 blocked→1；全 success→0；预算暂停但有已合并 scope→2。
- windows_collector（假 step 驱动 main 全流程）:全 0→发布且 step_changes 记 added；basic=2→保留并发布、result=partial;basic=1/tencent=2/p1=2→basic 回滚、tencent/p1 保留并发布、p1-checkpoints 与 p1-status.json 未被 reset；全灭→"all collection stages failed"、不发布。

基线对比(`git stash` 前后各跑 `pytest tests/`，按 FAILED/ERROR 排序 diff):

- 基线（main HEAD):**39 failed / 431 passed**（与任务书"11 failed/70 errors"口径不一致，以实测为准）
- 分支：失败清单与基线**逐行一致**(16 个新用例全过）
- 排雷记录：① 第一版 `any_validated` 曾造成 1 个真实回归（见 B3)，已修复并复测；② `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` 在某一轮全量中偶发失败，基线/分支另两轮均无它、单跑该文件 22 全过，属既有顺序依赖偶发，与本改动无关。

---

## D. 精灵零风险离线验证(不发布、不调飞书、不改计划任务）

方法:`C:\mcp-suite-partial-test\` 临时目录（robocopy 仅 `*.py` + 覆盖 4 个修复文件，certutil/shasum 双向 sha256 逐字节核对一致；正式目录 `C:\mcp-suite-collector` 未动）。`data\jobs.json` 用 `runs\20260917\jobs.before.json` 作基线，用正式 venv 的 python 以 `PYTHONPATH=临时目录` 跑 `python -m qiuzhao.collector.run --output-dir 临时data --source all --delay 2`(01:12–01:30，约 18 分钟）,stdout 落 `basic-test.log`，退出码落 `exit.txt`。**未发布到服务器、未触发飞书、未改计划任务。**

### D1. 退出码与总量

- **退出码 = 2**(`exit.txt`)——部分成功，符合新契约。
- summary:`job_count 92599`,`refreshed_jobs 1959`(telecom 14 + boc 14 + ccb 39 + guopin 1892),`added_jobs 368`（相对 9-17 基线的新 id),`alerts_count 6`。

### D2. 各来源结果(source_state.json；今晚网络比 9-17 早晨差，失败面更大，正好压测了契约）

| 来源 | 结果 | 处理 |
|---|---|---|
| postal | **failed**:`Postal pagination changed/incomplete: unique=2642, expected=2651`（抓取中列表变化） | **校验门正确拒收**，旧记录原样保留——证明校验没有放松 |
| chnenergy | failed:read timeout | 来源级回退 |
| telecom | success,14 条（比 9-17 多 4 条） | 已合并 |
| boc | success+complete,14 条 | 已合并 |
| ccb | success+complete,39 条 | 已合并 |
| guopin | **partial**：ceec 651 条、casicjob 1241 条 success+complete;zgyd(SSL EOF)、cam2027(timeout)、zglt（差 2 条 2578/2580）被拒；cgnpc 仍目录下线 | 两个 complete 专场已合并；失败专场旧记录全部原样保留 |

### D3. 合并正确性逐条核验（对临时 jobs.json 统计）

- 今日刷新的 guopin 记录：**ceec 651 + casicjob 1241 = 1892**；按 id 前缀 boc 14 / ccb 39 / telecom 14 / guopin 1892 = 1959 = refreshed_jobs。
- 今日标记 removed:**仅 ceec 4 条**（该 complete 专场里真实缺席）;"缺席即下线"没有命中任何失败专场。
- 失败专场旧记录全部未动（旧 reviewed_at):zgyd 1748、zglt 2580、cam2027 76、cgnpc 8，以及历史遗留专场（bqgy2027 406、bqzb2027 167 等）均原样保留。
- `source_state.json` 中 guopin 的 per-campaign 明细（campaigns[].status/error）完整保留——B1 的 state 保留改动生效。

### D4. 与修复前对照

同一输入（9-17 基线 + 今晚网络）在旧代码下：postal 分页校验失败 → alert → 退出 1 → **整个 basic 阶段（telecom/boc/ccb/guopin 两专场共 1959 条刷新 + 368 条新增）全部回滚**。修复后这些数据全部落库，且不合格的部分（postal 残缺列表、guopin 三失败专场）一条没进。

### D5. 临时目录清理（留给总控决定）

`C:\mcp-suite-partial-test\` 约占 700MB（含 350MB 基线副本 + 产出 + evidence)。精灵 C 盘余量约 70GB，不急；确认后可 `rmdir /s /q C:\mcp-suite-partial-test`。

---

## 给总控的部署步骤建议

1. **备份**:`robocopy C:\mcp-suite-collector\qiuzhao\collector C:\mcp-suite-backup-20260918\qiuzhao\collector run.py guopin.py p1_pipeline.py` + 备份 `deploy\windows_collector.py`（或直接整目录 robocopy 一份）。
2. **逐字节 sha256 核对**:Mac 侧 `shasum -a 256 <file>` 与精灵侧 `certutil -hashfile <file> SHA256` 对 4 个文件逐一比对后再覆盖。
3. **只覆盖 4 个文件**:`qiuzhao\collector\run.py`、`qiuzhao\collector\guopin.py`、`qiuzhao\collector\p1_pipeline.py`、`deploy\windows_collector.py`。不需要重启任何服务；计划任务次日 06:10 自然生效。
4. **首日观察**:06:10 后看 `runs\<日期>\receipt.json`:`steps` 里出现 `2`、`step_changes` 有逐阶段条数、`publication.published=true` 即符合预期；预期当天新增量级 = postal/国聘五专场/p1 通过校验公司的增量。
5. **回滚方法**:把备份的 4 个文件拷回即可；回滚后行为完全回到"非 0 即回滚"。被本修复保留入库的数据本身有完整证据链（evidence/ + source_state + step_changes),不需要数据层回滚；若确需数据回滚，服务器侧有每日 `jobs.json.bak.windows.*` 与 `runs\<日期>\jobs.before.json`。

## E. 可部署产物与部署步骤(修订版,20260918)

**为什么修订**:总控核实精灵正式目录 `deploy\windows_collector.py`(sha256 前16 `ea28c7b767a39391`,187 行,9-13 部署)不在 git 里,与 git main 的唯一差异是末尾飞书同步段——精灵版调 `qiuzhao.collector.lark_sync_daemon ... --apply`(`state['stage']='base-sync'`,`finished/success` 还要求 `sync_exit==0`);main/分支版是未部署的 `lark_sync_index` 镜像实现,精灵上没有 `lark_sync_index.py`,整文件拷上去会在同步段 ModuleNotFoundError。因此 `windows_collector.py` 必须用**移植版**(精灵正式版为底 + 仅套上分支 B4 的三处改动),**不能**用分支里的 `deploy/windows_collector.py`。`run.py`/`guopin.py`/`p1_pipeline.py` 精灵正式版与 main 逐字节一致,分支版可直接用。**本节取代上文《给总控的部署步骤建议》。**

### E1. 产物(`pipeline-watch/deploy-artifacts/20260918/`,已随本提交入库)

| 文件 | 来源 | sha256 前16 |
|---|---|---|
| `windows_collector.py` | **移植版** = 精灵正式版 + 分支 B4 三处改动 + 小修(diff_counts 异常降级) | `14e17785ccff51f9` |
| `run.py` | 分支 `fix/collector-partial-keep` | `5e94f91b770ef02b` |
| `guopin.py` | 分支 | `22e5f6ad0b66487b` |
| `p1_pipeline.py` | 分支 | `dc046e32f37d7482` |
| `windows_collector.prod-20260913.orig.py` | 精灵正式版原样备份(= 部署前回滚件) | `ea28c7b767a39391` |
| `SHA256SUMS.txt` | 以上五个文件的完整 sha256 | — |
| `PORT-DIFF.txt` | 精灵正式版 → 移植版的 unified diff,供总控逐行审 | — |

移植版 = 对精灵正式版逐字节副本 `git apply` 分支 commit `3bb0632` 中 `deploy/windows_collector.py` 的 diff(三处 hunk,全部落在第 178 行之前,与同步段无交集),随后叠加总控小修(见 E4)。`PORT-DIFF.txt` 可证:仅含 ① 新增 `diff_counts()`;② 退出码 2 保留产出 + `step_changes`;③ "all collection stages failed" 改为"没有任何阶段是 0 或 2";④ `diff_counts` 调用包进 try/except(小修)。末尾 `base-sync` 同步段与 `finished/success` 写法与精灵正式版逐字符一致(`lark_sync_daemon ... --apply`,无 `lark_sync_index`)。换行符风格已核对:精灵正式版与移植版均为 LF(精灵正式版本来就无 CRLF)。

### E2. 验证记录

- `python3 -m py_compile`:四个待部署文件全部通过(Mac)。
- 单元测试:`tests/test_collector_partial_keep.py` 中 4 个 windows_collector 用例以 importlib 按路径加载**移植版**模块再跑一遍(`--no-sync` + 假 step,不调真实同步),**4 passed**。
- 精灵临时目录 `C:\mcp-suite-partial-test\deploy\windows_collector.py`(分片 base64 传输,精灵侧 Get-FileHash 与 Mac 侧 shasum 逐字节一致;另补传了 import 依赖 `deploy\windows_rebase.py`):用正式 venv `Python 3.12.2` 以 `PYTHONPATH=C:\mcp-suite-partial-test` 执行 `py_compile` 与 `python -c "import deploy.windows_collector"` → `PY_COMPILE_OK` / `IMPORT_OK`,解析路径确认为临时目录内的移植版。**未运行 main,未触发发布/同步/计划任务,正式目录 `C:\mcp-suite-collector` 未动。**
- 连通性备注:runbook 中精灵地址 `192.168.1.52` 已过时(搬家换宽带),本次实测可用地址 `192.168.31.204`。

### E4. 小修记录(20260918,总控审查 `fix/collector-partial-keep`@`8936f72` 后)

**审查结论**:移植版通过,仅要求一处加固——`diff_counts` 是报告功能,出错不得中断采集。

**改动**(分支 `deploy/windows_collector.py` 与移植版 `deploy-artifacts/20260918/windows_collector.py` 两份逐字符一致地改):步骤循环内 `diff_counts(pre_step,stage/'jobs.json')` 调用包进 `try/except Exception`;失败时 `step_changes[name]` 仍记录 `exit` 与 `result`(`ok`/`partial`),另加 `'diff_error': type(e).__name__+': '+str(e)[:200]`,流程照常继续到发布。移植版其余内容(尤其末尾 `base-sync` 同步段)一个字符未动(`PORT-DIFF.txt` 已重生成可证)。

**验证**:

- 新增单测 `test_windows_collector_diff_counts_failure_is_reporting_only`(monkeypatch `diff_counts` 抛 `RuntimeError`):断言退出码 0、已发布(`publication` 在 receipt)、`step_changes.basic` 有 `exit=0`/`result='ok'`/`diff_error` 且无 `added`、阶段产出(`basic-new`)仍落库。对分支版与移植版(importlib 按路径加载)各跑一遍,**均通过**;`tests/test_collector_partial_keep.py` 全文件 **18 passed**。
- `SHA256SUMS.txt` 与 `PORT-DIFF.txt` 已重新生成;四个待部署文件 Mac 侧 `py_compile` 全部通过。移植版新 sha256:**`14e17785ccff51f94aea519bee1637582d974c6d65540ee6f379954b08c90c4a`**(14265 字节)。
- 移植版新文件已分片 base64(10 片 × 2000 字符,避开远端 cmd 8191 字符命令行上限)同步到精灵临时目录 `C:\mcp-suite-partial-test\deploy\windows_collector.py`:精灵侧 `Get-FileHash` SHA256 = `14E17785...C90C4A`、长度 14265,与 Mac 侧逐字节一致;正式 venv `Python 3.12.2` 以 `PYTHONPATH=C:\mcp-suite-partial-test` 执行 `py_compile` → `PY_COMPILE_OK`,`import deploy.windows_collector` → `IMPORT_OK`(解析路径确认为临时目录内移植版)。**未运行 main,未触发发布/同步/计划任务,未覆盖 `C:\mcp-suite-collector\` 下任何文件。**

### E3. 部署步骤(修订版)

1. **备份**:在精灵上把 `C:\mcp-suite-collector` 整目录 robocopy 一份到 `C:\mcp-suite-backup-<日期>\`(至少含 `deploy\windows_collector.py`、`qiuzhao\collector\run.py`、`guopin.py`、`p1_pipeline.py`)。其中 `deploy\windows_collector.py` 的备份应与 `deploy-artifacts/20260918/windows_collector.prod-20260913.orig.py` sha256 一致(`ea28c7b767a39391...`)——若不一致说明正式文件又被改过,**停下来找总控**。
2. **传输**:把 `deploy-artifacts/20260918/` 下四个待部署文件传到精灵临时位置(scp 不可用,用分片 base64,方法同 E2),精灵侧 `Get-FileHash` 与 `SHA256SUMS.txt` **逐字节核对通过后再覆盖**。
3. **只覆盖 4 个文件**:`qiuzhao\collector\run.py`、`qiuzhao\collector\guopin.py`、`qiuzhao\collector\p1_pipeline.py`(分支版)+ `deploy\windows_collector.py`(**用移植版 `deploy-artifacts/20260918/windows_collector.py`,不是分支 `deploy/windows_collector.py`**)。覆盖后再对这 4 个目标路径各做一次 sha256,与 `SHA256SUMS.txt` 比对留证。不需要重启任何服务;计划任务次日 06:10 自然生效。
4. **首日观察**:06:10 后看 `runs\<日期>\receipt.json`:`steps` 出现 `2`、`step_changes` 有逐阶段条数、`stage` 依次过 `validate-and-publish` → `base-sync`、`sync_exit==0`、`publication.published=true` 即符合预期。
5. **回滚方法**:`deploy\windows_collector.py` 用 `windows_collector.prod-20260913.orig.py`(或第 1 步的本地备份)拷回;其余三个文件用第 1 步备份拷回(它们与 main 逐字节一致,也可从 main 取)。回滚后行为完全回到"非 0 即回滚";被本修复保留入库的数据有完整证据链(evidence/ + source_state + step_changes),不需要数据层回滚,若确需可用服务器侧 `jobs.json.bak.windows.*` 与 `runs\<日期>\jobs.before.json`。

## 遗留问题与不确定点

1. **chnenergy 的 SSL UNEXPECTED_EOF** 是精灵出口到国家能源站点的偶发断连（9-17 抓到 126/422 时断）。本修复让它不再拖死其他来源，但该来源本身仍可能天天失败；建议后续加重试/断点，不在本次范围。
2. **cgnpc 专场下线是真实业务事件**:9-17 起官方目录已无其 2027 专场。若确认不再回归，应从 `CAMPAIGNS` 白名单移除（单独决策，本次未动）。cgnpc 旧岗位记录会原样留在库里，不会误标 removed。
3. **resume 语义**:同一 run 目录内 resume 时，记为 2 的步骤会重跑（2≠0),p1 靠 `--resume-latest` 续跑，属预期但会多花一次 basic 采集时间。
4. **auto_collect(tencent）步**未纳入 0/1/2 契约（任务范围外）；它退出非 0 仍整段回滚。
5. **p1 非 --apply(dry-run）调用**时退出码也可能为 2，但此时无实际合并；只有手工/测试走这条路，日常链总是 --apply。
6. 任务书称基线"11 failed / 70 errors"，实测为 39 failed / 0 error（两次全量一致），以实测为准；差异原因未深究（可能口径/环境不同）。
7. **D 验证夜新暴露的"接近完整但差几条"型失败**:postal(unique=2642/2651，抓取中列表变化）、guopin zglt(2578/2580）被校验门正确拒收。这类失败靠重试大概率能过，但 run.py 目前没有来源内重试；建议后续单独评估"来源级一次重试"，不在本次范围（本次刻意不放松任何校验）。

## F. 部署记录(20260918,Max 11:20 批准上线,执行者实测)

### F0. 部署前状态复核(只读)

- 精灵 `runs\20260918\receipt.json`(06:10 起跑的当日常规任务)在 13:00 只读核实:`completed_at=2026-09-18T12:50:45`,`steps={basic:1,tencent:0,p1:1,normalize:0}`,`total_jobs=92532`,`publication.published=true`,`sync_requested=true`,`sync_exit=0`。`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` 无返回(无 windows_collector.py/p1_pipeline/lark_sync 相关进程)。`data\lark-sync\status.json`:`status=success`,`finished_at=2026-09-18T04:50:45Z`(=12:50:45+08)。三个只读条件同时满足,判定当日跑批已结束,直接从第 2 步开始。
- 顺手核对当日飞书同步结果(部署前基线,非本次部署触发):`data\lark-sync\runs\20260918T120131523462\business-sync.json` → `changed=1231`,`finished=true`;`status.json` 显示 `last_attempt_at=2026-09-18T04:01:27Z`(=12:01:31+08 起)→`finished_at=2026-09-18T04:50:45Z`(=12:50:45+08),耗时约 49 分钟。较昨日同口径 `changed=92722` 下降两个数量级——这是昨晚"链接比较"修复上线后的首次实测,结果符合预期,判定通过。

### F1. 备份(第 2 步,过程有波折)

- 初次按任务书跑全目录 `robocopy C:\mcp-suite-collector C:\mcp-suite-backup-20260918 /E /XD .venv runs data` 后台执行 12 分钟仅拷贝 14 个文件。总控只读排查发现:上一位执行者(Kimi)断线前遗留的孤儿进程 PID 12872(12:53 启动)与本执行者本次启动的 PID 3208(13:01)两个 robocopy 同时写同一目标目录,互相锁文件、每次重试等 30 秒,导致几乎不推进。经 `Get-CimInstance Win32_Process -Filter "Name='robocopy.exe'"` 确认两个进程的 `CommandLine` 均为指向 `C:\mcp-suite-backup-20260918` 的 robocopy(非生产进程)后,`Stop-Process -Id 12872,3208 -Force` 终止;确认后 `robocopy.exe` 进程列表为空。
- 改为定向备份:`robocopy C:\mcp-suite-collector\deploy C:\mcp-suite-backup-20260918\deploy /E /R:2 /W:5`(exit=0)与 `robocopy C:\mcp-suite-collector\qiuzhao C:\mcp-suite-backup-20260918\qiuzhao /E /R:2 /W:5`(exit=1,均 ≤7,成功);`core`、`keys` 已在此前全目录 robocopy 里落地,未受影响。
- 备份内 4 个目标文件 sha256(`Get-FileHash`)与部署前哈希/`SHA256SUMS.txt` 回滚件核对:

| 文件 | 备份哈希 | 核对结果 |
|---|---|---|
| `qiuzhao\collector\run.py` | `11C8B59085DBD4079F3EB9122192763F4E307DC0645B87EC168F5129440C123F` | 前 8 位 `11c8b590`,与部署前一致 |
| `qiuzhao\collector\guopin.py` | `7E1FF1A6F68D42CFA5FA23167309B5CDC0D5003150BA67816153718EEDAE863D` | 前 8 位 `7e1ff1a6`,与部署前一致 |
| `qiuzhao\collector\p1_pipeline.py` | `505AA72559563D6B0A52CF557DDC488D1E83F06C569D43E5A4668F70168CC426` | 前 8 位 `505aa725`,与部署前一致 |
| `deploy\windows_collector.py` | `EA28C7B767A3939164237BFF3913F2B8D417ECE1CA1AEEBD4DA64D622BBEE2A9` | 与 `windows_collector.prod-20260913.orig.py` 完整 sha256 **逐字符一致** |

四项核对全部通过,进入第 3 步。

### F2. 传输(第 3 步)

- 4 个部署件用 `git show fix/collector-partial-keep:pipeline-watch/deploy-artifacts/20260918/<文件>` 取(主工作区保持 main,未切换),本地 `shasum -a 256` 与 `SHA256SUMS.txt` 先行核对一致。
- 传输方法:base64 分片(每片 1400 字节)+ `powershell -NoProfile -EncodedCommand`(UTF-16LE)逐片 `Add-Content` 写入精灵 `C:\mcp-suite-deploy-20260918\<文件>.b64`(run.py 22 片、guopin.py 14 片、p1_pipeline.py 30 片、windows_collector.py 14 片,共 80 片全部发送成功),最后 `[Convert]::FromBase64String` 解码写出二进制并删除临时 `.b64`。
- 精灵侧 `Get-FileHash` 结果与 `SHA256SUMS.txt` 逐字节比对:

| 文件 | 精灵侧哈希 | 长度(字节) | 结果 |
|---|---|---|---|
| `run.py` | `5E94F91B770EF02BFAD887E10BB6FAB3405D8B184A81B98DF9D14FE28C266B28` | 22709 | 一致 |
| `guopin.py` | `22E5F6AD0B66487BA7F6CCAEE041DA67C668D7ED98AEAA10408D7DC95A0ABF89` | 13739 | 一致 |
| `p1_pipeline.py` | `DC046E32F37D7482AC56222898D122EDB52D93D8B48FED4F3C5C2C67770FDB90` | 30959 | 一致 |
| `windows_collector.py` | `14E17785CCFF51F94AEA519BEE1637582D974C6D65540EE6F379954B08C90C4A` | 14265 | 一致 |

4/4 通过,进入第 4 步。

### F3. 覆盖(第 4 步)

- `Copy-Item -Force` 覆盖:`qiuzhao\collector\run.py`、`qiuzhao\collector\guopin.py`、`qiuzhao\collector\p1_pipeline.py`、`deploy\windows_collector.py`,仅这 4 个路径,未动 `.venv`/`data`/`runs`。
- 覆盖后对 4 个目标路径各重算一次 sha256,与 `SHA256SUMS.txt` 逐一比对:**4/4 MATCH=True**(与 F2 表中精灵侧哈希相同)。
- 编译/导入检查(cwd=`C:\mcp-suite-collector`,正式 venv `C:\mcp-suite-collector\.venv\Scripts\python.exe`):`python -m py_compile qiuzhao\collector\run.py qiuzhao\collector\guopin.py qiuzhao\collector\p1_pipeline.py deploy\windows_collector.py` → **exit=0**;`python -c "import deploy.windows_collector"` → 输出 `IMPORT_OK`,**exit=0**。未重启任何服务,未改计划任务。

### F4. 补跑(第 5 步)

- `Start-ScheduledTask -TaskName 'Qiuzhao-Collector-Daily'` 于 **13:36:44** 触发。8 秒后确认:`Get-ScheduledTask` 状态 = **Running**;`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` 可见新进程(PID 22916/640 跑 `deploy\windows_collector.py`,PID 588/18676 跑 `qiuzhao.collector.run --output-dir ...\runs\20260918\data --source all --delay 2`),确认为同日续跑(runner 在 `runs\20260918` 内续跑,退出码非 0 的阶段 basic/p1 重跑,tencent 因原退出码 0 预期跳过)。

### F5. 上线证据(第 6 步,basic 阶段)

- 前台 `while` + `Start-Sleep 120` 轮询 `receipt.json`,单次 SSH 会话 ≤8 分钟,超时即返回进度再发起下一轮。basic 阶段从 13:36:44 启动,**13:51:23 确认 `steps.basic` 从 1 变为 2**,耗时约 **15 分钟**(优于预期的 30–50 分钟,可能因大部分来源当日已抓过一轮,本轮为增量/重试)。
- `step_changes.basic`:`exit=2`,`result="partial"`,`added=115`,`updated=5930`,`marked_removed=22`,`disappeared=0`。**说明**:`updated` 达千级,符合预期;`added` 为百级(115),低于任务书"添加/更新为千级"的粗略预期——判断原因是当日 06:10 已跑过一次同源采集,本次补跑主要触发的是数据刷新(updated)而非新增(added),不属于任务书列出的回滚触发条件。
- `runs\20260918\data\source_state.json`(补跑后):

| 来源 | 状态 | 备注 |
|---|---|---|
| postal | success,complete,2648 条 | 与部署前一致 |
| chnenergy | failed(SSL UNEXPECTED_EOF) | 与部署前一致,来源侧网络问题,非本次改动范围 |
| telecom | failed(SSL UNEXPECTED_EOF) | 部署前本为 success,本轮转为网络偶发失败,与部署内容无关(telecom.py 未在本次 4 个部署文件内) |
| boc | success,complete,14 条 | 与部署前一致 |
| ccb | success,complete,39 条 | 与部署前一致 |
| **guopin** | **partial**,`collected_jobs=3097` | **修复验证通过**:部署前(旧 guopin.py)本轮上游整体 `status=failed`("source did not return a validated successful/partial snapshot",0 条);部署后 6 个专场中 zgyd(1775)、cam2027(81)、casicjob(1241)success+complete,ceec/zglt 因 SSL/超时失败、cgnpc 目录下线维持原状——guopin 从"整体失败"变为"部分专场成功入库",与 B/D 节验证的修复行为一致 |

### F6. 回滚判定

- 任务书第 6 步回滚触发条件为"`basic` 仍为 1 或 `step_changes` 缺失"。实测 `steps.basic=2` 且 `step_changes.basic` 完整存在,**不满足回滚条件,未触发第 8 步回滚**。
- `added` 低于粗略预期已在 F5 注明,留作后续观察项,不作为独立回滚依据。

### F7. 后续观察(p1,约 5 小时后,本次不等待)

- 待观察:`runs\20260918\receipt.json` 的 `steps.p1` 是否变为 2、`step_changes.p1`、`publication.published`、`sync_exit`,以及飞书同步 `data\lark-sync\runs\<新 run 目录>\business-sync.json` 的 `changed`(对照 F0 中本次部署前的 `changed=1231` 基线)。本执行者未等待、未手动触发飞书同步,由 runner 按既有门控自行执行。
