# 汇川技术 (Inovance) 校招源调查报告

- **company_slug**: inovance
- **调查时间**: 2026-09-10
- **调查人**: 制造汽车组探源执行者
- **任务编号**: QIUZHAO-EXPANSION-20260910

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://recruit.inovance.com/
- **attribution_evidence_excerpt**: 页面标题"全部职位"，多所高校就业网（四川美术学院、长春理工大学等）发布的汇川技术2027届校招简章均写明"汇川技术招聘官网：https://recruit.inovance.com/"，简历投递链接为 https://recruit.inovance.com/#/jobs?ref=APHZ76D。

## 2. 招聘入口

- **homepage_url**: https://www.inovance.cn/
- **official_entry_url**: https://recruit.inovance.com/
- **job_list_url**: https://recruit.inovance.com/#/jobs
- **detail_url_pattern**: https://recruit.inovance.com/#/job/{jobId} (SPA前端路由推断)

## 3. 读取方式

- **access_mode**: web_spa (Vue单页应用，hash路由)
- **authentication_required_for_read**: false (岗位列表可公开浏览)
- **authentication_required_for_apply**: true (投递需登录)
- **source_kind**: official_self_built (汇川技术自建招聘系统)
- **platform_family**: self_built_recruitment
- **platform_version_hint**: Vue SPA，hash路由 #/jobs

## 4. 分页信息

- **pagination_type**: scroll_or_page (页面显示"共有392个在招职位")
- **expected_total**: 392 (页面显示"共有392个在招职位")
- **observed_unique_total**: 392 (首页展示20+条，含大量27校招岗位)
- **completeness**: partial (采集首页20条，共392条)

## 5. 招聘范围

- **scope_country_region**: 中国为主，含海外（日本、泰国、德国、法国、意大利、英国等）
- **scope_recruitment_type**: 校园招聘 + 社会招聘（同一系统混合展示）
- **scope_campaign**: 2027届校园招聘（2026年8月启动）
- **地域分布**: 苏州（总部）、南京、深圳、上海、西安、北京、常州、武汉、济南、岳阳、东莞等
- **届别要求**: 2027届毕业生

## 6. 真实岗位样例

| # | 岗位标题原文 | 招聘单位原文 | 工作地点 | 性质判断及依据 | 届别要求 | 详情URL | 采集时间 |
|---|---|---|---|---|---|---|---|
| 1 | 【27校招 - 联合动力】机械可靠性工程师 | 分子公司-联合动力 | 苏州市 | 校招研发岗，标题含"27校招"，硕士 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |
| 2 | 【27校招 - 联合动力】嵌入式软件工程师（车载电源/电机控制器/底盘等） | 分子公司-联合动力 | 苏州市/深圳市/西安市 | 校招研发岗，标题含"27校招"，本科 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |
| 3 | 【27校招 - 联合动力】硬件工程师（功率/控制硬件/电源硬件、AIDC等） | 分子公司-联合动力 | 深圳市/苏州市/西安市/上海市 | 校招研发岗，标题含"27校招"，本科 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |
| 4 | 【27校招 - 数字化】全栈工程师 | 集团业务-数字化 | 苏州市 | 校招技术岗，标题含"27校招"，本科 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |
| 5 | 【27校招 - 数字能源】海外储能电站技术营销工程师 | 集团业务-数字能源 | 德国/法国/意大利/苏州市 | 校招营销岗，标题含"27校招"，本科 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |
| 6 | 【27校招 - 联合动力】电机控制算法工程师 | 分子公司-联合动力 | 苏州市/西安市 | 校招研发岗，标题含"27校招"，硕士 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |
| 7 | 【27校招 - 联合动力】EMC工程师 | 分子公司-联合动力 | 苏州市/深圳市 | 校招研发岗，标题含"27校招"，硕士 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |
| 8 | 【27校招 - 数字能源】全球零碳电气工程师 | 集团业务-数字能源 | 苏州市 | 校招技术岗，标题含"27校招"，本科 | 2027届 | https://recruit.inovance.com/#/job | 2026-09-10 |

## 7. 任务状态

- **integration_stage**: source_discovered
- **run_health**: healthy
- **blocker_reason**: null

---

## 补充说明

- 汇川技术招聘官网 recruit.inovance.com 为自建系统，社招和校招混合展示
- 校招岗位统一以"【27校招 - 业务板块】"前缀标识，便于筛选
- 岗位类别: 技术类、营销类、质量类、技能类、供应链管理类、其他职能类
- 业务板块: 联合动力、数字化、数字能源、通用自动化、品牌部等
- 微信公众号"汇川技术招聘"为移动端投递渠道
- 证据文件: evidence/inovance/job_list.txt
