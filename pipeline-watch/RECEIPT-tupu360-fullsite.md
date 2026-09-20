# RECEIPT: tupu360 全站真实岗位采集(20260919g)

分支 `feat/tupu360-fullsite`(基于 **`feat/foreign-ats-c` @ `64724de9`**)
worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/tupu360-fullsite`
产物目录 `/Volumes/臭垃圾桶/生财MCP/_worktrees/tupu360-fullsite-out/tupu360-fullsite/`
日期 2026-09-19 执行 DeepSeek Harness
范围 tupu360(图谱天下)公开 `careersite` 族**全站**真实岗位采集 + 表格 + 交接文档。
**未部署、未 SSH、未碰阿里云/精灵、未写生产库、未写飞书、未用 `--apply`、未读取或打印任何令牌、未 push、未合并 main、未 `git stash`。**（唯一被终止的进程是本会话自己在 17:34 用 `pkill` 停掉的采集进程，目的是让修好分页缺陷的适配器生效；没有碰任何别人的进程。）全部外呼都是公开只读 GET/POST,遵守每条 ≥2.0 秒间隔、同 host 并发 ≤3、聚合 ≤1.5 req/s。

---

## 0. 一句话结论

站长 2026-09-19 的「不管社招还是校招,还是实习,只要是有真实岗位就采集下来先」已执行完毕:
公开 `careersite` 族里 **60 家真实企业 × 3 频道 = 180 个采集单元**全部跑完,
采集到 **5523 条真实岗位**(校招 929 / 实习 201 / 社招 4393),
写入 `pipeline-watch/tupu360-fullsite/tupu360-全站岗位-20260919.xlsx`(5 个 sheet)与同名 `.csv`;
另有 17 家演示/试用租户被剔除、224 个目标公开频道 0 职位(含本次重试确认的 `bbac`)、2 个目标在本机网络下无法到达。
`robots.txt` 的 `User-agent: * / Disallow: /` 是平台级声明,本轮按站长决定继续采集,**原文与决定都记在第 3 节**。
本包**不部署**。

---

## 1. 平台形态(公开侧)

### 1.1 两个互不相通的入口族

| 族 | 入口 | 公开可读性 |
|---|---|---|
| **careersite**(公开) | `https://careersite.tupu360.com/<slug>/position/index?recruitmentType=<TYPE>` | **可读**。服务端渲染整页职位列表;分页走站点自带 `POST /<slug>/position/nextPageList`;详情 `/<slug>/position/detail?positionId=...` |
| **wxtemp**(微信专属) | `https://<slug>.tupu360.com/...` | **匿名不可读**。任意已存在路由一律 `302 → /pageQrCode`(「请用微信扫描二维码打开页面」),换 MicroMessenger UA 则跳 `open.weixin.qq.com` OAuth。**本任务不碰、不伪装 UA、不做 OAuth** |

### 1.2 公开客户目录(本次全站的枚举基础)

`https://careersite.tupu360.com/` 根页里有一个隐藏 div(`<div class="row" style="display: none">`),内容是**公开客户目录**:
**293 个 careersite 租户 `slug + 公司名`**;另有 9 个客户定制域(careersite 同平台、挂客户自己的域名)。
301 个目标(293 + 8 个去重后的定制域)就是本次普查与采集的全集。

### 1.3 三种取法(实测定型,本次只用第 1 种)

| 取法 | 实现 | 本次使用 |
|---|---|---|
| ① `html`(默认) | 带完整浏览器请求头的 `requests` GET 渲染列表页,再用站点自带 `nextPageList` 翻页 | **180 单元全部走这条默认阶梯**(`html → api → headless` 兜底自动升级) |
| ② `api` | 跳过列表页,直接 POST `nextPageList`(`offset`/`max`) | 只在 `html` 解析出 0 行时自动接管(SPA 租户;`jnj` 就是这种) |
| ③ `headless` | Playwright/Chromium 打开公开页读 DOM | 本次**未启用**(`QIUZHAO_TUPU360_HEADLESS` 显式清空),前两种已够 |

---

## 2. 本次采集口径

### 2.1 60 / 17 / 224 / 3 是怎么分出来的

普查口径:301 个目标 × 3 频道(`CAMPUSRECRUITMENT` / `INTERNSHIPRECRUITMENT` / `SOCIALRECRUITMENT`),
每个目标每频道请求一次官方列表页,读官方「共 N 个职位」。三频道合计 **7,123 条**。

| 分类 | 家数 | 条数 | 判定规则 |
|---|---|---|---|
| **纳入(include)** | **60** | **5,517** | 三频道合计 ≥1 条,且**公司名不是平台自己的演示/试用/回归租户** |
| **排除(exclude)** | **17** | **1,606** | 公司名含「试用/演示/测试/回归/图谱」,或名称为**纯数字**(平台内部/压测租户) |
| **0 职位** | **224** | 0 | 三频道均「共 0 个职位」——不是演示租户,只是当前没有发布 |
| **普查失败需重试** | **3** | — | `bbac`(194 字节异常页)、`hellohr`(503)、`careerjnj`(SSL EOF)。重试结果见 §4.4 |

