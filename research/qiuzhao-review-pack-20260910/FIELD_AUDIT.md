# 同行15列字段审计报告 — QIUZHAO-FIELD-AUDIT-20260910

> 任务编号：QIUZHAO-FIELD-AUDIT-20260910
> 关联任务：QIUZHAO-EXPANSION-20260910
> 审计时间：2026-09-10 北京时间
> 审计方式：只读源码分析 + 全量 jobs.json (9191条) 统计
> 快照路径：`qiuzhao/data/jobs.json`
> 数据截至时间：2026-09-10T06:46:41+08:00
> 统计分母：9191条全量记录（非样本推算）

---

## 状态分级定义

| 状态 | 含义 |
|---|---|
| `verified` | 有代码 + 有真实执行证据（全量数据统计/测试通过/线上e2e收据） |
| `implemented_unverified` | 有代码实现但未运行验证 |
| `planned` | 只有设计文档/扩源方案建议，无代码 |
| `unknown` | 无法读到材料 |

---

## 审计总览

| # | 同行列名 | 实际字段 | 落盘 | 有数据 | 工具返回 | 可筛选 | 状态 |
|---|---|---|---|---|---|---|---|
| 1 | 公司名称 | recruitment_unit / recruiting_unit_raw | ✅ | ✅ 100% | ✅ | ⚠️ keyword间接 | verified |
| 2 | 公司类型 | （无） | ❌ | ❌ | ❌ | ❌ | planned |
| 3 | 所属行业 | （无） | ❌ | ❌ | ❌ | ❌ | planned |
| 4 | 招聘类型 | nature_raw / recruitment_type_raw | ⚠️ 部分源 | ⚠️ 65.9% | ✅ | ❌ | verified |
| 5 | 招聘对象 | cohort_raw / campaign_cohort_raw / education_raw | ✅ | ⚠️ 55.3%/72.3% | ✅ | ✅ cohort入参 | verified |
| 6 | 工作地点 | cities | ✅ | ✅ 99.99% | ✅ | ✅ city入参 | verified |
| 7 | 岗位 | job_title / job_category / hiring_department_raw | ✅ | ✅ 100%/72.4% | ✅ | ⚠️ keyword间接 | verified |
| 8 | 投递进度 | status（公共事实，非用户私有） | ✅ | ✅ 100% | ✅ | ❌（deadlines间接） | verified |
| 9 | 更新时间 | reviewed_at / published_at | ✅ | ✅ 100% | ✅ | ❌ | verified |
| 10 | 投递截止 | deadline / deadline_type / deadline_scope | ✅ | ✅ 99.89% | ✅ | ✅ deadlines工具 | verified |
| 11 | 相关链接 | source_url / application_url / campaign_url / announcement_url | ✅ | ✅ 100%/95.3%/29.2% | ✅ | ❌ | verified |
| 12 | 招聘公告 | announcement_url / description_raw | ⚠️ 部分源 | ⚠️ 29.2%/100% | ✅ | ❌ | verified |
| 13 | 笔试情况 | （无） | ❌ | ❌ | ❌ | ❌ | planned |
| 14 | 公司规模 | （无） | ❌ | ❌ | ❌ | ❌ | planned |
| 15 | 备注 | status_note / description_raw | ⚠️ | ⚠️ 0.11%/100% | ✅ | ❌ | verified |

---

## 逐列详细审计

### 1. 公司名称

**1. 是否落盘**
- 落盘字段：`recruitment_unit`（集团全称，string）、`recruiting_unit_raw`（招聘单位/分公司标签，string）、`contracting_entity`（签约主体，string，始终空）、`parent_unit_raw`（上级单位，string，部分源有）
- 模型/源：`base_job()` 初始化 `recruitment_unit` 为集团名；各采集器填充 `recruiting_unit_raw`
- 文件：`qiuzhao/data/jobs.json`
- 类型：string

**2. 是否有数据（全量9191条）**
- `recruitment_unit`：键存在率 100%，有效非空率 100%
- `recruiting_unit_raw`：键存在率 100%，有效非空率 100%
- `contracting_entity`：键存在率 100%，有效非空率 **0%**（设计上始终为空字符串，不推断签约主体）
- `parent_unit_raw`：键存在率 5.02%（461条，仅chn和ccb源），有效非空率 5.02%
- 11个集团：邮政2648、国家能源422、电信10、中行14、建行39、移动1610、能建634、中广核8、机械总院72、航天科工1165、联通2569

