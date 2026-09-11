# 欧莱雅(L'Oréal)中国区校招源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**公司**: 欧莱雅 (L'Oréal)
**company_slug**: loreal
**采集时间**: 2026-09-10
**状态**: ⚠️ 部分完成 - 上海职位已获取(3条)，中国区管培生项目未在全球站列出

---

## 1. 官方归属证据

| 字段 | 内容 |
|------|------|
| attribution_evidence_url | https://careers.loreal.com/ |
| attribution_evidence_excerpt | 页面标题"Life Is Too Short For A Boring Career"，摘录"At L'Oréal, you'll find a career that feels as alive as you do. You're surrounded by people who are curious, creative and electric."，含Digital Marketing/Marketing/Finance/HR/Operations/R&I/Data/Tech/Sales/Campus(4个)等25+职能分类 |
| 中国总部 | 上海，在中国拥有32个品牌，一个研发和创新中心，两家工厂(苏州和宜昌)，超过15,000名员工 |

## 2. 招聘入口

| 字段 | 内容 |
|------|------|
| homepage_url | https://www.loreal.com/ |
| official_entry_url | https://careers.loreal.com/ |
| job_list_url | https://careers.loreal.com/en_US/jobs |
| detail_url_pattern | https://careers.loreal.com/en_US/jobs/JobDetail/{Job-Title}/{job-id} |

## 3. 读取方式

| 字段 | 内容 |
|------|------|
| access_mode | web.fetch (jobs页可渲染全球职位列表，含部分职位详情URL) |
| authentication_required_for_read | 否 |
| authentication_required_for_apply | 是 |
| source_kind | 官方全球招聘官网 |
| platform_family | 欧莱雅自建招聘平台 |
| platform_version_hint | 全球999+职位，职位ID为6位数字(如255199) |

## 4. 分页信息

| 字段 | 内容 |
|------|------|
| pagination_type | 滚动/分页 (Showing 1-20 of 999+ results) |
| expected_total | 999+ (全球) |
| observed_unique_total | 999+ (全球)，中国区上海职位3条(从列表中发现) |
| completeness | 全球职位可访问，中国区职位需手动从列表中筛选 |

## 5. 招聘范围

| 字段 | 内容 |
|------|------|
| scope_country_region | 全球 (中国区有上海职位) |
| scope_recruitment_type | 全球社招为主，中国区有管培生项目 |
| scope_campaign | 中国区: 管理培训生项目(Management Trainee) + 区域销售培训生项目(Regional Sales Trainee)，每年招募百余名 |
| 地域分布 | 中国区: 上海(总部)、苏州(工厂)、宜昌(工厂) |
| 届别要求 | 管培生项目面向应届毕业生(具体时间窗口未在全球站获取) |

## 6. 真实岗位样例

### 样例1: (Jr.) Product Manager, H.R.
- **岗位标题原文**: (Jr.) Product Manager, H.R.
- **招聘单位原文**: L'Oréal (欧莱雅)
- **工作地点**: Shanghai
- **性质判断及依据**: Jr.级别(Junior) - 标题含"(Jr.)"前缀，面向初级人才；职位描述提及"the country's priorities"和"3-year marketing plan"，为中国区品牌产品经理岗
- **届别要求**: Jr.级别(具体毕业时间未显示)
- **详情URL**: 未在web.fetch输出中暴露(台湾职位有URL，上海职位无)
- **采集时间**: 2026-09-10
- **发布日期**: 01-Aug-2026
- **职位描述**: Define and steer the country strategy for the category consistent with the international brand positioning and the country's priorities; Define the strategic orientations and the 3-year marketing plan

### 样例2: (Jr.) Product Manager, Shu Uemura
- **岗位标题原文**: (Jr.) Product Manager, Shu Uemura
- **招聘单位原文**: L'Oréal (欧莱雅)
- **工作地点**: Shanghai
- **性质判断及依据**: Jr.级别 - 标题含"(Jr.)"前缀，植村秀品牌中国区产品经理
- **届别要求**: Jr.级别
- **详情URL**: 未暴露
- **采集时间**: 2026-09-10
- **发布日期**: 15-May-2026
- **职位描述**: Own a product line within brand's portfolio — turning brand strategy into launches, campaigns and consumer experiences that bring the brand to life in China

### 样例3: (Jr.) Product Manager, Kiehl's
- **岗位标题原文**: (Jr.) Product Manager, Kiehl's
- **招聘单位原文**: L'Oréal (欧莱雅)
- **工作地点**: Shanghai
- **性质判断及依据**: Jr.级别 - 科颜氏品牌中国区产品经理
- **届别要求**: Jr.级别
- **详情URL**: 未暴露
- **采集时间**: 2026-09-10
- **发布日期**: 11-Jun-2026
- **职位描述**: Own a product line within brand's portfolio — turning brand strategy into launches, campaigns and consumer experiences that bring the brand to life in China

### 非中国区graduate项目(仅作佐证)
- **Marketing Graduate - Professional Products Division** - Copenhagen (丹麦), 发布01-Oct-2026
  - 描述: "Are you a recent graduate with a passion for the beauty industry, digital marketing, and retail?"
  - 明确的graduate项目，但位于丹麦非中国区

### blocker_reason (中国区管培生项目)
1. URL参数过滤不生效: ?keyword=trainee&location=Shanghai仍显示999+全球职位
2. 中国区管理培训生(MT)和区域销售培训生项目未在全球招聘页列出，可能通过微信公众号/小程序或专门校招网站招聘
3. 上海职位的详情URL未在web.fetch输出中显示(台湾职位有完整URL，上海职位仅显示标题)，无法直接获取详情页
4. Campus分类仅4个职位，未确认是否包含中国区
5. 上述3条上海Jr. Product Manager职位为真实可查职位，但非明确的"校招/管培生"项目，性质为Jr.级别社招/初级岗位

## 7. 任务状态

| 字段 | 内容 |
|------|------|
| integration_stage | A阶段-探源完成(列表级) |
| run_health | partial |
| blocker_reason | 中国区管理培训生(MT)和区域销售培训生项目未在全球招聘页列出(可能通过微信/专门校招站)；URL参数过滤不生效；上海职位详情URL未暴露。已获取3条上海真实Jr.级别职位(产品经理)，含职位描述和发布日期。 |
