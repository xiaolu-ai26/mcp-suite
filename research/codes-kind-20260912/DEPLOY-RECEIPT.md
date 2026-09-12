# 兑换码测试 / 正式分离部署收据（DEPLOY-RECEIPT，codes-kind-20260912）

部署时间：2026-09-12 14:54:22–14:54:40（北京时间，停机约 18 秒）　执行：豆包（Doubao），经 Max 批准；核验：总控会话（只读复核）
目标：`root@114.215.188.109`，代码 `/opt/mcp-suite`（venv `.venv`），数据 `/var/lib/mcp-suite`，服务 `mcp-suite.service`（127.0.0.1:8768，公网 `https://savegems.top/qiuzhao/`）
部署版本：分支 feat/codes-kind @ **5af6f7f**；基线为 v4 部署版本 `2f0f070`（main @ 98ca784 的已部署状态）
依据：`research/codes-kind-20260912/KIMI-DEPLOY.md`，按任务书执行。
范围：只替换 7 个文件、只重启 `mcp-suite.service`。未碰 `mcp-suite-bench.service`、nginx、cron、`jobs.json` 及其他站点。全程未使用、未输出任何真实 key、兑换码或管理员令牌。

> 执行者变更：任务书原写给 Kimi Code（文件名沿用 `KIMI-DEPLOY.md`），实际由豆包执行。除执行者身份外，任务书内容照此执行。

## 1. 部署结果：成功

功能已于 2026-09-12 14:54:40 上线生产并通过核验，未触发回滚。

## 2. 七个文件（线上 sha256 = feat/codes-kind@5af6f7f）

线上 7 个文件的 sha256 与分支版本逐一相同（本收据提交时又从 git 重新计算核对一次，仍相同）：

| 文件 | sha256（线上 = 5af6f7f） |
|---|---|
| `core/store.py` | `03d4c8438e0e4893105bbb1bb2d1cfeb4290e5af7410e747c4114d667428da40` |
| `core/server.py` | `0fce6e80a97c981dc4d72e8c130ebcaeab1263a372bb7bbbd1240b83ec1a943b` |
| `core/admin.py` | `7ccc97fc11e4a00f90eabb413a4b97462aa872bb79aac91d9f40c31add59e690` |
| `core/static/index.html` | `3d3c11b8b0aa55c69001868d08c39a8f83352da6319a5966d329ccb51ecd5fb4` |
| `core/static/app.js` | `b049adce57dd526ad41e2bec2da4ae277ce4b51e33c935fa284a31e4b02f7d6e` |
| `core/static/admin.js` | `944ee83210188904865330a3ebdbe51497e5b094768d0390be346d553d9f1f2a` |
| `core/static/admin.css` | `a78e92054ee8c9cc9fec1039fde4f29cdd3e014def9f749cb0bddac10eb2e765` |

服务器上 14:45 之后被改动的**只有这 7 个文件**；定时任务、systemd 单元、nginx 配置均未触碰。

## 3. 停机与服务

- 停机 **14:54:22–14:54:40**，约 18 秒，只重启 `mcp-suite.service`。
- `mcp-suite-bench.service` 的 `ActiveEnterTimestamp` 仍为 **2026-09-10 15:41:37**，与部署前相同，**未被重启**。
- 启动后日志零报错（无 `Traceback`、`Error`）。

## 4. 数据库迁移（首次启动时自动执行）

- 新增 `code_kind` 列。
- 新建三个触发器：`redemption_codes_formal_kept`、`redemption_codes_kind_fixed`、`redemption_codes_kind_required`。
- `按类别` 只有 `('test', 20)`；`按类别已兑换` 只有 `('test', 6)`——存量 20 个码全部记为测试码，符合迁移设计。
- 兑换码总数 **20**、有效密钥 **8**，与部署前完全一致：**无数据删改**。

核验只跑聚合计数（列名、触发器名、计数），未读取、未输出任何兑换码、hash 或 key。

## 5. 接口核验

