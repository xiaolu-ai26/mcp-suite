# 秋招 MCP v4 接口说明书（已按 Max 的决定修订，与 feat/v4 实现一致）

2026-09-11 起草，2026-09-12 按 Max 的覆盖决定和实际实现修订。实现在 `~/Projects/mcp-suite` 的 `feat/v4` 分支（`qiuzhao/v4_fields.py`、`qiuzhao/tools.py`、`core/server.py`），实现收据见 `../qiuzhao-v4-impl/RECEIPT.md`。数据快照：`../qiuzhao-doubao-fix-20260911/data/jobs.json`（28,616 行；v3 的有效性过滤后 27,506 行；按 id 去重后 25,463 条；再去掉 5 条测试记录后 25,458 条；68 个字段；data_as_of 2026-09-11T12:00+08:00）。文中数量都能用附录 C 的脚本复现，“今天”固定为 2026-09-11。

**一页结论。** v4 只有三个工具：`jobs_search` 找岗位，`jobs_stats` 用同样条件计数和分组，`jobs_detail` 按 id 取详情。`jobs_deadlines` 并入 `jobs_search`，**不做任何兼容**：没有别名、没有旧参数映射，旧工具名返回“未知工具”，旧参数由 FastMCP 直接拒绝。届别、城市、专业、学历四个条件按三档返回并排序：明确匹配 → 推断匹配 → 含未注明，每条附 `match` 依据；按届别筛选时社招岗位不返回，只报条数。结果只在 content 里放一份 JSON 文本，默认调用的 HTTP 响应从 A 包的 53,600 B 降到 23,011 B。page_size 默认 10、最大 20，另有 60KB 截断预算。数据侧套用了第 6 节的 10 项修正，其中 801 条岗位大类错分全修，1,087 条国聘记录的截止日按明确日期处理，5 条上游测试记录不再出现。

---

## 1. 设计原则

学生的问题无法穷举，所以 v4 不为某类问题单独开工具，而是提供三种可以组合的操作：筛选（`jobs_search`）、统计（`jobs_stats`，条件与 search 完全相同，组值能原样填回 search）、详情（`jobs_detail`）。没见过的问题靠组合这三者回答，上线后再看调用日志决定加什么。

列表一次返回全部业务字段，省掉学生“再展开看看”的追问。68 个原始字段逐个归为业务、内部、改名合并三类，只输出业务信息（附录 B）。

招聘类型默认三种都返回。公告没写的条件是事实缺口，不能当作“不符合”丢掉；能从招聘季、来源专场、岗位类型合理推断的，标“推断匹配”并写明依据；推断不了的标“未注明”，排在最后。顶层给出三档各自的条数；学生要求“只看写明的”时用 `explicit_only=true`。

参数只用 string、integer、boolean 和字符串 enum，这是豆包能正确传参的前提。现在没有存量用户，所以 v4 不做兼容层：tools/list 只有 3 个工具，未知参数由 FastMCP 在进入工具函数前拒绝。调用日志按天写 JSONL、记录参数值（3.0 末尾）。

## 2. 工具总览

| 工具 | 一句话 | 主要入参 | 返回要点 | 上游 → 下游 |
|---|---|---|---|---|
| `jobs_search` | 按条件找岗位，每条全部业务字段 + 匹配依据 | 9 个筛选条件、`deadline_within_days`、`explicit_only`、`include_expired`、`sort`、`page_size`、`offset` | `applied_filters`、`total/explicit_total/inferred_total/unspecified_total`、分页、`jobs[]` | 条件来自用户原话、schema 枚举或 `jobs_stats.groups[i].value` → `jobs[i].id` 给 `jobs_detail` |
| `jobs_stats` | 同样的条件计数，可按一个维度分组 | 与 search 相同的 12 个条件 + `group_by`、`top` | 四个总数、`groups[]`、`fill_param` | → 组值填回 `jobs_search` 中 `fill_param` 指定的参数 |
| `jobs_detail` | 按 id 取 1–10 个岗位 | `ids`（逗号分隔） | `found`、`not_found[]`、`jobs[]` | `ids` 只能来自 `jobs_search.jobs[i].id` |

## 3. 工具定义

### 3.0 通用约定

**Schema。** 每个属性都有顶层 `type`，取值只用 `string`、`integer`、`boolean`，以及带 `enum` 的 `string`；不出现 `anyOf`、`oneOf`、`allOf`，也不用数组，工具没有 `outputSchema`。可选参数一律有默认值（`""`、`0`、`false`），客户端传 `null` 按默认值处理。枚举写在 `json_schema_extra={"enum": ["", …]}` 里（第一个值是表示“不筛选”的 `""`），长度和取值范围同样写成 `maxLength`、`minimum`、`maximum`；这些约束由工具函数自己校验并返回中文报错，pydantic 只拒绝类型不对的值和未知参数（这两类是 pydantic 英文原文）。多个值用英文逗号拼进一个字符串（`city`、`company`、`ids`）。上线前用 `../qiuzhao-doubao-fix-20260911/scripts/verify_schema_snippet.py` 核验，两个产品都要输出 `RESULT OK`。

**不做兼容。** v3 的 `cohort`、`region`、`major_category`、`limit` 以及 `jobs_detail(id=…)` 都是未知参数，FastMCP 返回 pydantic 原文 `Unexpected keyword argument`；`jobs_deadlines` 是未知工具，中间件返回“未知工具，请刷新工具列表。”（真实返回见 `examples/errors.json`）。

**枚举与同义词。** 枚举参数先在服务端做同义词归一，再校验。例如 `产品经理`→`产品`，`校招`/`秋招`→`校园招聘`，`实习`→`实习招聘`，`社招`→`社会招聘`，`研究生`→`硕士`，`专科`→`大专`，`国企`/`央企`→`国企/央企`，`2027`/`27届`/`2027年`→`2027届`，`未披露`→`未注明`；城市去掉“市”后缀并做别名归一（`北京市`→`北京`、`中国香港`→`香港`）。完整表见 `qiuzhao/tools.py` 的 `SYNONYMS`。值被归一时，`notices` 写一句“参数 job_category 的值「产品经理」已按「产品」处理。”，这样 `applied_filters` 与传入值不同也不会被误当成客户端丢参数。归一后仍不在枚举内的值报错，文案为中文，写明可选值和改用哪个参数。

**单份返回。** 三个工具都用 `@mcp.tool(output_schema=None)` 注册，返回 `ToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, separators=(",", ":")))])`，没有 structuredContent。实测见第 4 节。

**匹配依据 `match`。** 只要用了届别、城市、专业、学历中的任一条件，每条岗位就带 `match`：`level` 加上所用维度各自的依据。

| 维度 | 明确匹配的依据 | 推断匹配的依据 | 未注明 |
|---|---|---|---|
| `graduation_year` | `岗位写明`（岗位原文 cohort_raw、岗位名称或岗位描述写了该届）/ `活动标题写明` | `按招聘季推断` / `来源专场注明` / `实习未写届别` / `社招不限届别`（只在 recruitment_type=社会招聘 时出现） | `未注明` |
| `city` | `岗位写明` / `全国`（对任何大陆城市都算，查海外、港澳台城市时不算） | — | `未注明`（城市为空） |
| `major` | `岗位写明` / `专业不限` | — | `未注明` |
| `education` | `岗位写明`（岗位最低学历不高于用户学历）/ `学历不限` | — | `未注明` |

