# 阿斯利康 (AstraZeneca) - 探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**company_slug**: astrazeneca
**采集时间**: 2026-09-10
**执行状态**: 成功(中国区社招) + 部分阻塞(中国区校招)

## 1. 官方归属证据
- **attribution_evidence_url**: https://job-search.astrazeneca.cn/
- **attribution_evidence_excerpt**: 页面标题"在阿斯利康的生活"，标语"多元思想 大胆颠覆 影响深远"，AstraZeneca logo，导航含"主页/搜索职位/您保存的职位"，语言切换含中文/English/Deutsch/Français等
- **辅助证据**: 全球站 https://careers.astrazeneca.com/ 标语"Diverse Minds, Bold Disruptors, Meaningful Impact"

## 2. 招聘入口
| 字段 | 值 |
|---|---|
| homepage_url | https://www.astrazeneca.com.cn/ |
| official_entry_url | https://job-search.astrazeneca.cn/ |
| job_list_url | https://job-search.astrazeneca.cn/求职?k=&l=China |
| detail_url_pattern | TalentBrew格式 (待确认具体路径) |
| 全球招聘 | https://careers.astrazeneca.com/ |
| Early Talent | https://careers.astrazeneca.com/early-talent |

## 3. 读取方式
| 字段 | 值 |
|---|---|
| access_mode | requires_rendering (TalentBrew SPA，职位数据通过JS加载，但web.fetch可渲染) |
| authentication_required_for_read | false |
| authentication_required_for_apply | true |
| source_kind | TalentBrew (Radancy) 前端 + 后端ATS |
| platform_family | TalentBrew/Radancy |
| platform_version_hint | TalentBrew Full版 (组织ID 12977, 站点ID 18300, 租户ID 3845) |

## 4. 分页信息
| 字段 | 值 |
|---|---|
| pagination_type | 前端分页 (上一页/下一页) |
| expected_total | 259 (中国区职位总数) |
| observed_unique_total | 259 (页面声明) |
| completeness | 总数确认，首屏约12个职位已验证 |

## 5. 招聘范围
| 字段 | 值 |
|---|---|
| scope_country_region | 中国全国 (汉中、成都、上海、北京、广州、杭州、长沙、无锡、青岛等) |
| scope_recruitment_type | 社招为主 (中国站无专门校招列表) |
| scope_campaign | 中国区: 常规社招259岗; 全球: Early Talent项目(含Operations Graduate Programme-中国) |
| 届别要求 | 中国站无应届毕业生专场; 全球Graduate Programme面向应届毕业生 |
| 职能分布 | 医学事务(MSL)、销售(MR)、市场、市场准入、研发、生产/质量(无锡、青岛) |

## 6. 真实岗位样例

### 岗位1: MR-突破性多适应症生物制剂-汉中
- **招聘单位**: 阿斯利康中国
- **工作地点**: 陕西 汉中
- **性质判断**: 社招 (医药代表)
- **采集时间**: 2026-09-10

### 岗位2: Medical Science Liaison-HCC/BTC-Chengdu
- **招聘单位**: 阿斯利康中国
- **工作地点**: 四川 成都
- **性质判断**: 社招 (医学联络官)
- **采集时间**: 2026-09-10

### 岗位3: BM/SBM-Bax MKT-上海
- **招聘单位**: 阿斯利康中国
- **工作地点**: 上海
- **性质判断**: 社招 (品牌经理/高级品牌经理)
- **采集时间**: 2026-09-10

### 校招相关 (全球Early Talent):
### 岗位4: Operations Graduate Programme (含中国)
- **招聘单位**: AstraZeneca Global
- **工作地点**: China, Sweden, UK, US, Ireland
- **性质判断**: 全球校招毕业生项目 (Early Talent - Graduates)
- **子项目**: Operations Global Graduate Associates Programme
- **来源**: https://careers.astrazeneca.com/early-talent
- **采集时间**: 2026-09-10

### 岗位5: 试翼计划实习生项目 (中国)
- **招聘单位**: 阿斯利康中国
- **性质判断**: 可转正实习项目
- **来源**: 澎湃新闻2025-07-07报道
- **状态**: 2025年开启，2027年状态待确认

## 7. 任务状态
| 字段 | 值 |
|---|---|
| integration_stage | A阶段-探源完成 |
| run_health | healthy (社招) / partial (校招) |
| blocker_reason | 中国区校招: job-search.astrazeneca.cn搜索trainee=0结果，graduate/intern返回常规职位而非校招项目；中国区无专门校招职位列表。校招通过全球Early Talent系统管理(Operations Graduate Programme含中国地点)，以及"试翼计划"实习项目(2025年数据)。2027届中国校招专场尚未在官方渠道发现。 |

## 备注
- 阿斯利康中国使用TalentBrew(Radancy)招聘平台，非Workday/SuccessFactors/Moka/北森
- 中国站259个职位均为社招，无应届毕业生专场
- 全球Early Talent页面的Operations Graduate Programme明确包含China，是中国区校招的主要通道
- "试翼计划"是阿斯利康中国的可转正实习项目，通常在每年年中开启
- 外企校招与社招分离，全球学生项目不等于中国校招，需通过全球系统申请
- 职位详情URL需进一步确认TalentBrew路由格式
