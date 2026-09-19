# 部署件 20260919m：飞书续表自动创建（发现 + 建表 + 逐字段校验）

**本包未部署、未 SSH、未碰阿里云、未调生产 Base、未 push。** 目标机：精灵（Windows）
`C:\mcp-suite-collector`。本包把「满表只记 `capacity_blocked`、续表 id 硬编码」变成
真正自动：按表名发现 `<行业基名>` / `<行业基名>·续表N`，最后一张表余量低于阈值时
自动建 `<行业基名>·续表N+1`，建完逐字段校验，不过就删表且绝不写入。

## 1. 本包内容（6 个运行时文件，不含测试）

| 文件 | 精灵目标路径 | 动作 |
|---|---|---|
| `lark_continuation.py` | `qiuzhao\collector\lark_continuation.py` | **新增**（发现/建表/校验/幂等/告警的唯一实现） |
| `sync_lark_multivalue.py` | `qiuzhao\collector\sync_lark_multivalue.py` | 覆盖（`full_fields` 委托共享读取；快照按名发现续表；常量改为来自共享模块） |
| `lark_sync_enrichment.py` | `qiuzhao\collector\lark_sync_enrichment.py` | 覆盖（`append_p1` 分组 → `ensure_capacity` → 写新高 N 表；`route_group` 动态路由） |
| `lark_sync_index.py` | `qiuzhao\collector\lark_sync_index.py` | 覆盖（transport 动态表清单；append 前自动建表；`locate` 覆盖全部续表） |
| `lark_sync_daemon.py` | `qiuzhao\collector\lark_sync_daemon.py` | 覆盖（身份漂移校验改为四个基表必须存在，允许动态续表） |
| `lark_reload_mirror.py` | `qiuzhao\collector\lark_reload_mirror.py` | **新增/覆盖**（整表重灌；容量不足改调 `ensure_total_capacity`，不再只报 `capacity_blocked`） |

`SHA256SUMS.txt` 为本目录 6 个文件；生成后已 `shasum -a 256 -c` 全 OK，且与分支源码
逐字节一致。**本包不含 `windows_collector.py`**：它不由本任务改动，见 §3 叠加顺序。

## 2. 行为与安全边界

- **阈值**：`CAPACITY_THRESHOLD = min(1000, 20000/20) = 1000`（`lark_continuation.py`）。
  最后一张表余量 < 1000 或不足以容纳本次新增行时先建续表；一天新增约 1000–2000 行，
  1000 余量可覆盖一天写入并吸收 `records_count` 的延迟。
- **校验**：字段数量 / 名称 / 类型 / `multiple` / `style`、以及单选多选**选项集合**必须与
  该行业**基表**一致；顺序按默认网格视图的可见字段顺序校验（Bitable `+field-list` 不保证
  返回创建顺序，2026-09-17 人工建表已记录该限制）。`工作地点` 600+ 选项走
  `+field-search-options` 全量分页，不会漏。
- **失败即删**：校验不通过 → `+table-delete --yes` 删除刚建的表 → 发
  `continuation_validation_failed` 告警 → 抛错，调用方记 `capacity_blocked`，**一个格都不写**。
- **幂等 / 并发**：状态文件 `continuation-state.json` 记录（表名、id、时间、校验结果）；
  进程内 RLock + 文件锁串行化「发现→判定→建表」；重跑发现新表已有余量则 0 次建表。
- **告警**：写入 run 目录的 `continuation-alerts.jsonl`（`continuation_created` /
  `continuation_create_failed` / `continuation_validation_failed` / `legacy_id_drift`）。
  项目当前**没有飞书消息通道**，故未接新通道，缺口见收据 §告警。

## 3. 叠加顺序（与 20260919g / lark-reload / 20260919a 的关系）

前提：精灵现役 = 20260918k（2026-09-18 20:27 上线，17/17 一致）。三条路径：

1. **只上本包（增量同步路径）**：`20260918k → 20260919m`。
   `windows_collector.py` 保持 k 版（末尾调 `lark_sync_daemon`），日更走
   `sync_lark_multivalue` + `append_p1`，满表时自动建续表。
