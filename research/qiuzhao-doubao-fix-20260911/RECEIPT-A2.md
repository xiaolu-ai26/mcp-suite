# 秋招 MCP A2 / A2d：收据

执行时间：2026-09-11 22:13–22:40（北京时间）。执行会话只在本地实现和测试，没有部署，没有向服务器写入任何东西。SSH 只执行了只读命令（sha256sum、systemctl show、ls、command -v、getent、df）。没有修改 `release-A/`、`release-B/`、`live-baseline/`、任何 static 文件和 `store.py`，也没有改动 `~/Projects/mcp-suite` 的 core/、qiuzhao/、private/、deploy/、.venv（收尾检查这些路径在 22:13 之后新增或修改的文件数为 0）。

## 1. 结论

- **A2** = A + 结构化调用日志，只改了 `core/server.py`，`qiuzhao/tools.py` 与 A 字节相同。
- **A2d** = A2 + jobs_deadlines 默认 10 条、按截止日从近到远排序，改了 `server.py` 里的 `jobs_deadlines` 和 `tools.py` 里的 `deadlines()`。

| 代码树 | 通过 | 失败 | 新增/改写的测试 |
|---|---:|---:|---|
| release-A2 | 30 | 7 | 12/12 通过 |
| release-A2d | 33 | 7 | 16/16 通过 |

7 个失败与 A 完全相同：都是 `test_core.py` 里的 `code_plain` 列问题，改动前就存在，按要求没有修。线上 sha256 在开工（22:13）和收尾（22:36）各核对一次，都等于基线，期间未变。

A2d 已包含 A2 的全部改动。若两项都要上，直接部署 A2d 即可。

## 2. 改了什么

### A2（`patches/A2.diff`，release-A → A2，239 行）

1. 删除了 A 在 stderr 输出的 `mcp_tool_call` 行和对应的 logging handler。
2. `MeterTools` 在 `finally` 里调用 `log_tool_call`，所以成功、参数校验失败、工具异常、扣次失败都会各记一行。鉴权、扣次的顺序和返回给客户端的错误文案都没有变。
3. 写入方式：每次调用追加一行 JSON 到 `$MCP_CALL_LOG_DIR/tool_calls-YYYYMMDD.jsonl`。
   - 目录默认 `/var/lib/mcp-suite/call_logs`，文件名里的日期取 `ts` 的北京日期。
   - 目录不存在时自动创建，权限 700；文件用 `O_APPEND|O_CREAT`、权限 600 打开。
   - 整行编码后在进程锁内用一次 `os.write` 写完，遇到部分写入会循环补写。所以同一进程并发调用时，行不会被截断或交错；bench 与 qiuzhao 两个进程共写一个文件时，靠 O_APPEND 保证整行写入。
   - 每次写入都重新打开文件，所以跨日换文件、日志被外部轮转或删除都不需要额外处理。
4. 日志失败绝不影响工具调用：写日志的整段代码包在 try 里，永远不抛异常。写不进去时，每个进程只在 stderr（journald）打一行 `mcp_call_log_warning {"error": "PermissionError", "dir": "…"}`。
5. 凭据防护。Authorization 头从来不进入记录内容。另外对参数值、参数名和 UA 先脱敏、再截断，这样截断不会留下半截凭据：
   - 当前请求的 token 原文替换为 `[redacted]`；
   - `Bearer xxx`，以及 PLANS 里定义的 key 前缀（`qz_`/`bm_`）和兑换码前缀（`QZ-`/`BM-`）后跟 16 位以上的串，不分大小写，替换为 `[redacted]`；
   - 参数名含 token、auth、secret、passw、api_key、redemption，或名字恰好是 key、code 的，整个值记为 `[redacted]`。
   这是为了应对客户端把 key 或兑换码误填进参数的情况。
6. **stderr 不再保留逐次调用记录**。权威记录只保留 JSONL 文件一处。journald 有自己的保留期，`adm`/`systemd-journal` 组都能读，如果再写一份带参数值的记录，会形成一份更难管控的副本。代价是日志目录写不进时，这段时间没有逐次记录，因此部署步骤里预建目录，并在第一次调用后立即核对（第 9 节第 3、8 步）。

