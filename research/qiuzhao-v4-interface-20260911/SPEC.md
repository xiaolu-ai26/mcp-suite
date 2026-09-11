# 秋招 MCP v4 接口说明书（待 Max 审）

2026-09-11 · 只写文档，未改代码、未部署、未访问服务器。数据快照：`../qiuzhao-doubao-fix-20260911/data/jobs.json`（28,616 行，`load()` 过滤后 27,506 条，68 个字段，data_as_of 2026-09-11T12:00+08:00）。文中每个数量都能用 `scripts/` 复现（见附录 C）；“今天”固定为 2026-09-11。

**一页结论。** v4 保留三个工具：`jobs_search` 找岗位，`jobs_stats` 用同样条件计数和分组，`jobs_detail` 按 id 取详情。`jobs_deadlines` 并入 `jobs_search`，旧名在中间件里做一版隐藏别名，所以 tools/list 仍只有三个工具。届别、城市、专业、学历四个条件默认返回“明确匹配 + 未注明”，每条附 `match` 依据。结果改为只返回一份 content 文本，本地实测线上字节数从 44,439 B 降到 22,857 B。page_size 默认 10、最大 20，另设 60KB 截断预算。数据修正共 9 项，其中新发现三项：539 条城市字段是乱码的 `area_code` 字典串；373 条海外城市岗位把 `overseas_flag` 标成了 false；1,492 个重复 id 全部是逐字段相同的重复采集，不是一岗多城。另有一处和决定 2 冲突：学历按“门槛”匹配时，`jobs_stats` 的学历组值填回 search 后，计数对不上，见 3.2 和待决第 3 条。

---

## 1. 设计原则

学生的问题无法穷举，所以 v4 不为某类问题单独开工具，而是提供三种可以组合的操作：筛选（`jobs_search`）、统计（`jobs_stats`，条件与 search 完全相同，组值能原样填回 search）、详情（`jobs_detail`）。没见过的问题靠组合这三者回答，上线后再看调用日志决定加什么（决定 1、2）。

列表一次返回全部业务字段，省掉学生“再展开看看”的追问（决定 3）。68 个原始字段逐个归为业务、内部、改名合并三类，只输出业务信息，这样在不瘦身的前提下每条仍从 2,588 B 降到 2,291 B。

招聘类型默认三种都返回（决定 4）。公告没写的条件是事实缺口，不能当作“不符合”丢掉，也不能当作“符合”推断，所以默认把未注明的岗位一起返回、单独标注、排在后面，顶层同时给出两类各自的条数；学生要求“只看写明的”时用 `explicit_only=true`（决定 5）。

参数只用 string、integer、boolean 和字符串 enum，这是豆包能正确传参的前提。调用日志记录参数值，由另一个会话实现（决定 6）。`jobs_deadlines` 按总控建议并入 search，另一方案放在附录 A（决定 7）。

## 2. 工具总览

| 工具 | 一句话 | 主要入参 | 返回要点 | 上游 → 下游 |
|---|---|---|---|---|
| `jobs_search` | 按条件找岗位，每条全部业务字段 + 匹配依据 | 9 个筛选条件、`deadline_within_days`、`explicit_only`、`include_expired`、`sort`、`page_size`、`offset` | `applied_filters`、`total/explicit_total/unspecified_total`、分页、`jobs[]` | 条件来自用户原话、schema 枚举或 `jobs_stats.groups[i].value` → `jobs[i].id` 给 `jobs_detail` |
| `jobs_stats` | 同样的条件计数，可按一个维度分组 | 与 search 相同的 12 个条件 + `group_by`、`top` | 三个总数、`groups[]`、`fill_param` | → 组值填回 `jobs_search` 中 `fill_param` 指定的参数 |
| `jobs_detail` | 按 id 取 1–10 个岗位 | `ids`（逗号分隔） | `found`、`not_found[]`、`jobs[]` | `ids` 只能来自 `jobs_search.jobs[i].id` |
| ~~`jobs_deadlines`~~ | 隐藏别名，保留一个版本 | `days`、`limit`、`offset` | 同 `jobs_search` + `notices` | 中间件改写为 `jobs_search(deadline_within_days, sort=deadline_asc)` |

## 3. 工具定义

### 3.0 通用约定

**Schema。** 每个属性都有顶层 `type`，取值只用 `string`、`integer`、`boolean`，以及带 `enum` 的 `string`；不出现 `anyOf`、`oneOf`、`allOf`，也不用数组。可选参数一律有默认值（`""`、`0`、`false`），客户端传 `null` 按未传处理（沿用 A 包的 `NoneToEmpty`）。多个值用英文逗号拼进一个字符串（`city`、`company`、`ids`）。上线前用 `../qiuzhao-doubao-fix-20260911/scripts/verify_schema_snippet.py` 核验，要求输出 `RESULT OK`。

**枚举与同义词。** 枚举参数先在服务端做同义词归一，再校验。例如 `产品经理`→`产品`，`校招`/`秋招`→`校园招聘`，`实习`→`实习招聘`，`社招`→`社会招聘`，`研究生`→`硕士`，`专科`→`大专`，`国企`/`央企`→`国企/央企`，`2027`/`27届`/`2027年`→`2027届`，`未披露`→`未注明`；完整表见 `scripts/v4lib.py` 的 `SYNONYMS`。归一后仍不在枚举内的值报错，报错文案为中文，写明可选值和改用哪个参数。实现建议：schema 用 `Field(json_schema_extra={"enum": [...]})` 声明枚举，类型写 `str`，在工具函数里校验后抛 `ToolError`。这样 schema 里有 enum，报错又不带 pydantic 的英文前缀。

**单份返回。** 每个工具注册时写 `@mcp.tool(output_schema=None)`，返回 `ToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, separators=(",", ":")))])`，只在 content 里放一份。实测数据见第 4 节。

**匹配依据 `match`。** 只要用了届别、城市、专业、学历中的任一条件，每条岗位就带 `match`：

| 维度 | 可能的依据 | 算明确匹配？ |
|---|---|---|
| `graduation_year` | `岗位写明`（岗位原文 cohort_raw 写了该届）/ `活动标题写明`（只在招聘活动标题里写了）/ `未注明` | 前两者算 |
| `city` | `岗位写明` / `全国`（岗位写“全国”，对任何大陆城市都算，查海外、港澳台城市时不算）/ `未注明` | 前两者算 |
| `major` | `岗位写明` / `专业不限`（原文写专业不限，对任何专业都算）/ `未注明` | 前两者算 |
| `education` | `岗位写明`（岗位最低学历不高于用户学历）/ `学历不限` / `未注明` | 前两者算 |

`match.level` 取 `明确匹配`（用到的维度全部明确）或 `含未注明`（至少一个维度是未注明）。排序时明确匹配始终在前，同一档内再按 `sort` 排。`explicit_only=true` 时去掉“含未注明”的岗位。