2. **本包 + 已审的累积包 g**：`20260918k → 20260919g → 20260919m`。
   g 覆盖采集侧 26 个文件；m 只覆盖飞书同步 6 个文件，二者无交集。若 g 先上、m 后上，
   中间若 `p1` 已修好继续跑，飞书这边仍是旧的「满表记 blocked」，不会写坏数据。
3. **整表重灌路径（lark-reload）**：`20260918k → 20260919g → 20260919a → 20260919m`。
   20260919a 的 `windows_collector.py` 把 base-sync 切到 `lark_reload_mirror`
   （默认 `QIUZHAO_LARK_SYNC_MODE=reload`，可设 `daemon` 回退）。**m 必须叠在 a 之后**：
   a 里的 `lark_reload_mirror.py` / `lark_sync_index.py` / `lark_sync_enrichment.py`
   被 m 的同名文件取代（m 保留 a 的全部字段映射与整表重灌逻辑，只把「容量不足只报警」
   改成「先自动建表并校验再写」）。a 的 `windows_collector.py` 与
   `windows_collector.minimal.diff` 不由 m 改动，按 a 原样部署。

任一路径都不改 `run.py`、不改计划任务、不改采集/发布步骤。

## 4. 部署步骤（未执行，供上线时照做）

1. **空闲判定**：当日轮已收尾、无采集进程、`data\lark-sync`（或 `data\lark-reload`）
   非 running。
2. **备份**：`robocopy C:\mcp-suite-collector\qiuzhao\collector
   C:\mcp-suite-backup-<时间戳>\qiuzhao\collector /E`（如需连 windows_collector
   一起回退，再备 `deploy\windows_collector.py`）。
3. **传文件**：6 个文件分片 base64 传到 `C:\mcp-suite-deploy-20260919m\`，
   对 `SHA256SUMS.txt` 复核 6/6。
4. **覆盖**：6 个目标路径依次覆盖；覆盖后重算 6/6。
5. **静态校验**：`py_compile` 6 个文件；`IMPORT_OK` 检查
   `python -c "import qiuzhao.collector.lark_continuation, qiuzhao.collector.lark_reload_mirror"`。
6. **干跑**（不带 `--apply`）：
   - 增量：`python -m qiuzhao.collector.lark_sync_daemon --source-path data\jobs.json
     --state-dir data\lark-sync --runs-dir data\lark-sync\runs`
   - 重灌：`python -m qiuzhao.collector.lark_reload_mirror --source-path data\jobs.json
     --state-dir data\lark-reload --runs-dir data\lark-reload\runs`
   干跑与盘点只读；建表只在真跑（`--apply`）且确实需要时发生。
7. **首次真跑**：次日 06:10 计划任务自带 `--apply`。看
   `data\lark-sync\runs\<时间戳>\continuation-alerts.jsonl`（增量）或
   `data\lark-reload\runs\<时间戳>\receipt.json` 的 `continuations` / `capacity_blocked` /
   `alerts`。

## 5. 回滚

- 设 `QIUZHAO_LARK_SYNC_MODE=daemon`：从整表重灌回到增量同步（若已部署 a 的
  `windows_collector.py`）。
- 从 `C:\mcp-suite-backup-<时间戳>\` 覆盖回 6 个文件；`lark_continuation.py` 可保留
  （无副作用）或删除。回滚到旧 `sync_lark_multivalue.py` 前，若新增的续表已写入过记录，
  旧代码不认识该表 → 会再次把满表记为 `capacity_blocked`，不会写坏数据。
- 误建表：`lark_continuation` 只在本包自己的逻辑里建表；校验失败会自删。若运维要手工
  清理，删除 `互联网科技岗·续表3` 之类的空表即可，删除前确认 `records_count=0`。

## 6. 没做什么

- 未部署、未 SSH、未碰阿里云、未 push、未合并 main。
- **生产 Base `REDACTED` 全程只读**（本轮只读了 1 次
  `+table-list`）；建表/写行只发生在测试 Base `ThAxbM3QAazvJLsJfKpcPKOwnyd`。
- 未读、存、打印任何令牌：鉴权全程在 lark-cli 进程内。
- 未终止任何进程。