**3. 是否返回**
- `jobs_search`：返回（经 `public()` 过滤后保留，`*_evidence_path` 被排除）
- `jobs_detail`：返回
- `jobs_deadlines`：返回（作为jobs数组元素的字段）
- 注意：`contracting_entity` 虽然返回但始终为空字符串

**4. 是否可筛选**
- 无直接的"公司名称"入参
- `keyword` 入参可间接匹配：`recruitment_unit`、`contracting_entity`、`recruiting_unit_raw`、`parent_unit_raw`、`hiring_department_raw`、`job_title`、`job_category`、`description_raw`
- 匹配方式：JSON序列化后 casefold 子串包含（关键词匹配，非精确）
- 多值：不支持，单值AND组合
- 未知值处理：空字符串不匹配任何非空关键词

**状态：verified** — 有代码、有全量数据、有测试、有线上e2e收据

---

### 2. 公司类型

**1. 是否落盘**
- 无对应字段。不存在 `company_type`、`enterprise_type`、`ownership` 等字段
- 国聘源有 `nature_raw`（值为"校招"），但这是**招聘性质**（校招/社招），不是公司类型（央企/国企/民企/外企）

**2. 是否有数据**
- 无数据。所有9191条记录均无公司类型字段

**3. 是否返回**
- 三个工具均不返回公司类型

**4. 是否可筛选**
- 不可筛选

**状态：planned** — 扩源方案可能建议新增，但当前无代码无数据。注意：不可将 `nature_raw`（校招性质）误当作公司类型

---

### 3. 所属行业

**1. 是否落盘**
- 无对应字段。不存在 `industry`、`sector`、`business_category` 等字段
- 可从 `recruitment_unit`（如"中国移动通信集团有限公司"）人工推断行业，但未结构化存储

**2. 是否有数据**
- 无数据

**3. 是否返回**
- 三个工具均不返回所属行业

**4. 是否可筛选**
- 不可筛选。`keyword` 可间接搜索公司名，但不是行业筛选

**状态：planned** — 当前无代码无数据

---

### 4. 招聘类型

**1. 是否落盘**
- 落盘字段：`nature_raw`（string，仅国聘源，值"校招"）、`recruitment_type_raw`（string，仅国聘源，值"校园招聘"或空）、`record_kind`（string，记录类型标记）
- 模型/源：`guopin.py` 从国聘API的 `nature_cn` 和 `recruitment_type_cn` 映射
- 文件：`qiuzhao/data/jobs.json`
- 类型：string
- 注意：所有记录均在**校招范围**内采集（guopin.py 明确排除非校招记录），但非所有源都有结构化的"招聘类型"字段

**2. 是否有数据（全量9191条）**
- `nature_raw`：键存在率 65.91%（6058条，仅国聘6企业），有效非空率 65.91%
- `recruitment_type_raw`：键存在率 65.91%，有效非空率 54.58%（部分国聘记录该字段为空）
- `record_kind`：键存在率 66.49%（6111条），有效非空率 66.49%
- 直采源（邮政/国家能源/电信/中行/建行）无 `nature_raw` 和 `recruitment_type_raw` 字段

**3. 是否返回**
- `jobs_search`：返回（如字段存在）
- `jobs_detail`：返回
- `jobs_deadlines`：返回

**4. 是否可筛选**
- 无直接的"招聘类型"入参
- `cohort` 入参匹配的是**届别**（2027/2026），不是招聘类型（校招/社招）
- 不可按校招/社招筛选（设计上所有数据均为校招范围）

**状态：verified** — 有代码（guopin.py映射）、有全量数据统计。但覆盖不完整（仅国聘源有结构化字段）

---

### 5. 招聘对象

**1. 是否落盘**
- 落盘字段：
  - `cohort_raw`（string，岗位级届别描述，如"2027届应届毕业生"）
  - `campaign_cohort_raw`（string，活动标题届别，如"2027年全球校园招聘"）
  - `cohort_scope`（string，届别来源范围标记）
  - `education_raw`（string，学历要求，如"硕士研究生"、"本科"）
- 模型/源：各采集器从公告/详情页提取；`base_job()` 初始化为空字符串
- 文件：`qiuzhao/data/jobs.json`
- 类型：string
- **语义区别**：招聘性质(campus/social) ≠ 招聘季(2026秋招) ≠ 毕业届别(2027届)。`cohort_raw` 存的是毕业届别，不是招聘季也不是招聘性质。