**分页与预算。** 返回 `offset`、`page_size`、`returned`、`has_next`、`next_offset`、`truncated`。服务端逐条累加 jobs 的字节数，超过 60,000 B 就在完整岗位的边界停下，置 `truncated=true`，`next_offset` 指向第一条没返回的岗位。至少返回 1 条，不截断单条内部的字段。

**服务端 instructions（最终文案）：**
> 仅提供公开官方公告中的岗位事实。回答要附原公告链接（source_url）和数据截至时间（data_as_of）。“未注明”指原公告没写，不代表符合或不符合，不要替用户推断资格；把明确匹配和未注明分开告诉用户。计数是岗位条数，不是招聘人数。返回里的 applied_filters 若与你传入的条件不一致，说明客户端没有传递参数，应告知用户，不要重复同样的调用。

### 3.1 jobs_search

**描述原文：**
> 【岗位搜索】按条件找秋招、实习、社招岗位。每条返回全部业务字段（岗位描述、城市、届别、学历、专业、截止日、投递链接、原公告链接）和匹配依据 match。
> 【何时用】用户要看具体岗位时用，例如“北京有哪些产品岗”“字节在招算法吗”“我是27届计算机硕士能投什么”“这周截止的校招”“国企的财务岗”。只问数量、分布、排名（“哪个城市最多”“有几家公司”）时，先用 jobs_stats。
> 【参数来源】keyword、company、city、major 取自用户原话。job_category、graduation_year、education、recruitment_type、industry、sort 只能填 schema 列出的值，“27届”“校招”“研究生”这类说法服务端会自动归一。也可以把 jobs_stats.groups[i].value 原样填到 jobs_stats.fill_param 指定的参数。offset 只能取上一次返回的 next_offset。
> 【参数用法】各条件需同时满足。city、company 可用英文逗号写多个，满足任一即可。届别、城市、专业、学历四个条件默认返回“明确匹配 + 未注明”：明确匹配排在前面，每条的 match 写明依据（岗位写明、活动标题写明、全国、专业不限、学历不限、未注明）；用户说“只看写明的”时传 explicit_only=true。education 填用户本人的学历，返回最低学历要求不高于它的岗位。recruitment_type 不传时校招、实习、社招都返回。deadline_within_days=N 只返回今天起 N 天内有明确截止日的岗位（招满即止和没写截止日的不返回），一般配 sort=deadline_asc。默认不返回已截止岗位。
> 【返回】applied_filters（服务端实际使用的条件；与你传的不一致说明客户端丢了参数，要告诉用户，不要重复同样的调用）、total、explicit_total、unspecified_total、分页信息（returned、has_next、next_offset、truncated）、data_as_of、notices（参数改名或被调整时的说明），以及 jobs[]。
> 【下一步】has_next=true 且用户要更多时，用 next_offset 翻页。要对比或复查某几个岗位时，把 jobs[i].id 传给 jobs_detail。要看分布时，用相同条件调 jobs_stats。
> 【限制】page_size 默认 10、最大 20。一页超过约 60KB 时，在完整岗位处截断并置 truncated=true，用 next_offset 接着取。城市只认城市名，不认省份。数据只包含公告里写了的信息：回答时把明确匹配和未注明分开说，未注明不代表符合条件，并附 source_url 和 data_as_of。

**参数表**（各参数的默认值都表示“不筛选”）：

| 参数 | 类型 | 默认 | 取值 / 范围 | 含义 | 值从哪来 | 匹配规则 | 未注明怎么处理 | 示例 |
|---|---|---|---|---|---|---|---|---|
| `keyword` | string | `""` | ≤100 字 | 岗位名、技能、单位关键词 | 用户原话 | 不区分大小写包含于 job_title、job_category_raw、description_raw、company、recruiting_unit_raw、parent_unit_raw、hiring_department_raw、contracting_entity | — | `算法`、`转正` |
| `company` | string | `""` | ≤100 字，逗号分隔多个时取并集 | 公司或单位 | 用户原话；`jobs_stats(group_by=company)` 的组值；`jobs[i].company` | 包含于 company、recruiting_unit_raw、parent_unit_raw、contracting_entity | — | `字节跳动`、`腾讯,阿里巴巴` |
| `city` | string | `""` | ≤100 字，逗号分隔多个时取并集；也可填 `全国`、`未注明` | 工作城市 | 用户原话；`group_by=city` 的组值；`jobs[i].cities` 的元素 | 与修正后 `cities` 的元素完全相同；输入会去掉“市”后缀并做别名归一（`中国香港`→`香港`） | 城市为空的岗位默认返回，标 `未注明`；“全国”岗位对大陆城市算明确匹配，标 `全国` | `北京`、`北京,上海` |
| `job_category` | enum | `""` | 技术/研发、产品、运营、设计、市场/营销、销售、职能/支持、金融、咨询、医疗/医药、制造/生产、科研、教育/培训、法律/合规、其他 | 岗位大类 | schema；`group_by=job_category`；`jobs[i].job_category` | 与修正后 `job_category` 完全相同 | 每条都有值，不涉及 | `产品` |
| `graduation_year` | enum | `""` | 2027届、2026届、2025届、未注明 | 届别 | 用户原话（会自动归一）；schema；`group_by=graduation_year` | `graduation_years` 列表里含该值 | 默认返回并标注；传 `未注明` 时只看没写届别的 | `2027届` |
| `major` | string | `""` | ≤50 字；可填 11 个专业大类名、专业关键词，也可填 `不限`、`未注明` | 专业 | 用户原话；`group_by=major_category` 的组值 | 填大类名时：`major_category` 相同，或专业原文/标签包含去掉“类”后的词；填其他词时：包含于 major_requirements_raw、major_tags | 默认返回并标注；“专业不限”算明确匹配 | `计算机类`、`统计` |
| `education` | enum | `""` | 不限、中专及以下、大专、本科、硕士、博士、未注明 | 用户本人的学历 | 用户原话（`研究生`→硕士）；schema；`group_by=education` | 岗位最低学历不高于该档时算匹配（门槛语义）；`不限` 只看写明学历不限的岗位 | 默认返回并标注；“学历不限”算明确匹配 | `硕士` |
| `recruitment_type` | enum | `""`（三种都返回） | 校园招聘、实习招聘、社会招聘 | 招聘类型 | 用户原话（校招、实习、社招会归一）；schema | 完全相同 | — | `实习招聘` |
| `industry` | enum | `""` | 互联网/科技、国企/央企、制造/工业、能源/电力、金融、医药/医疗、教育、物流/运输、传媒/广告、消费/零售、农业、房地产、其他 | 行业 | schema；`group_by=industry` | 完全相同 | — | `国企/央企` |
| `deadline_within_days` | integer | `0` | 0–366 | 今天起 N 天内（含今天）截止 | 模型把用户原话换算成天数（“国庆前”→到 9/30 的天数） | `deadline` 落在 [今天, 今天+N] | 没有明确日期的岗位（含招满即止）不返回 | `7` |
| `explicit_only` | boolean | `false` | — | 只看明确匹配 | 用户说“只看写明的” | 去掉 `match.level=含未注明` 的岗位 | 与条件值 `未注明` 同时传时报错 | `true` |
| `include_expired` | boolean | `false` | — | 是否包含已截止岗位 | 用户明确要看已截止的 | status 为 `已截止` 的默认排除 | — | `false` |
| `sort` | enum | `published_desc` | published_desc、deadline_asc | 排序 | schema；用户说“按截止时间”“最急的”时用 deadline_asc | 明确匹配始终在前；deadline_asc 时没有日期的排在同档最后 | — | `deadline_asc` |
| `page_size` | integer | `10` | 1–20（>20 按 20 返回并提示） | 每页条数 | 默认值；用户要“多给点”时填 20 | — | — | `10` |
| `offset` | integer | `0` | ≥0 | 翻页起点 | 上一页的 `next_offset` | — | — | `10` |

