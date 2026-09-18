# RECEIPT: 外企补齐 C —— tupu360 平台适配器(20260919f)

分支 `feat/foreign-ats-c`(基于 `feat/collector-next-3` @ `2b123c2` = 精灵现役 `20260918k`),
worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-ats-c`
日期:2026-09-19 执行:DeepSeek Harness
范围:平台形态摸底(三种取法)+ `p1_platform_tupu360.py` 适配器 + 配置驱动 + 14 家只读实测 + 夹具单测 + 部署件 + 收据。
**未部署、未 SSH、未碰阿里云、未写飞书、未写库(`--apply` 未用过)、未读取/打印任何令牌、未登录、未绕过验证码/签名、未 push、未合并 main、未终止任何进程。**全部外呼都是公开只读 GET/POST,遵守每条 ≥2 秒间隔。

---

## 0. 一句话结论

tupu360(图谱天下)在外企里其实是**两个产品**:公开的 `careersite` 一族(服务端渲染、无需账号)
和微信专属的 `wxtemp` 一族(所有 HTML 路由都 302 到扫码页 + 微信 OAuth,公开侧无入口)。
适配器做成配置驱动、三 scope、三种取法(html / 站点自带 nextPageList / Playwright 兜底),
**14 家里 6 家实测可取**(IQVIA 艾昆纬、礼来、舍弗勒、宝马、茵梦达、强生),
**8 家公开侧确实拿不到**(6 家微信专属 + 德昌电机租户在但 0 条 + 科赴 slug 已停用),
按"测过才启用"的口径写入配置:`tupu360` 段 15 行(14 家公司 + 1 行说明),
其中 **6 行 enabled**(进入日更)、**8 行 `enabled: false`**(保留入口 URL 与原因,翻一个开关即可启用)。
默认集合 **948 → 953**(+5;强生因既有 Workday 条目同名,按 `setdefault` 不顶替,待站长定夺)。
三种取法**都实测成功**:html(渲染列表页)13 请求拿 12 条、api(站点自带 nextPageList)14 请求拿 12 条、
headless(Playwright 渲染后 DOM)13 请求拿 12 条;强生的列表路由被重定向到 SPA,**只有 api 一种能读**
(html 0 条 → api 1 请求拿 18 条),这是把 api 作为一等回退的直接证据。

---

## 1. 平台形态(公开侧实测)

### 1.1 两个产品族

| 族 | 入口形态 | 公开可读性 |
|---|---|---|
| **careersite**(公开) | `https://careersite.tupu360.com/<tenant>/position/index?recruitmentType=<TYPE>` | **可读**。服务端渲染整页职位列表;分页走站点自带的 `POST /<tenant>/position/nextPageList`(`offset`/`max`);详情页 `/<tenant>/position/detail?positionId=...`;`careersite.tupu360.com/` 根页还是一份**公开客户目录**(293 个租户 slug + 公司名),本次就是靠它确认哪些租户有公开站 |
| **wxtemp**(微信专属) | `https://<tenant>.tupu360.com/position/list?...` | **不可读**。任意已存在路由一律 `302 → /pageQrCode?targetUrl=<加密串>`,落地页文案"请用微信扫描二维码打开页面",页内 `targetUrlSpan` 只回显原始 URL;换成 `MicroMessenger` UA 则跳 `open.weixin.qq.com/connect/oauth2/authorize?appid=...`。**匿名公开侧没有任何入口**,适配器不登录、不做 OAuth,标 blocked |

补充事实:`<tenant>.tupu360.com/` 根路径也 302 到扫码页;`/position/listJson`、`/position/positionTotal`、
`/position/index` 同样被 302;不存在的路由(`/position/nextPageList`、`/api/position/list`)返回真 404
(说明拦截器只挂在存在的路由上,不是全站 WAF)。

### 1.2 频道(`recruitmentType`)

