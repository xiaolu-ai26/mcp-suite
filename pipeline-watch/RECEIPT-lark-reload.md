# 收据：飞书镜像改为「固定表 + 每日整表重灌」

- 分支：`feat/lark-reload-mirror`（基于 `feat/collector-next-3`）
- 执行：DeepSeek（执行会话），2026-09-19
- 范围：新增 `qiuzhao/collector/lark_reload_mirror.py` + 部署件 `pipeline-watch/deploy-artifacts/20260919a/`。
  **未部署、未 SSH 精灵、未碰阿里云、未调生产 Base 的写接口、未 push、未合并 main。**
- 原型 Base（测试）：`https://my.feishu.cn/base/ThAxbM3QAazvJLsJfKpcPKOwnyd`
- 生产 Base（全程只读）：`REDACTED`

---

## 0. 结论摘要

站长定的「链接不能变」把导入式方案否掉了（导入每天新建 `table_id`，`?table=` 直达链接当天失效）。
本件实现备用方案：**表、字段、视图、选项一律不动，每天只重建表里的记录**。

```
备份全部记录(ndjson) → batch_delete 清空 → batch_create 整批重灌 → 校验行数
```

| 判断 | 结论 |
|---|---|
| 链接会不会变？ | **不会。实测两次完整重灌前后 `table_id` / `view_id` / 视图名 / 可见字段 / 视图筛选全部逐字节相同**，且带筛选的视图重灌后仍能正确取到行。模块里根本没有建表/删表/改名/改视图的调用。 |
| 每表要多少次调用？ | 1.95 万行的表 = **70 次**（备份 10 + 清空 39 + 重灌 20 + 校验 1）。现行增量同步同一张表是上千次。 |
| 实测多快？ | 测试 Base 实测 **2 张表 × 1.95 万行 = 3.9 万行**：串行 **590 s**；`--workers 3` **287 s（4.8 分钟）**；`--workers 6` **240 s（4.0 分钟）**。 |
| 9.3 万行能不能 ≤15 分钟？ | **能，但这是外推不是实测**：按每调用实测耗时外推 8 表 9.35 万行 ≈ **11 分钟**（workers=3），串行 ≈ 21 分钟。详见第 3、4 节。 |
| 慢的真因 | 不是限流（全程 **0 次限流重试**），是 **`lark-cli` 每次调用约 3 秒的固定开销**。所以设计目标是「压调用次数」而不是「压数据量」。 |
| 失败了会怎样？ | **实测过一次真失败**：`--workers 6` 首次跑（当时还没有瞬时错误重试）两张表都被 `1254607 Data not ready` 打断，**两张表都从自己的备份精确回滚到 19500 行（`restore.exact=true`）**，没有丢数据。随后给 1254607 加了退避重试，同样参数再跑即全绿。 |
| 字段保真 | 与现有同步**逐字段同一套映射**（直接复用 `lark_sync_index.append_row`）。重灌不碰 schema，所以不需要导入式那 7–9 次字段矫正。 |
| 每天表半空多久？ | **单表约 1.5 分钟**（最大表），8 张表的窗口串行分布在整轮约 11 分钟里。见第 8 节。 |
| 失败怎么办？ | 每表独立：失败表用自己重灌前的 ndjson 备份精确回滚（实测 `restore.exact=true`），其它表照常跑完。 |

---

## 1. 设计

### 1.1 流程与幂等门

```
sha256(jobs.json) == 上次成功重灌的 sha ?  → 跳过（0 次写调用）
    ↓ 否
读 Base 表清单 → 按行业分组把行分到已有表（超容量则告警不写，绝不自动建表）
    ↓
逐表串行：
    1. 备份：+record-list 分页导出全部记录 → runs/<ts>/<table_id>.before.ndjson（含 sha256）
    2. 清空：records/batch_delete，500 条/次（接口上限）
    3. 重灌：records/batch_create，1000 条/次（接口上限）
    4. 校验：+table-list 比对 records_count，不符则分页精确重数
    5. 任一步失败 → 重新读取当前记录并全部删除 → 用备份重建 → 精确重数
    ↓
全部成功才写 state（last_success_sha256）
```