**2. 是否有数据（全量9191条）**
- `cohort_raw`：键存在率 100%，有效非空率 **55.34%**（5086条有值，4105条为空字符串）
- `campaign_cohort_raw`：键存在率 66.49%（6111条），有效非空率 66.49%
- `cohort_scope`：键存在率 29.24%（2687条，仅postal/boc/ccb）
- `education_raw`：键存在率 100%，有效非空率 **72.33%**（6648条有值，2543条为空）
- 来源差异：邮政cohort_raw 100%有值（统一文案）；国聘源cohort_raw大量为空（仅从描述中提取含"届"的行）；电信cohort_raw全空

**3. 是否返回**
- `jobs_search`：返回，且 `public()` 会动态计算 `cohort_filter_scope` 字段（role_record / campaign_title_only / undisclosed）
- `jobs_detail`：返回
- `jobs_deadlines`：返回
- 运行时添加字段：`cohort_filter_scope` 由 `Jobs.public()` 计算，标识届别匹配来源

**4. 是否可筛选**
- `cohort` 入参：支持，匹配 `cohort_raw` OR `campaign_cohort_raw`（岗位级优先）
- 匹配方式：JSON序列化后 casefold 子串包含
- 优先级逻辑：`cohort_raw` 有值时用 `cohort_raw`，否则回退 `campaign_cohort_raw`（见 `tools.py` 第42行）
- 测试验证：`test_role_cohort_overrides_campaign_title` 确认岗位级cohort优先于活动标题
- 无 `education` 入参，不可按学历筛选
- 未知值处理：`cohort_raw` 和 `campaign_cohort_raw` 均为空时，`cohort_filter_scope` = "undisclosed"，不匹配任何届别关键词

**状态：verified** — 有代码、有全量数据、有专项测试（test_role_cohort_overrides_campaign_title）、有线上e2e验证（cohort_2027_full_http_pagination返回8654条）

---

### 6. 工作地点

**1. 是否落盘**
- 落盘字段：`cities`（array[string]，城市/地区列表）
- 模型/源：各采集器填充；`base_job()` 初始化为空数组
- 文件：`qiuzhao/data/jobs.json`
- 类型：array of string
- 注意：值可能是"北京"、"北京-东城区"、"阿拉善左旗"等不同粒度

**2. 是否有数据（全量9191条）**
- `cities`：键存在率 100%，有效非空率 **99.99%**（9190条非空，1条空数组）
- 单城市记录占绝大多数，多城市记录较少（如中行部分岗位有多个城市）

**3. 是否返回**
- `jobs_search`：返回
- `jobs_detail`：返回
- `jobs_deadlines`：返回

**4. 是否可筛选**
- `city` 入参：支持
- 匹配方式：JSON序列化 `cities` 数组后 casefold 子串包含（关键词匹配，非精确城市匹配）
- 多值：不支持，单值
- 未知值处理：空数组不匹配任何非空city关键词
- 注意：由于是子串匹配，搜索"北京"会匹配"北京-东城区"，但也可能匹配含"北京"子串的其他值

**状态：verified** — 有代码、有全量数据、有测试

---

### 7. 岗位

**1. 是否落盘**
- 落盘字段：
  - `job_title`（string，岗位名称）
  - `job_category`（string，岗位类别，如"科研"、"财务专员/助理"）
  - `job_title_scope`（string，岗位名称来源标记，仅ccb有）
  - `hiring_department_raw`（string，招聘部门）
- 模型/源：各采集器填充；`base_job()` 初始化 `job_title` 为标题，`job_category` 为空
- 文件：`qiuzhao/data/jobs.json`
- 类型：string
- **语义区别**：不为复刻同行表格把全部岗位合并为一条公司记录。每条记录是一个原始岗位ID，9191条 = 9191个原始岗位，不是11条公司汇总。

**2. 是否有数据（全量9191条）**
- `job_title`：键存在率 100%，有效非空率 100%
- `job_category`：键存在率 100%，有效非空率 **72.38%**（6653条有值，2538条为空，主要是国聘源部分记录category为"不限"或空）
- `hiring_department_raw`：键存在率 95.15%（8745条），有效非空率 95.15%
- `job_title_scope`：键存在率 0.42%（39条，仅ccb）

