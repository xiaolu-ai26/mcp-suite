# 秋招岗位库：日更交付、恢复与后续优化

本文件是秋招岗位库日更链路的唯一维护正文：交付口径、当前基线、已实现的计划、真实交付时序、代码与一次性工具的边界、遗留风险和待审批的优化都在这里维护。`README.md` 只保留摘要和链接。私有证据（运行收据、状态文件、账本、审查记录、数据快照）不进本仓库，下文以“本地恢复证据目录”加相对文件名引用。

## 0. 2026-10-08 实施方案与阶段状态（入口）

**目标：固定的已批准公司官网岗位，每日完整获取列表和详情、统一字段进入一个权威库，并同版交付原飞书 Base 与 MCP。** 全部固定来源成功且三层回执通过才完成；部分交付如实保留。

**阶段状态（2026-10-09入口核对）：0方案/A盘点完成；B五文件受审安装和normalize-only已完成，10/8已采成果补交尚待；C实现/独审中；D全来源真实两轮验收未达。** 固定范围已在0.5实测为1124名称键/3372 company-scope键，basic6源与独立tencent另列；全部目标未完成。后面的9/24–10/2章节是历史，尤其3.6的automation ACTIVE不代表当前：本轮automation-4保持PAUSED，不启动旧heartbeat。0.1保留本轮开始时快照，当前B/C状态以0.7的小收据为准。

### 0.1 本轮开始时历史快照与固定范围（2026-10-08，阶段A/B实施前）

源码基线 `main=bcae6e546a025a3a84c5bfe4aa9d619a38db9c79`。正式入口 [windows_collector.steps_for](../deploy/windows_collector.py) 顺序是basic、tencent、分段P1、normalize，再按受控发布/交付链处理。basic的 [run.py](../qiuzhao/collector/run.py) 声明6个源：postal/chnenergy/telecom/boc/ccb/guopin；tencent由 [auto_collect.py](../qiuzhao/collector/auto_collect.py) 单独运行。

P1权威代码入口为 [p1_pipeline.py](../qiuzhao/collector/p1_pipeline.py) 的COMPANIES/REGISTRY/DEFAULT_COMPANIES；固定优先名单50项，平台参数主要来自 [p1_platform_companies.json](../qiuzhao/collector/p1_platform_companies.json)，其13个平台节合计注册前配置条目含禁用项，不可直接当公司数。本轮完整qiuzhao/deploy检出离线导入得到REGISTRY和DEFAULT_COMPANIES **1089个名称键**、21个实际adapter模块；不是集团或实体去重数。默认rotation=1，正式P1入口不传公司子集；新增范围须审批。

历史10/8计划3372单元、3252未开始；3372÷3仅推算1124，不能证明公司名单，因为适用scope、禁用配置、名称冲突和运行版本可能不同。阶段A须把Windows实际registry、已批准名单/历史计划每key与本地1089逐项对齐，保留所有差异，**不得用较小本地名单删除原分母**。交接清单及5275映射/7111可见记录非固定范围证明。Windows配置差异及固定实体数仍未知。

PR #27 draft/open head=`b8b0bd991cf549f3d8fc7b33a022919626c703ec`；作者记录84聚焦测试，最新版独审与完整Windows回归未完成，旧8fa审查不覆盖新字节。生产normalize SHA仍`8590fd48eab7f84126866a31486286c8c72f680ad86292f51ae7bbaa43c4e02b`，normalization_io.py/windows_normalize_retry.py缺失。10/8 01:00:03–01:31:58在json.load/fp.read/UTF8 MemoryError停：collection stopped/publication pending/feishu not_requested；10/6–7也normalize失败，但10/7已有accepted f770…，不能说数日完全无成果。10/2 after-rollback staging 806915187字节/372f47…是恢复后样本，非故障瞬间原样本；故障证据沿用私有pr27-evidence-20261002，勿重搬2GB。

### 0.2 阶段目标、方法与验收

| 阶段 | 执行与产物 | 放行条件 |
|---|---|---|
| A 固定范围→方法绑定 | 逐key冻结已批准公司/租户/官方入口/适用scope/adapter/配置路径/方法ID/字段映射/样本/受审版本；未知保留。绑定存现有配置与可生成清单，方法索引只导航 | 全清单都有已验证方法或明确缺口；覆盖清单不等于全采成功，分母及差异可复算 |
| B 恢复归一化与已采补交 | 只审PR27最新字节；完整checkout与真实Windows隔离重放，验证长记录/内存/依赖冻结/数据保持；通过后按备份与回滚合同合并部署，先normalize-only，再补交已采成果 | 独审、Windows终态、版本SHA及差异真实可核；不重置旧预算、不补造历史采集success；accepted/served/Base分别核验 |
| C 补齐固定来源日更 | 按源原因修列表分页/详情、真实字段/稳定ID、内容更新与保守下架；失败隔离、有界重试、域名/租户并发、时间/内存/存储预算；预览共用正式解析与校验入口 | 每源可信total或末页/ID证据、详情缺口、字段披露、更新/下架与反向失败样本均可核；未知类型不强填，失败不推进完成游标 |
| D 交付与自然运行 | 原Base Excel投影/导入/verify/switch，MCP查询和详情核对同一已接受版本；至少2轮计划运行并逐源完整性验收 | 每轮固定分母完整、每源实际成功，accepted=served=Base账本对应版本，MCP真查询一致；两轮运行不替代每源验收 |

单个源授权不可得、上游范围不明或预算不足时，保留条件缺口和目标未达；不得删源、造字段、把attempt/partial/空结果包装为success。数据仍由现有accepted库统一承担，Base和MCP是投影/读取出口，不建第二套权威库。

### 0.3 成功方法如何沉淀与低成本扩源

现有[方法索引](collection-methods/README.md)已有A1分页(Workday及回归)、A2列表详情(51job/tupu360)、A3动态入口(HeadlessSource/Feishu及回归)、A5多入口；历史51job百事/马夸特campus、讯飞campus13条是代表成功案例，不代表所有公司。方法与adapter/公司参数/字段映射/样本/正式run证据的统一绑定仍须补齐；现有源码与历史文档已含部分规则和版本，不能宣称一概没有。

“成功方法完成”须同时具备：正式运行使用同入口代码；可复用公司配置（租户/入口/scope/预算）；字段映射；可执行SOP与失败恢复；脱敏真实代表样本与回归；正式版本和真实终态证据。同平台共一个SOP，公司只填参数与差异，沿[模板](collection-methods/TEMPLATE.md)补证据，不复制全流程。运行状态由配置/账本生成，方法文档不复写每日计数；AI用于一次性修方法，不能成为每日日更重新探索的依赖。后续扩源仅同平台加配置或新平台薄adapter，未经批准的新公司不启用。