`match.level`：用到的维度全部明确时为 `明确匹配`；没有未注明、但至少一个是推断时为 `推断匹配`；至少一个维度未注明时为 `含未注明`。排序时三档依次排列，同一档内再按 `sort` 排。`explicit_only=true` 只留明确匹配（“全国”算明确，保留）；它与任一条件取值 `未注明` 同时传时报错。

**届别的判定顺序。** 每条记录只按下面第一个成立的规则定届别和依据（括号里是 25,458 条上的实际条数）：

1. 岗位原文 `cohort_raw` 写了年份 → 这些年份，依据 `岗位写明`（13,997）；活动标题（`campaign_cohort_raw` 或 `batch_name`）写的年份一并补上，依据 `活动标题写明`。
2. 只有活动标题写了年份 → `活动标题写明`（4,280）。年份抽取沿用 6.3 的规则：毕业时间窗按覆盖了哪一年的 6–8 月毕业季来算届，“2026-2027年”算两年，其余单独出现的 20xx 都算。
3. 以上都没有，且是社会招聘 → 届别不适用，`graduation_year_note=社招不限届别`（3,016）。
4. 岗位名称写了届别（年份紧挨着“届、应届、校招、校园招聘、秋招、春招、毕业、Start、Graduate”或写成 campus-2027）→ `岗位写明`（190）。
5. 岗位描述写了届别（年份紧挨着“届、应届、毕业”，或写成“毕业时间为2027年…”“2025-2027届”“2026、2027届”“2026年1月至2027年8月毕业”“Class of 2027”；年龄截止日、公司历史、证书日期等不算）→ `岗位写明`（329）。
6. 实习招聘 → `graduation_year_note=实习未写届别`（509），查任何届别都按推断匹配返回。
7. 校园招聘、发布时间在 2026-07-01 至 2026-12-31 → `2027届`，依据 `按招聘季推断`（2,437）。
8. 校园招聘、没有发布时间 → 按 `research/qiuzhao-expansion-20260910/sources_registry.jsonl` 的 `scope_graduation_year`（以详情页网址前缀对应来源）给届别，依据 `来源专场注明`（381，全部是腾讯）；对不上的算未注明（155）。
9. 其余 → 未注明（164）。

规则 7、8 给出的是具体届别，所以查别的届别时这些岗位不返回（例如按招聘季推断为 2027届 的岗位，查 2026届 时不出现）。规则 6 没有具体届别，对任何届别都按推断匹配。

**社招与届别。** 用了 `graduation_year` 条件时，规则 3 的社招岗位不返回，顶层给出 `excluded_social_total` 并在 `notices` 里说明；传了 `recruitment_type=社会招聘` 时照常返回，依据 `社招不限届别`、档次为推断匹配。`explicit_only=true` 时不给这个计数（这些岗位本来也不会是明确匹配）。

**分页与预算。** 返回 `offset`、`page_size`、`returned`、`has_next`、`next_offset`、`truncated`。服务端逐条累加 jobs 的字节数，超过 60,000 B 就在完整岗位的边界停下，置 `truncated=true`，`next_offset` 指向第一条没返回的岗位。至少返回 1 条，不截断单条内部的字段。

**服务端 instructions（最终文案）：**
> 仅提供公开官方公告中的岗位事实。回答要附原公告链接（source_url）和数据截至时间（data_as_of）。匹配分三档：明确匹配是公告写明的；推断匹配是按招聘季、来源专场或岗位类型推断的，回答时要说明是推断；未注明指原公告没写，不代表符合或不符合，不要替用户推断资格。把三档分开告诉用户。计数是岗位条数，不是招聘人数。返回里的 applied_filters 若与你传入的条件不一致、又没有 notices 说明，说明客户端没有传递参数，应告知用户，不要重复同样的调用。

**调用日志。** 沿用 A2 的结构化日志：每次工具调用追加一行 JSON 到 `$MCP_CALL_LOG_DIR/tool_calls-YYYYMMDD.jsonl`（默认 `/var/lib/mcp-suite/call_logs`，北京日期分文件，目录 700、文件 600），字段固定为 ts、product、tool、args、ua、user_ref、outcome、error_type、result_total、returned、duration_ms。`tool` 记客户端实际调用的名字（包括已不存在的 `jobs_deadlines`）；`args` 记客户端原样发送的参数值（截断、脱敏规则同 A2）；`result_total` 对 search、stats 取 total，对 detail 取 found；`returned` 取 jobs 或 groups 的长度。参数校验失败记 `error_type=invalid_arguments`。日志永久保留，服务端不轮转、不删除。

### 3.1 jobs_search

**描述原文：**
> 【岗位搜索】按条件找秋招、实习、社招岗位。每条返回全部业务字段（岗位描述、城市、届别、学历、专业、截止日、投递链接、原公告链接）和匹配依据 match。
> 【何时用】用户要看具体岗位时用，例如“北京有哪些产品岗”“字节在招算法吗”“我是27届计算机硕士能投什么”“这周截止的校招”“国企的财务岗”。只问数量、分布、排名（“哪个城市最多”“有几家公司”）时，先用 jobs_stats。
> 【参数来源】keyword、company、city、major 取自用户原话。job_category、graduation_year、education、recruitment_type、industry、sort 只能填 schema 列出的值，“27届”“校招”“研究生”这类说法服务端会自动归一。也可以把 jobs_stats.groups[i].value 原样填到 jobs_stats.fill_param 指定的参数。offset 只能取上一次返回的 next_offset。
> 【参数用法】各条件需同时满足。city、company 可用英文逗号写多个，满足任一即可。届别、城市、专业、学历四个条件分三档返回并按此排序：明确匹配（岗位写明、活动标题写明、全国、专业不限、学历不限）→ 推断匹配（按招聘季推断、来源专场注明、实习未写届别）→ 含未注明；每条的 match 写明档次和依据。用户说“只看写明的”时传 explicit_only=true（只留明确匹配）。按届别筛选时社招岗位不返回（社招不限届别，excluded_social_total 给出条数），要看社招请加 recruitment_type=社会招聘。education 填用户本人的学历，返回最低学历要求不高于它的岗位。recruitment_type 不传时校招、实习、社招都返回。deadline_within_days=N 只返回今天起 N 天内有明确截止日的岗位（招满即止和没写截止日的不返回），一般配 sort=deadline_asc。默认不返回已截止岗位。
> 【返回】applied_filters（服务端实际使用、已归一的条件；与你传的不一致又没有 notices 说明时，说明客户端丢了参数，要告诉用户，不要重复同样的调用）、total、explicit_total、inferred_total、unspecified_total、分页信息（returned、has_next、next_offset、truncated）、data_as_of、notices（参数被归一或调整时的说明），以及 jobs[]。
> 【下一步】has_next=true 且用户要更多时，用 next_offset 翻页。要对比或复查某几个岗位时，把 jobs[i].id 传给 jobs_detail。要看分布时，用相同条件调 jobs_stats。
> 【限制】page_size 默认 10、最大 20。一页超过约 60KB 时，在完整岗位处截断并置 truncated=true，用 next_offset 接着取。城市只认城市名，不认省份。数据只包含公告里写了的信息：回答时把明确匹配、推断匹配和未注明分开说，推断和未注明都不代表一定符合条件，并附 source_url 和 data_as_of。

**参数表**（各参数的默认值都表示“不筛选”）：

