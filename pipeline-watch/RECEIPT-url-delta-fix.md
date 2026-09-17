# RECEIPT — 飞书链接字段比较口径修复(url-delta-fix)

日期:2026-09-17。目标:修掉 `business_delta` 把飞书读回的 markdown 链接 `[url](url)` 与纯 url 直接字符串比较、导致 `原链接`/`投递入口` 两字段每天对全部约 9.2 万行判定为"有差异"并全量重写的问题。

## 结论先行

1. **A(比较口径)已修**:`qiuzhao/collector/lark_sync_enrichment.py` 的 `business_delta` 改为对 `原链接`/`投递入口` 两个链接字段做"链接目标"归一化后再比较,能处理 markdown 链接、纯 url、`{"link":…}` 对象、以及上述形式的单元素列表。**关键修正**:任务书建议"优先按字段定义 `type=='url'` 做类型感知归一",但实测这两个字段在精灵当前 8 张表的真实 schema 里全部是 `type: 'text'`(飞书对写进文本字段的裸 url 仍会做超链接渲染、读回时套 markdown),不是专门的 `url` 类型字段。因此改为**字段名匹配**(`LINK_FIELD_NAMES = {'原链接','投递入口'}`)为主、`type=='url'` 为兼容性兜底,两者任一命中都归一化。
2. **B(零飞书调用离线验证)**:用 9-17 运行目录里已落盘的 `*.business-before-*.ndjson` + `source.jobs.json`,套用修好的函数重算,**还需更新的记录数从 92722 降到 788**(降幅 99.15%),且这 788 条不是同一个 bug 的残留,是两类另外的真实问题(见下)。
3. **C(853 条重复,查证过程中持续涨到 907→1049,dedup 尚未跑完)**:证据确认**不是**"`+record-batch-create` 盲重试"造成——当天 `sync-rerun.log` 里*没有任何一条* `+record-batch-create` 的重试记录(append 阶段 13 个批次全部一次性成功,`total_created` 从 50 连续累加到 597,中间无 `cli_retry`);且被 dedup 删除的全部重复分组(查证取样时点:650 组、907 条),其 `job_id` **无一个**出现在当天 `append-status.json` 的 `created` 映射里。**结论:这些是今天之前就存在的历史遗留重复,今天的 dedup 只是第一次大规模把它们清理掉,与"盲重试"无关**。按任务要求未改重试逻辑。
4. **D(部署)**:见下文——见证据部分记录的实际执行结果与 sha256。
5. **E(补全上一份收据)**:见文末对 `RECEIPT-sync-resilience.md` 的补写内容。

## A. 改了哪些文件

- `qiuzhao/collector/lark_sync_enrichment.py`:
  - 新增 `URL_MARKDOWN` 正则、`LINK_FIELD_NAMES = {'原链接','投递入口'}`、`normalize_url_field()`(递归处理 list/dict/markdown/纯字符串,统一取链接目标,空值归一为 `''`)。
  - `business_delta(old, desired, field_types=None)` 新增第三个可选参数;list 字段行为不变(仍按 set 比较);当字段名在 `LINK_FIELD_NAMES` 里或 `field_types.get(name)=='url'` 时,先归一化再比较;其余字段(如 `岗位描述`)保持原始字符串比较,不套正则,不会把普通文本里凑巧出现的 `[x](y)` 误判成链接。
  - `business_sync()` 调用处新增 `field_types={n:definitions[n]['type'] for n in names}` 并传给 `business_delta`。
  - **已查无同类问题**:`status_sync()`(257–301 行)只处理 `状态` 这一个 `select` 类型字段,读回值和期望值都是 list,走的是 `set(...) != set(...)` 分支,不受此 bug 影响,未改动。`sync_lark_multivalue.py` 里 `make_plan()`/`assert_current_values()` 涉及的三个字段(`毕业届别`/`工作地点`/`专业`)全部是 `select` 类型、按 set 比较,同样不受影响,未改动。
- `tests/test_lark_sync_enrichment.py`:新增 7 个单测(见下)。
- `pipeline-watch/RECEIPT-url-delta-fix.md`(本文件)、`pipeline-watch/RECEIPT-sync-resilience.md`(补写"补跑结果"一节)。
- 未改动 `qiuzhao/collector/sync_lark_multivalue.py`(C 已证实不是盲重试导致,按任务要求不改重试逻辑)。

