# 秋招 MCP v4 实现：收据

执行时间：2026-09-11 23:10 – 2026-09-12 00:40（北京时间）。工作副本 `~/Projects/mcp-suite-wt-v4`，分支 `feat/v4`（从 main 1127cf7 拉出），没有合并、没有 push、没有部署。

服务器 `root@114.215.188.109` 上只做了只读操作：`free -m`、`nproc`、`ps`、`systemctl show/is-active`、`sha256sum`、`stat`、`ls`、`df`、`id`、在 .venv 里 import 一次 fastmcp 看版本；另外把 `qiuzhao/v4_fields.py` 经 stdin 管道交给服务器上的 Python，在内存里读 `/var/lib/mcp-suite/jobs.json` 并打印计数（`nice -n 19`，约 1 秒，不落文件、不写任何路径）。没有碰 Kimi 负责的文件和工作副本（`git diff main..HEAD -- qiuzhao/normalize.py qiuzhao/normalize_tables.json qiuzhao/collector deploy .gitignore` 为空）；没有读 private/、*.sqlite3*、带 receipt 的 json、*.mcp.json、tests/e2e_bench_online.py。

## 0. 收尾（2026-09-12 01:00–01:50）

在 feat/v4 上合并采集修复、落实 Max 对第 11 节 8 个问题的决定、加排序修正，写 Kimi 的部署任务书。仍只在本地做：没有部署、没有重启。服务器上只跑了只读命令：`sha256sum`、`stat`、`ls -l`（只看文件名和大小）、`free -m`、`df`、`ps`/`pgrep`、`systemctl is-active`，以及用 `cat` 读 `cron-status.json`、两个静态页和 `jobs.json` 到本地。没有进入 `~/Projects/mcp-suite-wt-collector`，没有改 main；没有读 private/、*.sqlite3*、带 receipt 的 json、*.mcp.json、tests/e2e_bench_online.py。第 1–12 节是 9/12 00:40 的原收据，已过期的地方在原处标了。

### 0.1 提交

| 提交 | 内容 |
|---|---|
| `0098267` | `git merge fix/collector-normalize`（3d5cff6），无冲突，只进来采集修复的 10 个文件 |
| `8ccf6b8` | `git merge main`（6d580e1，只多一个 `research/collector-fix-20260911/DEPLOY-RECEIPT.md`）。采集部署后 main 多了这个收据提交，不合进来的话部署后 main 无法快进到 feat/v4 |
| `55bd3ee` | 决定 5：`core/store.py` 文件头、`tests/test_core.py` 的 `test_atomic_redemption` |
| `2f0f070` | 决定 2 与排序修正：`qiuzhao/v4_fields.py`、`qiuzhao/tools.py`、`core/server.py`（`sort`、`graduation_year` 两个参数描述和 `jobs_search` 描述）、测试。**这是要部署的代码提交** |
| 本收据所在提交 | SPEC、示例、验收与测量证据、部署用的 3 个脚本、`KIMI-DEPLOY.md` |

两次合并都没有碰 v4 的文件（`git diff b515a13 8ccf6b8 -- core qiuzhao/tools.py qiuzhao/v4_fields.py tests research/qiuzhao-v4-impl research/qiuzhao-v4-interface-20260911` 为空）。

### 0.2 Max 的 8 个决定

| # | 决定 | 处理 |
|---|---|---|
| 1 | 活动标题只写年份、不写“届”字，也算“活动标题写明” | 与现状一致，确认未改 |
| 2 | 推断为 2027届 的岗位，查其他届别时不排除，归入“含未注明”并标注 | **已改**，见 0.4 |
| 3 | 传了 recruitment_type=社会招聘 再按届别查，社招算推断匹配 | 与现状一致，确认未改 |
| 4 | 国聘 1,087 条按明确截止日 | 与现状一致，确认未改 |
| 5 | 兑换码继续明文落库 | **已改**：`core/store.py` 文件头改为“API key 只存 SHA-256 摘要；兑换码存摘要（查找用）和 code_plain 明文，管理后台列出来复制发货”；`test_atomic_redemption` 改为断言 key 只以摘要存在、兑换码只在自己那一行的 code_plain 里出现一次且 code_hash 等于它的摘要。生成、兑换、管理后台的代码都没动 |
| 6 | 梧桐科技“算法工程师”保留 | 确认未改 |
| 7 | 保留 2028届、2024届 两个枚举值 | 确认未改 |
| 8 | 保留 missing_queries.jsonl | 确认未改 |

### 0.3 排序修正

规则（`v4_fields.RANK_DIMENSIONS`、`v4_fields.BASIS_RANK`、`tools.Jobs.order`）：先按档次；同一档内逐维比较城市、专业、学历、届别的具体程度，前一维分出先后就不看后面；每一维内的先后是 岗位写明 → 全国 / 专业不限 / 学历不限 / 活动标题写明 → 推断依据 → 未注明 / 推断为其他届别；最后按 sort（published_desc：发布时间从新到旧，同一天按 id 从大到小；deadline_asc：截止日从近到远，没写截止日的在后，再按 id）。顺序完全确定。维度按 Max 列出的次序比较，城市排第一，所以同一档内写明成都的岗位全部排在“全国”之前。

“成都 + 2027届 + 计算机类”排序修正后的前 5 条（9/11 快照，`examples/jobs_search.1_city_year_major.json`；9/12 00:52 线上副本的前 5 条相同）：

| # | 岗位名 | 城市 | match |
|---:|---|---|---|
| 1 | 技术类校招岗位(2027届) | 成都、天津、北京、上海、深圳 | 明确匹配：届别 岗位写明、城市 岗位写明、专业 岗位写明 |
| 2 | 27届博士(J13367) | 成都 | 明确匹配：同上 |
| 3 | 成都市武侯区分公司-金融柜员 | 成都 | 明确匹配：同上 |
| 4 | 成都市金牛区分公司-金融柜员 | 成都 | 明确匹配：同上 |
| 5 | 成都市青羊区分公司-金融柜员 | 成都 | 明确匹配：同上 |

修正前排第 1 的是 cities 只有“全国”的“集控运行岗”（中电神头发电）。225 条明确匹配里，写明成都的 138 条在前，第 139 条起是依据“全国”的 87 条（`examples/jobs_search.1b_city_then_nationwide.json`）；线上副本上是 140 条和 104 条。

总数和三档计数不变，只有顺序变。验收里 Q01、Q15、Q20 的前 3 条 id 变了；Q05、Q16 取 Q01 的前两条 id，参数跟着变。Q01 条件的第 1 页换成写明杭州的岗位，描述更长，响应从 18,715 B 变为 30,333 B，仍远低于 60KB 预算；tools/list 因描述加长从 14,778 B 变为 15,484 B。多一次排序，本地中位延迟：默认 search 15.0 ms（原 14.6）、北京+2027届 19.5 ms（原 17.5）、Q01 16.4 ms（原 14.5）。

### 0.4 决定 2 的实现与数字

