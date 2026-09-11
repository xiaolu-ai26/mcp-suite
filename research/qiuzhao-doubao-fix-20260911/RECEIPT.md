# 秋招 MCP 豆包参数修复：收据

执行时间：2026-09-11 21:20–21:50（北京时间）。执行会话只在本地实现和测试，没有部署，没有向服务器写入任何东西。SSH 只执行了只读命令（sha256sum、stat、find、ls、systemctl show/is-active、ps，以及用 rsync 从服务器往本地拉取）。

## 1. 结论

发布包 A 修掉了根因。jobs_search 的 11 个字符串参数和 bench_search 的 6 个字符串参数，schema 从 `anyOf[string,null]` 变成了顶层 `"type":"string"`，两个产品的 tools/list 中 `anyOf` 从 11 处和 6 处都降为 0。不传、传 null、传值都能通过校验。返回结果新增 `applied_filters`，每次工具调用会在 stderr（即 journald）记一行：工具名、参数名、UA。默认 limit 改成 10，一次调用的 HTTP 响应体从 225,213 B 降到 53,600 B。

发布包 B 在 A 之上把参数收敛到 10 个，并把 job_category、graduation_year 改成对归一化字段精确匹配。代码和测试都通过了，但对比表里有两项差异超过 10%，根因都在数据归一化（见第 8 节）。**建议先只上 A**，B 等 Max 决定归一化怎么处理后再上。

## 2. 基线与拉取

线上 sha256 在开工时（21:21）和收尾时（21:48）各核对一次，都等于给定值，期间未变：
- `core/server.py` = `08143798a78ca401be294c7d3425b7f6398cd200cf93bf57b12a0e31f191dccd`
- `qiuzhao/tools.py` = `77ffdb613a746636314e31786b2a451b57dd061670abba2542695e406ece0d52`

`live-baseline/` 是用 rsync 从服务器拉到本地的（方向 server→local），共 52 个文件，清单在 `live-baseline/SHA256SUMS`，收尾时 `shasum -c` 全部通过。排除项：`.venv/`、`__pycache__/`、`*.pyc`、`data/`、`logs/`、`private/`、`*.sqlite3*`、`deploy/backup-*`、`missing_queries.jsonl`。另外还排除了以下几类，都没有拉：`python/`（服务器自带的 CPython 解释器）、`*.bak*` 和 `core/static/backups/`（备份副本），以及 `deploy/deployment-receipt.json`、`deploy/final-online-e2e-receipt.json`（在服务器上只统计了匹配次数，各有 1 处疑似 token 的字样，没有读取内容）。拉完后扫描本地文件，没有 `qz_`/`bm_` 形态的 key，也没有 `QZ-`/`BM-` 形态的兑换码。

数据文件 `data/jobs.json` 取自 `/var/lib/mcp-suite/jobs.json`，sha256 `d9cc6c7c…c002`，81,814,583 B，mtime 9/11 15:25:58。共 28,616 行，经 load() 过滤后 27,506 条有效，68 个字段。没有读取或拉取 access.sqlite3、distribution.db、missing_queries.jsonl、任何兑换码文件，也没有读取 systemd 环境变量的值（显示时已打码）。

## 3. 服务器现状（只读）

**2026-09-10 16:00 以来改动的文件**（`find -newermt`，已排除 .venv 和 __pycache__）：
- 代码：`core/server.py`（9/11 18:50）、`core/store.py`（18:46）、`core/distribution.py`（16:11 新建）、`qiuzhao/tools.py`（15:14）、`qiuzhao/collector/run.py`（12:28）、`auto_collect.py`（12:29）、`export_csv.py`（12:30）、`tencent.py`（9/10 16:02）。
- 静态文件：`core/static/index.html`、`app.js`（20:11）、`site.css`（19:41）、`guide.html`（18:52）、`admin.html`、`admin.js`（20:20）、`admin.css`（18:38）、`changelog.json`（16:12）、`wechat-qr.png`（15:51）、`img/guide/*` 6 张（18:48）。**20:20 仍有人在改线上静态文件**，本方案只替换两个 .py 文件，不会覆盖这些改动。
- 备份：`core/*.bak.*`（server.py 5 份、store.py 2 份）、`core/static/*.bak.*` 和 `core/static/backups/`、`qiuzhao/tools.py.bak.*` 2 份、`collector/run.py.bak`；`deploy/backup-*` 共 12 个目录（9/10 16:01–23:22，都含 jobs.json，其中 `backup-pre-v3-release-20260910` 还含 access.sqlite3）。
- `private/access.sqlite3`（9/11 16:12）。

