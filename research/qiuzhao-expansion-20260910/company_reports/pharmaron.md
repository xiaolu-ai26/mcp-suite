# 康龙化成 (Pharmaron) - 探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**company_slug**: pharmaron
**采集时间**: 2026-09-10
**执行状态**: 成功

## 1. 官方归属证据
- **attribution_evidence_url**: https://pharmaron.zhiye.com (北森门户HTML中tenantInfo明确: Name="Pharmaron", Alias="康龙化成（成都）临床研究服务有限公司")
- **attribution_evidence_excerpt**: 北森门户导航配置中校园招聘外链指向 `https://app.mokahr.com/campus-recruitment/pharmaron/44352?locale=zh-CN`，域名路径含"pharmaron"

## 2. 招聘入口
| 字段 | 值 |
|---|---|
| homepage_url | https://www.pharmaron.com/cn/ |
| official_entry_url | https://app.mokahr.com/campus-recruitment/pharmaron/44352?locale=zh-CN |
| job_list_url | https://app.mokahr.com/campus-recruitment/pharmaron/44352#/jobs |
| detail_url_pattern | https://app.mokahr.com/campus-recruitment/pharmaron/44352#/job/{job_uuid} |
| 社招入口 | https://pharmaron.zhiye.com/social (北森) |
| 实习入口 | https://app.mokahr.com/campus-recruitment/pharmaron/47265?locale=zh-CN |

## 3. 读取方式
| 字段 | 值 |
|---|---|
| access_mode | requires_rendering (Moka SPA) |
| authentication_required_for_read | false |
| authentication_required_for_apply | true |
| source_kind | Moka (校招/实习) + 北森 (社招) |
| platform_family | Moka |
| platform_version_hint | Moka现代版 (campus-recruitment/{org}/{id}) |

## 4. 分页信息
| 字段 | 值 |
|---|---|
| pagination_type | 前端分页 (30行/页) |
| expected_total | 584 |
| observed_unique_total | 584 (页面声明) |
| completeness | 总数确认，首屏30条已验证 |

## 5. 招聘范围
| 字段 | 值 |
|---|---|
| scope_country_region | 中国 (北京、宁波、天津、青岛、西安、绍兴等) |
| scope_recruitment_type | 校园招聘 (2027届为主，含少量2026届补录) |
| scope_campaign | 2027届全球校园招聘 |
| 届别要求 | 博士2026.1.1-2027.12.31; 硕士国内2027.1.1-2027.12.31/海外2026.1.1-2027.12.31; 本科2027.1.1-2027.12.31 |
| 职能分布 | 临床(195)、运营(92)、生物科学(84)、化学生产控制(66)、合成(46)、分析(41)、安评(35)、大分子(18)、AI(7) |

## 6. 真实岗位样例

### 岗位1: 2027届-博士-化学分析研究员(药物分析)-北京总部
- **招聘单位**: 康龙化成（北京）新药技术股份有限公司
- **工作地点**: 北京市
- **性质**: 校招全职 (标题"2027届-博士")
- **职能**: 分析
- **详情URL**: Moka SPA #/job/{uuid}
- **采集时间**: 2026-09-10

### 岗位2: 2027届-博士-有机合成研究员-天津
- **招聘单位**: 康龙化成（天津）药物制备技术有限公司
- **工作地点**: 天津市
- **性质**: 校招全职
- **职能**: 合成
- **采集时间**: 2026-09-10

### 岗位3: 2027届-博士-生物学研究员-北京总部
- **招聘单位**: 康龙化成（北京）新药技术股份有限公司
- **工作地点**: 北京市
- **性质**: 校招全职
- **职能**: 生物科学
- **采集时间**: 2026-09-10

### 岗位4 (补充): 2027届-博士-软件工程师-北京总部
- **招聘单位**: Engineering Department
- **工作地点**: 北京市
- **性质**: 校招全职 (2026届补录)
- **职能**: AI 人工智能

## 7. 任务状态
| 字段 | 值 |
|---|---|
| integration_stage | A阶段-探源完成 |
| run_health | healthy |
| blocker_reason | null |

## 备注
- 康龙化成采用双系统: 校招/实习用Moka，社招用北森(zhiye.com)
- 北森门户标题为"康龙临床"，租户主体为"康龙化成（成都）临床研究服务有限公司"
- 584个校招职位中临床类占比最大(195个)，符合CRO企业特征
- 投递限制: 每人3个职位，第一志愿优先