### A2d（`patches/A2d.diff`，A2 → A2d，41 行）

- `tools.py` 的 `deadlines()`：
  - `limit` 默认从 100 改为 10；
  - 排序改为按 `(截止日期, 截止原值, id)` 升序，今天截止的排最前，`id` 为空时按空串处理；
  - 返回的 `order` 从 `deadline_desc` 改为 `deadline_asc`。
- `server.py` 的 `jobs_deadlines`：
  - `limit` 默认 10，上限仍为 100，补了描述"每页条数，默认10，最大100"；
  - 工具描述改为"按截止日期从近到远排序，今天截止的排在最前……默认每次返回10条，可用offset翻页"。
- 没有改纳入哪些 deadline_type，也没有加筛选参数。
- 同一份数据下的效果：
  - 基线默认调用返回 100 条，截止日从 9/18 排到 9/16；
  - A2d 默认返回 10 条，全部是今天（9/11）截止的，今天共 33 条；
  - total 都是 456。
- 线上 `app.js` 的示例提示词本来就写"按截止日期从近到远排序"，与新行为一致，不需要改页面。

### 测试改动（`patches/A2.tests.diff`、`patches/A2d.tests.diff`）

- `_mcp_harness.py`：
  - 每个测试服务器用一次性的 `MCP_CALL_LOG_DIR`（位于 `tmp/` 下，不预建，验证由服务端自己创建）；
  - 可以用第二把 key 或额外请求头调用；
  - 停止时把 uvicorn 日志和调用日志复制到 `evidence/<A2|A2d>/` 后删除临时文件。
- `test_doubao_fix.py`：A 里按"stderr 只含参数名"写的两个测试，改为读取 JSONL 并核对参数值。
- A2d 的 `test_core.py`：`test_jobs_preserve_facts_and_deadline_order` 断言的就是旧的倒序，这次需求直接改变了它，所以把期望从 `['1','0']` 改成 `['0','1']`，并加了注释。其余 7 个失败的测试没有动。

## 3. 日志格式

每行一个 JSON 对象，字段固定为以下 11 个。

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | string | 调用开始时刻，北京时间 ISO 8601，精确到毫秒并带 `+08:00`；文件按这个日期分 |
| `product` | string | `qiuzhao` / `bench`，即 MCP_PRODUCT |
| `tool` | string | 工具名，最多 64 字符 |
| `args` | object | 客户端**实际发送**的参数名和值：记录校验和规范化之前的值，不补默认值，所以 `graduation_year: 2027` 保持整数，null 保持 null。字符串截断到 200 字符；列表保留前 20 项，后接 `"…(+N)"`；字典保留前 20 个键，另加 `"…": "+N"`；嵌套超过 2 层记为 `"<list>"`/`"<dict>"`；参数最多记 40 个（按名称排序）；整行超过 64 KiB 时，每个值退化为最多 200 字符的 JSON 文本。凭据形态的内容替换为 `[redacted]` |
| `ua` | string | User-Agent 前 100 字符，同样脱敏 |
| `user_ref` | string/null | 12 位十六进制的匿名标识（见第 4 节）；取不到时为 null |
| `outcome` | string | `ok` / `error` |
| `error_type` | string/null | ok 时为 null。error 时是简短类型：`invalid_arguments`（参数校验失败，包括枚举外的值、超长、未知参数）、`quota_exceeded`、`access_denied`、`unknown_tool`，工具内部异常则记异常类名（如 `FileNotFoundError`）。不记消息，不记堆栈 |
| `result_total` | int/null | 结果里的 `total`：jobs_search、jobs_deadlines、bench_search 有；jobs_detail、bench_detail、bench_taxonomy 和 error 时为 null |
| `returned` | int/null | 本次返回条数，即 `jobs` 或 `records` 的长度；bench_taxonomy 和 error 时为 null |
| `duration_ms` | int | 从进入中间件（扣次之前）到调用结束的毫秒数 |