**调用次数的关键**：`lark-cli` 的 `base +record-batch-create` 自带 **200 条/次上限**，
而开放平台 `records/batch_create` 是 **1000 条/次**、`records/batch_delete` 是 **500 条/次**。
模块改用 `lark-cli api POST ...` 打原始接口，拿到平台上限：

| 方式 | 1.95 万行「清空 + 重灌」调用数 |
|---|---|
| `base +record-*` 快捷命令（200/次） | 98 + 98 = 196 次 |
| **`lark-cli api` + 平台上限（500/1000）** | **39 + 20 = 59 次** |

### 1.2 分表规则（沿用现有）

| 行业 | 表 |
|---|---|
| 互联网/科技 | 互联网科技岗 → 互联网科技岗·续表1 → ·续表2 |
| 国企/央企 | 国企央企岗 → ·续表N |
| 制造/工业 | 制造工业岗 → ·续表N |
| 能源/电力、金融、医药/医疗、教育、物流/运输、传媒/广告、消费/零售、农业、房地产、其他、（空） | 其他行业岗 → ·续表N |

用**生产 Base 的真实表清单**验证过（只读 `+table-list` 一次），8 张表全部解析到正确 id：

```
互联网科技岗 ['tblX7rOpjWaRArng','tblu0nsYjntEOCGY','tblZOCFHBraQThw9']
国企央企岗   ['tbl0xkmJUMmLqZ1W']
制造工业岗   ['tbl0gDcxEaIOYERw','tbllqb2R9itUKXdH','tblffIc9CoTXcRUH']
其他行业岗   ['tblcrBAi0ld7uej8']
```

- 单表上限：`--max-rows-per-table` 默认 20000（= `lark_sync_index.TABLE_RECORD_LIMIT`，与现行一致）。
- **表不够时**：超出容量的部分进 `capacity_blocked`，**不写、不建表、不告警成失败**（沿用现有
  publisher-approved 的容量阻塞语义：`rows` / `capacity` / `overflow` 记进收据）。
- **不再需要的续表会被清空**：某个行业今天只有 1 张表的数据时，它的 `·续表1` 会被重灌成 0 行，
  不会留着昨天的溢出数据。（这是单测里发现并修掉的一个真 bug。）

### 1.3 字段映射：与现有同步完全一致

行的 19 列载荷直接调 `lark_sync_index.append_row(raw)` 生成——与现行增量同步**同一份代码**，
不重新实现。唯一两处刻意的差异：

1. **目标表与 `行业` 值按行自己的 `industry` 决定**，而不是 `append_row` 里那个只服务新收录记录的
   公司名路由（`enrichment.route`）。依据是生产 8 张表的实际分布：`其他行业岗` 里装的就是
   `能源/电力`、`金融`、`医药/医疗`… 各自的真实行业值。非 `V.INDUSTRIES` 的值降级为 `其他` 并告警。
2. **只写表里已经存在的字段与选项**（见 1.4）。

成员资格与排序沿用 `lark_sync_index.build_desired` 的既有规则（必须有 `source_url`+`application_url`、
丢测试记录、`id` 首现优先、`status=removed` 不发布）。重建时做**硬门校验**：第二遍扫出的 id 集合
与 `build_desired` 不一致就直接拒绝写入。

### 1.4 不新增字段、不新增选项

- 表里没有的字段：**整列丢掉**并记 `field_not_in_table` 告警。
  实测这条真的会命中：`append_row` 的输出里有 `岗位描述`，而生产 19 列里**没有这一列**
  （现有 `business_sync` 靠 `field_types` 过滤掉了它，直接 `append_row` 会把它带出来）。
- 选项：只保留表里已声明的选项；值不在选项表里就从单元格里去掉（**行照样写**，不会整条消失），
  记 `option_missing` 告警并带样例值。**绝不自动新增选项。**