`tools.Jobs._m_grad`：查询的届别不在岗位的届别里、而岗位的届别依据全是推断（按招聘季推断、来源专场注明）时，返回依据 `推断为其他届别`，档次为含未注明；原文或活动标题写了别的届的，仍不返回。查 2027届 不受影响，因为所有推断给出的届别都含 2027届。

9/11 快照（今天固定为 9/11）：
- 查 2026届：5,852 条（明确 2,206 / 推断 509 / 未注明 3,137），其中 `推断为其他届别` 2,818 条（按招聘季推断 2,437、来源专场注明 381）；原为 3,034 条。
- **Q07（2026届 + 国企/央企）：702（580 / 0 / 122，其中推断为其他届别 120、未注明 2），社招未计入 78**；原为 582（580 / 0 / 2）。
- 9/12 00:52 线上副本（今天为 9/12）：Q07 为 826（705 / 0 / 121，其中推断为其他届别 119），社招未计入 77（`evidence/acceptance_v4.live-20260912.json`）。

同步改了：服务端 `graduation_year`、`sort` 参数描述和 `jobs_search` 描述；SPEC 开头、一页结论、3.0（匹配依据表、判定顺序后的说明、新的“排序”段）、3.1（描述原文、参数表）、第 4、5、7、8、9 节和附录 C；示例新增 `jobs_search.1b_city_then_nationwide.json`、`jobs_search.5_2026_inferred_other_year.json`，其余示例重新生成；`evidence/acceptance_v4.json` 重算。

### 0.5 测试与核验

- `pytest`：**134 passed**（`evidence/pytest-final.txt`；2 条 warnings 是 authlib 的弃用提示）。原来失败的 `test_atomic_redemption` 按新断言通过。新增 4 项：`test_v4_fields.py` 的 `test_order_inside_a_tier_follows_specificity`（每一维的先后、维度次序、档次优先、两种 sort、不带条件时顺序不变）和 `test_inferred_year_is_unspecified_for_other_years`（2026届 / 2025届 / 2027届 / 未注明 / explicit_only）；`test_v4_tools.py` 的 `test_order_inside_a_tier_is_by_specificity`（真实数据上与独立写的参考排序逐条相同，HTTP 第 1 页和成都→全国分界是它的切片）和 `test_inferred_year_is_unspecified_for_other_years`（真实数据上依据 `推断为其他届别` 的集合与按定义算的一致，写明别的届的一条也不返回，Q07 的 HTTP 标注）。独立计数的参考实现（`test_counts_match_an_independent_reading_of_the_spec`）按决定 2 更新，多测 4 组条件。没有跑的仍是 `tests/e2e_local.py`、`tests/e2e_bench_local.py`：它们要连已启动的服务，并在 private/ 下建测试库，原因同第 6 节。
- schema 核验（`evidence/verify_schema_v4.txt`）：qiuzhao `jobs_detail params=1 / jobs_search params=15 / jobs_stats params=14`，bench 三个工具，都是 `RESULT OK []`。
- 枚举检查（`evidence/enum_check.txt`）：9/11 快照 25,458 条、9/12 00:52 线上版 25,631 条，都是 `RESULT OK`。线上版是从服务器只读拉的 `/var/lib/mcp-suite/jobs.json`（sha256 `6fd433129ab90a35440f36e1295f9432fccf99659179a971e83aaf9d0bc51080`，与服务器上的一致），放在 `qiuzhao/data/jobs.live-20260912.json`。
- 进程内端到端核验 `scripts/e2e_inprocess_check.py`（给 Kimi 在服务器上跑）：本地在快照和线上副本上各跑一次，都是 `RESULT OK []`；临时库、临时 key、临时日志目录用完即删，输出不含 key。
- 静态页重新套用脚本 `scripts/reapply_static_edits.py`：对线上两个页面的只读副本套用后，与 feat/v4 的两个文件逐字节相同；再套一次会拒绝写入（退出码 1）。
- 证据扫描：`evidence/`、`tools_list_v4*.json`、`examples/` 里 `Bearer`、qz_/bm_ key、QZ-/BM- 兑换码形态命中为 0。

### 0.6 线上只读核对（2026-09-12 01:02）

- 5 个要替换的文件的 sha256 都等于 main 1127cf7（`08143798…`、`77ffdb61…`、`0348d335…`、`4afa8338…`、`cb3d5e92…`），`qiuzhao/v4_fields.py` 不存在。**两个页面文件没有被改过**，不需要重新套用 6 处替换，部署包直接用 feat/v4 的 `guide.html`、`app.js`（来源 `4118fe8`，之后未变）。
- 采集部署的 7 个文件（normalize.py、normalize_tables.json、build_normalize_tables.py、collector/run.py、collector/auto_collect.py、collector-daily.sh、/etc/cron.d/mcp-suite-qiuzhao）与 feat/v4 里的版本逐一相同。
- `cron-status.json`：`success: true`，`completed_at 2026-09-11T16:52:46+00:00`（北京时间 09-12 00:52:46，晚于 00:00），steps 全为 0；没有采集进程。
- `free -m`：总 1,872 MB，已用 782，空闲 512，缓存 578，**可用 933**；swap 1,024，已用 496。磁盘余 16G（60%）。两个服务都是 active；`/var/lib/mcp-suite/call_logs` 还不存在；`access.sqlite3` 当时没有 -wal、-shm 文件。
- 01:43 用 KIMI-DEPLOY 第 1a、2、3 步的命令原样复核（1a 没跑 flock）：结论相同；`free -m` 可用 962 MB；bench 的 ActiveEnterTimestamp 为 2026-09-10 15:41:37；在服务器内存里用 `2f0f070` 的 `v4_fields.py` 对线上 jobs.json 做枚举检查，25,631 条 `RESULT OK`，没有留下文件。本地实测第 1c 步时发现 zsh 不对 `$FILES` 分词，已把本地命令里的文件列表写成明文。

### 0.7 部署

任务书：`research/qiuzhao-v4-impl/KIMI-DEPLOY.md`。部署 feat/v4 @ `2f0f070` 的 6 个文件：

| 文件 | 目标 sha256 |
|---|---|
| `core/server.py` | `09e831800ab674f36e0e855b22ec1befd261d71133b6c78d55c4d73e2ab6f7c8` |
| `qiuzhao/tools.py` | `5fe3d3d60e06b21ea5ea6ae73f327da6a2c8ba976859d8087a7e6bedeecc9d5b` |
| `qiuzhao/v4_fields.py`（新文件） | `ceb411808794ee6d742c73e4143cb15ea0b7ee52690e5d277e37368e80c25bd7` |
| `core/store.py` | `a43fe29325064352bbe69028359563d6dbc9dc3e162c7663acc94110e7f43c07` |
| `core/static/guide.html` | `a1e03aeaaf915bb72523f6a4cc3058fd66bc49804f367e7541d8cebec12813ec` |
| `core/static/app.js` | `cd30fbfd46544fefd28bcb117b2f540f4e9ed826f41ecbc4ccb3f0e050e9aa15` |