- **普查值是快照,采集按实时为准**:普查到采集之间官方会继续发/下架岗位,所以频道条数会有小幅漂移
  (例:`wuxiapptec` 社招普查 397 → 本次实采 398;`fuyao` 社招普查 228 → 本次实采 228)。
  表里的条数一律以**本次官方列表页实时读到**的为准,普查值只用于分档与排期。

判定规则逐条可复算:`pipeline-watch/tupu360-fullsite/inputs/tupu_scope.json` 的
`exclude` 就是 17 家的权威名单(含 `name` 与 `postings`),`include` 是 60 家的权威名单
(含 `name`/`slug`/三频道条数)。`include` 的 60 家名字全部来自**公开客户目录原文**,没有一条是推断的。

### 2.2 边界案例(逐个交代)

| slug | 名称 | 处理 | 理由 |
|---|---|---|---|
| `grgtest` | 广电计量检测集团股份有限公司 | **纳入**(社招 89 条) | slug 里带 `test`,但公司名是**真实上市检测企业**,岗位也真实。判据是「公司名」不是「slug」 |
| `tptest` | 中力迅科技 | **纳入**(社招 1 条) | 同上;仅 1 条,已在 §7 标为**需站长复核** |
| `jnjtest` | 强生校招试用 | **排除**(2 条) | 公司名含「试用」 |
| `accentureats` | 埃森哲 | **纳入**(109 条) | slug 带 `ats`,公司名是真实企业「埃森哲」;与演示租户 `accenture`(埃森哲**试用**,17 条)**不是同一个租户** |
| `bmw-brilliance` | 华晨宝马汽车有限公司 | **纳入**(28 条) | 真实合资公司;与演示租户 `bmw-brillianceats`(华晨宝马汽车有限公司**试用**,119 条)分开 |
| `fuyao` | 福耀玻璃 | **纳入**(353 条) | 真实;演示租户是 `fuyaogroup`(福耀校招**试用**,5 条) |
| `helpdesk` / `jnjtest` | 强生校招**试用** | **排除** | 名字含「试用」,且与真实 `jnj`(强生校招,344 条)是不同租户 |
| `tupu1592` / `tupu1955` / `tupu2325` | 纯数字或 tupu+数字 | **排除** | 平台内部/压测租户 |
| `p1_platform_companies.json` 同名的 3 家 | 强生 / 斯堪尼亚 / 药明康德 | **配置写入但日更不生效(setdefault)** | 详见 §5.3 |

### 2.3 字段口径(不推断)

- **发布时间**:只在官方页面真的印了才写(模板 A 的「发布日期」列 / 模板 B 的「发布于: YYYY-MM-DD」/ 详情页「发布时间」),逐条记 `published_at_source`。
- **截止时间**:官方没印就**留空**,并写 `deadline_source='not published'`。**全站 0 条有截止日**。
- **届别**:`cohort_raw` **恒为空**——官方没印届别就不推断;年份只留在标题里。
- **学历**:官方页面写了才进 `education_raw`;没有就空。
- **招聘人数**:模板 B 的卡片写了才取(`headcount_raw`);模板 A 没有这一列。
- **描述**:详情页正文;`jnj` 租户的 `position/detail` 被重定向到 hash 路由 SPA,**公开侧没有详情页**,所以走 `detail: "list"`,描述用**官方列表卡片原文**,并用 `description_source` 如实标注。
- **状态**:官方 `positionStatus` 隐藏字段(`PUBLISHING` = 在招)决定 `source_is_active`,不臆测。

---

## 3. robots.txt 声明原文 + 站长决定(必须留痕)

### 3.1 官方声明原文(2026-09-19 实测,逐字节)

```
GET https://careersite.tupu360.com/robots.txt   -> 200, 26 bytes
User-agent: *
Disallow: /
```

```
GET https://tupu360.com/robots.txt              -> 200 (301 -> www.tupu360.com/robots.txt), 26 bytes
User-agent: *
Disallow: /
```

即:平台在**全站**层面声明 `Disallow: /`,对包括 `careersite` 公开客户站在内的所有路径生效。

### 3.2 站长的决定(原话,2026-09-19)

> 「不管社招还是校招,还是实习,只要是有真实岗位就采集下来先」
> 「robot那个也要采集,做完之后落成表格文件和一份交接文档说明书」

### 3.3 本轮的执行边界(在站长决定之下仍然守住的线)