| 检查项 | 结果 |
|---|---|
| `/health` | 正常，`jobs` **25631** |
| `/api/pricing`（本机 127.0.0.1:8768 与公网） | 两者**一致** |
| `/api/pricing` 响应头 | `cache-control: no-store` |
| `/api/pricing` 正文 | `sold=0`、`early_bird_active=true`、`current_tier=1`、`current_price_cny=29.9`、`remaining=10` |
| `/api/pricing` 正文敏感信息 | **无**兑换码、无密钥 |
| 后台（不带令牌） | **401** |
| bench `/api/pricing` | **404**（bench 无此接口，符合预期） |
| bench `/health` | **200** |

## 6. 备份

目录 `/opt/mcp-suite/deploy/backup-pre-codes-kind-20260912-145422`，含 7 个文件的部署前副本，以及 `access.sqlite3`、`access.sqlite3-wal`、`access.sqlite3-shm` 的副本。库文件仅 `cp -p` 复制，未读取内容。

暂存目录已按任务书第 8 步清理。

## 7. 合并进 main

- 部署提交：**`feat/codes-kind@5af6f7f`**（线上 7 个文件即此版本）。
- 合并方式：**合并提交**（`git merge --no-ff`），合并提交 `17e5b6d`，两个父提交为 `dc15c00`（main）与 `5af6f7f`（feat/codes-kind）。
- **为什么不用 fast-forward**：feat/codes-kind 从 `98ca784` 拉出，而 main 在此之后已前进到 `dc15c00`（v4 收据、A2 证据与示例 fixtures），两条线已分叉，`--ff-only` 不成立。
- **为什么不 rebase**：本收据要引用部署提交 `5af6f7f`，rebase 会改写 hash，使收据与线上实际部署版本的对应关系失效。故保留原 hash，用合并提交。
- 合并无冲突（两边改动的文件集合无重叠：本分支改 `core/` 与 `research/codes-kind-20260912/`、`tests/`，main 侧改 `research/qiuzhao-doubao-fix-20260911/`、`research/qiuzhao-v4-impl/`、`research/qiuzhao-v4-interface-20260911/`）。
- 未 push，未改 `feat/codes-kind` 以外的任何分支。

## 8. 回滚

**未触发**。回滚方式见同目录 `KIMI-DEPLOY.md` 的「回滚」一节（R1 恢复 7 个文件、R2 删 `redemption_codes_kind_required` 触发器、R3 启动并确认、R4 仅库文件损坏时用备份库且须先得 Max 同意）。

## 9. 与任务书不一致之处 / 过程说明

1. **执行者**：任务书写给 Kimi Code，实际由豆包执行。
2. **暂存目录占位符未填**：任务书里的暂存目录占位符（`staging-codes-kind-<TS>`）没有填上实际时间戳。豆包自行定位到 `/opt/mcp-suite/deploy/staging-codes-kind-20260912-145004`，并以 7 个文件的 sha256 与目标值**逐一比对确认后**才继续。总控已复核该判断成立——比对的是内容哈希而非路径，结论不受占位符缺失影响。

## 10. 待办（本次未处理）

- **管理后台文案与实际不符**：`core/server.py:680`，兑换码分区（§ 02 · 兑换码）的说明文字为

  ```html
  <p class="sec-note">系统只存哈希；明文兑换码仅在生成时显示一次。</p>
  ```

  实际实现是**兑换码明文存储，并在后台列表中显示**（这是 Max 的选择，不是 bug）。文案与实现不一致，需另行修正文案。本次部署未改动这句话。

## 后续观察点

- 首批正式码生成后，确认 `code_kind` 写入为 `formal`，以及「正式码不许删」（`redemption_codes_formal_kept`）在后台删除操作上按预期拦截。
- 早鸟价随 `sold` 增长的档位切换（`current_tier`、`current_price_cny`、`remaining`）在真实成交后复核一次。
- 备份目录 `/opt/mcp-suite/deploy/backup-pre-codes-kind-20260912-145422`（含未读取的库文件副本）建议在确认稳定运行后由 Max 决定清理时机。