部署用的 3 个脚本都在 `scripts/`：`reapply_static_edits.py`（页面被改过时用）、`e2e_inprocess_check.py`（第 10 步）、`prepare_main_ff.py`（第 12 步，main 快进前清路）。

### 0.8 需要 Max 知道或决定

1. **main 工作副本里有 18 个文件会挡住快进**：`research/qiuzhao-v4-interface-20260911/` 下 17 个未跟踪文件（SPEC 原稿、evidence、examples、scripts）和改过没提交的 `scripts/v4lib.py`。它们和已提交的版本逐字节相同（17 个等于 `62c36fe`，v4lib.py 等于 feat/v4 的版本），但 git 仍会拒绝快进。KIMI-DEPLOY 第 12 步用 `prepare_main_ff.py` 先核对，全部相同才移到 `~/Projects/mcp-suite-preff-backup-<时间>/`（v4lib.py 先复制再还原到 HEAD），然后 `merge --ff-only`；有一个不同就停下。本地 dry run：`blockers=18 safe=18 different=0`。你如果不同意移动，Kimi 会停在快进这一步。
2. **管理后台的一句文案与决定 5 不一致**：`core/server.py` 的 `/admin` 页面仍写“系统只存哈希；明文兑换码仅在生成时显示一次。”，而后台列表实际显示 code_plain。按要求只改了 store.py 文件头，这句没动。
3. 部署之后、main 快进之前，如果 main 又有新提交（例如采集收尾的收据），快进会失败，Kimi 会停下；那时要先把 main 再合进 feat/v4。

## 1. 结论

- 三个工具 `jobs_search`、`jobs_stats`、`jobs_detail` 按修订后的 SPEC 实现；不做兼容；A2 调用日志完整移植；bench 照常能跑，两个产品的 schema 核验都是 `RESULT OK`，没有 anyOf/oneOf/allOf，qiuzhao 工具没有 outputSchema。
- 测试 130 项：129 通过，1 项失败是有意保留的（`test_atomic_redemption`：库里存了明文兑换码，见第 11 节第 5 条）。**2026-09-12 收尾后为 134 项全部通过，见第 0 节。**
- v4 字段在服务端由 `qiuzhao/v4_fields.py` 从原始字段算出，按 jobs.json 的 mtime+大小缓存：冷启动构建 0.8 秒，缓存后单次调用 4–57 毫秒；Python 堆常驻 124 MB、构建峰值 129 MB。
- 默认 search 的 HTTP 响应 23,011 B（A 包 53,600 B）；20 条满页 39,701 B；截断页 60,547 B。
- 线上 5 个要替换的文件此刻仍等于 main；线上 jobs.json 已在 00:05 被 Kimi 的采集修复重写（不再有重复行），用 v4 规则转换后仍是 25,458 条、枚举检查通过。

## 2. 提交（feat/v4）

| 提交 | 内容 |
|---|---|
| `a467a03` | 原始归一化脚本存档：`research/normalize-origin-20260911/`（原样复制，未执行） |
| `62c36fe` | SPEC 输入原样导入（main 工作区里未跟踪的 SPEC.md、evidence、examples、scripts，含 v4lib.py 未提交的改动） |
| `12fea78` | v4 主体：`qiuzhao/v4_fields.py`（新）、`qiuzhao/tools.py`、`core/server.py`、测试、`research/qiuzhao-v4-impl/scripts/` |
| `43f1298` | **单独提交**：`core/store.py` 加 `code_plain` 列和可重复执行的迁移；`tests/test_core.py` 里因套餐变化过期的断言。不要可以直接丢弃 |
| `4118fe8` | **单独提交**：`guide.html`、`app.js` 里提到 jobs_deadlines 和 limit 的 3 处文字 |
| `c557c84` | stats 分组的三档同时看组值本身（未注明组算未注明、届别组按该届依据） |
| `acd2499` | 分块 JSON 读取器移进 `v4_fields.py`，部署前检查可以单文件运行 |
| 本收据所在提交 | 修订版 SPEC、重新生成的 examples、本收据、tools/list、证据 |

丢弃 `43f1298` 时：`git revert 43f1298` 即可，它只动 `core/store.py` 和 `tests/test_core.py` 里 4 个套餐测试的断言；丢掉后测试会回到“7 个 code_plain 测试失败”的旧状态，HTTP 测试不受影响（测试夹具自己补列）。

## 3. 实现与 SPEC 的对应

| SPEC | 实现 |
|---|---|
| 3.0 schema、单份返回、同义词、中文报错 | `core/server.py`：`Annotated[...]` 参数类型（`TextIn`/`_none_to` 处理 null）、`json_schema_extra` 声明枚举和范围、`_reply()` 返回单个 `TextContent`、`mcp.tool(output_schema=None)`；`qiuzhao/tools.py`：`SYNONYMS`、`Jobs.check_filters/_choice/_text/_int`、`ParamError`→`InvalidParams(ToolError)` |
| 3.0 三档、届别判定顺序、社招 | `v4_fields.graduation_of`（规则 1–9）、`BASIS_TIER`；`tools.Jobs._m_grad/_m_city/_m_major/_m_edu/evaluate`、`excluded_social_total` |
| 3.0 分页与 60KB | `tools.Jobs.search`（`BUDGET_BYTES=60_000`） |
| 3.0 调用日志 | `core/server.py` 的 `write_call_log/log_tool_call/MeterTools`，从 release-A2 原样移植；`_result_data/_result_counts` 改为解析单份 JSON 文本，detail 取 found、stats 取 groups 长度 |
| 3.1–3.3 三个工具 | `core/server.py` 的 `jobs_search/jobs_stats/jobs_detail`（描述原文即 SPEC 引文）→ `tools.Jobs.search/stats/detail` |
| 3.2 组内三档 | `tools.Jobs.group_tier` |
| 6.1 去重 | `v4_fields.build`（先有效性过滤，再按 id 去重，保留第一次出现） |
| 6.2–6.8 | `v4_fields.job_category_of / graduation_of / education_of / major_category_of / deadline_of / cities_of / region_of / base_status / status_on`；缺 `*_normalized` 时的兜底规则在同一文件 |
| 6.10 测试记录 | `v4_fields.TEST_RULES / test_rule` |
| 缓存 | `tools.Jobs.dataset()`：键 (mtime_ns, size)，线程锁，读坏文件时继续用上一版；`v4_fields.iter_json_file` 分块读 |
| 9.15 枚举检查 | `v4_fields.enum_report` + `python qiuzhao/v4_fields.py check <jobs.json>`；`tests/test_schema.py` |

## 4. 与 SPEC 不一致的地方

指原稿叠加你的覆盖决定之后仍有出入、已同步写进修订版 SPEC 的点：

