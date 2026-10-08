# 证据、完整性与身份

最后验证：2026-10-01（源码与测试内容）。采到多少、列表看全、详情看全、字段实际改变是不同事实。

## E1 完整性、空列表、不适用与 schema 漂移

**输入与选型**：任何要合并到持续数据集的结果；尤其适用于供应商返回值可能漂移、零结果或详情缺失的来源。

**步骤**：保存范围绑定的请求与非空响应证据 → 核对结果结构、行数、ID、分类和 URL → 有 total 时核唯一数；无 total 时核 pagination_exhausted、唯一数与 last_page_evidence → 分离列表/详情完整性 → 页面上限、未知类别、失败详情保持 partial → 官方无公开范围记 blocked/不适用证据，不能移出分母后假称全覆盖 → 比较 schema 与先前证据，未知枚举单列不猜测。

**代码与验证**：[validate_result](../../qiuzhao/collector/p1_pipeline.py)、[collection_gap](../../qiuzhao/collector/collection_gap.py)、[完整性回归](../../tests/test_collector_partial_keep.py)、[缺口回归](../../tests/test_collection_gap.py)。pending 的证据文件必须实际存在且位于当前 scope 或 shared 目录；failed detail 不得 complete。

**运行案例**：运营正文第 3.4、3.5 节记录已尝试、partial、blocked 与未开始分别统计。Fable 两轮指出空读语义在各平台不同，这是待归类缺口，不应据文字粗分推断平台数量。

**失败反例**：空数组即成功；不适用无官方证据；吞掉未知类别；分页上限触发却标 complete；空 pending 计划当全部尝试。现有 Workday 按标题过滤的零匹配并不证明 scope 无岗。

**验收**：列表确证为空、关键词零匹配、结构性不适用、请求失败有不同原因；完整声称可重放；统计未知写未知。列表不完整绝不下架。现有 merge 即使 complete，仍要求非空 jobs 才做缺席退役；发布边界另有冻结，不能承诺空列表自动下架。

**费用/登录**：可用已有脱敏证据离线核验；无需模型 API；无法访问的登录/签名入口保留阻断，不以空数组代替。

## E2 稳定 ID、去重与字段级更新

**输入与选型**：多来源重复、历史 ID 命名空间、内容增量及纠错迁移。名称标签不能代替法律主体；相同标题不能代替同一记录。

**步骤**：绑定来源主体、scope、官方 ID → 保留明确声明的历史稳定前缀，否则派生稳定身份 → 优先同 ID，唯一官方 UUID，其次唯一精确详情 URL+范围的旧行认领 → 身份歧义隔离 → 对比业务字段，观察时间变化不计内容更新 → 详情失败保留先前已核正文 → 地点只按原始证据有条件继承并重新归一化 → 迁移另做逐字段白名单与可逆差异核验。

**代码与验证**：[validate_result、official_uuid、merge_records](../../qiuzhao/collector/p1_pipeline.py)、[business_value、carry_forward_location](../../qiuzhao/normalize.py)、[字段定义](../../qiuzhao/v4_fields.py)、[字段回归](../../tests/test_v4_fields.py)。现有 rebase 是整行冲突、线上同 ID 优先；不是通用字段级合并器。

**运行案例**：运营正文第 3.2 节的地点迁移先改大量旧行，会让日更同 ID 内容更新在整行 rebase 中被丢弃；因此候选保持未发布并从最新 accepted 重算。第 4 节只追加恢复逐字段保留旧行，未应用 merge 的修改与下架。

**失败反例**：模糊名称/标题去重；拿新 hash 命名空间重复导入旧记录；缺详情用空值抹掉正文；旧地点候选覆盖新版本；把重新看到列表称为内容更新。

**验收**：新增/更新/仅观察独立计数；字段变化可列差异；旧 ID、重复次数、正文保留符合契约；纠错不改无关字段；迁移基线仍当前。**费用/登录**：本地比较与存储；没有新增外部请求；私有原始行和差异包不上公共方法库。

## E3 缓存身份隔离与核验时间

**输入与选型**：重复运行中详情抓取占主要成本、列表提供可信修改指纹；不能用缓存取代每个逻辑 run 的新列表。

**步骤**：缓存键绑定平台/host/租户/company/scope/记录 ID/有效版本 → 保存列表指纹与详情核验时间 → 指纹一致且可信才复用 → 无指纹、身份漂移、版本不符重抓 → 逻辑 run 绑定列表共享目录；跨 run 不复用旧列表 → 缓存命中保留原详情时间 → 分别报告命中、请求、列表检查和内容变化。

**代码与验证**：[Moka 缓存函数](../../qiuzhao/collector/p1_sources_01_10.py)、[Moka 适配器](../../qiuzhao/collector/p1_platform_moka.py)、[缓存回归](../../tests/test_grok47_moka_cache.py)、[bind_logical_run](../../qiuzhao/collector/p1_pipeline.py)。测试涵盖指纹变化、身份不匹配、无指纹 envelope、resume 原始详情绕过、相同指纹保留时间。

**案例等级**：实现与回归内容已核对；运营正文第 5 节明确 24 小时缓存收益未实测，不给节省百分比。

**失败反例**：跨租户复用同 ID；有 raw detail 文件就跳过；缓存命中刷新 reviewed_at；按低产出降低列表频率后漏掉修改或状态变化。

**验收**：跨租户/范围/run 隔离；指纹失配确实调用详情；命中时 detail_checked_at 不变；每 run 列表重新取得。**费用/登录**：减少已证明冗余请求，缓存有磁盘成本；缓存不得存凭据或复用私人登录态。


## Eightfold / Phenom 空列表与分页契约（2026-10-09）

正式 `p1_pipeline → adapter.collect` 入口只接受类型正确的官方 response/data/list；缺 envelope 或 list 不解释为零岗位。total 存在时必须为非负非 bool 整数、各页一致，观察到的唯一合法 ID 数与 total 一致才完整；合法无 total 协议仍可由明确终止空页完成。ID 只接受非空字符串或非 bool 整数；Phenom 允许缺值/空值回退 reqId/jobSeqNo，已提供但畸形的主 ID 不用 fallback 掩盖。即使该行被地域过滤，畸形 ID 也不能证明可信空列表。

正 total 的过早空页、重复/缺 ID、无效行、total 漂移或错误保留有效岗位为 partial/blocked 和 errors，不推进完整性或下架判断。list_total 是全局分母，expected_total 是 scope 选择分母。Phenom 原始分页证据保存完整 refineSearch（status/totalHits/data）。恢复仍沿原入口和预算，不手改 complete，不把返回数当新增数。

原坏合同27项中19失败，typed-ID 被过滤反例原14项均失败；修后两个平台95测试独审通过。录制 fixture 截取部分列表，原 total16/56 与 observed10/12 明确 partial；合法 no-total 测试只证明该协议，不改 fixture 或宣称全量。私有 ef-phenom-independent-review-round2.json 绑定受审字节。尚不证明上游当前协议、全部公司完整或历史零结果触发缺陷；当前状态只维护在日更正文。