官方导航自报的取值:`CAMPUSRECRUITMENT`(校招)、`INTERNSHIPRECRUITMENT`(实习)、
`SOCIALRECRUITMENT`(社招)、`CAMPUSAMBASSADORRECRUITMENT`(校园大使)、
`TECHNOLOGYRUITMENT`(舍弗勒自己的自定义频道,注意平台侧就是少一个字母的拼写)。
适配器把 campus/intern/social 三 scope 映射到前三个,租户可用 `channels` 覆盖、
`extra_channels` 追加(舍弗勒 intern 就并入了 `TECHNOLOGYRUITMENT`,实测多拿 2 条不同的岗位)、
`CAMPUSAMBASSADORRECRUITMENT` 作为"主频道 0 条时才试"的兜底。

### 1.3 两种列表模板(必须都支持)

- **模板 A**:`div.position-list-header` 给**表头图例**,`div.position-item` 行的 `div.ele.e-*` 按顺序对应。
  **坑**:IQVIA 把 业务 / 职位类别 / 工作地点 三列复用同一个 `e-salary` class,按 class 取名会串列;
  适配器改成**按表头位置 zip**,不再按 class。发布日期在 `e-date` 列。
- **模板 B**:`div.position-item.event-vertical[pid]` 卡片,标题在 `.position-name .txt`,
  城市/职能/学历在 `li.ele` 里,`div.time` 是"发布于: YYYY-MM-DD",`card-header` 给"共N个职位"。
  卡片单元格是**租户可配的**:舍弗勒两颗 `e-city`(第二颗塞学历或 `data-original-title` 类别)、
  茵梦达用无 class 的 `li.ele` 放"公司ILD"、强生只有一行"工作地点：北京"且**没有任何 e-city**。
  适配器按"标签行 → e-city → 其余 li"三级解析,实测三类租户全部正确。

### 1.4 详情页

`div.position-description` 是职位描述(分享框 / 职位概况卡 / 投递按钮都是兄弟节点,必须切掉,
否则"立即申请"会混进描述);`input#positionName`、`input#positionStatus`(`PUBLISHING`=在招)、
`dl.position-extend` 的`发布时间 / 工作城市 / 职能类别`。**强生例外**:`/jnj/position/index` 与
`/jnj/position/detail` 都会被重定向到 hash 路由 SPA,公开侧**没有详情页**;J&J 的
`position-data.js` 只有 4 条宣传位、与列表 id 对不上,所以强生走 `"detail": "list"`,
`description_raw` 用**官方列表卡片原文**,`description_source` 如实标注。

---

## 2. 三种取法各自成败(实测)

通道探针 `pipeline-watch/tupu360-verify.py --channels-probe`,每单元独立预算 25、间隔 ≥2.2s。

