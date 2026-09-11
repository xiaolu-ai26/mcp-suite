# A线#5 模拟闭环日志（订单→兑换码分配台账）

- 运行时间：2026-09-10 13:55:41 UTC+08:00
- 台账库：order_ledger.sqlite3（与 private/access.sqlite3 物理分开）
- 隔离测试库：临时目录，运行后已删除；**未读取/未触碰正式50枚备货码，未连接生产鉴权库**
- 本日志只记录 code_reference（SHA256 前8位）与前缀，**不记录任何明文兑换码与测试 api_key**

[13:55:41] 隔离鉴权库: /var/folders/_6/ddpzt5tj2m10z3xjxzrrnw0c0000gn/T/qz-ledger-sim-mm6fb92k/isolated-test-access.sqlite3 （临时目录，结束后删除）
[13:55:41] 台账库: /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/order_ledger/order_ledger.sqlite3 （与上者物理分开）

### 步骤1：生成3个测试码（store.generate_codes）
[13:55:41] 测试码#1 入库 -> code_reference=27083798 prefix=QZ-4
[13:55:41] 测试码#2 入库 -> code_reference=1f41016c prefix=QZ-8
[13:55:41] 测试码#3 入库 -> code_reference=535f0e16 prefix=QZ-E

### 步骤2：模拟订单 TEST-20260910-001 分配码
[13:55:41] allocate 结果: order_id=1 reused=False status=allocated
[13:55:41]   绑定码 reference=27083798 prefix=QZ-4

### 步骤3：用 FULFILLMENT.md 模板生成发送文案（测试码仅内存占位）
[13:55:41] 发送文案已按模板渲染（明文码占位，未写入日志）

### 步骤4：mark_sent -> sent
[13:55:41] mark_sent: order_id=1 status=sent at=2026-09-10T13:55:41+08:00 via=simulated-msg-channel

### 步骤5：隔离环境调用 redeem 兑换测试码#1
[13:55:41] redeem: product=qiuzhao daily_limit=200 expires_at=2027-01-01T00:00:00+08:00 (api_key 为测试密钥，不落盘)

### 步骤6：服务端只读核对 -> redeemed
[13:55:41] check_redeemed: status=redeemed redeemed_at=2026-09-10T13:55:41+08:00 redeemed=['27083798'] pending=[]

### 步骤7：同一订单再次 allocate（幂等测试）
[13:55:41] 重复 allocate: reused=True order_id=1 status=redeemed
[13:55:41]   返回码 reference=27083798（应与首次一致=27083798）

### 步骤8：新订单 TEST-20260910-002 分配（应分到新码）
[13:55:41] 新订单 allocate: order_id=2 reused=False code_reference=1f41016c

### 步骤9：list_status 统计
[13:55:41] {"orders": {"allocated": 1, "redeemed": 1}, "code_inventory": {"allocated": 1, "available": 1, "redeemed": 1}, "code_total": 3}

### 步骤10：发送失败标 retry，码不释放
[13:55:41] order3 status=retry 后库存 available 数=0 allocated=2（码仍占用，未回库）
[13:55:41] 隔离临时库已删除（测试明文码不残留）