样例（取自 `evidence/A2/call_logs-release-A2-qiuzhao/`，user_ref 已打码，UA 已缩短）：
```
{"ts":"2026-09-11T22:32:35.064+08:00","product":"qiuzhao","tool":"jobs_search","args":{"city":null,"graduation_year":2027,"keyword":"产品","limit":3},"ua":"TruncUA/1.0 uuu…","user_ref":"192a••••8d10","outcome":"ok","error_type":null,"result_total":5914,"returned":3,"duration_ms":534}
{"ts":"2026-09-11T22:32:35.611+08:00","product":"qiuzhao","tool":"jobs_search","args":{"api_key":"[redacted]","city":{"c0":0,…,"c19":19,"…":"+10"},"company":"见 [redacted] 或 [redacted] 或 [redacted]","keyword":["k0-vvv…(200字符)",…,"…(+10)"],"limit":1},"ua":"BoundsUA/1.0","user_ref":"192a••••8d10","outcome":"error","error_type":"invalid_arguments","result_total":null,"returned":null,"duration_ms":…}
```
第二行是测试故意传入的：company 里含真实 token、`Bearer abc.def` 和一个兑换码形态的串，还有一个未知参数 api_key，以及 30 项的列表和 30 个键的字典。测试日志平均每行 471 B（测试里有意用了很长的 UA 和参数），正常调用一行约 250–350 B。

## 4. user_ref 的来源与不可逆性

**来源**：`store.py` 在兑换时为每把 key 生成 `api_keys.id = secrets.token_hex(12)`。这是一个 96 位的随机数，与 token 无关；库里只保存 `key_hash = sha256(token)`，不保存 token。鉴权时按 `sha256(传入值)` 查 `key_hash`，所以 id 本身不能当 key 用：测试 `test_user_ref_stable_distinct_and_not_a_credential` 用 `Bearer <id>` 调 `/mcp`，返回 401。id 也不对外返回：`/usage` 返回前会 pop 掉 key_id，兑换和管理接口也都不返回它。

**派生**：`user_ref = sha256("mcp-suite/user_ref/v1:" + api_keys.id)` 的前 12 位十六进制。server.py 用 `digest(token)` 执行一次只读的 `SELECT id FROM api_keys WHERE key_hash=?` 拿到 id。token 只用来查这一行，不参与哈希计算，也不进入日志；store.py 的鉴权、兑换、额度逻辑都没有改。

**为什么不可逆**：sha256 是单向函数；输入里含 96 位随机数，前缀即使公开也无法穷举；结果只保留 48 位。所以从 user_ref 推不出 id，更推不出 token，而 token 在库里本来就只有哈希。

**稳定性与区分度**：同一把 key 的 id 永远不变，所以 user_ref 不变；不同 key 的 id 不同，48 位下 1 万把 key 出现碰撞的概率约为 2×10⁻⁷。测试验证了：同一 key 两次调用 user_ref 相同，第二把 key 不同，并且 user_ref 与按上述公式独立计算的结果一致。

**需要知道的一点**：这是**假名，不是匿名**。持有 access.sqlite3 的运维可以对每个 `api_keys.id` 算一遍，把日志行对回到某把 key，再经 `redemption_codes.key_id` 对回兑换码和订单。日志本身不含 key、兑换码和 id。FAQ 文案因此写的是"无法反推出 key 的编号"，没有写"匿名"。

## 5. 测试

命令（A2d 同理，把 A2 换成 A2d）：
```
cd release-A2 && PYTHONDONTWRITEBYTECODE=1 MCP_JOBS_PATH=../data/jobs.json \
  ~/Projects/mcp-suite/.venv/bin/python -m pytest -p no:cacheprovider -W ignore::DeprecationWarning --basetemp=../tmp/pytest-A2 -rA -q
```
完整输出见 `test-output/A2-pytest.txt`、`test-output/A2d-pytest.txt`。2 条 warnings 是 fastmcp 依赖的 authlib 弃用提示，与本次改动无关。

