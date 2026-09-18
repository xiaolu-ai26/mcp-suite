# RECEIPT: 外企补齐 A —— Eightfold（惠普/微软/高通/应用材料/泛林）+ Phenom（宝洁/玛氏/罗氏/BCG/ABB/飞利浦/默沙东/思科）

分支:`feat/foreign-ats-a`(基于 `feat/collector-next-3` 2b123c2,worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-ats-a`)
日期:2026-09-19 执行:DeepSeek Harness 范围:2 个平台适配器 + 配置段 + 追加式注册块 + 夹具单测 + 真实只读实测 + 部署件 + 本收据。
**未部署**:未 SSH、未碰精灵正式目录、未碰阿里云、未调飞书、未 `--apply`、未写库、未 push、未合并 main、未终止任何进程。所有真实请求只打公开免登录页面/接口,未登录、未伪造签名、未过验证码。

---

## 0. 一句话结论

**上一轮判"接不了"的 Eightfold 是请求形状问题,不是需要登录。** 惠普/微软/高通/应用材料/泛林 5 家、宝洁/玛氏/罗氏/波士顿咨询/ABB/飞利浦/默沙东/思科 8 家,**13 家 × 3 scope = 39 次实测全部 `success`/`partial`,零 `blocked`、零 `errors`,字段可用率 100%**,默认集合 948 → **961 家**。Eightfold 的公开 `/api/pcsx/search` 用**普通 HTTP(只带 UA)** 就返回 200;上一轮的 `403 Not authorized for PCSX` 来自错误的请求形状(见 §2)。Phenom 的 `/widgets` `refineSearch`/`jobDetail` 同样公开可直连。Playwright 只作为被 401/403/429 拒绝时的**兜底**,本次 39 次实测**一次都没用上**(全部 `mode=direct`)。

---

## 1. 交付物

| 文件 | 说明 |
|---|---|
| `qiuzhao/collector/p1_platform_eightfold.py` | **新适配器**:Eightfold AI 公开 careers 租户(5 家) |
| `qiuzhao/collector/p1_platform_phenom.py` | **新适配器**:Phenom People 公开 careers 租户(8 家) |
| `qiuzhao/collector/p1_platform_companies.json` | **纯追加** `eightfold`(5)+`phenom`(8)两段,111 行新增、0 行删除 |
| `qiuzhao/collector/p1_pipeline.py` | **仅追加 1 个独立注册块**(+18 行)+ `PLATFORM_MODULES`/`PLATFORM_HOST_GROUPS` 各 +2 项;既有行一字未动 |
| `tests/test_p1_platform_eightfold.py` | 11 个夹具单测 |
| `tests/test_p1_platform_phenom.py` | 12 个夹具单测 |
| `tests/fixtures/platform/eightfold_*.json`、`phenom_*.json` | 9 个录制夹具(真实公开响应裁剪,未编造任何值) |
| `tests/test_collector_next_integration.py` | 顺序断言同步(追加 2 块 + 961 家) |
| `pipeline-watch/foreign-ats-a-verify.py` | 实测运行器(可复现 §4) |
| `pipeline-watch/foreign-ats-a-probe.py` | 零网络探针(`PROBE OK`) |
| `pipeline-watch/deploy-artifacts/20260919b/` | 部署件(4 运行时文件 + SHA256SUMS + PROD-BACKUP-MANIFEST.tsv + DEPLOY-NOTES.md) |

---

## 2. Eightfold:上一轮为什么 403,这次怎么打通的

上一轮用"裸 HTTP 打 Eightfold 公开 API"得到 `403 Not authorized for PCSX` 就收工了。本次先用 Playwright 打开站长给的公开 careers 页,**监听页面自己发出的请求**,拿到它真正在打的 URL:

```
GET https://apply.hp.com/api/pcsx/search
      ?domain=hp.com&query=&location=china&start=0&sort_by=distance&filter_include_remote=1&hl=zh-CN
→ 200, {"status":200,"data":{"count":16,"positions":[ ... 10 条 ... ]}}
```

把这条 URL 原样用 `requests`(只带 UA + Referer)**重放,HTTP 200**——也就是说 403 来自上一轮请求形状不对(缺 `domain=`、打错端点等),不是浏览器/登录门槛。适配器主路径因此是直连,不再需要浏览器。

其余契约同样是从页面自身请求读出来的,**不是猜的**:

| 项 | 实测结论 |
|---|---|
| 每页条数 | 服务端固定 **10**;`num=20/50/100` 无效(仍返回 10) |
| 翻页 | `start=` 游标;`start=0→10→16`,越界返回空数组 |
| 总数 | `data.count` |
| 详情 | `GET /api/pcsx/position_details?position_id=&domain=&hl=&queried_location=` → `data.jobDescription` 全文 + `publicUrl` + `positionUserActions.applyAction.applyUrl`(官方 ATS 投递链接) |
| 发帖时间 | `postedTs`(Unix 秒) |

**实测确认的 5 家租户入口**(应用材料/泛林都有专属域名,不必用共享的 `app.eightfold.ai`):

| 公司 | host | domain | 中国条数 |
|---|---|---|---|
| 惠普 | `apply.hp.com` | `hp.com` | 16 |
| 微软 | `apply.careers.microsoft.com` | `microsoft.com` | 41 |
| 高通 | `careers.qualcomm.com` | `qualcomm.com` | 96 |
| 应用材料 | `careers.appliedmaterials.com` | `appliedmaterials.com` | 131 |
| 泛林 | `careers.lamresearch.com` | `lamresearch.com` | 42(其中 36 条地点含中国) |

> 站长给的高通官网入口没找到——**高通实际用的是 Eightfold**,`careers.qualcomm.com`(也响应 `qualcomm.eightfold.ai`),两者返回同一份数据。本轮已实测确认。

### 2.1 一个必须做的行级复核

Eightfold 的 `location=china` **在应用材料上不做严格过滤**:它返回"任何一个办公地点在中国"的岗位,所以列表里会出现 `Field Service Engineer III (C3) - N. Phoenix, AZ.` 这种 88 个地点含中国的行。适配器因此在行级再判一次地点,并兼容三种官方拼法:

- `Chongqing, Chongqing, China`
- `Jinan,CHN`(应用材料的写法)
- `Xi'an, Shaanxi, CN`(标准化写法)

`CN` 只作为独立逗号分量匹配,不会把 `Cincinnati,OH` 误判成中国(有专门单测)。

---

## 3. Phenom:契约与地区/scope 判定

上一轮存档的参数(`PGBPGCCN`/`MARSGLOBAL`/`BCG1US`/`ROCHGLOBAL`)全部有效,并且**又确认了 4 家真实 Phenom 租户**:ABB(`ABB1GLOBAL`)、飞利浦(`PHILUS`)、默沙东(`MSD1GB`,上一轮标"site 未确认")、思科(`CISCISGLOBAL`)。

| 项 | 实测结论 |
|---|---|
| 列表 | `POST /widgets` `ddoKey=refineSearch` → `refineSearch.totalHits` + `data.jobs` |
| 分页 | `from=` 游标;`size` **服务端封顶 500**(要 1000 仍给 500) |
| 详情 | `POST /widgets` `ddoKey=jobDetail`(+`jobId`/`jobSeqNo`)→ `data.job.description` 全文、`postedDate`、`postingEndDate` |

### 3.1 地区判定

`location`/`country` 过滤字段**对非中国专属站无效**(罗氏/ABB/BCG/飞利浦/默沙东/思科全返回全球列表,我试过 13 种过滤字段形态,totalHits 一个都不变)。玛氏与宝洁靠站点 locale(`zh_cn`/`en_cn`)天然只返回中国。

因此做法是:**按 `size=500` 翻页走完该租户公开列表,再用岗位自己的官方 `country`/`location` 文本判中国地区**。罗氏 3 次、ABB 5 次、BCG 2 次即可走完,远在每租户 ≤25 次预算内(§5 实测用 25 次预算跑的是"部分成功"路径,生产不限预算)。

地区覆盖 **Greater China**(大陆 + 香港 + 台湾):外企官方列表本来就是这么分区的(`Chinese Mainland - Greater China` / `Hong Kong SAR – Greater China` / `Taiwan – Greater China` / `Greater China` / `China's Mainland`),我们原样保留官方地区文本,不合并、不改写。

### 3.2 scope 映射(只用官方标签,且默认只信标题)

**踩到的真坑**:BCG 的 `subCategory` 把 `Experienced Hire, Full-time, Greater China` 也归到 `Co-op/Intern/Temporary`。若扫全字段,这条会被误判成实习。所以默认 `label_fields = ('title',)`,租户可在配置里显式放开。

- **宝洁**:标题 `(Chinese Mainland) Campus Recruiting - ...` → 校招;`2027 P&G Internship` → 实习。
- **罗氏**:官方 `subCategory` 就是项目标签,配置里**精确值映射**——`Internship` → 实习,`Development Program` → 校招(岗位正文原文 *"looking for highly motivated and exceptional university graduates at the start of their careers to join the StartUp Roche Pharma China Development Program"*)。
- **ABB**:6 条 `Intern Student`/标题 Intern → 实习;`Power U 培训生`/`校园招聘`/`校招` → 校招。
- **飞利浦**:`Internship & Apprenticeship` / `EE_INTERN`,标题带 Intern → 实习 14 条。
- **BCG**:标题含 `Campus` → 校招 2 条;`intern` 0 条(那条 Co-op 归类的 Experienced Hire 正确地留在社招)。
- **玛氏/思科**:中国区当期没有任何带校招/实习官方标签的岗位 → 0 条(如实返回空,不硬凑)。
- 英文关键词用**词边界**匹配:`intern` 不会命中 `internal`/`international`(默沙东的 `Manager, Internal Communications` 因此正确留在社招)。

数据规则:届别 `cohort_raw` 一律留空(不推断);`deadline_raw` 只在官方 `postingEndDate` 有值时写;`published_at` 取官方 `postedDate`。

---

## 4. 实测结果(13 家 × 3 scope = 39 次,真实只读)

运行方式:走**生产同一条路径** `p1_pipeline.collect_process`(每公司×scope 一个子进程),
`QIUZHAO_PLATFORM_REQUEST_BUDGET=25`、`QIUZHAO_PLATFORM_REQUEST_INTERVAL=2.0`、
`QIUZHAO_PLATFORM_MAX_PAGE_LOADS=25`(站长口径:每租户 ≤25 次页面加载、间隔 ≥2 秒)。
报告:`/Volumes/臭垃圾桶/生财MCP/_research/foreign-ats-a/verify-a/verify-report.json`(含每条记录与字段明细)。

**总计 359 条;`success` 25 次 / `partial` 14 次 / `blocked` 0 次 / `errors` 0 条;**
39 次全部 `mode=direct`(Playwright 兜底一次未触发),39 次全部 `requests_used ≤ 25`(无超预算)。
`partial` 全部是"预算 25 用完、大租户详情没拉完"这一种原因(生产默认不限预算)。

| 平台 | 公司 | scope | status | complete | 条数 | 期望 | 翻页耗尽 | 详情完整 | 请求/上限 | 用时 |
|---|---|---|---|---|---|---|---|---|---|---|
| Eightfold | 应用材料 | campus | success | 是 | 3 | 3 | 是 | 是 | 17/25 | 46.3s |
| Eightfold | 应用材料 | intern | success | 是 | 3 | 3 | 是 | 是 | 17/25 | 48.5s |
| Eightfold | 应用材料 | social | partial | 否 | 11 | 125 | 否 | 否 | 25/25 | 66.6s |
| Eightfold | 微软 | campus | success | 是 | 0 | 0 | 是 | 是 | 5/25 | 16.3s |
| Eightfold | 微软 | intern | success | 是 | 0 | 0 | 是 | 是 | 5/25 | 15.7s |
| Eightfold | 微软 | social | partial | 否 | 20 | 41 | 否 | 否 | 25/25 | 70.9s |
| Eightfold | 惠普 | campus | success | 是 | 0 | 0 | 是 | 是 | 2/25 | 11.3s |
| Eightfold | 惠普 | intern | success | 是 | 1 | 1 | 是 | 是 | 3/25 | 9.5s |
| Eightfold | 惠普 | social | success | 是 | 15 | 15 | 是 | 是 | 17/25 | 47.2s |
| Eightfold | 泛林 | campus | success | 是 | 0 | 0 | 是 | 是 | 5/25 | 16.8s |
| Eightfold | 泛林 | intern | success | 是 | 0 | 0 | 是 | 是 | 5/25 | 16.5s |
| Eightfold | 泛林 | social | partial | 否 | 20 | 36 | 否 | 否 | 25/25 | 70.1s |
| Eightfold | 高通 | campus | success | 是 | 1 | 1 | 是 | 是 | 11/25 | 34.6s |
| Eightfold | 高通 | intern | partial | 否 | 15 | 18 | 否 | 否 | 25/25 | 85.1s |
| Eightfold | 高通 | social | partial | 否 | 15 | 77 | 否 | 否 | 25/25 | 75.7s |
| Phenom | ABB | campus | partial | 否 | 20 | 41 | 否 | 否 | 25/25 | 72.4s |
| Phenom | ABB | intern | success | 是 | 6 | 6 | 是 | 是 | 11/25 | 37.4s |
| Phenom | ABB | social | partial | 否 | 20 | 338 | 否 | 否 | 25/25 | 74.2s |
| Phenom | 宝洁 | campus | success | 是 | 12 | 12 | 是 | 是 | 13/25 | 37.6s |
| Phenom | 宝洁 | intern | success | 是 | 4 | 4 | 是 | 是 | 5/25 | 15.2s |
| Phenom | 宝洁 | social | partial | 否 | 24 | 40 | 否 | 否 | 25/25 | 64.0s |
| Phenom | 思科 | campus | success | 是 | 0 | 0 | 是 | 是 | 3/25 | 13.3s |
| Phenom | 思科 | intern | success | 是 | 0 | 0 | 是 | 是 | 3/25 | 12.0s |
| Phenom | 思科 | social | partial | 否 | 22 | 50 | 否 | 否 | 25/25 | 71.3s |
| Phenom | 波士顿咨询 | campus | success | 是 | 2 | 2 | 是 | 是 | 4/25 | 14.8s |
| Phenom | 波士顿咨询 | intern | success | 是 | 0 | 0 | 是 | 是 | 2/25 | 9.4s |
| Phenom | 波士顿咨询 | social | success | 是 | 9 | 9 | 是 | 是 | 11/25 | 32.8s |
| Phenom | 玛氏 | campus | success | 是 | 0 | 0 | 是 | 是 | 1/25 | 5.1s |
| Phenom | 玛氏 | intern | success | 是 | 0 | 0 | 是 | 是 | 1/25 | 4.8s |
| Phenom | 玛氏 | social | partial | 否 | 24 | 118 | 否 | 否 | 25/25 | 69.1s |
| Phenom | 罗氏 | campus | success | 是 | 7 | 7 | 是 | 是 | 10/25 | 30.4s |
| Phenom | 罗氏 | intern | partial | 否 | 22 | 48 | 否 | 否 | 25/25 | 71.5s |
| Phenom | 罗氏 | social | partial | 否 | 22 | 214 | 否 | 否 | 25/25 | 73.7s |
| Phenom | 飞利浦 | campus | success | 是 | 0 | 0 | 是 | 是 | 2/25 | 12.0s |
| Phenom | 飞利浦 | intern | success | 是 | 14 | 14 | 是 | 是 | 16/25 | 47.6s |
| Phenom | 飞利浦 | social | partial | 否 | 23 | 145 | 否 | 否 | 25/25 | 73.7s |
| Phenom | 默沙东 | campus | success | 是 | 0 | 0 | 是 | 是 | 2/25 | 8.1s |
| Phenom | 默沙东 | intern | success | 是 | 1 | 1 | 是 | 是 | 3/25 | 10.8s |
| Phenom | 默沙东 | social | partial | 否 | 23 | 128 | 否 | 否 | 25/25 | 67.5s |

平台分组： {'Eightfold': ['应用材料', '微软', '惠普', '泛林', '高通'], 'Phenom': ['ABB', '宝洁', '思科', '波士顿咨询', '玛氏', '罗氏', '飞利浦', '默沙东']}
各 scope 合计： {'campus': 45, 'intern': 66, 'social': 248} 总条数 359

| 平台 | 公司 | scope | 条数 | published_at | location | cities | detail_url | application_url | scope_evidence | 描述中位长 | 描述最短 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Eightfold | 应用材料 | campus | 3 | 100% | 100% | 100% | 100% | 100% | 100% | 4503 | 3308 |
| Eightfold | 应用材料 | intern | 3 | 100% | 100% | 100% | 100% | 100% | 100% | 2374 | 2368 |
| Eightfold | 应用材料 | social | 11 | 100% | 100% | 100% | 100% | 100% | 100% | 5313 | 2550 |
| Eightfold | 微软 | social | 20 | 100% | 100% | 100% | 100% | 100% | 100% | 5348 | 3189 |
| Eightfold | 惠普 | intern | 1 | 100% | 100% | 100% | 100% | 100% | 100% | 1628 | 1628 |
| Eightfold | 惠普 | social | 15 | 100% | 100% | 100% | 100% | 100% | 100% | 4434 | 1317 |
| Eightfold | 泛林 | social | 20 | 100% | 100% | 100% | 100% | 100% | 100% | 4690 | 4430 |
| Eightfold | 高通 | campus | 1 | 100% | 100% | 100% | 100% | 100% | 100% | 5414 | 5414 |
| Eightfold | 高通 | intern | 15 | 100% | 100% | 100% | 100% | 100% | 100% | 2579 | 2335 |
| Eightfold | 高通 | social | 15 | 100% | 100% | 100% | 100% | 100% | 100% | 5044 | 3718 |
| Phenom | ABB | campus | 20 | 100% | 100% | 100% | 100% | 100% | 100% | 1930 | 1260 |
| Phenom | ABB | intern | 6 | 100% | 100% | 100% | 100% | 100% | 100% | 2075 | 775 |
| Phenom | ABB | social | 20 | 100% | 100% | 100% | 100% | 100% | 100% | 3482 | 1120 |
| Phenom | 宝洁 | campus | 12 | 100% | 100% | 100% | 100% | 100% | 100% | 3208 | 2407 |
| Phenom | 宝洁 | intern | 4 | 100% | 100% | 100% | 100% | 100% | 100% | 2593 | 2483 |
| Phenom | 宝洁 | social | 24 | 100% | 100% | 100% | 100% | 100% | 100% | 1688 | 539 |
| Phenom | 思科 | social | 22 | 100% | 100% | 100% | 100% | 100% | 100% | 4940 | 3001 |
| Phenom | 波士顿咨询 | campus | 2 | 100% | 100% | 100% | 100% | 100% | 100% | 2806 | 2739 |
| Phenom | 波士顿咨询 | social | 9 | 100% | 100% | 100% | 100% | 100% | 100% | 6123 | 3223 |
| Phenom | 玛氏 | social | 24 | 100% | 100% | 100% | 100% | 100% | 100% | 671 | 283 |
| Phenom | 罗氏 | campus | 7 | 100% | 100% | 100% | 100% | 100% | 100% | 4867 | 4481 |
| Phenom | 罗氏 | intern | 22 | 100% | 100% | 100% | 100% | 100% | 100% | 1519 | 1284 |
| Phenom | 罗氏 | social | 22 | 100% | 100% | 100% | 100% | 100% | 100% | 3427 | 1551 |
| Phenom | 飞利浦 | intern | 14 | 100% | 100% | 100% | 100% | 100% | 100% | 840 | 358 |
| Phenom | 飞利浦 | social | 23 | 100% | 100% | 100% | 100% | 100% | 100% | 1322 | 236 |
| Phenom | 默沙东 | intern | 1 | 100% | 100% | 100% | 100% | 100% | 100% | 2935 | 2935 |
| Phenom | 默沙东 | social | 23 | 100% | 100% | 100% | 100% | 100% | 100% | 3385 | 1855 |



### 4.1 字段可用率(上表已逐家列出,此处给结论)

| 字段 | 可用率 | 说明 |
|---|---|---|
| `published_at` | **100%** | 官方 `postedTs` / `postedDate`,无则不写(实测每家都有) |
| `deadline_raw` | 有才写 | Phenom `postingEndDate`(宝洁中国区当前为空,罗氏 StartUp 项目有 `2026-10-12`);Eightfold 五个租户官方均不发布截止日,一律留空 |
| `cohort_raw` | **0%(故意)** | 外企这些岗位不发布届别,不推断;届别信息只保留在官方标题原文里(如宝洁 `2027 P&G Internship`) |
| `location` / `cities` | **100%** | 官方地点原文 + 归一化城市 |
| `detail_url` / `application_url` | **100%** | `detail_url` = 官方公开详情页;`application_url` = 岗位自带的官方 ATS 投递链接(如 `hp.wd5.myworkdayjobs.com/...`、`roche.wd3.myworkdayjobs.com/...`) |
| `scope_evidence` | **100%** | 记录该岗位被判成该 scope 的官方标签原文 |
| `description_raw` | **100%** | 官方详情正文;中位长度 671–6123 字符,最短 236 字符(玛氏部分岗位官方正文本身很短,未截断) |

### 4.2 逐家结论

| 公司 | 平台 | 中国区官方岗位 | 校招 | 实习 | 社招 | 结论 |
|---|---|---|---|---|---|---|
| 惠普 | Eightfold | 16 | 0 | 1 | 15 | ✅ 接入(3 scope 全 complete) |
| 微软 | Eightfold | 41 | 0 | 0 | 41 | ✅ 接入(中国区当期无校招/实习标签岗位,如实 0) |
| 高通 | Eightfold | 96 | 1 | 18 | 77 | ✅ 接入 |
| 应用材料 | Eightfold | 131 | 3 | 3 | 125 | ✅ 接入 |
| 泛林 | Eightfold | 42(36 含中国) | 0 | 0 | 36 | ✅ 接入 |
| 宝洁 | Phenom | 56 | 12 | 4 | 40 | ✅ 接入(校招/实习全 complete) |
| 玛氏 | Phenom | 118 | 0 | 0 | 118 | ✅ 接入(当期无校招/实习标签岗位) |
| 罗氏 | Phenom | 267 | 7 | 48 | 212 | ✅ 接入(含 StartUp China 毕业生项目) |
| 波士顿咨询 | Phenom | 11 | 2 | 0 | 9 | ✅ 接入(3 scope 全 complete) |
| ABB | Phenom | 385 | 41 | 6 | 338 | ✅ 接入 |
| 飞利浦 | Phenom | 159 | 0 | 14 | 145 | ✅ 接入 |
| 默沙东 | Phenom | 127 | 0 | 1 | 126 | ✅ 接入 |
| 思科 | Phenom | 45 | 0 | 0 | 45 | ✅ 接入 |

> 中国区口径 = Greater China(大陆 + 香港 + 台湾),按岗位官方地区文本判定。"校招/实习"列是该 scope 的**期望条数**,不是本批 25 次预算下的采集条数。

### 4.3 写入 `p1_platform_companies.json` 的条件核对

任务条件:**status success/partial 且中国地区 ≥1 条**。13 家全部满足(每家至少一个 scope 拿到 ≥1 条中国岗位,且 39 次实测无一次 `blocked`),故 13 行配置全部保留,无一家被剔除。

---

## 5. 单测与回归

| 项 | 结果 |
|---|---|
| 新增夹具单测 | Eightfold **11 个** + Phenom **12 个** = 23 个,**全绿** |
| 集成顺序断言 | 同步新增 2 块 + 961 家,`test_collector_next_integration.py` 全绿 |
| 本分支 `pytest tests/` | **3 failed / 521 passed / 55 skipped** |
| 基线 `feat/collector-next-3` `pytest tests/` | **3 failed / 498 passed / 55 skipped** |
| 失败清单对比 | **完全相同 3 条既有失败**:`test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts`;**未新增任何失败** |
| 零网络探针 | `pipeline-watch/foreign-ats-a-probe.py` → `PROBE OK {"default_total":961,...}` |

夹具测试覆盖到的**真实缺陷**(都是先写测试才暴露出来的):

1. **`evidence_files` 不能用目录 glob**。原来用 `output_dir.glob('*')` 收证据,会把生产链路提前建好的 **0 字节 `adapter.log`** 也算进去,`validate_result` 以"证据文件为空"整家公司判 `blocked`。改成只登记适配器真正写出的文件,并有专门单测复现 `adapter.log` 存在的场景。
2. **配置段的 `_note` 被当成公司名**。`_load_companies()` 把文档键 `_note` 当租户注册,`REGISTRY` 里会多出一个"公司名 = 一整段说明文字"的条目。已跳过 `_` 前缀键,并在集成测试的配置解析里同步跳过。
3. **空集成功缺 `scope_evidence`**。中国区确实没有该 scope 岗位时,适配器返回"成功的空读",但 `complete=True` 要求 `scope_evidence`,缺了会被判 `blocked`(把"这家没有校招岗位"误报成"这家采不了")。已补上官方列表请求作为证据。
4. **预算耗尽时的状态语义**。列表已确认岗位、但预算在拉详情前用尽,原来落到 `blocked`;现在正确报 `partial`(未读完 ≠ 源已死)。
5. **Eightfold 用 `name`、Phenom 用 `title`**。两个平台对"标题"的字段名不同,统一分类器时踩到,已各自设默认标签字段并加断言。

---

## 6. 部署件 `pipeline-watch/deploy-artifacts/20260919b/`

叠在 **20260918k** 之上,一步覆盖 **4 个运行时文件**:

| 文件 | 目标 | 类型 | 部署前(= k 包内同名文件) |
|---|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/` | 覆盖 | `ff96be4d772847a0…` |
| `p1_platform_companies.json` | `qiuzhao/collector/` | 覆盖 | `bf592f62cd644a20…` |
| `p1_platform_eightfold.py` | `qiuzhao/collector/` | **新增** | 不存在 |
| `p1_platform_phenom.py` | `qiuzhao/collector/` | **新增** | 不存在 |

- `shasum -a 256 -c SHA256SUMS.txt` → 4/4 OK;与分支源码**逐字节一致**(`cmp`)。
- **不含 `windows_collector.py`**(必须以精灵现役版为准,main 版末尾调 `lark_sync_index` 而精灵没有该模块,整文件覆盖会炸);`run.py` 未改。
- **不新增依赖**:主路径只用 `requests`;Playwright 仅兜底惰性导入,精灵已装 `chromium-1187`。
- 详细叠加说明见 `DEPLOY-NOTES.md`。

### 6.1 冻结后复跑(证明实测结论对应最终代码)

实测跑到中途对两个适配器做过一处**只影响提示文案**的收紧(空集提示增加 `and not request_budget_exhausted` 条件)。为排除"实测跑的不是最终代码",冻结后重跑惠普三 scope,结果与实测完全一致:

| scope | 冻结前 | 冻结后 |
|---|---|---|
| campus | success / complete / 0 条 / 2 请求 | success / complete / 0 条 / 2 请求 |
| intern | success / complete / 1 条 / 3 请求 | success / complete / 1 条 / 3 请求 |
| social | success / complete / 15 条 / 17 请求 | success / complete / 15 条 / 17 请求 |

---

## 7. 这一轮**没有**解决的

- **不是所有外企都在 Eightfold/Phenom 上**。上一轮判"接不了"的名单里,苹果/亚马逊/谷歌/麦肯锡/高盛/贝恩/ASML/大陆/麦当劳是自建站(无第三方 ATS);阿迪达斯/雅诗兰黛/戴尔/3M 的 51job 页是营销页(无岗位锚点);卡特彼勒/瑞银/宝马是 Cloudflare/WAF 硬拦;诺华入口带登录参数(不绕过)。这些与 ATS 适配器无关,需要各自的专用方案。
- **Avature / iCIMS / ORC / Tupu360 / 仟寻 MoSeeker 五个适配器仍未做**(不在本批"外企补齐 A"范围内)。
- **生产默认不限预算**,所以线上会走完整 listing + 全部详情;本批实测用的是 25 次预算,大租户只跑到 `partial`。首次上线后应按 `DEPLOY-NOTES.md` 的观察项核对 13 家线上真实表现(尤其 ABB 385 条、罗氏 267 条两个大租户的耗时)。
- **未验证精灵上的实际运行**:本批未 SSH、未部署,Playwright 兜底路径在精灵上只做过最小启动验证(此前批次做过),本批**没有**在精灵上跑过 `headless` 分支(39 次实测全部 `mode=direct`,兜底只有夹具单测覆盖)。

---

## 8. 硬约束遵守情况

| 约束 | 状态 |
|---|---|
| 不部署 / 不覆盖精灵正式目录 | ✅ 未 SSH,未碰 `C:\mcp-suite-collector` |
| 不碰阿里云 | ✅ 无任何服务器操作 |
| 不调写飞书生产 Base 的接口 | ✅ 未调飞书任何接口 |
| 不读取/打印任何令牌 | ✅ 全程无令牌参与 |
| 不登录 / 不绕过验证码 / 不签名伪造 | ✅ 只打公开免登录页面自身发出的 URL;无登录、无打码、无签名 |
| 不 `--apply` / 不写库 | ✅ 实测只写 `/Volumes/臭垃圾桶/生财MCP/_research/foreign-ats-a/verify-a/` 与临时目录 |
| 不 push / 不合并 main | ✅ 只在 `feat/foreign-ats-a` 提交 |
| 不 `git stash` | ✅ 未使用 |
| 绝对不终止任何进程 | ✅ 全程未 kill 任何进程 |
| 每租户 ≤25 次页面加载、间隔 ≥2 秒 | ✅ 实测用 `BUDGET=25`/`INTERVAL=2.0`;39 次全部 ≤25 请求,记录 0 次超预算 |
| `p1_pipeline.py` 只追加独立注册块 | ✅ +18 行纯追加,另按任务要求把 2 个新模块加入 `PLATFORM_MODULES`/`PLATFORM_HOST_GROUPS` |
| 产物写外接盘 | ✅ worktree、实测报告、收据均在 `/Volumes/臭垃圾桶/` |
| 外接盘 `._*` 忽略 | ✅ 未提交任何 `._*` |
