# 秋招 MCP v3 条件发布 — 条件3 数据质量核查报告

- **核查时间**: 2026-09-10 (Asia/Shanghai)
- **输入**: `job_mvp/staging_merged/jobs.json`（10,043 条，只读，未修改）
- **输出**: `conditional_release/qualified_jobs.json`（合格子集）、`conditional_release/needs_review.jsonl`（待核实清单）
- **结论**: **条件3 通过**。合格子集 **9,199 条**，待核实 **844 条**。

---

## 1. 各源字段覆盖率

覆盖率 = 该字段非空（非空字符串/非空列表/非 None）的记录占比。`recruitment_type` 为派生字段（校招/实习/社招/未知）。

| 来源 | 条数 | id | title | unit | rtype | cohort | cities | major | edu | deadline | source_url | apply_url | reviewed_at |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| postal（邮政） | 2648 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| guopin（国聘） | 6058 | 100% | 100% | 100% | 100% | 39% | 100% | 93% | 58% | 100% | 100% | 100% | 100% |
| chn（国家能源） | 422 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| tencent（腾讯） | 814 | 100% | 100% | 100% | 100% | 58% | 100% | 0% | 0% | 0% | 100% | 100% | 100% |
| ccb（建行） | 39 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| mindray（迈瑞） | 20 | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 0% | 100% | 100% | 100% |
| boc（中行） | 14 | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 0% | 100% | 100% | 100% | 100% |
| telecom（电信） | 10 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 0% | 100% | 100% | 100% |
| midea（美的） | 10 | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 0% | 0% | 100% | 100% | 100% |
| pg（宝洁） | 8 | 100% | 100% | 100% | 100% | 100% | 100% | 100%* | 25%→75% | 0% | 100% | 100% | 100% |

\* P&G 的 major_requirements_raw 修复前为"Required Graduation Period : 2025."（毕业时间误入），修复后仅 1 条（CNC003184 R&D Scientist）含真实专业列表，其余 7 条留空（JD 未限定专业，不伪造）。

**关键字段缺失说明：**
- **chn（422条）cohort_raw=0%**：国家能源校招公告级别信息未按岗位抽取，但岗位均来自 2027 校招专场，recruitment_type 派生为校招，major/edu/deadline 完整。
- **guopin cohort_raw=39%**：国聘 6058 条中，中国移动 1042 条、部分企业岗位未单独抽取届别，但 nature_raw="校招"，recruitment_type 明确。
- **boc（14条）major/edu=0%**：中国银行 14 条来自单篇公告页，公告未按岗位列专业/学历，cohort/deadline/description 完整。
- **midea（10条）major/edu/deadline=0%**：美的仅抓到列表页元数据 + 简短职责描述，未抓到专业/学历/截止；source_url 为列表页（非岗位深链）。
- **pg deadline=0%**：宝洁 JD 未披露截止日期，deadline_type=undisclosed，不伪造。

---

## 2. 修复记录

### 2.1 宝洁毕业时间误入专业字段（8 条）

**问题**：8 条 `pg-*` 记录的 `major_requirements_raw` 全部为 `Required Graduation Period : 2025.`，这是毕业时间（届别）信息，不是专业要求。

**修复**：
- 清空 8 条的 `major_requirements_raw`（原毕业时间内容）。
- 仅对 `pg-CNC003184`（R&D Scientist）从 JD 的 `Requirement:` 段提取真实专业列表：
  > "Bachelor's, Master's, or PhD. degree in Chemistry, Chemical Engineering, Biology, Life Sciences, Skin Science, Pediatrics, Behavioral Science, Psychology, Physics, Materials Science, Mathematics, Statistics, Data Science, Computational Chemistry, or other related disciplines."
- 其余 7 条（BRM/Finance/CBD/HR/CMK/IT/Product Supply）JD 未限定专业，`major_requirements_raw` 留空，不伪造。
- 从 JD `Requirement:` 段为 5 条 education_raw 为空的记录补 `本科及以上`（JD 原文 "Candidate must possess at least a bachelor's degree"）。
- `cohort_raw` 已正确保留 `Required Graduation Period: 2025.6.1 - 2027.8.31`，无需迁移。

### 2.2 腾讯/迈瑞字段缺失核查

**腾讯（814 条）**：原始 staging（`qiuzhao-expansion-20260910/staging/tencent_jobs.json`）中 `major_requirements_raw`、`education_raw`、`deadline` 均为空；`description_raw` 仅为列表元数据（"职位族ID: 2; 事业群: CDG...; 项目: 应届毕业生; 招聘标签: 应届毕业生"），**无真实 JD 正文**。无更多原始数据可补取，按"取不到留空，不伪造"处理，全部 814 条归入待核实。

**迈瑞（20 条）**：`description_raw` 为"职位编码J18899；研发族；广东省·深圳市"列表元数据，无 JD 正文；`major_requirements_raw` 无真实内容。20 条全部归入待核实。

**美的（10 条）**：`description_raw` 含真实职责描述（如"1、永磁同步电机PMSM、感应电机IM的控制算法研究及产品化应用…"），但 source_url 为列表页（`careers.midea.com/schoolOut/post`），非岗位深链。10 条归入合格子集，注明 source_url 为列表页。

### 2.3 港/海外岗位单列

