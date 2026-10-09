# 获取与入口选择

最后验证：2026-10-01（源码与历史证据核对）。先判断来源能否公开访问、范围能否证明、是否要完整存量，再选择协议。请求量、浏览器资源、存储与平台额度都计入预算；这里没有新增付费 API 或模型调用。

## A1 接口 / JSON 分页

**输入与选型**：有官方公开接口、稳定记录 ID、总数或可证明末页的目录；适合大列表。分页字段可能是 offset、page 或 cursor，必须按实际契约确认，不靠返回 HTTP 200 判成功。

**步骤**：确认主体/租户/范围 → 保存请求参数与第一页响应 → 去重累计官方 ID → 按 total 与实际 offset 继续翻页 → 保存末页或 reached_total 证据 → 请求详情并独立记录失败 → 请求/时间预算用尽时输出 partial 与已采子集。总数变化、重复页、异常空页或 schema 改变都须重新判断完整性。

**代码与验证**：[Workday collect、_list_page、_detail](../../qiuzhao/collector/p1_platform_workday.py)，[回归夹具与测试](../../tests/test_p1_platform_workday.py)。源码记录 `list_total`、`list_observed_ids`、`pagination_exhausted`、`last_page_evidence` 和请求预算；无可证明 scope 的零匹配仍可能 blocked。

**失败反例**：到页上限就标完整；关键词零匹配就宣布官方无该类记录；total 与唯一 ID 数不一致却按原始行数验收。

**验收**：范围绑定正确；唯一 ID 数与可信 total 相符，或有末页证据；详情失败单列；预算耗尽 complete=false。**费用/登录**：公开 HTTP 的带宽与计算成本；受登录、签名或访问限制阻断时保存原因，不凭空构造凭据。

## A2 网页列表 / 详情

**输入与选型**：公开 HTML 包含目录链接、官方页面结构可稳定定位；没有可用 JSON 接口时使用。适用于公告、文章、商品及岗位目录。

**步骤**：保存入口 HTML → 将相对链接解析为绝对官方 URL → 校验链接确为详情而非导航 → 逐页抓列表并保留原始标题/ID → 提取正文与原始字段 → 分离列表已发现、详情请求失败、详情未披露字段 → 交给统一结果校验。不得把门户标题或导航文字当记录标题。

**代码与验证**：[51job 适配器](../../qiuzhao/collector/p1_platform_51job.py)、[51job 回归](../../tests/test_p1_platform_51job.py)、[tupu360 适配器](../../qiuzhao/collector/p1_platform_tupu360.py)。运行实证见运营正文第 4、6 节：51job 假标题与证据修复进入定向补采；不推广为所有 HTML 站点均已验证。

**失败反例**：只抓首页；抓到站点名字作为标题；详情失败拿摘要冒充完整正文；重复 URL 跨范围误合并。

**验收**：已发现 ID 有列表证据；正文来自对应官方详情；页尾完整性与详情完整性分别可核；缺字段写未披露或待核。**费用/登录**：公开页面请求与本地解析；robots、WAF、微信专属或登录入口须按已有来源政策处置，未知条件保持 blocked。

## A3 浏览器渲染与串行资源

**输入与选型**：公开 SPA 由页面生成会话 cookie/CSRF，或需浏览器 SDK 才能取列表；只有 HTTP 适配器确实不适用时选择。浏览器是稀缺共享资源。

**步骤**：用匿名上下文打开已验证入口 → 等待页面身份与 SDK 就绪 → 核验租户名称/ID → 捕获真实请求参数而非猜 portal_type → 在同一上下文取分页和详情 → 保存身份、列表、详情证据 → 定期 checkpoint → 释放资源。浏览器锁串行；记录锁等待、本地启动失败、远端超时、预算截断四类原因。

**代码与验证**：[HeadlessSource](../../qiuzhao/collector/base_headless.py)、[匿名飞书 collect_feishu](../../qiuzhao/collector/p1_feishu_public.py)、[飞书回归](../../tests/test_p1_feishu_public.py)、[Windows 锁实现](../../qiuzhao/collector/portable_runtime.py)。当前飞书锁等待有 120 秒界限；有界排队优化属于待实现建议，不写成已经修复。