**3. 是否返回**
- `jobs_search`：返回
- `jobs_detail`：返回
- `jobs_deadlines`：返回

**4. 是否可筛选**
- 无直接的"岗位"入参
- `keyword` 入参可间接匹配 `job_title` 和 `job_category`
- 匹配方式：子串包含
- 不可按岗位类别精确筛选

**状态：verified** — 有代码、有全量数据、有测试

---

### 8. 投递进度

**1. 是否落盘**
- 落盘字段：`status`（string，公共招聘事实状态）、`status_note`（string，状态说明，仅telecom有）
- 模型/源：各采集器设置；`base_job()` 初始化为 `unverified`
- 文件：`qiuzhao/data/jobs.json`
- 类型：string
- **关键语义区别**：`status` 是**公共招聘事实**（open/expired/unverified/removed），**不是用户私有投递进度**（已投递/笔试中/面试中/offer/已拒绝）。系统不存储任何用户投递记录。

**2. 是否有数据（全量9191条）**
- `status`：键存在率 100%，有效非空率 100%
- 分布：open=9089（98.89%），unverified=102（1.11%），expired=0，removed=0
- 注意：`public()` 会在返回时动态将已过截止日期的标记为 `expired`（见 tools.py 第28-29行），但落盘快照中当前无expired
- `status_note`：键存在率 0.11%（10条，仅telecom）

**3. 是否返回**
- `jobs_search`：返回，且 `public()` 可能动态修改status为expired
- `jobs_detail`：返回
- `jobs_deadlines`：返回（但deadlines工具本身排除unverified/expired/removed状态）

**4. 是否可筛选**
- 无直接的"投递进度"入参
- `jobs_deadlines` 工具隐式过滤：只返回 `status` 不在 {removed, expired, unverified} 中的记录
- 不可按status值筛选open/expired等

**状态：verified** — 有代码、有全量数据。但需明确：这是公共岗位状态，不是用户投递进度。用户私有投递状态字段不存在。

---

### 9. 更新时间

**1. 是否落盘**
- 落盘字段：
  - `reviewed_at`（string，ISO8601，本次采集复核时间）
  - `published_at`（string，来源发布日期，YYYY-MM-DD）
  - `published_at_scope`（string，发布日期来源标记）
- 模型/源：各采集器填充；`base_job()` 初始化 `reviewed_at` 为采集时间
- 文件：`qiuzhao/data/jobs.json`
- 类型：string
- **语义区别**：
  - 今日新增（first_seen_at）：**不存在此字段**
  - 今日复核（reviewed_at）：本次采集运行的复核时间
  - 来源发布日期（published_at）：原始公告/岗位的发布日期
  - 三者不混用

**2. 是否有数据（全量9191条）**
- `reviewed_at`：键存在率 100%，有效非空率 100%
- `published_at`：键存在率 100%，有效非空率 100%
- `published_at_scope`：键存在率 94.72%（8706条），有效非空率 94.72%
- `reviewed_at` 最大值（数据截至时间）：2026-09-10T06:46:41+08:00

**3. 是否返回**
- `jobs_search`：返回 `reviewed_at`、`published_at`，且envelope返回 `data_as_of` 和 `数据截至时间`（=reviewed_at最大值）
- `jobs_detail`：返回
- `jobs_deadlines`：返回

**4. 是否可筛选**
- 无时间范围筛选入参
- `jobs_search` 按 `published_at` 降序排序（再按id降序），但不可按时间范围过滤
- `jobs_deadlines` 按 `deadline` 筛选，不是按更新时间

**状态：verified** — 有代码、有全量数据。注意：无"今日新增"字段，不可将reviewed_at误当作first_seen_at

---

### 10. 投递截止

**1. 是否落盘**
- 落盘字段：
  - `deadline`（string|null，截止日期 YYYY-MM-DD）
  - `deadline_type`（string，explicit/undisclosed/until_filled）
  - `deadline_scope`（string，截止日期来源范围标记）
- 模型/源：各采集器填充；`base_job()` 初始化 `deadline=None`、`deadline_type='undisclosed'`
- 文件：`qiuzhao/data/jobs.json`
- 类型：string 或 null