**从 /opt/mcp-suite 运行的服务**（两个服务都跑 `/opt/mcp-suite/.venv/bin/uvicorn core.server:app`，User=mcp-suite，`ReadWritePaths=/var/lib/mcp-suite`）：
- `mcp-suite.service`：qiuzhao，127.0.0.1:8768，PID 1796870，启动于 9/11 18:50:50，与 server.py 最后一次修改在同一秒。
- `mcp-suite-bench.service`：`MCP_PRODUCT=bench`，127.0.0.1:8769，PID 1709267，**启动于 9/10 15:41:36**。内存里还是 9/10 的代码，9/11 对 server.py、store.py、distribution.py 的全部改动它都还没加载。
- `mcp-suite.service.d/override.conf` 注入了 `MCP_DIST_ADMIN_TOKEN`，值没有读取。

**依赖**：线上和本地的 requirements.txt 一致。核心包版本相同：fastmcp 2.14.7、mcp 1.30.0、pydantic 2.13.5、pydantic_core 2.46.5、starlette 1.6.0、uvicorn 0.52.4。差异只有两类：本地多了测试用的 pytest、playwright 等，线上多了 Linux 钥匙串依赖 jeepney、secretstorage；Python 版本线上 3.12.12、本地 3.12.13。因此直接用 `~/Projects/mcp-suite/.venv` 跑测试，没有另建 venv，也没有改动它（收尾检查 .venv 内 21:20 之后的新文件数为 0）。

本地与线上的差异清单见 `local-vs-live.md`。

## 4. 发布包 A（`release-A/`，diff 见 `patches/A.diff`，只改两个文件）

`core/server.py`：
1. jobs_search 的 11 个字符串参数、bench_search 的 6 个字符串参数，改为 `Annotated[str, NoneToEmpty, Field(...)] = ""`，其中 `NoneToEmpty = BeforeValidator(lambda v: "" if v is None else v)`。wrapper 把 `""` 转回 None 再交给数据层，所以 tools.py 的匹配逻辑、缺失查询记录和 bench 的 `filters` 输出都与改前一致（bench 未传的条件仍返回 null）。
2. `job_category` 改为 `Literal["", 15 个值]`，15 个值与数据中 job_category_normalized 的实际取值完全一致，传入时会去掉首尾空格。`graduation_year` 改为 `Literal["", "2027届", "2026届", "2025届", "未披露"]`，这是数据的全部取值，**没有复合值**；BeforeValidator 会把 `2027`、`"2027"`、`"2027年"`、`" 2027 届 "` 统一成 `"2027届"`，None 变成 `""`。A 的匹配逻辑仍是改前的子串匹配。
3. `industry` 描述改为：在 industry / industry_tags 中做包含匹配，并列出高频值互联网/科技、国企/央企、制造/工业、能源/电力、金融、医药/医疗。
4. `MeterTools` 每次工具调用都在 stderr 输出一行 `mcp_tool_call {"tool":…,"args":[排序后的参数名],"ua":前100字符}`。用独立 logger 加 StreamHandler，不依赖 uvicorn 的日志配置；工具名和参数名各截断到 64 字符，参数名最多记 40 个。json.dumps 会转义换行，防止伪造日志行。整段包在 try 里，出错也不影响计费调用。**不记录 Authorization、key 或任何参数值。**
5. jobs_search 的 limit 默认从 50 改成 10，上限仍是 100，返回的字段数不变（每条 33–43 个字段，与改前相同）。
6. qiuzhao 的 instructions 末尾补了规定那句话；jobs_search 的描述补了"默认每次返回10条""applied_filters 是服务端实际使用的筛选条件"。

