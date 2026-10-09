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


<a id="ef-phenom-contract"></a>

## Eightfold / Phenom 空列表与分页契约（2026-10-09）

正式 `p1_pipeline → adapter.collect` 入口只接受类型正确的官方 response/data/list；缺 envelope 或 list 不解释为零岗位。total 存在时必须为非负非 bool 整数、各页一致，观察到的唯一合法 ID 数与 total 一致才完整；合法无 total 协议仍可由明确终止空页完成。ID 只接受非空字符串或非 bool 整数；Phenom 允许缺值/空值回退 reqId/jobSeqNo，已提供但畸形的主 ID 不用 fallback 掩盖。即使该行被地域过滤，畸形 ID 也不能证明可信空列表。

正 total 的过早空页、重复/缺 ID、无效行、total 漂移或错误保留有效岗位为 partial/blocked 和 errors，不推进完整性或下架判断。list_total 是全局分母，expected_total 是 scope 选择分母。Phenom 原始分页证据保存完整 refineSearch（status/totalHits/data）。恢复仍沿原入口和预算，不手改 complete，不把返回数当新增数。

原坏合同27项中19失败，typed-ID 被过滤反例原14项均失败；修后两个平台95测试独审通过。录制 fixture 截取部分列表，原 total16/56 与 observed10/12 明确 partial；合法 no-total 测试只证明该协议，不改 fixture 或宣称全量。私有 ef-phenom-independent-review-round2.json 绑定受审字节。尚不证明上游当前协议、全部公司完整或历史零结果触发缺陷；当前状态只维护在日更正文。


<a id="workday-contract"></a>

## Workday 专属总数与终止证据（2026-10-09）

正式入口仍为 `p1_pipeline → p1_platform_workday.collect`。校验 jobPostings 列表、行、externalPath 和可信非负整数总数；保留首可信 total，允许已存真实 3M 协议后页 total=0 sentinel，不套其它平台每页 total 一致规则。实际返回行数推进 offset，唯一 ID 数与可信总数一致才 reached_total；合法无 total 协议需要显式终止空页。坏 envelope/行/ID、重复、总数漂移或提前空页留下 errors 与有效岗位 partial，正常页限也显式 partial；不能冒充空成功或下架依据。

原始3M官方响应离线回放：首 total36/20行、后 total0/16行，36 unique，实习 expected1/jobs1，2页 complete；原始样本和配置不改。42专项离线测试独审通过，私有 workday-independent-review.json 绑定源码及回放。公司/地域/query/facets 参数未改：当前 China/应届关键词命中集不等于全官网或真实中国地域全集；真实 raw 有独立国家 facet 且 queryChina 返回印度行。地域取数口径和官方 UI 请求仍需另核，不用本修复宣称69名称全部完整。恢复沿原预算与同一入口，异常证据留原 run，不改分母。


<a id="pagination-sop"></a>

## 分页平台的执行参数、字段来源与恢复（2026-10-09）

本节补充上面两份契约的可复用步骤，不复制公司表。正式配置以 [p1_platform_companies.json](../../qiuzhao/collector/p1_platform_companies.json) 中平台节为准，经 registry绑定 `p1_pipeline → adapter.collect`。公开入口参数必须来自配置/官方请求证据，不因为回归通过就自行修改国家、query或范围。

| 平台 | 官方请求与配置 | 字段来源 |
|---|---|---|
| Eightfold | `_base(entry)/api/pcsx/search` GET；domain/location/start/sort_by/remote/hl来自entry，详情`position_details`以position_id绑定；必要的公开页面fallback仍沿既有代码 | typed id→稳定身份，name→标题；position_details.jobDescription→正文（源码可回退列表jobDescription）；locations/standardizedLocations→地点；postedTs→发布时间；地域与scope分类在ID合法性之后 |
| Phenom | entry.host + `/widgets` POST；ref/lang/country/site_type/location固定到租户，refineSearch的from/size推进；detail_body绑定该岗位，证据保留完整refineSearch envelope | `_record`映射title，详情description/ml_Description（可回退列表descriptionTeaser）→正文，city/state/country等原始字段→地点；ID按合法主id或缺值时reqId/jobSeqNo回退；提供畸形主ID不回退；totalHits属于全局列表，不等于scope expected_total |
| Workday | `/wday/cxs/<tenant>/<site>/jobs` POST，实际路径由源码构造；tenant/region/site/search_text/country/max_list_pages来自原配置；低层_list_page支持appliedFacets，但当前正式collect每页硬传{}，尚未贯穿配置facet；显式空searchText也会回退默认China。offset按实际页行数推进；详情GET同site+externalPath | jobPostingInfo.id/externalPath→身份，title→标题，jobDescription→正文，location/additionalLocations→地点，startDate/endDate→日期；没有届别字段不猜；China关键词不能替代真实地域全集 |

逐个读取三个模块各自 `__main__` 的 argparse 后确认：每个都只有 company 位置参数，`--scope`默认campus、`--output-dir`为必填Path、`--max-requests`为可选int；入口随后调用各自collect。预览CLI形状为：`python -B -m qiuzhao.collector.<p1_platform_eightfold|p1_platform_phenom|p1_platform_workday> '<已注册名称>' --scope <campus|intern|social> --output-dir <独占目录> --max-requests 20`。尖括号是待替换参数，禁止直接把该模板当命令；它是受预算的网络取证入口，本次未执行。离线复验分别运行 `python -B -m pytest -q tests/test_p1_platform_eightfold.py tests/test_p1_platform_phenom.py` 与 `python -B -m pytest -q tests/test_p1_platform_workday.py`，无需调用供应商。