| 参数 | 类型 | 默认 | 取值 / 范围 | 含义 | 值从哪来 | 匹配规则 | 未注明怎么处理 | 示例 |
|---|---|---|---|---|---|---|---|---|
| `keyword` | string | `""` | ≤100 字 | 岗位名、技能、单位关键词 | 用户原话 | 不区分大小写包含于 job_title、job_category_raw、description_raw、company、recruiting_unit_raw、parent_unit_raw、hiring_department_raw、contracting_entity | — | `算法`、`转正` |
| `company` | string | `""` | ≤100 字，逗号分隔多个时取并集 | 公司或单位 | 用户原话；`jobs_stats(group_by=company)` 的组值；`jobs[i].company` | 不区分大小写包含于 company、recruiting_unit_raw、parent_unit_raw、contracting_entity | — | `字节跳动`、`腾讯,阿里巴巴` |
| `city` | string | `""` | ≤100 字，逗号分隔多个时取并集；也可填 `全国`、`未注明` | 工作城市 | 用户原话；`group_by=city` 的组值；`jobs[i].cities` 的元素 | 与修正后 `cities` 的元素完全相同；输入去掉“市”后缀并做别名归一 | 城市为空的岗位默认返回，标 `未注明`；“全国”岗位对大陆城市算明确匹配，标 `全国` | `北京`、`北京,上海` |
| `job_category` | enum | `""` | 技术/研发、产品、运营、设计、市场/营销、销售、职能/支持、金融、咨询、医疗/医药、制造/生产、科研、教育/培训、法律/合规、其他 | 岗位大类 | schema；`group_by=job_category`；`jobs[i].job_category` | 与修正后 `job_category` 完全相同 | 每条都有值，不涉及 | `产品` |
| `graduation_year` | enum | `""` | 2028届、2027届、2026届、2025届、2024届、未注明 | 用户的届别 | 用户原话（会自动归一）；schema；`group_by=graduation_year` 的年份组值 | 按 3.0 的判定顺序与三档规则 | 默认返回并标注；传 `未注明` 时只看规则 8、9 那些没有任何届别线索的岗位 | `2027届` |
| `major` | string | `""` | ≤50 字；可填 11 个专业大类名、专业关键词，也可填 `不限`、`未注明` | 专业 | 用户原话；`group_by=major_category` 的组值 | 填大类名时：`major_category` 相同，或专业原文/标签包含去掉“类”后的词；填其他词时：包含于 major_requirements_raw、major_tags | 默认返回并标注；“专业不限”算明确匹配 | `计算机类`、`统计` |
| `education` | enum | `""` | 不限、中专及以下、大专、本科、硕士、博士、未注明 | 用户本人的学历 | 用户原话（`研究生`→硕士）；schema；`group_by=education` | 岗位最低学历不高于该档时算匹配（门槛语义）；`不限` 只看写明学历不限的岗位 | 默认返回并标注；“学历不限”算明确匹配 | `硕士` |
| `recruitment_type` | enum | `""`（三种都返回） | 校园招聘、实习招聘、社会招聘 | 招聘类型 | 用户原话（校招、实习、社招会归一）；schema | 完全相同 | — | `实习招聘` |
| `industry` | enum | `""` | 互联网/科技、国企/央企、制造/工业、能源/电力、金融、医药/医疗、教育、物流/运输、传媒/广告、消费/零售、农业、房地产、其他 | 行业 | schema；`group_by=industry` | 完全相同 | — | `国企/央企` |
| `deadline_within_days` | integer | `0` | 0–366 | 今天起 N 天内（含今天）截止 | 模型把用户原话换算成天数（“国庆前”→到 9/30 的天数） | `deadline` 落在 [今天, 今天+N] | 没有明确日期的岗位（含招满即止）不返回 | `7` |
| `explicit_only` | boolean | `false` | — | 只看明确匹配 | 用户说“只看写明的” | 去掉推断匹配和含未注明的岗位 | 与条件值 `未注明` 同时传时报错 | `true` |
| `include_expired` | boolean | `false` | — | 是否包含已截止岗位 | 用户明确要看已截止的 | 截止日早于今天的默认排除 | — | `false` |
| `sort` | enum | `published_desc` | published_desc、deadline_asc | 排序 | schema；用户说“按截止时间”“最急的”时用 deadline_asc | 三档始终依次排列；deadline_asc 时没有日期的排在同档最后 | — | `deadline_asc` |
| `page_size` | integer | `10` | 1–20（>20 按 20 返回并提示） | 每页条数 | 默认值；用户要“多给点”时填 20 | — | — | `10` |
| `offset` | integer | `0` | ≥0 | 翻页起点 | 上一页的 `next_offset` | — | — | `10` |

**返回顶层字段（按输出顺序）：** `applied_filters`（只含实际生效、已归一的条件，排序非默认时含 `sort`）、`total`、`explicit_total`、`inferred_total`、`unspecified_total`、`excluded_social_total`（只在用了届别条件且没传 recruitment_type=社会招聘、没传 explicit_only 时出现）、`sort`、`offset`、`page_size`、`returned`、`has_next`、`next_offset`（没有下一页时为 null）、`truncated`、`data_as_of`，以及可选的 `notices[]`、`suggestion`（结果为 0 时给出），最后是 `jobs[]`。jobs 放在最后，客户端截断输出时仍能看到总数和分页信息。v3 顶层的 `source_urls`、`数据截至时间` 已删除。

**每条字段**（带 `?` 的字段值为空时不输出；字段的来龙去脉见附录 B）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 去重后唯一，`jobs_detail` 用这个 |
| `match` ? | object | `level` + 所用维度的依据，见 3.0 |
| `job_title` | string | 岗位名称 |
| `company` | string | 招聘单位（原 recruitment_unit） |
| `recruiting_unit_raw` ?、`hiring_department_raw` ?、`parent_unit_raw` ?、`contracting_entity` ? | string | 用人单位、部门、上级单位、签约主体原文 |
| `job_category` | string | 修正后的岗位大类，取值同参数枚举 |
| `job_category_raw` ? | string | 原文类目 |
| `recruitment_type` | string | 校园招聘、实习招聘、社会招聘 |
| `industry`、`industry_tags` ? | string、string[] | 行业、细分标签 |
| `cities` | string[] | 修正后的城市列表；可含 `全国`；空列表表示未注明 |
| `region` | string | 中国大陆、港澳台、海外，跨地区时用“、”连接；由城市推导 |
| `country` ? | string | 国家原文 |
| `graduation_years` | string[] | 如 `["2027届","2026届"]`；包括推断出的具体届别；空列表时看 `graduation_year_note` |
| `graduation_year_basis` | object | 每个届别的依据，如 `{"2027届":"按招聘季推断"}` |
| `graduation_year_note` ? | string | `graduation_years` 为空时的说明：`社招不限届别`、`实习未写届别` 或 `未注明` |
| `cohort_raw` ?、`campaign_title` ? | string | 届别原文、招聘活动标题 |
| `education` | string | 最低学历档（7 档之一） |
| `education_raw` ? | string | 学历原文（乱码写法不输出） |
| `major_category` | string | 11 个大类，或 `不限`、`未注明` |
| `major_requirements_raw` ?、`major_tags` ? | string、string[] | 专业原文、标签 |
| `deadline` | string/null | YYYY-MM-DD |
| `deadline_kind` | string | 明确日期、招满即止或长期、未注明 |
| `status` | string | 招聘中、未核验、已截止（截止日早于今天时，调用时算出） |
| `status_note` ? | string | 状态说明原文 |
| `published_at` | string/null | YYYY-MM-DD |
| `job_code` ? | string | 岗位编号 |
| `description_raw` | string | 岗位描述原文 |
| `application_url`、`source_url` | string | 投递入口、原公告链接 |
| `announcement_url` ?、`campaign_url` ?、`job_listing_url` ? | string | 公告、专场、列表页链接 |
| `source_name`、`reviewed_at` | string | 来源、核验时间 |