`qiuzhao/tools.py`：`search()` 的返回里新增 `applied_filters`，内容是服务端实际参与筛选的非空条件，值为规范化并去掉首尾空格后的结果，没有条件时是 `{}`。它放在返回 JSON 的第一个键，这样即使客户端截断长输出也能看到。`search()` 的 limit 默认值也改成了 10，保持一致。

## 5. 发布包 B（`release-B/`，基于 A；diff 见 `patches/B.diff`，同样只改这两个文件）

1. jobs_search 的 MCP 签名删掉 `cohort`、`region`、`major_category`，剩 10 个参数：city、major、keyword、company、recruitment_type、industry、job_category、graduation_year、limit、offset。
2. 旧参数兼容在 `MeterTools` 里做：映射关系是 cohort→graduation_year（同样经过届别规范化）、region→city、major_category→major，只在新参数没传或为空时才映射；否则丢弃旧参数并记为 ignored。映射结果另记一行 `mcp_legacy_args {"tool","mapped":{旧:新},"ignored":[...]}`，同样只有参数名。`Jobs.search()` 仍保留这三个关键字参数，按改前语义工作，供直接调用方和现有测试使用。
3. `job_category` 对 job_category_normalized 精确匹配。`graduation_year` 对 graduation_year_normalized 精确匹配，匹配前会按 `、,，/;；|` 和空白拆分，为将来可能出现的复合值预留；当前数据里没有复合值。`major` 同时匹配 major_requirements_raw、major_tags、major_normalized，描述中列出了 10 个专业大类。
4. jobs_search 的描述加了用法说明：找某类岗位用 job_category，找具体岗位名或单位用 keyword，找公司用 company。

## 6. 测试

测试放在 `release-A/tests/` 和 `release-B/tests/`：`test_core.py` 原样复制自 `~/Projects/mcp-suite/tests/`；`test_doubao_fix.py` 是两个包共用的 14 项；`test_release_a.py` 是 A 专属 3 项；`test_release_b.py` 是 B 专属 8 项；`_mcp_harness.py` 和 `conftest.py` 是测试框架。端到端测试会起一个真实的 `python -m uvicorn core.server:app --no-access-log` 子进程，入口与 service 相同，再用 Bearer key 通过 HTTP 发 JSON-RPC。`MCP_DB_PATH` 和 `MCP_DIST_DB_PATH` 指向 `<工作目录>/tmp/` 下的一次性文件，停止时删除；`MCP_JOBS_PATH` 指向 `data/jobs.json`。收尾已删除整个 `tmp/`。

命令（B 同理，把 A 换成 B）：
```
cd release-A && PYTHONDONTWRITEBYTECODE=1 MCP_JOBS_PATH=../data/jobs.json \
  ~/Projects/mcp-suite/.venv/bin/python -m pytest -p no:cacheprovider -W ignore::DeprecationWarning --basetemp=../tmp/pytest-A -rA -q
```

| 代码树 | 通过 | 失败 | 新增测试 |
|---|---:|---:|---|
| live-baseline（只跑 test_core） | 3 | 7 | — |
| release-A | 20 | 7 | 17/17 通过 |
| release-B | 25 | 7 | 22/22 通过 |

输出文件：`test-output/baseline-test_core.txt`、`test-output/A-pytest.txt`、`test-output/B-pytest.txt`。

**7 个失败在三棵代码树上完全相同，都是改动前就存在的，与本次修改无关**：线上 `store.generate_codes` 往 `redemption_codes.code_plain` 写数据，但 store.py 的 CREATE TABLE 里没有这一列（线上库应是手工加的列），新建的库一调用就报 `OperationalError: table redemption_codes has no column named code_plain`。受影响的是 atomic_redemption、atomic_daily_limit、expiry_product_and_invalid、midnight_resets、qiuzhao_code_and_key_format、bench_plan_thirty_days、quota_message 这 7 项。其中还有断言已经过期：线上 qiuzhao 套餐改成了每日 999999 次、30 天，兑换码也明文落库了。按要求没有改这些断言，也没有改 store.py。端到端测试的框架只在一次性测试库上补了 `code_plain` 列，用来模拟线上库结构。