- 只做**公开只读 GET/POST**;**不登录、不做微信 OAuth、不伪装 MicroMessenger UA、不绕验证码/签名、不复用任何 cookie**。
- 单请求间隔 **≥2.0 s**(`QIUZHAO_PLATFORM_REQUEST_INTERVAL=2.0`)、同 host 并发 **≤3**、聚合 **≤1.5 req/s**;每单元请求数逐条记账(§6)。
- **不部署**:本包只是产物与文档,`enabled` 开关与日更接入方式写在 §5,由站长决定何时生效。
- 若要回到严格合规:**把 `tupu360` 段里 60 行的 `enabled` 全部改成 `false` 即可,代码不用动**(适配器已支持 `enabled: false`,日更会跳过)。

---

## 4. 实测结果

### 4.1 总账

| 项目 | 数值 |
|---|---|
| 采集单元(租户 × 频道) | **180** |
| 采集租户 | **60** |
| 岗位总条数(validated 合计) | **5523** |
| 校招 / 实习 / 社招 | 929 / 201 / 4393 |
| 公开只读请求总数 | **5772** |
| 采集墙钟时间 | **1:38:35**（2026-09-19T09:03:31Z → 2026-09-19T10:42:06Z，含中途为修分页缺陷重启一次） |
| ├ 第 1 段（旧适配器，17:03:59→17:34:36） | 30 分 37 秒，跑完 6 个单元后发现 600/828 缺陷 |
| ├ 第 2 段（修好后重启，断点续跑，17:34:36→18:31:30） | 56 分 54 秒，补齐其余 175 个单元 |
| └ 单独重采 `innomotics/intern`（18:41:51→18:42:06） | 13.5 秒 |
| 单元耗时合计（3 并发，含等待） | 13,111 秒 ≈ 3.64 工作小时 |
| 单元状态分布 | blocked 69、success 111 |
| `validate_result` 通过 | **180/180** |
| `validate_result` 未通过 | **0** |
| 发布时间可用率 | 5394/5523（97.7%） |
| 截止时间可用率 | 0/5523（0.0%） |

### 4.2 按租户(条数前 20)

| # | 公司 | slug | 条数 |
|---|---|---|---|
| 1 | 康龙化成（北京）新药技术股份有限公司 | `pharmaron-bj` | 1013 |
| 2 | 药明康德 | `wuxiapptec` | 623 |
| 3 | 福耀玻璃 | `fuyao` | 353 |
| 4 | 强生校招 | `jnj` | 344 |
| 5 | 辉瑞 | `pfizer` | 279 |
| 6 | 晖致医药有限公司 | `Viatris` | 272 |
| 7 | 阿斯利康 | `astrazeneca` | 268 |
| 8 | 西门子医疗Siemens Healthineers | `healthineers` | 236 |
| 9 | 西门子中国 | `siemens` | 215 |
| 10 | 赛诺菲（中国）投资有限公司上海分公司 | `sanofi` | 146 |
| 11 | LVMH | `lvmh` | 129 |
| 12 | 中国科学院计算技术研究所 | `ict.ac` | 111 |
| 13 | 埃森哲 | `accentureats` | 109 |
| 14 | 西门子能源 | `siemens-energy` | 99 |
| 15 | 中科院软件所 | `iscas` | 90 |
| 16 | 广电计量检测集团股份有限公司 | `grgtest` | 89 |
| 17 | 舍弗勒 | `schaeffler` | 74 |
| 18 | 万集科技 | `wanji` | 71 |
| 19 | 康明斯 | `cummins` | 67 |
| 20 | SK 海力士大连 | `skhynix` | 66 |
| … | 其余 40 家 | | 869 |

完整 60 家见 xlsx 的 **租户汇总** sheet。

### 4.3 不是 success 的单元(如实列出)

**结论:69 个 blocked 单元全部是「该频道官方当前 0 条职位」,不是采集失败。**
适配器的契约是「读到 0 行 → `status=blocked` + 一条 `no public posting found ...` 错误 + 一条
`官方站点 ... 的公开频道当前 0 条职位` 的 `note`」,所以 `blocked` 在这里的含义是**空频道**。

| 项目 | 数值 |
|---|---|
| blocked 单元 | 69（campus 26 / intern 36 / social 7） |
| 这些单元的 `collected_jobs` | 全部 0 |
| 这些单元的 `expected_total` | 全部 0 |
| 对照 2026-09-19 普查 | 这 69 个单元对应的普查条数**也全是 0**（逐条核对，无例外） |
| 60 家里有没有「三个频道全空」的 | **没有**；60 家每家至少 1 个频道 success |

逐单元的完整清单在 xlsx 的 **单元明细** sheet（180 行，含 `状态 / 采集条数 / 官方总数 / 请求数 /
错误数 / 首条错误 / 取法`），`采集记账` sheet 里另有 69 条错误原文。