**报错与边界**（文案原文见 `examples/errors.json`）：

| 情况 | 处理 |
|---|---|
| 枚举外的值（同义词归一后仍不在枚举内） | `isError`：参数 job_category 的值「游戏策划」不在可选范围。可选：技术/研发、产品……。找具体岗位名（如游戏策划、UI设计）请用 keyword。 |
| 值被同义词归一 | 不报错，`notices` 写明原值和归一后的值 |
| `page_size` 大于 20 | 不报错，按 20 返回，`notices` 里说明 |
| `page_size` 小于 1、`offset` 小于 0、`deadline_within_days` 不在 0–366、文本超过长度 | `isError`，中文说明取值范围 |
| `explicit_only=true` 且某条件值为 `未注明` | `isError`：两者矛盾，请去掉其中一个 |
| 未知参数（包括 v3 的 cohort、region、major_category、limit） | FastMCP 在进入工具函数前拒绝，返回 pydantic 原文 `Unexpected keyword argument` |
| 类型不对（如 page_size 传字符串） | pydantic 原文报错 |
| 结果为 0 | 不算错误：`total=0`，附 `suggestion` |
| 数据文件缺失或损坏 | 首次加载失败时 `isError`（“岗位数据尚未就绪”）；已加载过的，继续用上一版数据 |

### 3.2 jobs_stats

**描述原文：**
> 【岗位统计】用与 jobs_search 相同的筛选条件计数，可按一个维度分组。
> 【何时用】问数量、分布、排名、对比时用，例如“北京和上海哪个产品岗多”“哪些国企招计算机最多”“27届和26届各有多少岗位”“字节的岗位主要在哪些城市”“一共有多少家公司”。也可以在 jobs_search 之前先看规模。
> 【参数来源】筛选参数的来源同 jobs_search。group_by 只能填 schema 列出的值。
> 【参数用法】group_by 不传时只返回总数。一条岗位写了多个城市或多个届别时，按 city、graduation_year 分组会计入多个组，各组之和可能大于 total（此时 multi_valued=true）。top 控制返回的组数（默认 20、最大 100），其余组的计数合计在 other_count。
> 【返回】applied_filters、total、explicit_total、inferred_total、unspecified_total、excluded_social_total（按届别筛选时没计入的社招条数）、data_as_of；分组时另有 group_by、fill_param、multi_valued、groups_total、returned_groups、other_count、groups[]（value、count、explicit_count、inferred_count、unspecified_count）。组内三档同时看筛选条件和组值本身：未注明 组算未注明，届别组按该届的依据分档（如按招聘季推断的计入 inferred_count）。
> 【下一步】用户要看某一组的岗位时，把 groups[i].value 原样填到 jobs_search 中 fill_param 指定的参数，其余条件保持不变。graduation_year 分组里的“实习未写届别”“社招不限届别”不是届别，不能填回，改用 recruitment_type。
> 【限制】计数单位是岗位条数，不是招聘人数，数据里没有招聘人数。education 分组是岗位写明的最低学历；填回 jobs_search.education 时按“门槛不高于该档”匹配，所以返回的数量会不少于该组计数。

**参数：** `keyword`、`company`、`city`、`job_category`、`graduation_year`、`major`、`education`、`recruitment_type`、`industry`、`deadline_within_days`、`explicit_only`、`include_expired`，定义与 3.1 完全相同（schema 逐字相同，测试会比对）。另加两个：

| 参数 | 类型 | 默认 | 取值 | 含义 |
|---|---|---|---|---|
| `group_by` | enum | `""`（只返回总数） | company、city、job_category、graduation_year、education、major_category、industry、recruitment_type | 分组维度 |
| `top` | integer | 20 | 1–100（>100 按 100 返回并提示） | 返回前几组，按 count 从大到小，同数按值排序 |

`fill_param` 的对应关系：group_by 为 `major_category` 时填回 `major`，其余维度填回同名参数。组值：`city` 组里会出现 `未注明`、`全国`；`graduation_year` 组的值是 `graduation_years` 里的届别，没有届别的记录按 `graduation_year_note` 分到 `社招不限届别`、`实习未写届别`、`未注明` 三组；其他维度的空值记为 `未注明`。

**组内三档。** 每条记录在某组里的档次取两者中较弱的一个：它在当前筛选条件下的档次，以及组值本身的档次（`未注明` 组为未注明；届别组按这一届的依据，`按招聘季推断`、`来源专场注明` 为推断；`实习未写届别`、`社招不限届别` 组为推断）。所以 `stats(group_by=graduation_year)` 的 `2027届` 组里，明确匹配数正好等于 `stats(graduation_year=2027届, explicit_only=true).total`。

**返回：** 四个总数和 `data_as_of` 始终返回；传了 group_by 时再加 `group_by`、`fill_param`、`multi_valued`、`groups_total`、`returned_groups`、`other_count`、`groups[]`。报错规则同 3.1，另有两条：group_by 取枚举外的值时报错；top 小于 1 时报错。

### 3.3 jobs_detail

**描述原文：**
> 【岗位详情】按 id 取 1–10 个岗位的全部业务字段。
> 【何时用】用户要对比几个岗位、细看某一个（“第 2 个详细说说”），或跨轮对话复查之前看过的岗位时用。
> 【参数来源】ids 只能取 jobs_search 返回的 jobs[i].id（或之前 jobs_detail 返回的 id），不要自己拼；多个用英文逗号分隔。
> 【返回】requested、found、not_found[]、data_as_of、jobs[]（字段与 jobs_search 的每条相同，不含 match）。
> 【下一步】not_found 不为空，说明岗位已下线或 id 有误，改用 jobs_search 重新查。
> 【限制】一次最多 10 个 id，超过报错。

| 参数 | 类型 | 默认 | 取值 | 值从哪来 |
|---|---|---|---|---|
| `ids` | string（必填） | — | 1–10 个 id，英文逗号分隔，重复的会去掉 | `jobs_search.jobs[i].id` |

报错：ids 为空或超过 10 个时 `isError`。被过滤掉的测试记录（6.10）按不存在处理，出现在 `not_found`。

## 4. 返回大小预算

**每条大小**（紧凑 JSON，UTF-8 字节，不含 match）：

| | 条数 | 均值 | 中位 | P95 | P99 | 最大 |
|---|---:|---:|---:|---:|---:|---:|
| v3（线上 `public()` 输出） | 27,506 | 2,588 | 2,471 | 4,111 | 5,436 | 17,382 |
| v4（实现输出，去重、去测试记录后） | 25,458 | 2,303 | 2,170 | 3,826 | 5,086 | 16,900 |

v4 每条的字节里，`description_raw` 占 49.6%。

**每页大小**（v4 默认排序，把全库按 page_size 逐页切分，含约 430 B 的顶层字段，不截断）：

| page_size | 页数 | 均值 B | P95 B | 最大 B | 超过 60KB 的页 |
|---:|---:|---:|---:|---:|---:|
| 5 | 5,092 | 11,951 | 17,502 | 43,969 | 0 |
| **10** | 2,546 | 23,471 | 33,405 | 57,363 | 0 |
| **20** | 1,273 | 46,511 | 64,903 | 104,160 | 108 |
| 30 | 849 | 69,524 | 95,438 | 146,911 | 615 |
| 50 | 510 | 115,450 | 155,170 | 244,088 | 509 |