新增测试覆盖了以下内容：
- 两个产品所有工具的 inputSchema 里没有 anyOf/oneOf/allOf，每个属性都有字符串形式的顶层 type。
- 枚举与数据的取值集合完全相等。
- 不传、全部传 null、传值三种情况都成功。
- applied_filters 正确，包括 `2027` 转成 `2027届`、空白关键词不计入。
- 枚举外的值报错。
- limit 默认 10，传 100 可以，传 101 报错。
- 列表记录与 jobs_detail 返回的记录完全相等，即字段没有瘦身。
- industry 的描述已更新，并且能筛出结果。
- instructions 含 applied_filters 那句话。
- 日志行只含参数名，UA 截断到 100 字符，日志里不出现 token、`Bearer` 字样或测试注入的哨兵值。
- bench_search 传 null 与不传结果一致，filters 仍是 null。
- B 专属：参数正好 10 个；精确匹配的 total 等于数据中的分面计数（产品 939、技术/研发 13,512、2027届 13,895）；三个旧参数名映射后的结果与直接用新参数一致；新旧参数同时传时丢弃旧参数；无法映射的 cohort 值会明确报错；未知参数被 FastMCP 拒绝。

## 7. tools/list 与字节数

生成方式：`scripts/dump_tools_list.py <代码树> <标签>`。脚本从对应代码树起 uvicorn（qiuzhao 用 data/jobs.json，bench 用一个 2 条记录的测试数据），通过 HTTP 发 `tools/list` 和 `tools/call`，把 JSON-RPC 的 `result` 原样写入文件。产物：`tools_list_A.json`、`tools_list_B.json`（qiuzhao），`tools_list_A.bench.json`、`tools_list_B.bench.json`；作对照的 `tools_list_baseline*.json`；字节统计在 `evidence/sizes_{baseline,A,B}.json`。

| | 默认调用 | HTTP 响应体 | 结果 JSON（structuredContent） | 条数 | tools/list 中的 anyOf（qiuzhao/bench） |
|---|---|---:|---:|---:|---|
| 线上基线 | limit=50 | 225,213 B | 108,840 B | 50 | 11 / 6 |
| A | limit=10 | 53,600 B | 25,903 B | 10 | 0 / 0 |
| B | limit=10 | 53,600 B | 25,903 B | 10 | 0 / 0 |

FastMCP 会把同一份结果发两遍，一份放 content 文本、一份放 structuredContent，所以 HTTP 响应体约为结果 JSON 的 2 倍。按"不瘦身"的决定，这一点没有处理。

另有进程内的 schema 核验：`scripts/verify_schema_snippet.py`，结果在 `evidence/verify_schema_local.txt`。基线两个产品都是 `RESULT FAIL`（jobs_search 有 11 个参数缺 type，bench_search 有 6 个）；A、B 两个产品都是 `RESULT OK`。部署后核验用的也是这个脚本。

## 8. 调用日志证据（uvicorn 实跑）

日志来自 `evidence/pytest-A-uvicorn-qiuzhao.log`、`evidence/pytest-B-uvicorn-qiuzhao.log`，与 uvicorn 自己的 INFO 行交错输出在同一个 stderr 里：
```
INFO:     Uvicorn running on http://127.0.0.1:58381 (Press CTRL+C to quit)
mcp_tool_call {"tool": "jobs_search", "args": ["city", "graduation_year", "job_category", "keyword", "limit"], "ua": "doubao-fix-harness/1.0"}
mcp_tool_call {"tool": "jobs_search", "args": ["city", "keyword", "limit"], "ua": "DoubaoWork/9.9 xxxxxxxx…(截断至100字符)"}
mcp_tool_call {"tool": "bench_search", "args": ["platform"], "ua": "doubao-fix-harness/1.0"}
mcp_tool_call {"tool": "jobs_search", "args": ["cohort", "limit"], "ua": "doubao-fix-harness/1.0"}      ← B
mcp_legacy_args {"tool": "jobs_search", "mapped": {"cohort": "graduation_year"}, "ignored": []}      ← B
mcp_legacy_args {"tool": "jobs_search", "mapped": {}, "ignored": ["cohort", "region"]}               ← B
```
对全部 evidence 日志扫描 key 形态、`Bearer`、哨兵值以及测试中用到的城市值，命中数都是 0。线上 unit 没有设置 StandardError，按 systemd 默认 stderr 进 journald，部署后用 `journalctl -u mcp-suite.service | grep mcp_tool_call` 就能看到。

