# RECEIPT: 平台级适配器(北森 zhiye.com + Moka)——一个适配器覆盖一批公司

分支:`feat/platform-adapters`(基于 `fix/collector-partial-keep`,worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/platform-adapters`)
日期:2026-09-18 执行:DeepSeek Harness 范围:通用适配器 + 配置 + 单测 + 10 家真实只读采集验证 + 未采完公司的多轮有界续采 + 对比。
**未部署**:未 SSH、未碰阿里云、未调飞书、未登录任何站点、未 `--apply`、未写库、未 push、未合并。所有真实请求只打北森/Moka 公开接口并遵守限速。

---

## 0. 一句话结论

新增两个平台级适配器 `p1_platform_beisen.py` / `p1_platform_moka.py` + 一份配置 `p1_platform_companies.json`,对外契约与现有 `p1_sources_*` 完全一致;**新增一家公司 = 在配置里加一行**(REGISTRY 自动并入,有单测证明)。

首批 10 家真实 `campus` 只读采集**全部 `success/complete`**:北森 4 家(29/104/59/16 条);Moka 6 家(24/25/61/160/12/11 条),其中首轮受 20 请求/租户预算限制而 `partial` 的 4 家,已用「持久化详情缓存 + 多轮有界续采」补齐(18 轮,单轮仍 ≤20 网络请求/租户)。库内 3 家 Moka 的岗位 id/标题集合与专用适配器**完全相等**(⊇ 成立)。

---

## 1. 交付物

| 文件 | 说明 |
|---|---|
| `qiuzhao/collector/p1_platform_beisen.py` | 北森通用适配器(按 tenant slug 参数化) |
| `qiuzhao/collector/p1_platform_moka.py` | Moka 通用适配器(按 org/siteId 参数化,复用现有请求/AES 解密/详情缓存) |
| `qiuzhao/collector/p1_platform_companies.json` | 公司配置;两个模块的 `COMPANIES` 都从这里读 |
| `qiuzhao/collector/p1_pipeline.py` | **仅 REGISTRY 处 5 行最小改动**(见 §2.4) |
| `tests/test_p1_platform_beisen.py`、`tests/test_p1_platform_moka.py` | 12 个 fixture 单测(解析/分页/空字段/WAF/预算/缓存续采/注册表) |
| `tests/fixtures/platform/*` | 录制响应夹具(北森 list/detail/entry、Moka list/detail/entry) |
| `pipeline-watch/platform-adapters-verify.py` | 10 家首轮验证运行器(§3) |
| `pipeline-watch/platform-adapters-backfill.py` | 未采完公司的多轮有界续采运行器(§3.1) |
| `pipeline-watch/platform-adapters-compare.py` | 通用 ⊇ 专用 对比运行器(§4) |

现有专用适配器**一律未改、未删**,仅并存。

---

## 2. 契约对齐(与现有 `p1_sources_*` 同级)

### 2.1 模块对外契约
- `COMPANIES = {<key>: <公司中文名>}`:从 `p1_platform_companies.json` 读取(北森 key=tenant slug;Moka key=`org/siteId`)。
- `collect(company, scope, output_dir) -> {'jobs': [...], 'coverage': {...}}`;`company` 传**中文公司名**(与 pipeline 一致),内部再解析成 key。
- 子进程调用与现有完全一致(实际验证就是走这条):
  ```
  python -m qiuzhao.collector.p1_pipeline --adapter qiuzhao.collector.p1_platform_beisen \
      --company 中信建投 --scope campus --output-dir <目录>
  ```
  pipeline 的 `--adapter` 分支负责写 `result.json`;适配器自身写 `official-entry.html/list-*.json/detail-*.json`(北森)与 `<site>-list-*.json/detail-*.json`(Moka)证据。

### 2.2 校验
10 家结果全部通过 `p1_pipeline.validate_result(...)`(逐家 `VALID`)。`complete=true` 需要:分页穷尽 + 每个入选岗位都有官方岗位正文 + 无错误 + `expected_total` 等于唯一返回数 + `scope_request/evidence_files/scope_evidence` 齐备。

### 2.3 数据质量规则(按要求)
- `published_at`:北森用官方 `PostDate`,Moka 用官方 `publishedAt/openedAt`;**取不到留空,绝不用当天日期填**。实测可用率 100%。
- `deadline_raw`:北森 `EndTime`,Moka `closedAt`;没有留空。北森平台哨兵值 `0001-*` 与 `2222-02-02` 一律视为“无截止日”留空(民泰 16 条全部为空)。
- `cohort_raw`:两个平台都**不做届别推断**,一律留空(`cohort_rate=0.0`),届别只保留在平台原文/项目名中。
- `source_updated_at`:北森 `ChangeDate`,Moka `updatedAt`,取不到留空。

### 2.4 `p1_pipeline.py` 的最小改动(仅此一处)
```python
REGISTRY = {name: f'qiuzhao.collector.p1_sources_{(i // 10) * 10 + 1:02d}_{(i // 10 + 1) * 10:02d}'
            for i, name in enumerate(COMPANIES)}

# Platform-level adapters (Beisen zhiye.com / Moka) register every company
# declared in p1_platform_companies.json without another REGISTRY edit.
try:
    from .p1_platform_beisen import merged_registry as _platform_registry
    REGISTRY.update(_platform_registry())
except Exception:  # optional platform config may be absent in a minimal checkout
    pass
```
`COMPANIES`(硬编码 50 家列表)与其余行**一字未动**。

---

## 3. 首批 10 家真实 `campus` 实测(只读,不写库;最终状态全部 complete)

运行器:`pipeline-watch/platform-adapters-verify.py`(首轮)+ `pipeline-watch/platform-adapters-backfill.py`(续采);环境变量 `QIUZHAO_PLATFORM_REQUEST_BUDGET=20`(单次运行每租户 ≤20 网络请求);租户之间 `sleep 2.2s`;产物在 `_worktrees/platform-adapters-out/verify/<platform>/<slug>/`。表中“请求”为**最后一轮**实际网络请求数。

| # | 平台 | 公司 | key | status | complete | 条数/期望 | 列表页 | 末轮请求/上限 | published_at | deadline | cohort |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 北森 | 中信建投 | `csc108` | success | **true** | 29/29 | 3 | 9/20 | 100% | 100% | 0% |
| 2 | 北森 | 中金公司 | `cicc` | success | **true** | 104/104 | 11 | 17/20 | 100% | 100% | 0% |
| 3 | 北森 | 国信证券 | `guosen` | success | **true** | 59/59 | 4 | 10/20 | 100% | 22% | 0% |
| 4 | 北森 | 浙江民泰商业银行 | `mintai` | success | **true** | 16/16 | 4 | 10/20 | 100% | 0% | 0% |
| 5 | Moka | 三七互娱(库内) | `37/58016` | success | **true** | 24/24 | 2 | 10/20 | 100% | 0% | 0% |
| 6 | Moka | 金山办公(库内) | `wps/41436` | success | **true** | 25/25 | 9 | 18/20 | 100% | 0% | 0% |
| 7 | Moka | 鹰角网络(库内) | `hypergryph/26326` | success | **true** | 61/61 | 4 | 6/20 | 100% | 0% | 0% |
| 8 | Moka | 安踏集团(新增) | `antahr/142914` | success | **true** | 160/160 | 5 | 12/20 | 100% | 0.6% | 0% |
| 9 | Moka | 小天才(新增) | `eebbk/37594` | success | **true** | 12/12 | 2 | 15/20 | 100% | 0% | 0% |
| 10 | Moka | 信也科技(新增) | `paipaidai/168312` | success | **true** | 11/11 | 2 | 14/20 | 100% | 0% | 0% |

说明:
- 北森走官方**列表字段主采集 + 详情抽样核验**(列表已含官方 `Duty/Require/LocNames/PostDate/EndTime`;`DETAIL_VERIFY_LIMIT=5`,列表缺正文的行强制取详情)。因此 104 条的中金也只用了 17 个请求。
- Moka 岗位正文只在详情接口,首轮 20 请求预算下大租户必然 `partial`;续采方案见 §3.1。
- Moka 新增 3 家来源(公开 Moka 校招页,2026-09-18 web 检索确认,现场实测通过):
  - 安踏集团 `https://app.mokahr.com/campus-recruitment/antahr/142914`
  - 小天才 `https://app.mokahr.com/campus-recruitment/eebbk/37594`
  - 信也科技 `https://app.mokahr.com/campus-recruitment/paipaidai/168312`

### 3.1 未采完公司的续采(换了什么方法)

首轮把 `QIUZHAO_PLATFORM_REQUEST_BUDGET=20` 当作**硬礼貌上限**,4 家 Moka 因此只拿到部分详情。续采没有提高单轮上限,而是改了两点:

1. **额度只算真实网络请求**:`_detail()` 先复用本轮 output_dir 里已存的 `detail-<id>.json`(命中不花额度),再落到 `shared.moka_detail_cached`;共享缓存命中还会把额度退回。于是“再来一轮”是**接着上次的进度走**,而不是把额度浪费在已抓过的岗位上。
2. **多轮有界续采**:`platform-adapters-backfill.py` 对同一 output_dir 反复跑同一个适配器,每轮仍 ≤20 网络请求、轮间 sleep 2.2s,直到 `complete` 或连续两轮无进展。

| 公司 | 首轮 | 续采轮数 | 最终 | 续采总请求 | 单轮最大请求 |
|---|---|---|---|---|---|
| 三七互娱 | 17/24 | 1 | **24/24 complete** | 10 | 10 |
| 金山办公 | 9/24 | 2 | **25/25 complete** | 38 | 20 |
| 鹰角网络 | 15/61 | 4 | **61/61 complete** | 66 | 20 |
| 安踏集团 | 14/158 | 11 | **160/160 complete** | 212 | 20 |

合计 18 轮、326 个请求,单轮最大 20(见 `_worktrees/platform-adapters-out/backfill-summary.json`)。`expected_total` 在两次运行之间由上游真实变化(金山 24→25、安踏 158→160),不是解析漂移。

---

## 4. 通用适配器 ⊇ 原专用适配器(Moka,3 家库内公司)

方法(`platform-adapters-compare.py`):通用适配器实跑;专用适配器 `p1_sources_21_30.collect(...)` 作为对照,只把详情 seam 换成**无网络 stub**,于是对照只做官方列表扫描(≤15 请求/租户),其 campus 岗位 id/标题集合就是专用适配器的 campus 结果。比较对象正是任务要求的“岗位 id/标题集合”。

| 公司 | 专用适配器 campus 条数 | 对照请求数 | 通用结果条数 | 通用列表观测 id 数 | id 集合相等 | 标题集合相等 | 通用岗位 ⊆ 专用 |
|---|---|---|---|---|---|---|---|
| 三七互娱 | 24 | 3 | 24 | 24 | ✅ | ✅ | ✅ |
| 金山办公 | 25 | 11 | 25 | 25 | ✅ | ✅ | ✅ |
| 鹰角网络 | 61 | 15 | 61 | 61 | ✅ | ✅ | ✅ |

结论:三家最终通用结果的 campus 岗位 id/标题集合与专用适配器**完全相等**(因此 ⊇ 成立),且两边条数一致。原始集合见 `_worktrees/platform-adapters-out/compare-summary.json`。

---

## 5. 新增一家公司的 SOP(加一行 + 验证)

### 5.1 北森(tenant slug)
1. 在 `p1_platform_companies.json` 的 `"beisen"` 加一行:`"<tenant>": "<公司名>"`。
   - 若该租户有非招聘分类(人才库/内部招聘等),用对象式显式忽略:`"<tenant>": {"name": "<公司名>", "ignore_categories": ["4"]}`;未声明的未知分类会**阻止 complete**并写进 `unmapped_categories`(不会静默当 0 条成功)。
2. 验证:
   ```
   QIUZHAO_PLATFORM_REQUEST_BUDGET=20 python -m qiuzhao.collector.p1_pipeline \
     --adapter qiuzhao.collector.p1_platform_beisen --company <公司名> --scope campus --output-dir <目录>
   ```
   看 `result.json` 的 `coverage.status/complete/collected_jobs/expected_total/request_budget/errors`。

### 5.2 Moka(org/siteId)
1. 从企业官网“校园招聘”链接拿到 `https://app.mokahr.com/campus-recruitment/<org>/<siteId>`(或 `campus_apply`/`join.*`),在 `"moka"` 加一行:`"<org>/<siteId>": "<公司名>"`(自动推导 campus URL)。
   - 多门户(校招+社招)用对象式:`"<org>/<siteId>": {"name": "<公司名>", "sites": ["<campus url>", "<social url>"]}`。
2. 验证命令同上,`--adapter qiuzhao.collector.p1_platform_moka`;若 `partial` 且 `request_budget_exhausted=true`,直接用 §3.1 的续采运行器把同一 output_dir 跑完(无需改代码)。
3. 探测候选:`curl -s -o /dev/null -w '%{http_code}' https://app.mokahr.com/campus-recruitment/<org>`;页面含 `aesIv` 且标题匹配即可(缺 `aesIv` 视为 WAF 挑战,适配器记 blocked)。

### 5.3 注册表
不需要改代码:两个模块的 `COMPANIES` 从配置读取,`p1_pipeline.REGISTRY` 启动时调用 `merged_registry()` 一并并入。单测 `test_config_line_registers_company` 用临时配置证明“加一行 → 出现在 REGISTRY”。

---

## 6. 部署说明(精灵上要覆盖哪些文件;本次未部署)

覆盖以下文件到采集机代码树(与现有部署方式一致,只覆盖、不删除):
- `qiuzhao/collector/p1_platform_beisen.py`(新增)
- `qiuzhao/collector/p1_platform_moka.py`(新增)
- `qiuzhao/collector/p1_platform_companies.json`(新增)
- `qiuzhao/collector/p1_pipeline.py`(REGISTRY 5 行;与另一执行者的调度改动只在这一处相邻,易合并)
- 可选(仅测试/运维):`tests/test_p1_platform_*.py`、`tests/fixtures/platform/`、`pipeline-watch/platform-adapters-*.py`

注意(重要):
- 平台公司**不在**硬编码的 `COMPANIES` 默认 50 家列表里,而 `run()` 用 `COMPANIES.index(company)` 取序号,所以**不要**把它们塞进 `--companies` 的整批 `--apply` 跑法(会越界)。平台适配器按任务约定走**每公司一次的 `--adapter` 子进程**调用(§2.1);如需并入每日整批,需要另一处调度改动,不在本次最小改动范围内。
- 不加 `QIUZHAO_PLATFORM_REQUEST_BUDGET` 时为**不限请求**的生产全量模式(北森仍只抽样 5 条详情、其余走官方列表;Moka 取全量详情)。验证/试跑请显式设为 20;设了 20 又没采完时,用续采运行器多跑几轮即可。
- 礼貌与限速:适配器内 429/403/连接错误**退避一次**后放弃并记 blocked;租户之间由运行器保证 ≥2s;续采轮间同样 ≥2s。

---

## 7. 遗留与风险

1. **北森 tenant slug 发现**:目前靠人工/半自动。建议从牛客校招日程或国聘公司页拿公司名后,用 `<slug>.zhiye.com` 试探(HTTP 200 + 页面体积达标 + `<title>` 匹配 + `PortalId` 唯一);批量试探要限速,防 WAF。
2. **北森 WAF 频率风控**:报告记录过整批租户短时失效。现在是“每租户 ≤20 请求/轮 + 2s 间隔 + 退避一次”,大规模生产需继续观察;`request_budget` 已写进 coverage 便于审计。
3. **分类语义词表**:北森的 `CategoryId` 语义按租户不同(如中金 `2=校园招聘/暑期实习`、国信 `3=实习生招聘`、csc108/民泰 `4=人才库/内部招聘`)。通用默认 `1=社招/2=校招/3=实习`,异常租户用 `ignore_categories`/`categories` 配置;未声明分类会阻止 complete。
4. **Moka `aesIv`/WAF**:一次性 cookie 挑战;页面无 `aesIv` 时记 blocked 而不是硬闯。多门户站点要显式配置 `sites`。
5. **续采的列表开销**:每轮都要重扫一次官方列表(安踏每轮 5 个请求)以保证分页穷尽与总量一致;若将来要省这点量,可在同一 output_dir 复用列表快照,但要接受“总量不变、个别换岗”的漏检风险。
6. **`published_at` 口径**:Moka 部分租户详情 `publishedAt` 等于 `updatedAt`;北森用 `PostDate`。均为平台官方字段,不自行推算。
7. **未合并的主仓调度改动**:`p1_pipeline.py` 的调度段由另一执行者维护;本次只碰 REGISTRY 相邻 5 行,合并冲突面最小。

---

## 8. 测试

- 新增单测 12 个(北森 6 + Moka 6),覆盖:分页穷尽、字段映射、空字段不推断(2222 哨兵/无 closedAt → 留空)、未知分类阻止 complete、WAF 分支(PortalId 缺失 / aesIv 缺失 → blocked)、请求预算、**缓存命中不占额度 + 二轮续采补齐**、配置驱动注册表。
- 全量 `pytest tests/`:
  - 改动前基线(本 worktree 实测,环境缺 `qiuzhao/data/jobs.json`,55 skipped):**3 failed, 337 passed, 55 skipped**
  - 改动后:**3 failed, 349 passed, 55 skipped**(+12 passed,失败集合完全一致)
  - 3 个失败均为既有环境性失败:`test_core.py::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline.py::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema.py::test_enum_check_fails_when_data_drifts`(任务书写的 39 failed 与本地环境不符,以本地实测为准)。
- 首次改动曾让 `test_real_module_cli_dispatches_adapter` 失败(测试沙箱不拷贝平台模块),已用 `try/except` 让可选平台配置缺失时不影响 pipeline;复测通过。
- 环境性 flaky:`tests/test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` 在本机隔离复跑 10 次为 5 过 5 败(4 进程并起迁移同一 sqlite,偶发 `database is locked`),与本次改动无关(`core/store.py` 未改);全量套件复跑最终为 3 failed。