**结论：** `page_size` 默认 10、上限 20；jobs 数组的预算 60,000 B。page_size=20 时，1,273 页里有 108 页会在岗位边界截断（实测：逐页调用 `jobs_search(page_size=20, offset=k)`，truncated=true 的正好 108 页）；全库最大的 20 条拼在一起是 172,978 B，截断后仍控制在预算内。

**HTTP 实测**（真实 uvicorn、JSON-RPC 响应体；`../qiuzhao-v4-impl/scripts/measure_v4.py`，结果在 `../qiuzhao-v4-impl/evidence/sizes_v4.json`；粗估 token：汉字和全角字符 1 个、其余每 4 个字符 1 个，只是量级估计）：

| 调用 | 响应体 B | content 文本 B | jobs B | 条数 | 粗估 token |
|---|---:|---:|---:|---:|---:|
| `jobs_search` 默认（10 条） | 23,011 | 21,658 | 21,394 | 10 | 6,519 |
| `jobs_search(page_size=20)` | 39,701 | 37,145 | 36,881 | 20 | 10,948 |
| `jobs_search(page_size=20, offset=2380)`（截断页） | 60,547 | 57,950 | 57,682 | 19 | 17,997 |
| Q01 条件（10 条） | 18,715 | 17,157 | 16,622 | 10 | 5,045 |
| `jobs_stats(group_by=company, top=100)` | 13,299 | 11,969 | — | 100 组 | 3,256 |
| `jobs_detail`（10 个 id） | 22,818 | 21,485 | 21,394 | 10 | 6,476 |
| tools/list | 14,778 | — | — | 3 个工具 | 4,434 |

对照：A 包默认调用（10 条，content + structuredContent 两份）的 HTTP 响应体是 53,600 B；本说明书起草时进程内实测的双份 44,439 B、方案 A 22,857 B。实现采用方案 A，没有 structuredContent。据 Claude Code 文档，MCP 工具输出超过 10,000 token 会提示，默认上限 25,000 token；截断页约 1.8 万粗估 token，在上限内，要在验收时实测确认；豆包、千问的上限未知。

**上线前在 Claude Code、豆包、千问上各验证一遍：**
1. tools/list 显示三个工具，没有 outputSchema；schema 核验输出 `RESULT OK`。
2. 只有 content 时模型能读到完整结果：让它原样复述 `applied_filters`、`total`、最后一条的 `id`、`has_next` 和 `next_offset`。
3. 某个客户端读不到结果时，判断它是否只读 structuredContent：给它临时开方案 B（摘要文本 + structured_content）对照。
4. 20 条满页（接近 60KB）有没有被客户端截断或报超长：Claude Code 看是否出现超过 10k token 的提示；豆包、千问看是否报错或只显示一部分。
5. 中文不转义（UTF-8 原样输出）时显示正常。
6. 报错文案能被模型读到，并据此改参数重试，不会原样重试陷入死循环。
7. 豆包实际传了哪些参数：查调用日志的 `args`。
8. 用缓存了 v3 工具表的旧会话调用 `jobs_deadlines`、`limit`、`cohort`：客户端应收到“未知工具，请刷新工具列表。”或 `Unexpected keyword argument`，确认模型据此刷新工具列表或改用 v4 参数，而不是原样重试（调用日志里同一 user_ref 的相同参数不应连续出现）。

## 5. 返回示例（`examples/`）

示例由 `../qiuzhao-v4-impl/scripts/make_examples_v4.py` 用实现（`qiuzhao/tools.py`）对 data/jobs.json 实际运行生成，“今天”固定为 2026-09-11；报错类示例是真实 HTTP 调用的返回。为便于阅读，page_size 取 2–3。

| 文件 | 请求 | 看点 |
|---|---|---|
| `jobs_search.1_city_year_major.json` | 成都 + 2027届 + 计算机类 | total 1,914：明确 225、推断 26、含未注明 1,663；另有 167 条社招未返回；第 1 页就出现 `city=全国` |
| `jobs_search.2_explicit_inferred_boundary.json` | 同上，offset=224 | 最后一条明确匹配之后接着推断匹配 |
| `jobs_search.2b_inferred_unspecified_boundary.json` | 同上，offset=250 | 推断匹配之后接着含未注明 |
| `jobs_search.3_deadline_7d.json` | 校园招聘，7 天内截止，deadline_asc | 166 条，从今天截止的开始 |
| `jobs_search.4_tencent_2027_source_scope.json` | 腾讯 + 2027届 | 814 条里 812 条是推断匹配，依据 `来源专场注明` |
| `jobs_stats.1_product_2027_by_city.json` | 产品 + 2027届，按城市分组 | 北京 523（明确 496、推断 27）、上海 370；有 `未注明`、`全国` 组；multi_valued=true |
| `jobs_stats.2_soe_cs_by_company.json` | 国企/央企 + 计算机类，按公司分组 | 中国移动 1,356、中国邮政 1,070、航天科工 488 |
| `jobs_stats.3_campus_by_education.json` | 校园招聘，按学历分组 | 未注明为最大的一组；有学历门槛的说明 |
| `jobs_stats.4_by_graduation_year.json` | 按届别分组 | 2027届 21,533（明确 18,715、推断 2,818）；`社招不限届别`、`实习未写届别`、`未注明` 三组 |
| `jobs_detail.1_two_ids.json`、`.2_not_found.json` | 两个 id；一个真 id 加一个编造的 id | `not_found` 与 `suggestion` |
| `errors.json` | 同义词、超上限、5 类报错、v3 旧参数和旧工具 | `notices` 文案、中文报错、旧名直接被拒绝 |

## 6. 数据修正清单

口径：“27,506 行”是 v3 的有效性过滤后、未去重的行数，本说明书起草时的数字都按这个口径算，实现后逐项复核一致；“最终”是实现的 build 报告，按 id 去重、去掉测试记录后的 25,458 条。“管线”指采集和归一化脚本，它们产出 jobs.json；“服务端”指 `qiuzhao/v4_fields.py`（从原始字段算 v4 字段）和 `qiuzhao/tools.py`（匹配）。产出 `*_normalized` 的原始脚本已找到并存档在 `../normalize-origin-20260911/`；v4 仍以这些字段为参考，缺字段时用修正后的同一套规则从原始字段兜底。

