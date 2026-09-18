# 收据：字节跳动接入每日采集链 + 全库停更体检

**分支** `feat/bytedance-daily`（worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/bytedance-daily`，基线 `feat/collector-next-2` @ `bcdfd09`）
**执行时间** 2026-09-18 19:50–21:10（CST） **部署件** `pipeline-watch/deploy-artifacts/20260918i/`
**本会话未部署、未写精灵、未碰阿里云、未调飞书、未登录任何站点、未 push。**

---

## 0. 结论摘要

1. **字节跳动已接入 p1 日常链**，company=`字节跳动`，scope=campus/intern/social。顺带纠正了一个**存量错误**：`portal_type` 早已不决定门户，服务端对 1..12 一律返回社招结果集；真正生效的是 `recruitment_id_list`（201 校招正式 / 202 校招实习 / 101 社招）。老 `bytedance.py` 的 `--campus-only` 路径实际上会把社招岗位标成校招。
2. **id 规则按要求保持不变**：新增 `coverage['stable_id_prefix']` 白名单机制，字节继续写 `bytedance-<职位id>`、美的继续写 `midea-<positionId>`；未声明前缀的适配器行为与 h 版逐字节一致（有单测锁定）。实测字节 campus 快照 2663 条对库里 2244 条校园记录：**2222 条原地更新、441 条新增、0 条重复**。
3. **顺带接入第二个真实缺口：美的集团**（`midea.py` 有采集器但从未进任何日常链）。campus 214 条 / intern 321 条都跑成 `success+complete`；social 官方校招接口看不到，按设计 `blocked`（空集 ≠ 没有岗位）。
4. **全库停更体检**：生产库 93,519 行 / 1,087 个 `source_name`；**1,065 个来源最近核对早于 2026-09-16**，但其中**绝大多数不是"没接采集器"**，而是三类可解释原因：①09-18 那次 p1 被 5 小时硬上限截断，32 个单元根本没跑；②适配器失败/契约拒绝；③p1 迁移前的老 id 命名空间被冻结。真正"有采集器但没接入日常链"的只有字节与美的两家，本次已接入。
5. 单测：`pytest tests/` 失败清单与本 worktree 改动前**完全一致（4 条，无新增）**；新增 31 条适配器单测全绿。

---

## 1. 字节跳动接入

### 1.1 接口口径（2026-09-18 现场实测）

`POST https://jobs.bytedance.com/api/v1/search/job/posts`（免登录），`portal_type` 与 `recruitment_id_list` 的实际行为：

| 请求 | count | 返回岗位 |
|---|---|---|
| `portal_type` 1..12，`recruitment_id_list=[]` | 10000 | 全部 `正式/社招`（**portal_type 已被忽略**） |
| `recruitment_id_list=['201']` | 2663 | 全部 `正式/校招`（`recruit_type.id=201`） |
| `recruitment_id_list=['202']` | 5578 | 全部 `实习/校招`（`recruit_type.id=202`） |
| `recruitment_id_list=['101']` | 10000（接口上限） | 全部 `正式/社招`（`recruit_type.id=101`） |

`recruit_type.id` 取自官方岗位详情 `/api/v1/job/posts/<id>?portal_type=3` 的原始 payload，不是猜的。
前端打包产物同样印证：campus 门户 `portalTypeNumber=3`、`/campus/position`；experienced 门户 `portalTypeNumber=2`、`/experienced/position`，两者共用同一个 search 端点。

### 1.2 适配器

`qiuzhao/collector/p1_bytedance_public.py`（新增，`collect()` + `merged_registry()`），
列表接口一次就返回完整 `description`/`requirement`，**不需要逐岗请求详情**：

| scope | recruitment_id_list | 门户 / 详情 URL |
|---|---|---|
| campus 校园招聘 | `['201']` | `https://jobs.bytedance.com/campus/position/<id>/detail` |
| intern 实习招聘 | `['202']` | 同上 |
| social 社会招聘 | `['101']` | `https://jobs.bytedance.com/experienced/position/<id>/detail` |