1. **届别枚举多了 2028届、2024届。** 岗位描述里有“2027届或2028届硕士在读”“2024—2027届高校毕业生优先”，数据里分别有 4、3 条；按决定 15 的检查，枚举必须等于数据取值，所以加进枚举。
2. **新字段与计数。** 每条多了 `graduation_year_note`（届别为空时说明原因）；顶层多了 `inferred_total`、`excluded_social_total`；stats 组多了 `inferred_count`。
3. **stats 的组内三档也看组值本身**（`c557c84`）。原稿只按记录在查询条件下的档次计；不这样改，`stats(group_by=graduation_year)` 会把按招聘季推断的 2,818 条算成“明确”。
4. **长度和范围也在函数里校验**，中文报错（原稿只对枚举这样做）；schema 仍声明 `maxLength/minimum/maximum`。枚举第一个值是 `""`（沿用 A 包写法）。
5. **值被归一时写 notices**（同义词、城市去“市”）。原稿的 notices 用于旧参数改名，已删除。
6. **学历、城市等 6.x 规则与起草时的参考实现逐条一致**（测试在 27,506 行上逐字段比对 `scripts/v4lib.py`），但**届别**多了规则 3–9、岗位名称和描述补抽，所以 6.3 的数字全部换成了实现的数字。
7. **`/health`** 返回去重、去测试记录后的 25,458 条（v3 为 27,506）。
8. **保留了 v3 的 `missing_queries.jsonl`**：结果为 0 且 offset=0 时仍追加一行到 `/var/lib/mcp-suite/missing_queries.jsonl`（原稿没提）。
9. **测试专用环境变量 `MCP_TODAY`**：固定“今天”以复现数字，生产不设。
10. 第 4 节的截断页数从 110 变为 108（去重和测试记录过滤后的实测）。

## 5. 各项修正和推断的实际条数

### 5.1 构建报告（2026-09-11 快照）

| 项 | 条数 |
|---|---:|
| 原始行 / 有效行（source_url 与 application_url 都有） | 28,616 / 27,506 |
| 按 id 去重掉的行 | 2,043 → 25,463 条 |
| 测试记录（去重后） | 5 → **25,458 条** |
| 岗位大类改判（27,506 行口径 / 最终） | 801（产品 370、运营 244、设计 80、销售 72、市场/营销 21、职能/支持 14）/ 770 |
| 城市字典串修复（27,506 行 / 最终） | 539 / 519 |
| 海外城市标错 overseas_flag（27,506 行 / 最终） | 373 / 364 |
| 国聘 undisclosed 带日期 → 明确日期（27,506 行 / 最终） | 1,087 / 912 |
| 学历乱码（最终） | 89 |
| 截止日：明确日期 / 未注明 / 招满即止或长期 | 17,861 / 6,303 / 1,294 |
| 学历：未注明 / 本科 / 硕士 / 博士 / 大专 / 中专及以下 / 不限 | 9,351 / 8,915 / 5,035 / 1,071 / 831 / 130 / 125 |
| 专业：未注明 / 不限 / 写明 | 12,145 / 196 / 13,117 |
| 城市：全国 / 未注明 | 925 / 1,365 |

### 5.2 届别：原文和活动标题都没写的记录

| 规则 | 你给的数 | 实现 | 依据 / 档次 |
|---|---:|---:|---|
| 社会招聘 | 3,017 | 3,016 | 社招不限届别；按届别筛选时排除（除非 recruitment_type=社会招聘，此时为推断） |
| 岗位名称写明 | 147 | 190 | 岗位写明（明确） |
| 岗位描述写明 | 340 | 329 | 岗位写明（明确） |
| 实习、没写届别 | 510 | 509 | 实习未写届别（推断，对任何届别） |
| 校招、发布于 2026-07~12 | 约 5,120 | **2,437** | 按招聘季推断为 2027届（推断） |
| 校招、没有发布时间 | 540 | 536 | 381 条对上来源登记（全是腾讯，join.qq.com，scope 2027届）→ 来源专场注明（推断）；155 条对不上 → 未注明 |
| 其余 | 184 | 164 | 未注明 |
| 合计 | 9,858 | **7,181** | |

差距集中在“校招、发布于 2026-07~12”。实现按 SPEC 6.3 和决定 2 判断“写了届别”：原文或活动标题里出现年份就算（例如国聘活动标题“国聘行动2027校园招聘”没有“届”字，也算活动标题写明）。如果改成“必须出现‘20xx届’才算写了”，复算的“都没写”是 9,842 条，与你给的 9,858 基本一致，说明你的数是按这个更严的口径统计的。两种口径的差别是 2,661 条活动标题只写年份的校招记录（活动标题为“中国联通2027校园招聘”1,072 条、“中国移动2027校园招聘”982 条、“中国兵器工业集团有限公司2027校园招聘”399 条、“中国兵器装备集团有限公司2027校园招聘”163 条等，其中 2,660 条发布于 2026-07~12）：现在是“活动标题写明”（明确），按严口径会变成“按招聘季推断”（推断），届别都是 2027届，只影响档次。见第 11 节第 1 条。

最终届别总览：含 2027届 21,533 条（岗位写明 14,343、活动标题写明 4,372、按招聘季推断 2,437、来源专场注明 381）；2026届 2,206；2025届 53；2028届 4；2024届 3；多届 2,152 条。`search(graduation_year=2027届)`：22,361 条（明确 18,715 / 推断 3,327 / 未注明 319），另排除社招 3,016 条。

### 5.3 测试记录

先扫了岗位名、公司名、描述里的 test/测试/联调/示例/请勿投递等写法，逐条看过后定了 5 条规则（`v4_fields.TEST_RULES`），命中如下（有效行 / 去重后）：

| 规则 | 命中 | 记录 |
|---|---:|---|
| 岗位名整体是 test+数字 | 3 / 2 | `test50`（洛阳前钱有限企业，国聘行动 2 行 + 国聘专场 1 行） |
| 岗位名含“测试修改职位”或“测试职位”+4 位以上数字 | 2 / 2 | `zyx联调测试修改职位01`、`亲属关系优化测试职位26070701`（梧桐科技） |
| 描述只由“测试数据”组成 | 3 / 1 | `参与单位数据统计1`（开开心心有限公司2） |
| 描述含“测试职位请勿投递” / 描述是“这是工作职责…这是任职要求”模板 | 已被上面两条先命中 | 同上两条梧桐科技记录 |

合计 5 个 id（有效行 8 行）。没有误伤：“软件测试工程师”“培训生（市场营销）【仅限2027应届，往届勿投递】”“国检测试控股”等真实岗位都不命中（有测试覆盖）。存疑未过滤：梧桐科技的“算法工程师”（`gp_梧桐科技-216191773066658029`、`gp-216191773066658029`），同一租户有两条明显的测试岗，但这条内容像真实岗位，见第 11 节第 6 条。

### 5.4 国聘 1,087 行的截止日（决定 5）

结论：当明确日期。依据：
- `qiuzhao/collector/guopin.py` 第 141–148 行：`end=str(r.get('end_time') or '')`，`deadline=end[:10]`，`deadline_type='explicit' if deadline`，`deadline_scope='official_role_record'`，截止日早于核验日时 `status='expired'`。现行采集器就是把国聘的 end_time 当岗位截止日。
- 这 1,087 行都来自“国聘行动官方招聘平台”，日期是 `YYYY-MM-DD HH:MM:SS`，与国聘接口原始 end_time 格式相同（`research/qiuzhao-v3-launch-20260910/conditional_release/_guopin_raw.json` 的 61 条都是 19 位）；810 行是 23:59:59。
- 420 行能按 source_record_id 对上其他来源的同一岗位（主要是 guopin.py 产出、deadline_scope=official_role_record 的记录），日期全部相同，没有一条不同；另 667 行没有别的来源可比。同一来源另外 5,598 行本来就标 explicit。
- 没能确认的：国聘官方对 end_time 的字面定义（没有公开文档可查）。