**另有一次真实的瞬时故障（已修好，如实记）**：`innomotics`(茵梦达) 的 **intern** 频道第一次采集时
撞上一次瞬时 TLS 故障
（`SSLError: ... /innomotics/position/index?recruitmentType=INTERNSHIPRECRUITMENT (EOF occurred in violation of protocol)`），
`status=blocked`、0 条；而普查里该频道有 5 条。原因是适配器读到 0 行就报 blocked，
而续跑判据当时只看 `expected_total`（blocked 单元的 `expected_total` 是 0，看不出异常），
所以它没有被自动重试。处理：

1. 单独重采该单元 → **5 条 / 6 请求 / success**（`units/innomotics__intern/validated.json`）；
2. 给 `pipeline-watch/tupu360-fullsite-run.py` 的 `needs_retry()` 补上一条判据：
   **「本次 0 条、但普查该单元 > 0 条」也算待重跑**，避免这类「网络抖动伪装成空频道」再漏掉。
   这条只触发重试，不会伪造任何数据。

### 4.4 三个重试目标的结果

| 目标 | 公司 | 本次重试结果 |
|---|---|---|
| `bbac` | 北京奔驰人力资源 | 官方列表页正常（`<title>职位列表</title>`，45,420 / 46,067 字节），但三个频道的 `nextPageList` 都只回一个空分页器（195 字节）→ **确认 0 条**。普查里的「194 字节无法归类」就是这个空分页器，不是封禁（见 `logs/retry-probe.txt`） |
| `hellohr` | 三人行(`www.hellohr.cn`) | 本机网络不可达：系统代理 `127.0.0.1:1082` 返回 `503`，绕开代理直连则 TLS 握手 `EOF` → **本机网络路径限制，不是站点封禁**；要采它需要一条能到达该域的网络路径 |
| `careerjnj` | 强生社招(`career.jnj.com.cn`) | 同 `hellohr`：代理下 SSL `EOF`，直连也 `EOF`。对照实验：`careersite.tupu360.com` 直连同样 `EOF`，说明本机出网必须走代理 → **环境限制** |

### 4.5 本轮发现并修掉的适配器缺陷:分页硬截断 600 / 828

**现象**:第一轮采集里 `pharmaron-bj`(康龙化成)的**社招**频道只有 `600` 条,
而官方列表页自己写着「共 828 个职位 / 共 56 页」;`coverage` 却把 `pagination_exhausted` 报成 `true`。

**根因**(在 `qiuzhao/collector/p1_platform_tupu360.py`):
`_fetch_next_pages(..., page_cap=40)` 把 `page_cap` 当成了**目标页数**而不是安全上限,
40 页 × `PAGE_SIZE=15` = **恰好 600**,于是任何超过 600 条的频道都被硬截断到 600。
同一个文件里 `_fetch_direct_api(page_cap=60)` 的上限是 60×100=6000,所以走 `api` 取法反而拿得满——
也就是说缺陷只落在 `html` 阶梯(默认取法)上。

**修法**(只改适配器,没碰 `p1_pipeline.py`):

1. 翻页页数改成**站点自报的页数**:优先 `共N页`,模板不印页数时用 `ceil(共N个职位 / 每页条数)` 兜底;
   `page_cap` 降级为纯安全阀,并从 40 提到 **`PAGE_CAP = 120`**(120 × 15 = 1800 行,
   远高于全站普查里最大的单频道 828)。
2. 触顶时**如实标注**:`_fetch_next_pages` / `_fetch_direct_api` 都返回 `page_cap_hit`;
   `collect()` 在触顶时把 `pagination_exhausted` 置回 `False`、写 `coverage['page_cap_hit']=True`
   并追加一条错误说明,因此 `finish()` 不可能把截断的单元算成 `complete`。
   ——修之前触顶时 `pagination_exhausted` 仍是 `true`,这是同一个 bug 的第二个面。
3. 补 3 个单测(夹具全部是本次**真实录制**的 56 页页面:`pharmaron-bj-SOCIALRECRUITMENT-list-1.html`
   / `pharmaron-bj-social-page-2.html` / `pharmaron-bj-social-page-56.html`):
   - 56 页频道要发 **55** 次 `nextPageList`、拿到 828 条(不是 600);
   - 人为把 `PAGE_CAP` 调到 3 时,必须 `page_cap_hit=True` / `pagination_exhausted=False` / `status=partial`;
   - `_fetch_direct_api` 同样要报 `page_cap_hit`。

**新旧对照(同一份真实夹具,本地无网络复跑)**:

```
OLD (HEAD, page_cap=40)    pages_requested= 39 rows= 600 total_label=828 page_cap_hit=None
NEW (patched)              pages_requested= 55 rows= 828 total_label=828 page_cap_hit=False
```

**修完实测**:`pharmaron-bj/social` 在修好的适配器上重采 =
`828` 条 / `884` 次请求 /
`success / complete=True`(见 `单元明细` sheet 与 `units/pharmaron-bj__social/validated.json`)。

**是否还有别的截断点**(判据 `expected_total > 600`,ledger + 普查数据双向核对):