- 注册块追加在**现有全部注册块之后**（`p1_pipeline.py`，Feishu 块之后），`DEFAULT_COMPANIES` **924 → 926 家**（50 硬编码 + 874 平台/其它 + 字节跳动 + 美的集团）。
- `bytedance.py` 的 `fetch_page()` 新增 `recruitment_id_list` / `referer` 形参（默认值保持旧行为）+ 口径注释，HTTP 实现仍只有一份。

### 1.3 完整性边界（避免误删）

接口把 `count` 与分页都封顶在 10000。因此：

| scope | 官方 total | 能否证明完整 | 结果 |
|---|---|---|---|
| campus | 2663 | 能 | `success + complete`，参与缺席下线 |
| intern | 5578 | 能 | `success + complete`，参与缺席下线 |
| social | 10000（撞上限） | **不能** | 强制 `partial`，**永不**触发缺席下线 |

### 1.4 稳定 id 规则（本次唯一共享逻辑改动）

`validate_result()` 原先无条件把 id 写成 `p1-<sha256(company|scope|source_id)>`。现在：

```python
prefix = str(coverage.get('stable_id_prefix') or '')
supplied = str(row.get('id') or '')
if prefix and supplied.startswith(prefix) and len(supplied) > len(prefix):
    row['id'] = supplied            # 适配器自己的历史命名空间
else:
    row['id'] = 'p1-' + hashlib.sha256(...).hexdigest()[:24]   # 原行为
row['p1_identity'] = row['id']
```

仅当适配器**主动声明**前缀且自带 id 确实以该前缀开头时保留；否则与 h 版完全一致（`tests/test_p1_bytedance_public.py::test_other_adapters_without_prefix_still_get_hash_identity` 锁定）。
合并走 `merge_records` 的 `by_id` 主路径，命中既有行 → 原地更新，不会新增重复。

---

## 2. 小规模真实验证（只读，未 `--apply`）

命令与产物：`/Volumes/臭垃圾桶/生财MCP/_worktrees/bytedance-daily-out/`（脚本 `run_campus_verify.py`、证据 `campus/list-*.json`、调用记录 `campus-calls.json`）。

| 项 | 值 |
|---|---|
| scope | campus（`recruitment_id_list=['201']`） |
| 请求数 | **27**（offset 0…2600，limit=100；预算 ≤80） |
| 请求间隔 | 代码下限 1.0s；证据文件实际写入间隔 **最小 2.25s / 平均 2.56s** |
| status / complete | `success` / `True` |
| expected_total vs 实收 | 2663 = 2663，`unique_source_ids=2663`，0 重复、0 空正文 |
| `validate_result` | 通过；2663 条 id 全为 `bytedance-<职位id>` |
| recruit_type 分布 | 201×2663（无跨类型串味） |

**与库内 2244 条校园记录逐 id 对比**（在精灵侧只读比对，只回传聚合）：

| 项 | 条数 |
|---|---|
| 库内 `bytedance-` 合计 | 4171（校园 2244 + 实习 1927） |
| 快照 campus | 2663 |
| **交集（原地更新）** | **2222** |
| 快照有、库内无（新增） | 441 |
| 库内有、快照无 | 22 |

那 22 条**首次合并不会被删**：它们还没有 `p1_company`/`p1_scope`，而缺席下线只作用于 p1 已接管的行。第一次完整快照只接管出现的行；未出现的行保持原状（无破坏性首跑），从第二次完整快照起才进入正常缺席流程。已用单测同时锁定这两种行为。

---

## 3. 全库停更体检（只读，精灵 stdin 脚本）

脚本 `_inventory.py` / `_inventory2.py` / `_p1bad.py`（纯 stdlib、流式解析、只 print，未写精灵、未拉文件）。
库快照：`C:\mcp-suite-collector\data\jobs.json`，**343,047,764 字节，mtime 2026-09-18 18:55:57，93,519 行**，其中 297 行无 id、1,087 个 `source_name`。