**返回顶层字段：** `applied_filters`（放在第一个键；只含实际生效、已归一的条件）、`total`、`explicit_total`、`unspecified_total`、`sort`、`offset`、`page_size`、`returned`、`has_next`、`next_offset`（没有下一页时为 null）、`truncated`、`data_as_of`，以及可选的 `notices[]`、`suggestion`（结果为 0 时给出），最后是 `jobs[]`。jobs 放在最后，客户端截断输出时仍能看到总数和分页信息。v3 顶层的 `source_urls`、`数据截至时间` 删除（每条都有 source_url，data_as_of 保留）。

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
| `graduation_years` | string[] | 如 `["2027届","2026届"]`；空列表表示未注明 |
| `graduation_year_basis` | object | 如 `{"2027届":"岗位写明","2026届":"岗位写明"}` |
| `cohort_raw` ?、`campaign_title` ? | string | 届别原文、招聘活动标题 |
| `education` | string | 最低学历档（7 档之一） |
| `education_raw` ? | string | 学历原文 |
| `major_category` | string | 11 个大类，或 `不限`、`未注明` |
| `major_requirements_raw` ?、`major_tags` ? | string、string[] | 专业原文、标签 |
| `deadline` | string/null | YYYY-MM-DD |
| `deadline_kind` | string | 明确日期、招满即止或长期、未注明 |
| `status` | string | 招聘中、未核验、已截止（运行时按日期计算） |
| `status_note` ? | string | 状态说明原文 |
| `published_at` | string/null | YYYY-MM-DD |
| `job_code` ? | string | 岗位编号 |
| `description_raw` | string | 岗位描述原文 |
| `application_url`、`source_url` | string | 投递入口、原公告链接 |
| `announcement_url` ?、`campaign_url` ?、`job_listing_url` ? | string | 公告、专场、列表页链接 |
| `source_name`、`reviewed_at` | string | 来源、核验时间 |

**报错与边界：**

| 情况 | 处理 |
|---|---|
| 枚举外的值（同义词归一后仍不在枚举内） | `isError`，文案如：参数 job_category 的值「游戏策划」不在可选范围。可选：技术/研发、产品……。找具体岗位名（如游戏策划、UI设计）请用 keyword。 |
| `page_size` 大于 20 | 不报错，按 20 返回，`notices` 里说明 |
| `page_size` 小于 1、`offset` 小于 0、`deadline_within_days` 不在 0–366 | `isError`，中文说明取值范围 |
| `explicit_only=true` 且某条件值为 `未注明` | `isError`：两者矛盾 |
| 未知参数（不属于任何旧参数名） | FastMCP 在进入工具函数前拒绝，返回 pydantic 原文 `Unexpected keyword argument`（见 `examples/compat_and_errors.json`） |
| 旧参数 `cohort`、`region`、`major_category`、`limit` | 中间件改名后执行，见 3.4 |
| 结果为 0 | 不算错误：`total=0`，附 `suggestion` |
| 数据文件缺失或损坏 | 沿用现状 `isError`：“岗位数据尚未就绪” |

### 3.2 jobs_stats

**描述原文：**
> 【岗位统计】用与 jobs_search 相同的筛选条件计数，可按一个维度分组。
> 【何时用】问数量、分布、排名、对比时用，例如“北京和上海哪个产品岗多”“哪些国企招计算机最多”“27届和26届未就业各有多少岗位”“字节的岗位主要在哪些城市”“一共有多少家公司”。也可以在 jobs_search 之前先看规模。
> 【参数来源】筛选参数的来源同 jobs_search。group_by 只能填 schema 列出的值。
> 【参数用法】group_by 不传时只返回总数。一条岗位写了多个城市或多个届别时，按 city、graduation_year 分组会计入多个组，各组之和可能大于 total（此时返回 multi_valued=true）。top 控制返回的组数（默认 20、最大 100），其余组的计数合计在 other_count。
> 【返回】applied_filters、total、explicit_total、unspecified_total、group_by、fill_param、multi_valued、groups_total、returned_groups、other_count、groups[]（value、count、explicit_count、unspecified_count）、data_as_of。
> 【下一步】用户要看某一组的岗位时，把 groups[i].value 原样填到 jobs_search 中 fill_param 指定的参数，其余条件保持不变。
> 【限制】计数单位是岗位条数，不是招聘人数，数据里没有招聘人数。education 分组是岗位写明的最低学历；填回 jobs_search.education 时按“门槛不高于该档”匹配，所以返回的明确匹配数会不少于该组计数。

**参数：** `keyword`、`company`、`city`、`job_category`、`graduation_year`、`major`、`education`、`recruitment_type`、`industry`、`deadline_within_days`、`explicit_only`、`include_expired`，定义与 3.1 完全相同（不含 sort、page_size、offset）。另加两个：

| 参数 | 类型 | 默认 | 取值 | 含义 |
|---|---|---|---|---|
| `group_by` | enum | `""`（只返回总数） | company、city、job_category、graduation_year、education、major_category、industry、recruitment_type | 分组维度 |
| `top` | integer | 20 | 1–100（>100 按 100 返回） | 返回前几组，按 count 从大到小，同数按值排序 |

`fill_param` 的对应关系：group_by 为 `major_category` 时填回 `major`，其余维度填回同名参数。`city`、`graduation_year` 的组里会出现 `未注明`，`city` 的组里还会出现 `全国`，这两个值都能原样填回 search。

**返回：** 三个总数和 `data_as_of` 始终返回；传了 group_by 时再加 `group_by`、`fill_param`、`multi_valued`、`groups_total`、`returned_groups`、`other_count`、`groups[]`。报错规则同 3.1，另有一条：group_by 取枚举外的值时报错。

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

报错：ids 为空或超过 10 个时 `isError`。旧参数 `id` 会被映射成 `ids`。

### 3.4 旧参数名与旧工具名

映射在 `MeterTools` 中间件里完成，时机早于 FastMCP 的参数校验（未知参数会被 FastMCP 直接拒绝，见前一轮收据第 9 节）。release-B 已经用 `context.copy(message=context.message.model_copy(update=...))` 这样改写过参数；FastMCP 2.14.7 的 `_call_tool` 在中间件之后才读 `context.message.name`，所以工具名也能用同样的方法改写。