- 单选塞进多值：截断为第一个并记 `single_select_truncated`。
- 告警按 (表, 字段, 类型) 聚合计数，不会因为 1.95 万行刷出 1.95 万条。

### 1.5 一个反直觉的接口事实（踩过）

**原始记录接口的单元格格式和快捷命令不是一套。**

`base +record-batch-create` 会在本地做归一化，所以它接受 `["校招"]` 这种单选用数组、
以及裸 URL 字符串；**原始 `records/batch_create` 两个都拒**：

| 写法 | 原始接口结果 |
|---|---|
| 单选 `{"行业": ["互联网/科技"]}` | ❌ `1254062 SingleSelectFieldConvFail` |
| 单选 `{"行业": "互联网/科技"}` | ✅ |
| 多选 `{"专业": ["计算机类"]}` | ✅ |
| url 样式文本 `{"原链接": "https://..."}` | ❌ `1254068 URLFieldConvFail` |
| url 样式文本 `{"原链接": {"link": "...", "text": "..."}}` | ✅ |

在**两张独立创建方式不同的表**（`+table-create` 建的、xlsx 导入后矫正的）上复现一致，
所以不是建表方式的问题。模块用 `write_payload()` 统一转换（单选→字符串、多选→列表、
url 样式文本→`{link,text}`）。单测里的假 Base 也按这个规则**严格拒绝**错误格式，
避免这个坑再犯一次。

---

## 2. 原型实测（测试 Base，2 张表 × 1.95 万行）

- 表：`重灌原型-互联网科技岗` = `tbljze0OOpedWWkh`，`重灌原型-互联网科技岗·续表1` = `tblKNjgpXqLXoVri`
  （用生产 schema 快照的 19 列 + 全部选项**新建**，不覆盖原有 2 张对照表）。
- 数据：`_research/lark-reload/gen_jobs.py` 生成的合成 jobs.json，39000 行，19 列词表全部取自
  生产 schema；每 977 行故意塞一个表里没有的城市/专业值，用来验证「缺失选项只告警不新增」。
- 容量设为 19500，让 3.9 万行正好切成 **2 张 × 1.95 万行**（生产默认仍是 20000）。
- 一共跑了 6 次真跑：R1 首灌、R2/R4 串行与 workers=3 的完整重灌、R3 workers=3、R5 workers=6
  （失败那次）、R6 workers=6（加了瞬时重试后）。每张表每次都清空 19500 行再灌 19500 行。

### 2.1 每次调用的实测耗时（这是所有估算的基数）

| 调用 | 条数 | workers=1 | workers=3 | workers=6 |
|---|---|---|---|---|
| 备份一页 `+record-list` | 2000 行 | 4.27 s | 4.28 s | 3.51 s |
| 清空一批 `batch_delete` | 500 条 | 3.23 s | 3.99 s | 6.44 s |
| 重灌一批 `batch_create` | 1000 条 | 4.46 s | 5.30 s | 6.46 s |
| `+field-list` / `+field-search-options` | — | 0.67 / 0.52 s | 同 | 同 |

**固定开销约 3 秒/调用**：500 条删除 3.23 s，而 1000 条创建 4.46 s——多出来的只是服务端插入
1000 行本身的约 1.2 秒。并发会把单次耗时推高（workers=3 约 +20%，workers=6 约 +100%），
但总墙钟时间仍然下降。**这正是「调用次数比数据量重要」的直接证据。**

### 2.2 完整「清空 → 重灌 → 校验」（同一份 3.9 万行、同一批表）

| 运行 | workers | 调用数 | 调用耗时合计 | **墙钟** | 结果 |
|---|---|---|---|---|---|
| R1（空表首灌） | 1 | 54 | 187.6 s | 200.8 s | 2×19500 ✅ |
| R2（清空重灌） | 1 | 150 | 551.3 s | **590.4 s（9.8 分）** | 2×19500 ✅ |
| R3（清空重灌） | 3 | 152 | 667.8 s | **341.9 s（5.7 分）** | 2×19500 ✅ |
| R4（清空重灌） | 3 | 149 | 619.9 s | **287.5 s（4.8 分）** | 2×19500 ✅ |
| R5（清空重灌） | 6 | 271 | 1247.0 s | 721.1 s | ❌ `1254607`，**两表精确回滚** |
| R6（清空重灌） | 6 | 152 | 843.4 s | **240.5 s（4.0 分）** | 2×19500 ✅（3 次瞬时重试） |