## A. 单测

新增用例(均在 `tests/test_lark_sync_enrichment.py`):
- `test_url_field_markdown_echo_with_same_target_is_not_a_difference`:markdown 形式且 url 相同 → 无差异。
- `test_url_field_markdown_echo_with_different_target_is_a_difference`:url 不同 → 有差异。
- `test_url_field_link_object_and_list_echo_forms_normalize_the_same`:`{"link":…}` 对象、单元素 list 包 dict/markdown,均归一到同一 url。
- `test_url_field_empty_old_value_is_a_difference`:旧值为空(`{}` 或 `''`)→ 有差异。
- `test_plain_text_field_with_markdown_looking_content_is_not_normalized_as_url`:普通文本字段(`岗位描述`)里含 `[x](y)` 不被误归一,原样字符串比较。
- `test_link_field_is_url_aware_even_when_live_schema_type_is_text`:复现生产实际场景——`field_types` 传 `'text'`(而非 `'url'`)时,`原链接`/`投递入口` 仍按字段名归一化生效;不传 `field_types` 时同样生效(字段名兜底)。
- `test_multiselect_field_comparison_is_unaffected_by_url_awareness`:多选字段行为不变。

pytest 尾部输出(`pytest tests/ -q`,已确认与改动前基线的失败列表完全一致——用 `git stash` 比对,11 个失败一字不差,含任务书点名的已知失败 `test_core.py::test_role_cohort_and_campaign_title_bases`;70 个 error 均为 uvicorn 端口类环境问题,与本次改动无关,改动前后数量不变):

```
11 failed, 373 passed, 70 errors in 6.69s
```

失败列表(与改动前 `git stash` 基线逐行 diff 为空,无新增失败):
```
FAILED tests/test_call_log.py::test_unwritable_log_dir_keeps_calls_working
FAILED tests/test_codes_kind.py::test_migration_is_safe_when_both_services_start_together
FAILED tests/test_collector_lifecycle_failures.py::test_real_string_publication_path_sync_retry_does_not_republish
FAILED tests/test_core.py::test_role_cohort_and_campaign_title_bases
FAILED tests/test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint
FAILED tests/test_schema.py::test_enums_equal_the_values_in_the_data
FAILED tests/test_schema.py::test_enum_check_fails_when_data_drifts
FAILED tests/test_v4_fields.py::test_test_rules_hit_only_the_known_records
FAILED tests/test_v4_fields.py::test_shared_rules_match_the_spec_reference
FAILED tests/test_v4_fields.py::test_build_report_numbers
FAILED tests/test_v4_fields.py::test_iter_json_file_equals_json_load
```
与 `qiuzhao/collector/lark_sync_enrichment.py`/`sync_lark_multivalue.py` 相关的全部测试文件单独跑:`tests/test_lark_sync_enrichment.py tests/test_incremental_lifecycle.py tests/test_sync_lark_multivalue.py tests/test_lark_sync_daemon.py tests/test_lark_sync_index.py` → **57 passed**。

## B. 离线验证(零飞书调用)

在精灵上用运行目录 `C:\mcp-suite-collector\data\lark-sync\runs\20260917T134605188879` 里已落盘的 `backup.json`(8 张表的 `<table>.fields.before.json` schema)、`<table>.business-before-*.ndjson`(当天 business_sync 实际读回的旧值,共 934 个文件)、`source.jobs.json`(350MB,流式读取)跑离线脚本:只 `import business_fields`(纯函数,无副作用),本地内联与 Mac 端逐字节一致的 `normalize_url_field`/`business_delta`/`LINK_FIELD_NAMES` 重新计算 delta,全程未调用任何 `lark-cli`/飞书接口。

结果(与当天 `business-sync.json` 记录的 `changed:92722` 对应同一批 92722 条记录复核):

| 指标 | 数值 |
|---|---|
| 复核记录数(与原 `changed` 一致) | 92722 |
| **修复后仍需更新** | **788**(降幅 99.15%) |
| 涉及字段 | `原链接` 665 条、`来源` 123 条(`投递入口` 0 条) |

