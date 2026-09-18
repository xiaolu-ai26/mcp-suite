# RECEIPT — collector-next：四线整合 + 平台公司进日常链 + 精灵部署件（20260918b）

结论：四条分支已合并到 `feat/collector-next`（未 push、未合 main）。平台公司已进入日常链默认集合，
序号越界已修，checkpoint 对"新增公司"不再报 resume mismatch；请求预算生产默认不限；精灵链
`windows_collector.py` 以精灵现役移植版为底、只改 p1 一步参数；全量测试失败清单与基线一致；
4 家 campus 离线并发验证全过；部署件 `pipeline-watch/deploy-artifacts/20260918b/` 已就绪。

工作区：`/Volumes/臭垃圾桶/生财MCP/_worktrees/collector-next`（分支 `feat/collector-next`）。
全程未部署、未 SSH、未碰阿里云/飞书、未读取或打印任何令牌、未 push。外接盘 `._*` 为 macOS
AppleDouble 垃圾文件，未纳入任何提交。

## 0. 分支与提交

| 项 | 值 |
|---|---|
| 基线 | `fix/collector-partial-keep` = `4155851` |
| `feat/p1-speed` | `9d555fd`（是 4155851 的子节点，快进合并） |
| `feat/platform-adapters` | `e7434b3`（是 4155851 的子节点，clean merge = `c89916c`） |
| `feat/guopin-auto-campaigns` | `f71a7fc`（基于 main 59dca7b，合并产生冲突，merge = `ba3f3e6`） |
| 整合改动 | `05d05a3`（默认公司集合 / 序号 / checkpoint / 预算默认 / 精灵参数 / 单测） |
| 部署件+收据 | 本次收尾提交 |

`git log --graph`（顶部）：

```
* 05d05a3 feat(collector): platform companies in daily chain + budget default + jingling p1 args
*   ba3f3e6 Merge branch 'feat/guopin-auto-campaigns' into feat/collector-next
|\
| * f71a7fc feat(guopin): discover 2027 campus campaigns from the official banner directory
* |   c89916c Merge branch 'feat/platform-adapters' into feat/collector-next
|\ \
| * | e7434b3 feat(qiuzhao): add config-driven platform adapters for Beisen and Moka
* | | 9d555fd perf(p1): concurrent company chains, scope-timeout, next-day retry priority
|/ /
* | 4155851 docs(receipt): record collector fix deployment to jingling (20260918)
```

## 1. 合并与冲突解决

- 依次：`git merge feat/p1-speed`（Fast-forward 4155851→9d555fd）→ `git merge feat/platform-adapters`
  （clean，`c89916c`）→ `git merge feat/guopin-auto-campaigns`（`guopin.py` 冲突，`ba3f3e6`）。
- **冲突仅一处**：`qiuzhao/collector/guopin.py` 末尾 `collect_guopin()` 的顶层 state 组装
  （HEAD 第 232–248 行 vs guopin 分支）。两边 status 表达式逐字相同，差别只是 HEAD 把它提成了
  `overall` 变量并带解释注释，guopin 分支多了自动发现字段。
- **解决**：保留 HEAD 的 `overall` 变量与注释（现役 fix 语义：`success` / 有专场 success 即
  `partial` / 否则 `partial_failure`），并入该分支的 `discovered` / `skipped` / `fallback_used`
  与新的 `coverage` 文案。即：**状态语义 + 自动发现逻辑同时保留**。
- **一致性核对**：把结果与 `f71a7fc:qiuzhao/collector/guopin.py` 去空白后 diff，唯一差异是把
  `collector.states['guopin']={'status':'success' if complete else (...)}` 改写成
  `overall=...; 'status':overall`；状态表达式逐字符一致。其余自动发现逻辑（`campaign_alias`
  / `discover_campaigns` / `merge_campaigns` / banner 失败回退）全部来自 f71a7fc。
- **跨分支测试对账**：guopin 分支按业务事件把 `cgnpc` 从 `CAMPAIGNS` 移除（现为 5 个专场）。
  fix 分支的 `tests/test_collector_partial_keep.py` 仍按 6 个专场断言，属合并引入的新失败。
  已同步该测试：`GUOPIN_DOMAINS` 改为 5 个；“专场被下线 → partial”用例改以 `zglt` 下线来验证同一语义
  （结果 4 条、`status=partial`、`alerts=['guopin:zglt']`）。语义未放松，只是换了被测专场。