**2. 是否有数据（全量9191条）**
- `deadline`：键存在率 100%，有效非空率 **99.89%**（9181条有日期，10条为null）
- `deadline_type`：键存在率 100%，有效非空率 100%
  - explicit=9181（99.89%）
  - undisclosed=10（0.11%，全部为telecom源）
  - until_filled=0
- `deadline_scope`：键存在率 95.3%（8759条），有效非空率 95.3%
- 10条undisclosed全部为telecom记录（电信未披露截止日期）

**3. 是否返回**
- `jobs_search`：返回
- `jobs_detail`：返回
- `jobs_deadlines`：返回（专门工具）
- `public()` 动态逻辑：若 `deadline` 存在且 `status != removed` 且 deadline < 今天，则status改为expired

**4. 是否可筛选**
- `jobs_deadlines` 工具：专门按截止日期筛选
  - 入参 `days`：未来N天（含今天），范围1-366
  - 过滤条件：`deadline_type == 'explicit'` AND `status` 不在 {removed, expired, unverified} AND today <= deadline <= today+days
  - 排序：按deadline降序
- `jobs_search` 不可按截止日期范围筛选
- 未知值处理：`deadline_type != 'explicit'` 的记录被deadlines工具排除；解析失败的日期被跳过

**状态：verified** — 有代码、有全量数据、有测试（test_jobs_preserve_facts_and_deadline_order）、有线上e2e（deadlines_total=5007）

---

### 11. 相关链接

**1. 是否落盘**
- 落盘字段：
  - `source_url`（string，原公告/岗位详情链接）
  - `application_url`（string，直接投递入口）
  - `campaign_url`（string，活动主页）
  - `announcement_url`（string，公告页）
  - `job_listing_url`（string，岗位列表页，仅ccb有）
- 模型/源：各采集器填充
- 文件：`qiuzhao/data/jobs.json`
- 类型：string
- **语义区别**：原链接(source_url) ≠ 直接投递入口(application_url)。不把一个URL复制成三个字段。各URL有独立来源和用途。

**2. 是否有数据（全量9191条）**
- `source_url`：键存在率 100%，有效非空率 100%
- `application_url`：键存在率 100%，有效非空率 100%
- `campaign_url`：键存在率 95.26%（8755条），有效非空率 95.26%
- `announcement_url`：键存在率 29.24%（2687条，仅postal/boc/ccb），有效非空率 29.24%
- `job_listing_url`：键存在率 0.42%（39条，仅ccb）
- 注意：`Jobs.load()` 要求 `source_url` 和 `application_url` 同时存在才视为有效记录（见 tools.py 第19行）

**3. 是否返回**
- `jobs_search`：返回所有URL字段，且envelope返回 `source_urls` 去重排序列表
- `jobs_detail`：返回
- `jobs_deadlines`：返回

**4. 是否可筛选**
- 无URL筛选入参
- `source_urls` 仅作为返回元数据，不可作为筛选条件

**状态：verified** — 有代码、有全量数据

---

### 12. 招聘公告

**1. 是否落盘**
- 落盘字段：`announcement_url`（string，公告链接）、`description_raw`（string，岗位描述/公告内容原文）
- 模型/源：postal/boc/ccb有 `announcement_url`；所有源有 `description_raw`
- 文件：`qiuzhao/data/jobs.json`
- 类型：string
- 注意：`announcement_evidence_path` 是证据文件路径，**不返回给客户端**（被 `public()` 过滤）

**2. 是否有数据（全量9191条）**
- `announcement_url`：键存在率 29.24%（2687条，仅postal/boc/ccb），有效非空率 29.24%
- `description_raw`：键存在率 100%，有效非空率 100%
- 国聘源和国家能源、电信无 `announcement_url`（它们的source_url就是详情页）

**3. 是否返回**
- `jobs_search`：返回 `announcement_url`（如有）和 `description_raw`
- `jobs_detail`：返回
- `jobs_deadlines`：返回
- `announcement_evidence_path` 不返回（以evidence_path结尾的键被 `public()` 排除）

**4. 是否可筛选**
- 无公告筛选入参
- `keyword` 可间接匹配 `description_raw` 内容

**状态：verified** — 有代码、有全量数据。但announcement_url覆盖不完整（仅3/11源有）

---

### 13. 笔试情况

**1. 是否落盘**
- 无对应字段。不存在 `written_exam`、`exam_date`、`exam_status`、`笔试` 等字段

**2. 是否有数据**
- 无数据

**3. 是否返回**
- 三个工具均不返回笔试情况