### 5.5 线上最新 jobs.json 的只读复核（9/12 00:05 版）

用 v4 规则在服务器内存里转换：原始 26,570 行、有效 25,463 行、重复 0、测试记录 5，得到 25,458 条，data_as_of 2026-09-12T00:05:52+08:00；枚举检查 `problems=[]`；各项修正和届别规则的条数与 9/11 快照完全相同。说明 Kimi 的修复在管线侧去掉了重复行，其余字段（包括 `*_normalized`）未变，v4 的服务端修正仍然需要。

## 6. 测试

命令（输出全文 `evidence/pytest-final.txt`，其中一次断言失败打印的临时测试兑换码已替换为 `[redacted-test-code]`）：
```
cd ~/Projects/mcp-suite-wt-v4 && PYTHONDONTWRITEBYTECODE=1 ~/Projects/mcp-suite/.venv/bin/python -m pytest -p no:cacheprovider -W ignore::DeprecationWarning -rA -q
→ 1 failed, 129 passed in 20.4s
```

| 文件 | 项数 | 内容 |
|---|---:|---|
| `tests/test_call_log.py` | 14 | A2 的 10 项日志测试全部移植（字段与原值、超长值截断、列表/字典截断与凭据脱敏、无凭据与 700/600 权限、user_ref 稳定且不是凭据、日志目录不可写时调用照常且只警告一次、32 路并发整行、16 线程长行、值边界与 64KiB 行上限、分析脚本）+ A2 `test_doubao_fix` 里的日志项（stderr 不再有 mcp_tool_call）+ 新增 3 项：stats/detail 的 result_total、tool 记客户端调用的旧名 jobs_deadlines、参数值错误记 invalid_arguments；另 1 项确认旧日期文件不被动（永久保留） |
| `tests/test_schema.py` | 11 | tools/list 恰好 3 个工具、无 anyOf/oneOf/allOf、无 outputSchema；bench schema 扁平；search 与 stats 的 12 个筛选参数定义逐字相同；枚举值与默认值；枚举等于数据取值（测试 + CLI）；数据漂移时检查失败；全部参数传 null；v3 参数名被 FastMCP 拒绝；instructions；bench 返回形状不变 |
| `tests/test_v4_fields.py` | 64 | 届别抽取正反例 25 个、判定顺序 11 种、来源登记常量与 registry 文件一致、测试记录规则正反例 11 个且在真实数据上只命中那 5 个 id、与 SPEC 参考实现逐字段一致（801/539/373/1,087）、构建报告数字、缺 `*_normalized` 时的兜底、运行时状态、分块读取器跨块边界 6 种块大小、与 json.load 全量一致、缓存只在文件变化时重建且读坏文件时保留上一版、60KB 预算至少返回 1 条、与按 SPEC 3.0 独立重写的计数逻辑在 49 组条件上逐一相等 |
| `tests/test_v4_tools.py` | 31 | 单份返回（HTTP 响应体里结果只以转义文本出现一次）、默认返回形状、翻页拼接、60KB 截断在完整岗位处且下一页接得上、page_size/top 超上限、同义词与 notices、17 种中文报错、三档边界与 explicit_only、推断依据、社招排除计数、stats 填回与组内三档、detail、测试记录消失、截止窗口、**24 个验收问题的 HTTP 返回与进程内结果逐字相同** |
| `tests/test_core.py` | 10 | 见下 |

**已有测试改了什么（逐条）：**
- `test_jobs_preserve_facts_and_deadline_order`（v4 设计变化，在 `12fea78`）：`jobs.deadlines(7)` 改为 `search(deadline_within_days=7, sort=deadline_asc)`，期望顺序 `['1','0']` → `['0','1']`（由近到远）；`source_urls`、`数据截至时间` 改为断言已删除；`search(cohort='2027')==[]` 改为 `graduation_year=2027` 返回 3 条“按招聘季推断”（fixture 是 2026-09 发布的校招）；`search(major='计算机')` 有 suggestion 改为 3 条未注明、加 explicit_only 才为 0；`status=='expired'` 改为 `已截止`；`detail('missing')['source_urls']==[]` 改为 `not_found==['missing']`。
- `test_role_cohort_overrides_campaign_title` → `test_role_cohort_and_campaign_title_bases`（SPEC 6.3 变化）：v3 让岗位原文届别覆盖活动标题；v4 活动标题的年份作为补充，标“活动标题写明”，所以 `explicit-2026` 也出现在 2027届 结果里；`cohort_filter_scope` 改为断言已删除。
- 套餐相关（在 `43f1298`）：`test_atomic_redemption` 剩余次数 200→999999；`test_atomic_daily_limit` 先把这把 key 的 daily_limit 用 SQL 设为 200，仍用 220 个并发调用验证原子扣次（按 999999 无法验证上限）；`test_midnight_resets_and_handshake_free` 199/200/199→999998/999999/999998；`test_qiuzhao_code_and_key_format_unchanged` 固定激活时间，改为激活后 30 天到期（expires_at `2026-10-11T21:00:00+08:00`、valid_through `2026-10-11`）、daily_limit 999999。
- 原来 7 个失败里，`test_expiry_product_and_invalid`、`test_bench_plan_is_thirty_days_from_activation`、`test_quota_message_uses_plan_limit` 补列后直接通过，没有改断言。
- **仍失败 1 项**：`test_atomic_redemption` 最后一条断言“数据库里不应有明文兑换码”。`generate_codes` 把明文写进 `code_plain`，与 `store.py` 文件头“Never persist bearer secrets or redemption codes”冲突；这不是套餐变化造成的过期断言，没有改，见第 11 节第 5 条。
- release-A 的 `test_release_a.py`（13 个 v3 参数、job_category 子串匹配、旧参数仍可用）整体不再适用，没有移植；A2 `test_doubao_fix.py` 的其余项按 v4 改写进 `test_schema.py`、`test_v4_tools.py`（工具集合、枚举、limit 上限改为 page_size 上限、search 与 detail 同一条记录相同）。
- `tests/e2e_local.py`、`tests/e2e_bench_local.py` 没有运行：它们要连一个已启动的服务，并在 `private/` 下建测试库，private/ 不在可操作范围；`tests/e2e_bench_online.py` 按要求没有读。