| 旧调用 | v4 处理 | notices 文案 |
|---|---|---|
| `jobs_search(cohort=…)` | → `graduation_year`：抽出年份转成“YYYY届”，抽不到年份就忽略 | 参数 cohort 已改名为 graduation_year，本次已自动转换。 |
| `jobs_search(region=…)` | → `city` | 参数 region 已改名为 city…… |
| `jobs_search(major_category=…)` | → `major` | …… |
| `jobs_search(limit=…)` | → `page_size`，超过 20 按 20 返回 | 参数 limit 已改名为 page_size……；page_size=50 超过上限 20…… |
| 新旧参数同时传 | 用新参数，忽略旧参数 | 同时收到旧参数 cohort 和新参数 graduation_year，已忽略 cohort。 |
| `jobs_detail(id=…)` | → `ids` | 参数 id 已改名为 ids…… |
| `jobs_deadlines(days, limit, offset)` | 隐藏别名：不出现在 tools/list 里，改写为 `jobs_search(deadline_within_days=days, sort=deadline_asc, page_size=limit(≤20), offset)` | jobs_deadlines 已并入 jobs_search……排序已从截止日由远到近改为由近到远。 |

别名保留一个版本（v4.0），v4.1 删除。删除前在调用日志里按 `tool=jobs_deadlines` 以及含旧参数名的 `args` 统计剩余调用量。调用日志（决定 6：按天写 JSONL，字段 ts/tool/args/ua/user_ref/outcome/result_total/duration_ms）需要和日志会话对齐三点：`args` 记映射前的原始入参；`tool` 记客户端调用的原名，便于统计别名使用量；`result_total` 对 search 和 stats 取 total，对 detail 取 found。

## 4. 返回大小预算

**每条大小**（紧凑 JSON，UTF-8 字节，27,506 条口径）：

| | 均值 | 中位 | P95 | P99 | 最大 |
|---|---:|---:|---:|---:|---:|
| v3（线上 `public()` 输出） | 2,588 | 2,471 | 4,111 | 5,436 | 17,382 |
| v4（去掉内部字段和重复字段，加上修正字段；去重后 25,463 条） | 2,291 | 2,160 | 3,815 | 5,083 | 16,900 |

v4 每条的字节里，`description_raw` 占 50.3%。校准：用同样的方法复算 A 包的默认调用，结果 JSON 为 25,903 B，与 A 包实测的 structuredContent 25,903 B 完全一致。

**每页大小**（v4 默认排序，把全库按 page_size 逐页切分，含 410 B 的顶层字段）：

| page_size | 页数 | 均值 B | P95 B | 最大 B | 超过 60KB 的页 | 粗估 token 均值 / P95 / 最大 |
|---:|---:|---:|---:|---:|---:|---|
| 5 | 5,092 | 11,873 | 17,408 | 47,941 | 0 | 3,473 / 5,186 / 15,262 |
| **10** | 2,546 | 23,334 | 33,245 | 61,140 | 1 | 6,946 / 10,012 / 19,360 |
| **20** | 1,273 | 46,258 | 64,441 | 104,140 | 110 | 13,891 / 19,366 / 33,168 |
| 30 | 848 | 69,191 | 94,402 | 146,891 | 607 | 20,840 / 28,461 / 46,727 |
| 50 | 509 | 115,041 | 153,887 | 244,068 | 507 | 34,732 / 47,153 / 77,711 |

粗估 token 的算法是：一个汉字或全角字符算 1 token，其余字符每 4 个算 1 token。这只是个量级估计，不能代替实测。

**结论：** `page_size` 默认 10、上限 20；jobs 数组的预算 60,000 B（按上表比例约 1.8 万粗估 token）。page_size=20 时，1,273 页里有 110 页会在岗位边界截断；全库最大的 20 条拼在一起是 173,365 B，截断后仍控制在预算内。page_size=30 时 72% 的页会被截断，所以上限定为 20。据 Claude Code 文档，MCP 工具输出超过 10,000 token 会提示，默认上限 25,000 token（可用 `MAX_MCP_OUTPUT_TOKENS` 调整），这一点要在验收时实测确认；豆包、千问的上限未知。

**FastMCP 双份返回的实测**（`scripts/probe_single_copy.py`，FastMCP 2.14.7 进程内 Client，同一份 v4 默认结果 21,561 B）：

| 写法 | tools/list 里的 outputSchema | 线上传输的结果字节 | content | structuredContent |
|---|---|---:|---|---|
| 现状：返回 dict | `{"type":"object","additionalProperties":true}` | 44,439 | 完整 JSON 文本 | 完整 |
| **方案 A**：`output_schema=None` + 一个 TextContent | 无 | **22,857** | 完整 JSON 文本 | 无 |
| 方案 B：`output_schema=None` + 摘要文本 + structured_content | 无 | 21,721 | 一句摘要 | 完整 |

建议用方案 A。content 文本是所有 MCP 客户端都支持的格式，structuredContent 则是 2025-06 版协议才有的，只有部分客户端会读。如果某个客户端验证下来只读 structuredContent，再对该客户端（按 UA 判断）改用方案 B。上表是进程内的 CallToolResult 字节数，HTTP 另有 JSON-RPC 外壳和 SSE 帧，实现后要用前一轮的 `dump_tools_list.py` 再测一次 HTTP 响应体（A 包 10 条是 53,600 B）。

**上线前在 Claude Code、豆包、千问上各验证一遍：**
1. tools/list 显示三个工具，没有 outputSchema；schema 核验输出 `RESULT OK`。
2. 只保留 content 后模型能读到完整结果：让它原样复述 `applied_filters`、`total`、最后一条的 `id`、`has_next` 和 `next_offset`。
3. 某个客户端读不到结果时，判断它是否只读 structuredContent：给它临时开方案 B 对照。
4. 20 条满页（接近 60KB）有没有被客户端截断或报超长：Claude Code 看是否出现超过 10k token 的提示；豆包、千问看是否报错或只显示一部分。
5. 中文不转义（UTF-8 原样输出）时显示正常。
6. 报错文案能被模型读到，并据此改参数重试，不会原样重试陷入死循环。
7. 豆包实际传了哪些参数：查调用日志的 `args`。
8. 用旧会话调用 cohort、region、limit、jobs_deadlines，返回里出现 `notices`。

## 5. 返回示例（`examples/`）

示例由 `scripts/make_examples.py` 从 data/jobs.json 的真实记录生成。依赖数据修正的字段（match、graduation_years 及依据、education、major_category、修复后的 cities、region、job_category、deadline_kind、中文 status）按第 6 节规则模拟，每个文件的 `_说明` 字段写明了这一点。为便于阅读，page_size 取 2–3。

