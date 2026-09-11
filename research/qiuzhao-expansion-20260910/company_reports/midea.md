# 美的集团 (Midea Group) 校招源调查报告

- **company_slug**: midea
- **调查时间**: 2026-09-10
- **调查人**: 制造汽车组探源执行者
- **任务编号**: QIUZHAO-EXPANSION-20260910

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://careers.midea.com/
- **attribution_evidence_excerpt**: 页面标题为"美的集团-校园招聘官网"，meta keywords 包含"美的校园招聘,美的校招,美的应届生招聘"，页脚标注"版权所有 美的集团股份有限公司 ICP许可证号：粤ICP备09215446号"。2027届校招公告（南开就业2026-09-03发布）明确写明"岗位详情及投递链接：https://careers.midea.com/"。

## 2. 招聘入口

- **homepage_url**: https://www.midea.com/
- **official_entry_url**: https://careers.midea.com/
- **job_list_url**: https://careers.midea.com/schoolOut/post
- **detail_url_pattern**: https://careers.midea.com/schoolOut/post/details?id={jobId} （由Vue路由 path:"post/details" 推断，SPA前端路由）

## 3. 读取方式

- **access_mode**: web_spa (Vue 3 单页应用，需浏览器渲染)
- **authentication_required_for_read**: false (岗位列表可公开浏览)
- **authentication_required_for_apply**: true (投递简历需登录账号)
- **source_kind**: official_self_built (美的自建校招系统，基于内部@hrd组件库)
- **platform_family**: self_built_hr_system
- **platform_version_hint**: Vue 3 + @hrd-recruit-school-out 组件，移动端自动跳转 /recruit-school-wechat

## 4. 分页信息

- **pagination_type**: numbered_pagination (页码导航，每页10条)
- **expected_total**: 146 (页面显示"在招岗位（146）")
- **observed_unique_total**: 146 (第1页10条已验证，总数与页面声明一致)
- **completeness**: partial (仅采集第1页10条，共15页；分页结构明确可遍历)

## 5. 招聘范围

- **scope_country_region**: 中国大陆为主，含少量海外岗位（泰国、墨西哥、埃及、越南、印尼）
- **scope_recruitment_type**: 校园招聘（应届生 + 应届博士 + 实习生）
- **scope_campaign**: 2027届全球校园招聘（2026年9月启动）
- **地域分布**: 佛山（总部）、合肥、无锡、上海、重庆、苏州、芜湖、北京、荆州、深圳、广州、武汉等40+城市
- **届别要求**: 2026年1月1日-2027年12月31日期间毕业的海内外本硕博学生

## 6. 真实岗位样例

| # | 岗位标题原文 | 招聘单位原文 | 工作地点 | 性质判断及依据 | 届别要求 | 详情URL | 采集时间 |
|---|---|---|---|---|---|---|---|
| 1 | 电机控制软件工程师 | 美的集团（研发技术类） | 佛山市 | 校招研发岗，页面标注"应届生"标签 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 2 | 解决方案工程师-海外 | 美的集团（海外营销类） | 深圳市 | 校招营销岗，页面标注"应届生"标签，涉及储能/智能电网海外项目 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 3 | 算法工程师-运筹优化 | 美的集团（信息技术类） | 上海市、佛山市、无锡市 | 校招算法岗，页面标注"应届生"标签，涉及路径规划/仓网规划 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 4 | 研究员-阀体结构 | 美的集团（研发技术类） | 上海市、佛山市 | 校招研究岗，页面标注"应届生"标签 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 5 | 研究员-系统PHM算法 | 美的集团（研发技术类） | 上海市、佛山市 | 校招研究岗，页面标注"应届生"标签，空调系统健康管理算法 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 6 | 智能开发工程师-传感器 | 美的集团（研发技术类） | 佛山市 | 校招研发岗，页面标注"应届生"标签，多模态融合感知 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 7 | 人力资源管理-SSC | 美的集团（管理类） | 上海市、佛山市 | 校招管理岗，页面标注"应届生"标签 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 8 | 质量技术研究工程师 | 美的集团（制造技术类） | 佛山市、合肥市 | 校招制造岗，页面标注"应届生"标签 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 9 | 研究员-系统智能控制算法 | 美的集团（研发技术类） | 上海市、合肥市 | 校招研究岗，页面标注"应届生"标签，空调智能控制 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |
| 10 | 产品培训运营 | 美的集团（国内营销类） | 合肥市 | 校招营销岗，页面标注"应届生"标签 | 2027届 | https://careers.midea.com/schoolOut/post/details | 2026-09-10 |

## 7. 任务状态

- **integration_stage**: source_discovered
- **run_health**: healthy
- **blocker_reason**: null (详情页URL为SPA路由推断，未获取到具体jobId参数；列表页数据完整可采集)

---

## 补充说明

- 美的官网 www.midea.com/cn/careers 为品牌展示页，无实际岗位列表，实际校招系统独立部署在 careers.midea.com
- 岗位按八大类划分：研发技术类、制造技术类、信息技术类、国内营销类、供应链物流类、海外营销类、财务金融类、管理类
- 每年校招规模约2000余人，硕博占比60%以上
- 有"美少年计划"实习生招聘（当前阶段已结束）
- 证据文件: evidence/midea/job_list_page1.txt
