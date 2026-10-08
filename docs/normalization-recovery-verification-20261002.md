# Pro normalize 修复验证记录（2026-10-02）

适用基线：`bcae6e546a025a3a84c5bfe4aa9d619a38db9c79`。**独立审查待完成，生产未部署。** 当前网页会话没有独立 Agent，没有把自查称为独审；用户对本轮 Pro 实现的授权覆盖旧任务书的执行模型限制，历史审查归属保留。

## 输入和能力

GitHub 连接器实际读取了公开源码、私有 README/TASK_PROMPT/READY、准备审查摘要、Release 附件元数据；Release 的二进制归档未下载，context-inventory 超大文件的内容未成功读取，不能声称逐项读过 5275 条。公开日更正文完整读取，踩坑正文和方法索引/R1/R2完整读取，源码按本次调用链读取；没有把整个仓库逐行审查。

实际可用：本地 Linux、Python 3.13.5、pytest、Git；GitHub 分支写入已验证。直接联网 clone/DNS 和 Release 二进制下载不可用。无法访问精灵 Windows、生产服务器、真实飞书或当前 Scheduler；没有读取或索取账号凭据。

精确重建的四个基线文件逐个以 Git blob 身份核验：

| 文件 | 基线 blob SHA |
|---|---|
| qiuzhao/normalize.py | ea251f9b5989aaa9f536b86264b38477afd30f1c |
| docs/qiuzhao-daily-delivery.md | 7cbc07310974bcfc6244bfc3888525b12ef73675 |
| docs/qiuzhao-collection-pitfalls.md | a6ff890ab9d056368a1b19ed4073e8d449d5f500 |
| docs/collection-methods/README.md | 12704949dbf4e6e119f9683ee34e1b8348d7f0cd |

本地验证树是上述精确文件和本次新增文件的聚焦 checkout，不是完整仓库，也没有伪造 bcae 提交。Git diff 的旧文件身份来自真实基线；应用/反向检查在此聚焦 checkout 执行，完整仓库检查另需在精灵执行。

## 已运行

`python -m pytest -q tests/test_normalization_io.py tests/test_windows_normalize_retry.py`：最终 79 passed。I/O 测试实际读写临时文件，覆盖分块解析、Unicode、完整结束、坏输入、回调失败、原记录/重复记录保留、模式、fsync/替换失败、漂移与 check 不写入。恢复测试使用真实文件与 Linux flock，但 runner 的阶段进程和 Scheduler 为 stub；覆盖只调用 normalize、计划/预算/截止保持、重复执行拒绝、未知发布/active_batch/锁/容量/资产漂移拒绝、中断校验屏障。

测试开发过程保留：第一次 75 passed/1 failed，失败是并发改写测试先触发“尾随内容”而不是预期“身份漂移”；改为等长外部改写后验证准确场景，第二次 76 passed。补充校验窗口中断、异常 exit 2 与屏障解除测试后为 79 passed。没有删掉失败安全场景或将失败隐藏为 skip。

静态检查：本次 Python 文件 py_compile；最终 diff 的 whitespace 和补丁正反向检查以包内 evidence 的实际日志为准。没有运行供应商 API、正常采集、发布、Base 写入或删除归档。

## 内存风险复现（合成，不是生产根因）

输入 120000 行、127688890 字节；SHA256 `3f9f87ba5af881528c1eb3c28ff41934f93f95236820676864dc235c0a63173e`。探针抽取真实旧/新 normalize_file 入口，业务回调为空操作，测量 I/O 而非完整业务归一化：

```bash
python -S tests/probes/normalization_memory_probe.py --module BEFORE/qiuzhao/normalize.py --input ISOLATED/jobs.json --limit-mib 128
python -S tests/probes/normalization_memory_probe.py --module qiuzhao/normalize.py --input ISOLATED/jobs.json --limit-mib 128
```

| 同样的隔离条件 | 结果 | 峰值 RSS KiB | 探针时间秒 |
|---|---|---:|---:|
| bcae 旧入口 | MemoryError | 14720 | 0.000（显示精度） |
| 新入口 | 成功，120000 行 | 16124 | 3.264 |

新入口完成后 SHA 与输入一致。最初不加 `-S` 的两次探针均失败：当前站点注入令 Python 初始虚拟内存约 413332 KiB，已超过 128 MiB 限制，不能用于算法对比。两次失败和后续隔离实测日志都保留，未挑选旧失败/新成功的不同限制条件。

## 未运行、阻断和非结论

10/2 normalize.log、完整 receipt 和真实 staging 未取得，因此实际错误可能是内存、数据、资产、权限、超时或其他异常，**仍未归因**。代码确认缺表本身走 fallback，不能断言缺表导致该次失败。流式修复不会自动解决坏数据或业务映射异常。