| 文件 | 请求 | 看点 |
|---|---|---|
| `jobs_search.1_city_year_major.json` | 成都 + 2027届 + 计算机类 | total 2,095，明确 218；第 1 页就出现 `city=全国`、`major=专业不限` |
| `jobs_search.2_explicit_unspecified_boundary.json` | 同上，offset=217 | 同一页里前一条是明确匹配，后面接着含未注明的岗位 |
| `jobs_search.3_deadline_7d.json` | 校园招聘，7 天内截止，deadline_asc | 166 条，从今天截止的开始 |
| `jobs_stats.1_product_2027_by_city.json` | 产品 + 2027届，按城市分组 | 北京 530（明确 494）、上海 375；有 `未注明`、`全国` 组；multi_valued=true |
| `jobs_stats.2_soe_cs_by_company.json` | 国企/央企 + 计算机类，按公司分组 | 中国移动 1,356、中国邮政 1,070、航天科工 488 |
| `jobs_stats.3_campus_by_education.json` | 校园招聘，按学历分组 | 未注明 7,160 为最大的一组；有学历门槛的说明 |
| `jobs_detail.1_two_ids.json`、`.2_not_found.json` | 两个 id；一个真 id 加一个编造的 id | `not_found` 与 `suggestion` |
| `compat_and_errors.json` | 旧工具、旧参数、同义词、5 类报错 | `notices` 文案、page_size 50→20、中文报错 |

## 6. 数据修正清单

口径：“现状”和“单项修正后”按 27,506 行计算；“去重后”按 25,463 条计算，已套用全部修正。“管线”指采集和归一化脚本，它们产出 jobs.json；“服务端”指 `qiuzhao/tools.py`。注意：产出 `*_normalized` 字段的归一化脚本不在 live-baseline 的 52 个文件里（changelog 2026-09-11 12:25 记为“字段归一化升级”），管线项开工前要先找到这个脚本。

| # | 问题 | 现状 | 修正规则 | 修正后 | 归属 |
|---|---|---|---|---|---|
| 6.1 | id 重复 | 1,492 个 id 重复，涉及 3,535 行，多出 2,043 行。**1,492 组全部逐字段相同**（941 组 2 行、551 组 3 行），来源全是国聘系：国聘行动官方招聘平台 1,303 组、国聘网校园招聘 114 组、国聘 62 组、国聘行动 2 组。结论是重复采集，不是一岗多城 | 按 id 去重，采集合并时按 id upsert；服务端 load 时再去重一次兜底 | 25,463 条，id 唯一 | 管线 + 服务端兜底 |
| 6.2 | job_category 错分 | 原文含“产品”、归一化却不是产品的有 371 条，全部被归成技术/研发，其中字节 307 条；明显是产品岗的 362 条（字节 305 条）。运营、设计、销售、市场、人力也有同样问题 | 归一化结果是技术/研发、而原文类目命中词表时，以原文为准（词表见 `v4lib.RAW_CATEGORY_RULES`；“产品/工程研发”因含“研发”保留原判） | 改判 801 条：产品 370、运营 244、设计 80、销售 72、市场/营销 21、职能/支持 14。产品从 939 升到 1,309（去重后 1,279），与 v3 子串匹配的 1,310 基本持平 | 管线 |
| 6.3 | 届别多值与依据 | 归一化后 2027届 13,895、未披露 13,193、2026届 414、2025届 4。4,266 条只在活动标题写 2027，被归为未披露；319 条同招 26、27 届，被压成 2026届。岗位原文同时写了 2026 和 2027 的共 2,542 条 | `graduation_years` 改成多值。从岗位原文（cohort_raw）抽出的年份标“岗位写明”，从活动标题（campaign_cohort_raw、batch_name）补充的标“活动标题写明”。毕业时间窗按覆盖了哪一年的 6–8 月毕业季来算届（“2026-11-01 至 2027-10-31”只算 2027届）。334 种原文到结果的对应见 `evidence/cohort_mapping.tsv` | 含 2027届 18,586 条（岗位写明 14,214，活动标题写明 4,372）；那 4,266 条全部变为活动标题写明，那 319 条全部含 2027届；多届 2,070 条（2027+2026 共 2,046 条）；未注明 8,913 条。去重后：2027届 18,270，未注明 7,186 | 管线产出字段，服务端负责匹配和依据 |
| 6.4 | 学历归一化 | 原文非空写法 30 种，其中 6 种是乱码（如 `116yhC4D`，共 93 条，全部来自“国聘行动”）；另有 9,258 条为空 | 映射到 7 档：不限、中专及以下、大专、本科、硕士、博士、未注明。“本科/硕士”这类写法取较低一档，乱码归为未注明，原文输出为空 | 本科 9,958、未注明 9,369、硕士 5,414、博士 1,266、大专 1,137、中专及以下 181、不限 181。去重后未注明 9,354，其中 8,019 条的届别原文或描述里出现了学历字样，可作为补抽候选（待决 9） | 管线负责映射，服务端负责门槛匹配 |
| 6.5 | 专业 | major_normalized 为未披露的 12,865 条，占 46.8%；原文“详见职位描述”231 条、“未披露”30 条被归成“其他”（其中无标签的 261 条）；写明“专业不限”的 231 条；201 条专业原文里混进了岗位职责 | 占位词归为未注明；“专业不限”归为 `major_category=不限`，任何专业都算匹配 | 未注明 13,126 条（去重后 12,149，占 47.7%）；不限 231 条（去重后 196） | 管线 |
| 6.6 | 截止日口径统一 | deadline_type 有 8 种写法：explicit 18,371、undisclosed 6,685、招满即止 1,290、空 661、timestamp 445、unknown 44、固定截止 5、rolling 5。jobs_deadlines 只认 explicit，30 天内漏掉 203 条（timestamp 198、固定截止 5）。**标 undisclosed 却带日期的 1,087 条**全部来自“国聘行动官方招聘平台”，格式都是 `YYYY-MM-DD HH:MM:SS`，没有 deadline_scope，其中 30 天内的 190 条。线上的 guopin.py（第 141–148 行）只要 end_time 有值就标 explicit，并截取前 10 位，所以这批数据推测来自另一条导入路径。另有 16 条用 2099-01-01 占位；30 条 deadline 字段是“未披露”文本；默认按截止日由远到近排 | `deadline` 统一为日期。`deadline_kind` 规则：能解析出日期且早于 2099 年的算明确日期；2099 占位，以及招满即止、rolling 且无日期的，算招满即止或长期；其余算未注明。1,087 条要由管线确认 end_time 确实是投递截止时间 | 明确日期 19,905、未注明 6,303、招满即止或长期 1,298（去重后 17,863、6,303、1,297）。30 天内从 4,031 变为 4,424（去重后 3,715）；7 天内从 456 变为 504（去重后 374）；排序改为由近到远 | 管线写 deadline_kind；服务端做窗口筛选和排序 |
| 6.7 | 城市与“全国” | city_normalized 中“全国”942 条、“未披露”1,376 条（原文“未披露”1,229 条、“未知”147 条）；cities_normalized 含“全国”的 952 条（原文写“全国”或“中国”）。**539 条（全部来自“国聘”）三个城市字段都是 `{'area_code': …}` 字典串**，按城市精确匹配会漏掉它们。另有 49 条英文或别名、6 条非城市词，还残留省级写法 58 条、区县写法 332 条 | 修复后的 `cities`：解析字典串里的 area_cn；做别名归一（中国、中国大陆→全国，中国香港→香港，SanJose→圣何塞等）；去掉未披露、未知、多地和非城市词。匹配规则：“全国”岗位对任一大陆城市算明确匹配，标“全国”，查海外或港澳台城市时不算 | 全国 967 条、未注明 1,383 条（去重后 926、1,366）。以北京为例：v3 子串匹配 6,325 条，v4 为明确 6,325 条 + 全国 957 条 + 未注明 1,383 条。省级和区县写法留给管线补映射 | 管线负责修复，服务端负责“全国”规则 |
| 6.8 | region、overseas 与 status 写法 | region 有 145 种写法：大陆 5 种（mainland 25,638、全国 349、内地 340、中国大陆 31、中国 22）、海外 2 种（overseas 47、海外 20）、空值 625、误写成区县的 434 条（137 种）。**overseas_flag 与城市不一致**：373 条城市在海外却标 false（字节 309 条），26 条标 true 却没有海外城市。status 有 4 种写法：open 26,765、active 445（国聘 timestamp 行）、qualified 204（美的 146、迈瑞 58）、unverified 92（全部是上游标了不可投递） | region 由城市推导，取值中国大陆、港澳台、海外，跨地区用“、”连接；海外城市名单共 36 个，从本数据人工整理（`v4lib.OVERSEAS_CITIES`）。status：open、active、qualified→招聘中，unverified→未核验，截止日已过→已截止，removed→已下线（不返回） | region：中国大陆 27,043、海外 376、港澳台 36、跨地区 51。status：招聘中 27,414、未核验 92 | 管线负责 region，服务端负责 status 运行时计算 |
| 6.9 | 顺带发现（不阻塞 v4） | 同单位、同标题、同描述但 id 不同的有 1,801 组（5,461 条）：城市各不相同的 1,286 组（一岗按城市拆成多条，合理）、城市全相同的 351 组、部分相同的 164 组；跨来源的 912 组。published_at 晚于今天的 234 条（国聘系），缺失的 2,315 条 | 城市全相同的 351 组是否合并见待决 7；published_at 晚于今天的，管线确认取的是哪个字段 | — | 管线 |