| # | 问题 | 现状 | 修正规则 | 最终 | 归属 |
|---|---|---|---|---|---|
| 6.1 | id 重复 | 1,492 个 id 重复，涉及 3,535 行，多出 2,043 行，全部逐字段相同（国聘系重复采集，不是一岗多城） | 服务端加载时按 id 去重，保留第一次出现的；管线按 id upsert | 25,463 条，id 唯一。9/12 00:05 采集流程修复后，线上 jobs.json 已无重复行 | 管线 + 服务端兜底 |
| 6.2 | job_category 错分 | 原脚本先匹配“技术/研发”，关键词过宽（技术、数据、AI、go 等），原文是产品、运营等的岗位被归成技术/研发 | 归一化结果是技术/研发、而原文类目命中词表时以原文为准（`RAW_CATEGORY_RULES`；“产品/工程研发”因含“研发”保留原判）。没有 `job_category_normalized` 时，用原脚本的词表但把技术/研发放到最后、先看原文类目 | 27,506 行口径改判 801 条：产品 370、运营 244、设计 80、销售 72、市场/营销 21、职能/支持 14（与起草时一致）；最终 770 条。产品岗最终 1,279 条 | 服务端 |
| 6.3 | 届别多值、依据与推断 | 原脚本只读 cohort_raw，不读活动标题；写了两届的只取第一个 | 多值；判定顺序见 3.0 | 最终：岗位原文 13,997、活动标题 4,280、岗位名称 190、岗位描述 329、按招聘季推断 2,437、来源专场注明 381、实习未写届别 509、社招不限届别 3,016、未注明 319（其中 155 条是校招无发布时间且来源对不上）。含 2027届 21,533 条（岗位写明 14,343、活动标题写明 4,372、按招聘季推断 2,437、来源专场注明 381）；多届 2,152 条；数据里出现的届别有 2028届 4、2027届、2026届 2,206、2025届 53、2024届 3 | 服务端 |
| 6.4 | 学历归一化 | 原文非空写法 30 种，6 种是乱码（93 行，全部来自“国聘行动”） | 7 档，“本科/硕士”取较低一档，乱码归为未注明、原文不输出 | 最终：未注明 9,351、本科 8,915、硕士 5,035、博士 1,071、大专 831、中专及以下 130、不限 125；乱码 89 条。正文补抽学历留到下一版 | 服务端 |
| 6.5 | 专业 | 未披露 12,865 行；“详见职位描述”“未披露”被归成“其他” | 占位词归为未注明；“专业不限”归为 `major_category=不限` | 最终：未注明 12,145（47.7%），不限 196，写明 13,117 | 服务端 |
| 6.6 | 截止日口径统一 | deadline_type 8 种写法；“国聘行动官方招聘平台”1,087 行标 undisclosed 却带 `YYYY-MM-DD HH:MM:SS` 日期；16 行 2099 占位 | 能解析出日期且早于 2099 年的算明确日期（含那 1,087 行，依据见下）；2099 占位、招满即止、rolling 算招满即止或长期；其余未注明。排序由近到远 | 最终：明确日期 17,861、未注明 6,303、招满即止或长期 1,294；那 1,087 行去重后 912 条。30 天内 3,714，7 天内 374 | 服务端（管线仍应写对 deadline_type） |
| 6.7 | 城市与“全国” | 539 行三个城市字段都是 `{'area_code': …}` 字典串；英文、别名、非城市词混入 | 解析 area_cn；别名归一；去掉未披露、未知、多地和非城市词 | 27,506 行口径修复 539 行；最终全国 925、未注明 1,365。北京 8,219 = 岗位写明 5,939 + 全国 915 + 未注明 1,365。省级和区县写法留给管线 | 服务端 |
| 6.8 | region、overseas 与 status | region 145 种写法；373 行海外城市却标 overseas_flag=false；status 4 种写法 | region 由城市推导；status：open、active、qualified→招聘中，unverified→未核验，截止日已过→已截止（调用时算），removed→不载入 | 最终 region：中国大陆 25,006、海外 371、港澳台 34、跨地区 47；status：招聘中 25,366、未核验 92 | 服务端 |
| 6.9 | 顺带发现（不处理） | 同单位、同标题、同描述但 id 不同的 1,801 组；published_at 晚于今天的 234 行 | 不合并（决定 7），管线下一轮处理 | — | 管线 |
| 6.10 | 上游测试记录 | 国聘系里有租户测试岗位：岗位名 `test50`、`zyx联调测试修改职位01`、`亲属关系优化测试职位26070701`，描述只有“测试数据”的 `参与单位数据统计1` | 整条过滤：岗位名整体是 test+数字；岗位名含“测试修改职位”或“测试职位”+4 位以上数字；描述只由“测试数据”组成；描述含“测试职位请勿投递”；描述是“这是工作职责…这是任职要求”模板 | 5 个 id（有效行里 8 行）不再出现，`jobs_detail` 查它们返回 not_found | 服务端（管线也应过滤） |

**国聘 1,087 行的截止日（决定 5）。** 按“确认 end_time 是投递截止时间就当明确日期”的决定，依据如下：`qiuzhao/collector/guopin.py`（第 141–148 行）把国聘接口的 `end_time` 截取前 10 位作为 `deadline`，标 `deadline_type=explicit`、`deadline_scope=official_role_record`，并在截止日已过时把状态标为 expired，也就是现行采集器本来就把 end_time 当岗位截止日；这 1,087 行的日期格式与国聘接口原始 `end_time` 相同（`YYYY-MM-DD HH:MM:SS`，`../qiuzhao-v3-launch-20260910/conditional_release/_guopin_raw.json` 里 61 条都是 19 位），其中 810 行是 23:59:59；有 420 行能按 source_record_id 对上别的来源（主要是 guopin.py 产出、deadline_scope=official_role_record 的记录），日期全部相同、没有一条不同。能确认的是“这些值就是国聘的 end_time，且现行采集器把它当截止日”；国聘官方文档里 end_time 的字面定义没有查到，这一点写进了收据。

招聘类型三类（最终）：校园 19,899、社会 3,062、实习 2,497。公司 3,628 家。

## 7. 变化说明（v4 不做兼容）

现在没有用户，v4 直接替换 v3：
1. **工具列表**：新增 `jobs_stats`，`jobs_deadlines` 删除。旧会话缓存着旧工具表，调用旧名会收到“未知工具，请刷新工具列表。”；重连（`/mcp`）或新开会话后才能看到新工具。
2. **参数**：`cohort`、`region`、`major_category`、`limit` 删除（传了就报 `Unexpected keyword argument`），`jobs_detail` 的 `id` 改为 `ids`；新增 `education`、`explicit_only`、`include_expired`、`deadline_within_days`、`sort`、`page_size`；`city`、`company` 支持逗号分隔多个值；枚举参数接受“校招”“产品经理”“研究生”这类说法。
3. **结果变多、口径变化**：带届别、城市、专业、学历条件时，会多出推断匹配和未注明的岗位（按档次排在后面并标注）；按届别筛选时社招不返回。例如北京 + 2027届：total 7,463（明确 5,044、推断 1,094、未注明 1,325），另有 728 条社招未计入。产品岗 1,279 条。截止日窗口按统一口径计算，排序由近到远。page_size 上限从 100 降到 20。默认不返回已截止岗位。
4. **字段**：改名 7 处（recruitment_unit→company、job_category→job_category_raw、job_category_normalized→job_category、graduation_year_normalized→graduation_years + graduation_year_basis + graduation_year_note、campaign_cohort_raw→campaign_title、major_normalized→major_category、deadline_type→deadline_kind）；删除 city_normalized、cities_normalized（合并进 cities）、overseas_flag（合并进 region）、cohort_filter_scope（由 match 和 graduation_year_basis 取代）、20 个内部字段，以及顶层的 source_urls、数据截至时间。
5. **返回只有一份**：不再有 structuredContent。
6. **静态页**：`guide.html` 的“接入成功”一节和 `app.js` 的接入提示词、`deadline` 示例已改为 `jobs_stats`、`page_size=1`、`jobs_search` 配 `deadline_within_days=7`、`sort=deadline_asc`（feat/v4 的单独提交）。`exclude` 那条“排除某些公司”仍只能由模型在结果里自己剔除（决定 12：不做排除）。
7. **`/health`**：`jobs` 返回去重、去测试记录后的条数（25,458），v3 返回的是未去重的有效行数。

**changelog 文案**（沿用 `changelog.json` 的格式）：
```json
{"time": "<上线时间>", "version": "v4.0", "title": "岗位查询升级：统计、三档匹配依据、截止日统一",
 "changes": ["新增 jobs_stats：按公司、城市、岗位大类、届别、学历、专业、行业、招聘类型分组计数",
             "按届别、城市、专业、学历筛选时分三档返回：公告写明的在前，按招聘季、来源专场或岗位类型推断的其次，没写的最后并标“未注明”；可用 explicit_only 只看写明的",
             "所有写了具体日期的岗位都参与“N 天内截止”筛选；jobs_deadlines 并入 jobs_search（deadline_within_days + sort=deadline_asc），按截止日由近到远",
             "修正 801 条岗位大类错分、539 条城市乱码、373 条海外岗位地区标错，去除重复收录和上游测试岗位",
             "每页默认 10 条、最多 20 条；旧工具名和旧参数名（jobs_deadlines、cohort、region、major_category、limit）已停用，请重连刷新工具列表"]}
```