## 9. FastMCP 2.14.7 收到未知参数时的行为

**不会忽略，而是直接报错。** 返回 `isError`，内容是 pydantic 的 `Unexpected keyword argument [type=unexpected_keyword_argument]`。实测脚本和输出在 `probes/probe_unknown_param.py`、`probes/probe_unknown_param.out.txt`，B 的端到端测试 `test_unknown_parameter_is_rejected_by_fastmcp` 也通过 HTTP 验证过。所以 B 删除参数后，中间件映射是必需的，否则旧客户端传 cohort/region/major_category 会直接失败。枚举外的值同样报 `literal_error`，并列出允许的取值。

## 10. 前后对比表（`data/jobs.json`，对比基线逻辑与 B 逻辑）

脚本 `scripts/compare_totals.py` 在两个独立解释器里分别调用各自代码树的 `Jobs.search`（即 MCP 工具实际调用的函数），结果在 `evidence/compare_totals.{md,json}`，差异明细在 `evidence/gap_breakdown.txt`。

| 条件（基线 → B） | 基线 total | B total | 差值 | 差异% |
|---|---:|---:|---:|---:|
| job_category=产品 | 1,310 | 939 | −371 | **−28.3%** |
| job_category=技术/研发 | 13,512 | 13,512 | 0 | 0% |
| cohort=2027 → graduation_year=2027届 | 18,480 | 13,895 | −4,585 | **−24.8%** |
| major_category=计算机类 → major=计算机类 | 4,831 | 4,831 | 0 | 0% |
| region=北京 → city=北京 | 6,325 | 6,325 | 0 | 0% |
| keyword=产品 | 9,733 | 9,733 | 0 | 0% |

两项超过 10% 的差异中，B 的结果都是基线的子集（只有基线命中、B 没命中的记录分别是 371 条和 4,585 条，B 没有多出任何记录）。

**job_category=产品（−371）**：这 371 条的 job_category_normalized **全部是"技术/研发"**，而原始 job_category 是"产品"160 条、"产品经理"149 条、"产品运营"16 条、"产品类"12 条、"高级产品经理"10 条等，其中 362 条明显是产品岗；来源以字节跳动为主（305 条），其次是国聘 26 条。简报里说"多出的是'金融产品经理'这类原文命中"，与数据不符：多出的主要是**被归一化错分到技术/研发的真实产品岗**。B 改成精确匹配后会丢掉这些岗位。

**cohort=2027 → graduation_year=2027届（−4,585）**：
- 4,266 条的 cohort_raw 为空，只有招聘活动标题写了 2027（如"中国联通2027校园招聘""中国航天科工…2027届校园招聘"），归一化结果是"未披露"。基线对这类记录标注的 `cohort_filter_scope` 就是 `campaign_title_only`。
- 319 条原文写的是"2026届未就业及2027届"或"2027应届、2026届"，同时面向两届，但归一化只保留了一个"2026届"。这属于把复合值压缩成了单值，B 的拆分匹配也救不回来。

反向核对：归一化为 2027届、而基线 cohort=2027 没有命中的记录为 0 条。

## 11. 未解决的问题

**需要 Max 决定的：**
1. **B 的上线时机。** B 的精确匹配结果完全取决于归一化质量（见第 10 节）。可选方案：(a) 先上 A，修好归一化后再上 B：把原文"产品/产品经理"类映射到"产品"，届别保留多值，活动标题里的届别是否算作届别由 Max 定口径；(b) B 里 job_category 继续用 A 的包含匹配；(c) 接受 B 的口径变化。
2. **bench 服务要不要重启。** bench 与 qiuzhao 共用 `/opt/mcp-suite/core/server.py`。bench 进程从 9/10 15:41 跑到现在，一旦重启，除了 bench_search 的 schema 修复，还会同时加载 9/11 所有未加载的 server.py、store.py、distribution.py 改动（管理后台、分销路由、套餐调整等）。部署方案里默认**只重启 mcp-suite.service**；但 bench 以后任何一次重启（崩溃自动拉起或服务器重启）都会加载新文件。