招聘类型三类：校园 20,598、社会 4,406、实习 2,502（去重后 19,903、3,063、2,497，重复主要出在社招）。

## 7. 兼容与迁移

**现有 Claude Code 用户会遇到的变化：**
1. **工具列表**：新增 `jobs_stats`，`jobs_deadlines` 从列表中消失。已打开的会话缓存着旧工具表，仍会调用旧名和旧参数，都会被映射并返回 `notices`；重连（`/mcp`）或新开会话后才能看到新工具。
2. **参数**：`cohort`、`region`、`major_category`、`limit` 改名（自动映射一个版本）；新增 `education`、`explicit_only`、`include_expired`、`deadline_within_days`、`sort`、`page_size`；`city`、`company` 支持逗号分隔多个值；枚举参数接受“校招”“产品经理”“研究生”这类说法。
3. **结果变多、口径变化**：带届别、城市、专业、学历条件时，会多出“未注明”的岗位（排在后面并标注）。例如北京 + 2027届，去重后 total 8,218，其中明确 4,887。产品岗从 939 条变为 1,309 条（同为 27,506 行口径；去重后 1,279 条）。截止日窗口按统一口径计算，排序由近到远。page_size 上限从 100 降到 20。默认不返回已截止岗位。
4. **字段**：改名 7 处（recruitment_unit→company、job_category→job_category_raw、job_category_normalized→job_category、graduation_year_normalized→graduation_years + graduation_year_basis、campaign_cohort_raw→campaign_title、major_normalized→major_category、deadline_type→deadline_kind）；删除 city_normalized、cities_normalized（合并进 cities）、overseas_flag（合并进 region）、cohort_filter_scope（由 match 和 graduation_year_basis 取代）、20 个内部字段，以及顶层的 source_urls、数据截至时间。
5. **返回只有一份**：不再有 structuredContent。Claude Code 读取 content 预计不受影响，以第 4 节验证第 2 条为准。
6. **静态页要同步**（这些文件归其他会话维护，9/11 20:20 仍有人在改，这里只列出）：`guide.html` 的“接入成功”一节写的是 `jobs_deadlines` 和 `limit=1`（limit 仍能用，但会提示改名）；`app.js` EXAMPLES 里 `deadline` 这条提示词调用了 `jobs_deadlines`，建议改为“调用 jobs_search，deadline_within_days=7，sort=deadline_asc”；`exclude` 那条的“排除某些公司”目前只能由模型在结果里自己剔除（见待决 12）。

**changelog 文案**（沿用 `changelog.json` 的格式）：
```json
{"time": "<上线时间>", "version": "v4.0", "title": "岗位查询升级：统计、匹配依据、截止日统一",
 "changes": ["新增 jobs_stats：按公司、城市、岗位大类、届别、学历、专业、行业、招聘类型分组计数",
             "按届别、城市、专业、学历筛选时，没写这些条件的岗位也会列出并标“未注明”，写明的排在前面；可用 explicit_only 只看写明的",
             "所有写了具体日期的岗位都参与“N 天内截止”筛选，jobs_deadlines 并入 jobs_search，按截止日由近到远",
             "修正 801 条岗位大类错分、539 条城市乱码、373 条海外岗位地区标错，去除 2,043 条重复收录",
             "每页默认 10 条、最多 20 条；旧参数名 cohort/region/major_category/limit 本版仍可用，下个版本停用"]}
```

## 8. 验收问题集

执行方法：实现并部署后，在 Claude Code、豆包、千问里各问一遍，用调用日志核对实际调用链，再对照“必须包含”逐项判断。参考值是 2026-09-11 数据的模拟结果，存于 `evidence/acceptance_expected.json`；上线当天用当天的 jobs.json 重跑 `scripts/acceptance.py` 更新数字。调用链和“必须包含”的要素不随数据变化。

