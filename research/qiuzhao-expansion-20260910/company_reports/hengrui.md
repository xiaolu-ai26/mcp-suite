# 恒瑞医药 (Hengrui) - 探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**company_slug**: hengrui
**采集时间**: 2026-09-10
**执行状态**: 成功

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://www.hengrui.com/
- **attribution_evidence_excerpt**: 官网页脚"恒瑞医药招聘"二维码，与"恒瑞官微""合规廉正投诉举报""报告不良事件"并列；公司地址"江苏省连云港经济技术开发区昆仑山路7号"；服务热线400-8283900
- **辅助证据**: Moka社招页 https://app.mokahr.com/social-recruitment/hengrui/145996 显示"恒瑞医药"品牌标识、"科技为本，为人类创造健康生活"标语，与官网一致

## 2. 招聘入口

| 字段 | 值 |
|---|---|
| homepage_url | https://www.hengrui.com/ |
| official_entry_url | https://app.mokahr.com/campus-recruitment/hengrui |
| job_list_url | https://app.mokahr.com/campus-recruitment/hengrui#/jobs |
| detail_url_pattern | https://app.mokahr.com/campus-recruitment/hengrui#/job/{job_uuid} |
| 社招入口 | https://app.mokahr.com/social-recruitment/hengrui/145996 |

## 3. 读取方式

| 字段 | 值 |
|---|---|
| access_mode | requires_rendering (Moka SPA，职位数据通过JS动态加载) |
| authentication_required_for_read | false (职位列表可公开浏览) |
| authentication_required_for_apply | true (投递需注册登录Moka账号) |
| source_kind | Moka |
| platform_family | Moka |
| platform_version_hint | Moka现代版 (SPA架构，hash路由 #/jobs) |

## 4. 分页信息

| 字段 | 值 |
|---|---|
| pagination_type | 前端滚动加载/分页 (Moka标准列表) |
| expected_total | 444 (校招职位列表页显示"444 结果") |
| observed_unique_total | 444 (页面声明值) |
| completeness | 部分验证 - 首页可见约20+职位，含2027届校招岗和实习生岗 |

## 5. 招聘范围

| 字段 | 值 |
|---|---|
| scope_country_region | 中国全国 (武汉、天津、郑州、济南/青岛、南京/杭州/上海、合肥、沈阳、上海等) |
| scope_recruitment_type | 校园招聘 (含2027届全职管培生 + 实习生) |
| scope_campaign | 2027届秋季校园招聘 (2026-09-10大量职位发布) + 恒星计划管理培训生项目 |
| 届别要求 | 2027届为主，另有27届实习生岗位 |
| 职能分布 | 营销类占多数 (销售管培生、医药信息沟通专员/实习生)，研发/临床/生产/职能类需进一步筛选验证 |

## 6. 真实岗位样例

### 岗位1: 销售管培生-肿瘤-武汉-2027届
- **招聘单位**: 恒瑞医药
- **工作地点**: 湖北·武汉市
- **性质判断**: 校招全职管培生 (标题标注"2027届"，岗位职责含"管培生培养计划，多岗位轮岗培养")
- **届别要求**: 2027届毕业生；211/985院校硕士及以上，医药相关专业
- **详情URL**: https://app.mokahr.com/campus-recruitment/hengrui#/job/{job_uuid}
- **采集时间**: 2026-09-10
- **发布时间**: 2026-09-10

### 岗位2: 销售管培生-肿瘤-天津-2027届
- **招聘单位**: 恒瑞医药
- **工作地点**: 天津市
- **性质判断**: 校招全职管培生 (同上)
- **届别要求**: 2027届毕业生；211/985院校硕士及以上，医药相关专业
- **详情URL**: https://app.mokahr.com/campus-recruitment/hengrui#/job/{job_uuid}
- **采集时间**: 2026-09-10
- **发布时间**: 2026-09-10

### 岗位3: 医药信息沟通实习生-肿瘤-上海
- **招聘单位**: 恒瑞医药
- **工作地点**: 上海市
- **性质判断**: 校招实习生岗位 (标题含"实习生"，任职要求"本科及以上，医药类专业"，页面标注"全职"但实际为实习带教岗)
- **届别要求**: 未明确届别，本科及以上学历，医学/药学/护理/生物/化学/医疗健康类专业
- **详情URL**: https://app.mokahr.com/campus-recruitment/hengrui#/job/{job_uuid}
- **采集时间**: 2026-09-10
- **发布时间**: 2026-09-10

### 岗位4 (补充): BBU代谢疼痛—27届—实习生—上海
- **招聘单位**: 恒瑞医药
- **工作地点**: 上海市
- **性质判断**: 校招实习生 (标题明确"27届""实习生")
- **届别要求**: 2027届
- **采集时间**: 2026-09-10
- **发布时间**: 2026-06-11

## 7. 任务状态

| 字段 | 值 |
|---|---|
| integration_stage | A阶段-探源完成 |
| run_health | healthy |
| blocker_reason | null |

## 备注

- 恒瑞官网招聘入口为页脚二维码，扫码后进入Moka系统
- 校招与社招共用Moka平台，不同路径 (campus-recruitment vs social-recruitment)
- 投递限制: 一年内最多投递3个职位
- 2027届秋招已于2026-09-10大规模发布 (销售管培生系列全国多城市同步上线)
- 职位详情URL中的job_uuid为Moka内部UUID，需通过前端API获取，静态HTML中不可见
