# 20260920e 累积部署件(P0:TypeError 'NoneType' object is not subscriptable)

生成:2026-09-20,分支 `fix/p0-typeerror-20260920`
(worktree `/Users/maxzhl/Projects/mcp-suite-p0b`;起点 `feat/gap-report` 3468074a
= `feat/collector-next-6` f0694da7 + tupu360 60 家启用 + 美团少采修复 + 每日采集缺口报告)。

状态:**未部署**。必须由站长明确说「上线」后才可覆盖精灵正式目录。

## 0. 这个包是什么,以及它和 20260920c / 20260920d 的关系

**20260920e 取代 20260920d,不要两个一起部署,也不要再部署 c。**
`20260920c`、`20260920d` 都**从未部署**;e = d 的全部 16 个文件 + 5 个「从没有任何包带过」的
文件(本次 P0 的另外 5 处读子进程输出点),合计 **21 个运行时文件 = 20 个覆盖 + 1 个新增**。
叠加顺序:**`20260920a`(精灵现役)→ `20260920e`**,一步到位。

| 来源 | 文件数 | 说明 |
|---|---|---|
| `feat/collector-next-6`(20260920c 的内容) | 13 | Moka 详情缓存续采、tupu360 分页硬截断修复、6 处「分页谎报」缺陷修复 |
| 本 P0 分支之前的 `feat/gap-report` | 3 | 新增 `collection_gap.py`;修改 `p1_meituan_public.py`、`deploy/windows_collector.py` |
| 本次 P0(本包新增的 5 个文件 + 2 个文件再改) | 5 + 2 | 见 §2 |

`p1_pipeline.py`、`windows_collector.py` 在 e 里是**再改过的版本**(P0 修复);其余 14 个文件与
20260920d **逐字节相同**(已逐个 sha256 比对),可把本包理解为「d + P0」。

## 1. P0 根因(确切行号 + 触发条件,已在精灵实机复现)

**现象**:2026-09-20 `runs\20260920\receipt.json` `stage="partial-or-failed"`、
`steps={"basic":2,"tencent":0}`(**没有 p1 键**)、
`error="TypeError: 'NoneType' object is not subscriptable"`、`success=false`、
`started 06:10:01`、`completed 11:43:31`、`total_jobs`/`publication` 都不存在 → **当天零发布**。

**链条(每一步都有证据)**:

1. p1 于 `06:41:51` 起跑(`runs\20260920\data\p1-runs\20260920T064151\`),
   自带 deadline `--max-run-seconds 18000` → **11:41:51** 到期;
2. 外层 `deploy\windows_collector.py` 给 p1 步骤的限时是 **18100s**(= deadline + 100s),
   于是在 **11:43:31** 触发 `step()` 的 `subprocess.TimeoutExpired`
   → 调 `qiuzhao\collector\portable_runtime.py` 的 `stop_tree(child)`;
3. `stop_tree` 在 Windows 上用 `subprocess.run([...taskkill.exe,'/PID',pid,'/T','/F'],
   capture_output=True, text=True)` 收尾。**精灵的中文 Windows 上 taskkill 用 GBK 输出**
   (成功时是「成功: 已终止 PID … 的进程。」,首字节 `0xb3`),而计划任务用
   `python.exe -X utf8` 启动(schtasks XML 已核:`-X utf8 C:\mcp-suite-collector\deploy\windows_collector.py`),
   `text=True` 因此按 UTF-8 解码;
4. 解码异常发生在 **Windows 专用的读取线程** `subprocess._readerthread`
   (`subprocess.py:1599 buffer.append(fh.read())`)→ 线程死掉、`_stderr_buff` 仍是 `[]`;
5. CPython 3.12 的 Windows `_communicate` 结尾是
   `stdout = stdout[0] if stdout else None` / `stderr = stderr[0] if stderr else None`
   → **`result.stderr` 变成 `None`**;
6. `portable_runtime.py:41` 的 `result.stderr[-1000:]` → **TypeError: 'NoneType' object is not
   subscriptable**。它在 `except subprocess.TimeoutExpired:` 里抛出,所以 `step()` 直接冒泡;
7. `windows_collector.main()` 的 `state['steps'][name]=step(...)` 因此**从未赋值**
   (receipt 里没有 p1 键),内层 `except` 回滚 staging `jobs.json` 并 `reset_p1(stage)`
   (删 `p1-status.json`/`p1-checkpoints`),外层 `except` 把消息截断成 500 字符写进 `error`;
   **`validate-and-publish` 一步都没走到** → basic 与 p1 的成果一起作废。

**复现(精灵实机,只读诊断,未终止任何真实进程)**:

```
C:\mcp-suite-collector\.venv\Scripts\python.exe -X utf8 -c \
 "... subprocess.run(['C:/Windows/System32/taskkill.exe','/PID','999999','/T','/F'],
                     capture_output=True,text=True,check=False,timeout=30) ..."