## 8. 验收问题集

执行方法：部署后在 Claude Code、豆包、千问里各问一遍，用调用日志核对实际调用链，再对照“必须包含”逐项判断。参考值由 `../qiuzhao-v4-impl/scripts/acceptance_v4.py` 用实现在本地算出（2026-09-11 数据，“今天”固定为 2026-09-11），存于 `../qiuzhao-v4-impl/evidence/acceptance_v4.json`；`tests/test_v4_tools.py` 核对 HTTP 服务返回与它逐字相同。上线当天用当天的 jobs.json 重跑脚本更新数字；调用链和“必须包含”的要素不随数据变化。括号里依次是明确 / 推断 / 未注明。

| # | 学生原话 | 类型 | 期望调用链 | 正确回答必须包含 | 参考值 |
|---|---|---|---|---|---|
| Q01 | 我是27届计算机专业硕士，想留杭州，有哪些岗位能投？ | 筛选 | search(city=杭州, graduation_year=2027届, major=计算机类, education=硕士) | 先列明确匹配的岗位；说明另有推断匹配和未注明的各多少条、社招未计入；每条附 source_url；给出 data_as_of | 2,766（196 / 22 / 2,548），社招未计入 135 |
| Q02 | 字节现在有哪些产品经理岗位？主要在哪些城市？ | 筛选 + 统计 | search(company=字节跳动, job_category=产品) + stats(同条件, group_by=city) | 总数、城市分布；说明只列了第一页或主动翻页 | 637；北京 422、上海 306、深圳 71 |
| Q03 | 接下来一周要截止的校招有哪些？按截止时间排 | 截止 | search(recruitment_type=校园招聘, deadline_within_days=7, sort=deadline_asc) | 按日期从近到远；给出 application_url | 166 |
| Q04 | 北京有没有不限专业的国企岗位？ | 筛选 | search(city=北京, industry=国企/央企, major=不限) | 只算原文写了“专业不限”的岗位；未注明的不算“不限” | 10 |
| Q05 | 第 2 个岗位的具体要求是什么？投递链接给我 | 下钻 | detail(ids=<Q01 返回的第 2 个 id>) | id 取自上一轮结果，不自己编；给出 application_url 和 source_url | found 1 |
| Q06 | 上海有能转正的实习吗？ | 筛选 | search(recruitment_type=实习招聘, city=上海, keyword=转正) | 说明“转正”是在描述里做关键词匹配 | 204（201 / 0 / 3） |
| Q07 | 我 2026 年毕业还没找到工作，还能投哪些央企？ | 资格 | search(graduation_year=2026届, industry=国企/央企) | 说明这些岗位的原文多为“2026届未就业可报”，依据来自原文；未注明的单独说 | 582（580 / 0 / 2），社招未计入 78 |
| Q08 | 国庆前截止的产品岗有哪些？ | 截止 | search(job_category=产品, deadline_within_days=19, sort=deadline_asc) | 模型把“国庆前”换算成到 9/30 共 19 天；按日期排列 | 19 |
| Q09 | 腾讯和阿里在深圳招算法吗？ | 筛选 | search(company=腾讯,阿里巴巴, city=深圳, keyword=算法) | 两家都要覆盖到（写一次调用或两次调用都可以） | 272 |
| Q10 | 北京和上海，哪边的 27 届产品岗更多？ | **统计对比** | stats(job_category=产品, graduation_year=2027届, group_by=city) | 给出两个数和明确匹配数；说明一条岗位可同时算进多个城市 | 北京 523（496 / 27 / 0）、上海 370（343 / 26 / 1） |
| Q11 | 今年校招哪些行业招得最多？给我前五 | **分布** | stats(recruitment_type=校园招聘, group_by=industry, top=5) | 说明单位是岗位条数，不是人数 | 互联网/科技 8,895、国企/央企 5,798、制造/工业 1,999、能源/电力 1,265、其他 742 |
| Q12 | 哪几家国企招计算机专业最多？ | **排行 + 下钻** | stats(industry=国企/央企, major=计算机类, group_by=company, top=5) → 可再 search(company=<第 1 名>, major=计算机类) | 前几名及其数量；组值原样填回 search | 中国移动 1,356、中国邮政 1,070、航天科工 488 |
| Q13 | 本科和硕士能投的岗位差多少？ | **对比 + 口径** | stats(education=本科)、stats(education=硕士)，或 stats(group_by=education) | 解释门槛语义（硕士也能投要求本科的岗位）；未注明的两边都算 | 明确：本科 10,001、硕士 15,036；未注明 9,351 |
| Q14 | 为什么很多岗位没写专业要求？这些我能投吗？ | **数据解释** | stats(major=计算机类) + stats(group_by=major_category) | 未注明的比例；“未注明=公告没写，要看原公告”；不替用户下结论 | 未注明 12,145（47.7%） |
| Q15 | 帮我排一下未来两周上海技术岗的投递计划 | **规划** | search(city=上海, job_category=技术/研发, deadline_within_days=14, sort=deadline_asc, page_size=20) + 翻页 | 按日期分组；has_next=true 时主动翻页或向用户说明还有 | 39（26 / 0 / 13） |
| Q16 | 对比一下这两个岗位，哪个更适合学统计的我？ | **对比** | detail(ids=a,b) | 对比专业要求原文；不编造原文里没有的要求 | found 2 |
| Q17 | 你们的数据是什么时候的？一共有多少家公司？ | **元数据** | stats(group_by=company, top=1) | 给出 data_as_of 和 groups_total | 2026-09-11T12:00+08:00；3,628 家；25,458 条 |
| Q18 | 字节的岗位主要在哪些城市？技术和非技术各多少？ | **画像** | stats(company=字节跳动, group_by=city) + stats(company=字节跳动, group_by=job_category) | 两个维度的分布 | 4,171 条；北京 2,287、上海 1,692；技术/研发 2,453 |
| Q19 | 有新加坡或者海外的岗位吗？ | **边界** | search(city=新加坡) 和/或 stats(group_by=city) | 不能把“全国”岗位当成新加坡的；城市未注明的单独说 | 新加坡明确 87，城市未注明 1,365 |
| Q20 | 我只想看明确写了招 27 届的，没写届别的不要 | 筛选 | search(graduation_year=2027届, explicit_only=true) | 结果里没有推断和未注明；说明依据包括“活动标题写明” | 18,715 |
| Q21 | 我是 27 届，腾讯现在有哪些岗位？ | **推断** | search(company=腾讯, graduation_year=2027届) | 说明大部分是按腾讯 2027届校招专场推断的，不是岗位原文写明 | 814（2 / 812 / 0） |
| Q22 | 有哪些 27 届能投的实习？ | **推断** | search(recruitment_type=实习招聘, graduation_year=2027届) | 区分写明届别的实习和“实习未写届别”的实习 | 2,495（1,986 / 509 / 0） |
| Q23 | 社招里有 27 届也能投的吗？ | **推断** | search(recruitment_type=社会招聘, graduation_year=2027届) | 说明社招一般不限届别但通常要求经验，依据是“社招不限届别”，不是公告写明 | 3,062（46 / 3,016 / 0） |
| Q24 | 27 届和 26 届各有多少岗位？没写届别的有多少？ | **统计 + 口径** | stats(group_by=graduation_year)，或 stats(graduation_year=2027届)、stats(graduation_year=2026届) | 分开报明确和推断；实习未写届别、社招不限届别、未注明单独说 | 2027届 21,533（18,715 / 2,818）、2026届 2,206、实习未写届别 509、社招不限届别 3,016、未注明 319 |