| 取法 | 实现 | 实测 | 结论 |
|---|---|---|---|
| **① 带完整浏览器请求头的 requests 打页面自身的接口** | `html`(渲染列表页 + 站点自带 `nextPageList` 翻页)+ `api`(跳过列表页直接分页 POST `nextPageList`) | IQVIA campus `html` **success 12 条 / 13 请求 / 32.1s**;`api` **success 12 条 / 14 请求 / 34.8s**;舍弗勒 intern `html` **success 2 条 / 3 请求**;强生 campus `html` **blocked 0 条 / 1 请求**(列表路由被重定向到 SPA)、`api` **success 18 条 / 1 请求** | **选为默认**。`html` 最省事、可核对页面自身证据;`api` 是"列表页被 SPA 接管"时唯一读法,并顺手支持大频道分页(强生 social 322 条 4 次 POST 拿满) |
| **② 移动端 / H5 页** | 同一公开列表页换 iPhone Safari UA 重打 | IQVIA 51072 B / 12 行;礼来 47387 B / 15 行;茵梦达 38015 B / 3 行;舍弗勒 campus 46793 B / 0 行(**与桌面 UA 逐字节同一份文档**) | **没有独立 H5 站**。careersite 是响应式,移动 UA 拿到的是同一份服务端渲染 HTML;`wxtemp` 族的"移动端"就是微信内页,公开侧同样不可读。因此 H5 **不单列通道**,只作为 `html` 的 UA 变体记录在案 |
| **③ Playwright 无头浏览器,普通访客打开 + 读页面自身渲染结果** | `headless`(Chromium 直接 `goto` 公开列表页,`networkidle` 后读 DOM) | IQVIA campus **success 12 条 / 13 加载 / 43.9s**;舍弗勒 intern **success 2 条 / 2 加载 / 9.1s` | **可用但最慢**,作为最后兜底(默认关闭,`QIUZHAO_TUPU360_HEADLESS=1` 或 `fetch_channel='headless'` 才跑);对这两个租户它读到的行数与 `html` 完全一致,说明列表本来就是服务端渲染、不需要 JS |

> 适配器的默认阶梯是 `html → api → headless`;`fetch_channel=` 可把某一种钉死用于渠道验证
> (这个参数**只选取法,不选频道**,`recruitmentType` 永远来自配置——早期版本把两者混成一个
> 参数,已修并补了回归单测)。

---

## 3. 14 家实测表

口径:每 租户×scope 预算 ≤25 次请求、间隔 ≥2.2s;`status/complete` 来自适配器 `coverage`,
`发布/截止` 是字段可用率;`validate_result` 全部通过(42/42 单元 `validation_ok=true`)。

| # | 公司 | tenant / host | campus | intern | social | 请求 | 写入配置 |
|---|---|---|---|---|---|---|---|
| 1 | **IQVIA 艾昆纬** | `iqvia` @ careersite | success 12/12 · 100%/0% | success 5/5 · 100%/0% | success 12/12 · 100%/0% | 32 | **enabled** |
| 2 | **礼来** | `lilly` @ careersite | success 18/18 · 100%/0% | blocked 0(官方 0 条) | blocked 0(官方 0 条) | 24 | **enabled** |
| 3 | **舍弗勒** | `schaeffler` @ careersite | blocked 0(官方 0 条) | success 4/4 · 100%/0% | partial 20/70 · 100%/0%(预算所限) | 34 | **enabled** |
| 4 | **宝马** | `bmw` @ careersite | blocked 0(官方 0 条) | blocked 0(官方 0 条) | success 19/19 · 100%/0% | 26 | **enabled** |
| 5 | **茵梦达** | `innomotics` @ careersite | success 3/3 · 100%/0% | success 5/5 · 100%/0% | partial 22/36 · 100%/0%(预算所限) | 35 | **enabled** |
| 6 | **强生** | `jnj` @ chinacampus.jnj.com.cn | success 18/18 · 100%/0% | success 4/4 · 100%/0% | success 322/322 · 100%/0% | 9 | **enabled**(`detail:list`) |
| 7 | 德昌电机 | `johnsonelectric` @ careersite | blocked 0 | blocked 0 | blocked 0 | 7 | disabled(租户在,全部公开频道"共0个职位") |
| 8 | 雀巢 | `nestle` @ nestle.tupu360.com | blocked 0 | blocked 0 | blocked 0 | 0 | disabled(微信专属) |
| 9 | 太太乐 | `nestle` @ nestle.tupu360.com(同租户) | blocked 0 | blocked 0 | blocked 0 | 0 | disabled(微信专属) |
| 10 | 奥托立夫 | `autoliv` @ autoliv.tupu360.com | blocked 0 | blocked 0 | blocked 0 | 0 | disabled(微信专属) |
| 11 | 路易威登 | `louisvuitton` @ louisvuitton.tupu360.com | blocked 0 | blocked 0 | blocked 0 | 0 | disabled(微信专属) |
| 12 | 科赴 | `jntl` @ jntl.tupu360.com | blocked 0 | blocked 0 | blocked 0 | 0 | disabled(微信专属;对应 slug `kenvue` 已"停用") |
| 13 | Google 谷歌 | `google` @ google.tupu360.com | blocked 0 | blocked 0 | blocked 0 | 0 | disabled(微信专属) |
| 14 | 博世华域转向 | `boschhuayu-steering` @ boschhuayu-steering.tupu360.com | blocked 0 | blocked 0 | blocked 0 | 0 | disabled(微信专属) |

- **写入配置的条件**(任务书):status ∈ {success, partial} 且中国地区 ≥1 条 → 第 1~6 家满足。
  已核对:所有已采岗位的 `city/cities` **没有一条是海外**;强生 social/intern 的官方卡片
  **本身就不印城市**(只印标题 + 发布于),所以那 326 条 `city` 为空——这是页面事实,不是丢字段。
- **条数**:已采 464 行(去重前的 scope 计),其中强生 344、IQVIA 29、茵梦达 30、舍弗勒 24、宝马 19、礼来 18。
  舍弗勒/茵梦达 social 显示 partial 是**实测预算 25 所限**,生产不限预算时会拉全(舍弗勒 70 需 ≈76 请求,
  茵梦达 36 需 ≈42 请求,与其它平台适配器同量级);强生 social 因为走 `nextPageList` 分页 + 不请求详情页,5 个请求就拿满 322 条。
- **发布时间可用率 100%**(除无岗位的单元):模板 A 取自官方"发布日期"列/详情页"发布时间",
  模板 B 取自卡片"发布于: YYYY-MM-DD";`published_at_source` 逐条记录来源。
- **截止日可用率 0%**:这 14 家的官方页面**没有一条印截止日期**。按口径留空,`deadline_source='not published'`,
  正则 `_deadline_from_text` 只在正文真的写了"截止日期：YYYY-MM-DD"时才填。
- **届别不推断**:`cohort_raw` 恒为空;2027 这类年份只留在标题里,不写进届别字段。

---

## 4. 加一家的 SOP

1. 在 `careersite.tupu360.com/` 根页(公开客户目录)搜公司名,或直接试
   `https://careersite.tupu360.com/<slug>/position/index?recruitmentType=CAMPUSRECRUITMENT`:
   出现"职位列表"= 有公开站;出现"抱歉，该网站已停用"= 只有微信站。