R2 的 150 次调用构成：备份 21 + 清空 78 + 重灌 40 + 校验 2 + 表结构 9。
R4 每张表墙钟 138.6 s / 134.3 s，其中备份约 43 s、清空约 52 s、重灌约 35 s。
R6 每张表墙钟 107.9 s / 118.6 s。

**限流：全程 0 次限流重试**（平台限额 50 次/秒，workers=3 时约 0.7 次/秒，用不到 2%）。
网络重试：R3 命中 3 次（备份/删除/创建各 1 次），全部按 5 s 退避后成功，未影响结果。

### 2.3 幂等门实测

R4 成功后拿**同一份** jobs.json 再跑：输出
`{"skipped": true, "reason": "source sha256 unchanged since last successful reload"}`，
**0 次写调用**，未新建 run 目录内容、未改 state。

### 2.4 workers 扫描（3.9 万行，同样的表、同样的数据量）

| workers | 墙钟 | 相对串行 | 删/建单次中位数 | 瞬时错误 |
|---|---|---|---|---|
| 1 | 590.4 s | 1.00× | 3.23 / 4.46 s | 0 |
| 3 | 287.5 s | **2.05×** | 3.99 / 5.30 s | 0 |
| 6 | 240.5 s | **2.46×** | 6.44 / 6.46 s | 3 次（已重试成功） |

**默认选了 3，不是 6**，理由是：3→6 只再快 1.20×（边际收益已经很小），而 6 会稳定触发
`1254607 Data not ready, please try again later`——每次重试还要多等 10–60 s，把收益又吃掉一部分。
3 在两次干净运行里一次瞬时错误都没有。要更快可以 `--workers 6`，重试逻辑已经能兜住。

### 2.5 失败与回滚的实测（R5，这是最有价值的一次运行）

`--workers 6` 第一次跑时还没有瞬时错误重试，两张表先后被
`1254607 Data not ready, please try again later` 打断（152 次调用里 2 次失败）。

结果：

```
tbljze0OOpedWWkh  status=failed  restore={"records": 19500, "exact": true}
tblKNjgpXqLXoVri  status=failed  restore={"records": 19500, "exact": true}
```

- 两张表都被**清空过**（各删了 19500 行）之后才失败的，回滚路径重新读表 → 删干净 → 用
  `<table_id>.before.ndjson` 重建，**两张表都精确回到 19500 行**。
- 失败没有扩散：每张表独立，`state` 没有写（`last_success_sha256` 保持上一次成功的值），
  所以下一次跑不会被误判成"已同步"而跳过。
- 随后把 `1254607` 加进退避重试（`TRANSIENT_CODES`），R6 同参数一次跑通。
- `800040832 quota_exceeded`（容量拒绝）**明确不在重试集合里**——那是要人来决策的，不是重试能解决的。

### 2.6 字段保真抽查（R6 之后，随机 500 行）

```
19 列，无 岗位描述
原链接   '[https://example.invalid/job/003000](https://example.invalid/job/003000)'   ← 可点击链接
投递入口 '[https://example.invalid/apply/003000](...)'                                ← 可点击链接
行业     ['互联网/科技']      ← 单选，单元素列表
工作地点 ['伦敦']             ← 多选
毕业届别 ['2031届'] / 专业 ['其他']
届别条件说明 '官方采集岗位资格字段：2031届\n官方采集岗位说明摘录：\n…'   ← 换行保留
截止类型 []                   ← 现行同步从不写这一列，保持为空
备注     None                 ← 站长人工列，同步永不写
```