完整 normalize/v4/company 业务测试、已有分段/发布/partial-keep/recovery 回归、Windows 锁/进程/Scheduler/路径、NTFS、实际安装、原 run 重放、accepted/served/Base 检查均未运行。缺完整运行树、资产、历史夹具或目标环境；命令和前提见 runbook。79 项不等于全项目通过，不等于 HTTP 分页、详情、枚举、全部计划 key、长期容量已验收。

原 deploy/qiuzhao-deploy-manifest.json 保持不变；其 normalize 冻结 SHA 将与修复文件不同，原部署/交付门应继续拒绝。必须独审最终字节后明确更新涉及环境的冻结清单，并将新 normalization_io.py 纳入清单，而不是删除检查或把本地测试当审查 PASS。10/1 特例绑定旧 normalize SHA，修复后该特例也应 fail closed，不更新其硬编码身份来绕过。

## 独立审查清单

审查者需针对最终提交/补丁与 SHA 确认：逐条转换语义与原业务函数一致；严格输入变化可接受；坏尾部不提交；源/候选身份、并发和 Windows 句柄约束；新重试中 exit 0 与校验屏障的中断顺序；不改变原预算和计划；缺资产状态如实保留；新依赖部署冻结；真实故障重放及必要目标回归。审查结论只签对应最终字节，修改后重新审核。


## 第二轮：真实故障证据与独审整改

证据提交 `qiuzhao-lzh-handoff@59f110f0940562bed92d55d52b9396f7f4388afa` 已读取 README、独审、完整 normalize.log、receipt、依赖/staging 观测、资产指纹与 manifest。该证据更新了上文“生产根因未归因”的旧状态。

**直接失败已确认。** 第7段 traceback 为 `normalize.py:424 json.load(f)` → `json/__init__.py:293 fp.read()` → UTF-8 codecs decode → `MemoryError`。直接失败点是旧实现整文件读取/文本解码时的内存分配，不是字段规则异常。receipt 显示第7段 P1 partial，normalize=1 后 staging 回滚、publication blocked、collection stopped；前6次 normalize 均成功且 `tables_loaded=false`。因此缺 `normalize_tables.json` 不是该 MemoryError 的直接证据，本轮不安装历史表。

20:54 只读观测的回滚后 staging 为 806,915,187 bytes，SHA256 `372f47f330645d92aa37d1b96cd3c94700333c72297aacb04b86275d5a2024fa`，size/mtime 前后稳定且未观察到匹配 collector Python 进程；它**不证明与失败瞬间输入逐字节相同**。历史 RAM/pagefile 压力没有收据，所以只确认“整文件 read/decode 时内存分配失败”，不推断当时为什么内存不足。

独审 Medium 1 已整改：长对象改为增量扫描字符串、转义和嵌套 `{}`/`[]` 边界，完整对象只交给严格 JSON decoder 一次；记录上限、严格 JSON、坏尾部、源漂移和原子提交保护保留。新增多 MB 中文/emoji/引号/反斜杠/嵌套记录，直接断言 `raw_decode` 每条只调用一次；另测长合法首记录 + 截断坏尾部整批不提交。

独审 Medium 2 已整改：安全身份集合新增 `deploy/windows_recover_run.py`，并绑定 `deploy/deploy_manifest.py`、`deploy/windows_rebase.py`、`qiuzhao/collector/p1_pipeline.py` 等实际安全依赖。新增 `windows_normalize_retry` 部署环境，但当前条目故意全部 pending/null；`--apply` 必须同时通过独立目标字节 manifest 与仓库 frozen manifest 的 `require_frozen=True`。测试证明旧 manifest 缺该环境会拒绝；即使独立目标 manifest 更新，修改安全依赖后旧 frozen manifest 仍拒绝。没有自动刷新 PASS。

第二轮网页沙盒聚焦测试为 **84 passed**。旧 head 的独立 GPT-6.1 Sol low 审查记录仍是：新测试79 PASS；company/business_value/portable-lock 60 PASS + 1 skip；graduation/location 因受限目录缺真实 `export_csv/tools` 未收集。仓库已确认这些真实模块存在，但当前网页容器 GitHub clone 因 DNS 失败，无法物化完整 checkout，因此缺失组和完整既有回归仍必须在精灵真实 checkout 执行；不使用占位 stub 冒充通过。第二轮是新字节，旧独审不覆盖。

仍待目标验证：真实 Windows 锁竞争、Scheduler unknown/queued/running、NTFS ACL/replace、子进程 timeout/termination、当前 staging 隔离重放及峰值内存。normalize-only 边界不变：不重采、不重置预算、不延截止、不发布、不调用 Base。

## 2026-10-08 本机最新字节整改（第三轮）