A2 的调用日志测试（`test_release_a2.py` 10 项，另有 `test_doubao_fix.py` 改写的 2 项），除第 8 项在进程内直接调用写日志函数外，都通过 uvicorn 子进程和真实 HTTP 进行：
1. 字段恰好 11 个；参数值原样记录（整数、null 保留原样）；UA 截断到 100 字符；`result_total`/`returned` 与返回结果一致；ts 带 `+08:00`，文件名日期与 ts 一致。
2. 超过 200 字符的 keyword 被参数校验拒绝，日志仍然记录，值截断到 200 字符，error_type 为 `invalid_arguments`。
3. 列表和字典截断正确，未知参数 api_key 记为 `[redacted]`，参数值里粘贴的 token、`Bearer …`、兑换码都被替换。
4. 日志文件和 uvicorn stderr 中都不出现 token、兑换码、内部 key id、`sha256(token)`、放在 `X-Api-Key`/`Cookie` 请求头里的哨兵值，也不出现 `Bearer` 字样；目录权限 700，文件 600。
5. user_ref 同一 key 稳定、不同 key 不同，且等于公式结果；内部 id 当 Bearer 使用返回 401。
6. 日志目录不可写（chmod 500）时：调用两次都成功，stderr 只有 1 行 `mcp_call_log_warning`，目录里没有产生任何文件。
7. 32 个并发 HTTP 调用写出 32 行完整 JSON，参数值一一对应。
8. 进程内 16 个线程各写 100 行、每行约 6 KB（远超 PIPE_BUF），1,600 行全部可解析且 id 无缺失；另测了值的边界（超大整数、NaN、嵌套深度）和 64 KiB 行上限的退化逻辑。
9. 分析脚本对测试日志的输出：3 次相同调用计为 2 次重复；按 UA、零结果、热门值统计正确。
10. stderr 不再出现 `mcp_tool_call`。

A2d（`test_release_a2d.py` 3 项）：
- schema 中 limit 默认 10、最大 100，描述含"从近到远"且不再含"倒排"；
- 默认调用返回 10 条，`order=deadline_asc`，日期非降序，第一条等于窗口内最近的截止日（今天），total 等于按纳入规则独立计算的 456；
- `offset=0` 与 `offset=10` 两页拼接后等于 `limit=20`，前一页最后一条的截止日不晚于后一页第一条；
- 调用日志里 jobs_deadlines 这一行的 `returned=10`，`result_total` 等于返回的 total。

另外有两项检查不属于 pytest：
- `evidence/verify_schema_local_A2.txt`：用部署时的 schema 核验脚本在本地跑 A2 和 A2d，三个工具都是 `anyOf/oneOf=False missing_type=[]`，`RESULT OK`；并确认只 import 代码不会创建日志目录。
- `evidence/artifact-scan-A2.txt`：对 `evidence/A2/`、`evidence/A2d/` 和两份 pytest 输出扫描 `Bearer`、`SENTINEL`、key 形态、兑换码形态和 `abc.def`，命中全部为 0。

## 6. 分析脚本 `scripts/analyze_call_logs.py`

用法：`analyze_call_logs.py 日志目录 [--window 60] [--top 20] [--json]`。只用标准库，只读不写。输出包括：
- 按天调用量；
- 按工具的调用、成功、失败、p50/p95 耗时和错误类型；
- 按 UA 统计；
- 各工具的参数名出现频率；
- 每个参数的热门值 Top N；
- 零结果比例（只统计成功且能取到条数的调用）；
- 同一 user_ref 在窗口内以相同工具、相同参数重复调用的次数和最长连发，这一项用来发现豆包那种死循环。

在服务器上可以不落文件直接跑：
```
ssh root@114.215.188.109 '/opt/mcp-suite/.venv/bin/python -B - /var/lib/mcp-suite/call_logs' < scripts/analyze_call_logs.py
```