| 租户 | 频道 | 本次实采 | 官方总数 | 触顶 |
|---|---|---|---|---|
| 康龙化成（北京）新药技术股份有限公司 | social | 828 | 828 | 否 |

普查数据里三频道合计 > 600 的只有 `pharmaron-bj`(1013)与 `tupuCampus`(678,演示租户已排除);单频道 > 600 的只有 `pharmaron-bj` 社招 828。两条来源(普查 json / 本次 ledger)结论一致,**没有第二个被截断的单元**。

---

## 5. 如何加一家 / 如何接入日更

### 5.1 加一家(SOP)

1. 在 `https://careersite.tupu360.com/` 根页(公开客户目录)搜公司名,拿到 slug;
   或直接开 `https://careersite.tupu360.com/<slug>/position/index?recruitmentType=CAMPUSRECRUITMENT`:
   出现「职位列表」= 有公开站;出现「抱歉，该网站已停用」= 只有微信站。
2. 在 `qiuzhao/collector/p1_platform_companies.json` 的 `tupu360` 段加一行:
   ```json
   "acme": {"name": "某某公司", "note": "careersite tenant; verified 2026-09-19."}
   ```
   可选字段:`host`(默认 `careersite.tupu360.com`)、`tenant`(key 与 slug 不同名时)、
   `channels` / `extra_channels`(覆盖或追加官方 `recruitmentType`)、`detail: "list"`
   (该租户公开侧没有详情页,用官方列表卡片原文)、`scope`(钉死单一频道)、`url`(覆盖证据 URL)、
   `enabled: false` + `blocked_reason`(调查过但公开侧拿不到)。
3. 跑一次单单元验证:
   ```bash
   python3 pipeline-watch/tupu360-fullsite-run.py --only acme --scopes campus,intern,social
   ```
   看 `单元明细` sheet 的 `状态 / 采集条数 / 官方总数 / 校验通过`;
   看 `记录id` 与 `详情链接` 是否指向真实岗位。
4. 若 0 条:先看 `首条错误`(是「官方 0 条」还是「微信专属」),再决定写 `enabled:false` 还是调整 `channels`。

### 5.2 接入日更

- `p1_pipeline.py` 里 tupu360 的注册块**已经就位且本轮未改**:`merged_registry()` 会把配置里的
  每一行并进 `REGISTRY`(append-only,`setdefault`),所以往配置里加行就等于接入日更。
- 本轮把 60 家真实租户**全部追加**进 `tupu360` 段(**实际新增 54 行**),
  日更默认集合 `DEFAULT_COMPANIES` 因此从 **953 → 1005**(+52;
  54 行里有 2 行的公司名已被更早的适配器占用,见 §5.3)。
- **成本提醒**:全量 5,523 条岗位、180 个单元,在 ≥2.0 s/请求 + 3 并发下**实测用了 5,772 次请求 / 1 小时 39 分**(§4.1)。日更自己的节流更松(`--platform-workers 2`、`PLATFORM_MIN_INTERVAL=1.0`,`collect_process` 注入的 `QIUZHAO_PLATFORM_REQUEST_INTERVAL` 默认 1.0),实际耗时可能短一些,但 tupu360 一家就会占掉当日平台预算的一大块。所以**建议**:
  - 把 `qiuzhao/collector/p1_pipeline.py` 的 `ROTATING_MODULES` 加上
    `'qiuzhao.collector.p1_platform_tupu360'`,然后按天轮换:
    日更命令加 `--platform-rotation N`(N = 轮换天数,例如 `--platform-rotation 7`),
    即 tupu360 每 N 天跑一次完整一轮;`PLATFORM_ROTATION_DEFAULT` 保持 1 时是全跑。
  - 或者继续用配置里的 `"scopes"` 窄化:例如只保留 `["campus","intern"]`
    (`p1_pipeline._load_scope_opt_ins` 已把 `tupu360` 段纳入),把社招从日更改成按周跑。
  - 或者只给站长点名的公司开 `enabled`,其余写 `enabled: false`(代码不用动)。
  - 以上三条都是**建议**,本轮没有改 `p1_pipeline.py`(任务书要求本轮不动它),是否采纳由站长拍板。
  - 若站长要求日更也保持本轮 ≥2.0 s 的间隔,在采集机上显式导出
    `QIUZHAO_PLATFORM_REQUEST_INTERVAL=2.0` 即可(`collect_process` 用的是 `setdefault`,
    **调用方显式给的值永远不会被调低**)。

### 5.3 三处同名:配置写了但日更不生效(setdefault 语义,如实交代)

| 公司名 | tupu360 租户 | 日更实际归属 | 说明 |
|---|---|---|---|
| 强生 | `jnj`(校招 18 / 实习 4 / 社招 322) | 既有 `workday` 段 `jj/wd5/JJ` | `feat/foreign-ats-c` 时期就有的冲突,本轮未改 |
| 斯堪尼亚 | `scania`(社招 36) | 既有 `moka` 段 `scania/168376` | 追加行不会顶替 moka |
| 药明康德 | `wuxiapptec`(校招 198 / 实习 27 / 社招 397) | 硬编码 `p1_sources_41_50` | 公司名在硬编码 50 家里,`setdefault` 保留原适配器 |

