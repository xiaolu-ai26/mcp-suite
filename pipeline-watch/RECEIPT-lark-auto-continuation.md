# 收据 · 飞书续表自动创建（`feat/lark-auto-continuation`）

**结论**：续表从「人工建表 + 人工改代码登记 id」变成真正自动。新增共享模块
`qiuzhao/collector/lark_continuation.py`，增量同步（`sync_lark_multivalue` /
`lark_sync_enrichment.append_p1` / `lark_sync_index.run_mirror` / `lark_sync_daemon`）与
整表重灌（`lark_reload_mirror`）**共用同一套「发现 + 创建 + 逐字段校验」**；最后一张表
余量低于阈值自动建 `<行业基名>·续表N+1`，校验 19/19 一致才写，否则删表并告警。
单测 13 条全绿；`pytest tests/` 相对 `feat/collector-next-4` 基线**无新增失败**；测试
Base 端到端实测通过（建表 + 校验 + 写入 + 幂等）。**未部署、未 SSH、未碰阿里云、未 push、
未合并 main、生产 Base 全程只读、未终止任何进程。**

---

## 1. 现状容量表（2026-09-19 23:25 总控实测；本任务只读复核一致）

生产 Base `REDACTED`，单表上限 **20000**（证据：`lark_sync_index.py`
原 `TABLE_RECORD_LIMIT=20000`，19843+n 时 `800040832 quota_exceeded`）：

| 表 | table_id | 行数 | 余量 |
|---|---|---:|---:|
| 互联网科技岗 | `tblX7rOpjWaRArng` | 18980 | 1020 |
| 互联网科技岗·续表1 | `tblu0nsYjntEOCGY` | 19993 | **7** |
| 互联网科技岗·续表2 | `tblZOCFHBraQThw9` | 1079 | 18921 |
| 国企央企岗 | `tbl0xkmJUMmLqZ1W` | 5884 | 14116 |
| 制造工业岗 | `tbl0gDcxEaIOYERw` | 14514 | 5486 |
| 制造工业岗·续表1 | `tbllqb2R9itUKXdH` | 19973 | **27** |
| 制造工业岗·续表2 | `tblffIc9CoTXcRUH` | 5483 | 14517 |
| 其他行业岗 | `tblcrBAi0ld7uej8` | 7226 | 12774 |
| **合计** | | **93132** | **约 6.7 万** |

`互联网科技岗·续表1`（余 7）与 `制造工业岗·续表1`（余 27）均已远低于阈值，只是恰好各自
还有一张较空的续表 2 在承接。库每天至少 +1000 条，p1 修好后 1056 家更快 → 续表 2 数周内
会满，不做自动建表时新岗位会**静默丢在飞书之外**（服务器库不受影响）。

**「之前一直是自动建的」是误解**：`lark_sync_index.py` 原文写明满表只记
`capacity_blocked` + `blocked_job_ids`；续表 id 是 `sync_lark_multivalue.py` 里的硬编码常量
（`INTERNET_CONTINUATION` 等）；2026-09-17 的「互联网科技岗·续表2」是人工建表 + 人工改代码
登记（commit 3112763，证据 `research/qiuzhao-p1-20260912/base-overflow/internet2.*.json`）。

## 2. 阈值选择理由

`lark_continuation.CAPACITY_THRESHOLD = min(1000, TABLE_RECORD_LIMIT // 20) = 1000`。
- 触发条件：某行业最后一张表 `余量 < 1000` 或 `余量 < 本次新增行数`，先建续表再写。
- 1000 = 上限 5%：一天发布量约 1000–2000 行，留 1000 头寸既能覆盖一天写入，又能吸收
  `+table-list` 的 `records_count` 延迟（该字段最终一致，实测写入 3 行后仍显示 0）。
- 不等到 0 才建：并发/重试时若等写满，`+record-batch-create` 会返回容量拒绝，溢出部分
  需要回滚；提前建表把这种拒绝路径留给真正的异常。
- 常量可调：`ensure_capacity(..., threshold=...)` / `ensure_total_capacity(..., threshold=...)`；
  整表重灌按 `min(1000, max_rows_per_table/20)` 随 `--max-rows-per-table` 缩放。

## 3. 发现 + 创建 + 校验流程

**发现**（`lark_continuation.discover`）：读 `+table-list`，只认精确名字
`<行业基名>`（N=0）与 `<行业基名>·续表N`（N≥1、无前导零），按 N 排序；`互联网科技岗2`、
`续表0`、`续表01`、`续表X`、`重灌原型-互联网科技岗` 等一律跳过。同名/同 N 冲突会返回
`problems`，调用方报错而不是静默挑一张。硬编码 8 个 id 保留在 `LEGACY_TABLE_IDS`，只用于
`legacy_id_drift` 告警——**live 名发现永远优先，绝不静默用错表**。