500/500 行的 `原链接` 读回都是 markdown 链接（说明 `{link,text}` 写法生效、飞书已把它当链接），
500/500 行的 `行业` 都是合法单元素列表。

---

## 3. 9.3 万行要多久（外推，不是实测）

生产现状（只读核对）：8 张表、93519 行、19 列、单表最大 19993 行。

**调用数**（按平台上限整除）：

| 阶段 | 公式 | 调用数 |
|---|---|---|
| 盘点 `+table-list` | 1 | 1 |
| 表结构 `+field-list` + 选项分页 | 8 + 3×8 | 32 |
| 备份 `+record-list` | ceil(93519/2000) | 47 |
| 清空 `batch_delete` | ceil(93519/500) | 188 |
| 重灌 `batch_create` | ceil(93519/1000) | 94 |
| 校验 | 8 | 8 |
| **合计** | | **370 次** |

**耗时**（用 §2.1 的 workers=3 中位数，再乘 R4 实测的相位外系数 1.06）：

| 阶段 | workers=1 | workers=3 |
|---|---|---|
| 备份（串行，不改） | 201 s | 201 s |
| 清空 | 607 s | 250 s |
| 重灌 | 419 s | 166 s |
| 表结构 + 校验 + 盘点 | 27 s | 27 s |
| 相位合计 | 1254 s | 644 s |
| **外推总墙钟** | **≈ 21 分钟** | **≈ 11 分钟** |

同一套算法算 `--workers 6`：备份 165 s + 清空 202 s + 重灌 101 s + 其他 27 s ≈ 495 s × 1.06 ≈ **8.8 分钟**。

| workers | 9.3 万行外推总墙钟 | 是否 ≤15 分钟 |
|---|---|---|
| 1（串行） | ≈ 21 分钟 | ❌ |
| **3（默认）** | **≈ 11 分钟** | ✅ |
| 6 | ≈ 8.8 分钟 | ✅ |

**结论：默认 `--workers 3` 下 9.3 万行预计约 11 分钟，满足 ≤15 分钟；串行约 21 分钟不满足。**
这是从 3.9 万行实测按每调用耗时线性外推的，**没有在 9.3 万行上真跑过**（生产 Base 只读，
测试 Base 只放了 3.9 万行）。外推的三个不确定点：① 表数从 2 涨到 8，表结构读取与逐表串行
切换会多花一点；② 若飞书侧对同一 Base 的并发写更敏感，单次耗时会比 §2.1 更高；
③ 生产有 3 张接近 2 万行的表，它们的单表墙钟会比原型更长，但总调用数已经被上限算准了。

**如果 11 分钟还不够宽裕，按性价比排序的三个后续杠杆**（本次都没做）：
1. 备份分页并发（只读，省约 130 s）——没做是因为它要打破「按 offset 顺序翻页」的写法，
   而这恰好是回滚件的来源，宁可慢一点；
2. `--workers` 提到 6（见 §2.4，边际收益递减）;
3. 行数不变的日子改用 `batch_update` 原地更新（调用数再降 2/3），代价是偏离任务书
   指定的「先删后建」语义，本次不做。

---

## 4. 直连开放平台 HTTP 会不会更快？——会，但被「不许读令牌」挡住

任务书要求评估「直接用开放平台 HTTP 接口（用 lark-cli 已有的用户态凭据获取方式，不打印令牌）」。

**事实核对**：

- `lark-cli auth` 的子命令只有 `check / list / login / logout / qrcode / scopes / status`，
  **没有任何一条会把用户 access token 交出来**。
- macOS 上凭据存在 Keychain（CLI 里有一条 `config keychain-downgrade`，只有在默认存 Keychain 时
  才需要「降级」到文件）。
- 因此「取一次 token，之后用 `requests` + keep-alive 直连」必然要**读取令牌**，与硬约束冲突。

**放弃的性能（如实量化）**：原始接口每调用约 3 秒固定开销、HTTP 往返只要约 0.2–0.4 秒。
9.3 万行的 282 次删/建调用里约 850 秒是这 3 秒固定开销。真能直连的话，写入阶段大概能从
约 7 分钟压到 2 分钟左右。

