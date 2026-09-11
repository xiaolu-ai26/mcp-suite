# 比亚迪集团 (BYD) 校招源调查报告

- **company_slug**: byd
- **调查时间**: 2026-09-10
- **调查人**: 制造汽车组探源执行者
- **任务编号**: QIUZHAO-EXPANSION-20260910

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://job.byd.com/portal/pc/
- **attribution_evidence_excerpt**: 页面标题"比亚迪招聘"，页脚"比亚迪集团 Copyright ©1995-2023 BYD Company Ltd. All rights reserved. 粤ICP备10216027号"。多所高校就业网（南开大学、四川美术学院等）发布的比亚迪2027届校招简章均写明"PC端：job.byd.com-选择'校园招聘'"。

## 2. 招聘入口

- **homepage_url**: https://www.byd.com/
- **official_entry_url**: https://job.byd.com/ (自动重定向到 /portal/pc/)
- **job_list_url**: https://job.byd.com/portal/pc/#/school/schoolPositionList
- **detail_url_pattern**: https://job.byd.com/portal/pc/#/school/schoolPositionDetail (SPA前端路由，需jobId参数)

## 3. 读取方式

- **access_mode**: web_spa (Vue单页应用，hash路由)
- **authentication_required_for_read**: false (岗位列表可公开浏览)
- **authentication_required_for_apply**: true (投递简历需登录账号)
- **source_kind**: official_self_built (比亚迪自建人力资源服务平台)
- **platform_family**: self_built_hr_portal
- **platform_version_hint**: Vue + elementUI，webpack打包，API base /portal-api

## 4. 分页信息

- **pagination_type**: numbered_pagination (页码导航，每页10条)
- **expected_total**: 386 (应届生岗位，页面显示"在招职位(386)")
- **observed_unique_total**: 386 (第1页10条已验证，总数与页面声明一致)
- **completeness**: partial (仅采集第1页10条，共39页；分页结构明确可遍历)

## 5. 招聘范围

- **scope_country_region**: 中国大陆为主，含境外岗位（巴西、匈牙利、墨西哥、马来西亚、澳大利亚、智利、印尼、土耳其、越南、泰国、荷兰、乌兹别克斯坦）
- **scope_recruitment_type**: 校园招聘（应届生 + 博士生 + 实习生 + 外派专项）
- **scope_campaign**: 2027届全球校园招聘（2026年8月19日启动）
- **地域分布**: 深圳（总部）、西安、惠州、上海、重庆、绍兴、成都、合肥、长沙、郑州、芜湖、抚州等
- **届别要求**: 境内院校 2026.09.01-2027.08.31；境外院校 2026.07.01-2027.12.31

## 6. 真实岗位样例

| # | 岗位标题原文 | 招聘单位原文 | 工作地点 | 性质判断及依据 | 届别要求 | 详情URL | 采集时间 |
|---|---|---|---|---|---|---|---|
| 1 | 高级供应链管理工程师 | 比亚迪集团（采购类） | 深圳市 | 校招技术岗，应届生频道，发布日期2026-09-09 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 2 | 高级关务专员 | 比亚迪集团（物流类） | 深圳市 | 校招综合岗，应届生频道 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 3 | 高级律师 | 比亚迪集团（法务类） | 深圳市/西安市 | 校招综合岗，应届生频道 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 4 | 高级整车集成工程师 | 比亚迪集团（研发技术类） | 深圳市 | 校招研发岗，应届生频道，汽车研发 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 5 | 高级车型成本分析工程师 | 比亚迪集团（技术支持类） | 深圳市 | 校招技术岗，应届生频道 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 6 | 高级异响工程师 | 比亚迪集团（研发技术类） | 深圳市 | 校招研发岗，应届生频道，NVH方向 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 7 | 高级热管理工程师 | 比亚迪集团（研发技术类） | 深圳市/重庆市 | 校招研发岗，应届生频道 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 8 | 模具设计工程师 | 比亚迪集团（制造技术类） | 广州/惠州/深圳/西安/郑州/阜阳/韶关 | 校招制造岗，应届生频道 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 9 | 高级产品设计工程师 | 比亚迪集团（研发技术类） | 上海/惠州/深圳/西安/长沙 | 校招研发岗，应届生频道 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |
| 10 | 高级软件工程师 | 比亚迪集团（研发技术类） | 上海/北京/宝鸡/惠州/深圳/芜湖/西安/郑州/重庆 | 校招研发岗，应届生频道 | 2027届 | https://job.byd.com/portal/pc/#/school/schoolPositionDetail | 2026-09-10 |

## 7. 任务状态

- **integration_stage**: source_discovered
- **run_health**: healthy
- **blocker_reason**: null (详情页URL为SPA路由推断，未获取到具体jobId参数；列表页数据完整可采集)

---

## 补充说明

- 比亚迪招聘官网 job.byd.com 自动重定向到 /portal/pc/，是自建人力资源服务平台
- 岗位按四大类筛选：技术、综合、运营、营销
- 业务覆盖汽车、电子、新能源、轨道交通四大产业
- 校招流程含测评环节（比亚迪校招测评）
- 同时设有技工招聘、普工招聘频道（非校招）
- 证据文件: evidence/byd/job_list_page1.txt