**失败反例**：通过提高同平台并发解决锁竞争；多个逻辑 run 同时使用 writer；以本地 busy 推断供应商不可用；租户页面漂移仍沿用旧身份。

**验收**：身份吻合；全部站点状态分别可见；锁超时不会伪造 complete；pending_details 保留；进程退出释放资源。**费用/登录**：本地 Chromium CPU/RAM 与下载成本；现有 HeadlessSource 不登录、不解验证码、不复用私人凭据。新浏览器流程需另行确认访问契约。

## A4 RSS / Atom 条件获取（AIHOT 参考未实施）

**输入与选型**：发布者提供 feed，目标是持续新增资讯而非证明全部存量。feed 窗口不能证明历史全集或条目删除。

**步骤**：确认 feed URL → 区分 RSS/Atom/RDF → 解析单项/数组、CDATA/XHTML、alternate 链接、日期 → 基于来源配置与响应 URL 绑定 ETag/Last-Modified → 条件请求 → 提取摘要与正文状态 → 正文仅为 teaser 时保留 pending 再取详情 → 成功处理后才推进游标。304 仅说明对应验证器下响应未改，不证明详情新鲜或全库完整。

**代码指针**：AIHOT `packages/backend/src/sources/rss.ts` 的 `fetchRss`、`isTeaser`、`RssValidator`；`sources/collect.ts` 的采集与游标推进。固定快照见索引。

**案例等级**：本次读取参考源码；本项目没有 RSS 运行收据或回归验收。**失败反例**：用 feed 最新若干项下架旧记录；摘要当正文；配置变更还沿用旧验证器；照搬资讯评分过滤到完整目录。

**验收（未来接入时）**：构造 RSS/Atom 单项与多项、相对链接、teaser、304、配置变化及失败游标测试；公开供应商单次验收另记。**费用/登录**：公开 feed 无须模型调用；运行带宽仍有成本；不继承 AIHOT 的付费评分或外部登录流程。

## A5 可访问的官方多入口

**输入与选型**：同一主体的 campus/social、子站或地区入口互补；需要覆盖多个数据范围。每个入口都应有官方链接出处与租户证据。

**步骤**：建立主体+范围+站点集合+租户标识单元 → 保存官方入口出处 → 逐入口验证匿名可访问与分类语义 → 分别统计 total/分页/失败 → 同范围以官方 ID 合并 → 缺入口时保留部分状态 → 新入口先隔离，小批启用后按实际 run 验收。

**代码与验证**：[飞书 sites_for 与 source_coverage](../../qiuzhao/collector/p1_feishu_public.py)、[阿里官方入口](../../qiuzhao/collector/alibaba_headless.py)、历史 `RECEIPT-multi-entrance.md`（当前公开树未收录，不作为可复查仓库证据；需从私有历史档案另核）。

**失败反例**：REGISTRY.update 静默覆盖原适配器；平台相同就当租户相同；第二入口重复记录按新主体宣传；无公开范围仍靠标题猜分类。

**验收**：每入口有独立证据；主体不冲突；合并后 ID 去重可解释；未支持与确证为空分开。**费用/登录**：入口数量增加请求和浏览器预算；登录、签名、WAF 入口不自动采用。新租户的 robots 决策遵循项目既有准入政策。

## 2026-10-08 平台 SOP 绑定（代表样本，不是全来源验收）

以下三条复用现有 A1/A2/A3，不增加每家公司流程。正式调用仍通过 `deploy/windows_collector.py::steps_for → p1_segment_args → p1_pipeline.main → adapter.collect`；新增公司只提供同平台租户参数。当前部署的三模块与 main bcae 对应源码逐字节一致，逐件 SHA、配置参数、静态字段表达式与测试路径在私有 `phase-20261008/method-bindings.generated.json` 中。9/29 原始小样本从 Windows 只读复制，样本及官方响应共约 92 KiB；历史执行时的全依赖字节关联尚未补齐，不能把当前 SHA 倒填成历史版本。