分表:除 `tblcrBAi0ld7uej8`(医药/医疗表,781 条:`原链接` 665 + `来源` 116)和 `tblffIc9CoTXcRUH`(制造续表,7 条:`来源` 7)外,其余 6 张表(含记录数最多的互联网科技岗主表/续表1、制造主表/续表1)**修复后 0 条差异**。

788 条抽样核实,**不是同一个 markdown/url bug 的残留**,是两类独立、真实的问题:
- **`原链接` 665 条(全部在医药/医疗表)**:源数据本身没有真实链接,`business_fields()` 算出的期望值是占位文本"请在详情页核验"(无 scheme);但飞书对这段纯中文文本仍做了超链接渲染,读回是 `[请在详情页核验](http://请在详情页核验)`,归一化后是 `http://请在详情页核验`,与期望值"请在详情页核验"因多出的 `http://` 前缀而不相等。这是飞书对占位文本自动加链接渲染的副作用,不是本次要修的"markdown 包 url"比较 bug——重写后若飞书仍会对这段文本重新加 `http://`,不排除这批记录会持续小量重写;不在本次任务范围内,列为遗留问题,不在本次改动。
- **`来源` 123 条**:抽样确认是源数据里 `source_name` 从非空变空的真实业务差异(如某记录旧值"恒瑞医药官方招聘"、期望值变成空字符串),与链接/markdown 无关,是 `business_sync` 该发现的真实变更(此前被 9.2 万条噪音掩盖,看不出来)。

**结论:未发现新的同类口径问题需要继续找;788 属于"很小的量级",符合任务预期,未上线前也未发现需要回退设计的情况。**

## C. 853 条重复(dedup 进行中持续增长)的来源

任务书给出的怀疑:`sync_lark_multivalue.py::cli()` 新加的"网络错误重试 3 次"对 `+record-batch-create` 这种非幂等调用做了盲重试,导致请求其实已成功、重试又建了一遍。

证据(均只读,来自 9-17 运行目录 + `C:\mcp-suite-collector\runs\20260917\sync-rerun.log`):

1. **当天日志里没有一条 `+record-batch-create` 的 `cli_retry` 记录**。完整读出 `sync-rerun.log`(112 行)后逐行检查:append 阶段(`appended_table: tblZOCFHBraQThw9`,13 个批次,`total_created` 从 50 连续累加到 597)之间**没有插入任何 `cli_retry` 行**,说明这 13 次 `+record-batch-create` 全部一次性成功,没有触发过重试(更谈不上盲重试)。当天日志里出现的 `cli_retry` 全部是 `+record-batch-update`/`+record-get`/`+record-list`/`+field-list`/`+field-search-options`/`+record-delete`,无一次是 `+record-batch-create`。
2. **被删的重复行,job_id 无一个是今天 append 新建的**。对证运行目录里的 `append-status.json`(`created` 映射,597 条,今天由 append_p1 写入 `tblZOCFHBraQThw9`)与 `duplicate-*.before.ndjson`/`duplicate-*.delete.json`(截至查证时 650 个重复分组、907 条已删):650 个分组的 job_id **全部不在** `created` 映射里(`groups_where_job_id_not_in_created_today = 650`,100%);"今天创建又被今天删除""今天创建但保留了另一条"两种情况均为 **0**。抽样的重复 job_id 前缀是 `gp_`(非 `p1-` 前缀,不是 append_p1 今天的候选来源)。

**结论:不是这个原因。这批重复是今天之前(历史遗留)就存在的,今天的 `deduplicate_exact()` 只是第一次大规模把它们找出来删除,与今天的重试机制无关。真实的历史成因(具体哪一天/哪次运行造成)无法仅凭 9-17 这一个运行目录确定,需要翻更早的运行目录才能查,超出本任务只读范围,未继续深挖。按任务要求:不改重试逻辑。**

## D. 部署到精灵