对测试日志跑一遍的输出如下（`evidence/A2/analyze_call_logs-qiuzhao.txt`；bench 的输出在同目录的 `-bench.txt`，A2d 的在 `evidence/A2d/`）。数据都是测试产生的，只用来展示格式。重复调用那一项抓到的是测试框架连续 4 次发出的相同 `{"limit":1}`：
```
调用日志分析：evidence/A2/call_logs-release-A2-qiuzhao（文件 1 个，有效行 25，坏行 0）
时间范围：2026-09-11T22:32:28.401+08:00 — 2026-09-11T22:32:37.014+08:00；不同 user_ref 2 个；结果 {'ok': 20, 'error': 5}

== 按天调用量 ==
日期              调用    成功    失败
2026-09-11      25    20     5

== 按工具 ==
产品/工具                         调用    成功    失败   p50ms   p95ms  错误类型
qiuzhao/jobs_search           24    19     5     432     507  invalid_arguments×5
qiuzhao/jobs_detail            1     1     0     345     345  -

== 按客户端（UA）==
    18  doubao-fix-harness/1.0
     1  DoubaoWork/9.9 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     1  TruncUA/1.0 uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu
     1  LongArgUA/1.0
     1  BoundsUA/1.0
     1  RefUA/a1
     1  RefUA/a2
     1  RefUA/b1

== 参数名出现频率（占该工具调用次数的比例）==
qiuzhao/jobs_search（24 次调用）
  limit                   20    83.3%
  graduation_year          9    37.5%
  keyword                  6    25.0%
  city                     5    20.8%
  job_category             4    16.7%
  cohort                   2     8.3%
  company                  2     8.3%
  industry                 2     8.3%
  major_category           2     8.3%
  region                   2     8.3%
  major                    1     4.2%
  recruitment_type         1     4.2%
  api_key                  1     4.2%
qiuzhao/jobs_detail（1 次调用）
  id                       1   100.0%

== 热门参数值（每个参数取前 N 个，N 见 --top）==
qiuzhao/jobs_search · limit
      16  1
       1  5
       1  100
       1  101
       1  3
qiuzhao/jobs_search · graduation_year
       4  2027
       1  (null)
       1  2027届
       1   2027 届 
       1  2027年
       1  2030届
qiuzhao/jobs_search · keyword
       1  (null)
       1     
       1  ARGMARK产品值9f3c
       1  产品
       1  ARGMARK长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长长…
       1  ["k0-vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv…
qiuzhao/jobs_search · city
       3  (null)
       1   北京 
       1  {"c0": 0, "c1": 1, "c2": 2, "c3": 3, "c4": 4, "c5": 5, "c6":…
qiuzhao/jobs_search · job_category
       2  产品
       1  (null)
       1  产品经理
qiuzhao/jobs_search · cohort
       1  (null)
       1  2027
qiuzhao/jobs_search · company
       1  (null)
       1  见 [redacted] 或 [redacted] 或 [redacted]
qiuzhao/jobs_search · industry
       1  (null)
       1  互联网/科技
qiuzhao/jobs_search · major_category
       1  (null)
       1  计算机类
qiuzhao/jobs_search · region
       1  (null)
       1  北京
qiuzhao/jobs_search · major
       1  (null)
qiuzhao/jobs_search · recruitment_type
       1  (null)
qiuzhao/jobs_search · api_key
       1  [redacted]
qiuzhao/jobs_detail · id
       1  guopin-216471935930860193

== 零结果比例（成功且能取到条数的调用）==
全部                             1/20        5.0%
qiuzhao/jobs_detail            0/1         0.0%
qiuzhao/jobs_search            1/19        5.3%

== 同一 user_ref 在 60 秒内用相同参数重复调用 ==
重复次数合计：3（涉及 1 组；无 user_ref 的调用 0 次，未计入）
user_ref      产品/工具                      调用   重复     最长连发  UA | 参数
192a97368d10  qiuzhao/jobs_search         4    3        4  doubao-fix-harness/1.0 | {"limit": 1}
```