逐页保存响应→先校验envelope/list/行/ID→记录可信总数和末页→按scope/地域选择→绑定详情→统一validate_result。一个异常页不能抹去前页有效岗位，也不能提升complete；页限与预算不足保留partial。恢复使用原run保存的失败页与配置身份，修复后离线重放→owner按原截止续跑；未校验通过不推进完整时间/下架，回归通过不直接推进生产游标。

独审与Windows `ef-phenom-independent-review-round2.json`、`ef-phenom-windows-regression.json`分别95通过；EF源码`0cf70aa3…`、Phenom`b20bcb2b…`。Workday `workday-independent-review.json`、`workday-windows-regression.json`分别42通过，源码`046587fb…`；3M36unique/实习1的已存真实两页为零total哨兵成功样本，不是当前网络验收。前述截取fixture、filtered-out畸形ID、正total提前空页、短页offset、total漂移皆保留失败边界。官方接口无新增付费调用；公开访问阻断仍记录原因，不登录、不绕限制。


科思创真实小样证明国家facet可精确查询，且Full time与Regular不证明社会招聘；Student/Intern/Trainee混合桶也不能全判实习。现_scope_of非关键词默认social不满足这一新契约，候选接入仍待typed query/facet贯穿、官方性质证据与用户地域选择；不能沿当前默认值宣称公司官网全范围。

### CLI 源码签名核对（2026-10-09，无采集）

| 入口 | 实际 argparse 签名 | 正文命令核对 |
|---|---|---|
| `p1_platform_eightfold.__main__` | company；--scope choices=shared.TYPES/default campus；--output-dir required/Path；--max-requests int | 与上述模块预览模板一致 |
| `p1_platform_phenom.__main__` | 独立 parser 声明 company；--scope choices=shared.TYPES/default campus；--output-dir required/Path；--max-requests int | 与上述模块预览模板一致；字段函数实际名为 `_record` |
| `p1_platform_workday.__main__` | 独立 parser 声明 company；--scope choices=shared.TYPES/default campus；--output-dir required/Path；--max-requests int | 与上述模块预览模板一致 |
| `run.main`（BOC） | --output-dir Path/default库data；--source choices含boc/default all；--chn-limit int/default0；--delay float/default1.25 | 正文显式source=boc、独占output-dir与delay，不沿用三个平台的位置参数 |
| `p1_sources_31_40.__main__`（LiAuto） | company、scope（campus/intern/social）、output_dir三个位置参数；无--scope/--max-requests | 正文理想汽车、social、独占目录三个位置参数匹配 |

先逐模块读取当前 main 的五段 parser、字段映射与配置路径，owner随后实际执行上述五模块及p1_pipeline的`python3 -B -m ... --help`，六个入口均退出0，未进行岗位采集、网络请求或供方健康检查。私有`method-library-cli-help-actual.json`保存原命令与完整help；这证明入口参数可解析，不能代替供方运行验收。复用命令前替换模板参数；默认data路径与basic来源入口会写输出，不可拿它们当只读探针。新版本实际供方/生产验收另由 owner 收据证明。


<a id="dayee-request-scope"></a>

## 请求级性质证据与可信空列表（Dayee / 51job）

正式入口为 `p1_pipeline → p1_foreign_01.collect`，复用配置节 `dayee` 的原租户 key、名称及 `_host_for` 主机；请求性质沿已有 `RECRUIT_TYPE` 映射（campus=1、intern=12、social=2），不能以返回零行推出整家公司没有该类岗位。列表与详情仍使用已有 `listPosition`/`listPositionDetail` 同租户接口，pageSize=10，postId绑定正文、岗位名称、地点及原日期；届别未披露不补。

先保存实际响应，再校验官方state、pageForm、pageData数组与非负整型dataCount/totalPage；首可信dataCount是不可缩小的分母，后页漂移、正总数提前空页及终页唯一ID数不足均保留有效岗位为partial。请求级 `scope_evidence`、`scope_response_evidence` 和 `scope_checked_at` 在合法响应校验之后产生，空列表不依赖jobs拼证据。shared.finish和正式validate_result仍保留原验证门；预算耗尽不改小首分母、不推进下架。Dayee没有已证Workday后页0哨兵协议，不跨平台套用。

离线复验：`python -B -m pytest -q tests/test_p1_foreign_01.py tests/test_p1_platform_51job.py tests/test_beisen_legacy_engel.py`。原益海嘉里实习157B响应（SHA109ee4…）在Mac与Windows都经实际collect→validate_result重放，合法0/0、请求12与响应文件/时间证据对应；没有新HTTP或当前源重采。坏envelope、总数缩小、空页矛盾、预算partial是回归反例。受审Dayee源码cf363c…、51job c7a9b3…；独审收据 `dayee-51job-independent-review-round2.json`，Win完整集合收据 `dayee-51job-windows-regression-complete.json`。Win保留旧literal REDACTED租户配置断言失败与既有私有Mac原HTML路径skip，不能概括为全套通过。

51job仅配置campus而未验证其他官方route时，返回blocked/source_scope_not_verified，无HTTP与空success；不缩计划、不下架。已验证ENGEL social route与原campus路线照旧。恢复先核真正官方替代入口，修配置/协议后离线回放，再按原预算运行；改阻断标签不等于补齐公司官网范围。费用沿既有请求预算，未新增付费、登录或绕过访问限制。当前运行版本/每日成功数量只维护在日更正文。