**其他核验：**
- `evidence/verify_schema_v4.txt`：用部署时的核验脚本在本地 import 两个产品，qiuzhao `jobs_detail params=1 / jobs_search params=15 / jobs_stats params=14`，bench 三个工具，都是 `anyOf/oneOf=False missing_type=[]`、`RESULT OK []`；只 import 不会建日志目录。
- `evidence/enum_check.txt`：`python -m qiuzhao.v4_fields check qiuzhao/data/jobs.json` → `RESULT OK`，退出码 0。
- 证据扫描：`evidence/`、`tools_list_v4*.json` 里 `Bearer`、`qz_/bm_` key 形态、`QZ-/BM-` 兑换码形态、测试哨兵值命中均为 0。

**验收问题与起草时参考值的差别**（`evidence/acceptance_v4.json`，今天固定 2026-09-11）：Q02、Q03、Q04、Q06、Q08、Q09、Q12、Q15、Q18、Q19 的总数和明确数与起草时相同；Q13、Q14、Q11、Q17 只差被过滤的测试记录（如公司 3,630→3,628）；Q01（2,910→2,766）、Q10（北京 530→523）、Q07（815→582）、Q20（18,270→18,715）变化来自：按届别筛选时排除社招（Q01 135 条、Q07 78 条）、推断档接住原来的未注明、按招聘季推断为 2027届 的岗位不再出现在 2026届 结果里（Q07 的未注明 252→2）、岗位名称和描述补抽出的届别计入明确。新增 Q21–Q24 覆盖推断档。

## 7. 性能与内存

**服务器现状**（9/11 23:1x 只读）：2 vCPU；内存 1,872 MB，已用 767、可用 919；swap 1,024 MB 已用 448。qiuzhao uvicorn RSS 169 MB（systemd MemoryCurrent 172 MB），bench 12.6 MB。线上 Python 3.12.12、fastmcp 2.14.7、pydantic 2.13.5，与本地一致。

**本地实测**（`evidence/perf_v4.json`、`sizes_v4.json`；macOS，同版本依赖）：

| 项 | 数值 |
|---|---|
| 冷构建（读 81.8 MB、有效性过滤、去重、测试记录、全部 v4 字段、排序、关键词索引） | 0.79–0.81 秒 |
| 服务启动后第一次调用（含构建） | 888 毫秒 |
| 缓存命中的 `dataset()` | 1.1 微秒（一次 stat） |
| 进程内单次调用中位数 | 默认 search 14.6 ms；page_size=20 44 ms；北京+2027届 17.5 ms；keyword 17 ms；Q01 14.5 ms；7 天截止 4.3 ms；stats 总数 43 ms；按城市 57 ms；按公司 57 ms；detail 10 个 <0.1 ms |
| HTTP 端到端中位数 | 6–35 ms（见第 8 节） |
| Python 堆 | 常驻 124 MB（25,458 条 + 小写关键词串）；构建峰值 129 MB |
| 对照：整文件 json.load（v3 每次调用都这样做） | 堆峰值 573 MB（bytes + UCS-4 字符串 + 解码缓冲） |
| uvicorn RSS（macOS） | 启动 93 MB → 第一次调用后 360 MB → 再 60 次调用后 325 MB |
| 部署前检查（单文件运行） | 0.77 秒，RSS 峰值 265 MB |

**缓存方式和估算。** 每个服务一个 uvicorn 进程、jobs.json 每天换一次，所以选进程内缓存：键是 (mtime_ns, size)，只存 v4 记录和两份小写检索串，不存原始行；读文件用分块解码，一次只保留一条原始记录。预计线上 qiuzhao 常驻 RSS 250–350 MB（现在 169 MB，多出的主要是 124 MB 缓存）；jobs.json 更新后的第一次调用会在旧缓存还在时构建新的，短时再多约 130 MB；bench 不加载岗位数据，不受影响。可用 919 MB，放得下。v3 现在每次调用都整文件解析（堆峰值约 570 MB），v4 只在文件变化时解析一次、峰值约 130 MB。

**需要知道的一点**：采集流程若原地改写 jobs.json，服务可能读到半截文件；这时继续用上一版，直到文件再次变化。建议采集流程写临时文件后 rename（Kimi 的范围，这里只提）。

## 8. 返回字节数（真实 uvicorn，`evidence/sizes_v4.json`）

| 调用 | 响应体 B | content 文本 B | jobs B | 条数 | 截断 | 粗估 token | HTTP 中位 |
|---|---:|---:|---:|---:|---|---:|---:|
| `jobs_search` 默认 | 23,011 | 21,658 | 21,394 | 10 | 否 | 6,519 | 21 ms |
| `jobs_search(page_size=20)` | 39,701 | 37,145 | 36,881 | 20 | 否 | 10,948 | 22 ms |
| `jobs_search(page_size=20, offset=2380)` | 60,547 | 57,950 | 57,682 | 19 | 是 | 17,997 | 21 ms |
| Q01 条件 | 18,715 | 17,157 | 16,622 | 10 | 否 | 5,045 | 21 ms |
| Q15 条件（page_size=20） | 43,597 | 40,900 | 40,549 | 20 | 否 | 12,284 | 11 ms |
| `jobs_stats(group_by=city)` | 2,519 | 2,149 | — | 20 组 | — | 548 | 34 ms |
| `jobs_stats(group_by=company, top=100)` | 13,299 | 11,969 | — | 100 组 | — | 3,256 | 35 ms |
| `jobs_detail`（10 个 id） | 22,818 | 21,485 | 21,394 | 10 | — | 6,476 | 6 ms |

所有 qiuzhao 结果都没有 structuredContent。对照 A 包默认调用 53,600 B。

## 9. 最终 tools/list

- qiuzhao：`research/qiuzhao-v4-impl/tools_list_v4.json`（14,778 B，粗估 4,434 token）：`jobs_detail`（1 个参数，ids 必填）、`jobs_search`（15 个）、`jobs_stats`（14 个）；没有 outputSchema。
- bench：`research/qiuzhao-v4-impl/tools_list_v4.bench.json`：`bench_detail`、`bench_search`、`bench_taxonomy`，与 A2 相同（`str | None` 已改为带默认值的 string，无 anyOf）。

## 10. 部署方案（只写，未执行；已被 `KIMI-DEPLOY.md` 取代）

> 2026-09-12：本节的目标哈希和步骤已过期（代码在 `55bd3ee`、`2f0f070` 又改过）。部署以 `research/qiuzhao-v4-impl/KIMI-DEPLOY.md` 为准，本节只留作记录。

线上 9/12 00:1x 只读核对：`core/server.py`、`qiuzhao/tools.py`、`core/store.py`、`core/static/guide.html`、`core/static/app.js` 的 sha256 都等于 main（08143798… / 77ffdb61… / 0348d335… / 4afa8338… / cb3d5e92…），`qiuzhao/v4_fields.py` 不存在；现有代码文件属主是 uid 501（显示为 UNKNOWN）:staff、644，是以前从 Mac 用 rsync -a 传上去的；`mcp-suite.service`、`mcp-suite-bench.service` 都在运行；`/var/lib/mcp-suite/call_logs` 还不存在；磁盘余 16G。

目标文件 sha256（feat/v4 `acd2499` 起未变）：