## 7. FAQ / 接入指南说明文案（草稿，未改任何页面）

> 为了改进岗位数据和搜索效果，我们会记录每次查询的条件（如关键词、城市、岗位大类）、所用客户端和返回条数；记录里不包含你的 API key、兑换码、姓名或联系方式，不同用户只以一个无法反推出 key 的编号区分，请不要在查询条件里填写个人信息。

保留期定下来之后，可以在末尾补"记录保存 N 天"（见第 10 节第 1 条）。

## 8. 目标 sha256

| 版本 | core/server.py | qiuzhao/tools.py |
|---|---|---|
| 线上基线 | `08143798a78ca401be294c7d3425b7f6398cd200cf93bf57b12a0e31f191dccd` | `77ffdb613a746636314e31786b2a451b57dd061670abba2542695e406ece0d52` |
| A（参照） | `de5cadb3ced55f3d3f4041aa5d523ae997706d467d6ce9bc106b1a948a04fb39` | `8dce3fe6b4b3bdb70feac65b2a78e03153b6febd7b93b468d1045b6f61a5e5ec` |
| **A2** | `788ab12564bf99ea65701b8a33eea38183ffcb189918e377e59e5741a2bfd1c8` | `8dce3fe6b4b3bdb70feac65b2a78e03153b6febd7b93b468d1045b6f61a5e5ec`（与 A 相同） |
| **A2d** | `869f92b4e8257fb5ae73372eed38a737f81721f465e6a25fd3b173a285fa6457` | `4360b4556e75e2442772f96a62f2fa4b8b7342ec7010ab23ccb15e8e4f3f49d0` |

同样记录在 `evidence/release_sha256_A2.txt`。

## 9. 部署方案（只写，未执行；需 Max 看过 diff 同意后执行）

在 RECEIPT.md 第 12 节的基础上补齐。服务器现状（22:36 只读核对）：
- `mcp-suite.service` 的配置为 `User=mcp-suite`、`UMask=0077`、`ProtectSystem=strict`、`ReadWritePaths=/var/lib/mcp-suite`；
- `/var/lib/mcp-suite` 属主 mcp-suite，权限 700；`call_logs` 目录尚不存在；
- `/usr/sbin/runuser` 可用，mcp-suite 的 shell 是 nologin；磁盘剩余 16G。

