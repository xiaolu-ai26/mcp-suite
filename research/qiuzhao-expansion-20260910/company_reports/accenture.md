# 埃森哲(Accenture)中国区校招源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**公司**: 埃森哲 (Accenture)
**company_slug**: accenture
**采集时间**: 2026-09-10
**状态**: ⚠️ 部分完成 - 职位列表已获取(6条)，详情页URL未找到

---

## 1. 官方归属证据

| 字段 | 内容 |
|------|------|
| attribution_evidence_url | https://www.accenture.com/cn-zh/careers |
| attribution_evidence_excerpt | 页面标题"归属、成长、成就。与埃森哲一起重塑"，含"学生"、"初级职位"、"社会招聘"、"执行高管"职业阶段分类，以及AI和数据科学、咨询、工程与制造、运营与交付、软件工程、战略、技术服务等业务领域 |
| 中国官网 | https://www.accenture.com/cn-zh |

## 2. 招聘入口

| 字段 | 内容 |
|------|------|
| homepage_url | https://www.accenture.com/cn-zh |
| official_entry_url | https://www.accenture.com/cn-zh/careers |
| job_list_url | https://www.accenture.com/cn-zh/careers/jobsearch |
| detail_url_pattern | 未确认 (尝试 /jobdetail?jobId= 和 /job-detail/ 均link dead) |

## 3. 读取方式

| 字段 | 内容 |
|------|------|
| access_mode | web.fetch (jobsearch页可渲染职位列表) |
| authentication_required_for_read | 否 (职位列表公开可读) |
| authentication_required_for_apply | 是 |
| source_kind | 官方招聘官网 |
| platform_family | 埃森哲自建招聘平台 |
| platform_version_hint | 职位编号格式 R00XXXXXX，级别标签 Early Career/Mid-Level |

## 4. 分页信息

| 字段 | 内容 |
|------|------|
| pagination_type | 页码分页 (显示"1 / 1") |
| expected_total | 6 (按位置过滤后)，另有"11"可能为未过滤总数 |
| observed_unique_total | 6 |
| completeness | 当前过滤条件下完整，但可能存在更多未过滤职位 |

## 5. 招聘范围

| 字段 | 内容 |
|------|------|
| scope_country_region | 中国 (大连、北京、广州、Various locations) |
| scope_recruitment_type | 含Early Career(初级/校招)和Mid-Level(社招) |
| scope_campaign | FY25 PWD Hiring (People with Disabilities招聘项目) |
| 地域分布 | 大连、北京、广州、Various locations |
| 届别要求 | Early Career职位面向初级人才/应届毕业生，具体毕业时间未在列表中显示 |

## 6. 真实岗位样例

### 样例1: Business Agility Senior Analyst (Presales/Implementation Expert)
- **岗位标题原文**: Presales/Implementation Expert — Job: Business Agility Senior Analyst
- **招聘单位原文**: Accenture (埃森哲)
- **工作地点**: Various locations
- **性质判断及依据**: Early Career级别 - 职位列表标注"Early Career"标签，面向初级人才；职位编号R00002228
- **届别要求**: Early Career (具体毕业时间未显示)
- **详情URL**: 未确认 (详情页URL模式未找到)
- **采集时间**: 2026-09-10
- **职位描述**: SAP FICO/SD/MM/PP/PS/EWM等模块咨询工作，包括业务需求分析、方案设计、项目实施、测试支持和用户培训

### 样例2: Business Architecture Analyst (FY25 PWD Hiring)
- **岗位标题原文**: FY25 PWD Hiring — Job: Business Architecture Analyst
- **招聘单位原文**: Accenture (埃森哲)
- **工作地点**: 大连
- **性质判断及依据**: Early Career级别 - 标注"Early Career"，FY25 PWD Hiring项目面向残障人士的校招/初级招聘；职位编号R00195057
- **届别要求**: Early Career
- **详情URL**: 未确认
- **采集时间**: 2026-09-10
- **职位描述**: 学习工作中主要应用的技术，完成技术文档编写、代码编写及单元测试，适应开发/测试/技术支持/项目流程管理等不同项目角色

### 样例3: Procure to Pay Operations Associate
- **岗位标题原文**: Procure to Pay Operations Associate/Analyst — Job: Procure to Pay Operations Associate
- **招聘单位原文**: Accenture (埃森哲)
- **工作地点**: 大连
- **性质判断及依据**: Early Career级别 - 标注"Early Career"，运营类初级岗位；职位编号R00180300
- **届别要求**: Early Career
- **详情URL**: 未确认
- **采集时间**: 2026-09-10
- **职位描述**: 协助客户处理AP日常业务，包括发票审核及入账、税票清单整理及单据归档、付款科目对账、员工报销审核等

### 其他职位
4. Contracting Counsel Associate Manager - 北京, Mid-Level, R00344040
5. Order to Cash Operations Analyst/Associate - 大连, Early Career, R00180299
6. AI/ML Computational Science Associate Manager - 广州, Mid-Level, R00163755

### blocker_reason (详情页)
职位详情页URL模式未找到。尝试的两种模式(/jobdetail?jobId=R00195057和/job-detail/R00195057)均返回link dead。jobsearch页带查询参数进行筛选时被robots.txt禁止。职位列表信息(标题/地点/级别/编号/描述摘要)真实可靠，但完整详情页需通过页面JS交互获取。

## 7. 任务状态

| 字段 | 内容 |
|------|------|
| integration_stage | A阶段-探源完成(列表级) |
| run_health | partial |
| blocker_reason | 职位详情页URL模式未找到，带参数的jobsearch页被robots.txt禁止；职位列表(6条含Early Career校招级)已获取，含职位编号和描述摘要 |
