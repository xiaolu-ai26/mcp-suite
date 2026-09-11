# Codex 执行提示词：秋招MCP 500家企业批量采集（代码优先）

请将以下内容完整复制给Codex执行：

---

## 任务：用Python脚本批量采集企业招聘岗位，目标新增100+家企业上线

### 你的优势
你擅长写代码和跑脚本。**不要用浏览器手动逐家采集**。优先写Python脚本批量调用公开API。遇到需要浏览器渲染的就跳过，不纠缠。

### 项目信息
- 本地项目: /Users/maxzhl/Projects/mcp-suite/
- 输出目录: /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-500-mvp/codex_output/
- 生产服务器: root@114.215.188.109
- 生产jobs.json: /var/lib/mcp-suite/jobs.json
- 服务重启: ssh root@114.215.188.109 "systemctl restart mcp-suite.service"
- 健康检查: curl https://savegems.top/qiuzhao/health

### 已上线企业（不要重复采集）
腾讯、字节跳动、阿里巴巴、京东、美团、网易、美的、迈瑞、小米、中科创达、百度、滴滴、大疆、360、携程、贝壳、虎牙、58同城、得物、叠纸、莉莉丝、广联达、爱奇艺、易车、宝洁、达能、罗氏、普华永道、LVMH、阿迪达斯、快手、百威、西门子、辉瑞、中芯国际、科大讯飞、奇安信、华为、vivo、中国邮政、联通、移动、航天科工、能源建设、国家能源、机械总院、建行、中行

---

## 第一批：Workday标准API批量采集（31家，最高优先）

Workday所有企业共用同一套API模式，写一个脚本跑全部：

**API模式**: `https://{tenant}.workday.com/careers/{site}/c/results.json` 或 GraphQL端点
**已知Workday企业**:
埃森哲、阿斯利康、百事、可口可乐、亿滋、高露洁、雅诗兰黛、强生、卡夫亨氏、帝亚吉欧、保乐力加、耐克、宜家、迪士尼、微软、思科、英特尔、IBM、戴尔、惠普、赛默飞世尔、嘉吉、摩根大通、美国银行、富国银行、卡地纳健康、克罗格、家得宝、塔吉特、UPS、联邦快递

**做法**:
1. 先写脚本探测每家的Workday tenant和site名（通常是公司名小写）
2. 调用 `https://{tenant}.workday.com/careers/{site}/c/results.json?client_request_id=...&LimitingEntity=...&searchText=campus` 或GraphQL
3. 每家取前1-3条岗位，提取title/location/description/externalURL
4. 探测失败的立刻跳过，记录原因
5. 输出到 codex_output/workday_batch.json

---

## 第二批：Greenhouse标准API批量采集（3家）

Greenhouse有公开Job Board API，无需鉴权：

**API模式**: `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
**企业**:
- 英伟达 NVIDIA (board_token可能是 nvidia)
- AMD (board_token可能是 amd)
- Adobe (board_token可能是 adobe)

**做法**: 写脚本调用API，每家取1-3条，description字段直接是HTML正文。输出到 codex_output/greenhouse_batch.json

---

## 第三批：SuccessFactors/OData批量采集（5家）

**企业**: SAP、诺华、ABB、壳牌、DHL
**做法**: 探测各家的OData API端点 `https://{host}/sap/opu/odata/sap/...`，失败就跳过。

---

## 第四批：飞书招聘API批量采集

飞书招聘(*.jobs.f.mioffice.cn)有公开API：
**已知未上线飞书招聘企业**: 商汤科技(sensetime.jobs.feishu.cn)
**做法**: 参考已验证的小米/中科创达/广联达采集模式，写脚本批量调用飞书招聘API。

---

## 第五批：互联网自建站API（有entry_url）