独立审查真实复跑 b8b0bd9 得到聚焦 **74 passed / 10 failed**，不是网页沙盒记录的84通过。根因是 `normalization_io.iter_records.peek` 的字符集合写成字面反斜杠和t/r/n，拒绝实际JSON换行/tab/CR，却接受非法尾随n/t/r/反斜杠。

本轮在完整qiuzhao/deploy/tests/docs稀疏检出、真实模块与现有项目venv上最小修正为实际space/tab/CR/LF。新增10个实际空白边界用例（五种空白×chunk1/7）及7个非法尾随字符/字面转义用例；后者调用真实normalize_path并核输入字节不变、无残留候选文件。原84项保留，未删/skip/放松断言。

实际命令：`PYTHONDONTWRITEBYTECODE=1 /Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_normalization_io.py tests/test_windows_normalize_retry.py`。结果 **101 passed / 0 failed / 0 skipped**，0.53s；私有 `phase-20261008/pr27-whitespace-focused.log` 与 exit=0收据。`git diff --check`通过。该结果证明本机聚焦范围，Scheduler/runner测试stub边界仍沿原说明。

待核仍包括：修复后最终字节独审、完整checkout既有回归与冻结清单两个新增漂移问题、真实Windows隔离重放/NTFS/锁/Scheduler/超时/峰值内存。部署环境pending/null仍原样拒绝，不机械刷新PASS；本轮未安装、采集、重试--apply、发布或改服务。生产额外35来源的真实配置须保留，不能用main占位配置全树覆盖。

## 2026-10-08 目标环境实测与最终字节

已有生产1124名称/3372scope配置已纳管，源配置SHA `3b2dedf9e86c1af0557b7dbaf4919a62afca0aa8d1fc00402eef7f664c6078d1` 与运行机原件一致，独立配置审查通过；此为现状范围，不是新增来源。collector/retry/delivery的归一化依赖已协调冻结，delivery强制包含新增normalization_io，缺依赖负测通过；合法缺失的normalize_tables继续缺失，未安装历史表。

真实精灵D隔离输入来自最新10/8 run，一次流式稳定复制：814080217字节，SHA `107859a9e4331fe720d2e43167f3a32346601c2cf23c8010fef170e8992b5b8a`，178833条。真实业务check229.782秒/峰值工作集31535104字节；完整归一化258.485秒/30138368字节，输出SHA `f6f9ada9879cd377d6ccde2dc1ea62bf3b3eb4f1ee0e8a4e354491ba5b43039b`。两者tables_loaded=false，填充3240、既有字段变化567；这些计数不表示新增岗位。

原位流式黄金对照：ID/记录顺序保持，297条无ID历史记录保留，重复ID余量0；非归一化字段原位不变，全部变化记录的完整dict与捕获旧normalize_records真实函数一致。变化297条，不用ID相等单独证明匿名语义；发布仍须沿原受审匿名/重复ID保护。

真实msvcrt跨进程争锁拒绝/解锁后成功，NTFS共享句柄导致替换WinError5时原件SHA不变且候选清理，关闭句柄后替换成功；实际无害父子进程timeout返回124、完整进程树终止。Daily仅只读确认COM state3；unknown/queued/running/error由实际解析函数、模拟COM返回的9个新增回归覆盖，未改生产任务。

D原锁/真实子进程/最终冻结门下normalize-only inspect0/apply0，真实终态normalized-not-published，输出仍f6f9ada；原basic/tencent/P1、预算、deadline、completed_at、collection stopped、delivery pending及P1status字节保持。D-only审查manifest仅用于D，不得用于C。

最终本机IO/retry/冻结门/Scheduler为124 passed、0 skipped；Windows同组123 passed、1 skipped，唯一POSIX mode bits不适用，NTFS实测另列。完整Git历史同D扩展：head22 failed/326 passed/39 skipped，base22 failed/325 passed/39 skipped，新增失败0。安全类旧用例分别留失败原因：Linux receiver fcntl不适用于Win；P1 timeout/跨进程锁未被本次normalize-only路径调用，C阶段仍需按真实源链收口，不笼统称全部安全门通过。

MCP正式执行环境是Linux。Win本地HTTP因既有/dev/fd不支持而失败，不为跨平台绿灯改MCP层；同100条当前真实代表数据在Mac POSIX真实uvicorn/MCP七调用与in-process逻辑完全一致，服务已停止。旧9/11历史fixture仍未取得；已找到的9/10 9191条不是该fixture，未冒充。该小样HTTP不是全库或旧验收替代。

最终代码/目标环境独审已允许限定五文件C安装及normalize-only，仍需实时原锁、writer/Scheduler、真备份、前后身份条件。此文是安装前验证回执，不是生产安装或三层交付完成；后续实际终态仅维护唯一日更正文。