→ rc 128 | STDOUT '' | STDERR None        ← 正是 None
→ Exception in thread Thread-2 (_readerthread) ... UnicodeDecodeError:
  'utf-8' codec can't decode byte 0xb4 in position 0
```
(PID 999999 不存在,只打印「没有找到进程」,没有任何进程被终止。)

**同一缺陷在当天早些时候已经出现过 9 次**:p1 自己的 `collect_process()` 也用
`stop_tree(..., strict=False)` 收尾超时的适配器,`p1.log` 里 9 条
`UnicodeDecodeError: ... byte 0xb3 in position 0`(= taskkill **成功**终止的 GBK 文案),
对应 `p1-runs\20260920T064151\**\timeout-cleanup.json` 里 **18 处**
`"cleanup_error": "TypeError: 'NoneType' object is not subscriptable"`。
p1 那 9 次被自己的 `except Exception` 收敛成「该单元失败」;外层这一步没有捕获,于是整轮死。

## 2. 这个包改了什么

### 2.1 P0 主体(6 个文件)

| 文件 | 改法 |
|---|---|
| `qiuzhao\collector\portable_runtime.py` | **根因**。新增 `child_output()`:`subprocess.run(..., text=True, encoding='utf-8', errors='replace')` + `(result.stdout or '')`→ 读取线程不会死、`None` 也被兜住;`stop_tree` 的 Windows 分支改走它,taskkill 失败/超时也只是记 `taskkill_error` + `tree_termination_confirmed=False`(**strict 语义不变**:确认不了照样抛,防止带着活写者继续写共享库) |
| `deploy\windows_collector.py` | ① p1 步骤限时 **18100s → 21600s**(= `P1_MAX_RUN_SECONDS 18000` + `P1_FINALIZE_BUDGET 3600`,并抽出 `steps_for()` 让「父看门狗必须晚于 p1 自己的 deadline + 收尾窗口」成为可断言的常量);② 外层 `except` 追加 **`error_traceback`(完整 traceback)与 `error_step`**(这次只有 500 字消息,才需要二次排查) |
| `qiuzhao\collector\p1_pipeline.py` | `collect_process()` 的「部分 checkpoint」路径:`checkpoint['coverage']` 改成类型校验,**取不到就按该单元失败处理并把原因写进 errors**(`partial checkpoint rejected: …`),不再静默 `pass`;`any_validated()`/`is_full_success()`/`run()` 收尾判定改为容忍 None/非 dict 的 coverage,保证**收尾阶段不会因为一条脏记录整轮退出 1** |
| `qiuzhao\collector\auto_collect.py` | basic/tencent 两处 `subprocess.run(text=True)` 加 `encoding='utf-8', errors='replace'`;`result.stderr[-500:]` → `(result.stderr or '')[-500:]`(否则真正的退出码会被 TypeError 顶掉) |
| `qiuzhao\collector\lark_sync_daemon.py` | `source_hash()` 的 ssh 输出同上;`None` 时落到既有校验 `ValueError('invalid source hash response')` |
| `qiuzhao\collector\sync_lark_multivalue.py` | `lark-cli` 调用加 `errors='replace'`;`proc.stderr/ stdout` 为 `None`/空时给出结构化 `{'type':'decode'}` 错误,不再 `TypeError`/`JSONDecodeError` |

另:`qiuzhao\collector\p1_sources_11_20.py`(滴滴 openssl verify 那处 `text=True`)一并加
`errors='replace'` 与 `(verification.stderr or '')` —— 这是全仓最后一处严格的子进程文本解码。

### 2.2 与 20260920d 相同的那 14 个文件

`p1_platform_companies.json`(1124 家,tupu360 60 家启用)、`p1_meituan_public.py`(少采修复)、
`collection_gap.py`(每日缺口报告,新文件)、6 个平台适配器 + `p1_foreign_01.py` +
`alibaba_headless.py` + `p1_netease_public.py`(collector-next-6 的分页谎报修复)。
详细说明见 `pipeline-watch/deploy-artifacts/20260920d/DEPLOY-NOTES.md`,
本包内容与其逐字节一致。

## 3. 行为变化(部署后与现在不同的地方,仅两处)

1. **p1 跑到 5 小时上限不再等于失败**:p1 自己在 deadline 处返回 2(部分成功,已校验单元保留),
   父进程给足 21600s 收尾窗口,于是流程照常进入 `validate-and-publish` ——
   **已采到的成果会被发布**。只有真·超时(>21600s,说明 p1 卡死)才走 124 + 回滚,契约不变。
2. **receipt.json 多两个字段**:`error_step`(崩在哪一步)、`error_traceback`(完整栈)。
   失败时不再需要靠日志反推。

## 4. 2026-09-20 当天丢了什么(部署这个包**不能**找回,只是把事实写清楚)

生产库(`data\jobs.json`)最后一次成功发布是 **9-19 07:02**,94,486 行;9-20 一整天零发布。

| 阶段 | 已做但未发布的成果 |
|---|---|
| basic | 新增 634 / 更新(刷新)62,491 / 标记下架 10(`step_changes.basic`);回滚后 95,120 行 |
| tencent | exit 0,added/updated 均为 0(无净变化) |
| p1 | **958 个单元**(744 success/complete、84 partial、130 blocked)、**828 次本地 CAS 发布**、跨单元共 44,967 条岗位;合并结果 **95,120 → 114,739 行**(新增 19,619 / 更新 13,310 / 移除 432);`reset_p1` 已把 staging 回滚到 `p1.before.json` |
| 线上可见影响 | 库里少了 **20,253 条新岗位**(634 + 19,619),用户侧 9-20 当天看不到任何更新 |

**可打捞材料仍在盘上(未被删除,采集不用重跑)**:
`runs\20260920\data\p1-runs\20260920T064151\`(958 个单元的 `validated.json`/`result.json`、
`status.json` 含 828 条 publication 明细、`batches\<ns>\jobs.before.json.gz` 63MB = p1 开跑前快照)
与 `runs\20260920\data\jobs.json`(= basic+tencent 之后、p1 之前的状态)。
注意打捞的坑:`p1-status.json`/`p1-checkpoints` 已被 `reset_p1` 删除,新起一轮 p1 会**重新采集**;
若要「不重采只补发布」,需人工把该 run 的 `status.json` 恢复成 checkpoint 并把各单元
`published` 置回 false 再 `--resume --run-dir <该目录>`,属站长决策,本次未执行。

## 5. 部署步骤(与既有部署任务书一致,需站长明确批准后由执行者做)

1. **空闲判定**(只读):`runs\<今日>\receipt.json` 已 `completed_at`、无
   `windows_collector`/`p1_pipeline`/`lark_sync` 进程、`data\lark-sync\status.json` 非 running、
   计划任务 `State=Ready`、且**距下一次 06:10 有充足余量**。
2. **备份**:`robocopy` 只备 `deploy` 与 `qiuzhao`(见 `PROD-BACKUP-MANIFEST.txt` 末尾两条命令,
   退出码 ≤7 为成功),**不要**整目录 robocopy(`recovery\` 约 3.4GB)。
3. **前提核对**:按 `PROD-BACKUP-MANIFEST.txt` 的 PRE-DEPLOY 列逐条比对现役 sha256
   (21 行,本次已全部由本任务在精灵上只读实测;若实测不同 → 停,记差异并当漂移处理)。
4. **传输**:21 个文件分片 base64(每片 ≤1300 字符)→ `C:\mcp-suite-deploy-20260920e\`,
   逐文件 `Get-FileHash` 与 `SHA256SUMS.txt` 比对后才覆盖。
5. **覆盖 21 个路径**(1 个新增,不删任何文件、不碰 `data\`/`runs\`/`.venv`/飞书/阿里云),
   覆盖后 21/21 哈希一致;再与备份全树比对,预期差异恰好 = 21 个覆盖 + 1 个新增。
6. **导入自检**(正式 venv,cwd=`C:\mcp-suite-collector`):`py_compile` 全通过、
   `IMPORT_OK 1124 1124`、`LOCK True`、`CHILD_TEXT` 生效
   (`portable_runtime.CHILD_TEXT['errors']=='replace'`)、`P1_STEP_LIMIT==21600`、
   `REGISTRY['雀巢']='moka'`、tupu360 60 家启用。
7. **不得**重启服务、改计划任务、手动补跑 p1;首次实测 = 次日 06:10。

### 5.1 部署前已在 Mac 上做的「等价目录」自检

把 21 个文件覆盖进一棵工作区副本、并用**精灵现役的 `v4_fields.py`**(`f74e6ab3…`,与分支不同的
既有分叉)替换后再导入,实测输出:

```
IMPORT_OK 1124 1124
REGISTRY_EQ_DEFAULT True
LOCK True
CHILD_TEXT {'text': True, 'encoding': 'utf-8', 'errors': 'replace'}
P1_STEP_LIMIT 21600 P1_MAX_RUN_SECONDS 18000
STEP_LIMITS {'basic': 7200, 'tencent': 1800, 'p1': 21600, 'normalize': 1800}
tupu360 注册 55 家  nestle=moka  hp=eightfold  hsbc=successfactors
```

即:包里的 `p1_pipeline.py` 与现役 `v4_fields.py` 兼容(分支只用 live 已有的
`iter_json_file`/`graduation_of`/`graduation_constraints_of`)。

## 6. 回滚

按 `PROD-BACKUP-MANIFEST.txt`:20 个文件从备份恢复,**删除唯一新增的
`qiuzhao\collector\collection_gap.py`**;恢复后必须确认 `p1_pipeline.py` 回到
`093b237e…`、`windows_collector.py` 回到 `9eaf97cc…`(`13a5ec53…` 那条 P0 发布锁补丁与
`_publish_thread_lock` 必须始终在位,06:10 的日更依赖它)。

## 7. 遗留与提醒(不属于本次修复)

- **p1 容量**:20260920d 的提醒仍然成立 —— 1124 家 × 3 scope ≈ 3300 个单元,
  9-20 那次 958 个单元就撞了 5 小时上限(说明单轮预算被 tupu360/长尾拖满)。
  本包让「撞上限」变成正常收尾(发布已采部分),但**覆盖率**仍取决于
  `--max-run-seconds` / `--platform-rotation` 的取舍,建议站长单独决策。
- **`qiuzhao\v4_fields.py` 是既有分叉,本包故意不动**:现役 `f74e6ab3…`,
  分支/main `3c08ed8d…`(分支多了 `data_as_of` 的时区处理与 `_reviewed_time`)。
  该文件不在 `112de24e..HEAD` 的改动范围内,本包所有文件只用到 live 版本已有的
  `iter_json_file`/`graduation_of`/`graduation_constraints_of`(已核查 live ⊇ branch)。
- `deploy\windows_receiver.py`、`deploy\windows_recover_run.py` 同样是既有分叉
  (现役 `046aa698…`/`0cb339c2…`,分支 `54cbf8fc…`/`4eebdcb9…`),都不在每日链上,
  自 20260920a 起就未随任何包含进来;要同步请另开任务。
- `qiuzhao\normalize_tables.json` 在精灵上不存在,`normalize.py` 走内置值集降级路径
  (20260920a 收据已记录,本包未改变该行为)。
- **完整性审计**(本次对精灵 `qiuzhao\` + `deploy\` 全树 66 个文件逐个 sha256 比对):
  除上面三处既有分叉与精灵上的 `*.bak-*`/`*.before-*` 备份文件外,分支与现役**唯一的差异
  就是本包的 21 个文件**。分支里另有三个精灵上没有的文件,均**不需要**下发:
  `lark_sync_index.py`(只被 `deploy\windows_recover_run.py` 引用,而现役 `windows_collector.py`
  用 `lark_sync_daemon`,测试也断言 deployable 文件里不出现 `lark_sync_index`)、
  `p1_company_names.py`(只被自己的单测与 `company_names.py` 的注释引用,不进每日链)、
  `normalize_tables.json`(降级路径,见上条)。
- 打捞 9-20 的 p1 数据是**独立决策**,不在本包范围。