### 不做/未做

- 未 push，未合并到 main；未在主工作区操作。
- 未改 `run.py`（本次不变，因此不放进部署件）。

## 2. 平台公司进日常链（关键修复）

原状：精灵日常链 `python -m qiuzhao.collector.p1_pipeline --data-dir ... --apply --resume-latest
--timeout 1200 --max-run-seconds 18000` 不传 `--companies`，`main()` 回落到硬编码 `COMPANIES`（50 家）
→ 平台公司永远不跑；且 `run_unit()` 用 `COMPANIES.index(company)+1` 对平台公司直接 `ValueError`。

改法（`qiuzhao/collector/p1_pipeline.py`，最小改动）：

1. **默认公司集合**：新增
   ```python
   PLATFORM_COMPANIES = [name for name in REGISTRY if name not in COMPANIES]
   DEFAULT_COMPANIES = [*COMPANIES, *PLATFORM_COMPANIES]
   ```
   `main()` 中 `companies = args.companies.split(',') if args.companies else DEFAULT_COMPANIES`。
   顺序稳定：先硬编码 50 家（保原优先级），后平台按配置顺序（beisen→moka），去重。
   平台 import 失败时 `REGISTRY` 无平台键，`DEFAULT_COMPANIES` 自动退回 50 家。实测 **57 家**，
   平台 7 家：中信建投、中金公司、国信证券、浙江民泰商业银行、安踏集团、小天才、信也科技
   （三七互娱/金山办公/鹰角网络与硬编码重叠，保留在硬编码原位置、不重复）。
2. **目录序号**：`run_unit()` 改为 `ordinal = companies.index(company) + 1`（按本次 companies 列表位置）。
   硬编码公司在列表最前，所以**硬编码公司的序号与旧代码完全一致**（大疆仍 `02`），对现役
   `--resume-latest`/checkpoint 的 `result_path` 兼容；平台公司得到 51–57 号目录，不再越界。
3. **checkpoint companies 校验**：新增 `resume_compatible(checkpoint, companies, scopes)`：
   scopes 一致且 checkpoint 公司集合是本次集合的**子集**才可续跑。`run()` 里：
   - 子集（纯新增平台公司）→ 复用已校验结果，只跑新增公司；
   - 非子集（公司被删/不同选择）→ 视为**新 run**（重置 status），不再抛
     `resume company/scope selection differs from checkpoint`。
   日常链走 `select_checkpoint()`，其 `companies` 精确匹配失败时本来就会开新的 run_dir（视为新 run），
   本改动覆盖显式 `--resume --run-dir` 的路径，保证任何情况下不会因集合变化把整天卡死。

### 新增单测：`tests/test_collector_next_integration.py`（9 条，全过）

- `test_default_companies_append_platform_in_config_order_without_duplicates`：57 家、先硬编码后平台、
  7 家平台在 `REGISTRY`、重叠 3 家只出现一次、硬编码顺序不变。
- `test_platform_companies_are_appended_after_hardcoded_in_config_order`：beisen 在 moka 前。
- `test_platform_company_runs_without_index_error_and_gets_unique_dir`：`['大疆','小天才']` → `01/02`，
  平台公司不再 `COMPANIES.index` 崩。
- `test_cli_default_company_set_reaches_run`：不带 `--companies` 时 `main()` 把 57 家传给 `run()`。
- `test_resume_accepts_newly_added_platform_company`：先只跑大疆，再在同一 run_dir 追加小天才 →
  大疆跳过、小天才跑、`status['companies']` 更新、全 success。
- `test_resume_with_removed_company_restarts_instead_of_raising`：集合被删 → 重置为新 run，不抛错。
- `test_resume_compatible_only_for_scopes_and_company_subsets`：子集/scope 判定。
- `test_platform_request_budget_defaults_to_unlimited`：见第 3 节。
- `test_deployable_windows_collector_uses_scope_timeout_and_workers`：见第 4 节。

既有测试同步：`tests/test_p1_pipeline.py::test_subset_run_does_not_replace_another_selection_checkpoint`
的目录断言由 `first/'02'/campus` 改为 `first/'01'/campus`（序号改按本次列表位置）。

## 3. 请求预算默认值

`p1_platform_beisen.py` / `p1_platform_moka.py` 各新增并引用：

```python
DEFAULT_REQUEST_BUDGET = None   # 生产默认不限
def _budget_limit(max_requests):
    if max_requests is not None: return int(max_requests)
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET
```