**已知但本次不改的：**
3. 枚举是写死的。数据以后出现新取值（如 2028届、新的岗位大类）时，传这些值会报参数错误，直到更新枚举为止。`test_enums_and_limit` 会在本地跑测试时发现枚举与数据不一致。
4. 线上 store.py 的建表语句与写入的列不一致（`code_plain`），导致现有 7 个测试失败。另外兑换码以明文写入 redemption_codes，并通过 `/api/admin/codes` 返回，与 store.py 文件头的注释"Never persist … redemption codes"相矛盾；`_dist_admin_ok` 允许用 URL 参数 `?token=` 传管理令牌，令牌可能进入 nginx 访问日志。这些在禁改范围内，没有动，只在这里记录。
5. `Jobs.load()` 每次调用都重新读取并解析 81 MB 的 jobs.json，没有缓存。客户端连续重试几十次，就是几十次全量解析。
6. 数据里有 1,492 个 id 重复出现（多出 2,043 行，主要来自国聘），按 id 调 jobs_detail 可能返回多条。
7. 豆包客户端本身没有实测。本地只证明了 schema 里已没有 anyOf、缺省和 null 都可用；豆包是否真的带上参数，要在部署后由 Max 在豆包里查一次，再看 journald 里的 `mcp_tool_call` 行确认。
8. 行为变化提醒：
   - A 起枚举外的值会直接报错，例如 job_category="产品经理" 改前按子串匹配有结果，现在会返回可选值列表。
   - 所有客户端（包括 Claude Code）默认只返回 10 条，需要翻页。
   - B 里 cohort 传的若不是届别写法（如"2027届校园招聘"），映射到 graduation_year 后会报参数错误，不再按子串匹配；日志里仍记为 mapped。
9. 简报里"归一化为产品的 987 条"是按 28,616 条原始行统计的；经 load() 过滤后是 939 条。

## 12. 部署方案（只写，未执行；需 Max 看过 diff 同意后执行）

A 需要替换的只有两个文件。A 的目标 sha256：server.py `de5cadb3ced55f3d3f4041aa5d523ae997706d467d6ce9bc106b1a948a04fb39`、tools.py `8dce3fe6b4b3bdb70feac65b2a78e03153b6febd7b93b468d1045b6f61a5e5ec`。B 的目标：server.py `e8bf7390023cf121e2d661e652ea95fa9efa512c218f107773f13f5bbf98e4af`、tools.py `f2c19c4b0bf837aa671c6fc0cf2c613a6eccc5b48657d29d2d2b417e7c6d21e5`。全部哈希见 `evidence/release_sha256.txt`。

