# 部署件 20260919a：base-sync 切到「固定表整表重灌」

**本包未部署、未 SSH、未碰阿里云、未调生产 Base、未 push。** 覆盖的是精灵（Windows）
`C:\mcp-suite-collector` 的 `base-sync` 这一步：从 `lark_sync_daemon`（增量同步）切成
`lark_reload_mirror`（固定 table_id/view_id，每天清空整表重灌）。

## 1. 这个包解决什么

站长定的硬约束是**分享给用户的表格链接不能变**，所以不能用"导入新表"方案（导入每天新建
table_id，`?table=...&view=...` 直达链接当天失效）。本包走备用方案：表结构、表名、视图
全部不动，每天只重建表里的**记录**：

```
备份全部记录 → batch_delete 清空 → batch_create 整批重灌 → 校验行数
```

服务器发布的 `jobs.json` 仍是唯一真源；飞书只写展示 Base，绝不回写服务器，不保留飞书侧
人工改动（与现行规则一致）。

## 2. 本包内容

| 文件 | 目标路径（精灵） | 动作 |
|---|---|---|
| `windows_collector.py` | `deploy\windows_collector.py` | 覆盖（**仅 base-sync 段有 diff**，见 `windows_collector.minimal.diff`） |
| `lark_reload_mirror.py` | `qiuzhao\collector\lark_reload_mirror.py` | **新增** |
| `lark_sync_index.py` | `qiuzhao\collector\lark_sync_index.py` | 新增（精灵上目前没有；新模块复用它保证字段映射与现有一致） |
| `lark_sync_enrichment.py` | `qiuzhao\collector\lark_sync_enrichment.py` | 新增（同上） |

**最小 diff**（`windows_collector.py`，共 +11/−1 行）：

1. `ROOT` 之后加一行 `SYNC_MODE=os.environ.get('QIUZHAO_LARK_SYNC_MODE','reload')...`；
2. 原来的 `sync_exit=step(['-m','qiuzhao.collector.lark_sync_daemon',...],21600)` 换成
   一个 `if SYNC_MODE=='daemon': … else: …` 的分支，reload 分支超时 3600s，
   并把 `sync_mode` 写进 `windows-status.json`。

**没有**改采集步骤、没有改发布/CAS、没有改计划任务、没有动 `run.py`。

## 3. 部署前必须已经在精灵上的文件（本包不含，只校验）

| 文件 | 期望 sha256 |
|---|---|
| `qiuzhao\collector\sync_lark_multivalue.py` | `5c77cde828bae6f609684fe1c00606c85e50a69b0258dbab6bafc75ed3878ce0` |
| `qiuzhao\v4_fields.py` | `3c08ed8dd5a67e723522ef5f9aee6f89ea52961d12bed6aadbd5a08d5fab1463` |
| `qiuzhao\collector\portable_runtime.py` | `1e40c5c215b97f374b38a558c55ce2e9ca46bea0654399cec7f88b56afd69bda` |
| `qiuzhao\normalize.py` | `a53adaf33c891b5d8d8dd5b7531c0799b57666d5a62e987dc92ac22b9eb51b31` |
| `qiuzhao\collector\p1_pipeline.py` | `ff96be4d772847a0273003e2db0466d3ad698dc5cd719d968f40fb96abc8dc76`（= 20260918k 的值） |

任一不符 → **停下**，记录真实哈希并当漂移处理，不要覆盖。

## 4. 部署步骤（未执行，供上线时照做）

1. **空闲判定**：当天采集轮已收尾、无采集进程、`data\lark-sync` 没有 running 状态。
2. **备份**：`robocopy C:\mcp-suite-collector\deploy C:\mcp-suite-backup-<时间戳>\deploy /E`
   与 `...\qiuzhao\collector C:\mcp-suite-backup-<时间戳>\qiuzhao\collector /E`（只备这两处）。
3. **传文件**：4 个文件分片 base64 传到 `C:\mcp-suite-deploy-20260919a\`，对
   `SHA256SUMS.txt` 复核 4/4。
4. **覆盖**：4 个目标路径依次覆盖；覆盖后重算 4/4 哈希。
5. **静态校验**：`py_compile` 4 个文件；`IMPORT_OK` 检查
   `python -c "import qiuzhao.collector.lark_reload_mirror"`。
6. **干跑**：`python -m qiuzhao.collector.lark_reload_mirror --source-path data\jobs.json
   --state-dir data\lark-reload --runs-dir data\lark-reload\runs`（**不带 `--apply`**）
   —— 只读盘点 + 出计划，不写飞书。
   `--workers` 默认 3（实测 3.9 万行 287 s，外推 9.3 万行约 11 分钟）；
   6 更快（240 s / 外推约 8.8 分钟）但会触发可重试的瞬时错误 `1254607`，需要时才调。
7. **首次真跑**：次日的 06:10 计划任务自带 `--apply`。跑完看
   `data\lark-reload\runs\<时间戳>\receipt.json` 的 `success`/`failed_tables`/
   `capacity_blocked`/`alerts`。

## 5. 回滚

代码层（二选一，都不需要改文件）：

- 设环境变量 `QIUZHAO_LARK_SYNC_MODE=daemon` → 立刻回到原增量同步；
- 或从 `C:\mcp-suite-backup-<时间戳>\` 把 4 个文件覆盖回去（`lark_reload_mirror.py` 可直接删）。

数据层：重灌是"先备份、后清空、再重灌"，每张表的备份在
`data\lark-reload\runs\<时间戳>\<table_id>.before.ndjson`，失败表会自动用它回滚
（`receipt.json` 的 `restore.exact=true` 表示已精确还原到重灌前）。

**注意**：回滚到 `lark_sync_daemon` 后，它自己的 `data\lark-sync` 索引里记的 record_id
已经全部失效（重灌每天换 record_id）。回滚后第一次必须让它重新 `--snapshot` 建索引，
不能直接 `--apply`，否则会把"找不到记录"当成新增而重复写入。

## 6. 没做什么

- 没有新建/改名/删除任何表、字段、视图、选项——模块里根本没有这些调用（`calls.json`
  的 kind 只有 `inventory / base+field-list / base+field-search-options / backup /
  delete / create / verify`）。
- 没有碰生产 Base（原型只在测试 Base `ThAxbM3QAazvJLsJfKpcPKOwnyd` 上跑）。
- 没有读、存、打印任何令牌：鉴权全程在 lark-cli 进程内完成。