| # | 学生原话 | 类型 | 期望调用链 | 正确回答必须包含 | 参考值 |
|---|---|---|---|---|---|
| Q01 | 我是27届计算机专业硕士，想留杭州，有哪些岗位能投？ | 筛选 | search(city=杭州, graduation_year=2027届, major=计算机类, education=硕士) | 先列明确匹配的岗位；说明另有若干条至少一项未注明；每条附 source_url；给出 data_as_of | 明确 188 / 含未注明 2,722 |
| Q02 | 字节现在有哪些产品经理岗位？主要在哪些城市？ | 筛选 + 统计 | search(company=字节跳动, job_category=产品) + stats(同条件, group_by=city) | 总数、城市分布；说明只列了第一页或主动翻页 | 637；北京 422、上海 306、深圳 71 |
| Q03 | 接下来一周要截止的校招有哪些？按截止时间排 | 截止 | search(recruitment_type=校园招聘, deadline_within_days=7, sort=deadline_asc) | 按日期从近到远；给出 application_url | 166 |
| Q04 | 北京有没有不限专业的国企岗位？ | 筛选 | search(city=北京, industry=国企/央企, major=不限) | 只算原文写了“专业不限”的岗位；未注明的不算“不限” | 10 |
| Q05 | 第 2 个岗位的具体要求是什么？投递链接给我 | 下钻 | detail(ids=<Q01 返回的第 2 个 id>) | id 取自上一轮结果，不自己编；给出 application_url 和 source_url | found 1 |
| Q06 | 上海有能转正的实习吗？ | 筛选 | search(recruitment_type=实习招聘, city=上海, keyword=转正) | 说明“转正”是在描述里做关键词匹配 | 204（明确 201） |
| Q07 | 我 2026 年毕业还没找到工作，还能投哪些央企？ | 资格 | search(graduation_year=2026届, industry=国企/央企) | 说明这些岗位的原文多为“2026届未就业可报”，依据来自原文；未注明的单独说 | 815（明确 563） |
| Q08 | 国庆前截止的产品岗有哪些？ | 截止 | search(job_category=产品, deadline_within_days=19, sort=deadline_asc) | 模型把“国庆前”换算成到 9/30 共 19 天；按日期排列 | 19 |
| Q09 | 腾讯和阿里在深圳招算法吗？ | 筛选 | search(company=腾讯,阿里巴巴, city=深圳, keyword=算法) | 两家都要覆盖到（写一次调用或两次调用都可以） | 272 |
| Q10 | 北京和上海，哪边的 27 届产品岗更多？ | **统计对比** | stats(job_category=产品, graduation_year=2027届, group_by=city) | 给出两个数和明确匹配数；说明一条岗位可同时算进多个城市 | 北京 530（494）、上海 375（343） |
| Q11 | 今年校招哪些行业招得最多？给我前五 | **分布** | stats(recruitment_type=校园招聘, group_by=industry, top=5) | 说明单位是岗位条数，不是人数 | 互联网/科技 8,897、国企/央企 5,798、制造/工业 1,999、能源/电力 1,265、其他 744 |
| Q12 | 哪几家国企招计算机专业最多？ | **排行 + 下钻** | stats(industry=国企/央企, major=计算机类, group_by=company, top=5) → 可再 search(company=<第 1 名>, major=计算机类) | 前几名及其数量；组值原样填回 search | 中国移动 1,356、中国邮政 1,070、航天科工 488 |
| Q13 | 本科和硕士能投的岗位差多少？ | **对比 + 口径** | stats(education=本科)、stats(education=硕士)，或 stats(group_by=education) | 解释门槛语义（硕士也能投要求本科的岗位）；未注明的两边都算 | 明确：本科 10,001、硕士 15,036；未注明 9,354 |
| Q14 | 为什么很多岗位没写专业要求？这些我能投吗？ | **数据解释** | stats(major=计算机类) + stats(group_by=major_category) | 未注明的比例；“未注明=公告没写，要看原公告”；不替用户下结论 | 未注明 12,149（47.7%） |
| Q15 | 帮我排一下未来两周上海技术岗的投递计划 | **规划** | search(city=上海, job_category=技术/研发, deadline_within_days=14, sort=deadline_asc, page_size=20) + 翻页 | 按日期分组；has_next=true 时主动翻页或向用户说明还有 | 39（明确 26） |
| Q16 | 对比一下这两个岗位，哪个更适合学统计的我？ | **对比** | detail(ids=a,b) | 对比专业要求原文；不编造原文里没有的要求 | found 2 |
| Q17 | 你们的数据是什么时候的？一共有多少家公司？ | **元数据** | stats(group_by=company, top=1) | 给出 data_as_of 和 groups_total | 2026-09-11T12:00+08:00；3,630 家；25,463 条 |
| Q18 | 字节的岗位主要在哪些城市？技术和非技术各多少？ | **画像** | stats(company=字节跳动, group_by=city) + stats(company=字节跳动, group_by=job_category) | 两个维度的分布 | 4,171 条；北京 2,287、上海 1,692；技术/研发 2,453 |
| Q19 | 有新加坡或者海外的岗位吗？ | **边界** | search(city=新加坡) 和/或 stats(group_by=city) | 不能把“全国”岗位当成新加坡的；城市未注明的单独说 | 新加坡明确 87 |
| Q20 | 我只想看明确写了招 27 届的，没写届别的不要 | 筛选 | search(graduation_year=2027届, explicit_only=true) | 结果里没有未注明；说明依据包括“活动标题写明” | 18,270 |

其中 9 个问题（Q10–Q14、Q16–Q19）超出浏览、筛选、下钻、截止这四类。

## 9. 待 Max 决定

| # | 问题 | 选项 | 建议 |
|---|---|---|---|
| 1 | jobs_deadlines 的去留 | 并入 search 并保留隐藏别名一版 / 保留独立工具（附录 A） | 并入。tools/list 维持 3 个工具，旧会话靠别名不报错 |
| 2 | “活动标题写明”算不算明确匹配 | 算 / 不算 | 算，并标注依据。不算的话，2027届的明确匹配（去重后）从 18,270 降到 13,898，这 4,372 条会落进“含未注明” |
| 3 | education 的语义 | 门槛（岗位要求不高于用户学历）/ 精确（岗位要求等于该档） | 门槛，因为学生问的是“我能投什么”。代价是违背决定 2 的对称性：stats 的学历组值填回 search 后，明确匹配数大于组计数。描述里已写明这一点 |
| 4 | “全国”在 explicit_only 时保留吗 | 保留 / 去掉 | 保留并标“全国” |
| 5 | 1,087 条 undisclosed 却带日期的岗位 | 当明确日期 / 当未注明 | 管线确认国聘 end_time 是投递截止时间后，当明确日期（本说明书的数字已按此计算）。若不确认，30 天窗口会少 190 条 |
| 6 | 字段改名（7 处）是否随 v4 一次改完 | 一次改完 / 分批改 | 一次改完。模型读的是 JSON，分批改反而要维护两套名字 |
| 7 | 351 组“同单位、同标题、同描述、同城市、不同 id”的岗位要不要合并 | 合并 / 不合并 | v4 不动，管线下一轮处理 |
| 8 | job_category 修正的范围 | 只修产品 370 条 / 同一机制下的 801 条全修 | 801 条全修，都是原文类目被岗位标题关键词覆盖掉 |
| 9 | 学历未注明 9,354 条里，8,019 条正文出现学历字样，要不要补抽 | 现在补 / 下一版 | 下一版补，依据新增“正文写明” |
| 10 | page_size 上限 20 + 60KB 预算 | 采用 / 调整 | 采用，三端验收后再看是否调整 |
| 11 | 单份返回用方案 A 还是 B | A / B | A，三端验证通过后上线 |
| 12 | city、company 支持逗号多值（取并集）；要不要做“排除某公司” | 多值做，排除不做 / 两个都做 | 多值做；排除不做，看调用日志再定 |
| 13 | 默认排除已截止岗位 | 是 / 否 | 是（今天 0 条已截止，但数据会随时间过期） |
| 14 | 按省份筛选（“广东的岗位”） | 现在支持 / 暂不支持 | 暂不支持，看调用日志再定 |
| 15 | 枚举维护：出现新值（2028届、新行业）时怎么办 | 部署前自动检查 / 人工维护 | 部署前自动检查，枚举与数据取值集合不一致就阻止上线 |
| 16 | “国企/央企”和行业混在同一个字段（去重后 5,882 条） | v4 就拆 / 以后再拆 | v4 不动，以后单独加“企业性质”字段 |
| 17 | 多个条件叠加后，未注明的尾巴很长（Q01：明确 188 / 含未注明 2,722） | 维持决定 5 / 只要有 2 维以上未注明就不返回 | 维持决定 5，由描述要求模型先报明确匹配，未注明的只报数量 |