> 注：同日 12:50 那次 `windows_collector` 发布的快照是 92,532 行；18:55 的文件是之后另一次发布（本次会话未参与，应为另一执行者的部署动作）。以下体检基于 18:55 这份现役文件。

### 3.1 按 id 前缀（顶层命名空间）

| 前缀 | 行数 | 最近核对 | 说明 |
|---|---|---|---|
| `p1-` | 66,562 | 2026-09-18（最早 09-12） | p1 日常链主命名空间 |
| `guopin-` | 7,962 | 2026-09-18 | 国聘（run.py，当日 partial） |
| **`bytedance-`** | **4,171** | **2026-09-10** | 本次接入 |
| `postal-` | 2,648 | 2026-09-18 | 正常 |
| `iguopin-` | 1,337 | 2026-09-11 | research 一次性导入的孤儿命名空间 |
| `tencent-` | 907 | 2026-09-18 | 正常（tencent 步骤） |
| `gp-` | 865 | 无 reviewed_at | research 一次性导入的孤儿命名空间 |
| `alibaba-` | 477 | 2026-09-10 | 老命名空间（p1 阿里适配器写 `p1-`） |
| `chn-` | 422 | 2026-09-14 | chnenergy 采集器失败 |
| `<none>` | 297 | 无 | 迁移前匿名遗留行 |
| `netease-` | 193 | 2026-09-14 | 老命名空间 |
| `meituan-` | 188 | 2026-09-14 | 老命名空间 |
| **`midea-`** | **146** | **2026-09-10** | 本次接入 |
| `thundersoft-` | 125 | 2026-09-10 | 老命名空间（飞书配置已注册） |
| `jd-` | 106 | 2026-09-14 | 老命名空间 |
| `xiaomi-` | 100 | 2026-09-14 | 老命名空间 |
| 其余 ~3,300 个前缀 | 各 <100 | 多为 09-10 | 一次性导入 / 已废弃命名空间 |

### 3.2 最近核对早于 2026-09-16 的来源（≥100 行）