**默认 = 不限**。理由：预算是**礼貌/验证用的可选上限**，不是生产截断器。安踏集团公开招聘 158 条，
仅列表+详情就远超 20 次；20 会把健康租户误判成 `request_budget_exhausted` 的 partial。验证阶段
的 20 只是任务限制，通过 `QIUZHAO_PLATFORM_REQUEST_BUDGET` 或 `max_requests` 显式传入
（`pipeline-watch/platform-adapters-verify.py` 即如此），不进生产默认。单次 scope 的墙钟仍由
`--scope-timeout` / `--max-run-seconds` 兜底。离线验证中实测平台 `coverage.request_budget.limit = null`
（中信建投 used=9、小天才 used=15），证明生产路径未继承 20。

## 4. 精灵链参数（deploy/windows_collector.py）

- **底本**：`pipeline-watch/deploy-artifacts/20260918/windows_collector.py`（**精灵现役移植版**，
  sha256 `14e17785ccff51f9…`）。整文件先逐字节复制，**末尾 `base-sync` 同步段
  （`lark_sync_daemon … --apply`、`finished/success` 要求 `sync_exit==0`）一字未动**，也无
  `lark_sync_index`（精灵上没有该模块）。
- **唯一改动**：p1 一步参数
  `--timeout 1200` → `--scope-timeout 600 --workers 4 --max-run-seconds 18000`
  （去掉 `--timeout 1200`，因为 `--scope-timeout` 优先级更高、二者同时传 `--timeout` 会被忽略，直接去掉更清晰）。
- 新文件 sha256 `611254083a22eae1ad627f03ffccc720fb3b5532d989d436cd8698a6a28c4c3a`；
  `PORT-DIFF.txt` 显示现役 → 新版**只有 1 行**差异。

## 5. 单测

| 套件 | 结果 |
|---|---|
| 整合分支 `pytest tests/` | **3 failed, 374 passed, 55 skipped** |
| 基线 worktree `p1-speed`（=fix+1）`pytest tests/` | **3 failed, 347 passed, 55 skipped** |
| 新增 `tests/test_collector_next_integration.py` | **9 passed** |
| `tests/test_collector_partial_keep.py` + `tests/test_guopin_auto_campaigns.py` | **25 passed** |

失败清单**逐条一致**（均为既有失败，非本次引入）：

1. `tests/test_core.py::test_role_cohort_and_campaign_title_bases`
2. `tests/test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`
3. `tests/test_schema.py::test_enum_check_fails_when_data_drifts`

任务书提到 `test_codes_kind` 既有 flaky：本次两次全量均 **passed**。整合分支新增 27 条用例
（19 条平台/并发测试 + 9 条新整合测试 - 1 条被改写），全部通过。

## 6. 离线验证（Mac，只读，不 `--apply`，不写库）

输出根目录：`/Volumes/臭垃圾桶/生财MCP/_worktrees/collector-next-out/`。

### 6.1 默认集合证明（零网络）

```
python -m qiuzhao.collector.p1_pipeline \
  --data-dir .../collector-next-out/default-probe \
  --run-dir  .../collector-next-out/default-probe/run \
  --scopes campus --max-run-seconds 0
```
不加 `--companies`，`max-run-seconds=0` 不发起任何请求。`default-probe/run/status.json`：
`companies` 共 **57** 家，前 3 为 `拼多多,大疆,华为`（硬编码顺序），并含全部 7 家平台公司
`['中信建投','中金公司','国信证券','浙江民泰商业银行','安踏集团','小天才','信也科技']`。
即**默认集合确实包含平台公司**。

### 6.2 4 家 campus 并发实跑

```
python -m qiuzhao.collector.p1_pipeline \
  --data-dir .../collector-next-out/offline/data \
  --run-dir  .../collector-next-out/offline/run \
  --companies "商汤科技,中信建投,大华股份,小天才" \
  --scopes campus --workers 2 --scope-timeout 900 --max-run-seconds 3600
```
`PIPELINE_EXIT:0`（全部 success+complete），耗时约 47s（07:57:17Z→07:58:04Z，UTC）。

