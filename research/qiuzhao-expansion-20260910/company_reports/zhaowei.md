# 兆威机电 (Zhaowei) 校招源调查报告

- **company_slug**: zhaowei
- **调查时间**: 2026-09-10
- **调查人**: 制造汽车组探源执行者
- **任务编号**: QIUZHAO-EXPANSION-20260910

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://www.szzhaowei.net/
- **attribution_evidence_excerpt**: 官网首页标注"深圳市兆威机电股份有限公司"，股票代码003021.SZ & 02692.HK，总部地址"深圳市宝安区燕罗街道燕川社区燕湖路88号兆威工业园"，电话0755-27322645，邮箱sales@szzhaowei.net。公司成立于2001年，注册资金2.3亿余元，是微型驱动系统方案解决商。

## 2. 招聘入口

- **homepage_url**: https://www.szzhaowei.net/ (也可通过 https://www.zwgear.com/ 访问)
- **official_entry_url**: 无独立在线招聘门户；官网无"加入我们"/"人才招聘"频道
- **job_list_url**: 无官方岗位列表页（岗位通过猎聘、企查查、职友集等第三方平台发布）
- **detail_url_pattern**: 第三方平台URL，如 https://m.qcc.com/jobdetail/{jobId}.html

## 3. 读取方式

- **access_mode**: third_party_platform (无自建招聘系统，岗位发布在第三方招聘平台)
- **authentication_required_for_read**: false (第三方平台岗位可公开浏览)
- **authentication_required_for_apply**: true (投递需在第三方平台注册/登录)
- **source_kind**: third_party_platform
- **platform_family**: liepin_qcc_jobui (猎聘/企查查/职友集等综合平台)
- **platform_version_hint**: 无统一招聘系统，岗位编号格式如Z00563、Z01668、Z10821

## 4. 分页信息

- **pagination_type**: not_applicable (无官方岗位列表系统)
- **expected_total**: unknown (未发现2027届校招统一公告)
- **observed_unique_total**: 1 (可验证的应届生岗位)
- **completeness**: incomplete (仅通过第三方平台获取1条应届生岗位，无完整校招岗位清单)

## 5. 招聘范围

- **scope_country_region**: 中国（深圳总部、东莞、上海、苏州、香港、德国）
- **scope_recruitment_type**: 以社会招聘为主，少量应届生岗位
- **scope_campaign**: 未发现2027届统一校招公告
- **地域分布**: 深圳市宝安区（总部）、东莞市望牛墩镇、上海市闵行区、苏州高新区、德国Marktoberdorf
- **届别要求**: 应届硕士（已验证岗位要求硕士以上）

## 6. 真实岗位样例

| # | 岗位标题原文 | 招聘单位原文 | 工作地点 | 性质判断及依据 | 届别要求 | 详情URL | 采集时间 |
|---|---|---|---|---|---|---|---|
| 1 | 电控硬件工程师（应届生）-Z00563 | 深圳市兆威机电股份有限公司 | 深圳-宝安区 | 应届生岗位，第三方平台明确标注"应届毕业生"，岗位编号Z00563 | 应届硕士 | https://m.qcc.com/jobdetail/4de4499e9c1ef1856f1bbe44268da25c.html | 2026-09-10 |

**岗位1详情**: 电控硬件工程师（应届生）-Z00563
- 薪资: 15-20k
- 发布日期: 2026-03-12（企查查）/ 2026-03-31（顺企网）
- 职责:
  1. 协助团队完成电控硬件产品如控制器、驱动板、传感器模块等的方案设计、原理图绘制、PCB Layout及元器件选型工作
  2. 参与硬件样品的焊接、调试与测试，协助排查样品故障
- 要求: 硕士以上学历，应届毕业生
- 岗位编号: Z00563

## 7. 任务状态

- **integration_stage**: source_discovered_with_limitations
- **run_health**: degraded
- **blocker_reason**: 兆威机电无自建在线招聘门户/岗位列表系统，官网（szzhaowei.net / zwgear.com）无招聘频道，校招岗位主要通过猎聘、企查查、职友集等第三方平台零散发布。未发现2027届统一校招公告，仅验证到1条应届生岗位（电控硬件工程师-Z00563，2026年3月发布）。无法获取完整校招岗位清单及分页遍历。

---

## 补充说明

- 兆威机电官网为产品展示网站，无"加入我们"/"人才招聘"频道
- 公司在猎聘有55个在招职位，但绝大多数为社招（要求2年以上经验）
- 岗位编号体系：Z开头（如Z00563、Z01668、Z10821、Z10692、Z00681），J开头（如J10399），可能为内部招聘管理系统编号
- 已验证的应届生岗位发布于2026年3月，可能为2026届春招岗位，非2027届秋招
- 建议后续关注第三方平台或公司官网是否发布2027届校招公告
- 证据文件: 无独立证据文件（岗位详情来自企查查/职友集页面抓取）
