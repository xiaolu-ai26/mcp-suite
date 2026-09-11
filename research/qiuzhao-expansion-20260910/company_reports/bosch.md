# 博世(Bosch)中国区校招源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**公司**: 博世 (Robert Bosch GmbH)
**company_slug**: bosch
**采集时间**: 2026-09-10
**状态**: ⚠️ 部分完成 - 180个校招职位列表已获取，职位详情URL受SPA限制

---

## 1. 官方归属证据

| 字段 | 内容 |
|------|------|
| attribution_evidence_url | https://www.bosch.com.cn/careers/ |
| attribution_evidence_excerpt | 页面标题"Work #LikeABosch"，含"2027届博世中国校园招聘"、"博世战略未来领军人(JMP)"、"博世学徒制项目"入口，以及"社会招聘"和"校园招聘"分类 |
| 全球招聘页 | https://www.bosch.com/careers/ (含Pupils/Students/Graduates/Professionals) |

## 2. 招聘入口

| 字段 | 内容 |
|------|------|
| homepage_url | https://www.bosch.com.cn/ |
| official_entry_url | https://www.bosch.com.cn/careers/ |
| job_list_url | https://app.mokahr.com/campus-recruitment/bosch/168626 |
| detail_url_pattern | https://app.mokahr.com/campus-recruitment/bosch/168626#/job/{job_id} |

## 3. 读取方式

| 字段 | 内容 |
|------|------|
| access_mode | web.fetch (MokaHR SPA页面可渲染职位列表) |
| authentication_required_for_read | 否 (职位列表公开可读) |
| authentication_required_for_apply | 是 (申请需注册MokaHR账号) |
| source_kind | 官方校招平台 (MokaHR) |
| platform_family | MokaHR (中国本土ATS) |
| platform_version_hint | 校招项目ID 168626 (主项目) / 73873 (实习生项目) |

## 4. 分页信息

| 字段 | 内容 |
|------|------|
| pagination_type | 页码分页，30行/页 |
| expected_total | 180 |
| observed_unique_total | 180 (6页 × 30条) |
| completeness | 职位列表完整(180条标题/地点/日期)，但详情页ID未提取 |

## 5. 招聘范围

| 字段 | 内容 |
|------|------|
| scope_country_region | 中国内地 |
| scope_recruitment_type | 校园招聘 (全职)，含JMP战略未来领军人项目 |
| scope_campaign | 2027届博世中国校园招聘 (2026-09-03和2026-09-08两批发布) |
| 地域分布 | 上海市、江苏·苏州市、江苏·无锡市、江苏·常州市、湖南·长沙市 |
| 届别要求 | 2026-2027届海内外本科、硕士、博士毕业生 (外部报道佐证) |

## 6. 真实岗位样例

### 样例1: 端到端算法工程师（XC）
- **岗位标题原文**: 端到端算法工程师（XC）
- **招聘单位原文**: 博世(中国)投资有限公司
- **工作地点**: 江苏·苏州市 上海市
- **性质判断及依据**: 校园招聘 - 来自MokaHR博世校招项目(168626)职位列表，标注"全职"，发布于2026-09-03校招批次
- **届别要求**: 2026-2027届毕业生 (校招项目统一要求)
- **详情URL**: https://app.mokahr.com/campus-recruitment/bosch/168626#/job/{id} (ID需JS渲染获取)
- **采集时间**: 2026-09-10

### 样例2: JMP_AI算法专家（DC）
- **岗位标题原文**: JMP_AI算法专家（DC）
- **招聘单位原文**: 博世(中国)投资有限公司
- **工作地点**: 上海市
- **性质判断及依据**: 校园招聘(JMP战略未来领军人项目) - 标题含"JMP_"前缀，来自校招项目列表，发布于2026-09-08
- **届别要求**: 2026-2027届毕业生 (JMP项目面向优秀应届生)
- **详情URL**: https://app.mokahr.com/campus-recruitment/bosch/168626#/job/{id} (ID需JS渲染获取)
- **采集时间**: 2026-09-10

### 样例3: JMP_数字化商业创新工程师（BD）
- **岗位标题原文**: JMP_数字化商业创新工程师（BD）
- **招聘单位原文**: 博世(中国)投资有限公司
- **工作地点**: 上海市
- **性质判断及依据**: 校园招聘(JMP项目) - 标题含"JMP_"前缀，来自校招项目列表，发布于2026-09-08
- **届别要求**: 2026-2027届毕业生
- **详情URL**: https://app.mokahr.com/campus-recruitment/bosch/168626#/job/{id} (ID需JS渲染获取)
- **采集时间**: 2026-09-10

### blocker_reason (详情页)
MokaHR为SPA单页应用，职位详情页ID通过JS动态加载。curl无法获取，web.fetch可渲染列表页但详情页链接的具体ID未在输出中暴露。MokaHR API端点(/api/campus-recruitment/.../positions)返回"页面不存在"，需特定认证或请求头。职位列表信息(标题/地点/日期)真实可靠，详情URL模式已知但具体ID需浏览器交互获取。

## 7. 任务状态

| 字段 | 内容 |
|------|------|
| integration_stage | A阶段-探源完成(列表级) |
| run_health | partial |
| blocker_reason | 职位详情页ID受MokaHR SPA限制，无法通过curl/web.fetch直接提取；职位列表(180条标题/地点/日期)已完整获取 |