| 序号目录 | 公司 | 类型 | status | complete | jobs | request_budget | validate_result 复验 |
|---|---|---|---|---|---|---|---|
| `run/01/campus` | 商汤科技 | 硬编码 | success | True | 80 | — | OK |
| `run/02/campus` | 中信建投 | 平台 beisen | success | True | 29 | `{'limit': None, 'used': 9}` | OK |
| `run/03/campus` | 大华股份 | 硬编码 | success | True | 146 | — | OK |
| `run/04/campus` | 小天才 | 平台 moka | success | True | 12 | `{'limit': None, 'used': 15}` | OK |

- **目录/序号无越界**：4 家按本次列表位置得到 `01–04`；平台公司在 `02`/`04`，未触发
  `COMPANIES.index` 越界。`status.json` 的 `result_path` 与序号一一对应（脚本断言 `ORDINAL_MAPPING_OK`）。
- **结果都通过 `validate_result`**：把每个 `validated.json` 用整合后的
  `p.validate_result(payload, company, scope, output_dir)` 再验一遍，4/4 `VALIDATE_OK`
  （`ALL_REVALIDATE_OK True`）。
- **2 秒间隔**：`--workers 2`，且公司顺序把两家平台公司排在不同批次——beisen 首个请求
  `run/02/campus/official-entry.html` 生成为 15:57:18，moka 首个请求 `run/04/campus/37594-list-0.json`
  生成为 15:57:54，**相隔 36s**（>2s）；本轮只触达中信建投与小天才两家平台租户，其余 5 家平台公司
  未被请求。
- 全程**未加 `--apply`**，未写 `jobs.json`，`--data-dir` 为外接盘 scratch，不碰任何生产库/服务。

## 7. 部署件 `pipeline-watch/deploy-artifacts/20260918b/`

覆盖到精灵的 6 个文件 + 3 个说明文件：

| 文件 | sha256 | 说明 |
|---|---|---|
| `guopin.py` | `add0d50c715e06eb968bb7671bc2e9787e81d9ad39be008e66731337f16b6c03` | 合并+冲突解决版 |
| `p1_pipeline.py` | `78cf1f030dabbeb019cb620bfa1d1d89335c3d592b586fff14c9a82be35fbb2e` | 平台公司进日常链版 |
| `p1_platform_beisen.py` | `3faeb5686aa7bf05a7b6754b35a607c50a9666e8247dd5b46d430307b9eb33a5` | 新文件（精灵不存在） |
| `p1_platform_moka.py` | `569e0865d96ba7f91a4803330975ac76f9f35277b9f1bf312092c598c636a777` | 新文件 |
| `p1_platform_companies.json` | `7347c77987c4f0e7b791739e120824d124151c9526c7de4207d9e51dab2cdbc7` | 新文件 |
| `windows_collector.py` | `611254083a22eae1ad627f03ffccc720fb3b5532d989d436cd8698a6a28c4c3a` | 精灵现役为底 + p1 参数 |
| `SHA256SUMS.txt` | — | 上面 6 个文件的完整 sha256 |
| `PROD-BACKUP-MANIFEST.txt` | — | 精灵现役原版哈希 + 回滚副本指引 |
| `PORT-DIFF.txt` | — | windows_collector 现役→新版 diff（仅 1 行） |

**精灵现役原版哈希（覆盖前，来自 `../20260918/` 的逐字节副本）**：
`run.py 5e94f91b770ef02bfad887e10bb6fab3405d8b184a81b98df9d14fe28c266b28`、
`p1_pipeline.py dc046e32f37d7482ac56222898d122edb52d93d8b48fed4f3c5c2c67770fdb90`、
`guopin.py 22e5f6ad0b66487ba7f6ccaee041da67c668d7ed98aeaa10408d7dc95a0abf89`、
`windows_collector.py 14e17785ccff51f94aea519bee1637582d974c6d65540ee6f379954b08c90c4a`；
`p1_platform_beisen.py` / `p1_platform_moka.py` / `p1_platform_companies.json` 三个新文件精灵上**不存在**。
`run.py` 本次不变，**不在**部署件内。

## 8. 部署步骤（同 partial-keep 收据 E3；不执行）