三家的**岗位都已经采进本轮表格**,只是日更路由仍归原适配器。要不要交接由站长定夺。

---

## 6. 请求记账与硬约束

### 6.1 记账

| 项目 | 数值 |
|---|---|
| 本次采集请求(180 单元,含翻页与逐岗位详情) | **5772** |
| 平均每单元 | 32.07 |
| 请求间隔 | `QIUZHAO_PLATFORM_REQUEST_INTERVAL=2.0`(实测生效,见 `单元明细` 的 `耗时秒` ÷ `请求数`) |
| 同 host 并发 | 3(`--workers 3`,硬上限 3) |
| 聚合速率 | ≤ 1.5 req/s |
| 单元耗时合计 | 13111 秒（3.64 小时，按 3 并发并行） |
| 普查阶段(上一轮,总控执行) | 903 次只读请求 |
| 本次新增的探针请求(3 个重试目标 + robots.txt) | 14 次重试探针 + 2 次 robots.txt 取样 + 2 次分页夹具录制 = 18 |
| 三个重试目标一次性的形态探针 | 见 §4.4 与 `logs/retry-probe.txt` |

### 6.2 硬约束核对

| 约束 | 状态 |
|---|---|
| 请求间隔 ≥2.0 s | ✅ |
| 同 host 并发 ≤3 | ✅ |
| 聚合速率 ≤1.5 req/s | ✅ |
| 只做公开只读 GET/POST | ✅ |
| 不登录 / 不做微信 OAuth / 不伪装 MicroMessenger UA | ✅ |
| 不绕验证码 / 不绕签名 / 不复用 cookie | ✅ |
| 不部署 / 不 SSH / 不碰阿里云 / 不碰精灵 | ✅ |
| 不写生产库 / 不写飞书 / 不用 `--apply` | ✅ |
| 不读取或打印任何令牌 | ✅ |
| 不 push / 不合并 main / 不 `git stash` | ✅ |
| 不终止任何进程 | ✅（只 `pkill` 了本会话自己在 17:34 启动的采集进程，为的是让分页修复生效；没有碰任何别人的进程） |
| `p1_pipeline.py` 本轮未改 | ✅（`git diff 64724de9 -- qiuzhao/collector/p1_pipeline.py` 为空（0 行）；本轮唯一改动的运行时文件是 `qiuzhao/collector/p1_platform_tupu360.py`（分页修复）） |
| 不把 partial/blocked 粉饰成 success | ✅（§4.3 逐条列出） |

---

## 7. 遗留与风险

1. **robots.txt 仍是平台级 `Disallow: /`**(§3)。本轮按站长决定采集;**是否长期日更是站长的决定**,
   一键回退方式见 §3.3。
2. **日更成本**:60 家全开每天约 5,772 次请求;本轮实测墙钟 1 小时 39 分(含一次重启)。
   建议按 §5.2 做轮换或窄化,否则会挤占当日其它平台预算。
3. **`tptest`(中力迅科技)只有 1 条社招岗位**,是 60 家里最小的一家,建议人工扫一眼是否值得长期跟。
4. **`jnj` 没有公开详情页**(`detail: "list"`),344 条(校招 18 / 实习 4 / 社招 322)的描述来自**官方列表卡片原文**,
   比其它租户的详情页正文短;`city` 也只在官方卡片印了才有(强生 social/intern 卡片本身不印城市)。
5. **`hellohr` / `careerjnj` 在本机网络下不可达**,原因在本机网络路径而非站点本身:
   系统代理 `127.0.0.1:1082` 对 `www.hellohr.cn` 返回 `503`、对 `career.jnj.com.cn` 在 TLS 握手时 `EOF`;
   绕开代理直连时这两个域与本机的 `careersite.tupu360.com` **都**不可达(说明本机出网必须走该代理)。
   要采这两家需要一条能到达它们的网络路径。
6. **`bbac`(北京奔驰人力资源)确认 0 条**:本次重试 3 个频道,官方列表页正常返回「职位列表」,
   但 `nextPageList` 只回一个空分页器(195 字节),即当前**没有发布任何岗位**。普查里的「194 字节无法归类」
   就是这个空分页器,不是封禁。等它发布后自动会有数据。
7. **wxtemp 族(微信专属租户)公开侧无解**,本任务明确不碰;若站长要,需要站长的微信登录态,不属于本轮范围。
8. **`pytest tests/` 有 3 条稳定的既有失败 + 1 条既有偶发(`test_codes_kind`) + 13 条既有 error
   (缺 `uvicorn` 等可选依赖)**,与本轮改动无关,本轮新增失败 **0**(逐条对比见 §10)。