2. 打开 `p1_platform_companies.json` 的 `tupu360` 段,加**一行**:
   ```json
   "acme": {"name": "某某公司", "note": "careersite tenant; verified 2026-09-19."}
   ```
   可选字段:`host`(默认 `careersite.tupu360.com`)、`tenant`(公司 key 与租户 slug 不同名时,
   例如太太乐共用 `nestle`)、`channels`(覆盖某 scope 的 `recruitmentType`)、
   `extra_channels`(把官方附加频道并进某 scope)、`detail`(`list` = 该租户没有公开详情页,
   用官方列表卡片原文当描述)、`scope`(把租户钉死在单一频道)、`url`(覆盖证据 URL)、
   `enabled: false` + `blocked_reason`(调查过但公开侧拿不到,保留不启用)。
3. 跑一次 `python pipeline-watch/tupu360-verify.py --out <外接盘目录> --companies acme`:
   看 `status/complete/发布率/截止率`,并确认 `validation_ok=true`。
   只有 `status ∈ {success, partial}` 且中国地区 ≥1 条才留在 enabled。
4. 若列表页 0 条:先看 `coverage['note']`(是"官方 0 条"还是"微信专属"),再决定写 disabled 还是
   换 `channels`/`extra_channels` 重试;必要时用 `--channels-probe` 单测三种取法。
5. 新公司**不需要**改 `p1_pipeline.py`:注册块已就位,`merged_registry()` 会把它并进 `REGISTRY`;
   同名冲突时 `setdefault` 保证不顶替既有适配器。

---

## 5. 契约与单测

- 契约与其他平台适配器一致:`collect(company, scope, output_dir, max_requests=None, fetch_channel=None, include_disabled=False)`
  → `{jobs, coverage}`;`merged_registry()` / `resolve()` / `reload_config()` / `site_url()`;
  证据文件写在 `output_dir`(列表页 HTML + 每岗位详情页 HTML),`coverage` 带
  `channel_evidence / channels_used / list_observed_ids / request_budget / scope_evidence`。
  `p1_pipeline.validate_result` 在实测中对 42/42 个单元全部通过。
- 单测:`tests/test_p1_platform_tupu360.py` **32 个**(夹具全部是本次录制的真实公开页面,
  不联网),覆盖:配置契约(enabled/disabled、`_README` 跳过、14 家、6 enabled)、
  `is_wechat_only`/`tenant_slug`/频道与附加频道、模板 A 的**按位置取列**(IQVIA 同 class 三列)、
  模板 A 分页与"共N页"、模板 B 的 pid/标题/城市/职能/招聘人数/发布于、模板 B 的租户标签城市
  ("城市上海"→"上海")、模板 B 的**标签行城市**(强生"工作地点：北京")、卡片原文不漏 HTML、
  详情页 A/B 两种模板、`_iso_date`/`_deadline_from_text` 不臆造、`collect()` 全链路(列表+翻页+详情)、
  `detail=list` 模式不请求详情页、`fetch_channel` 钉取法不钉频道、api 兜底、微信租户 0 请求 blocked、
  官方 0 条 blocked、预算耗尽 partial、`headless` 不可用降级不崩、disabled 行需要显式审计开关。