**4. 是否可筛选**
- 不可筛选

**状态：planned** — 当前无代码无数据。扩源方案可能建议新增，但未实现。

---

### 14. 公司规模

**1. 是否落盘**
- 无对应字段。不存在 `company_size`、`employee_count`、`revenue`、`公司规模` 等字段

**2. 是否有数据**
- 无数据

**3. 是否返回**
- 三个工具均不返回公司规模

**4. 是否可筛选**
- 不可筛选

**状态：planned** — 当前无代码无数据

---

### 15. 备注

**1. 是否落盘**
- 无独立"备注"字段
- 最接近的字段：`status_note`（string，状态说明，仅telecom有）、`description_raw`（string，岗位描述，可视为备注信息）
- 文件：`qiuzhao/data/jobs.json`

**2. 是否有数据（全量9191条）**
- `status_note`：键存在率 0.11%（10条，仅telecom），有效非空率 0.11%
- `description_raw`：键存在率 100%，有效非空率 100%（但这是岗位描述，不是结构化备注）

**3. 是否返回**
- `jobs_search`：返回 `status_note`（如有）和 `description_raw`
- `jobs_detail`：返回
- `jobs_deadlines`：返回

**4. 是否可筛选**
- 无备注筛选入参
- `keyword` 可间接匹配 `description_raw`

**状态：verified** — 有description_raw全量数据，但无独立备注字段。status_note覆盖极低。

---

## 五个语义区别审计确认

### 区别1：招聘性质 vs 招聘季 vs 毕业届别
- **招聘性质(campus/social)**：对应 `nature_raw`（仅国聘源，值"校招"）和 `recruitment_type_raw`（值"校园招聘"）
- **招聘季(2026秋招)**：**无独立字段**。可从 `campaign_cohort_raw`（如"2027校园招聘"）推断，但不是结构化的"招聘季"字段
- **毕业届别(2027届)**：对应 `cohort_raw`（岗位级）和 `campaign_cohort_raw`（活动级）
- **确认**：三者未混用。`cohort` 筛选入参匹配的是毕业届别，不是招聘性质也不是招聘季。✅

### 区别2：企业汇总 vs 原始岗位
- **确认**：9191条记录 = 9191个原始岗位ID，不是11条企业汇总。每条记录有独立的 `id`、`job_title`、`source_url`。`summary.json` 的 `counting_note` 明确说明"Unique official role/post identifiers; no multiplication by hiring headcount or city"。✅

### 区别3：今日新增 vs 今日复核 vs 来源发布日期
- **今日新增(first_seen_at)**：**不存在此字段**
- **今日复核(reviewed_at)**：存在，100%有值，=采集运行时间
- **来源发布日期(published_at)**：存在，100%有值，=原始公告发布日期
- **确认**：三者未混用。无first_seen_at字段，不可将reviewed_at误当作首次发现时间。✅

### 区别4：原链接 vs 直接投递入口
- **原链接(source_url)**：存在，100%有值，=公告/岗位详情页URL
- **直接投递入口(application_url)**：存在，100%有值，=投递/报名入口URL
- **确认**：两者为独立字段，值通常不同。例如邮政source_url是智联岗位详情页，application_url是投递入口。未将一个URL复制成三个字段。✅

### 区别5：公共招聘事实 vs 用户私有记录
- **公共招聘事实(status)**：存在，值为open/expired/unverified/removed
- **用户私有记录(投递状态)**：**不存在**。系统无用户投递管理功能，无application_status、applied_at、interview_status等字段
- **确认**：严格区分。`status` 是岗位本身的公开状态，不是任何用户的投递进度。✅

---

## 字段覆盖率汇总（全量9191条）