AIHOT仅借鉴固定新版 `6e67a9d9e8d87b95b8118a8a0b328a9bebd2bb48` 的[信源](https://github.com/KKKKhazix/AIHOT/blob/6e67a9d9e8d87b95b8118a8a0b328a9bebd2bb48/docs/sources.md)与[架构](https://github.com/KKKKhazix/AIHOT/blob/6e67a9d9e8d87b95b8118a8a0b328a9bebd2bb48/docs/architecture.md)：类型化配置/未知参数拒绝、preview同正式逻辑、失败不推进cursor、一个public read layer。禁止照搬资讯评分筛选、旧文/日期过滤、首次限量或模型付费流水；不迁Node+PG、不重搭平台。

### 0.4 分工、记录与恢复边界

总控只设goal、派阶段合同、核回执与独立验收；命名执行者在隔离分支实现，独立审查者核最新版代码与Windows证据后再放行部署。官方本机dsh可分担机械盘点/简单执行，限定私有草稿写权，不给生产/Git主写权；现有供应商成本授权只适用已指定范围，不新购、不换供应商。

本轮dsh `0.1.5-rc.1` 实际provider/model=`deepseek-official/deepseek-flash`，session `7d871e9d-db61-4ec9-b8d8-29072de2212b`，退出0、持久化turn/end completed且草稿存在；人工核对后采纳绑定字段建议，纠正“真实发布仅这些案例”“无版本/合并规则”等过度断言。私有收据位于 `/Users/maxzhl/Projects/qiuzhao-lzh-handoff-20261002/phase-20261008/`，stderr含内部推理不上传。

阶段状态/阻断只续本节，方法只续方法库，事故只续[踩坑正文](qiuzhao-collection-pitfalls.md)；不另建平行PROGRESS/BLOCKED正文，不扩大重hash/重扫/health，阶段0当时不修改PR27分支；该限制已由B授权解除，继续保留旧heartbeat暂停。阶段0等待已结束，现按active goal逐阶段执行并读回终态。

### 0.5 阶段A终态（2026-10-08，只读对齐与方法投影）

Windows `C:\mcp-suite-collector` 小源码/config先复制到D隔离审计目录，再在本机以 `python -B` 离线加载；未在C导入或写入。10/8原plan逐key实测：**1124个名称键、3372个唯一company/scope键，campus/intern/social各1124；registry-only/plan-only/main-only均0**。这是运行固定范围，非法律实体公司数。用户本轮明确授权按1124/3372现状范围实现，本轮不增源不删分母、不重复逐公司索审批；额外12条禁用声明单独保留为条件缺口，不计作活动1124，也不因禁用推断授权已撤销或scope不适用。basic6源与独立tencent另列，未混入P1名称分母。

main与Windows的p1_pipeline源码同SHA `fff52389c4aad220183c77db6c29e63186afe1736c0f340e535a2d0a04cda0aa`；22个活动adapter对应源码全部同main。配置却不同：Windows新增Moka16/Workday10/Dayee11个key，并替换main中的3个REDACTED占位key；这些37个真实参数key及既有名称覆盖关系使Windows多35个登记名称。35个名称及逐参数差异留私有 `config-difference.json/windows-registry.json`；禁止用main全树覆盖生产配置。优先50名单在源码明确标user-approved； broader已配置范围有运行plan证据，但本轮未找到单独的人类审批逐项台账，原外盘all-companies文件当前不可访问，不把发现清单或映射包当批准证明。该授权溯源缺口保留，不阻断已配置固定范围的修复。

私有 `phase-20261008/generate-method-bindings.py` 从捕获版本与指定三份历史status生成投影，**不手编、不是第二公司真源**；输入/源码SHA、官网观测、配置、adapter、字段表达式、正式入口、历史样本与测试/缺口均可追溯。投影1136行=1124登记+12禁用声明。分类仅candidate，所有登记项明确per-company-verification-pending；54名称仍为代码内参数，55名称协议方法未分类，22名称尚无绑定的专用测试路径，974名称未覆盖本次保留的平台代表样本。静态表达式不等于语义映射完成，已存在shared代码的继承字段需继续补指针。

历史9/29、9/30、10/2快照中，任一scope曾success+complete的名称1057，三个scope跨历史均曾成功的名称871；按scope为944/939/1007，**均不代表当前成功或同一轮全成功**。coverage.published标志也不等于服务器accepted。三个平台SOP（Workday/51job/飞书）沿[获取正文](collection-methods/acquisition.md#2026-10-08-平台-sop-绑定代表样本不是全来源验收)固化，3份真实小样本合计92KiB，对应现有回归46 passed/0 skipped；严格成功方法所需历史运行字节关联与每源当前验收尚未完成，已验证方法数不能报为1124。

生成器独立GPT-6.1 Sol low复审PASS，SHA `e7667da3e98990bbd0b930352e1179b966bd6b51c551fe483e72a8a5deb1f59c`，只代表投影正确性。阶段A盘点终态已完成；后续B修复PR27已发现的JSON空白解析缺陷并独审/Windows隔离重放，C补齐上述绑定及逐源完整性。未启动heartbeat、未采集、未部署或发布。

**B阶段性收据：** 原PR27追加修复head `50062ac9362516b528b392eb8f5a7a18776bb79b`，实际JSON空白解析已独立复审 `PARSER_FIX_PASS / OVERALL_NOT_PASS`；实现与独审均101 passed/0 failed/0 skipped。只修解析器/新增17回归/验证记录，代码SHA `c63f645e63483a651d0b0a9f14879291ed756738ae69ad695481ea541318adfe`。完整tracked checkout已物化约110MB；跨环境freeze、真实Windows隔离/内存/Scheduler及现有业务回归仍待，不部署。尤其retry冻结集含公司配置，repo与Windows配置SHA不同；目标冻结必须保留1124范围，不能盲用repo配置覆盖。

### 0.6 B目标环境边界（2026-10-08，安装前）

最终代码头cfa4ad28（后续文档提交不改运行字节），源码纳管与目标冻结独审已准五文件C安装/normalize-only，未批准采集或数据发布。最新10/8 staging一次稳定复制D：814080217 bytes/107859…，178833条；真实业务check229.782s/峰值31.5MB，完整normalize258.485s/峰值30.1MB，输出f6f9ada…；原位黄金对照297无ID历史记录保留、重复ID余量0、非归一化字段不变、所有变化record与旧真实业务函数整dict相等。3240填充/567非空变化不是新增岗位量。

D真实retry inspect0/apply0、normalized-not-published，原已采阶段/预算/deadline/collection stopped/delivery pending/P1status保留；真实msvcrt、NTFS失败保全与成功替换、超时子孙清理通过。124本机聚焦通过；Win123通过/1个POSIX mode bits skip（NTFS另测），fullgit扩展head22 fail/326 pass/39 skip、同D base22 fail/325 pass/39 skip，新增失败0。receiver Linux fcntl及P1 timeout/锁等失败须按各实际平台/路径区分；本次未采P1，不把同baseline自动当安全通过。

验证矩阵：collector/normalize/retry真实Win；MCP正式Linux、同100当前真样本POSIX HTTP七调用parity通过；Win既有/dev/fd不支持并非本项目要移植的服务目标，旧9/11夹具未取得，未冒充替代。D-only manifest绝不用于C，另有C专用五文件签署与现场条件。生产安装及三层恢复仍待实际终态，不据代码合并写B完成。

原Base f770于22:39 schema_snapshot明确failed，projection/xlsx/samples均已完成；空CLI stdout失败已用原参数只读复查国家/地点选项正常返回，23:14:50仅续同版本失败阶段，23:22:08 schema_snapshot完成并进入import，未开新批或并行writer。Mac余约1GB，新raw不传回，后续容量/归档与长期非Mac执行器缺口仍须实核。

### 0.7 当前B/C状态与私有证据（2026-10-09核对）

PR #27已合并为`b643a16f5831c8a70a5a65935035f8aec4166534`，PR #28已合并为`89d0211559d66adf27acc51cfad64e7063c7b2c9`。10/8生产五文件安装收据为`installed-byte-verified`，normalize inspect/apply均退出0，终态`normalized-not-published`；原run20261008仍collection stopped/publication pending，未重采、未延长原deadline。私有证据目录沿用`/Users/maxzhl/Projects/qiuzhao-lzh-handoff-20261002/phase-20261008/`：`production-install.json`、`production-normalize-driver-receipt.txt`。10/9 `publication-only-review-20261009.json`仅为conditional PASS；本次核对所据阶段记录为避01:00 Daily尚未启动补发，不将候选写成accepted或已交Base。

此前已接受的f770版本于**2026-10-09 00:47:37（北京时间）**完成原Base交付：12表176849行，ledger active=null、last_delivered=f770；核验包含核心必需字段全行检查，全部23字段仅固定24样本，非23字段全量逐格验收。这是旧已接受版本补交完成，不能代替10/8新归一化成果待补交的状态。 同版本服务器实际MCP检索、同ID详情、校园招聘筛选已通过；默认检索172494与包含已截止/下线等记录176849的差4355是正式默认有效性过滤，不是Base漏行。`server-mcp-current-f770.json`保存实际响应与未变服务PID/既有live served版本绑定，响应自身不含SHA。私有Base证据根为`/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/delivery/`：`ledger.json`、`versions/f770ed9659f6936b42af02387809ba4e0e1ce7b464ffb85b0ba09d24243e8cd9/state.json`及该版本目录下`work/runs/20261008T232209/{verify,switch}-receipt.json`。

10/9阶段容量收据`next-daily-capacity.json`记录C空闲19.818GB、原门5.369GB通过、D空闲8.417GB，只证明该启动门，不证明整日容量可持续。`archive-physical-device-correction.json`证实2ddc/8ab版本父目录已为外盘symlink，原Mac释放1.3GB计划无效且脚本安全拒绝；实际零删除/零释放，不继续这两件搬运。

C北森同run完整列表复用已独审25项通过、Windows隔离真实缓存/NTFS失败保原与后续替换验证通过，PR #30已合main（`faf56be4372bba1d01a168ada9266ff391ffcb45`）；Eightfold/Phenom空成功与typed-ID缺陷已独审95项通过，Windows同字节95项通过，PR #31已合main（`3df0f740e04365bb9fc7f982ad67464c8ce88f4e`）。均未部署当前运行依赖，不代表各名称完整采集或提速已实测。私有证据为`beisen-independent-review-round2.json`、`beisen-windows-cache-result.json`、`beisen-original-protocol-validation.json`、`ef-phenom-independent-review-round2.json`、`ef-phenom-windows-regression.json`，方法沿原方法正文维护。第二轮机械草稿已有私有`c-deepseek-result.md`，仅供人工核对；私有推理日志不作为正文或上传材料。D固定全来源真实两轮验收仍未达，1124/3372固定分母与basic6/tencent分列保持不变。

记录的事件发生在 **2026-09-24（北京时间）**，文中时间均为该日，除非另行注明。

## 2026-10-02 Pro 修复候选：尚未部署

本轮依据 Max 的最新明确授权由网页端 Pro 实现；不改写历史模型与独审归属。源码基线为 `bcae6e546a025a3a84c5bfe4aa9d619a38db9c79`。**独立审查待完成；不是生产恢复成功回执。** 历史 automation、版本、容量和 Base 状态均不代表现在的状态，本轮没有启动或修改任何生产调度。

交接材料报告 2026-10-02 05:42:11（北京时间）`collection.state=stopped`、normalize 失败、publication pending。已读取任务书、README、准备审查摘要和源码；未取得 Release 压缩包内的该次 normalize.log、原始 staging 与完整运行收据，因此该事故的具体异常根因仍未证实。缺 `normalize_tables.json` 在本基线会使用 fallback，本身不是必然异常；不能用补旧表或 10/1 特例绕过。

本轮实现 `normalize_file` 的流式原子 I/O，业务字段函数不变；任一记录、JSON 尾部、写入或校验失败不提交候选。新增 `deploy/windows_normalize_retry.py`：默认只检查，apply 在同一 runner 锁、Scheduler 安全状态、代码/资产审查绑定和原容量门下只重试 normalize；不调用采集、发布、Base，不重置预算/截止，不改计划分母。中断后未完成校验的 retry 保持现有 unsafe_writer 门关闭。正常 collector、10/1 零段 guard、CAS、飞书导入和容量公式均未改。

可复核的本地证据：聚焦 Python 测试与 Linux 合成内存探针，详见 [验证报告](normalization-recovery-verification-20261002.md)。12 万行、127688890 字节样本在隔离 Python 进程、128 MiB 地址空间限制下，旧入口 MemoryError，新入口通过且样本 SHA 不变；字段回调为 no-op，这不是生产故障归因或全字段验收。

[精灵操作手册](normalization-recovery-runbook-20261002.md)给出应用、审查、真实依赖回归、保全证据、受控部署、normalize-only 与后续发布边界。[方法 R3](collection-methods/streaming-normalization-recovery.md)记录适用条件、完整性、失败反例和未验证边界。原部署清单保持冻结，代码漂移会继续阻断交付，独审之前不得刷新成 PASS 或关闭该检查。

尚未完成：10/2 样本重放、Windows/实际账号锁与进程测试、完整字段/原回归套件、独审、最终字节冻结、accepted/served/Base 实测；逐来源分页、详情、类型枚举、新鲜度、每计划 key 证据与长期容量缺口没有因本次 I/O 修复被宣称解决。恢复成果不等于补齐未开始的采集。

## 1. 交付目标与口径

每天让用户查到已成功采集的新岗位和内容更新；服务器与飞书各有确认回执；遗漏和失败清楚可见。先可靠交付已采内容，再减少重复采集，随后小批扩大覆盖。

统计口径：

- 采集完成、服务器接受（accepted）、服务在线提供（served）、飞书 Base 交付是四个不同状态，分别记录时间，不互相代替。导入失败不回滚服务器数据。
- 原始记录数（服务器 `jobs.json` 身份数）与服务/飞书投影行数不同，分开报告。
- `status` 取值 `open`、`unverified`、`expired`、`removed` 按原样统计；`unverified` 不算作已确认可投。
- 招聘单位、公司名称的去重数是名称标签数，不是集团或法律主体数。
- 某日运行“全部尝试”不等于全部成功；首轮与补采的结果分开统计，不做算术合并。
- 未测得的计数写“未知”，不以 0 代替。

## 2. 产品规则（不可破坏）

1. 列表最近检查时间、详情最近核验时间、内容实际变化分别记录；重新看到岗位不等于正文已更新。
2. 保守退役：列表不完整、来源身份不一致、写入状态不明时不下架。
3. 缓存按来源、租户、岗位 ID、scope 及有效版本隔离；可信指纹不匹配就重抓；列表每个逻辑运行重新获取。
4. 飞书投影只来自服务器已接受的版本，只写既定的原 Base，走 Excel 文件导入；不恢复旧的逐行写入 API。
5. 失败不伪装成功；修复只做相关场景、样本和交付回执检查，不为修复重新核验全库岗位。

## 3. 2026-09-24 交付基线（截至 19:41）

| 项目 | 值 |
|---|---|
| 代码 | `main` = `dev` = `origin/main` = `origin/dev` = `10dea612159d884997b38dddeb58833977e48625`；PR #1–#8 均已合入 main |
| 服务器接受版本 | `07205aef0602eae144ed1888c97359ec8322623ae6eb69d6ed870647cb7b1f3a`，原始记录 171,976 |
| 在线服务 | 07205aef，投影 170,038 行（19:00:01 小时激活收据） |
| 飞书原 Base | 07205aef，正式 11 张子表，170,038 行（19:39:28 verify 收据，19:41:12 切换） |
| 按招聘性质 | 校招 64,593 / 实习 22,126 / 社招 83,319 |
| 按状态 | unverified 145,454 / open 23,975 / expired 609 |
| 名称标签 | 招聘单位 6,642 个，公司名称 4,682 个（非集团数） |

上表代码行是 2026-09-24 交付时核对的历史基线。2026-09-25 外部复审针对的是文档基线 main `0d5313fe`（见第 10 节）；此后的提交只修订文档，不改变上表。生产代码按受审文件逐个部署，不声称采集机或服务器与任一提交的全树逐字节一致；已核对的范围见第 6 节。

### 3.1 2026-09-28 历史状态（B1+B2 代码合入 main 时）

**四天容量阻断（只读审计 14:40）。** 9-25 至 9-28 每天 01:00 的日更 run 都停在 `validate-and-publish`：服务器 receiver 的容量门要求 2,823,685,866 字节，实际空闲约 2.70–2.72 GB，候选版本在上传前被拒、未被接受，四个 run 的终态均为 `partial-or-failed`。9-25 的 run 在被拒前已接受 3 次，最后一次为 `c76dcc89`（03:03:48），它自 9-25 04:01:12 起在线服务；9-26 至 9-28 没有新的接受版本。四天 p1 大部分单位未开始（9-25 未开始 2,898 家，9-26 至 9-28 每天 3,252 家，计划均为 3,372 家）。四个被拒候选没有重发或续跑。

**已上线：容量拒绝改为延期（PR #12，`9aa3719`）。** 9-28 14:53 服务器 receiver、14:56 采集机 collector 已按该提交安装，实测拒绝时 receiver 退出码 75 并输出一行 `RECEIVER_REFUSED`；collector 此后把该段记为延期并继续采集，不再整轮中止。Windows 计划任务没有改动，下一次运行是 9-29 01:00，结果尚未发生。

**当时进行中：备份有界保留（PR #13，`b0f71da`）。** 工具已合入 main；首批 18 个旧备份当时正在归档。其终态和后续进展见第 3.2 节；容量门公式没有改。

**当时代码已审、已合入 main、尚未部署：B1 交付闭环与 B2 地点全链路。**
- B1：`deliver-latest` 与部署清单 `deploy/qiuzhao-deploy-manifest.json`。6 个 R1 脚本进入本仓库 `deploy/feishu_r1/`，其中 3 个与 9-24 使用的外置原件逐字节相同，3 个只改地点列；交付机的全部运行依赖（R1、`v4_fields`、`normalize`、`normalize_tables.json`、`lark_sync_enrichment`、`sync_lark_multivalue` 等）已按受审版本冻结 sha256，任一文件漂移时 `--apply` 被拒。
- B2：按第 10.2 节 ② 修改 normalize、`v4_fields`、联想适配器、合并路径和 MCP；飞书新增 4 列 `国家/地区`、`州/省`、`办公方式`、`地点明细`（R1 由 19 列变为 23 列）。
- 自动交付规则（当时代码与 launchd 模板尚未安装）：每小时 :20 检查一次；有 active 版本时只续跑它；没有 active 时，最新 accepted 所属的 daily run 进入终态（`completed` 或 `partial-or-failed` 都可交付）后自动开一批；到北京时间 22:20 当天仍没有自动批次时，只要最新 accepted 是已交付版本的后继就保底开一批（采集机不可达时只用本地缓存且要求后继唯一）；每天最多一个自动批次。手动 `--force-new-batch` 和历史人工交付不占自动名额。
- 当时尚未发生：采集机与服务器部署、launchd 安装、Base 列变更、地点数据迁移（含联想 81482），以及无人值守交付的真实验收。后续状态见第 3.2 节。
- 测试只跑聚焦范围：B1 交付三组 96 passed；地点新测试 37 passed（项目 venv；系统 Python 缺 fastmcp 时 1 项 skip）；较大的聚焦组合 314 passed、4 failed、46 skipped，4 个失败在改动前的 HEAD 上同样失败，46 个 skip 缺历史 jobs 夹具。不代表全库测试通过。

### 3.2 2026-09-28 执行状态（17:20 的阶段性快照，北京时间）

- **代码与部署。** PR #14 已合入 `8bce6319b6d1a46531105f010aa9da2c32b8e3b1`。B1 的交付机运行依赖通过冻结清单校验；B2 的 Windows 6 个文件、服务器 3 个文件已按受审 SHA 逐件备份并原子替换。Windows 计划任务仍为 Ready，采集机 venv 模块导入及 16:23 receiver preflight 通过；服务器仅重启 `mcp-suite.service`，16:15 健康检查 `ok`。旧 `normalize_tables.json` 在采集机仍缺失，未将其旧地点默认映射盲目安装。部署细节见私有证据目录 `audit-20260928/deploy-b1-b2-20260928.json`。
- **历史已采记录恢复。** 15:54:57 的一次只追加 CAS 接受 `f066b095`：原始记录 175,370，较 `c76dcc89` 增加 1,697 条，原有行未修改或删除，原 213 条和讯飞 13 条均保留。16:01:22 小时激活及部署重启后 16:15 的健康检查均显示 served=`f066b095`，MCP 投影 173,434 行。这不等于 9/28 日更已续跑；四个旧 run 收据未改。私有收据：`audit-20260928/recovery/addonly-recovery-publication-receipt.json`。
- **容量。** 首批 18 个备份已逐件归档、验证并删除，15:52 服务器空闲约 4.79 GB，达到当时容量门但未达 30 次日发布的空间目标。基于新的 accepted/served/Base 保护集合重算后，下一批 40 个候选从 16:16 起逐件执行；截至 17:19，新增 19 个已验证删除，任务仍在运行，最终空闲量以终态收据为准。旧计划不能直接当作当前白名单。
- **飞书与调度。** 原 Base `KaJIbYuIPacWersWD4jcO1AjnGh` 于 16:21 只读核到正式 11 表、170,038 行；账本 `last_delivered=07205aef`、`active=null`。新的 `com.maxzhl.qiuzhao-feishu-deliver-latest` launchd 已安装并在 16:20 真实触发一次，结果 `waiting`：accepted 与 served 均为 f066，历史 add-only 恢复不是同一 daily run 的结算，须等新 run 终态或 22:20 保底，人工 `--force-new-batch` 不占自动名额。旧逐行 Base sync 的未加载 plist 已可逆禁用。尚无新 Excel 导入或 Base 切换回执。
- **自动结算门已加固。** collector 遇可续跑错误也会写 `partial-or-failed` 与 `completed_at`。原 `run_settlement()` 只看这两个字段，可能在下一次 :20 误开批；现要求收据明确 `collection.state=complete`。示例配置已同步该字段，实际安装配置读取 Windows 完整 `windows-status.json`。独立 GPT-6 Sol 审查 PASS，交付相关三组 98 tests passed，冻结清单 20 项无漂移；launchd 17:20 再次真实触发并返回 `waiting`，没有 Base 写入。22:20 fallback、手动补交额度和 active 优先规则保留。
- **地点数据。** 基于 f066 的 175,370 行离线逐字段迁移候选和 `prepare_candidate` 后产物已完成；独立 GPT-6 Sol 代码审查 PASS。准备后的 SHA 为 `fafd8033`，与原迁移候选 `7210f451` 不同。Windows 仅暂存该产物，服务器尚未接受地点迁移；原 Base 尚无新四列。详见私有 `audit-20260928/location-migration/sol-f066/` 与 `location-staging-20260928.json`。
- **9/28 原 run 已续跑。** 16:49 在 Windows 原 `runs/20260928` 上以 `--resume-run` 启动，16:51 正在 basic；原 21:35:30 截止和 P1 checkpoint 不重置，腾讯已成功阶段不重跑，未启动第二个逻辑实例。归档仍逐件运行，发布层遇容量或锁问题按其真实回执处理。
- **地点发布顺序已调整。** 当前 rebase 按整行判冲突、线上同 ID 胜出。9/28 已采的 basic 有 311 处、首段 P1 有 3,439 处同 ID 更新；如果先把 f066 地点迁移版发布，迁移会改变 175,073 个具名行，旧 run 的同 ID 内容更新会在 rebase 中被丢弃。用受审 `rebase_files` 的最小探针复现了这一结果。因此 f066 地点候选保持 `NOT_PUBLISHED`，须待原 run 的最新 accepted 落定后重新以该版本为基线生成逐字段候选并独立核验，不得把 f066 产物覆盖到后继版本。
- **仍待完成。** 原 run 的后续采集和终态（原 21:35:30 截止不延长）、新 accepted 基线上的地点迁移单次 CAS 及激活、原 Base 最新版本 Excel 导入与无人值守交付终态验收。9/25–27 未开始的采集不由只追加恢复补成“已采”。

### 3.3 2026-09-28 后续实测（截至 23:21，北京时间）

- **集成与部署。** B1 自动结算门修复已由独立 GPT-6 Sol 审查通过，98 个交付聚焦测试通过，PR #15 合入 `cfe5502`；交付机按该版本运行。Windows 与服务器的 B1/B2 业务文件仍按第 3.2 节所述受审 SHA 部署。采集机仍缺旧 `normalize_tables.json`，没有盲目安装带有错误地点默认映射的文件。
- **原日更 run 真实收口。** Windows 原 `runs/20260928` 自 16:49 续跑，未重置原 21:35:30 截止或启动第二个逻辑实例。总预算在段边界检查，截止前开始的末段于 22:05:37 自然发布并结算，收据为 `stage=partial-or-failed`、`collection.state=complete`、`p1_budget.exhausted=true`、`unconfirmed_publications=0`。3372 个计划单元中有结果 957 个：成功 497、部分 168、阻断 292；按计划键减结果键，未开始 2415，已尝试但状态未知 0。basic 为部分成功（退出码 2），已成功的腾讯阶段没有重跑。不能把这轮称为全来源日更完成；9/25–27 未开始的采集仍未补齐。私有终态摘要见 `audit-20260928/run-terminal-20260928.json`。
- **接受、服务与容量。** 末段 CAS 在 22:05:34 接受 `2ddc2c0f65ed1518dfb6dcfa2caec50c89c3710da1ce5c078c93d4223a0754de`，Windows manifest、工作基线和服务器文件 SHA 一致，原始行 175901、797144629 字节。22:00 定时激活实际服务的还是上一版 `0d4a80f4`；22:28 对最终 SHA 单次执行已有的受控激活器，22:30 返回 `activated`，实际 served 与控制账本均为 `2ddc2c0f`，服务投影 173966 行。20:00 激活 `7e24ba28` 曾超时而实际服务稍后加载，21:00 与 22:00 定时激活随后各自成功；120 秒 warm 界限的修复尚未独立审查或部署。因此这次包含人工续跑和手动激活，**不能称为全流程无人值守验收**。最终激活收据见 `audit-20260928/final-activation-2ddc-20260928.json`。
- **备份保留。** 9/28 共 66 个服务器旧备份逐件归档、校验、删除，归档收据终态 `target_met`，副本在外盘 `生财MCP/归档/服务器备份/20260928`。后续各段接受又产生新备份；22:06 服务器空闲 7915249664 字节。下一次处置必须按最新 accepted、served、Base 与在途状态重算保护集，不能沿用旧删除计划。
- **Base 真实交付。** `com.maxzhl.qiuzhao-feishu-deliver-latest` 已在 16:20、17:20、18:20、19:20、20:20、21:20 实际检查且未误开批。22:20:07 的定时任务因原 run `collection.state=complete`，以 `run_settled` 而非保底触发，自动对最终 `2ddc2c0f` 开了当天唯一批次。投影、Excel、抽样、schema 快照与 11 张新表导入完成后，schema 修复先因飞书 Excel 导入把标题“国家/地区”“州/省”改成“国家|地区”“州|省”而在查字段时失败；随后 5 个字段更新失败。人工只在新待切换表按原 ID 将 22 个字段改回斜杠名，保留类型、选项和单元格；另外按受审目标补齐 5 个字段的类型、选项或 URL 样式，并读回。两次手动执行同一 `deliver-latest --apply` 仅续 active 的 `2ddc2c0f`，没有另开批或重复导入。23:15:45 终态 `delivered`：11 张新正式表共 173966 行，verify 对 schema、行数、ID 集合和单元格等 11/11 表通过，错行 0；旧 11 张表按 07205aef 版名归档。平台表清单共 22 张（新正式 11 + 旧归档 11）；账本 `last_delivered=2ddc2c0f`、`active=null`，与 accepted、实际 served 一致。23:20 的下一次 launchd 实际触发返回 `up_to_date`（退出码 0），没有第二批或重复导入。这是一次**自动起批、人工排障续跑后完成的交付**，不是全流程无人值守验收。综合私有收据：`audit-20260928/base-final-2ddc-20260928.json`。
- **地点数据。** 针对最终 `2ddc2c0f`（175901 原始行）在外盘离线运行原独立审查通过的 `8bce6319` 迁移脚本并核对源码 SHA，候选及逐字段可逆差异通过非地理字段、ID 和顺序检查。经生产同款 `prepare_candidate` 后，仅联想官方 81482 一条有 ID 记录需地理修正，297 条匿名记录按原位恢复；准备版仍标记 `NOT_PUBLISHED`。Base active 的 `2ddc2c0f` 批次运行期间没有让地点候选越过它；候选还须独立数据审查，当前未执行地点 CAS、激活或 Base 地点版导入。私有审查包在外盘 `生财MCP/归档/地点迁移/20260928/candidate/review-packet.json`。

### 3.4 2026-09-29 日更与交付实测（截至 18:18，北京时间）

- **采集终态。** Windows 原计划任务于 01:00:01 启动当天唯一逻辑 run，16:17:28 自然结算；收据为 `stage=partial-or-failed`、`collection.state=complete`、无未确认发布。P1 的 3372 个计划单元全部有结果：成功 2847、部分 182、阻断 343、未知 0、未开始 0。basic 退出码 2（新增 0、更新 49、仅观察 4901、标记移除 61），腾讯退出码 0，P1 退出码 2，normalize 退出码 0。**全部尝试不等于全部成功或所有内容已更新。** 失败原因字段的粗分中，部分结果有 109 个未映射的官方招聘类别、15 个超时或连接问题；阻断结果有 62 个公开渠道/招聘范围不覆盖、57 个超时或连接问题、21 个缺官方 scope 证据，另有 133 个阻断结果未在 `coverage.errors` 中填错误文本。粗分只用于定位来源，不代替逐来源证据；私有摘要见 `audit-20260928/run-terminal-20260929.json` 与 `p1-failure-groups-20260929.json`。
- **接受与服务。** 最后一次 CAS 于 16:17:24 接受 `a8adaba930eda8bdd39b595c855ca4eaef2eb7a90d0d2e6dcc1c04d78fe0dcfc`，原始记录 176757；Windows 最终 manifest、工作基线与服务器接受版本一致。17:00 小时激活的实际回执为 `activated`，17:01:54 加载同一 SHA，服务投影 174822 行；没有为最终版另做人工激活。采集机仍报告缺 `qiuzhao/normalize_tables.json`，其旧映射含有毒地点默认值，没有盲目补装。下一轮自动运行仍须按实际收据验收。
- **Base 同版交付。** 16:20:07 的 launchd 在 run 已结算后以 `run_settled` 对 `a8adaba9` 开当天唯一自动批次。Excel 导入生成 12 张待切换表；飞书仍把 24 个斜杠字段名改成竖线，随后 3 个字段的类型/选项更新失败。人工只针对这些新表按原字段 ID 修复并读回，随后两次用同一 `deliver-latest --apply` 续 active，没有另开批、重复导入或改正式旧表。17:11:48 verify 对 12/12 表的 schema、行数、ID、单元格及视图等关卡全部通过，合计 174822 行、错行 0；17:13:38 switch 完成，12 张新表成为正式表，旧 11 张表按 `2ddc2c0f` 版名归档且读回通过。账本 `last_delivered=a8adaba9`、`active=null`，与 accepted、实际 served 一致。17:20:06 下一次真实 launchd 检查返回 `up_to_date`、无告警，当天自动批次仍仅一条。12 张来自既有单表容量分片规则新增“其他行业岗·续表6”，**不是**第 10.2 节的中性编号改名。私有综合收据见 `audit-20260928/base-final-a8ad-20260929.json` 和 `base-scheduled-1720-a8ad-20260929.json`。本轮是自动起批、人工修复后同版交付，仍未通过全流程无人值守验收。
- **容量与地点边界。** 9/29 前六批先归档 23 个旧 gzip；当天最终 accepted、served、Base 均为 `a8adaba9` 后重新冻结保护集和候选，第七批再将 10 件先传回外盘、逐件校验后精确删除。18:18:16 收据终态 `target_met`，当天累计 33 件，服务器空闲 8,231,755,776 字节，高于本次按发布频率重算的 7,823,224,158 字节目标与 2,947,257,108 字节容量门；最新 8 个 gzip、当前版本和在途保护未放松。下一次处置仍须重算保护集，不能沿用本批候选。私有摘要见 `audit-20260928/retention-20260929T1818-final.json`，原归档收据在 `生财MCP/归档/服务器备份/20260929/retention-receipt.json`。9/28 的 `2ddc2c0f` 地点候选已经落后于当天 accepted，仍为 `NOT_PUBLISHED`；地点纠错没有进入当前服务或 Base，若继续须从 `a8adaba9` 或更新基线重算并独立审查。

### 3.5 2026-09-30 终态与 10-01 补交（截至 10-01 22:38，北京时间）

- **9/30 采集终态与容量。** 当天 01:00 自动任务先被 Windows C 盘容量门阻断。经对历史已完成冷文件逐件 SHA、大小、修改时间核验，使用 Windows 原生 NTFS 压缩原位恢复空间后，于 02:38 只续原 `runs/20260930`，未重置原 P1 预算。17:55:38 因 C 盘再次低于原门而以 `stage=partial-or-failed`、`collection.state=stopped` 结束。3372 个计划单元中 3333 个有结果：成功 2824、部分 188、阻断 321、未开始 39；没有全目标成功。原截止已过，39 个未开始单元不得用新预算冒充 9/30 日更。一次性 `Qiuzhao-Collector-Resume-20260930` 后来精确禁用，日常计划任务保持启用。压缩不删除或移动源文件，也不改变容量门；私有收据见 `audit-20260928/windows-capacity-recovery-compression-summary-20260930.json`、`resume-once-task-disabled-20261001.json`。
- **接受与服务。** 9/30 最后一次 CAS 于 17:55:33 接受 `8abfa95df1eaa1cfdc5c8cfdf462f586089e90c7f5a7d9acbe912f8843f560a0`，原始记录 177288。18:02:10 实际服务切到同版；10/1 22:00 小时激活回执为 `unchanged`，原因是该版本已经在线，无须重启。该版本没有包含尚未发布的地点迁移候选。
- **同版飞书交付。** 9/30 22:20 自动保底只对 `8abfa95d` 开一批，12 张待切换表导入完成。冻结的 schema 修复程序仍遇 Excel 将 24 个斜杠字段改名为竖线，另有 3 个投递入口 URL 样式、1 个办公方式多选及选项、1 个状态选项与正式表 schema 不符；人工只在新 staging 表按原字段 ID 完整保留属性修复并逐项读回，没有部署未审代码、重复导入或另开批。同一 active 续跑中，`clean_blank` 曾因飞书读取第 13000 偏移发生 `unexpected EOF`，按既有阶段恢复后通过。10/1 20:34:01 verify 对 12/12 张表的 schema、行数、ID 集合、单元格、去重、视图顺序和主字段均通过，20:36:18 切换为正式 12 表；账本 `last_delivered=8abfa95d`、`active=null`，与 accepted 和实际 served 一致。这是自动起批、人工字段修复及同版续跑后完成的交付，**不是无人值守验收**。私有收据见 `audit-20260928/base-schema-slash-verify-8ab-20261001.json`、`base-schema-five-verify-8ab-20261001.json`、`three-layer-light-20261001T2140.json`。
- **10/1 日更终态与仍在途的容量处置。** 当天 01:00 日常任务已启动，但 C 盘低于原门，收据 `collection.state=stopped`；basic 退出 1 且回滚、腾讯退出 0 并观察到 2 项更新，P1 计划未生成，不能把其数目写成 0。21:46 前又对 9/30 的 26 个历史冷候选逐件原位压缩并核验，C 盘空闲从约 6.50 GB 升至 15.19 GB；21:47:34 在原 `runs/20261001` 上启动单实例续跑，原 P1 截止 **21:56:44.600** 不变。启动时的多个临时副本曾使空闲量迅速降至 3.39 GB，随后回升；因此压缩达到的是本次短窗口余量，**未证明可持续整日容量**。22:20:13 续跑真终态为 `stage=partial-or-failed`、`collection.state=complete`：basic 退出 2，仅部分成功（新增 12、更新 1284、仅观察 6403），腾讯成功阶段没有重跑；P1 因原预算到点从未启动段，计划未生成，不得把空的 pending 列表解释成全目标完成。运行器在零 P1 段路径因 `KeyError: 'normalize'` 中断发布，`delivery.publication=pending`、未确认发布 0；截至 22:21 accepted、实际 served 与 Base 都仍是 9/30 的 `8abfa95d`，**10/1 已采的 basic 变化尚未交付**。一次性 `Resume-20261001` 在真终态后精确禁用，Daily 仍计划于 10/2 01:00 运行。零段补发的私有代码候选独立 GPT-6 Sol 审查给出 FAIL，尚未部署；原受审规范化模块对当前 staging 做只读 `--check` 显示填充 0、既有非空值变化 0，但此结果不能单独代替逐字段数据审查。服务器根据当前 accepted/served/Base 与回滚版本重算保护，受审旧 gzip 归档仍独立串行执行中，不能把在途传输计为已释放空间。私有收据见 `audit-20260928/run-terminal-20261001.json`、`resume-once-task-disabled-20261001.json`、`collector-zero-segment-fix/normalize-check-20261001.json`、`windows-cold-930-compress-summary-20261001.json` 和 `retention-apply-20261001.json`。

### 3.6 2026-10-01 修复接管（截至 23:31，北京时间）

- **零段已采成果恢复。** PR #21 合入 main `8b6c352`，零段修复源码未改历史独审通过字节；23:10:41 Windows备份旧版fdb4565e并原子部署SHA `1b5468413cabc9863cd7eab07f4da5a2d93e2b7b89257e86770397e3f6ef05f5`。23:11:26仅复用原Resume20261001计划任务，以原身份/cwd/venv执行 `--resume-run`；原截止不延长，P1不重开。23:23终态实际接受3e784（177300原始身份），direct CAS/rebase0/conflicts0/未知发布0；原KeyError已解除，basic仍部分成功且P1零段，不改成全来源成功。23:24同版一次性task已禁用，原daily计划继续01:00。23:26:33受控单次激活实际served=3e784、175366投影；Base普通deliver-latest已起同版批次，未force新批，仍待供应商导入和切换终态。收据：`collector-zero-segment-fix/deploy-gpt61-20261001.json`、`publication-only-start-gpt61-20261001.json`。
- **飞书复发修复代码。** 私有原schema候选经独立GPT-6.1 Sol low审查发现description及staging正向保护缺口，最小修复后当前脚本SHA `02be32bc43693efda027b50eac431639ff7073e63455ca22849768649ce66ec2` 获PASS。真实8ab工件12表身份校验通过；集成测试99 passed、1 skipped，20项交付runtime哈希匹配。PR #22合main `00a911a`，在Base active=null且无交付进程窗口进入交付机受控运行依赖；真实供应商修复与无人值守仍待后续同版交付验收。收据：`schema-review-gpt61-20261001/review-receipt.json`。
- **长期容量和缺口。** 10/1服务器归档陈旧running只有5件验证删除，不能作正在运行或已完成；恢复前必须重核保护与plan。23:13 Windows C约22.12GB、D约66.7GB，不按旧13.87GB继续推算，也不等同整日容量已满足。每key缺口、地点纠错、长期有界容量仍待实测；仅已采成果补交不能补成全目标成功。
- **持续记录。** [踩坑正文](qiuzhao-collection-pitfalls.md)维护现象、影响、根因、最小修复、验证、回滚与复发；[方法库](collection-methods/README.md)维护来源方法。automation-4同ID保持ACTIVE及原周期/target/通知文字/停止条件，执行和独审模型更新为GPT-6.1 Sol low；代码完成不会停止监控。

## 4. 2026-09-24 真实时序

| 时间 | 事件 | 状态层 |
|---|---|---|
| 00:00:31 | d516c351 交付飞书（首次真实补交，10 表） | Base |
| 01:00 | Windows 计划任务启动全目标日更 run 20260924 | 采集 |
| 01:34:35 | 首批 5 家扩源 213 条随 1244d37f 交付飞书 | Base |
| 03:55:37 | bd4f0f70 交付飞书（11 表 162,380 行） | Base |
| 05:20:57 | 科大讯飞 campus 离线恢复 13 条被服务器接受 | accepted |
| 13:11 | 服务器容量门阻断发布；独立审查后归档 23 个旧备份，腾出 1,666,174,976 字节，同一 run 续跑 | 服务器 |
| 17:50:06 | run 20260924 终态，accepted cff69dce | accepted |
| 17:57–18:40:19 | 定向补采 74 个单位，一次执行 | 采集 |
| 18:56:23 | 一次 CAS 发布，receiver 回执 `published=true`，cff69dce → 07205aef（171,976 身份） | accepted |
| 19:00:01 | 小时激活，服务切到 07205aef（170,038） | served |
| 19:41:12 | 飞书切换完成，ledger 记录 07205aef 已交付 | Base |

从 bd4f0f70（02:46 接受）到 07205aef 共 30 次服务器接受，含主 run 各段、两次恢复发布和定向补采；每一步都有采集机 accepted 清单记录父版本，飞书交付据此证明新版本是已交付版本的后继。

### 首轮与补采（分开统计）

| 批次 | 单位 | success | partial | blocked |
|---|---:|---:|---:|---:|
| 首轮 run 20260924 | 3,372（全部尝试） | 2,856 | 188 | 328 |
| 定向补采（一次执行，预算截止 21:30:03，实际 18:40:19 结束） | 74 | 16 | 17 | 41 |

- 补采只选网络暂时故障 60 个、飞书锁串行 12 个、51job 已修复 2 个单位；4xx、未知原因、已隔离和不支持的单位不在其中。
- 科大讯飞 intern/social 离线验证 31/729 条，与库内去重后实际新增 19/5 条；campus 没有重采。
- 补采结果先过来源守卫：新结果的来源必须与原配置、原始结果或已接受行中同一公司的来源一致；共享招聘平台按租户（Moka 组织、51job 项目与 CtmID、Hotjob 站点 ID、飞书子域）区分；无法绑定的单位只隔离不发布。本次 35 个可用单位（补采 success/partial 33 个 + 讯飞离线 intern/social 2 个 scope）全部通过，隔离 0。
- 构建只追加：旧 170,925 条原始记录的完整字段内容与重复次数不变（文件内排序曾变化，见第 8 节），新增 1,051 条原始记录；merge 想做的 6,587 处更新和 114 处下架均未应用；首批 213 条和讯飞 13 条全部保留。

## 5. 三步计划的实现状态

**第一步：已采内容可靠交付——人工监督下可恢复的交付已投产，不是无人值守日更。**

- 发布工作基线随服务器真正接受的冻结产物推进；外部冲突三方合并；回执丢失或中途写入时恢复程序对齐实际版本；deferred 不标全流程成功；常规与恢复路径共用 unsafe_writer、退役与完整性保护；逻辑运行的截止与已用预算持久化（PR #1）。
- 服务进程只持有一份数据集；每小时整点受控激活已接受的新版本并核对 served sha；发布端遇 receiver 锁忙时延期而非终止（PR #3）。
- Excel 日更：服务器接受版本 → 固定投影与 xlsx → 导入同一 Base 的临时子表 → schema/空行/verify → 切换 → 账本记录。同版本不重复导入，失败从记录的阶段恢复（PR #1、#6）。
- 2026-09-24 的四次飞书交付均为人工监督下执行。Windows 采集流程不会自动调用 Excel 交付：它写出的 `delivery_summary` 中飞书一项为 `not_requested`，飞书交付需要另行启动（见第 9、10 节）。

**第二步：减少重复采集——部分实现。**

- 缓存身份与逻辑运行隔离、调度修改已合入（PR #1）；Windows 锁竞争改为可等待的 `BlockingIOError`（PR #5）。
- 24 小时实际缓存收益未实跑测量；按域名/租户并发的 canary 未开始。

**第三步：小批扩源——首批已交付。**

- 首批 5 家 213 条已进入服务器与飞书。其中新出现的名称标签不等于新集团，不作新公司宣传。
- 其余候选只做了准备，不计为已覆盖公司或已交付岗位。

## 6. PR 与部署证据

“已核对”指采集机上的文件 sha256 与 main 同路径文件一致（2026-09-24 定向补采启动前自动校验，或当日运行时实测）；“按收据”指只有当时的部署记录，本轮未重新核对 hash。

| PR | merge | 内容 | 部署证据 |
|---|---|---|---|
| #1 | `62e9a8f` | 发布恢复、Excel 交付、减少重复采集 | `windows_collector.py`、`windows_rebase.py`、`p1_pipeline.py` 已核对（含后续 PR 的修改）；`windows_excel_delivery.py` 在交付机从 main 直接运行；`windows_recover_run.py` 按收据 |
| #2 | `c5e2c2e` | collection-gap 分母与缓存计数 | `normalize.py` 已核对；`collection_gap.py` 按收据 |
| #3 | `e8cff9b` | 单数据集服务、小时激活、锁忙安全发布 | 服务器 16:00–19:00 每小时激活收据；服务器侧文件 hash 按收据 |
| #4 | `f1d801e` | tupu360 正文/证据、18 个身份精确隔离 | `p1_pipeline.py` 已核对；`p1_platform_tupu360.py` 按收据（01:11:49） |
| #5 | `f30ef11` | Windows `LOCK_NB` 竞争 | `portable_runtime.py` 已核对（12:43） |
| #6 | `f721c85` | 归档表名按被替换版本唯一 | 交付机从 main 运行；19:41 切换使用 `（20260924-bd4f0f70版）` |
| #7 | `65c725f` | 讯飞证据路径 | `p1_sources_21_30.py` 已核对（有部署前备份） |
| #8 | `10dea61` | 51job 证据与假标题 | `p1_platform_51job.py` 已核对（06:21:50 部署）；首次实际运行是定向补采的百事、马夸特 campus |

## 7. 持续代码与一次性恢复工具

**持续依赖的运行代码**（2026-09-28 起均在本仓库，受审版本记录在 `deploy/qiuzhao-deploy-manifest.json`）：

- `deploy/windows_excel_delivery.py` 在运行时从 `deploy/feishu_r1/` 加载 6 个 R1 脚本（投影、xlsx、schema 快照、导入、schema 修复/空行清理/verify、切换）；2026-09-24 用的是仓库外的同名原件，见第 3.1 节。
- 服务器 receiver 调用的容量门/备份轮转模块（要求空闲空间 ≥ 2 × jobs.json + 上传上限 + 256 MiB）的受控副本为 `deploy/windows_receiver_rotation.py`，与线上逐字节相同（PR #12）。

**一次性恢复工具**：以下工具经测试和独立审查后只在本地恢复证据目录中运行，**不在本仓库、未合入 main**，也不再使用：

| 工具 | 用途 | 状态 |
|---|---|---|
| `server-backup-archive/archive_batch22.py` | 容量阻断时归档 22 个旧备份（先传回验证再逐个删除；另 1 个先行单独归档） | 独立审查通过，已执行 |
| `feishu-20260923/delivery/p1-failure-queue/targeted/targeted_recovery_20260924.py` 及测试 | 74 单位定向补采、来源守卫、只追加构建、一次 CAS | 审查 v4 未通过、v5/v6 通过；collect 用初版运行，guard/build/apply 用 v6（42 项测试） |
| `expansion-first5-20260924/publish/publish_iflytek_campus_recovery.py` | 讯飞 campus 13 条离线恢复发布 | 已执行 |

飞书交付账本、策略、各版本状态和 verify/switch 收据同样只在本地恢复证据目录（`feishu-20260923/delivery/` 下），不入库。

## 8. Excel 交付的运行要点

- 交付机 Python 必须有 openpyxl；仓库 `.venv` 缺该依赖，2026-09-24 用系统 Python 3.13（openpyxl 3.1.5）运行。
- 快照以 gzip 流一次传回交付机并核对 sha256，不下载未压缩文件。
- 采集端 `preserve()` 会把无 id 的旧记录排到末尾。2026-09-24 定向补采构建首次因此被逐位校验拒绝，改为按该顺序写出后通过；旧记录内容不变，但文件内排序与旧版不同。
- 账本记录的“已归档表”可能被人工删除。07205aef 首次导入因此在建表前拒绝；按导入脚本当时读取的真实表清单对账后，同一版本续跑，没有改代码。
- lark-cli 读取记录时偶发网络 `unexpected EOF`；schema 修复、空行清理、verify 各出现一次，均为同版本幂等续跑一次通过。不做无界重试，不手改阶段状态。

## 9. 待处理风险

- **来源成功率未到 100%。** 9/29 虽然 3372 个计划单元全部尝试，仍有 partial 182、blocked 343；9/28 另有 2415 个未开始。失败原因按现有状态和证据定位，不把“已尝试”写成“已更新”，也不无差别重采。
- **飞书无人值守闭环仍待验收。** Windows 采集流程不会直接调用 Excel 交付（`delivery_summary` 的飞书一项为 `not_requested`）。9/28 与 9/29 的 launchd 都自动开了当天唯一批次并最终交付，但飞书 Excel 导入器把含斜杠字段名改成竖线，后续字段类型/选项更新也失败；两轮都依赖人工修复待切换表和同版续跑。现有 CLI 封装在失败时只记录 stdout，漏掉 stderr 中的详细错误。须对真实导入形态与报错捕获做最小、独立受审代码修复，并在后续计划运行中验收无人值守；两轮终态不能倒推长期自动可靠。
- **日更长期自动运行仍待验收。** Windows 01:00 计划任务与服务器小时激活均已配置；9-25 至 9-28 的四轮实际遇过容量门，9/28 原 run 还需人工续跑和一次人工激活。9/29 计划任务按时启动，P1 全部尝试并自然结算，最终 SHA 由 17 点定时任务实际激活；但 basic 部分成功，P1 仍有 182 个部分和 343 个阻断，采集机仍缺受控 `normalize_tables.json` 资产。后续轮次继续按实际收据验收。
- **服务器备份仍消耗空间。** 9/28 精确归档 66 件，9/29 在最终版落定后累计归档 33 件；18:18 的本批容量目标已达。后续发布还会产生新备份，必须按最新 accepted、served、Base 与在途保护集重算才能继续归档，不能复用旧计划（见第 3.4 节）。
- **地点候选尚未发布。** `2ddc2c0f` 的离线字段候选通过本地语义校验，但独立数据审查尚未完成，且已落后于 9/29 的 `a8adaba9`。当前服务与 Base 均不能宣称联想官方地点已纠正。若将来从最新基线重算候选、通过审查并发布，仍须分别核 accepted、served、Base 三层。
- **测试基线已知失败。** 首次部署前的组合检查为 211 passed、1 failed、6 skipped；失败的 pipeline 超时 checkpoint 测试在改动前的原实现上可复现同样结果；6 个 XLSX 用例因 `.venv` 缺 openpyxl 跳过，用系统 Python 另行通过。
- 30 分钟总控 heartbeat `automation-4` 于 9-28 保持 ACTIVE，后续执行模型为 GPT-6 Sol；它与 Windows 采集计划任务、服务器激活、飞书 launchd 是不同的调度，互不代表业务成功。

## 10. 后续优化的历史诊断与已批准批次

以下诊断在 2026-09-25 对 07205aef 版只读完成，当时**未实施任何修改**。此后 B1/B2 已获批准并按第 3.2 节部署，地点数据迁移和 Base 切换仍以真实回执确认。下文历史诊断分母统一为飞书投影 170,038 行（原始 171,976 行中剔除 removed 845、无效 1,085、测试 8），不能当作 f066 版当前统计。

### 10.1 诊断结论

**行业分表。** 只有互联网/科技、国企/央企、制造/工业三个行业各有专表，其余全部落入“其他行业岗”。

| 口径 | 行数 | 占 170,038 |
|---|---:|---:|
| “其他行业岗”表组（6 张表） | 111,138 | 65.36% |
| 其中行业值本身为“其他” | 95,806 | 56.34% |
| 其中行业明确、只因没有专表而并入 | 15,332 | 9.02% |

- 行业值来自 `qiuzhao/normalize.py` 的 `_fill_industry`：先查 `normalize_tables.json` 对照表，再用正则匹配招聘单位名，都不命中则为“其他”。对照表于 2026-09-11 用旧库生成，不含联想（已核），其他 P1 公司的覆盖未逐一核对；字节跳动、小米、美团、联想等头部公司的行业值都是“其他”（原因只对联想做了核实）。
- `qiuzhao/collector/lark_sync_enrichment.py`：全量投影确实调用其中的 `business_fields`，但不经过 `route()`/`new_fields()` 的行业路径；硬件公司归类只在增量追加路径生效，两条路径的行业结果因此不一致。`route()` 对未知公司兜底为“互联网/科技”，不能直接复用到全库。`_fill_industry` 遇到已有值（包括“其他”）会跳过，所以对存量记录不会自动修正。
- **联想**：按公司字段严格统计 1,276 条，全部为“其他”。按“公司或 URL 含 lenovo”的宽口径是 1,277 条，多出的 1 条公司字段为“英特尔”，属于待查异常。两个口径不混用。
- 公司行业与岗位职能是两个维度：`行业` 描述公司，`岗位大类` 描述职能（如市场/营销）。按行业分表让用户把“其他行业岗”误读为“其他类岗位”。

**地点缺失。** `工作地点=未注明` 共 43,224 条（25.42%）。其中 39,477 条原始 `cities` 非空，但包含“未知”“未披露”这类值，所以 39,477 只是可恢复的候选上限，不能说全部可以恢复。

- 采集阶段：联想适配器只取城市，丢掉了页面上的国家和州。
- 规范化阶段：城市元素不在对照表或已知城市集合里就被改成“未披露”；字段只在为空时写入，错误值此后不会被修正；城市未知的记录一律补成 `country=中国`、`region=mainland`，海外岗位因此被标成中国大陆。
- 地区推导：`qiuzhao/v4_fields.py` 的 `region_of` 只要有城市就按 `city_region` 判断，不在海外城市白名单里的城市一律算“中国大陆”，即使记录的 country 是美国。例如 `region_of({'country':'美国','region':'overseas','overseas_flag':True}, ['Morrisville'])` 返回“中国大陆”。海外城市白名单里还包含“远程”，国内远程岗位可能被误归为海外。
- 对照表本身也有默认值：`normalize_tables.json` 中 `city_to_region['未披露']` 为 `mainland`（计数 598），`city_source_to_country['未披露\x1f']` 为 `海外`（计数 0）。因此补回这张表不是中性操作，必须和地点样例一起验收，不能直接补表后全库重算。
- 采集机上缺少 `qiuzhao/normalize_tables.json`，有两份证据：2026-09-19/20 的历史部署收据，以及 2026-09-25 00:16:51（北京时间）的只读实测（`is_file=False`，SSH 退出码 0）。不能据此回溯声称 2026-09-24 全天都已实时确认缺失。这是部署资产完整性问题；仅补回这个文件，仍解决不了 `Morrisville` 这类词典外地点被丢弃、以及已写入的“未披露”不会被覆盖的问题。

**官方实证（联想）。** [Global Media Strategy Manager B2B](https://jobs.lenovo.com/en_US/careers/JobDetail/Global-Media-Strategy-Manager-B2B/81482)（Req WD00104952）官方页标注 Career area 为 Marketing，地点为 United States of America / North Carolina / Morrisville，JD 写明 remote。库内记录 `p1-4e448b5631f14405b03f63c3` 采集到了 `cities=["Morrisville"]`，但规范化后为 `未披露`，并被默认补成 `country=中国`、`region=mainland`；飞书显示“工作地点=未注明”“行业=其他”。标题里的 “Global” 不能推出全球远程；地理位置与办公方式（remote）应分开记录。

### 10.2 外部复审与建议批次（历史诊断及当前执行边界）

2026-09-25 对文档基线 main `0d5313fe`（tree `8360ac98`）做了一轮外部复审（ChatGPT Pro，约 21 分钟），附件为该提交的完整仓库包、本文副本、复审上下文和 6 个外置 R1 脚本。这不是对全部 2,023 个文件的逐行审查；复审方自述的隔离测试结果（109 passed、1 skipped）不等于本地全项目测试通过。复审记录保存在本地恢复证据目录，不入库。

吸收后的建议分四批。每批按第 11 节流程执行并取得实测结果后才更新状态。截至 2026-09-29 18:18，① 的容量延期、备份保留和自动 Excel 调度已经部署，9/28 与 9/29 的最终 accepted 版 Base 批次均经人工排障同版续跑后真实交付；② 的地点代码已部署，但对最新数据的纠错候选仍未发布；③④ 未实施。实际结果与证据见第 3.3、3.4 节，不能用 9/25 的历史诊断替代当前生产统计。

**① 交付最小闭环（最先）**

- 把持续依赖的 6 个外置 R1 脚本和服务器 receiver 的容量/轮转增强纳入受审部署清单，记录依赖 hash 和解释器；补齐采集机上的规范化资产（见上文，需与地点样例一起验收）。
- 容量与备份保留有界：归档经验证后才删除。
- 最新 accepted 的后继版本触发现有 Excel 交付；有未完成（active）的版本先续跑，不对每个 accepted 版本都整库导入。
- accepted、served、Base 分别告警；提交结果未知时先核对，不盲目重发。激活失败而被跳过的版本需要显式恢复；“未变化”不等于新的健康证明。
- 验收：在真实计划任务账号下，一轮中无人工补关键阶段，完成 accepted / served / Base 版本一致且同版本幂等，才称“单轮无人值守验收”；这不代表以后每天都有保证。下一次实际计划运行的结果要在执行前后核验，不预设日期或结果。

**② 地点全链路（P0，可与 ① 并行准备）**

- 覆盖 normalize、`cities_of`、`region_of`、`convert`、联想适配器、两条合并路径，以及 R1 的列定义与校验。
- 规则：已采集的原始地点优先；国家未知就保持未知，不默认中国；合法的 country/state/city 原样保留，新采集缺字段不能覆盖旧的可信值；remote 是办公方式，不能替代地理位置；country、state、办公方式要真正进入 MCP 返回和飞书列。
- 修复复发点：`run.py` 按 `NORMALIZED_FIELDS` 继承旧值，`p1_pipeline` 用新记录整体替换旧记录，两者都会让修正后的地理字段被旧值或新缺值覆盖；只针对地理字段处理，不让旧的整行复活。
- 字段纠错不伪造来源站点的更新时间。
- 验收用固定用例，不逐岗重抓官网：联想 81482（Req WD00104952）为美国 / North Carolina / Morrisville + remote；另加国内、海外、未知、多地点、出差地、总部等反例。报告缺失率和误标“中国”记录数的实测变化。

**③ 行业与表名（小范围）**

- 少量高价值公司的行业映射收敛到一个入口。联想建议产品口径为“互联网/科技”（含 IT 硬件），岗位职能为市场/营销；这与现有增量路径把联想归为“制造/工业”的映射不同，需一并统一；“国企/央企”是企业性质，不在这次做全库主数据工程。
- 9/25 提议对当时的 11 张正式表原位改名为“岗位库01 … 岗位库11”，记录集合和表 ID 不变。9/29 依现有容量分片规则已形成 12 张正式表；实施编号前须先按当前表数重定编号，再同步更新账本、交付策略与 R1 脚本里写死的正式表名，并用下一轮交付验证兼容。目前未执行编号改名。
- 之前提议的 9 张表重新切分暂缓：只少 2 张表，解决不了跨表筛选。MCP 已支持全库检索；飞书跨表一次筛选目前没有实现。

**④ 继续小批扩源**

- 失败来源只在原因明确发生变化后定向重试。
- 核对已批准的来源清单与实际加载的 registry 数量是否一致。注册代码中的 `try/except: pass` 可能静默漏注册，这是代码风险，目前没有证据表明生产已经发生。

## 11. 变更流程

执行分支 → 实际 diff 与针对性测试 → 独立代码审查 → 解决发现 → 合入 main → 部署明确 commit → 回读与小批运行回执。部署前确认当前生产版本及仍在运行的采集任务；未取得服务器、飞书真实回执时只报“代码实现/模拟通过”，不报“已上线”。


### 3.7 2026-10-02 normalize 故障证据补充

10/2 第7个 P1 段后 normalize 的生产日志确认 `json.load → fp.read → UTF-8 decode → MemoryError`；05:42:11 receipt 为 partial-or-failed、collection stopped、publication pending。第6段最后 accepted 记录为 `c808646a...`，这里只作历史收据，不冒充当前 served/Base。前6次 normalize 均成功且 tables_loaded=false，因此缺 normalize_tables.json 不是该 MemoryError 的直接证据。20:54 回滚后 staging 为 806,915,187 bytes / SHA256 `372f47f3...`，不是失败瞬间输入的位级副本；历史 RAM/pagefile、当前三层状态本证据未查询。

PR #27 第二轮针对该真实失败路径修复长记录重复解析并补安全冻结门，仍为 draft、未部署；新字节须重新独审及 Windows 完整 checkout/目标环境验证。恢复边界不变：不重采、不重置预算、不延截止、不发布、不调用 Base。


## 2026-10-08 B安装阶段实际回执

PR27已合main `b643a16f5831c8a70a5a65935035f8aec4166534`，合并树13个运行/必要资产SHA与独审一致，目标normalization table依然合法缺失。C五文件在原runner锁/Scheduler安全/相关writer检查/旧15指纹/原容量门下备份并安装，23:33实际终态installed-byte-verified；备份目录`C:\mcp-suite-collector\recovery\normalize-code-backup-20261008T153341374443Z`，新依赖/入口及冻结清单逐件回读通过。仅原normalize被替换，其余四件此前缺失；没有安装源配置（生产已有相同3b2参数）、旧表、地点迁移或其他服务文件。

当前仅绑定现场source/receipt并执行C normalize-only，仍未发布；原P1/basic/tencent不运行，旧预算/deadline不延长。B不得据安装完成宣告三层交付完成。五文件安装helper已独审及真实原子复制三项测试；可捕获异常回滚，强杀/断电须按真实journal+backup人工恢复，不称硬中断自动恢复。