| 来源 | 行数 | 最近核对 | 涉及公司 | 应由谁负责 | 为什么没在跑 |
|---|---|---|---|---|---|
| 国聘行动官方招聘平台 | 4,869 | 09-11 | 国聘聚合（3587 行无 reviewed_at） | `run.py --source guopin` | **在跑**，当日 `partial`；只用完整专场做缺席下线，非专场行不刷新 |
| 宁德时代官方招聘 | 4,398 | 09-14 | 宁德时代 | p1 Moka | 已接入；09-18 `Moka total changed during scan` → blocked/partial |
| **字节跳动校园招聘官方网站** | **4,171** | **09-10** | **字节跳动** | `bytedance.py` | **有采集器、无任何日常流程调用** → 本次接入 |
| 蔚来汽车官方招聘 | 3,482 | 09-14 | 蔚来汽车 | p1（飞书/Moka） | 已接入；09-18 被 5h 上限截断，3 个单元**从未尝试** |
| 国聘官方企业校招专场：中国联通 | 2,580 | 09-14 | 中国联通 | `run.py --source guopin` | 在跑，当日 partial |
| 快手官方社会招聘网站 | 2,366 | 09-13 | 快手 | p1 | 已接入；`Repeated Kuaishou source ID` → blocked |
| 滴滴官方招聘 | 1,256 | 09-14 | 滴滴 | p1 | 已接入；`Didi duplicate ID across pages` → social blocked |
| 安克创新官方招聘 | 1,118 | 09-14 | 安克创新 | p1 飞书 | 已接入；DNS/接口失败 + `Unrecognized Anker enum` → 全 blocked |
| 国聘网校园招聘 | 944 | 09-11 | 国聘聚合 | 无（research 一次性导入） | 孤儿命名空间，无对应采集器 |
| 国聘（`gp-`） | 913 | 无 | 国聘聚合 | 无（research 一次性导入） | 同上 |
| 得物官方招聘 | 751 | 09-14 | 得物 | p1（`p1_dewu_public.py`） | 已接入；09-18 3 个单元**从未尝试**（pending） |
| 国聘官方企业校招专场：中国能源建设 | 649 | 09-14 | 中国能建 | `run.py --source guopin` | 在跑，当日 partial |
| 比亚迪官方招聘网站 | 525 | 09-13 | 比亚迪 | p1 | 已接入；`Repeated page IDs` + social 超时 → blocked |
| 阿里巴巴校园招聘官方网站 | 477 | 09-10 | 阿里巴巴 | `alibaba_headless.py`（p1） | 已注册，但 09-18 那次运行的 `companies` 只有硬编码 50 家，平台公司整批未跑 |
| 国家能源集团官网校园招聘直招 | 422 | 09-14 | 国家能源集团 | `run.py --source chnenergy` | 在跑但**失败**（09-17、09-18 连续 `chnenergy: failed`） |
| 国聘官方企业校招专场：中国兵器工业 | 406 | 09-10 | 中国兵器工业 | `run.py --source guopin` | 在跑，当日 partial |
| 国聘行动 | 345 | 无 | 国聘聚合 | 无 | 孤儿命名空间 |
| 小米官方招聘 | 168 | 09-12 | 小米 | p1 | 已接入；09-18 3 个单元**从未尝试** |
| 国聘官方企业校招专场：中国兵器装备 | 167 | 09-10 | 中国兵器装备 | `run.py --source guopin` | 在跑，当日 partial |
| **美的集团校园招聘官网** | **146** | **09-10** | **美的集团** | `midea.py` | **有采集器、无任何日常流程调用** → 本次接入 |
| 中科创达校园招聘官方网站 | 125 | 09-10 | 中科创达 | p1 飞书配置（`thundersoft`） | 已注册但未产出 `p1-` 行；09-18 平台公司整批未跑 |

来源总数：`source_name` 维度 **1,065 个 / 最近的核对时间 < 2026-09-16**；其中 ≥100 行的 21 个（上表），20–99 行 9 个，其余 1,035 个均 <20 行（合计 2,488 行，几乎全是一次性导入批次）。
当日仍新鲜（`max reviewed_at = 2026-09-18`）的来源只有 **22 个**：postal/boc/ccb/移动·机械总院·航天科工(国聘专场)/腾讯+17 家 p1 公司。

### 3.3 p1 管辖区（50 家硬编码公司）新鲜度

- **36 家** 最近核对 2026-09-18；**14 家** 停在 09-12 / 09-14：
  科大讯飞(09-12)、京东、吉利汽车、安克创新、小米、得物、恒瑞医药、汇川技术、网易、美团、药明康德、蔚来汽车、迈瑞医疗、长城汽车(均 09-14)。
- 归因（来自 `runs\20260918\data\p1-status.json`，118 单元中 69 个 success+complete、49 个不完整、**32 个从未尝试**）：

| 类别 | 公司 | 直接证据 |
|---|---|---|
| 被 5 小时硬上限截断，单元从未尝试 | 吉利汽车、长城汽车、迈瑞医疗、恒瑞医药、药明康德、小米、京东、美团、网易、得物（各 3 scope）+ 蔚来汽车(intern,social) | `p1-status.pending` 共 32 项，`run_finished=false` |
| 适配器契约/网络失败 | 科大讯飞（`adapter contract rejected: evidence must be a nonempty current scope or company shared file`）、安克创新（DNS + 枚举不识别）、汇川技术（`recruit.inovance.com` 读超时） | `p1-status.results[*].coverage.errors` |
| 源站 ID 重复 / 计数漂移 | 快手、比亚迪、滴滴、宁德时代、完美世界、金山办公 | 同上 |
| 详情页取不到 | 百度、联想、米哈游、用友、海康威视、携程、理想汽车、蚂蚁集团、金蝶 | 同上 |

