# 腾讯校招详情补采 — API 探测与采集记录

时间：2026-09-10 17:15–17:25 (UTC+8)
范围：staging/tencent_pending/jobs.json 共 814 条

## 1. API 端点探测

### 已知列表接口（staging 已使用）
- POST https://join.qq.com/api/v1/position/searchPosition
  - body: {"pageIndex":1,"pageSize":N}
  - 返回 positionList（含 postId / projectName / workCities）

### 详情接口（本次发现）
- GET https://join.qq.com/api/v1/jobDetails/getJobDetailsByPostId?postId=<postId>
  - Referer: https://join.qq.com/post_detail.html?postid=<postId>
  - 返回字段：postId, title, desc(职责), request(要求), topicDetail/topicRequirement(青云计划课题),
    graduateBonus/internBonus(加分项), projectName, recruitType, recruitLabelName,
    workCityList, intentionBGDList(事业群)
  - 探测过程：post_detail.html 为 SPA(2KB壳)，静态引用
    cdn.multilingualres.hr.tencent.com/joinqq/static2/js/p_zh-cn_post_detail.build.js (778KB)，
    从该 bundle 中 grep 出 `url: '/api/v1/jobDetails/getJobDetailsByPostId'`。
  - 排除：POST 该路径返回 405；postId 需大写 camelCase（小写 postid 返回 400 "缺少请求的参数"）。

### recruitType 映射
- recruitType=1 → 校招（projectName=应届毕业生 / 青云计划-应届生）
- recruitType=2 → 实习（projectName=应届实习 / 青云计划-实习生 / 日常实习 / 项目实习生）
- 最终：校招 382，实习 432，与任务预估一致。

## 2. 采集执行
- 脚本：collect_details.py（urllib，0.35s 间隔，3 次重试，断点续跑）
- 结果：814/814 成功，0 失败，0 限流/验证码
- 原始缓存：details_cache.json（814 条完整 API 返回）
- 采集日志：collect_details.log

## 3. 正文提取口径
- 普通岗：desc(职责) + request(要求) + graduateBonus/internBonus(加分项)
- 青云计划岗（539 条 desc/request 为空）：topicDetail(课题描述) + topicRequirement(课题要求)
- 无伪造：major_requirements_raw 腾讯 API 不提供 → 留空；education_raw 仅从要求正文正则提取最低学历门槛（博士29/硕士426/本科92/留空267）

## 4. 输出
- batch_tencent.json：814 条合格集（有真实正文，最短 94 字符）
- batch_tencent_incomplete.jsonl：0 条（本次无未取到详情记录）
- 香港/含香港岗 13 条 → overseas_flag=true, region=overseas
- 行业标签：industry="互联网/社交游戏"
- deadline：API 未披露 → deadline_type="招满即止"