```bash
REL=A                                   # 或 B（B 的两个文件本身已包含 A 的改动）
W=~/Projects/mcp-suite/research/qiuzhao-doubao-fix-20260911
LOCAL=$W/release-$REL
H=root@114.215.188.109
TS=$(date +%Y%m%d-%H%M%S)
BK=/opt/mcp-suite/deploy/backup-pre-doubao-fix-$TS

# 1) 部署前核对：线上必须仍等于基线，否则立即停止
ssh $H 'sha256sum /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py'
#    期望 08143798…1dccd 和 77ffdb61…e0d52

# 2) 备份要替换的两个文件
ssh $H "mkdir -p $BK && cp -p /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py $BK/ && cd $BK && sha256sum server.py tools.py | tee SHA256SUMS"

# 3) 只同步这两个文件（先 dry-run 看清单；-a 保持与现有文件相同的 501:staff、644 属主和权限）
rsync -a --checksum --itemize-changes --dry-run $LOCAL/core/server.py  $H:/opt/mcp-suite/core/server.py
rsync -a --checksum --itemize-changes --dry-run $LOCAL/qiuzhao/tools.py $H:/opt/mcp-suite/qiuzhao/tools.py
rsync -a --checksum --itemize-changes $LOCAL/core/server.py  $H:/opt/mcp-suite/core/server.py
rsync -a --checksum --itemize-changes $LOCAL/qiuzhao/tools.py $H:/opt/mcp-suite/qiuzhao/tools.py
ssh $H 'sha256sum /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py; stat -c "%U:%G %a %n" /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py'
#    期望等于上面列出的目标 sha256

# 4) 重启 qiuzhao 服务（bench 默认不动，见第 11 节第 2 条）
ssh $H 'systemctl restart mcp-suite.service; sleep 5; systemctl is-active mcp-suite.service; journalctl -u mcp-suite.service --since "-2 min" --no-pager | tail -20'

# 5) health 检查
ssh $H 'curl -s http://127.0.0.1:8768/health'      # 期望 {"status":"ok","jobs":27506,...}
curl -s https://savegems.top/qiuzhao/health

# 6) 线上 schema 无 anyOf 的核验：在服务器上 import 代码，不起 HTTP、不用 token；
#    MCP_DB_PATH 指向 /tmp 下的临时文件，用完删除，不碰生产 DB；脚本经 stdin 传入，不在服务器落文件
ssh $H 'cd /opt/mcp-suite && T=$(mktemp /tmp/doubao-verify-XXXXXX) && PYTHONDONTWRITEBYTECODE=1 MCP_PRODUCT=qiuzhao MCP_DB_PATH=$T.sqlite3 MCP_DIST_DB_PATH=$T-dist.db MCP_JOBS_PATH=/var/lib/mcp-suite/jobs.json .venv/bin/python -W ignore - ; rm -f $T $T.sqlite3 $T.sqlite3-wal $T.sqlite3-shm $T-dist.db; ls /tmp/doubao-verify-* 2>/dev/null || echo tmp-cleaned' < $W/scripts/verify_schema_snippet.py
#    期望：jobs_search params=13（B 为 10）anyOf/oneOf=False missing_type=[]，最后一行 RESULT OK []
#    查 bench 代码时，改成 MCP_PRODUCT=bench MCP_BENCH_PATH=/var/lib/mcp-suite/bench.json（只检查文件，不重启 bench 进程）

# 7) 实际效果观察：Max 用自己的 key 在豆包工作里查一次"产品"岗位
ssh $H 'journalctl -u mcp-suite.service --since "-10 min" --no-pager | grep -E "mcp_tool_call|mcp_legacy_args"'
#    看 args 里有没有 job_category 等参数名，ua 是哪个客户端；返回里的 applied_filters 应与提问一致
```

**回滚**（在同一个 shell 里执行，需要保留 `$BK` 变量）：
```bash
ssh $H "cp -p $BK/server.py /opt/mcp-suite/core/server.py && cp -p $BK/tools.py /opt/mcp-suite/qiuzhao/tools.py && sha256sum /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py && systemctl restart mcp-suite.service && sleep 5 && systemctl is-active mcp-suite.service && curl -s http://127.0.0.1:8768/health"
#    期望 sha256 回到 08143798…1dccd / 77ffdb61…e0d52，health 返回 ok
```
如果在回滚之前 bench 已经被重启过，也要执行 `systemctl restart mcp-suite-bench.service`，让它加载回滚后的文件。

## 13. 产物清单（均在 `~/Projects/mcp-suite/research/qiuzhao-doubao-fix-20260911/`）

- `live-baseline/`（52 个文件和 `SHA256SUMS`）、`data/jobs.json`、`local-vs-live.md`
- `release-A/`、`release-B/`（完整代码树，含 `tests/` 和 `pytest.ini`；本地运行没有写入 `__pycache__`）
- `patches/A.diff`（基线→A，210 行）、`patches/B.diff`（A→B，128 行）：只包含两个会部署的运行时文件；测试代码在各自的 `tests/` 目录里
- `tools_list_A.json`、`tools_list_B.json`、`tools_list_A.bench.json`、`tools_list_B.bench.json`，以及对照用的 `tools_list_baseline*.json`
- `test-output/`（三次 pytest 的完整输出）、`evidence/`（uvicorn 日志、字节统计、对比表、差异明细、schema 核验、哈希）、`probes/`（FastMCP 未知参数实测）、`scripts/`（dump_tools_list、compare_totals、verify_schema_snippet）