**建表**（`create_continuation`，复刻 2026-09-17 人工流程并自动化）：
1. `+table-create --name <基名·续表N+1> --fields '<主字段>'`（主字段 = 基表视图顺序第一个）；
2. `+field-create --json '<其余 18 字段数组>'`（CLI 逐字段串行创建；Windows 下长 `--json`
   由 `S.cli` 自动落 `@file`，避开命令行长度限制）；
3. `wait_fields` 轮询等字段创建生效；
4. `+view-set-visible-fields` 把默认网格视图钉到基表视图顺序；
5. 读回逐字段校验。

**校验**（`schema_diff`，对基表）：
- 硬失败（`severity=error`）：字段数量、缺失/多余字段、`type`、`multiple`、`style`、
  单选/多选**选项集合**、视图字段顺序；
- 软告警（`warning`）：`description`、`default_value`、选项颜色/顺序（Bitable
  `+field-list` 不保证返回创建顺序，2026-09-17 人工建表已记录此限制，故顺序以「用户实际
  看到的默认视图顺序」为准）；
- `工作地点` 600+ 选项：`+field-search-options` 全量分页（`read_fields`），一条不漏。

**失败即清理**：任一硬失败 → `+table-delete --yes` 删除刚建的表 →
`continuation-alerts.jsonl` 记 `continuation_validation_failed`（含 `deleted=true` 与
fatal 明细）→ 抛 `ContinuationValidationError`。**绝不往未校验的表写一行数据。**

**幂等 / 并发**：状态文件 `continuation-state.json` 记录（基名、N、表名、id、时间、
校验结果、`adopted`/`deleted`）；`provision_lock` = 进程内 `RLock`（解决 Windows
`msvcrt.locking` 同进程重入抛 Errno 36 的问题）+ 状态文件旁 `.lock` 的跨进程 `flock`，
串行化「发现→判定→建表」。重跑时新表已存在且有余量 → 0 次建表；并发/重试不会建出两张同名表。

**告警**：`record_alert` 写 run 目录 `continuation-alerts.jsonl`，事件
`continuation_created` / `continuation_create_failed` / `continuation_validation_failed` /
`continuation_live_invalid` / `legacy_id_drift` / 重复名冲突。**缺口**：全仓搜索 `+message`/
`message-send`/IM 发送，当前**没有飞书消息通道**（收据第 8 节遗留），按站长「没有通道就写
告警文件、不要自己接新通道」的约定执行；`record_alert` 预留了 `notifier` 回调，接入通道时
无需改调用点。

**两条路径共用**：
- 增量：`append_p1` 按 `route_group` 分组 → `ensure_capacity` → 写返回的最高 N 表；
  `run_mirror` 同样分组 → `ensure_capacity` → 写目标表；`S.snapshot` 按名发现全部续表；
  `LarkCliTransport.locate` / `all_table_ids` 覆盖全部续表；`run_local` 身份校验改为
  四个基表必须存在。
- 重灌：`lark_reload_mirror.main` 在 `--apply` 且容量不足时调 `ensure_total_capacity`
  （同 `create_continuation`），再 `plan_placement`；失败则该组记 `capacity_blocked` 不写。
  原注释「never a reason to create one」已改。

## 4. 测试 Base 实测（`ThAxbM3QAazvJLsJfKpcPKOwnyd`，生产 Base 全程只读）

脚本 `research/lark-auto-continuation/validate-test-base.py`，报告
`research/lark-auto-continuation/run-20260919/validation-report.json`。**只动测试 Base。**

| 项 | 结果 |
|---|---|
| 触发前 | 测试 Base `互联网科技岗`（`tbl4UFSltrBFE0Pp`）**19500 行**，余量 500 < 阈值 1000 |
| 自动建表 | `互联网科技岗·续表1` = **`tblSH4UL8HT5inJj`**，视图 `vew…`（同默认网格） |
| 校验 | **19/19** 字段；`diff=[]`、fatal=0；含 `工作地点` 全量选项与 `原链接/投递入口` url style |
| 写入 | `+record-batch-create` 5 行 **全部成功**，表计数 0 → 5 |
| 幂等 | 第二次 `ensure_capacity` **0 建表**、0.63 s、目标仍是续表1 |
| 清理 | 实测前删掉上一轮手工试验表 1 张（仅测试 Base） |
| 耗时/调用 | 建表+校验 **36.69 s / 该段约 26 次调用**；全程 **31 次**（`+field-create` 单次 19.64 s 是主耗时；`工作地点` 分页 9 次 `+field-search-options`） |
| 写入耗时 | `+record-batch-create` 5 行 1.75 s |

调用分布：`+table-list` 6、`+field-list` 5、`+field-search-options` 9、`+view-list` 3、
`+view-get-visible-fields` 3、`+table-create` 1、`+field-create` 1、`+view-set-visible-fields`
1、`+record-batch-create` 1、`+table-delete` 1（清理上一轮）。

生产容量表由 1 次只读 `+table-list` 复核（§1），未对生产 Base 做任何写操作。

## 5. 失败与回滚行为