| 文件 | sha256 |
|---|---|
| `core/server.py` | `f8e0351f24db49c0f9dd3f3f50098a872954e2cd940d42e6ba76369255650b69` |
| `qiuzhao/tools.py` | `8c9b10110c9f23b39691b8ae82638f0def5171372cb514e75ff5b7223869dfb7` |
| `qiuzhao/v4_fields.py`（新文件） | `a56f6c0e706a083f223eff5871f1af5953e6cdfcdef0350ef56ac1d77ebc4eed` |
| `core/static/guide.html` | `a1e03aeaaf915bb72523f6a4cc3058fd66bc49804f367e7541d8cebec12813ec` |
| `core/static/app.js` | `cd30fbfd46544fefd28bcb117b2f540f4e9ed826f41ecbc4ccb3f0e050e9aa15` |
| `core/store.py`（只在保留 `43f1298` 时上传） | `b7f3fef42b25c51a2f3c4ff1f6cff446228f1976706eb7fd44e76bcc3db99909` |

```bash
W=~/Projects/mcp-suite-wt-v4            # feat/v4
H=root@114.215.188.109
TS=$(date +%Y%m%d-%H%M%S)
BK=/opt/mcp-suite/deploy/backup-pre-v4-$TS
CODE="core/server.py qiuzhao/tools.py qiuzhao/v4_fields.py"
STATIC="core/static/guide.html core/static/app.js"
STORE="core/store.py"                     # 丢弃 43f1298 时从下面各步去掉

# 0) 本地：确认要上传的就是上表的目标哈希
cd $W && git log -1 --format='%h %s' && shasum -a 256 $CODE $STATIC $STORE

# 1) 线上现状必须等于 main（1127cf7），v4_fields.py 必须还不存在
ssh $H 'cd /opt/mcp-suite && sha256sum core/server.py qiuzhao/tools.py core/store.py core/static/guide.html core/static/app.js; ls qiuzhao/v4_fields.py 2>&1'
#   期望 08143798… 77ffdb61… 0348d335… 4afa8338… cb3d5e92…，以及 No such file。
#   server.py / tools.py / store.py 任何一个不同：停下报告。
#   guide.html 或 app.js 不同（21:26 以后被改过）：取线上最新版，在其上重新套用 4118fe8 的 6 处替换，
#   看过 diff 后用这两份替换第 5 步的本地文件（第 0、5 步的目标哈希随之改为新文件的哈希）：
L=$W/research/qiuzhao-v4-impl/tmp/live-static && mkdir -p $L
ssh $H 'cat /opt/mcp-suite/core/static/guide.html' > $L/guide.html
ssh $H 'cat /opt/mcp-suite/core/static/app.js' > $L/app.js
(cd $L && python3 - <<'PY'
import pathlib
edits = {"guide.html": [("<code>jobs_deadlines</code>", "<code>jobs_stats</code>"),
                        ("参数 <code>limit=1</code>", "参数 <code>page_size=1</code>"),
                        ("jobs_search，参数 limit=1。", "jobs_search，参数 page_size=1。")],
         "app.js": [("请调用秋招岗位库的 jobs_deadlines，查询未来7天内即将截止的岗位，按截止日期从近到远排序，",
                     "请调用秋招岗位库的 jobs_search，参数 deadline_within_days=7、sort=deadline_asc，查询未来7天内即将截止的岗位（按截止日期从近到远），"),
                    ("jobs_search、jobs_deadlines、jobs_detail", "jobs_search、jobs_stats、jobs_detail"),
                    ("参数 limit=1，", "参数 page_size=1，")]}
for name, pairs in edits.items():
    path = pathlib.Path(name); text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        assert text.count(old) == 1, (name, old)   # 线上文案若已改掉这句，停下人工处理
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
print("re-applied")
PY
)
#   然后 diff 线上原文与 $L 下的文件，确认只有这 6 处变化。

# 2) 用线上最新 jobs.json 做枚举与数据一致性检查（只读；脚本经 stdin 传入，不落文件；约 1 秒、峰值约 270 MB）
ssh $H 'nice -n 19 /opt/mcp-suite/.venv/bin/python -B - check /var/lib/mcp-suite/jobs.json' < $W/qiuzhao/v4_fields.py
#   期望最后一行 RESULT OK。FAIL 表示出现了新届别、新行业等：先改 v4_fields.py 的枚举并重跑测试，不要上线。

# 3) 备份将被替换的文件（保持相对路径）
ssh $H "mkdir -p $BK && cd /opt/mcp-suite && cp -p --parents core/server.py qiuzhao/tools.py core/store.py core/static/guide.html core/static/app.js $BK/ && cd $BK && find . -type f | sort | xargs sha256sum | tee SHA256SUMS"

# 4) 以 mcp-suite 身份预建调用日志目录（服务第一次调用也会自己建；预建是为了现在就确认属主和权限）
ssh $H 'runuser -u mcp-suite -- install -d -m 700 /var/lib/mcp-suite/call_logs && stat -c "%U:%G %a %n" /var/lib/mcp-suite/call_logs'
#   期望 mcp-suite:mcp-suite 700

# 5) 只替换本次改动的文件：先 dry-run 看清单，再正式传；属主沿用以前的 rsync -a 方式，权限固定 644
for f in $CODE $STATIC $STORE; do rsync -a --checksum --chmod=F644 --itemize-changes --dry-run $W/$f $H:/opt/mcp-suite/$f; done
for f in $CODE $STATIC $STORE; do rsync -a --checksum --chmod=F644 --itemize-changes $W/$f $H:/opt/mcp-suite/$f; done
ssh $H 'cd /opt/mcp-suite && sha256sum core/server.py qiuzhao/tools.py qiuzhao/v4_fields.py core/store.py core/static/guide.html core/static/app.js && stat -c "%U:%G %a %n" qiuzhao/v4_fields.py'
#   期望等于第 0 步的哈希；静态文件在第 1 步重新套用过的，用 $L 下文件的哈希核对。

# 6) 重启前先在服务器上做 schema 核验：只 import 新代码，不起 HTTP、不用 token；DB 和日志目录指向 /tmp 临时路径，用完删除
for P in qiuzhao bench; do
  ssh $H "cd /opt/mcp-suite && T=\$(mktemp /tmp/v4-verify-XXXXXX) && PYTHONDONTWRITEBYTECODE=1 MCP_PRODUCT=$P MCP_DB_PATH=\$T.sqlite3 MCP_DIST_DB_PATH=\$T-dist.db MCP_JOBS_PATH=/var/lib/mcp-suite/jobs.json MCP_BENCH_PATH=/var/lib/mcp-suite/bench.json MCP_CALL_LOG_DIR=\$T-logs .venv/bin/python -W ignore - ; rm -rf \$T \$T.sqlite3 \$T.sqlite3-wal \$T.sqlite3-shm \$T-dist.db \$T-logs; ls -d /tmp/v4-verify-* 2>/dev/null || echo tmp-cleaned" < $W/research/qiuzhao-doubao-fix-20260911/scripts/verify_schema_snippet.py
done
#   期望 qiuzhao：jobs_detail params=1、jobs_search params=15、jobs_stats params=14，RESULT OK []；
#   bench：bench_detail params=1、bench_search params=8、bench_taxonomy params=0，RESULT OK []。
#   任何一个不是 OK：不要重启，直接按“回滚”恢复文件（线上进程还在跑旧代码，不受影响）。

# 7) 只重启 mcp-suite.service；mcp-suite-bench.service 不动
ssh $H 'systemctl restart mcp-suite.service; sleep 5; systemctl is-active mcp-suite.service mcp-suite-bench.service; journalctl -u mcp-suite.service --since "-2 min" --no-pager | tail -20'
#   期望 active active；journal 里没有 Traceback；出现 mcp_call_log_warning 说明日志目录写不进，回第 4 步查权限。

# 8) health（第一次请求会构建 v4 缓存，约 1–2 秒）与内存
ssh $H 'time curl -s http://127.0.0.1:8768/health; echo; ps -o pid,rss,args -C uvicorn; free -m'
curl -s https://savegems.top/qiuzhao/health
#   期望 {"status":"ok","jobs":25458 左右,"data_as_of":"…"}；qiuzhao RSS 预计 250–350 MB。

# 9) 调用一次后核对调用日志：由 Max 用自己的 key 在客户端调一次（例如 jobs_search page_size=1），执行会话不经手 key
ssh $H '/opt/mcp-suite/.venv/bin/python -B -' < $W/research/qiuzhao-doubao-fix-20260911/scripts/verify_call_log_snippet.py
ssh $H 'tail -n 3 /var/lib/mcp-suite/call_logs/tool_calls-$(TZ=Asia/Shanghai date +%Y%m%d).jsonl'
#   期望：dir mcp-suite:700、file mcp-suite:600；Bearer / api_key / redemption_code 的 hits 都为 0；RESULT OK []；
#   最后一行 product=qiuzhao、tool=jobs_search、outcome=ok、result_total 为整数、returned=1、user_ref 为 12 位十六进制。
```