**结论**：`lark-cli api` 是**约束内最快的路径**，而且它已经让我们拿到了平台批量上限
（500/1000，对比快捷命令的 200）。真正省下来的调用次数（196 → 59 次/表）比省单次开销更值钱。
要再快只有两条路：放宽「不许读令牌」，或提高 `--workers`。

---

## 5. 与现方案对比

| 维度 | 现行增量同步（`lark_sync_daemon` + `lark_sync_index`） | **固定表整表重灌（本件）** | 导入式（站长否掉） |
|---|---|---|---|
| `?table=` / `?view=` 链接 | ✅ 不变 | ✅ **不变（实测）** | ❌ 每天变 |
| 9.3 万行耗时 | 9-18 实测：改 1231 行跑了 **49 分钟**；1.8 万行 >1 小时 | **≈ 11 分钟**（外推，workers=3） | ≈ 5 分钟 |
| 单表调用数 | 上千次（200/批 × 多阶段 × CAS 回读） | **70 次/1.95 万行** | 约 25 次 |
| 限流风险 | 中（调用量大） | **极低**（0 次限流重试；约 0.7 次/秒 vs 限额 50 次/秒） | 极低 |
| 保留飞书侧人工改动 | 部分保留（有 `human lifecycle value retained` 逻辑） | **不保留**（每天整表重建，符合「服务器是唯一标准」） | 不保留 |
| 失败模式 | 部分写入 + 持久 journal + 精确 job_id 点查对账，状态机复杂 | 每表**独立**：备份 → 删 → 建 → 校验，失败表用备份精确回滚 | 旧表不动即为回退 |
| 依赖 | 无 | 无（只用已授权的记录读写接口） | ⚠️ 依赖未文档化字段 |
| 每天表半空窗口 | 无（原地更新） | **单表约 1.5 分钟** | 无（换表是原子的） |
| 代码量 | 现有 836 + 480 + 29120 行 | 新增约 700 行，不动现有同步代码（回退即开关） | — |

**代价是明确的**：重灌期间单表会短暂不完整，且飞书侧任何人工改动每天都会被覆盖。
后者本来就是既定规则（「服务器库是唯一标准，不保留飞书侧改动」），前者见第 8 节。

---

## 6. 链接与视图：实测证据

两次完整重灌（R2 之前 → R4 之后）对比：

```
tbljze0OOpedWWkh 重灌原型-互联网科技岗 | table_id stable: True
   view vewKzkmRao -> vewKzkmRao | id same: True | name same: True | filter same: True | visible_fields same: True
      filter: {"conditions": [["公司名称", "intersects", "云图"]], "logic": "and"}
tblKNjgpXqLXoVri 重灌原型-互联网科技岗·续表1 | table_id stable: True
   view vewLcPUmD0 -> vewLcPUmD0 | id same: True | name same: True | filter same: True | visible_fields same: True
```

带筛选的视图重灌后仍能正确取行：`+record-list --view-id vewKzkmRao` 返回 200 行，
**200 行的 `公司名称` 全部包含「云图」**，筛选条件仍然生效。

分组（group）没法在测试 Base 上写进去验证——`+view-set-group` 返回
`800004135 the method：OpenAPIUpdateViewGroup limited`（该 Base 不允许通过开放接口改分组）。
**这不是设计问题**：模块从头到尾没有调用过任何 `+view-*` 接口，`calls.json` 里只有
`inventory / base+field-list / base+field-search-options / backup / delete / create / verify`
七种 kind，所以视图配置在物理上不可能被改到。视图 id / 名称 / 可见字段的实测一致也印证了这一点。

---

## 7. 单测

`tests/test_lark_reload_mirror.py`，**15 条，全绿，零网络**（用一个内存假 Base 复刻 lark-cli 接口）：