- **建表失败**（网络/权限/API 拒绝）：`create_continuation` 兜底删除可识别的半成品表，
  记 `continuation_create_failed`，调用方 `capacity_blocked`，**不写数据**。
- **校验失败**：删表 + `continuation_validation_failed` + 抛错，**不写数据**。
- **已存在的同名表校验失败**：记 `continuation_live_invalid` 并拒绝写入，**不删**（避免误删
  线上真实表）。
- **写入中途容量拒绝**（`800040832`）：只对明确容量拒绝不重试；记 `capacity_blocked`
  与剩余 job_ids，其余组继续。
- **回滚**：代码层设 `QIUZHAO_LARK_SYNC_MODE=daemon`（若部署了 20260919a 的
  `windows_collector.py`）或覆盖回旧文件；旧的 `sync_lark_multivalue.py` 不认识新建的续表，
  会重新把它当未知/满表处理，**不会写坏数据**。误建的空表可手工删除（删前确认计数为 0）。
- **单测已覆盖**：容量不足触发、字段/选项不一致拒绝并删除、跑两次只建一张、两线程只建一张、
  发现按 N 排序并跳过无关表名、建表失败告警且不留表、`run_mirror` 校验失败零写入。

## 6. 改动与产物

| 文件 | 说明 |
|---|---|
| `qiuzhao/collector/lark_continuation.py` | **新增**：共享发现/创建/校验/幂等/告警 |
| `qiuzhao/collector/sync_lark_multivalue.py` | 常量委托共享模块；`full_fields` 委托 `read_fields`；`snapshot` 按名发现；`valid_selection_for_snapshot` |
| `qiuzhao/collector/lark_sync_enrichment.py` | `route_group`/`new_fields_for_group`；`append_p1` 自动建表；`verified_backup` 动态校验 |
| `qiuzhao/collector/lark_sync_index.py` | transport 动态清单；append 前 `ensure_capacity`；`locate` 覆盖续表 |
| `qiuzhao/collector/lark_sync_daemon.py` | 身份校验改为四个基表存在 |
| `qiuzhao/collector/lark_reload_mirror.py` | 并入本分支（`merge feat/lark-reload-mirror`）；`ensure_total_capacity` 自动扩容；`field_options` 委托共享读取 |
| `tests/test_lark_continuation.py` | **新增 13 条**假 Base 单测 |
| `research/lark-auto-continuation/validate-test-base.py` + `run-20260919/` | 真实测试 Base 验证脚本与报告 |
| `pipeline-watch/deploy-artifacts/20260919m/` | 6 运行时文件 + `SHA256SUMS.txt`（`shasum -c` 6/6 OK、与源码逐字节一致）+ `DEPLOY-NOTES.md`（叠加顺序） |
| `pipeline-watch/RECEIPT-lark-auto-continuation.md` | 本收据 |

**基线与测试**：`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/` =
**3 failed / 668 passed / 55 skipped**，失败清单与 `feat/collector-next-4` 基线
（3 failed / 640 passed / 55 skipped）**逐条相同、无新增**（668 = 640 + 15 lark-reload
合并 + 13 本任务；3 条为交接文档已注明的既有失败）。零网络 import 校验：6 个运行时模块
在模拟精灵目录结构下全部导入成功。

## 7. 遗留 / 待站长决策

1. **飞书消息通道缺失**：建表成功/失败目前只落 `continuation-alerts.jsonl`。按约定未自建
   通道；若要站长即时收到，需接一个已有/新的飞书消息发送入口（`record_alert` 已留
   `notifier` 钩子）。
2. **硬编码续表 id 仍保留**为兼容/兜底（`LEGACY_TABLE_IDS`），仅用于漂移告警；等生产
   Base 上不再需要人工登记后，可在下个版本删除或在收据里标记废弃。
3. **生产 Base 尚未产生 续表3**：本轮只在测试 Base 验证了建表+校验+写入；生产第一次真实
   自动建表会发生在 续表2 余量 < 1000 时，届时看 `continuation-alerts.jsonl` 的
   `continuation_created` 与表计数。
4. **字段顺序的定义**：因 Bitable `+field-list` 不保证创建顺序，顺序校验以默认网格视图
   `visible_fields` 为准（与 2026-09-17 人工建表一致）；若站长另有「导出顺序」要求，
   需要额外用 Base 导出核对。
5. **未部署**：部署件 20260919m 与叠加顺序见其 `DEPLOY-NOTES.md`；上线需站长明确说
   「上线」，且应在 9-19 首轮实测（p1 winlock 修复）核对之后再上。

## 8. 硬约束遵守

未部署、未覆盖精灵、未碰阿里云、**未对生产 Base 做任何写操作**（仅 1 次只读
`+table-list`）、未读取/打印令牌、未 push、未合并 main、未终止任何进程；不使用
`git stash`；`._*` 未提交；Python 用主仓 venv；产物写外接盘
`/Volumes/臭垃圾桶/生财MCP/_research/lark-auto-continuation/`（外加提交内小体积收据/部署件）。
