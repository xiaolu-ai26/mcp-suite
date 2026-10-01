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
