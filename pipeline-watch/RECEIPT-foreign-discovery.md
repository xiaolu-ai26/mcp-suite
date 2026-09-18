# RECEIPT: 外企"找全"——可重复的外资/合资企业发现管线(20260919d)

分支:`feat/foreign-discovery`(基于 `feat/collector-next-3`,worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery`)
日期:2026-09-19 执行:DeepSeek Harness 范围:公开名单发现 + 平台解析 + 能加一行的实测加行 + CSV 接收工具 + 单测 + 部署件。
**未部署**:未 SSH、未碰阿里云、未写飞书生产 Base、未登录任何站点、未绕过验证码/签名、未 push、未合并 main、未终止任何进程。全部外呼都是公开 GET,遵守 ≥2s 间隔与每来源请求上限。

---

## 0. 一句话结论

外企全景 **732 家**(目标 ≥600 达成),其中 **599 家尚未接入**;本轮按 SOP 实测后**净增 16 家**写入配置——**未达到任务书 ≥80 家的目标**,差距来自"能加一行"的平台在外企里的真实分布(见 §6 原因分布,主因:51job 微站改版成 JS 渲染、Moka/北森租户大量 404/WAF、大外企多用 Eightfold/Phenom/tupu360/自建等尚无适配器的系统)。**企查查这条路的合规走法已经变成可执行工具**:站长按 §1 导出 CSV,`tools/ingest_company_csv.py` 直接吃。

---

## 1. 站长怎么配合:企查查/天眼查 VIP 导出 5 步

我们不爬企查查(需登录 + 付费导出 + 条款禁止抓取),走"站长自己导出、交给我们"的合规路径。

**第 1 步:登录站长自己的企查查 VIP 账号**(我们全程不碰账号)。

**第 2 步:用「高级搜索」按下面条件筛**
| 维度 | 建议取值 | 说明 |
|---|---|---|
| 企业类型 | 外商投资 / 外商独资 / 中外合资 / 中外合作 / 港澳台投资 | 多选;这是外企口径的核心 |
| 登记状态 | 存续 / 在业 / 开业 | 注销、吊销、迁出不要 |
| 参保人数 | ≥200 | 低于 200 人的外资小微基本不办校招;想放宽就导出 ≥50,我们在入库时再筛 |
| 行业(白名单) | 制造业、信息传输/软件、金融业、科学研究和技术服务、批发零售、医药、汽车、化工、电气机械、商务服务 | 与校招岗位供给相关 |
| 地区 | 上海、北京、深圳、广州、苏州、杭州、成都、武汉、南京、天津、西安、重庆 | 有校招需求的外企集中地 |
| 成立年限 | ≥3 年 | 新设公司通常不校招 |

**第 3 步:导出 CSV**(UTF-8 带 BOM 最好;如果不确定编码,直接给原文件也行,我们用 `utf-8-sig` 兜底)。

**第 4 步:把 CSV 丢给我们**,并附一句"这批的筛选条件是什么"(方便我们在收据里记录口径)。

**第 5 步:我们跑**
```
python tools/ingest_company_csv.py --input <你的导出.csv> \
    --out pipeline-watch/foreign-imported.json \
    --existing pipeline-watch/foreign-universe.json --min-insured 200
```
输出:规范化后的公司记录 + 被拒行及原因(非外资类型 / 已注销 / 参保不足 / 缺公司名)+ 与现有 732 家全景的重复标记。之后进入和本轮一样的解析流程(找校招入口 → 识别招聘系统 → 能加一行的实测加行)。

### 我们接收的 CSV 列规范
必需一列(任一即可):`公司名称` / `企业名称` / `company` / `company_name`。
建议列(有就带,没有不影响):`统一社会信用代码`、`企业类型`、`登记状态`、`参保人数`、`行业`、`省份`、`城市`、`法定代表人`、`成立日期`、`注册资本`、`注册地址`、`英文名`。
**列顺序无所谓,列名中英文都认**;任何额外列会原样保留在 `extra` 字段里不丢。

---

## 2. 交付物

| 文件 | 说明 |
|---|---|
| `pipeline-watch/foreign-universe.json` | 外企全景 **732 家**(中英文名/国别/行业/来源/是否已在配置/招聘系统) |
| `pipeline-watch/foreign-backlog-by-ats.json` | 待接清单,按招聘系统分桶(599 家未接入) |
| `pipeline-watch/foreign-universe-build.py` | 全景生成器(可重复跑) |
| `pipeline-watch/foreign-backlog-build.py` | 待接清单生成器 |
| `pipeline-watch/foreign-entry-probe.py` | 招聘入口解析器(每家 ≤4 请求,实测用到 1) |
| `pipeline-watch/foreign-51job-entry.py` | 51job 微站职位页定位器(找 `job.html` 这类真职位页) |
| `pipeline-watch/foreign-workday-probe.py` / `foreign-workday-http.py` | Workday 租户发现(DNS 会被通配符污染,必须 HTTP 复核) |
| `pipeline-watch/foreign-discovery-verify.py` | 平台实测运行器(每租户 ≤15 请求、请求间隔 ≥2s、租户间隔 ≥2.2s) |
| `tools/ingest_company_csv.py` | **站长 CSV 接收器**(规范化 → 过滤 → 去重 → 标记已存在) |
| `tests/test_foreign_discovery.py` + `tests/fixtures/foreign/sample_export_20.csv` | 11 个单测(20 行假 CSV 接收/去重/域名→平台识别) |
| `qiuzhao/collector/p1_platform_companies.json` | 唯一改动的既有文件:**净增 16 行** |
| `pipeline-watch/deploy-artifacts/20260919d/` | 部署件(只有新版 `p1_platform_companies.json` + SHA256SUMS) |
| `pipeline-watch/foreign-discovery-targets*.json` | 三轮实测的目标清单(可复现) |

`p1_pipeline.py` **一字未改**;没有改任何既有适配器。

---

## 3. 各来源贡献家数

| # | 来源 | 只读请求 | 抓到 | 进入全景(去重后新增) |
|---|---|---|---|---|
| ① | Top Employers Institute「中国杰出雇主」2025 认证名单(两页:1–100 / 101–156) | 2 | 142 家 | ~99 |
| ② | Universum 中国最具吸引力雇主 | 0 | **未取得** | 0 |
| ③ | 上海/北京/苏州/深圳/广州 跨国公司地区总部/研发中心名单 | 3 | 新闻页只报总数不列名单;深圳页 SSL `BAD_ECPOINT` 失败 | ~0 |
| ④ | 商会会员名录(AmCham / 欧盟商会 / AHK / 日本商会 / 英国商会) | 0 | **未取得**(名录页需登录或 JS 渲染) | 0 |
| ⑤ | 《财富》世界 500 强在华企业 | 0 | **未取得**(只有榜单 PDF/新闻,无"在华"名单) | 0 |
| ⑥ | 牛客校招日程「外企」标签(id=2834) | 1 | 页面内嵌仅 75 家当页公司,无外企专区 API | 0 |
| ⑦ | 闲鱼表(Base `REDACTED` / `tblMKWxJGIPhcDbw`,只读,lark-cli) | 4 | 7801 行 → **571 行外企/合资** | ~33(122 行合资记录此前未被消费) |
| — | 上轮 `foreign-companies-discovery.json`(分支 `feat/foreign-companies`) | 0 | 443 家 | 443(基数) |
| — | 招聘入口解析(entry-probe,对 106 家未识别公司) | 103 | 29 家识别出系统 | 见 §5 |
| — | 51job 职位页定位(21 个微站) | 56 | 5 个站找到公开发布页 | 2(其余 JS 渲染) |

**合计全景 732 家**(443 基数 + 闲鱼表新增合资行 + 杰出雇主 142 家去重后并入)。

> ②④⑤ 没拿到不是"没找",而是这几个来源在公开侧确实没有一个可机读的完整名单:Universum 只在新闻稿里放前 10;商会名录要会员登录;财富 500 强是全球榜、没有"在华企业"子榜。**建议**:若站长有 AmCham/欧盟商会的会员账号,用同样的 CSV 口径导出会员名册交给我们,收益比继续在公开侧刨更大。

---

## 4. 净增清单(本轮实测通过、已写入配置的 16 家)

判定标准(任务书口径):`status = success|partial` 且中国地区 **≥1 条**;每租户 ≤15 请求;请求间隔 ≥2s。

| # | 公司 | 平台 | 配置 key | 采集条数 | 状态 | 备注 |
|---|---|---|---|---|---|---|
| 1 | 溢达 | Moka | `REDACTED` | 1 | success | 2027 中国管理培训生 |
| 2 | 德州仪器-补招专场 | Moka | `ti/143986` | 11/68 | partial | 预算 15 请求所限,列表已穷尽 |
| 3 | 嘉实基金 | Moka | `REDACTED` | 12/22 | partial | 2027 届校招多岗 |
| 4 | 药明生物 | Moka | `wuxibiologics/98698` | 12/35 | partial | 校园体验官系列 |
| 5 | 深圳方正微电子 | 北森 | `founderic` | 33 | success | 分类映射完整 |
| 6 | 一汽大众 | 大易 | `REDACTED` | 13/14 | partial | 2027 校招多岗 |
| 7 | 宝时得集团 | 大易 | `REDACTED` | 13/14 | partial | 2027 应届生多岗 |
| 8 | 永赢基金 | 大易 | `REDACTED` | 14/15 | partial | 挑战赛/研究员 |
| 9 | 万事达卡 | Workday | `mastercard/wd1/Campus` | 4 | success | Launch Graduate Program 2027(北京/上海) |
| 10 | 托克 | Workday | `trafigura/wd3/TrafiguraCareerSite` | 1 | success | China Commodity Trading Graduate Programme |
| 11 | ENGEL | 51job | `engel2027` | 1 | success | 注塑机方向;**标题取自页面按钮文本,质量待观察** |
| 12 | 德乐 | 51job | `Doehler2027` | 1 | success | 同上 |
| 13 | 科思创 | 51job | `Covestro2027` | 1 | success | 同上 |
| 14 | 英格索兰 | 51job | `IR2027` | 1 | success | 标题为岗位要求片段 |
| 15 | 泰科电子 | 51job | `te` | 1 | success | 标题"投递苏州" |
| 16 | NSK | 51job | `nskchina` | 1 | success | 需把 URL 指向 `job.html`(索引页无公开投递锚点) |

配置行数变化:beisen 478→479、moka 317→321、dayee 7→10、job51 1→7、workday 10→12;feishu/successfactors 不变。**默认集合 948 → 964 家**(不重名、无既有模块被顶替)。

**质量提醒**:第 11–16 行(51job)每站只解析出 1 条,标题多为页面按钮/说明文本,建议站长抽查后再决定是否保留;第 1–10 行(Moka/北森/大易/Workday)是正常岗位记录。

---

## 5. 按系统分的待接 backlog(599 家未接入)

完整数据:`pipeline-watch/foreign-backlog-by-ats.json`(每行带公司中英文名、国别、行业、官方入口 URL、tenant key、来源)。

**已有适配器、加一行即可(87 家)** —— 但需要先补 tenant key 或解决 WAF:

| 平台 | 家数 | 卡在哪 |
|---|---|---|
| 前程无忧(非 campus 微站) | 32 | 适配器只支持 `campus.51job.com/<slug>/`;这批是 `xyz/xym/young/jobs/meta.51job.com` 等其它产品线,需要扩适配器 |
| 北森 | 22 | universe 里的入口多数是 `m.zhiye.com` 分享页或已失效租户;实测 10 家里 6 家 PortalId 缺失(WAF) |
| Moka | 12 | 入口多为社招门户或旧 siteId;实测 7 家里 4 家 404、1 家 WAF 挑战 |
| 51job | 6 | 微站首页已无公开投递锚点(JS 渲染),需先定位职位子页 |
| Workday | 5 | 租户/site 组合待确认(猜测租户名不命中) |
| 大易 | 4 | 需要先拿到 `SU` hash(部分入口只有首页) |
| 飞书招聘 | 3 | 需要 `tenant_names` 与门户 URL 的官方验证 |
| SuccessFactors | 3 | 入口不是 CSB 站点(jobs2web/自建),需逐个确认 |

**需要新适配器(512 家)** —— 其中任务点名的四家由另两个执行者负责:

| 平台 | 家数 |
|---|---|
| 未识别 / 其他 / 本地招聘(tcrcsc 太仓企业页、微信公众号文章) | 491 |
| 智联 7、tupu360 4、moseeker 2、SmartRecruiters 2、Avature 1、Taleo 1、ajinga 1、牛客 1、BOSS 1、猎聘 1 | 21 |

> 注:Eightfold(BCG)、Phenom(宝洁)、Avature(彭博)、iCIMS(ZS 致盛)、ORC 的确认结果已写进 backlog 对应桶,`adapter_ready=false`,等适配器落地后可直接加行。
> `tupu360` 是本次新发现的高价值平台:**14 家外企**在用(雀巢、太太乐、奥托立夫、舍弗勒、路易威登、科赴、德昌电机、茵梦达、宝马、Google、IQVIA、强生、礼来、博世华域转向),建议优先做。

---

## 6. 接不了的原因分布(实测 80 次运行、248 个请求)

| 原因 | 次数 | 说明 |
|---|---|---|
| 51job 微站无公开投递锚点 | 17 | 站点改版为 JS 渲染,首页/职位页都拿不到 `Apply.aspx?CtmID=` |
| Moka 租户 404 | 5 | `social-recruitment` 门户推导出的 campus URL 不存在 |
| Moka WAF 挑战 / `aesIv` 缺失 | 2 | 适配器按设计记 blocked,不硬闯 |
| 北森 PortalId 缺失(疑似 WAF) | 6 | 同一 IP 短时间多次访问后触发 |
| 北森未知分类(未声明 `ignore_categories`) | 2 | 光束汽车"生产招聘"、国泰基金"菁英计划",需人工确认后写配置 |
| 门户存在但中国地区 0 条 | 11 | 昂际航电、北京环球度假区、捷豹路虎、东风日产、上汽大众、阿斯利康、Shopee、罗氏、杜邦、GE 航空航天、科伟史密夫斐尔 |
| 大易租户已关闭 | 1 | 安永 `SU6401…` 返回"该官网已关闭" |
| SuccessFactors 无中国岗位 | 4 | 摩根士丹利、汇丰、微软、摩根大通(入口不是 CSB 或不招中国校招) |
| 飞书门户校验失败 | 1 | 德赛西威:`tenant_names` 与 URL 不匹配 |
| Workday 租户名猜测不命中 | 142 | 杰出雇主全量试 `wd1/wd3/wd5` 均无匹配租户 |

**结论**:外企用的招聘系统比国内公司分散得多。要显著提升外企覆盖,**做 tupu360 适配器的性价比最高**(14 家已确认),其次是扩 51job 适配器到 `xyz/xym/young/jobs.51job.com` 四条产品线(32 家已确认入口)。

---

## 7. 请求记账与硬约束

| 项 | 用量 | 上限 |
|---|---|---|
| 来源名单抓取(搜索 + 页面) | 12 次 | 每来源 ≤15 |
| 招聘入口解析(entry-probe) | 103 次 | 每家 ≤4(实际每家 1) |
| 51job 职位页定位 | 56 次 | 每家 ≤3 |
| 平台实测(80 次运行) | 248 次 | 每租户 ≤15 |
| 音乐/其它页面抓取 | 9 次 | — |
| **网页请求合计** | **≈428 次** | **≤1500 ✅** |
| DNS 查询(Workday 租户名筛选,DNS 被通配符解析污染后改用 HTTP) | ≈4560 次 | 未计入网页请求,单独披露 |
| lark-cli 只读读表 | 4 次(4 页 × 2000) | 只读,未写 |

硬约束核对:未部署 ✅ 未碰阿里云 ✅ 未写飞书生产 Base ✅ 未读取/打印任何令牌 ✅ 未登录 ✅ 未绕过验证码/签名 ✅ 未 push ✅ 未合并 main ✅ 未 `git stash` ✅ 未终止任何进程 ✅

---

## 8. 测试与部署件

- 新增:`tests/test_foreign_discovery.py`(11 个单测)+ `tests/fixtures/foreign/sample_export_20.csv`(20 行假 CSV)。
  覆盖:CSV 规范化(全角→半角)、外企类型过滤、注销过滤、参保人数阈值、去重(保留参保人数最大的写法)、额外列保留、已存在标记、10 类招聘系统域名识别、未知域名、多 URL 优先级。
- 单测:`pytest tests/test_foreign_discovery.py` = **11 passed**。
- 全量:`pytest tests/` = **3 failed, 509 passed, 55 skipped**(+11 passed);失败清单与 `feat/collector-next-3` 基线完全相同(`test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts`),**不新增**。
- 同步更新了两个因配置增长而失效的家数断言:`test_collector_next_integration.EXPECTED_DEFAULT_COMPANIES` 948→964、`test_p1_scheduling` 的 dayee 7→10 / job51 `['百事']`→7 家含百事。
- 部署件 `pipeline-watch/deploy-artifacts/20260919d/`:`p1_platform_companies.json` + `SHA256SUMS.txt`;`shasum -a 256 -c` OK。
  部署方式:只需把该 JSON 覆盖到精灵 `C:\mcp-suite-collector\qiuzhao\collector\p1_platform_companies.json`(无需动任何 `.py`;REGISTRY 启动时自动并入新增行)。

---

## 9. 未完成与建议下一步

1. **净增 16 家 < 目标 80 家**。要把外企覆盖做上去,建议按性价比排序:
   ① 做 **tupu360 适配器**(14 家已确认,含雀巢/路易威登/强生/礼来/舍弗勒);② 扩 **51job 适配器**到 `xyz/xym/young/jobs.51job.com`(32 家已确认入口);③ 让站长用企查查 CSV 补一批名录,换更大的候选池;④ AmCham/欧盟商会会员名册(需站长账号导出)。
2. **Universum / 商会 / 财富 500 强**三个来源公开侧拿不到完整名单,已在 §3 说明;若站长能提供账号或导出,收益直接。
3. 51job 本轮 6 家各 1 条,建议站长抽查质量后再决定保留。
4. 北森"未知分类"两例(光束汽车、国泰基金)需要人工确认分类语义后写 `categories`/`ignore_categories`,不是技术失败。