| 测试 | 覆盖 |
|---|---|
| `test_industry_routes_to_the_live_table_group` | 行业 → 表分组；缺失/未知行业降级 + 告警 |
| `test_continuation_tables_are_discovered_in_numeric_order` | 续表按 N 排序；缺表 = 零容量 |
| `test_placement_fills_existing_tables_and_blocks_the_overflow` | 容量切分；溢出 → `capacity_blocked`，不建表 |
| `test_sanitize_drops_undeclared_field_and_option_but_keeps_the_row` | 丢未声明字段/选项但保留整行；单选截断；告警聚合 |
| `test_sanitize_reports_a_value_whose_option_the_table_lacks` | 缺失选项告警 |
| `test_write_payload_uses_the_raw_endpoint_cell_format` | 单选→字符串、多选→列表、url→`{link,text}` |
| `test_write_payload_drops_a_field_the_table_does_not_declare` | `岗位描述` 被丢 |
| `test_restore_payload_reduces_markdown_links_and_drops_empty_cells` | 备份回灌：markdown 链接还原、空格不写 |
| `test_snapshot_keeps_the_established_membership_and_payload` | 成员规则与 `build_desired` 一致（去重/下架/缺链接/首现优先） |
| `test_end_to_end_reload_is_idempotent_and_never_touches_table_identity` | 端到端；**不再需要的续表被清空**；sha 相同即跳过；无建表/删表调用 |
| `test_a_failed_create_is_rolled_back_from_that_tables_own_backup` | 单表失败 → 备份精确回滚，其它表照常完成，不写 state |
| `test_a_restore_that_also_fails_is_reported_as_partial_data` | 回滚也失败 → `partial_data` 告警 |
| `test_run_batches_overlaps_but_keeps_order_and_propagates_failure` | 并发真的有重叠、顺序保持、失败传播、失败后无残留 worker |
| `test_module_has_no_undefined_globals` | 静态查未定义全局名（防漏 import） |

`pytest tests/` 全量：**3 failed / 508 passed / 55 skipped**，3 条失败与基线（`test_core` /
`test_p1_pipeline` / `test_schema`）完全相同，**无回归**。

---

## 8. 部署与回滚

部署件：`pipeline-watch/deploy-artifacts/20260919a/`（**未部署**）。细节见其中的
`DEPLOY-NOTES.md` 与 `PROD-BACKUP-MANIFEST.txt`。要点：

- 只改 `base-sync` 一步：`windows_collector.py` 加 `SYNC_MODE` 常量 + 一个 if/else 分支
  （共 +11/−1 行，见 `windows_collector.minimal.diff`），reload 分支超时 3600 s。
- 新增 `lark_reload_mirror.py`；因为要复用现有映射，还要带上精灵上目前没有的
  `lark_sync_index.py` 与 `lark_sync_enrichment.py`。
- 回滚：设 `QIUZHAO_LARK_SYNC_MODE=daemon` 即可切回原增量同步，**不用改文件**；
  或从备份目录覆盖回去。
- ⚠️ **回滚到 daemon 后必须先 `--snapshot` 重建索引再 `--apply`**：重灌每天换 record_id，
  daemon 旧索引里的 record_id 全失效，直接 `--apply` 会把「找不到记录」当新增而重复写入。

### 每天「表半空」的时间窗

重灌不是原子的，单表会经历「逐渐变少 → 空 → 逐渐填满」。实测（1.95 万行的表，workers=3）：

```
备份期间        数据完整          约 43 s
清空期间        19500 → 0（递减）  约 52 s
重灌期间        0 → 19500（递增）  约 35 s
────────────────────────────────────────
单表不完整窗口                    约 87 s ≈ 1.5 分钟
（其中真正「全空」只是一瞬间）
```

- 8 张表是**串行**跑的，所以整轮约 11 分钟里总有一张表处在窗口内，但**每张表自己只受影响约 1.5 分钟**。
- 用户拿 `?table=` 直达链接看到的就是自己那张表：在它自己的 1.5 分钟里行数会跳动。
- 对比：现行增量同步改 1231 行要跑 49 分钟，那 49 分钟里表一直处在「改了一半」的状态。
- 想彻底消掉这个窗口只能换表（导入式），而换表就会换链接——两者不可兼得。

