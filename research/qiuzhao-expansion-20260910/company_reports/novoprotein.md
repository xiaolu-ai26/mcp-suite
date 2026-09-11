# 诺唯赞 (Vazyme / Novoprotein) - 探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**company_slug**: novoprotein
**采集时间**: 2026-09-10
**执行状态**: 部分阻塞

## 1. 官方归属证据
- **attribution_evidence_url**: https://www.vazyme.com/
- **attribution_evidence_excerpt**: "诺唯赞是一家围绕酶、抗原、抗体等功能性蛋白及高分子有机材料进行技术研发和产品开发的生物科技企业"；地址"南京经济技术开发区科创路红枫科技园C1-2栋东段1-6层"；科创板688105

## 2. 招聘入口
| 字段 | 值 |
|---|---|
| homepage_url | https://www.vazyme.com/ |
| official_entry_url | 未确认 (官网无直接招聘链接) |
| job_list_url | 未确认 |
| detail_url_pattern | 未确认 |
| 疑似Workday | https://novoprotein.wd5.myworkdayjobs.com (域名存在，UI重定向至维护页) |
| 北森域名 | https://vazyme.zhiye.com (域名存在，所有页面返回Error) |

## 3. 读取方式
| 字段 | 值 |
|---|---|
| access_mode | blocked |
| authentication_required_for_read | 未知 |
| authentication_required_for_apply | 未知 |
| source_kind | Workday (疑似，基于MJ前缀职位ID) |
| platform_family | Workday |
| platform_version_hint | 未知 (租户维护中或名称不匹配) |

## 4. 分页信息
| 字段 | 值 |
|---|---|
| pagination_type | 未知 |
| expected_total | 未知 |
| observed_unique_total | 0 (官方系统不可访问) |
| completeness | 未获取 |

## 5. 招聘范围
| 字段 | 值 |
|---|---|
| scope_country_region | 中国 (南京总部，全国销售) |
| scope_recruitment_type | 未知 (官方系统不可访问) |
| scope_campaign | 未知 |

## 6. 真实岗位样例 (第三方佐证-猎聘)
### 岗位1: 海外产品专员 (学生职位)
- **招聘单位**: 南京诺唯赞生物科技股份有限公司
- **工作地点**: 南京-栖霞区
- **性质判断**: 学生职位 (猎聘标注"学生职位")
- **学历要求**: 硕士
- **薪资**: 9-13k
- **来源**: https://m.liepin.com/company-jobs/7940091/
- **采集时间**: 2026-09-10

### 岗位2: HRBP实习生 (学生职位)
- **招聘单位**: 南京诺唯赞生物科技股份有限公司
- **工作地点**: 南京-栖霞区
- **性质判断**: 学生职位/实习 (猎聘标注"学生职位")
- **学历要求**: 本科
- **薪资**: 150-180元/天
- **采集时间**: 2026-09-10

### 岗位3: 国际售后(FAS)主管 (MJ003481)
- **招聘单位**: 南京诺唯赞生物科技股份有限公司
- **工作地点**: 南京-栖霞区
- **性质判断**: 社招 (MJ前缀Workday ID)
- **学历要求**: 硕士, 3-5年
- **薪资**: 15-20k
- **采集时间**: 2026-09-10

## 7. 任务状态
| 字段 | 值 |
|---|---|
| integration_stage | A阶段-探源完成(部分阻塞) |
| run_health | degraded |
| blocker_reason | 官方招聘系统不可直接访问: (1)Workday域名novoprotein.wd5.myworkdayjobs.com存在但UI重定向至community.workday.com/maintenance-page，API返回HTTP 422; (2)北森vazyme.zhiye.com所有页面返回"Error!您访问的站点出错"; (3)vazyme.italent.cn被robots.txt禁止; (4)官网vazyme.com无直接招聘入口链接。职位ID格式MJxxxxx确认使用Workday，但租户当前不可用。第三方猎聘可佐证真实职位存在(52个在招)，含2个学生职位。 |

## 备注
- 诺唯赞官网基于自定义CMS (fastimg.com CDN)，招聘入口可能仅通过微信公众号"诺唯赞招聘"提供
- 建议B阶段: (1)通过微信公众号获取招聘入口; (2)等待Workday租户恢复; (3)尝试浏览器真实访问北森页面