1. **备份**：精灵上 `robocopy C:\mcp-suite-collector C:\mcp-suite-backup-<日期> /E /XD .venv runs data`
   （或至少定向备份 `deploy\`、`qiuzhao\collector\`、`keys\`）。核对现役 4 个哈希与
   `PROD-BACKUP-MANIFEST.txt` 一致；不一致说明正式文件又被改过，**停下来找总控**。
2. **传输**：把 `deploy-artifacts/20260918b/` 的 6 个待部署文件分片 base64（每片 ≤1400 字节 +
   `powershell -NoProfile -EncodedCommand`）传到精灵临时目录；精灵侧 `Get-FileHash` 与
   `SHA256SUMS.txt` **逐字节核对通过后再覆盖**。scp 不可用，方法同 partial-keep E2。
3. **覆盖 6 个路径**：
   - 已存在、被覆盖：`qiuzhao\collector\guopin.py`、`qiuzhao\collector\p1_pipeline.py`、
     `deploy\windows_collector.py`；
   - **新增**：`qiuzhao\collector\p1_platform_beisen.py`、`qiuzhao\collector\p1_platform_moka.py`、
     `qiuzhao\collector\p1_platform_companies.json`。
   覆盖后对 6 个目标路径各重算一次 sha256，与 `SHA256SUMS.txt` 比对留证。不需重启服务，
   计划任务次日 06:10 自然生效。
4. **编译/导入**（精灵正式 venv，cwd=`C:\mcp-suite-collector`）：
   `python -m py_compile qiuzhao\collector\guopin.py qiuzhao\collector\p1_pipeline.py qiuzhao\collector\p1_platform_beisen.py qiuzhao\collector\p1_platform_moka.py deploy\windows_collector.py`
   → 期望 exit=0；`python -c "import deploy.windows_collector"` → `IMPORT_OK`；
   `python -c "from qiuzhao.collector import p1_pipeline as p; print(len(p.DEFAULT_COMPANIES))"` → `57`。
5. **次日 06:10 观察项**：`runs\<日期>\receipt.json` 的 `steps` 出现 0/2、`step_changes` 有逐阶段条数、
   `stage` 过 `validate-and-publish` → `base-sync`、`sync_exit==0`、`publication.published=true`；
   `data\p1-status.json` 的 `companies` 含 7 家平台公司、`p1-runs\<ts>\5x\campus` 出现 51–57 号目录；
   平台公司若网络不通应为 `blocked/partial` 且不拖垮其余公司（退出码 2 保留产出）。
6. **新增文件也要校验**：第 3/4 步包含 3 个新文件；回滚时需删除。

## 9. 回滚方法

- `qiuzhao\collector\p1_pipeline.py`、`guopin.py`、`deploy\windows_collector.py` 用
  `deploy-artifacts/20260918/` 下同名逐字节副本拷回（即现役 14e17785 / 22e5f6ad / dc046e32）；
- 三个新文件 `p1_platform_beisen.py` / `p1_platform_moka.py` / `p1_platform_companies.json` **删除**
  （回到 p1_pipeline 无平台 import 的状态，`DEFAULT_COMPANIES` 自动退回 50 家）；
- `run.py` 未动，无需回滚。
- 数据层：本次只改采集/编排，未改数据格式；如需数据回滚用服务器侧 `jobs.json.bak.windows.*` 与
  `runs\<日期>\jobs.before.json`。回滚后行为完全回到"平台公司不进日常链 + `COMPANIES.index` 旧序号"。

## 10. 遗留与不确定点

1. **平台公司覆盖不完整**：离线端到端只实跑了 2 家（中信建投 beisen / 小天才 moka）。其余 5 家
   （中金公司、国信证券、浙江民泰商业银行、安踏集团、信也科技）在 `feat/platform-adapters` 分支
   用预算 20 验过适配器，但未在整合后的日常链里实跑；上线后首日应重点看它们的 `p1-status.json`。
2. **日常链耗时/请求量上升**：默认 50→57 家，7 家平台公司的列表+详情请求在 600s/公司预算内。
   若某平台公司长期超时，会进 retry 队列并按"连续 3 天降级到最后"策略处理，不影响其余公司。
3. **显式 resume 的 scope 变化**：`run()` 现在把 scope 不一致也当作新 run（不再抛错）。这比原
   `raise` 更不容易卡死，但若有人误用不同 scope resume，旧的 checkpoint 会被原地重置（结果文件仍在）。
4. **cgnpc 语义**：合并后 `cgnpc` 不再是硬编码专场，靠 banner 自动发现回归；其历史岗位记录不会误标
   removed。与 guopin 分支一致。
5. 外接盘 `._*` AppleDouble 文件大量存在（1847 个），全部未入库；提交均按显式路径添加。
6. 本次未执行任何部署/SSH/阿里云/飞书操作；`windows_collector.py` 的精灵侧参数与现役完全一致，
   仅 p1 一步参数不同，是低风险变更。