- 全量:`pytest tests/` 在本分支跑两次:一次 **3 failed, 525 passed, 55 skipped**,
  一次 **4 failed, 529 passed, 55 skipped**(多出来的是任务书点名的**偶发** `test_codes_kind::
  test_migration_is_safe_when_both_services_start_together`,单独重跑 `tests/test_codes_kind.py`
  = **22 passed**,与本批改动无关)。
  基线 `feat/collector-next-3` @ `2b123c2` 两次均为 **3 failed, 498 passed, 55 skipped**,
  失败清单逐条相同(`test_core::test_role_cohort_and_campaign_title_bases`、
  `test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、
  `test_schema::test_enum_check_fails_when_data_drifts`),**新增失败 0**(+27~31 passed = 32 个新单测减去同步改动的既有断言)。
- 同步改动的既有测试(必要,非绕过):`tests/test_collector_next_integration.py`
  家数断言 948 → 953、`CONFIG_SECTION_MODULES` 加 `tupu360`、
  `_declared_config_names()` 跳过 `_` 开头的说明键与 `enabled:false` 行、
  新增 `SETDEFAULT_SECTIONS=('feishu','tupu360')` —— 因为本批注册块用 `setdefault`,
  允许"声明了同名但不顶替"这一**已文档化**的行为;断言依旧会抓住真正的顶替
  (被 shadow 的名字必须仍指向原 section 的模块)。

---

## 6. 部署件 `pipeline-watch/deploy-artifacts/20260919f/`

| 文件 | 目标 | 类型 | SHA256(前 12) |
|---|---|---|---|
| `p1_platform_tupu360.py` | `qiuzhao/collector/` | **新增** | `51a109901822`… |
| `p1_platform_companies.json` | `qiuzhao/collector/` | 覆盖(现役全文 + 新 `tupu360` 段) | `23dc725543bf`… |
| `p1_pipeline.py` | `qiuzhao/collector/` | 覆盖(= 20260918k 全文 + 1 个追加注册块 + 3 处纯新增行) | `8c459167d6fd`… |
| `test_p1_platform_tupu360.py` / `test_collector_next_integration.py` / `fixtures/tupu360/*.html`(10 个) | `tests/` | 可选(仅测试) | 见 `SHA256SUMS.txt`(15 条) |

- **叠加顺序**:直接叠在 **`20260918k`(精灵现役)之后**,整文件覆盖。本包基线
  `feat/collector-next-3` @ `2b123c2` 与 20260918k 的 `p1_pipeline.py` **逐字节相同**,
  所以本包 `p1_pipeline.py` 可直接覆盖,不需要其它补丁。详见 `DEPLOY-NOTES.md`。
  若后续先叠加 `20260919b/c/d/e`,请改走整合分支的累积部署件——`p1_pipeline.py` 与
  `p1_platform_companies.json` 是多任务共同修改的文件,逐个叠加会互相覆盖。
- `shasum -a 256 -c SHA256SUMS.txt` = **15/15 OK**;三个运行时文件与分支源码 `cmp` **逐字节一致**;
  9+1 个夹具与 `tests/fixtures/tupu360/` 逐字节一致。
- **本包未部署**:未 SSH、未覆盖精灵、未碰阿里云、未 push、未合并 main。

---

## 7. 请求记账与硬约束

| 阶段 | 公开只读请求 | 说明 |
|---|---|---|
| 平台形态摸底(robots / 客户目录 / 模板 / 接口定位 / CDN JS / 候选 slug 扫频) | ≈120 | 间隔 ≥2s;`careersite.tupu360.com/` 根页的客户目录是发现租户的关键 |
| 实测第 1 轮(跑到第 7 家时脚本在 disabled 行抛错中止) | 158 | 缺陷已修(`include_disabled` 审计开关) |
| 实测第 2 轮(全量 42 单元) | 167 | 平均 4.0 次/单元 |
| 实测第 3 轮(全量 + 三取法探针 47 + 移动 UA 探针 4) | ≈218 | 探针数不计入单元素预算 |
| 强生修复后重测(3 单元) | 9 | 模板 B"标签行城市"修复后复核 |
| **合计** | **≈672** | 全部 GET/POST 公开页面,无登录、无 cookie 复用、无签名、无验证码 |

- 每 租户×scope 预算 **25**(实测硬上限,`request_budget` 逐单元记录;中位数 1.0、最大 25);
  单测里逐条断言过预算生效(`max_requests=2` → partial + `detail_complete=false`)。
- 间隔:实测 `QIUZHAO_PLATFORM_REQUEST_INTERVAL=2.2`(≥2s 要求);摸底脚本逐请求 `sleep 2.2`。
- 每租户总请求(全 scope,含探针):IQVIA 32+27、礼来 24、舍弗勒 34+5、宝马 26、茵梦达 35、强生 9+2、德昌电机 7;
  微信专属 6 家 **0 请求**(在 `is_wechat_only` 分支直接返回,不发任何外呼)。
- 硬约束核对:未部署 ✅ 未 SSH ✅ 未碰阿里云 ✅ 未写飞书 ✅ 未写库(未用 `--apply`) ✅
  未读取/打印令牌 ✅ 未登录/未做 OAuth ✅ 未绕验证码/签名 ✅ 未 push ✅ 未合并 main ✅
  未 `git stash` ✅ 未终止任何进程 ✅(唯一被"终止"的是本会话自己超时的 `git worktree add`,属工具默认超时,非人为杀进程)。

---

## 8. 遗留

1. **robots.txt 合规待站长拍板(最重要)**:`careersite.tupu360.com/robots.txt` 与每个租户 host
   都返回 `User-agent: * / Disallow: /`(平台级一刀切声明,`tupu360.com/robots.txt` 301 到同一份)。
   本轮按任务书只做公开只读、不登录、不绕验证码,并保留预算与 ≥2s 间隔;但**是否长期日更**
   需要站长按 robots 声明决定。若要严格合规,把 6 行 `enabled` 改成 `false` 即可,代码不用动。
2. **强生同名冲突**:`强生` 已被既有 `workday` 条目 `jj/wd5/JJ` 占用,本批按 `setdefault` 不顶替,
   所以 tupu360 的 18 条校招 + 322 条社招**当前不会进日更**。建议站长定夺:若认可 tupu360 是更真实的
   来源,删掉 `workday` 段的 `jj/wd5/JJ` 一行即可交接(该 workday 条目是外企二批按猜测租户名写的,
   且外企发现收据里"Workday 租户名猜测不命中 142").
3. **8 家 blocked 里最值得回头看的**:
   - 德昌电机 `johnsonelectric` 租户公开站在、但三个频道都"共0个职位",发布时会自动恢复(改回 enabled 即生效);
   - 科赴 `kenvue` slug 已"停用",若平台给它换 slug 需重新找;
   - 另外 6 家是 wxtemp 微信族,除非站长愿意提供**站长的微信登录态**(任务书明确不允许本轮做),
     公开侧无解;不要尝试伪装 UA / 走 OAuth,那会违反"不登录、不伪造"的约束。
4. **舍弗勒/茵梦达 social 的 partial 是实测预算造成**:生产不限预算即可全量(70 / 36 条);
   若站长想控制每日请求,可给这两家写 `"scopes": ["campus","intern"]` 之类的窄化开关
   (适配器已支持,`p1_pipeline._load_scope_opt_ins` 已把 `tupu360` 段纳入)。
5. **强生 social/intern 没有城市**:官方卡片本身就不印,库里会是空 `city`;若站长要地点筛选,
   需要另找官方来源,本轮不推断。
6. **`careersite` 客户目录里还有 280+ 个未核租户**,其中外企不少(西门子/西门子医疗/赛诺菲/辉瑞/
   康明斯/索尼/采埃孚/太古地产/阿斯利康/丹佛斯/科莱恩/费森尤斯…)。本批按任务书只做点名的 14 家,
   目录已记录在收据与 `summary.json.facts`;下一批可以直接按 SOP 加行。