9. **60 家里的 `enabled` 默认全开**——这是「追加进配置」的字面执行结果;若站长只想先跑几家,
   按 §5.2 第三条改 `enabled` 即可,不用改代码。

---

## 8. 部署件说明(本包不部署)

目录 `pipeline-watch/deploy-artifacts/20260919g/`:

| 文件 | 目标 | 类型 | SHA256(前 12) |
|---|---|---|---|
| `p1_platform_companies.json` | `qiuzhao/collector/` | 覆盖 | `bac15cf7bd23`… |
| `p1_platform_tupu360.py` | `qiuzhao/collector/` | 覆盖（= 20260919f 全文 + 分页修复） | `0130b3bbf006`… |
| `tupu360-fullsite-run.py` | `pipeline-watch/` | **新增** | `e83033b62390`… |
| `test_collector_next_integration.py` | `tests/` | 覆盖 | `d94cf410fe69`… |
| `test_p1_platform_tupu360.py` | `tests/` | 覆盖 | `0ec3615ea67e`… |
| `fixtures/tupu360/pharmaron-bj-*.html` ×3 | `tests/fixtures/tupu360/` | **新增**（仅测试） | 见 `SHA256SUMS.txt` |
| `DEPLOY-NOTES.md` | — | 本文件 | — |

- 本包**未部署**:未 SSH、未覆盖精灵、未碰阿里云、未 push、未合并 main。
- **叠加前提**:本包只覆盖 `p1_platform_companies.json`,它必须在
  **`20260919f`(tupu360 适配器包)已经叠加之后**再叠,否则配置里有 60 行指向一个不存在的适配器。
  `p1_pipeline.py` 本轮**没有改动**,所以不需要覆盖它。
- 校验:`shasum -a 256 -c SHA256SUMS.txt` → **8/8 OK**；8 个文件与分支源码 `cmp` 逐字节一致。

---

## 9. 怎么复算文档里的每个数字

把下面这段贴进 `python3` 即可复算总账(只读本地产物,不联网):

```python
import json, glob
OUT = '/Volumes/臭垃圾桶/生财MCP/_worktrees/tupu360-fullsite-out/tupu360-fullsite'
units = [json.load(open(f, encoding='utf-8')) for f in glob.glob(OUT + '/units/*/validated.json')]
jobs  = [r for u in units for r in (u['validated'].get('jobs') or [])]
print('units      =', len(units))
print('tenants    =', len({u["slug"] for u in units}))
print('jobs       =', len(jobs))
print('校招/实习/社招 =', sum(r['recruitment_type']=='校园招聘' for r in jobs),
      sum(r['recruitment_type']=='实习招聘' for r in jobs),
      sum(r['recruitment_type']=='社会招聘' for r in jobs))
print('requests   =', sum(u['meta']['requests'] for u in units))
print('published  =', sum(1 for r in jobs if r['published_at']), '/', len(jobs))
print('deadline   =', sum(1 for r in jobs if r['deadline_raw']), '/', len(jobs))
print('validate_ok=', sum(1 for u in units if u['meta']['validation_ok']), '/', len(units))
```

本次实测输出:

```
units      = 180
tenants    = 60
jobs       = 5523
校招/实习/社招 = 929 201 4393
requests   = 5772
published  = 5394 / 5523
deadline   = 0 / 5523
validate_ok= 180 / 180
```

其它数字的复算方式:

| 文档里的数字 | 复算方式 |
|---|---|
| 请求总数 / 状态分布 / 错误条数 | xlsx 的 **采集记账** sheet,或 `sum(u['meta']['requests'] ...)` |
| 每单元条数 / 状态 / 请求数 / 取法 | xlsx 的 **单元明细** sheet(180 行,逐行对应 `units/*/validated.json`) |
| 发布/截止可用率 | xlsx **租户汇总** sheet 的「发布时间可用率」「截止时间可用率」列 |
| 17 家演示租户 + 224 家 0 职位 | xlsx 的 **排除名单** sheet(241 行),来源 `inputs/tupu_scope.json` 的 `exclude` 与 `inputs/tupu_census.json` |
| 953 / 1005 / +52 / +54 行 | `python3 -c "from qiuzhao.collector import p1_pipeline as p; print(len(p.DEFAULT_COMPANIES))"`;配置行数 `python3 -c "import json;print(len(json.load(open('qiuzhao/collector/p1_platform_companies.json'))['tupu360']))"` |
| 600 → 828 | `units/pharmaron-bj__social/validated.json` 的 `meta.collected_jobs`;新旧对照见 `tests/test_p1_platform_tupu360.py` 的三个分页单测 |
| pytest 对比 | `logs/pytest-baseline.txt` vs `logs/pytest-branch.txt` |
| 部署件校验 | `cd pipeline-watch/deploy-artifacts/20260919g && shasum -a 256 -c SHA256SUMS.txt` |
| xlsx 行数 | `python3 -c "from openpyxl import load_workbook;wb=load_workbook('pipeline-watch/tupu360-fullsite/tupu360-全站岗位-20260919.xlsx',read_only=True);print({n:(wb[n].max_row-1,wb[n].max_column) for n in wb.sheetnames})"` |