```bash
REL=A2d                                  # 或 A2（A2d 已包含 A2 的全部改动）
W=~/Projects/mcp-suite/research/qiuzhao-doubao-fix-20260911
LOCAL=$W/release-$REL
H=root@114.215.188.109
TS=$(date +%Y%m%d-%H%M%S)
BK=/opt/mcp-suite/deploy/backup-pre-$REL-$TS

# 0) 本地确认要上传的文件就是第 8 节的目标哈希
shasum -a 256 $LOCAL/core/server.py $LOCAL/qiuzhao/tools.py

# 1) 部署前核对线上 sha256：应仍是基线 08143798…1dccd / 77ffdb61…e0d52；
#    若 A 已先上线，则应是 A 的 de5cadb3…fb39 / 8dce3fe6…e5ec。其他任何值都立即停下报告。
ssh $H 'sha256sum /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py'

# 2) 备份要替换的两个文件
ssh $H "mkdir -p $BK && cp -p /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py $BK/ && cd $BK && sha256sum server.py tools.py | tee SHA256SUMS"

# 3) 以 mcp-suite 身份预建日志目录。服务在第一次调用时也会自己创建，
#    预建是为了在部署阶段就确认属主和权限，期望输出 mcp-suite:mcp-suite 700
ssh $H 'runuser -u mcp-suite -- install -d -m 700 /var/lib/mcp-suite/call_logs && stat -c "%U:%G %a %n" /var/lib/mcp-suite/call_logs'

# 4) 只替换这两个 .py（先 dry-run 看清单；-a 保持与现有文件相同的属主和权限），再核对哈希
rsync -a --checksum --itemize-changes --dry-run $LOCAL/core/server.py  $H:/opt/mcp-suite/core/server.py
rsync -a --checksum --itemize-changes --dry-run $LOCAL/qiuzhao/tools.py $H:/opt/mcp-suite/qiuzhao/tools.py
rsync -a --checksum --itemize-changes $LOCAL/core/server.py  $H:/opt/mcp-suite/core/server.py
rsync -a --checksum --itemize-changes $LOCAL/qiuzhao/tools.py $H:/opt/mcp-suite/qiuzhao/tools.py
ssh $H 'sha256sum /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py; stat -c "%U:%G %a %n" /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py'
#    期望等于第 8 节的目标值。上 A2 时 tools.py 与 A 相同；若线上还是基线，tools.py 这次也会被替换

# 5) 只重启 mcp-suite.service，bench 不动
ssh $H 'systemctl restart mcp-suite.service; sleep 5; systemctl is-active mcp-suite.service; journalctl -u mcp-suite.service --since "-2 min" --no-pager | tail -20'
#    journal 里不应再有 mcp_tool_call 行；出现 mcp_call_log_warning 说明日志目录写不进去，回到第 3 步查权限

# 6) health 检查
ssh $H 'curl -s http://127.0.0.1:8768/health'      # 期望 {"status":"ok","jobs":27506,...}
curl -s https://savegems.top/qiuzhao/health

# 7) 线上 schema 无 anyOf：在服务器上 import 代码，不起 HTTP、不用 token；DB 和日志目录都指向 /tmp 下的临时路径，用完删除；脚本经 stdin 传入，不在服务器落文件
ssh $H 'cd /opt/mcp-suite && T=$(mktemp /tmp/doubao-verify-XXXXXX) && PYTHONDONTWRITEBYTECODE=1 MCP_PRODUCT=qiuzhao MCP_DB_PATH=$T.sqlite3 MCP_DIST_DB_PATH=$T-dist.db MCP_JOBS_PATH=/var/lib/mcp-suite/jobs.json MCP_CALL_LOG_DIR=$T-logs .venv/bin/python -W ignore - ; rm -rf $T $T.sqlite3 $T.sqlite3-wal $T.sqlite3-shm $T-dist.db $T-logs; ls -d /tmp/doubao-verify-* 2>/dev/null || echo tmp-cleaned' < $W/scripts/verify_schema_snippet.py
#    期望 jobs_deadlines params=3、jobs_detail params=1、jobs_search params=13，都是 anyOf/oneOf=False missing_type=[]，
#    最后一行 RESULT OK []（本地结果见 evidence/verify_schema_local_A2.txt）

# 8) 调用一次后核对日志：由 Max 用自己的 key 在豆包工作里查一次（执行会话不经手 key）；上 A2d 时再让客户端调一次 jobs_deadlines
ssh $H '/opt/mcp-suite/.venv/bin/python -B -' < $W/scripts/verify_call_log_snippet.py
#    期望：dir mcp-suite:700、file mcp-suite:600；Bearer / api_key / redemption_code 的 hits 都为 0；最后一行 RESULT OK []。
#    last 那一行应满足：args 与提问一致，ua 是豆包，user_ref 是 12 位十六进制，outcome=ok，result_total/returned 有数值
ssh $H 'tail -n 3 /var/lib/mcp-suite/call_logs/tool_calls-$(TZ=Asia/Shanghai date +%Y%m%d).jsonl'
#    A2d 另看返回：order=deadline_asc，10 条，第一条的截止日是今天
```

**回滚**（在同一个 shell 里执行，需要保留 `$BK` 变量）：
```bash
ssh $H "cp -p $BK/server.py /opt/mcp-suite/core/server.py && cp -p $BK/tools.py /opt/mcp-suite/qiuzhao/tools.py && sha256sum /opt/mcp-suite/core/server.py /opt/mcp-suite/qiuzhao/tools.py && systemctl restart mcp-suite.service && sleep 5 && systemctl is-active mcp-suite.service && curl -s http://127.0.0.1:8768/health"
#    期望 sha256 回到第 1 步看到的值，health 返回 ok
```
回滚后 `/var/lib/mcp-suite/call_logs/` 保留原样，旧代码不读取它，是否删除由 Max 决定。如果在回滚之前 bench 已经被重启过，也要执行 `systemctl restart mcp-suite-bench.service`。