**回滚**（同一个 shell，需要 `$BK`）：
```bash
ssh $H "cd /opt/mcp-suite && cp -p $BK/core/server.py core/server.py && cp -p $BK/qiuzhao/tools.py qiuzhao/tools.py && cp -p $BK/core/store.py core/store.py && cp -p $BK/core/static/guide.html core/static/guide.html && cp -p $BK/core/static/app.js core/static/app.js && rm -f qiuzhao/v4_fields.py && sha256sum core/server.py qiuzhao/tools.py core/store.py core/static/guide.html core/static/app.js && systemctl restart mcp-suite.service && sleep 5 && systemctl is-active mcp-suite.service && curl -s http://127.0.0.1:8768/health"
#   期望哈希回到第 1 步的值，health 为 ok（v3 按有效行计数，线上文件去重后约 25,463）。
```
回滚后 `/var/lib/mcp-suite/call_logs/` 原样保留（旧代码不读它）。`code_plain` 迁移只在列不存在时 ALTER，线上库本来就有这一列，所以数据库无需回滚。部署后到回滚前若 bench 被重启过（包括崩溃自动拉起），它会跑新 server.py，回滚后也要 `systemctl restart mcp-suite-bench.service`。

## 11. 需要 Max 决定（2026-09-12 已全部决定，处理见第 0 节）

1. **活动标题只写年份、不写“届”字，算不算写了届别。** 现按 SPEC 6.3 和决定 2 算“活动标题写明”（明确）。你给的 9,858 / 5,120 看起来是按“必须有‘20xx届’”统计的；按那个口径，2,661 条校招（主要是国聘专场“中国联通/中国移动/兵器集团 2027校园招聘”）会从明确匹配降为“按招聘季推断”（届别仍是 2027届）。
2. **推断出具体届别的岗位，查别的届别时不返回。** “按招聘季推断”“来源专场注明”给的是 2027届，所以查 2026届 时它们不出现：Q07（2026届 + 国企）从起草时的 815（明确 563）变为 582（明确 580），原来的 252 条未注明只剩 2 条。另一种做法是对其他届别算“含未注明”，改一处匹配规则即可。
3. **社招在传了 recruitment_type=社会招聘 时按届别查，现为推断匹配**（依据“社招不限届别”）。若希望算明确匹配，改 `BASIS_TIER` 一处。
4. **国聘 1,087 行按明确日期处理**，依据见 5.4；唯一没确认的是国聘官方对 end_time 的字面定义。如不认，改 `deadline_of` 一处，去重后这 912 条变为未注明，30 天窗口少 157 条、7 天窗口少 25 条。
5. **兑换码明文落库。** `generate_codes` 把明文写进 `code_plain`（管理后台要显示），与 `store.py` 文件头“Never persist … redemption codes”和 `test_atomic_redemption` 冲突，该测试仍失败。保留明文：改文件头和这条断言；不保留：丢弃 `43f1298` 并另改 `generate_codes` 和后台（本次按要求没动）。
6. **梧桐科技“算法工程师”**（2 个 id，同一租户有两条明显的测试岗）是否也按测试记录过滤。现在保留。
7. **枚举里加了 2028届、2024届**（各 4、3 条，来自岗位描述）。不想提供这两个选项的话，需要规定描述里抽出的届别只取某个范围。
8. **`missing_queries.jsonl`** 仍按 v3 行为在零结果时写一行，与调用日志重复，是否停掉。

## 12. 产物清单

- 代码与测试：`core/server.py`、`qiuzhao/tools.py`、`qiuzhao/v4_fields.py`、`core/store.py`、`core/static/guide.html`、`core/static/app.js`；`tests/_mcp_harness.py`、`conftest.py`、`acceptance_cases.py`、`test_call_log.py`、`test_schema.py`、`test_v4_fields.py`、`test_v4_tools.py`、`test_core.py`。
- 修订版说明书：`research/qiuzhao-v4-interface-20260911/SPEC.md`，示例 `research/qiuzhao-v4-interface-20260911/examples/`（由实现重新生成，`compat_and_errors.json` 换成 `errors.json`）。
- 本目录：`RECEIPT.md`、`tools_list_v4.json`、`tools_list_v4.bench.json`；`scripts/acceptance_v4.py`、`measure_v4.py`、`make_examples_v4.py`；`evidence/pytest-final.txt`、`verify_schema_v4.txt`、`enum_check.txt`、`acceptance_v4.json`、`sizes_v4.json`、`perf_v4.json`、`evidence/pytest/`（测试与测量时的 uvicorn 日志和调用日志样例）。
- 原始归一化脚本存档：`research/normalize-origin-20260911/`。
- 测试数据：`qiuzhao/data/jobs.json`（9/11 快照）、`qiuzhao/data/jobs.live-20260912.json`（9/12 00:52 线上版的只读副本），都被 .gitignore 忽略，未提交。`research/qiuzhao-v4-impl/tmp/` 为空。
- 2026-09-12 收尾新增：`KIMI-DEPLOY.md`；`scripts/reapply_static_edits.py`、`scripts/e2e_inprocess_check.py`、`scripts/prepare_main_ff.py`；`evidence/acceptance_v4.live-20260912.json`。