- 全局背景：09-18 那次 `windows_collector` 的三个采集步骤 `basic=1 / tencent=0 / p1=1 / normalize=0`，`finished=false, success=false`；`basic` 里 `chnenergy=failed`、`telecom=failed`、`guopin=partial`。按 `windows_collector.py` 的回滚规则（退出码 ∉ {0,2} 即回滚该步），p1 与 basic 的写入被还原。

### 3.4 体检结论

"有采集器但完全没接入日常链"的只有 **2 家**：字节跳动、美的集团 —— 都在本次接入。
其余停更来源属于：**在跑但失败**（网络/契约/源站重复 ID，属质量问题不属接入问题）、**被时间上限截断**（调度问题）、**p1 迁移前的老 id 命名空间被冻结**（数据治理问题，见 §6 遗留）。

---

## 4. 顺带接入：美的集团

`qiuzhao/collector/p1_midea_public.py`（新增，`collect()` + `merged_registry()`），注册块同样追加在最后。

- 官方校招接口：`GET .../school/position/common/project/list` 发现 campaign，`POST .../school/position/common/position/list` 逐项目翻页。
- scope 口径：`employementCategory 1 = 校招`（2027届美的星 + 2027应届博士）、`4 = 实习`（日常实习 + 校企合作实习）；项目每次动态发现，campaign 改名/新增无需改代码。
- **social 按设计 `blocked`**：公开校招接口看不到社招岗位，空集不能被当成"没有岗位"。
- id 沿用 `midea-<positionId>` + 同一详情 URL，146 条存量原地更新。

**真实验证（31 次请求，间隔 ≥1.0s）**

| scope | 项目 | expected_total | 实收 | status |
|---|---|---|---|---|
| campus | 美的星 148 + 博士 66 | 214 | 214 | `success` / `complete` |
| intern | 日常实习 152 + 校企合作 169 | 321 | 321 | `success` / `complete` |
| social | — | — | 0 | `blocked`（设计如此） |

campus/intern 均通过 `validate_result`，id 全为 `midea-<positionId>`。
另有防护：跨项目重复 id 会从 expected_total 里扣除（并在证据里记录）；出现**未被任何 scope 认领**的活跃项目分类时强制降级 `partial`，不做缺席下线。

---

## 5. 单测

| 套件 | 结果 |
|---|---|
| `tests/test_p1_bytedance_public.py`（新增 18 条） | 全通过 —— 含 scope→recruitment_id 映射、接口 10000 上限强制 partial、计数漂移、重复 id、空正文、**统一 id 规则回归**、**老行原地合并不重复**、**接管后缺席下线** |
| `tests/test_p1_midea_public.py`（新增 13 条） | 全通过 —— 含多项目并集、分类隔离、跨项目去重、未映射分类降级、social blocked、老行原地合并 |
| `tests/test_collector_next_integration.py` | 更新（新增 `PUBLIC_API_ONLY` 分组，保证两个新注册块在 DEFAULT_COMPANIES 里连续且不与其他块交错），通过 |
| `pytest tests/` 全量 | **4 failed / 479 passed / 55 skipped**，与**本 worktree 改动前基线完全一致，无新增失败** |

基线 4 条（改动前同样 4 条）：`test_core.py::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline.py::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema.py::test_enum_check_fails_when_data_drifts`（任务书所述既有 3 条），外加 `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together`。
最后一条是**外接盘 exFAT 慢盘导致的 sqlite 锁竞争 flake**：同一提交在本地盘 worktree `collector-next-2` 上是 3 failed，在本 worktree 上偶发第 4 条（`database is locked`，4 进程同时初始化）。

---

## 6. 部署件 `pipeline-watch/deploy-artifacts/20260918i/`

**须叠加在 `20260918h` 之后。** 只含本次新增/改动的运行时文件：