## 10. 需要 Max 决定 / 已知情况

**需要 Max 决定：**
1. **日志保留期。** 现在没有轮转也没有清理。按每行约 300 B 估算，每天 1 万次调用约 3 MB。建议定一个期限（例如 180 天），再用 cron 或 systemd-tmpfiles 清理，并写进 FAQ。本次没有实现清理，这是一个有状态的持续配置，没有授权不应该加。
2. **user_ref 是假名。** 运维持有 access.sqlite3 就能把日志对回 key 和兑换码（见第 4 节）。如果要求连运维也对不回，可以改成用只存在于服务器的密钥做 HMAC，代价是密钥一旦丢失，所有 user_ref 都会变。建议保持现状。
3. **上 A2 还是 A2d**，以及是否先上 A。三个版本互相兼容，目标哈希见第 8 节。

**已知但本次不改的：**
4. 查询条件本身可能含有用户自己输入的个人信息，例如在 keyword 里写学校或姓名。按 Max 的决定记录参数值，只对凭据形态做了脱敏，所以 FAQ 文案里提醒不要填写个人信息。
5. A2d 的第一页全是今天截止的岗位（今天共 33 条）。其中 1 条的截止值带具体时间，且到 22:39 已经过了，但纳入规则按日期判断，它仍会出现在第一页。纳入规则按要求没有改，与 deadline_type 一起留到 v4 统一处理。
6. bench 与 qiuzhao 共用 server.py。bench 下次重启（包括崩溃自动拉起）后，也会以 `product=bench` 写入同一个目录和同一个文件。两个服务的运行用户相同，每行都是单次 O_APPEND 写入，分析脚本按 product 区分。跨进程共写没有专门做测试。bench 的重启时机仍按 RECEIPT.md 第 11 节第 2 条处理。
7. A2 每次调用多一次 SQLite 只读查询来取 user_ref，与每次 0.3–0.5 秒的 jobs.json 全量解析相比可以忽略。
8. A 起 journald 里的 `mcp_tool_call` 行在 A2 取消了，所以 RECEIPT.md 第 12 节第 7 步的 `journalctl | grep mcp_tool_call` 由本节第 8 步代替。
9. RECEIPT.md 第 11 节列出的既有问题（7 个 `code_plain` 测试失败、兑换码明文落库、`?token=` 管理令牌、`Jobs.load()` 不缓存、重复 id）没有变化。

## 11. 产物清单（均在 `~/Projects/mcp-suite/research/qiuzhao-doubao-fix-20260911/`）

- `release-A2/`、`release-A2d/`：完整代码树，含 `tests/` 和 `pytest.ini`，没有 `__pycache__`。
- `patches/A2.diff`（release-A → A2，运行时文件，239 行）、`patches/A2d.diff`（A2 → A2d，运行时文件，41 行）；测试改动在 `patches/A2.tests.diff`、`patches/A2d.tests.diff`。
- `test-output/A2-pytest.txt`、`test-output/A2d-pytest.txt`。
- `evidence/A2/`、`evidence/A2d/`：调用日志样例（`call_logs-*/tool_calls-20260911.jsonl`）、uvicorn 日志（不可写目录那一份里只有 1 行 warning）、分析脚本输出。
- `evidence/artifact-scan-A2.txt`（敏感信息扫描，全部为 0）、`evidence/verify_schema_local_A2.txt`、`evidence/release_sha256_A2.txt`。
- `scripts/analyze_call_logs.py`（任务 6），`scripts/verify_call_log_snippet.py`（部署第 8 步用的只读核对脚本）。
- `tmp/` 已清空；本次运行的 pytest 临时目录都已删除。
