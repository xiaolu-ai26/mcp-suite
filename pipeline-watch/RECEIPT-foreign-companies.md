# RECEIPT: 外企(含小而美)怎么找准、怎么接 —— 发现清单 + Workday/SuccessFactors 平台适配器 + 首批实测

分支:`feat/foreign-companies`(基于 `feat/banks-batch1`,worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign`)
日期:2026-09-18 执行:DeepSeek Harness 范围:只读发现调研 + 2 个平台适配器 + 配置 + 单测 + 首批真实只读实测 + 部署件 + 收据。
**未部署**:未 SSH、未碰阿里云、未调飞书、未登录任何站点、未 `--apply`、未写库、未 push、未合并。所有真实请求只打 Workday CXS / SuccessFactors 公开接口,每租户 ≤20 次、每请求间隔 ≥2s。

---

## 0. 一句话结论

给站长的答案是:**外企不是"一块"而是一条条公司,必须"先列名单、再逐家回官网认系统"**。发现清单已产出 443 条(去重前口径),覆盖 3 条可重复路径(闲鱼外企切片 / 牛客外企标签 / 公开名录);平台侧新增通用 `p1_platform_workday.py`(Workday CXS)与 `p1_platform_successfactors.py`(SAP SuccessFactors CSB)两个适配器,**新增一家外企 = 配置里加一行**。首批真实只读实测:Workday 9 家、SuccessFactors 3 家全部取到官方岗位;其中 Workday 校招 6 家 `success/complete`。同时实测证伪了"外企=Workday":Unilever 的 Workday 站有 16 条全球早期职业岗位但**中国校招 0 条**(中国入口走前程无忧),宝洁走 Phenom、博世走 Moka、西门子自建。

---

## 1. 交付物

| 文件 | 说明 |
|---|---|
| `pipeline-watch/foreign-companies-discovery.json` | 443 条外企发现清单(公司/国家/行业/校招 URL/ATS/是否中国频道/大小类/证据) |
| `qiuzhao/collector/p1_platform_workday.py` | Workday CXS 通用适配器(key=`tenant/region/site`) |
| `qiuzhao/collector/p1_platform_successfactors.py` | SAP SuccessFactors CSB 通用适配器(key=career-site host) |
| `qiuzhao/collector/p1_platform_companies.json` | 在 `beisen`/`moka` 后追加 `workday`(9)/`successfactors`(3)两段 |
| `qiuzhao/collector/p1_pipeline.py` | **仅追加一段独立注册块**(append-only,未动其它行) |
| `tests/test_p1_platform_workday.py`、`tests/test_p1_platform_successfactors.py` | 14 个 fixture 单测 |
| `tests/fixtures/platform/workday_*.json`、`sf_*.html` | 录制响应夹具 |
| `pipeline-watch/foreign-platforms-verify.py` | 首批实测运行器(可复现 §5) |
| `pipeline-watch/deploy-artifacts/20260918f/` | 部署件(4 文件 + SHA256SUMS + DEPLOY-NOTES) |

---

## 2. 给站长的"以后怎么找外企"5 步 SOP

### 第 1 步:从闲鱼公司表直接筛"外企"(最省事的存量)
用 `lark-cli base +record-list`(只读 `--as user`)拉主表 `tblMKWxJGIPhcDbw`,按 `企业性质 == 外企` 过滤,再按**投递链接域名**判系统:`myworkdayjobs.com`→Workday、`successfactors`/`*.jobs/search`→SuccessFactors、`mokahr.com`→Moka、`zhiye.com`→北森、`hotjob.cn`→大易。
- 实测:命中 449 行,原始公司名 342 个,是本清单最大的来源。

### 第 2 步:牛客校招日程按"外企"标签抽公司名(增量发现)
牛客 `jobs/school/schedule` 页面 SSR 内嵌筛选 JSON,`companyNature` 外企 `id=2834`。**只取公司名**,岗位仍回官方站。
- 实测:应届生求职网首页/搜索页未出现"外企/外资"标签(JS 渲染),不作为发现源。

### 第 3 步:公开"外企校招"名录补"小而美"
本次用了三份名录(只列名字):太仓德企名单(隐形冠军聚集,140 家)、中国美国商会招聘广场、中国外商投资企业协会(CAEFI)会员名录。

### 第 4 步:逐家回官网 Careers/校园招聘页"认系统"
拿公司名 → 搜公司官网招聘入口 → 看真实落点。**关键动作是"认系统"而不是"猜系统"**:
- 页面 URL/源码出现 `myworkdayjobs.com` → Workday,抄下 `tenant/region/site`;
- 出现 `/search/?...locationsearch=` 且带 `jobTitle-link` → SuccessFactors CSB,抄下 host;
- 出现 `mokahr.com` / `zhiye.com` / `hotjob.cn` → 对应 Moka / 北森 / 大易(已有适配器)。

### 第 5 步:能参数化的进配置并只读验证
- Workday:`p1_platform_companies.json` 的 `workday` 块加一行 `"<tenant>/<region>/<site>": "<公司名>"`;
- SuccessFactors:`successfactors` 块加一行 `"<host>": "<公司名>"`;
- 验证:`QIUZHAO_PLATFORM_REQUEST_BUDGET=20 QIUZHAO_PLATFORM_REQUEST_INTERVAL=2 python -m qiuzhao.collector.p1_pipeline --adapter <adapter> --company <名> --scope campus --output-dir <目录>`,看 `result.json` 的 `coverage.status/complete/collected_jobs/request_budget`。**仅在 success/partial 且 ≥1 条时保留在配置**。

---

## 3. 发现清单统计(`foreign-companies-discovery.json`)

| 维度 | 数值 |
|---|---|
| 总条数 | 443 |
| 小而美(`small_beautiful`) | 183(目标 ≥30) |
| 大型跨国(`large_mnc`) | 93 |
| 其它中型(`medium_other`) | 167 |
| 有中国校招频道 | 303 |

按 ATS:其他/自建 164、本地招聘/未核实 140、Moka 39、前程无忧 38、Workday 17、北森 13、大易 13、智联 7、SuccessFactors 4、飞书招聘 3、猎聘 1、牛客 1、BOSS直聘 1、Taleo 1、SmartRecruiters 1。
按来源:闲鱼外企切片 291、太仓德企名单 140、平台探测 12。

三条发现路径的实测证据见 `methods` 字段。**注意:清单是"线索池",同名公司可能因多条投递链接重复出现,岗位必须回官方站重新确认(本清单不用于直接入库)。**

---

## 4. 平台适配器契约

- 对外契约与 `p1_sources_*` 一致:`COMPANIES` + `collect(company, scope, output_dir) -> {'jobs': [...], 'coverage': {...}}`,证据文件 `list-*.json/json` 或 `list-*.html`,并逐家通过 `p1_pipeline.validate_result`。
- 配置驱动注册:两个模块的 `merged_registry()` 在 `p1_pipeline.py` 的**追加独立注册块**里并入 `REGISTRY`,不改硬编码 50 家顺序。
- `p1_pipeline.py` 改动经核对:相对 `feat/banks-batch1` **仅 +14 行,全部是追加块**(注释 + 2 个 `try/except`),未改任何既有行。
- 数据质量:只写官方字段。Workday `startDate`→`published_at`、`endDate`→`deadline_raw`(无则留空);SuccessFactors `datePosted`/`validThrough` 同理。**两个平台都没有届别字段,`cohort_raw` 一律留空,不推断。**
- **城市规范化**:只用官方 location 里的城市 token;`"Shanghai, China"`→`["Shanghai"]`、`"Beijing, China"`→`["Beijing"]`、`"Shanghai China, CN, 200000"`→`["Shanghai"]`。国家/邮编片段剔除,**不做中英翻译**(保持官方英文城市名,与 Workday 一致)。
- **请求预算/限速**:`QIUZHAO_PLATFORM_REQUEST_BUDGET`(生产缺省不限,验证设 20);`QIUZHAO_PLATFORM_REQUEST_INTERVAL`(生产缺省 0,验证设 2 秒)。
- SuccessFactors 列表页有**两种主题**:多数 `<tr class="data-row">`;部分(勃林格殷格翰)用 `<div class="row job job-row">` 且 `jobTitle-link` 带附加 class。适配器两种都解析——这是首轮实测发现的真缺陷(否则有岗位的租户被静默读成 0 条)。

---

## 5. 首批真实只读实测(2026-09-18,不写库)

运行器:`python pipeline-watch/foreign-platforms-verify.py`;`QIUZHAO_PLATFORM_REQUEST_BUDGET=20`、`QIUZHAO_PLATFORM_REQUEST_INTERVAL=2.0`;产物在 `_worktrees/foreign-out/verify-20260918-final/`。

| # | 平台 | 公司 | scope | status | complete | 条数/期望 | 列表页 | 请求/上限 | published 率 | deadline 率 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | workday | 英伟达 | campus | success | ✅ | 6/6 | 11 | 17/20 | 100% | 0% |
| 2 | workday | 强生 | campus | success | ✅ | 1/1 | 1 | 2/20 | 100% | 0% |
| 3 | workday | 壳牌 | campus | success | ✅ | 1/1 | 1 | 2/20 | 100% | 100% |
| 4 | workday | 英国石油 | campus | success | ✅ | 2/2 | 1 | 3/20 | 100% | 100% |
| 5 | workday | 美敦力 | campus | success | ✅ | 1/1 | 5 | 6/20 | 100% | 0% |
| 6 | workday | 奥纬咨询 | campus | success | ✅ | 1/1 | 2 | 3/20 | 100% | 100% |
| 7 | workday | 花旗银行 | campus | blocked | ❌ | 0/0 | 5 | 5/20 | — | — |
| 8 | workday | 美满电子 | campus | blocked | ❌ | 0/0 | 1 | 1/20 | — | — |
| 9 | workday | 史密夫斐尔 | campus | blocked | ❌ | 0/0 | 1 | 1/20 | — | — |
| 10 | workday | 花旗银行 | intern | success | ✅ | 3/3 | 5 | 8/20 | 100% | 0% |
| 11 | workday | 美满电子 | intern | success | ✅ | 3/3 | 1 | 4/20 | 100% | 0% |
| 12 | workday | 史密夫斐尔 | intern | success | ✅ | 1/1 | 1 | 2/20 | 100% | 0% |
| 13 | workday | 英伟达 | intern | partial | ❌ | 9/40 | 11 | 20/20 | 100% | 0% |
| 14 | successfactors | 思爱普 | campus | success | ✅ | 4/4 | 2 | 6/20 | 100% | 0% |
| 15 | successfactors | 采埃孚 | campus | blocked | ❌ | 0/0 | 4 | 4/20 | — | — |
| 16 | successfactors | 勃林格殷格翰 | campus | blocked | ❌ | 0/0 | 2 | 2/20 | — | — |
| 17 | successfactors | 思爱普 | intern | success | ✅ | 13/13 | 2 | 15/20 | 100% | 0% |
| 18 | successfactors | 采埃孚 | intern | success | ✅ | 8/8 | 4 | 12/20 | 100% | 100% |
| 19 | successfactors | 勃林格殷格翰 | intern | success | ✅ | 1/1 | 2 | 3/20 | 100% | 0% |

说明:
- **Workday**:校招 `success/complete` 6 家(英伟达/强生/壳牌/英国石油/美敦力/奥纬咨询),已满足"≥6 家";花旗/美满/史密夫斐尔的中国岗位当期只在实习口径(实测 intern 3/3/1),因此整体 9 家全部达到"≥1 条",保留在配置。英伟达实习校园岗位多,20 次预算下为 `partial`(刻意的礼貌上限,不是解析失败)。
- **SuccessFactors**:SAP(校招 4 + 实习 13)、采埃孚(实习 8)、勃林格殷格翰(实习 1),**3 家达到"≥1 条"**。阿克苏诺贝尔、必维国际检验的列表接口可用但其中国岗位当期**全是社招**,校招/实习均 0 条,按"≥1 条才写"规则**未保留在配置**(站点信息保留在发现清单)。
- **`deadline_rate` 低是平台事实**:Workday `endDate`、SuccessFactors `validThrough` 多数为空,按"没有就留空、不推断"处理。
- **城市**:全部为官方英文城市 token(Shanghai/Beijing/Dalian/Kunshan 等)。
- **Unilever(额外探查,未写入配置)**:`unilever.wd3.myworkdayjobs.com/Unilever_Early_Careers` 有 16 条全球早期职业岗位(英国/印尼/新加坡),`searchText=China` 为 0;其中国校招入口是前程无忧(`xyz.51job.com/...ctmid=8833740`,见发现清单)。故**不满足"≥1 条"、不写入 Workday 配置**,但它正是"外企=Workday 不成立"的实测反例。

---

## 6. 哪些系统接不了、为什么

| 系统 | 证据 | 结论 |
|---|---|---|
| Phenom People(宝洁) | 宝洁中国官网 `careers.pg.com.cn` 实测用 `cdn.phenompeople.com` | 无公开免登录列表 API,前端渲染,本次不接 |
| Taleo(科尔尼) | `taleo.net` 根域 301 到 Oracle 产品页 | 产品被 Oracle Recruiting 替代,中国校招案例基本绝迹,不接 |
| SmartRecruiters(罗兰贝格) | 站点 `jobs.smartrecruiters.com` 存在 | 未确认免登录列表接口,未接 |
| 自建/定制(164 条) | 工/建/招/交、西门子"图普"等 | 每家一套,需逐站开发,成本高,只列清单不接 |
| 前程无忧 38 / 智联 7 / 本地招聘 140 | 名录与域名判断 | 聚合/本地渠道,岗位分散在门户,只作发现源或未定位 ATS |
| 飞书招聘 / 猎聘 / BOSS直聘 / 智联校园 / 牛客 | 调研记录:飞书招聘请求签名+滑块;猎聘 robots 明禁 `/api/com.liepin.campus*`;BOSS robots+协议双禁;智联 robots 禁带参 URL | 产品级硬拦截或 robots/协议禁止,不绕过,不接 |
| SuccessFactors 部分租户(BASF 等) | `basf.jobs/search/` 无可解析的 `jobTitle-link`/行结构 | 列表主题不兼容,未接(清单仍记录) |

---

## 7. 遗留与风险

1. **发现清单未去重**:443 条按"链接"计数,同名公司重复出现(如 Workday 17 条里英伟达/美满/奥纬各出现多次)。后续应加"公司主键+别名"归并,再去重统计覆盖公司数;当前 183 条小而美也已远超 ≥30 的目标。
2. **SuccessFactors 只覆盖 3 家**:主题不兼容(BASF)与"当期无校招/实习"(阿克苏诺贝尔/必维)会漏。建议后续优先补 `jobTitle-link` 之外的 SF 主题适配,并定期(校招季)复测被裁剪的租户。
3. **Unilever 类反例**:中国校招挂在本土渠道(前程无忧)的公司,Workday 全球站取不到中国岗位,需逐家认渠道,不能靠母公司 ATS。
4. **限定 scope 的"0 条"≠系统不可用**:花旗/美满/史密夫斐尔的 campus 当期 0 条但 intern 有;每日链应按 scope 分别判断,不因 campus 空就判定公司失败。
5. **未接平台的岗位**:Phenom/Taleo/SmartRecruiters/自建目前只能人工/半自动,详见 §6。
6. **限速与 WAF**:本次每租户 ≤20 请求、每请求 ≥2s;生产不限预算时大租户页数多,建议保持限速并观察 Workday/SF 的 429/403。
7. **城市未中文化**:当前保留官方英文城市 token;若下游页面需要中文城市,应另建"官方城市→中文"映射表(可追溯),不在采集层翻译。

---

## 8. 测试与基线

- 新增 14 个 fixture 单测(Workday 8 + SuccessFactors 6):字段映射、scope 关键词优先级(intern 先于 campus)、空字段不推断(endDate/validThrough 空→留空、cohort 恒空)、国家过滤、请求预算、配置驱动注册表。
- 全量 `pytest tests/`(本 worktree 实测,环境缺 `qiuzhao/data/jobs.json`,55 skipped):**3 failed, 402 passed, 55 skipped**。
- 失败集合与基线 `feat/banks-batch1` **完全一致**:`test_core.py::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema.py::test_enum_check_fails_when_data_drifts`。其中 `test_p1_pipeline` 超时用例本次把基线分支受管文件导出到临时目录单独复跑,**基线同样失败**,确认是既有失败而非本次引入;`test_codes_kind` 为既有偶发(本次全量通过)。
- 顺序类断言同步更新(属预期行为变化,非新增失败):`tests/test_collector_next_integration.py` 的"银行必须最后"改为"平台块→银行块→外企块";`tests/test_p1_banks.py` 同理改为断言银行块连续且不被后续追加块打散。
- 相对 `feat/banks-batch1`,`p1_pipeline.py` 仅 +14 行追加块;`p1_platform_companies.json`、2 个适配器、单测与夹具为新增。

---

## 9. 部署(本次不做)

部署件 `pipeline-watch/deploy-artifacts/20260918f/`:**叠加在 `20260918e` 之后**。因本分支基线是 `feat/banks-batch1`(不含 e 的阿里/腾讯块),包内 `p1_pipeline.py` 采用**累积版**(=`20260918e` 全文 + 本批外企块),可整文件覆盖;细节见同目录 `DEPLOY-NOTES.md` 与 `SHA256SUMS.txt`。**未部署、未 push。**