- 国聘 11 条（10 条中国移动香港 CMHK + 1 条中国能源建设澳门）原数据未设 `overseas_flag`/`region`，已补标 `overseas_flag=True, region=overseas`。
- 腾讯 13 条含"中国香港"岗位，原数据已标 `overseas_flag=True`（随腾讯整体进入待核实）。
- 合格子集中港/海外 11 条不纳入内地校招默认计数。

---

## 3. 校招/实习/社招分离

| 来源 | 校招 | 实习 | 社招 | 未知 | 合计 |
|---|---:|---:|---:|---:|---:|
| postal | 2648 | 0 | 0 | 0 | 2648 |
| guopin | 6058 | 0 | 0 | 0 | 6058 |
| chn | 422 | 0 | 0 | 0 | 422 |
| ccb | 39 | 0 | 0 | 0 | 39 |
| boc | 14 | 0 | 0 | 0 | 14 |
| telecom | 10 | 0 | 0 | 0 | 10 |
| tencent | 382 | 432 | 0 | 0 | 814 |
| mindray | 20 | 0 | 0 | 0 | 20 |
| midea | 10 | 0 | 0 | 0 | 10 |
| pg | 8 | 0 | 0 | 0 | 8 |
| **合计** | **9611** | **432** | **0** | **0** | **10043** |

- 腾讯 382 校招 / 432 实习分离确认正确（来源 `recruitment_type_raw` 字段，校招来自"应届毕业生"项目，实习来自"实习生"标签）。
- 全部 10,043 条均为校招或实习，无社招混入。
- 默认校招查询（`recruitment_type=校招`）不会召回 432 条实习岗。

---

## 4. 合格子集

### 4.1 合格标准

- 有真实 `job_title`、`recruitment_unit`、`source_url`、`reviewed_at`
- `recruitment_type` 明确（校招/实习）
- 无重复 id
- 有真实 JD 正文（非仅列表元数据）
- 非 `status=unverified` 且数据缺失（国聘 92 条 unverified 因含完整 JD 正文保留）

### 4.2 合格条数：9,199

| 来源 | 合格条数 | 校招 | 其中港/海外 |
|---|---:|---:|---:|
| postal（邮政） | 2,648 | 2,648 | 0 |
| guopin（国聘） | 6,058 | 6,058 | 11 |
| chn（国家能源） | 422 | 422 | 0 |
| ccb（建行） | 39 | 39 | 0 |
| boc（中行） | 14 | 14 | 0 |
| midea（美的） | 10 | 10 | 0 |
| pg（宝洁，已修复） | 8 | 8 | 0 |
| **合计** | **9,199** | **9,199** | **11** |

- **内地校招默认查询可用**：9,188 条（9,199 − 11 港/海外）
- **实习岗合格**：0 条（腾讯 432 实习全部因无 JD 正文进入待核实）
- 无重复 id（9,199 条 id 全唯一）
- 无关键字段缺失

### 4.3 与生产当前 9,191 条对比

生产当前 9,191 条 = postal 2648 + guopin 6058 + chn 422 + ccb 39 + boc 14 + telecom 10。
合格子集 9,199 条 = 上述减去 telecom 10（待核实）+ midea 10 + pg 8。

净变化：**+8 条**（midea 10 + pg 8 − telecom 10）。

---

## 5. 待核实清单：844 条

输出文件：`conditional_release/needs_review.jsonl`

| 来源 | 条数 | 原因 |
|---|---:|---|
| tencent（腾讯） | 814 | 仅有列表元数据（title/cities/部门/项目标签），无 JD 正文；major/edu/deadline 均无原始数据可补。含校招 382 + 实习 432，其中 13 条含香港。 |
| mindray（迈瑞） | 20 | 仅有列表元数据（职位编码/职族/城市），无 JD 正文；major_requirements_raw 无真实内容。 |
| telecom（电信） | 10 | status=unverified；无 cohort_raw、无 deadline；岗位标题（技术经理/解决方案经理/政企客户经理）及任职要求含团队管理经验，疑似社招岗挂校园页，需人工确认。 |

**待核实不混入正式发布库。** 后续补齐 JD 正文（抓取腾讯 post_detail 详情页、迈瑞岗位详情页）后可再评估转正。

---

## 6. 硬性约束遵守确认

- [x] 未伪造任何字段内容（宝洁专业列表来自 JD 原文 Requirement 段；取不到的留空）
- [x] 未修改 `staging_merged/jobs.json`（原始文件 mtime 14:53 未变，仅读取）
- [x] 未读取 `private/` 目录
- [x] 校招/实习/社招严格分开（腾讯 382 校招 / 432 实习已分离；无社招）
- [x] 港/海外岗位单列（11 条合格 + 13 条腾讯待核实均标 overseas_flag，不计入内地可投计数）

---

## 7. 最终结论

**条件3：通过。**

- 合格子集：**9,199 条**（内地校招 9,188 条 + 港/海外 11 条）
- 待核实：844 条（腾讯 814 + 迈瑞 20 + 电信 10），不混入正式发布库
- 宝洁毕业时间误入专业字段问题已修复
- 腾讯/迈瑞无 JD 正文问题已识别并归入待核实，未伪造
- 校招/实习分离正确，港/海外单列

**可发布。**