等待窗口:任务开始时(2026-09-17 12:44:41Z / 20:44:41 CST)`status.json` 即为 `running`/`deduplicate`;此后每 5 分钟查看一次(未杀进程、未手动重跑同步),到 13:44:41Z(60 分钟窗口用满)仍是 `running`/`deduplicate`(dedup 期间被删重复行数从查证时的 853 持续涨到 1049,说明进程活着、在正常推进,不是卡死)。按任务书"60 分钟后仍在跑,也可以部署"的条款,在 **60 分钟等待窗口用满后仍在运行** 的情况下执行部署(改动只新增一个函数和一个可选参数、不改变量名/导出符号,对已加载到内存的旧模块不产生影响,不影响当前 dedup 进程)。

部署时间:2026-09-17 21:47 CST(13:47:48Z 起)。通道:base64 → `powershell -NoProfile -EncodedCommand`(UTF-16LE),因文件 29120 字节整体编码后超出单次 `-EncodedCommand` 长度上限(实测约 8000+ 字符即报"命令行太长"),改为拆成 21 个 ≤1400 字节的分片,每片各自 base64→UTF-16LE→`-EncodedCommand`,用 `[IO.File]::Open(...,[IO.FileMode]::Create/Append)` 顺序写入同一目标文件。

| 步骤 | 结果 |
|---|---|
| 备份旧文件 | `qiuzhao\collector\lark_sync_enrichment.py.bak-20260917-2147`,sha256 `0558ced2bb8853a8f3f6066d40986b954937223f0eea23edaf1fe49c72dc0775`(与部署前实测精灵原文件、及上次 `RECEIPT-sync-resilience.md` 记录的基线完全一致) |
| 写入新文件(21 片) | 全部 0 输出(无报错) |
| 本地(Mac)sha256 | `6e1256ec35afa125ac073a079341de2057bc7435c07d9c7d72aea072e2d7c746` |
| 精灵部署后 sha256(`Get-FileHash`) | `6e1256ec35afa125ac073a079341de2057bc7435c07d9c7d72aea072e2d7c746` |
| **逐字节校验** | **一致** |
| `python -X utf8 -m py_compile` | `exit code 0`(语法有效) |

只替换了 `qiuzhao\collector\lark_sync_enrichment.py` 一个文件;未动 `sync_lark_multivalue.py`(C 已证实不是盲重试,未改重试逻辑,故不部署该文件);未动 `data\`、`runs\`、`keys\`、`.venv`、计划任务;未杀任何进程;未手动触发同步。部署完成后清理了本次为 B/C 调查在运行目录下新建的临时脚本/结果文件(`_offline_verify*`、`_check_types*`、`_sample_probe.py`、`_dup_probe*`、`_read_log.py`),不影响 dedup 正在写的原有文件。

截至部署完成时(21:48 CST)`status.json` 仍是 `running`/`deduplicate`,已删除重复行数 ≥1049(仍在增长)。

## 明早验证命令

```bash
ssh -i ~/.ssh/id_ed25519_lzh_qiuzhao -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -l 'LZH\-LZH-' 192.168.31.204 \
  "powershell -NoProfile -Command \"Get-Content 'C:\mcp-suite-collector\data\lark-sync\status.json' -Raw\""
```
关注 06:10 计划任务 `Qiuzhao-Collector-Daily` 跑完后最新 run 目录下 `business-sync.json` 的 `changed` 字段:预期从 92722 量级降到几百(参考本次离线复核的 788,实际数字会因源数据当天变化而略有出入,但应远小于 9 万)。

## 遗留问题

1. `原链接` 里"占位文本被飞书自动加超链接渲染"导致的 665 条(见 B),不在本次比较口径修复范围内;9-18 验证后如果这批记录仍每天出现在 changed 里,需要另开任务处理(例如把占位文本判定为"无链接"直接跳过比较,而不是当成 url 归一化)。
2. C 的历史重复真实成因未定位到具体日期/运行(只读范围内只能排除"是今天盲重试"这一个假设)。
3. 部署已完成(见上方 D 节,sha256 逐字节一致);部署时精灵仍在跑 9-17 当天的 dedup 阶段(未结束),因此本次修复要到 9-18 06:10 计划任务 `Qiuzhao-Collector-Daily` 的下一次同步才会首次生效验证,今天这次 dedup 收尾用的仍是旧的比较口径产生的既有中间态(不受影响,dedup 只处理重复合并,不涉及本次改动的 business_delta)。
