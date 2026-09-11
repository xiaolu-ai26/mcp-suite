# 宝洁(P&G)中国区校招源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**公司**: 宝洁 (Procter & Gamble)
**company_slug**: pg
**采集时间**: 2026-09-10
**状态**: ✅ 完整 - 3条真实岗位样例

---

## 1. 官方归属证据

| 字段 | 内容 |
|------|------|
| attribution_evidence_url | https://www.pgcareers.com/ |
| attribution_evidence_excerpt | "We're the world's largest consumer goods company and home to iconic, trusted brands that make life a little bit easier in small but meaningful ways." 页面标题"Careers at P&G"，含Student Programs/Internships/Entry Level等分类 |
| 中国官网 | https://www.pg.com.cn/ 含"宝洁招聘"入口 |

## 2. 招聘入口

| 字段 | 内容 |
|------|------|
| homepage_url | https://www.pg.com.cn/ |
| official_entry_url | https://www.pgcareers.com/ |
| job_list_url | https://www.pgcareers.com/search-jobs?country=China |
| detail_url_pattern | https://www.pgcareers.com/global/en/job/{jobSeqNo}/{title} |

## 3. 读取方式

| 字段 | 内容 |
|------|------|
| access_mode | web.fetch (JS渲染页面可读取) + sitemap.xml提取职位URL |
| authentication_required_for_read | 否 (职位列表和详情公开可读) |
| authentication_required_for_apply | 是 (申请需注册账号) |
| source_kind | 官方招聘官网 |
| platform_family | Phenom (phenompeople.com) |
| platform_version_hint | 租户ID PGBPGNGLOBAL，Widget API https://www.pgcareers.com/widgets |

## 4. 分页信息

| 字段 | 内容 |
|------|------|
| pagination_type | 页码分页 (1-10+页，Next按钮)，每页10条 |
| expected_total | 中国区约100+职位 (含社招和校招) |
| observed_unique_total | sitemap2.xml含328个URL，其中8个为Chinese Mainland Campus Recruiting |
| completeness | 校招职位完整 (8个全部从sitemap提取)，社招职位未全量采集 |

## 5. 招聘范围

| 字段 | 内容 |
|------|------|
| scope_country_region | 中国内地 (Chinese Mainland)，另有Hong Kong SAR单独列出 |
| scope_recruitment_type | 校园招聘 (Campus Recruiting)，含全职管理岗 |
| scope_campaign | 2027届秋季校园招聘 (宝洁2027秋季校园招聘，招聘200人) |
| 地域分布 | 北京、上海、广州、天津、太仓、成都 |
| 届别要求 | 毕业时间窗口: 2025.6.1 - 2027.8.31 (原文保留) |

## 6. 真实岗位样例

### 样例1: Research & Development Scientist
- **岗位标题原文**: (Chinese Mainland) Campus Recruiting - Research & Development Scientist
- **招聘单位原文**: Procter & Gamble (宝洁)
- **工作地点**: Beijing, Chinese Mainland
- **性质判断及依据**: 校园招聘 - 标题含"(Chinese Mainland) Campus Recruiting"，毕业时间窗口2025.6.1-2027.8.31
- **届别要求**: Required Graduation Period: 2025.6.1 - 2027.8.31；Bachelor's/Master's/PhD in Chemistry, Chemical Engineering, Biology等
- **详情URL**: https://www.pgcareers.com/global/en/job/CNC003184/-Chinese-Mainland-Campus-Recruiting-Research-Development-Scientist
- **采集时间**: 2026-09-10

### 样例2: Manager of One Brand Function - Brand Management (BRM)
- **岗位标题原文**: (Chinese Mainland) Campus Recruiting – Manager of One Brand Function - Brand Management (BRM)
- **招聘单位原文**: Procter & Gamble (宝洁)
- **工作地点**: Guangzhou/Shanghai/Beijing
- **性质判断及依据**: 校园招聘 - 标题含"(Chinese Mainland) Campus Recruiting"，品牌管理管培岗
- **届别要求**: Required Graduation Period: 2025.6.1 - 2027.8.31；Bachelor's minimum
- **详情URL**: https://www.pgcareers.com/global/en/job/CNC003221/-Chinese-Mainland-Campus-Recruiting-Manager-of-One-Brand-Function-Brand-Management-BRM
- **采集时间**: 2026-09-10

### 样例3: Finance & Accounting Manager
- **岗位标题原文**: (Chinese Mainland) Campus Recruiting - Finance & Accounting Manager
- **招聘单位原文**: Procter & Gamble (宝洁)
- **工作地点**: Guangzhou/Shanghai/Beijing/Tianjin/Taicang/Chengdu
- **性质判断及依据**: 校园招聘 - 标题含"(Chinese Mainland) Campus Recruiting"，财务管培岗
- **届别要求**: Required Graduation Period: 2025.6.1 - 2027.8.31；Bachelor's minimum
- **详情URL**: https://www.pgcareers.com/global/en/job/CNC003185/-Chinese-Mainland-Campus-Recruiting-Finance-Accounting-Manager
- **采集时间**: 2026-09-10

### 其他中国区校招职位(共8个)
4. Human Resources Manager (CNC003210) - 地点待确认
5. Product Supply Manager – Operation Management / Digital Engineer (CNC003172)
6. Manager of One Brand Function - Consumer Market Knowledge (CMK) (CNC003222)
7. Customer Business Development Manager (CNC003200)
8. Information Technology Manager (CNC003215)

## 7. 任务状态

| 字段 | 内容 |
|------|------|
| integration_stage | A阶段-探源完成 |
| run_health | healthy |
| blocker_reason | 无 (3条真实岗位样例已获取，含完整详情) |