| 方法与平台 | 参数与代表实证 | 字段来源与边界 | 回归 |
|---|---|---|---|
| A1 Workday CXS | 配置节 workday，key=`3m/wd1/Search`，search_text=China，max_list_pages=8；9/29 3M/intern：1 条，coverage success/complete/detail_complete | `_job` 的 info.id/externalPath→身份、title→标题、jobDescription→正文、location/additionalLocations→城市；startDate/endDate→发布日期/截止；cohort_raw留空。教育/专业来自共用原文提取，不补猜届别 | [test_p1_platform_workday.py](../../tests/test_p1_platform_workday.py)，已核 workday_list_offset0/20、detail_campus/intern JSON 夹具 |
| A2 51job 微站 | 配置节 job51，key=pepsico2027，url为配置内官方 campus 微站，scope=campus；9/29 百事/campus：3 条，coverage success/complete/detail_complete | `parse_postings` 的 CtmID→身份/投递链接，投递锚点前条目文字→标题，公告+条目块→description_raw。代码的 detail_complete 表示微站文本契约，**不能证明有独立岗位详情全文**；发布时间/截止/届别不推断，详情语义是否足够列入阶段C | [test_p1_platform_51job.py](../../tests/test_p1_platform_51job.py)，已核51job_pepsico.html与无列表反例 |
| A3 飞书公开站 | 配置节 feishu，key=intellicrane，site为配置内 /mhdl，tenant_names=[Uni-MIND]，portal_type=6；9/29 Uni-MIND/intern：1 条，coverage success/complete/detail_complete | `collect_feishu` 核website租户、detail.id/recruit_type匹配；title→标题，description+requirement→正文，city_list/required_degree/target_major_list→城市/教育/专业；缺失字段显式记录。支持多入口不等于每公司已完成A5绑定 | [test_p1_feishu_public.py](../../tests/test_p1_feishu_public.py)，内置假SDK/响应回归，详情空值、失败与跨站冲突反例 |

执行 SOP：先核官方入口、租户与scope配置；依上述平台同入口获取列表并保留 total/末页/唯一ID证据；逐岗位取详情或明确微站文本限制；由 `p1_pipeline.validate_result` 校验身份/来源/分类/完整性，再进入统一归一化与发布链。临时只读预览可使用 `python -m qiuzhao.collector.p1_pipeline --adapter <真实模块路径> --company <已登记名称> --scope <配置范围> --output-dir <隔离目录>`；此入口仍访问上游，不属于离线测试，退出0也不能替代coverage验收，本阶段没有执行。

失败恢复：保留result、pending_index、scope请求和原始响应，预算截断记partial；未知分类/租户不符/异常空页保持blocked或隔离；列表不完整不得下架。修复先回归对应样本，再从原run/checkpoint恢复，遵守[恢复与发布](recovery-and-publication.md)的单writer、原截止与CAS规则；不得新预算冒充旧日成功，不用历史success_flag替代服务器接受回执。

本轮在 bcae 上真实运行上述三个测试文件：**46 passed，0 skipped**（0.44s，私有 platform-regression.log）。这证明现有离线回归，未运行新网络采集；三份代表样本、三个SOP及当前代码指针已固定，完整成功方法标准中的历史正式版本关联、每公司字段语义及当前完整性仍待B/C补证。每日数量只维护日更正文。


<a id="beisen-sop"></a>

## 北森同一运行的完整列表复用（2026-10-09）

正式入口仍为 `deploy/windows_collector.py → p1_pipeline → p1_platform_beisen.collect`。同一 logical run、UTC 日、租户、配置入口/实际 Origin、PortalId、完整 POST 参数和配置文件 SHA 相同，才复用完整列表；仅存储 Code=200、Count 非负整数且各页一致、唯一 Id 数=Count、末页为空的原始响应。失败、截断、未知/重复 ID、新 run、参数或配置漂移均重新请求，不能冒充空成功。scope 独立分类、selected ID、分页与详情缺口证据照旧保存。