---

## 9. 约束遵守

| 约束 | 执行情况 |
|---|---|
| 不部署 | ✅ 未 SSH 精灵、未覆盖任何生产文件；部署件只落在分支的 `pipeline-watch/deploy-artifacts/20260919a/` |
| 不覆盖精灵正式目录 | ✅ 全程未连精灵 |
| 不碰阿里云 | ✅ 未连 114.215.188.109，未跑任何远端命令 |
| 不调写飞书生产 Base 的接口 | ✅ 生产 Base **只读 3 次调用**：`+table-list`（盘点 8 表 + 验证分表规则）。写操作全部发生在测试 Base `ThAxbM3QAazvJLsJfKpcPKOwnyd` |
| 不读取/打印任何令牌 | ✅ 鉴权全程在 lark-cli 进程内；脚本不读 Keychain、不读配置文件、不打印任何凭据（`calls.json` 只记命令名前三个 token 与耗时） |
| 不登录、不绕过验证码/签名 | ✅ 复用已有用户态登录，未触发任何授权流程 |
| 不 push、不合并 main | ✅ 只在本 worktree 分支提交 |
| 不用 `git stash`、忽略 `._*` | ✅ |
| 不终止任何进程 | ✅ 未调用 `stop_tree`/`kill`；重试只 sleep 后重发 |
| macOS 无 `timeout` | ✅ 未使用；子进程超时用 `subprocess.run(timeout=)` |
| 产物写外接盘 | ✅ 原型 run/脚本在 `/Volumes/臭垃圾桶/生财MCP/_research/lark-reload/`；仓库产物在分支 |

**测试 Base 现在的状态**（保留供总查，未删）：

| 表 | id | 行数 |
|---|---|---|
| 互联网科技岗（导入原型遗留） | `tbl4UFSltrBFE0Pp` | 19500 |
| 对照-CSV导入-未矫正（导入原型遗留） | `tbl5DmuVHfurc5Ul` | 19500 |
| 重灌原型-互联网科技岗 | `tbljze0OOpedWWkh` | 19500 |
| 重灌原型-互联网科技岗·续表1 | `tblKNjgpXqLXoVri` | 19500 |

---

## 10. 产物

| 路径 | 内容 |
|---|---|
| `qiuzhao/collector/lark_reload_mirror.py` | 新模块（约 700 行） |
| `tests/test_lark_reload_mirror.py` | 15 条单测 |
| `pipeline-watch/deploy-artifacts/20260919a/` | 部署件（windows_collector.py + 3 个模块 + SHA256SUMS + DEPLOY-NOTES + PROD-BACKUP-MANIFEST + minimal diff） |
| `pipeline-watch/RECEIPT-lark-reload.md` | 本文件 |
| `/Volumes/臭垃圾桶/生财MCP/_research/lark-reload/` | 原型脚本与原始数据（`gen_jobs.py`、`setup_tables.py`、`view_state.py`、`proto_jobs*.json`、`proto_runs/*/receipt.json` + `calls.json`） |

---

## 11. 原始数据（各次运行的收据）

`_research/lark-reload/proto_runs/` 下每次运行一个目录，含 `receipt.json`（逐表逐阶段）
与 `calls.json`（每一次 lark-cli 调用的 kind/耗时/成败）。关键几次：

| 目录 | 说明 |
|---|---|
| `20260918T171336Z` | R2，串行完整重灌，3.9 万行，590.4 s |
| `20260918T172434Z` | R3，workers=3，341.9 s（含 3 次网络重试） |
| `20260918T173043Z` | sha 相同 → 跳过（0 写调用） |
| `20260918T173043Z-1` | R4，workers=3，287.5 s |
| `20260918T173544Z` | R5，workers=6 首次，**两表失败 + 精确回滚**，721.1 s |
| `20260918T174807Z` | R6，workers=6 + 瞬时重试，240.5 s |
