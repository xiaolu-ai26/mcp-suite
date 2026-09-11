# 义翘神州 (SinoBiological) - 探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**company_slug**: sinobiological
**采集时间**: 2026-09-10
**执行状态**: 成功

## 1. 官方归属证据
- **attribution_evidence_url**: https://sinobiological.zhiye.com/campus
- **attribution_evidence_excerpt**: 北森招聘门户，职位类型"实验类、质量类"，工作地点含北京市(亦庄开发区)、上海市、苏州市、武汉市、广州市、成都市、温哥华；职位ID格式Jxxxxx
- **辅助证据**: 官网 https://cn.sinobiological.com/ 电话400-890-9989，地址北京市北京经济技术开发区科创十街18号院11号楼，创业板301047

## 2. 招聘入口
| 字段 | 值 |
|---|---|
| homepage_url | https://cn.sinobiological.com/ |
| official_entry_url | https://sinobiological.zhiye.com/campus |
| job_list_url | https://sinobiological.zhiye.com/campus |
| detail_url_pattern | https://sinobiological.zhiye.com/campus/jobs/{jobId} (如J11088) |
| 备用域名 | https://sino.zhiye.com |

## 3. 读取方式
| 字段 | 值 |
|---|---|
| access_mode | public_html (北森传统页面，职位列表直接渲染在HTML中) |
| authentication_required_for_read | false |
| authentication_required_for_apply | true |
| source_kind | 北森 |
| platform_family | 北森(Beisen) |
| platform_version_hint | 北森传统版 (zhiye.com，服务端渲染表格) |

## 4. 分页信息
| 字段 | 值 |
|---|---|
| pagination_type | 服务端分页 (表格形式) |
| expected_total | 未知 (页面未显示总数，首屏可见24个职位) |
| observed_unique_total | 24 (首屏) |
| completeness | 部分验证 - 首屏24个职位，可能有更多页 |

## 5. 招聘范围
| 字段 | 值 |
|---|---|
| scope_country_region | 中国 (北京亦庄为主，上海、苏州、武汉、广州、成都) + 温哥华 |
| scope_recruitment_type | 校招/社招混合列表 (含"市场培训生2026"等校招岗) |
| scope_campaign | 未明确2027届校招专场，最新职位发布于2026-08-18 |
| 届别要求 | 未明确 (培训生岗位面向应届毕业生) |
| 职能分布 | 实验类为主 (检测员、纯化专员、研究员、实验员)，质量类，市场/销售培训生 |

## 6. 真实岗位样例

### 岗位1: 市场培训生2026 (J11088)
- **招聘单位**: 北京义翘神州科技股份有限公司
- **工作地点**: 北京市,上海市
- **性质判断**: 校招培训生 (标题含"培训生2026"，面向应届毕业生)
- **发布时间**: 2025-10-31
- **详情URL**: https://sinobiological.zhiye.com/campus/jobs/J11088
- **采集时间**: 2026-09-10

### 岗位2: 微生物检测员 (J11191)
- **招聘单位**: 北京义翘神州科技股份有限公司
- **工作地点**: 北京市-亦庄开发区
- **性质判断**: 校招/社招 (实验类岗位，北森校招列表)
- **发布时间**: 2026-08-18
- **职位类型**: 实验类
- **采集时间**: 2026-09-10

### 岗位3: 蛋白标记专员 (J11186)
- **招聘单位**: 北京义翘神州科技股份有限公司
- **工作地点**: 北京市-亦庄开发区
- **性质判断**: 校招/社招 (实验类岗位)
- **发布时间**: 2026-08-06
- **职位类型**: 实验类
- **采集时间**: 2026-09-10

### 岗位4 (补充): 销售培训生 (J11154) [猎聘佐证]
- **工作地点**: 苏州-虎丘区
- **学历**: 本科
- **薪资**: 6-8k
- **性质**: 校招培训生

## 7. 任务状态
| 字段 | 值 |
|---|---|
| integration_stage | A阶段-探源完成 |
| run_health | healthy |
| blocker_reason | null |

## 备注
- 义翘神州使用北森传统版招聘系统，职位列表为服务端渲染HTML表格，易于抓取
- 校招列表与社招列表混合，需通过职位标题(含"培训生")判断校招性质
- 未发现2027届专门校招专场，最新职位为2026-08-18发布的常规实验岗
- 温哥华有海外职位，说明系统支持全球招聘