| 企业 | 入口 | 平台 |
|---|---|---|
| 哔哩哔哩 | https://jobs.bilibili.com/campus/positions?type=3 | SPA |
| 小红书 | https://job.xiaohongshu.com/campus/position | 自建 |
| 米哈游 | https://jobs.mihoyo.com/#/campus | SPA |
| 拼多多 | https://careers.pddglobalhr.com/campus/grad | Next.js |
| OPPO | https://careers.oppo.com/university/oppo/campus/post | 自建 |
| 吉比特 | https://hr.g-bits.com/web/index.html#/post-web/post-list | SPA |

**做法**: 用浏览器开发者工具思路找XHR/API端点，写脚本调用。找不到API的跳过，不用Playwright硬渲染。

---

## 第六批：世界500强中国企业（找招聘入口+API）

国家电网、中石油、中石化、中国建筑、鸿海精密、工商银行、农业银行、中国人寿、中国平安、中国中铁、中国铁建、中信集团、中交建、华润、恒力、台积电、中海油、南方电网、山东能源、比亚迪、中国五矿、宝武钢铁、中国电建、厦门建发、浙江荣盛、中国人保、上汽集团、国药集团、中国电信、吉利、联想、物产中大、山东魏桥、中粮、盛虹、江西铜业、太平洋建设、一汽、交通银行、纬创、浙江恒逸、中国铝业、广达电脑、保利、金川

**做法**: 逐家用搜索引擎找官方校招入口，有公开API的写脚本采1-3条，没有的跳过。

---

## 统一岗位Schema（每条必须符合）

```json
{
  "job_id": "公司slug_序号",
  "job_title": "岗位名称",
  "recruitment_unit": "企业主体中文名",
  "source_name": "企业名+招聘官网",
  "source_url": "列表页URL",
  "detail_url": "详情页URL",
  "cities": ["城市"],
  "industry": "企业行业（互联网/快消/制造/医药/金融/能源/零售/科技/汽车/其他）",
  "recruitment_type": "校招|实习|社招",
  "job_category": "岗位类别",
  "education_raw": "学历原文或未披露",
  "major_raw": "专业原文或未披露",
  "graduation_year": "2027届或未披露",
  "description_raw": "职责+要求原文（必须>50字符，HTML转纯文本）",
  "deadline_text": "截止日期或未披露",
  "first_seen_at": "2026-09-10T20:00:00+08:00",
  "verified_at": "2026-09-10T20:00:00+08:00",
  "status": "open",
  "country": "中国/美国/德国等",
  "fortune_rank": 数字或null
}
```

---

## 发布流程（每采集完一批就发布）

1. 合并本批所有合格岗位到一个列表
2. SSH拉取线上live: `ssh root@114.215.188.109 "cat /var/lib/mcp-suite/jobs.json" > /tmp/live_jobs.json`
3. 去重：按detail_url去重，已存在的不重复添加
4. 合并后上传: `scp merged.json root@114.215.188.109:/var/lib/mcp-suite/jobs.json`
5. 重启: `ssh root@114.215.188.109 "systemctl restart mcp-suite.service"`
6. 验证: `curl https://savegems.top/qiuzhao/health`
7. 记录发布日志到 codex_output/publish_log.md

**重要**: 服务端有独立采集器会周期性重建jobs.json，所以每次发布前必须先拉线上live作基础，合并后再上传。

---

## 安全红线（绝对不可违反）

- 不读取/覆盖/回滚 access.sqlite3（private/目录）
- 不修改套餐(39元/200次/日)、额度、鉴权逻辑
- 不动正式库存、兑换记录、订单台账
- 不修改Nginx、其他站点
- 不绕过登录、验证码、付费限制
- 不伪造岗位或测试结果
- 阻塞企业记录原因后跳过，不硬刚

---

## 执行要求

1. **先写脚本再跑**，不要手动浏览器采集
2. **每批跑完立即发布**，不要攒着
3. **阻塞企业写入** codex_output/blocked.jsonl（企业名/原因/时间）
4. **速度优先**，单家探测超过3分钟就跳过
5. 最终报告: 新增企业数、岗位数、阻塞企业数、各批结果

立即从第一批Workday开始。

---

以上为完整提示词。
