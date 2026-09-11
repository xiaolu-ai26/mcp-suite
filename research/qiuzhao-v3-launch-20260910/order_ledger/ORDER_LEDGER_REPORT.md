# A线#5 订单→兑换码分配台账 — 交付报告

- 任务：秋招MCP v3 A线#5
- 执行时间：2026-09-10（北京时间）
- 台账目录：`research/qiuzhao-v3-launch-20260910/order_ledger/`
- 套餐：39 元/秋招季，每日 200 次工具调用，有效至 2026-12-31（北京时间）

---

## 1. 台账设计

### 1.1 与生产鉴权库完全分开

台账数据库 `order_ledger.sqlite3` 是**新建的独立 SQLite**，与 `private/access.sqlite3`
在文件路径、连接、进程上均不耦合：

- 本次执行**未打开、未读取、未覆盖** `private/access.sqlite3`；
- 未读取 `private/qiuzhao-2026-stock-50.txt`（正式 50 枚备货码明文全程未触碰）；
- 台账进程不引用生产库路径，`Ledger` 类只操作自身 `.sqlite3` 文件。

### 1.2 表结构（与任务给定 schema 一致）

- `orders`：订单主表，`UNIQUE(channel, order_number)`；记录渠道、订单号、SKU、份数、
  码安全引用（SHA256 前 8 位 `code_reference`）、码完整 SHA256（`code_hash`）、
  状态机、分配/发送/兑换时间、售后状态。
- `code_inventory`：码库存表，`code_hash UNIQUE`，`order_id` 外键关联订单；
  仅存 `code_hash` + 前 4 位前缀 `code_prefix`（供人工核对），**不存明文**。

状态机：`available → allocated → sent → redeemed`；发送失败走 `retry`（码不释放）。

### 1.3 管理脚本 `ledger_manager.py`

| 函数 | 作用 |
|---|---|
| `add_code(code)` | 入库一枚码：仅落 SHA256 哈希 + 前 4 位前缀，重复入库幂等 |
| `allocate(channel, order_number, quantity)` | 原子分配：`BEGIN IMMEDIATE` 事务 + 先查已绑定；同单重复调用返回原绑定，不重复分码 |
| `mark_sent(order_id, sent_channel)` | 标记已发送，联动库存码状态 |
| `mark_send_failed(order_id, reason)` | 发送失败标 `retry`，码仍绑定该订单，不释放回可售库存 |
| `check_redeemed(order_id, probe=None)` | 通过只读 `probe(code_hash)` 核对服务端兑换事实；已兑换则落 `redeemed` |
| `list_status()` | 订单/库存各状态计数 |
| `export_public_view()` / `write_public_view()` | 导出公开视图（只留 `code_reference`，不含明文、不含完整哈希） |

**原子性与幂等**：分配在单事务内“选可用码 → 逐枚 `UPDATE ... WHERE status='available'`
二次确认 rowcount=1”，任何竞争失败整单回滚；`UNIQUE(channel,order_number)` 兜底重复事件。

**明文不落盘**：`code_hash` 是 SHA256 摘要，`code_prefix` 仅前 4 位；完整明文码只在
调用方内存中存在，写入数据库前已哈希。文件权限统一 `0600`。

---

## 2. 模拟闭环结果（3 枚测试码，隔离环境）

测试码由 `core.store.Store.generate_codes(3)` 在**临时隔离库**生成（运行后临时库已删除），
与正式 50 码无任何关系。详细逐步记录见 `simulation_log.md`（只含 `code_reference` 摘要）。

| 步骤 | 结果 |
|---|---|
| a. 模拟订单 `TEST-20260910-001` | channel=test |
| b. 分配码 | → `allocated`，绑定 reference `27083798` |
| c. 渲染发货文案 | 按 FULFILLMENT.md 模板，明文码仅内存占位，未落盘 |
| d. 标记已发送 | → `sent`，经 `simulated-msg-channel` |
| e. 隔离环境 `/redeem` 兑换 | 成功（daily_limit=200，expires 2027-01-01） |
| f. 只读核对兑换 | → `redeemed`，`redeemed_at` 已落账 |
| g. 同订单再次 allocate | `reused=True`，返回原绑定 `27083798`，**未分新码** ✅ |
| h. 新订单 `TEST-20260910-002` 分配 | 分到不同码 `1f41016c`，**未与订单1复用** ✅ |
| 补充：发送失败 `mark_send_failed` | 订单3 标 `retry`，码仍 `allocated`，**未回库** ✅ |

闭环结束时台账统计：订单 `{redeemed:1, sent→已流转, allocated:1, retry:1}`；
库存 `{redeemed:1, allocated:2, available:0}`，3 枚测试码全部去向清晰、无一错配。

---

## 3. 商家后台权限核对

- 已检索项目内（排除 `private/` 与 `.venv`）是否存在小红书/淘宝开放平台
  appkey、session token、卡密自动发货配置或商家后台会话。
- **结果：未发现任何已授权的商家后台/开放平台访问凭证**（命中的“淘宝/字节/阿里”字样
  均来自岗位采集数据，与店铺发货无关）。
- 因此如实记录：**未核对平台自动发货能力**；本次未打开任何商家后台页面，
  未猜测平台菜单，未配置任何自动发货，未向任何真实买家发送消息。
- 后续要走自动发货，需先由 Max 完成商家后台登录授权、确认渠道类目与卡密/虚拟商品
  交付权限后，再接本台账的 `allocate/mark_sent`；在此之前一律人工逐单手动交付。

---

## 4. 安全声明（硬性约束核对）

- [x] 未读取 `private/` 任何文件，未读取正式 50 枚备货码明文。
- [x] 未连接、未覆盖、未读取生产 `access.sqlite3`；模拟兑换发生在临时隔离库，运行后已删除。
- [x] 未替任何买家预兑换；测试兑换仅作用于隔离测试码。
- [x] 同一枚码未分配给不同订单（步骤 g/h 已验证）。
- [x] 码明文仅在内存最小范围出现；交付物与日志中只存 SHA256 摘要/前 8 位引用/前 4 位前缀，
      已用正则扫描确认无 35 位明文码泄漏。
- [x] 没有真实付款不构成订单成交：当前所有订单均为 `channel=test` 的模拟单，不对外成立。
- [x] 未配置平台自动发货，未向真实买家发消息。
- [x] 台账数据库与 `access.sqlite3` 物理独立，文件权限 `0600`。

---

## 5. 交付物清单

| 文件 | 说明 |
|---|---|
| `order_ledger.sqlite3` | 独立台账库（权限 0600） |
| `ledger_manager.py` | 台账管理脚本（含 CLI） |
| `simulation_log.md` | 模拟闭环逐步日志（无明文码） |
| `fulfillment_template.txt` | 发货文案模板（占位符，无真实码） |
| `ORDER_LEDGER_REPORT.md` | 本报告 |

> 注：`.gitignore` 已含 `*.sqlite3*`，台账库不会被提交；模拟测试码为一次性隔离产物，
> 不进入正式可售库存。
