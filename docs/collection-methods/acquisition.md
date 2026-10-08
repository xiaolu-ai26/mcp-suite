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

**代码与验证**：[飞书 sites_for 与 source_coverage](../../qiuzhao/collector/p1_feishu_public.py)、[阿里官方入口](../../qiuzhao/collector/alibaba_headless.py)、[多入口收据](../../pipeline-watch/RECEIPT-multi-entrance.md)。

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


## 北森同一运行的完整列表复用（2026-10-09）

正式入口仍为 `deploy/windows_collector.py → p1_pipeline → p1_platform_beisen.collect`。同一 logical run、UTC 日、租户、配置入口/实际 Origin、PortalId、完整 POST 参数和配置文件 SHA 相同，才复用完整列表；仅存储 Code=200、Count 非负整数且各页一致、唯一 Id 数=Count、末页为空的原始响应。失败、截断、未知/重复 ID、新 run、参数或配置漂移均重新请求，不能冒充空成功。scope 独立分类、selected ID、分页与详情缺口证据照旧保存。

缓存命中后仍请求当前详情。核对 Id/CategoryId 后，以新详情的标题/职责等内容映射并绑定实际详情时间；缺字段显式记录 gap，冲突隔离，详情失败仅保留旧列表事实及旧列表时间。原始列表快照不变，不用缓存命中刷新 detail_checked_at。列表缓存是可丢弃优化，删除该 run 的独占缓存后按同一入口恢复；不修改 accepted 数据或运行预算。

隔离预览命令已用实际 `--help` 核验：`python -B -m qiuzhao.collector.p1_platform_beisen 'AIVA汽车' --scope campus --output-dir <独占目录> --max-requests 20`。此请求上限只适用于协议验证，不作为正式全量验收上限。正式流程设置 `QIUZHAO_P1_LOGICAL_RUN_ID` 与 `QIUZHAO_P1_DETAIL_CACHE_ROOT`；公司参数继续来自唯一 `p1_platform_companies.json`，不复制公司说明。

代表原始协议：2026-09-29 AIVA 官方原始 5 页，总 Count=174、唯一 Id=174、末页空；campus 历史 selected=172 是不同分母。私有 `beisen-original-protocol-validation.json` 绑定源路径与每页 SHA。北森+Moka 离线回归25通过；独审覆盖新详情内容变化、字段缺失、身份/类别冲突、失败保旧时间与 run/参数失配。Windows 实际 20,000 条/401 页探针核缓存落盘读取、真实 NTFS WinError5 保原及释放后新版本替换；峰值256,757,760 bytes 是含原行、序列化和读取副本的整个探针进程，不能等同 collector 峰值。缓存 O(列表大小)，没有全局常驻状态，scope 子进程退出释放；磁盘缓存沿现有 run 生命周期保留。

证据等级：受审代码、真实历史官方响应、Windows 隔离验证；尚不证明当前481名称全部完整、实际网络请求节约比例或当前自然 run 成功。当前状态仍只维护在日更正文。