缓存命中后仍请求当前详情。核对 Id/CategoryId 后，详情明确披露的新内容优先；GET DTO缺键/null/空数组不能证明招聘方清空，保留同一 run 已验证列表事实及原时间，并区分详情缺字段、整个来源缺字段与两个来源差异。新 Require不拼接旧专业条件，学历只在明确硬下限与条款语义支持时主展示，等效资格/偏好/无法可靠解析保留全文及公开说明。字段来源、各自时间和旧 Degree通过既有detail_presentation/status_note可查；未修改全局normalize/carry-forward。详情失败仅保留列表事实及旧时间。原始快照不变，不用缓存命中刷新 detail_checked_at。列表缓存是可丢弃优化，删除该 run 的独占缓存后按同一入口恢复；不修改 accepted 数据或运行预算。

隔离预览命令已用实际 `--help` 核验：`python -B -m qiuzhao.collector.p1_platform_beisen 'AIVA汽车' --scope campus --output-dir <独占目录> --max-requests 20`。此请求上限只适用于协议验证，不作为正式全量验收上限。正式流程设置 `QIUZHAO_P1_LOGICAL_RUN_ID` 与 `QIUZHAO_P1_DETAIL_CACHE_ROOT`；公司参数继续来自唯一 `p1_platform_companies.json`，不复制公司说明。

代表原始协议：2026-09-29 AIVA 官方原始 5 页，总 Count=174、唯一 Id=174、末页空；campus 历史 selected=172 是不同分母。私有 `beisen-original-protocol-validation.json` 绑定源路径与每页 SHA。初版缓存北森+Moka 离线回归25通过；字段融合增量独审北森37+平台Moka9=46通过，Windows北森37+缓存Moka11=48通过，实际collect→证据校验→merge→normalize→V4→公开详情链核教育替代/硬下限与DTO地点保留。有限资格规则不保证任意语言全部结构化，当前cfg组合另含3个租户分类反例；不将不同集合数互换。Windows 实际 20,000 条/401 页探针核缓存落盘读取、真实 NTFS WinError5 保原及释放后新版本替换；峰值256,757,760 bytes 是含原行、序列化和读取副本的整个探针进程，不能等同 collector 峰值。缓存 O(列表大小)，没有全局常驻状态，scope 子进程退出释放；磁盘缓存沿现有 run 生命周期保留。

证据等级：受审代码、真实历史官方响应、Windows 隔离验证；尚不证明当前481名称全部完整、实际网络请求节约比例或当前自然 run 成功。当前状态仍只维护在日更正文。


北森租户分类补例（2026-10-09）：神州数码集团 `digitalchina` 历史官方原 list0/list3 明确 CategoryId4“AI专项招聘(社招)”与5“AI专项招聘(校招)”，配置只增加4→social、5→campus，默认1社招/2校招/3实习保留。私有 `beisen-scope-evidence.json` 绑定10份原文件SHA、PortalId/租户/Id/标签；历史源码关联unknown。代表页控制回归不冒充原Count355完整回放，名称与3372计划键不变。

迅销4/5/7为技术研发/项目管理/系统运维职能，津电4的Category为JSON null，均不能强归社招；代表raw无独立可用招聘性质字段。未知仍partial，未观察实习类别不等于不适用。租户配置映射需官方语义，供应商默认数字不能代替该租户验收。


<a id="platform-sop-execution"></a>

## 平台 SOP 执行与证据绑定（2026-10-09）

**执行顺序**：先检查配置中的注册名称、租户 host、入口与类别映射，核当前受审文件 SHA；随后用已有隔离证据回归，再由执行 owner 按正式运行入口安装与验收。文档内的预览命令会访问官方站点，只在已授权的来源探针任务中执行；本次整理没有运行它们。`--max-requests 20` 是诊断上限，达到上限的 partial 不能算正式完整。

北森公开入口 HTML 提取唯一 `PortalId`，实际 Origin 来自响应 URL；列表 POST 为 `/api/Jobad/GetJobAdPageList`，参数 `PortalId/PageIndex/PageSize=50/Category=[]/KeyWords/SpecialType/DisplayFields` 由代码和唯一配置生成。`Code=200`、各页 Count 类型与一致性、唯一 Id=Count、终止空页均满足才写完整缓存。`_annotate_fields` 将 JobAdName→标题、Duty/Require→正文、地点/学历等官方字段及各自列表/详情时间写入公开说明；实际映射仍以源码为准，不在这里复制 DisplayFields 全表。恢复时失效缓存可丢弃；失败不写完整缓存、不推进最后完整时间、不改原预算。