---

## 10. 单测与验收

- 新增/改动:`tests/test_collector_next_integration.py`(公司数 953→1005、
  `TUPU360_ONLY` 扩到 57 个名字、`药明康德` 的硬编码 setdefault 分支)、
  `tests/test_p1_platform_tupu360.py`(配置契约 14→68 行、6→60 enabled,并**加强**成「enabled 必须是公开 careersite」)。
- `pytest tests/` 对比基线 `feat/foreign-ats-c` @ `64724de9`:
  **失败/错误清单逐条一致，新增失败 0**：

| | 基线 `64724de9` | 本分支 |
|---|---|---|
| summary | 4 failed, 516 passed, 55 skipped, 13 errors | 4 failed, **519** passed, 55 skipped, 13 errors |
| FAILED 清单 | 4 条 | 4 条，逐条相同（`new failures: []`） |
| ERROR 清单 | 13 条 | 13 条，逐条相同（`new errors: []`） |

- `+3 passed` = 本次新增的 3 个分页深度单测。
- 13 条 ERROR 全部是**既有环境缺依赖**（`uvicorn` 等 `ModuleNotFoundError`/`RuntimeError`），基线同样存在。
- 4 条 FAILED 里 3 条是基线已知失败（`test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts`），第 4 条 `test_codes_kind::test_migration_is_safe_when_both_services_start_together` 是既有**偶发**（两次基线各出现一次）。
- 原始输出：`logs/pytest-baseline.txt` / `logs/pytest-branch.txt`。

---

## 11. 产物与证据清单

分支内（`/Volumes/臭垃圾桶/生财MCP/_worktrees/tupu360-fullsite`）：

| 路径 | 说明 |
|---|---|
| `pipeline-watch/tupu360-fullsite/tupu360-全站岗位-20260919.xlsx` | **交付表格**，5 sheet：全部岗位 5523 行 / 租户汇总 60 行 / 单元明细 180 行 / 排除名单 241 行（17 演示 + 224 零职位）/ 采集记账 |
| `pipeline-watch/tupu360-fullsite/tupu360-全站岗位-20260919.csv` | 同名主表导出（UTF-8 BOM，Excel 可直接打开），5523 行 × 20 列 |
| `pipeline-watch/tupu360-fullsite/inputs/` | 权威输入：`tupu_scope.json`(60/17/3)、`tupu_census.json`(301×3)、`tupu_tenants.json`(293 租户)、`tupu_census_analysis.json` |
| `pipeline-watch/tupu360-fullsite-run.py` | 可断点续跑的采集运行器 + 表格生成器（`--build-table` 可离线重建表格） |
| `pipeline-watch/RECEIPT-tupu360-fullsite.md` | 本说明书 |
| `pipeline-watch/deploy-artifacts/20260919g/` | 部署件（**未部署**），`shasum -a 256 -c SHA256SUMS.txt` = 8/8 OK |
| `qiuzhao/collector/p1_platform_companies.json` | `tupu360` 段 14 → 68 行（60 enabled + 8 disabled）；其余 section 零改动（216 insertions / 0 deletions） |
| `qiuzhao/collector/p1_platform_tupu360.py` | 分页硬截断修复 + `page_cap_hit` 诚实标注 |
| `tests/test_p1_platform_tupu360.py` | 35 个单测（+3 个分页深度断言） |
| `tests/test_collector_next_integration.py` | 公司数 953→1005、`TUPU360_ONLY` 扩到 57 个名字、`药明康德` 硬编码 setdefault 分支 |

工作区外（`/Volumes/臭垃圾桶/生财MCP/_worktrees/tupu360-fullsite-out/tupu360-fullsite/`）：

| 路径 | 说明 |
|---|---|
| `units/<slug>__<scope>/validated.json` | 180 个单元的 `collect()` + `validate_result()` 结果（表格的唯一数据源） |
| `units/<slug>__<scope>/*.html` | 原始证据：官方列表页 + 每个岗位的详情页（约 6,200 个文件，可逐条回溯） |
| `logs/unit-ledger.jsonl` | 每单元一行：状态 / 条数 / 请求数 / 耗时 / 错误 |
| `logs/run.log` | 完整运行日志（含第一段、重启、pass 边界、summary） |
| `logs/retry-probe.txt` | 三个重试目标的逐条探针证据 |
| `logs/pytest-baseline.txt` / `logs/pytest-branch.txt` | 基线与本分支的 pytest 摘要 |
| `table-summary.json` | 表格总账（units/jobs/requests/errors） |