| 字段 | 键存在率 | 有效非空率 | 主要缺失来源 |
|---|---|---|---|
| id | 100% | 100% | - |
| recruitment_unit | 100% | 100% | - |
| recruiting_unit_raw | 100% | 100% | - |
| job_title | 100% | 100% | - |
| source_url | 100% | 100% | - |
| application_url | 100% | 100% | - |
| status | 100% | 100% | - |
| deadline_type | 100% | 100% | - |
| reviewed_at | 100% | 100% | - |
| published_at | 100% | 100% | - |
| description_raw | 100% | 100% | - |
| source_name | 100% | 100% | - |
| evidence_path | 100% | 100% | (不返回客户端) |
| cities | 100% | 99.99% | 1条空数组 |
| deadline | 100% | 99.89% | 10条null(telecom) |
| major_requirements_raw | 100% | 95.33% | 430条空字符串 |
| campaign_url | 95.26% | 95.26% | telecom/boc/chn部分 |
| deadline_scope | 95.30% | 95.30% | telecom/boc/chn部分 |
| hiring_department_raw | 95.15% | 95.15% | telecom/boc/chn部分 |
| announcement_evidence_path | 95.15% | 95.15% | (不返回客户端) |
| source_record_id | 95.15% | 95.15% | telecom/boc/chn部分 |
| published_at_scope | 94.72% | 94.72% | telecom/boc/chn部分 |
| job_category | 100% | 72.38% | 国聘部分"不限"/空 |
| education_raw | 100% | 72.33% | 国聘/电信部分空 |
| cohort_raw | 100% | 55.34% | 国聘/电信大量空 |
| campaign_cohort_raw | 66.49% | 66.49% | 直采源部分无 |
| record_kind | 66.49% | 66.49% | 直采源部分无 |
| nature_raw | 65.91% | 65.91% | 仅国聘源 |
| recruitment_type_raw | 65.91% | 54.58% | 仅国聘源，部分空 |
| source_group_key | 65.91% | 65.91% | 仅国聘源 |
| source_is_apply_raw | 65.91% | 65.91% | 仅国聘源 |
| source_status_raw | 65.91% | 65.91% | 仅国聘源 |
| directory_evidence_path | 65.91% | 65.91% | (不返回客户端) |
| announcement_url | 29.24% | 29.24% | 仅postal/boc/ccb |
| cohort_scope | 29.24% | 29.24% | 仅postal/boc/ccb |
| parent_unit_raw | 5.02% | 5.02% | 仅chn/ccb |
| requirements_scope | 0.53% | 0.53% | 仅ccb/telecom |
| education_scope | 0.42% | 0.42% | 仅ccb |
| job_title_scope | 0.42% | 0.42% | 仅ccb |
| job_listing_url | 0.42% | 0.42% | 仅ccb |
| status_note | 0.11% | 0.11% | 仅telecom |
| contracting_entity | 100% | 0% | 设计上始终空(不推断) |
| major_tags | 100% | 0% | 预留未用，始终空数组 |

---

## 按来源分组记录数

| 来源 | 记录数 | 占比 | 采集方式 |
|---|---|---|---|
| 中国邮政 | 2648 | 28.81% | 直采(智联API) |
| 联通 | 2569 | 27.95% | 国聘平台 |
| 移动 | 1610 | 17.52% | 国聘平台 |
| 航天科工 | 1165 | 12.68% | 国聘平台 |
| 国家能源 | 422 | 4.59% | 直采(官网HTML) |
| 能建 | 634 | 6.90% | 国聘平台 |
| 机械总院 | 72 | 0.78% | 国聘平台 |
| 建行 | 39 | 0.42% | 直采(官网API) |
| 中行 | 14 | 0.15% | 直采(公告HTML) |
| 电信 | 10 | 0.11% | 直采(官网HTML,不完整) |
| 中广核 | 8 | 0.09% | 国聘平台 |
| **合计** | **9191** | **100%** | |

---

## 缺口与建议（仅标注，不实施）

1. **公司类型、所属行业、公司规模、笔试情况**：4列完全无字段无数据，状态为planned
2. **招聘类型**：仅国聘源有结构化字段，直采5源缺失
3. **招聘对象(cohort_raw)**：44.66%记录为空，主要是国聘源和电信
4. **学历要求(education_raw)**：27.67%记录为空
5. **岗位类别(job_category)**：27.62%记录为空
6. **announcement_url**：70.76%记录缺失（国聘6源+国家能源+电信无）
7. **contracting_entity**：设计上始终为空，不推断签约主体（这是保守设计，不是bug）
8. **无first_seen_at字段**：无法统计"今日新增"
9. **无用户投递状态**：status是公共岗位状态，不是用户投递进度
10. **筛选能力有限**：仅支持city/major/cohort/keyword四个筛选维度，不支持公司、行业、岗位类别、学历、状态等精确筛选

---

*本报告基于只读源码分析和全量数据统计，未修改任何生产文件，未运行采集，未部署。所有缺口如实标注，未伪造字段或测试结果。*