字段融合独审 `beisen-field-independent-final-review.json` 绑定适配器 `22efbcc54e69add1365f9e6370851b02651cc06ad25c04064873f8bd101b7612`；其 46 项为北森37+平台Moka9，`beisen-field-windows-regression.json` 的48项为北森37+缓存Moka11。20,000行缓存探针属于较早缓存字节 `676cb0a3…`，不能把该探针 SHA 写成字段融合最终版。成功案例、参数/run miss、真实 NTFS 替换拒绝保留原文件见 `beisen-windows-cache-result.json`；峰值是整个探针进程。已存在的跨平台 Moka 详情缓存策略与北森同 run **列表**缓存是不同优化，不合并统计。

可离线复验入口：`python -B -m pytest -q tests/test_p1_platform_beisen.py tests/test_grok47_moka_cache.py`。先保证真实 fixtures/core 依赖完整，中文 JSON 显式 UTF-8；不得通过 deselect、改断言或放宽容量门制造通过。回归通过后仍需部署身份与自然 run 的真实完整性收据。TLS 本轮只有只读诊断及一次瞬态重试成功的证据，尚无统一自动修复，不在此作为已验证恢复方案。

<a id="boc-sop"></a>

## BOC 公开 campaign 目录与适用共同条件（2026-10-09）

**入口与执行**：[Collector.boc](../../qiuzhao/collector/run.py) 合并原公告角色与 [collect_campaign](../../qiuzhao/collector/chinahr_public.py) 的原生目录。公开配置常量 `BOC_CAMPAIGN_PAGE` 指向 `https://campus.chinahr.com/pages/2027-boc/`；campaign 名、共同条件标题与集团名传给 `collect_campaign`。没有新增 company-scope，不改变正式 basic→发布链。隔离来源调用为 `python -B -m qiuzhao.collector.run --source boc --output-dir <新建独占目录> --delay 1.25`，该入口会取上游并在输出目录合并数据，**不是只读测试**；禁止指向生产 data 或已有 run 代替受控恢复。

**具体协议**：读取公开页面的实际 campaign bootstrap → 校验 campaign 与共同条件标题 → `https://ats.chinahr.com/api/company/list` 取目录 → 遍历已核层级下的叶选择器 → `/api/job/list` 按 `companyId/page/pageSize=10000/callback` 分页。页面选择器在运行中使用，证据与错误输出不保存它。各页 totalCount 必须为非负整数且一致；唯一原生 ID 数等于 totalCount 才停止，100页安全上限、早空页、重复、孤儿或更深层级都留下 partial，不推进完整性。

**字段来源与共同条件**：原生 id→`boc-ats-`稳定身份；name→标题；列表内 `jobDesc` 是官方嵌入正文，不另称已请求独立详情；workPlaceList→披露地点；education/experience/jobNo→原始字段；applyEndTime→有证据的截止；投递入口由原生 ID 构造。只有正文明确引用共同条件标题，且 `conditions_for` 对单位标题唯一匹配、专门岗位条款与岗位名精确唯一匹配，才附适用条件。没有精确匹配时保留嵌入正文与待核说明，detail_complete=false；禁止把总部条件借给分支、通用角色标题或未知专门岗位。

**粒度与反例**：14个历史公告角色 ID 保留并公开粒度说明；它们不计入原生目录完整性分母。原生缺席退役只在 `boc-ats-`命名空间且符合既有门时适用。重复单位标题、泛化岗位名、跨选择器相同 ID 但字段冲突、截断树/列表均不能称完整。

**验收与恢复**：先跑 `python -B -m pytest -q tests/test_chinahr_public.py tests/test_collector_partial_keep.py tests/test_guopin_auto_campaigns.py`；Windows 使用本次解释器 `-X utf8`或显式UTF-8读取，不改全机编码。逐 leaf 核 expected_total/observed_unique_ids、listing_complete 与条件缺口；失败保留有效原生行、公告角色及错误证据，从原正式 run 的预算/锁入口恢复，不直接重写 accepted。公开样本只证明历史266节点目录和一个leaf岗位；代表夹具的4节点/1岗位不代表完整266树。