**与已定决定的出入、做不到的地方：**
- **决定 2 与学历门槛语义冲突**（待决 3）：两者只能保留一个，本说明书按门槛语义写。
- **“三个工具”与兼容别名**：用隐藏别名解决，tools/list 仍是三个；如果改用附录 A，就会变成四个。
- **与简报数字的差异**（都能复现）：
  - 简报“修正后 2027 届约 18,480 条、真正没写的约 8,927 条”，是 v3 子串口径。按 6.3 的规则是 18,586 和 8,913：多出的 106 条是岗位原文只写了别的年份、活动标题写了 2027 的（92 条），以及岗位原文没有年份、活动标题写了 2027 的（14 条）；没有减少的。去重后为 18,270 和 7,186。
  - 简报“学历 30 种写法”：非空写法确实是 30 种，其中 6 种是乱码。
  - 简报“其中 305 条来自字节”：305 是 362 条明显产品岗里的字节条数；按 371 条算，字节是 307 条。
- **id 重复**不是一岗多城，是完全相同的行重复采集（6.1）。
- **做不到或未验证**：
  - 归一化脚本不在手头的代码树里，管线项的具体改动位置无法给出。
  - Claude Code 的 token 上限，以及豆包、千问的输出上限和 structuredContent 支持情况，只能在验收时实测。
  - HTTP 层的响应字节本次没测（只测了进程内结果）。

## 附录 A：保留独立 jobs_deadlines 的方案与取舍

**方案：** 保留 `jobs_deadlines`，参数改为 `days`（1–366，默认 7）、`page_size`（1–20，默认 10）、`offset`，按 6.6 的统一口径筛选，排序改为由近到远，返回结构与 jobs_search 相同。如果还要支持“北京这周截止的产品岗”这类问题，就得把 search 的 9 个筛选条件复制一份过来；stats 要统计截止情况，也仍然要在 stats 上加 `deadline_within_days`。

| | 并入 search（正文方案） | 保留独立工具 |
|---|---|---|
| 组合能力 | 截止条件可以和任意条件、分组组合 | 不复制参数就无法组合；复制了又会出现两套一样的参数 |
| 模型选工具 | 描述里需要教模型“截止类问题也用 search”；豆包、千问可能漏选 | 看工具名就知道用途 |
| 维护 | 一套筛选、分页和预算逻辑 | 两套分页逻辑，改一处容易漏另一处 |
| 旧用户 | 别名保留一版，之后要改提示词 | 不用改 |
| 工具数 | 3 | 4 |

如果上线后日志显示“截止类”问题的 search 调用常常漏传 `deadline_within_days`，再考虑恢复独立工具。

## 附录 B：68 个字段的归类

完整表格（含每个字段的出现行数、非空行数、理由）见 `evidence/field_inventory.md`，由 `scripts/v4_numbers.py` 生成；脚本会断言 68 个字段全部归了类。汇总如下：

- **业务字段，原样输出（23 个）**：id、job_title、education_raw、cohort_raw、application_url、source_url、source_name、description_raw、recruitment_type、industry、country、contracting_entity、major_requirements_raw、major_tags、recruiting_unit_raw、hiring_department_raw、parent_unit_raw、announcement_url、campaign_url、job_listing_url、status_note、industry_tags、reviewed_at。
- **改名、合并或修正（25 个，信息都保留在输出里）**：
  - 改名：recruitment_unit→company；job_category→job_category_raw；job_category_normalized→job_category；graduation_year_normalized→graduation_years + graduation_year_basis；campaign_cohort_raw→campaign_title；major_normalized→major_category；deadline_type→deadline_kind。
  - 合并：company（与 recruitment_unit 相同）、title（与 job_title 相同）、job_id（与 id 相同）、detail_url（与 source_url 相同）、category（与 job_category 相同）、batch_name（并入 campaign_title）、position_code（并入 job_code）、job_code、cities、city_normalized、cities_normalized（三个城市字段合为一个修正后的 cities）、overseas_flag（并入 region）、recruitment_type_raw、nature_raw（并入 recruitment_type）。
  - 修正：deadline、status、published_at、region。
- **仅内部使用（20 个，不输出）**：source_record_id；evidence_path、announcement_evidence_path、directory_evidence_path（服务器本地路径）；deadline_scope、published_at_scope、cohort_scope、requirements_scope、education_scope、job_title_scope、recruitment_scope_note（采集流程标记）；record_kind；incomplete；source_status_raw；source_is_apply_raw（已折算进 status）；source_group_key；company_id；first_seen_at；verified_at；fortune_rank（全为 null）。

## 附录 C：复现

```bash
cd ~/Projects/mcp-suite/research/qiuzhao-v4-interface-20260911
python3 scripts/v4_numbers.py        # → evidence/numbers.json、field_inventory.md、cohort_mapping.tsv
python3 scripts/make_examples.py     # → examples/*.json
python3 scripts/acceptance.py        # → evidence/acceptance_expected.json
PYTHONDONTWRITEBYTECODE=1 ~/Projects/mcp-suite/.venv/bin/python -W ignore scripts/probe_single_copy.py   # → evidence/probe_single_copy.json
```
- `scripts/v4lib.py` 是本说明书全部规则的参考实现：修正规则、匹配、三个工具、旧参数映射。它不是服务端代码，实现时可以照着写测试。
- 所有脚本只读 `../qiuzhao-doubao-fix-20260911/data/jobs.json`。probe 只是 import 已安装的 fastmcp，不写 `__pycache__`，不 import 任何代码树。
- 文中数字与 `evidence/numbers.json` 键名的对应：第 4 节对应 `size_*`；6.1 对应 `dup_*`、`same_post_*`；6.2 对应 `jc_*`；6.3 对应 `gy_*`；6.4 对应 `edu_*`；6.5 对应 `major_*`；6.6 对应 `dl_*`；6.7 对应 `city_*`；6.8 对应 `region_*`、`status_*`；6.9 对应 `published_at_*`；招聘类型对应 `rtype_*`；公司数对应 `companies_distinct_deduped`。