| 文件 | 目标 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/` | 覆盖（h 版 + 2 个注册块 + `stable_id_prefix` 规则） |
| `p1_bytedance_public.py` | `qiuzhao/collector/` | 新增 |
| `p1_midea_public.py` | `qiuzhao/collector/` | 新增 |
| `bytedance.py` | `qiuzhao/collector/` | 覆盖（`fetch_page` 新增 2 个形参 + 口径注释） |
| `SHA256SUMS.txt` / `DEPLOY-NOTES.md` | — | 校验与说明 |

`deploy/windows_collector.py` 及平台/银行/阿里/腾讯音乐/飞书各文件**本次不变**，不在包内；
计划任务参数无需改动（新公司通过 `REGISTRY` 自动进入 `DEFAULT_COMPANIES`，924 → 926 家）。

---

## 7. 遗留（未做，需站长决策）

1. **字节 22 条 + 美的存量老行的最终归宿**：老命名空间里没被首次完整快照覆盖的行不会被自动删除，也不会再刷新（`status=open`、`reviewed_at` 停在 09-10）。需要一次性治理决策：确认下线 → 由 p1 缺席规则在第二次完整快照后自然处理；或直接标记 `removed`。本次**不做破坏性清理**。
2. **孤儿命名空间**：`iguopin-`(1337)、`gp-`(865)、`<none>`(297)、`beisen-`(89)、`zhiye-`(37)、`feishu-`(26) 等一次性导入批次没有任何采集器，会永久停留在 09-10/无 `reviewed_at`。建议按「历史导入」打标或清出主库。
3. **`alibaba-`(477)、`netease-`(193)、`meituan-`(188)、`jd-`(106)、`xiaomi-`(100)、`thundersoft-`(125)、`chn-`(422)、`telecom-`(10)** 这些老命名空间的替代采集器都已在链上（p1 / run.py），但老行不会被覆盖写入，属于同类冻结问题。
4. **09-18 那次 p1 被 5h 上限截断**（32/150 单元未跑）。h 版的「次日公平兜底」正是为此设计，但需确认 09-19 的运行确实把未尝试公司排到了最前。
5. **平台公司整批未跑**：09-18 运行的 `companies` 只有硬编码 50 家（h 版未部署）。i 部署后 926 家全跑，首日耗时会显著上升，建议观察一次完整运行的 `--max-run-seconds` 是否够用。
6. **阿里/飞书系 headless 依赖**：精灵 `%LOCALAPPDATA%\ms-playwright` 不存在时，阿里系与飞书公司会 blocked（h 的部署说明已记录，本次未验证）。
7. **`mode`/adapter 侧未做的**：字节未接详情页（列表已含全文，无需）；美的社招通道未探源；`mindray.py`/`netease.py`/`meituan.py` 三个老式 `Collector` 模块已被 p1 适配器取代，未删除（避免影响 `v4_fields` 的 URL→届别映射）。

---

## 8. 复现命令

```bash
# 体检（只读，精灵侧）
ssh -i ~/.ssh/id_ed25519_lzh_qiuzhao -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=yes -l 'LZH\-LZH-' 192.168.31.204 \
    'C:\mcp-suite-collector\.venv\Scripts\python.exe -X utf8 -' < _inventory.py

# 字节 campus 真实验证（只读，非 --apply）
/Users/maxzhl/Projects/mcp-suite/.venv/bin/python run_campus_verify.py

# 单测
cd /Volumes/臭垃圾桶/生财MCP/_worktrees/bytedance-daily
/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/ -q
/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/test_p1_bytedance_public.py tests/test_p1_midea_public.py -q
```

## 9. 合规声明

本会话全程只读：未部署、未运行 `--apply`、未写精灵任何文件、未触碰阿里云 ECS、未调用飞书接口、未读取或打印任何令牌、未登录任何站点、未 `push`、未合并、未终止任何进程。精灵上的 SSH 仅用于 stdin 只读统计（jobs.json 与 p1 状态文件的聚合打印），未拉取大文件。产物全部写在外接盘 `/Volumes/臭垃圾桶/生财MCP/_worktrees/`。