**版本与证据**：`boc-independent-review-round2.json`、`boc-independent-utf8-review.json`、`boc-windows-regression.json`；适配器 `f91ab486b8534e96dee19e59030bf7780fcd76a0d339cd6f33db5560e5424d1d`、run `4672f6d4…`。独审 Mac 三文件67通过/7项原容量门失败，Windows完整同三文件74通过、0失败/skip/deselect；二者不能互相改写。UTF-8增量审查未重跑完整Windows业务，完整执行由Windows收据证明。未证明生产安装或全campaign当前完整。公开HTTP与本地计算成本，无登录、投递或新付费API；不公开项目选择器和私有原始响应。

<a id="liauto-sop"></a>

## 理想汽车外包枚举的严格映射（2026-10-09，已合入未生产验收）

**版本边界**：下述新规则来自已独审并合入 PR39 的实现 `p1_sources_31_40.py` SHA `ad4f88152f1b943907f8008bf6e7b6cfaaa814f8205ca5619f77ddc44ed50fe7`，对应测试 `634221fa5c5420f6605f375a3a842dd75e25c39b80a8c190ff25fc5c45a21cd8`；PR39 已合入，merge `a2f40003b89981b58ec7466b5a3a52b939b4bec7`、head `468c0b0da68d1b82ef4c56eb1da3acb9590bcbf8`。已核仓库 [现有模块入口](../../qiuzhao/collector/p1_sources_31_40.py) 与上述受审 SHA 一致；已合入不等于生产安装或当前全公司完整验收。

**入口与参数**：正式 `p1_pipeline → p1_sources_31_40.collect → collect_lixiang`，公司登记参数保持理想汽车/lixiang与原scope。公开入口 `https://www.lixiang.com/employ/campus/list.html`；`api-web.lixiang.com/osd-hr-recruitment-website/v1/recruit/{school|social}/job-page` 使用 page/page_size=50，分别校验两个通道的total_count、page/total_pages与唯一ID；详情 `/v1/recruit/job/detail?job_id=<列表ID>`。隔离模块调用 `python -B -m qiuzhao.collector.p1_sources_31_40 '理想汽车' social <新建独占目录>` 为网络探针，非离线验收，本次未执行。

**字段与严格门**：列表和详情均先校验分类。仅当原始 job_mode是字符串`"102"`、hire_mode是严格int1（排除bool/字符串）、job_mode_name精确为“外包”，才把该租户枚举映射为social。numeric102、冲突label、不同类型均拒绝；该门先于其它标签，不能以“实习”等标签绕过。原101/201/202规则保持，不推广102到其它公司。详情id与scope须匹配；title、description+requirements、location_title来自对应详情。外包披露写入 description_raw/detail_presentation/status_note/source_fields，明确具体用工主体未披露，不能认定公司直聘；不捏造雇主。

**样本、反例与恢复**：既存官方详情20237的raw SHA `93c049e3705a1c97f43dd1a4d8651e2b0e3a4bf711db87626b50ff3add58fda6`仅证明该单个枚举组合，不证明当前15岗位全量。错误中的45字符串是3个键×15观察，不是45家公司。未知枚举留下errors/partial，列表不足不得下架，详情失败保留对应证据，不推进完整游标；按原run、deadline与单writer恢复，不用新预算抵销原失败。

**验收与成本**：`python -B -m pytest -q tests/test_p1_sources_31_40.py tests/test_p1_platform_beisen.py`；独审 `liauto-independent-review-round2.json` 和隔离 `liauto-windows-regression.json` 均50通过+22subtests（subtests不算另22个顶层test）。实际collect数字102反例在列表与详情均拒绝，公开投影保留外包说明。受审实现已合入，仍未生产安装、未当前全公司完整验收。公开HTTP与计算成本，无登录/投递、新API计费；raw私有证据不复制进方法库。