其中 13 个问题（Q10–Q14、Q16–Q19、Q21–Q24）超出浏览、筛选、下钻、截止这四类。与起草时参考值的差别及原因见收据第 6 节（主要是：社招按届别筛选时不再返回；推断档接住了原来的大部分未注明；岗位名称和描述补抽了届别；去掉了 5 条测试记录）。

## 9. Max 的决定（已全部决定）

| # | 问题 | 决定 | 实现 |
|---|---|---|---|
| 1 | jobs_deadlines 的去留 | 并入 search，不留别名 | tools/list 只有 3 个工具；旧名返回“未知工具” |
| 2 | “活动标题写明”算不算明确匹配 | 算，依据标“活动标题写明” | 3.0 规则 1、2 |
| 3 | education 的语义 | 按门槛匹配 | 3.1；stats 描述写明组值填回后数量不少于组计数 |
| 4 | “全国”在 explicit_only 时保留吗 | 保留 | 全国算明确匹配 |
| 5 | 1,087 条 undisclosed 却带日期的国聘记录 | 确认 end_time 是投递截止时间就当明确日期，否则当未注明 | 当明确日期，依据见第 6 节末 |
| 6 | 字段改名是否一次改完 | 一次改完 | 第 7 节第 4 条 |
| 7 | 351 组同单位、同标题、同描述、同城市、不同 id 的岗位要不要合并 | 不合并 | 未处理 |
| 8 | job_category 修正的范围 | 801 条全修 | 6.2 |
| 9 | 学历从正文补抽 | 放到下一版 | 未处理 |
| 10 | page_size 上限 20 + 60KB 预算 | 默认 10、上限 20，另加 60KB 预算 | 3.0、第 4 节 |
| 11 | 单份返回用方案 A 还是 B | 方案 A | 3.0 |
| 12 | city、company 多值；要不要做排除 | 多值做，排除不做 | 3.1 |
| 13 | 默认排除已截止岗位 | 是 | `include_expired=false` |
| 14 | 按省份筛选 | 不支持 | 描述写明只认城市名 |
| 15 | 枚举维护 | 测试加部署前检查：枚举和数据取值不一致就失败 | `tests/test_schema.py`；`python qiuzhao/v4_fields.py check <jobs.json>` |
| 16 | “国企/央企”和行业混在同一字段 | 不拆 | 未处理 |
| 17 | 多个条件叠加后未注明的尾巴很长 | 维持决定 5（未注明照常返回、排在最后） | 三档排序 |

另外按 Max 的覆盖决定：v4 不做任何兼容（原 3.4 节整节删除）；原文和活动标题都没写届别的记录按 3.0 的规则 3–9 定届别和依据；过滤上游测试记录（6.10）。

**实现中遇到、需要 Max 再看的地方**（详见收据第 11 节）：活动标题只写年份不写“届”字时仍算“活动标题写明”；按招聘季推断为 2027届 的岗位查 2026届 时不返回；社招在传了 recruitment_type=社会招聘 时算推断匹配；枚举加入了 2028届、2024届。

**做不到或未验证：**
- Claude Code 的 token 上限，以及豆包、千问的输出上限和 structuredContent 支持情况，只能在验收时实测。
- 国聘官方文档里 end_time 的字面定义没有找到（第 6 节末）。

## 附录 A：保留独立 jobs_deadlines 的方案（未采用）

决定 1 选了并入 search。当时的备选是保留 `jobs_deadlines`（`days`、`page_size`、`offset`，统一截止口径、由近到远），代价是要么不能和其他条件组合，要么复制一套筛选参数，并且维护两套分页逻辑。如果上线后日志显示“截止类”问题的 search 调用常常漏传 `deadline_within_days`，再考虑恢复独立工具。

## 附录 B：68 个字段的归类

完整表格见 `evidence/field_inventory.md`（起草时由 `scripts/v4_numbers.py` 生成）。实现按这张表输出，另加一个新字段 `graduation_year_note`。

- **业务字段，原样输出（23 个）**：id、job_title、education_raw、cohort_raw、application_url、source_url、source_name、description_raw、recruitment_type、industry、country、contracting_entity、major_requirements_raw、major_tags、recruiting_unit_raw、hiring_department_raw、parent_unit_raw、announcement_url、campaign_url、job_listing_url、status_note、industry_tags、reviewed_at。
- **改名、合并或修正（25 个，信息都保留在输出里）**：
  - 改名：recruitment_unit→company；job_category→job_category_raw；job_category_normalized→job_category；graduation_year_normalized→graduation_years + graduation_year_basis + graduation_year_note；campaign_cohort_raw→campaign_title；major_normalized→major_category；deadline_type→deadline_kind。
  - 合并：company（与 recruitment_unit 相同）、title（与 job_title 相同）、job_id（与 id 相同）、detail_url（与 source_url 相同）、category（与 job_category 相同）、batch_name（并入 campaign_title）、position_code（并入 job_code）、job_code、cities、city_normalized、cities_normalized（三个城市字段合为一个修正后的 cities）、overseas_flag（并入 region）、recruitment_type_raw、nature_raw（并入 recruitment_type）。
  - 修正：deadline、status、published_at、region。
- **仅内部使用（20 个，不输出）**：source_record_id；evidence_path、announcement_evidence_path、directory_evidence_path（服务器本地路径）；deadline_scope、published_at_scope、cohort_scope、requirements_scope、education_scope、job_title_scope、recruitment_scope_note（采集流程标记）；record_kind；incomplete；source_status_raw；source_is_apply_raw（已折算进 status）；source_group_key；company_id；first_seen_at；verified_at；fortune_rank（全为 null）。

## 附录 C：复现

```bash
cd ~/Projects/mcp-suite-wt-v4          # feat/v4；qiuzhao/data/jobs.json 为 2026-09-11 快照（已被 .gitignore 忽略）
PY=~/Projects/mcp-suite/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -p no:cacheprovider -q                      # 全部测试
PYTHONDONTWRITEBYTECODE=1 $PY research/qiuzhao-v4-impl/scripts/acceptance_v4.py    # → ../qiuzhao-v4-impl/evidence/acceptance_v4.json
PYTHONDONTWRITEBYTECODE=1 $PY research/qiuzhao-v4-impl/scripts/measure_v4.py       # → tools_list_v4*.json、evidence/sizes_v4.json、perf_v4.json
PYTHONDONTWRITEBYTECODE=1 $PY research/qiuzhao-v4-impl/scripts/make_examples_v4.py # → 本目录 examples/
$PY qiuzhao/v4_fields.py check qiuzhao/data/jobs.json                             # 枚举与数据一致性检查，RESULT OK / FAIL
```
- 本目录 `scripts/v4lib.py` 是起草时的参考实现，没有推断档和测试记录过滤；`tests/test_v4_fields.py` 用它核对实现：届别以外的全部字段在 27,506 行上逐条一致，届别在岗位原文或活动标题写了年份的记录上一致。
- 本目录 `scripts/` 其余脚本和 `evidence/` 是起草时的产物，数字按起草时的规则算，不再更新。
