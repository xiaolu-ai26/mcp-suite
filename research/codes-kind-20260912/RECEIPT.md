# 秋招兑换码测试 / 正式分离收据（codes-kind-20260912）

日期：2026-09-12　分支：`feat/codes-kind`（worktree `~/Projects/mcp-suite-wt-codes`），基于 `feat/v4` 2f0f070（开工时 0098267，收尾前 rebase 到 2f0f070，无冲突）。没有合并、没有 push、没有部署。

服务器 `root@114.215.188.109` 只做了只读操作：`ssh cat` 拉 6 个页面文件到本地临时目录（没带 `backups/`、`*.bak*`）、`sha256sum`、`ls`、`systemctl show/status/cat`（环境变量只看名字）、`ss`、nginx 扩展配置的 `sha256sum`、在代码目录和 cron 里 grep `redemption_codes`。**没有打开线上 access.sqlite3**，没有读取任何 token、兑换码或 key。

## 结论

- 管理后台生成码时分“测试 / 正式”，默认测试，选正式有二次确认；列表多了类别列和“全部类别 / 正式 / 测试”筛选，和“全部 / 未兑换 / 已兑换”叠加生效；正式码行没有删除按钮，显示“不可删除”。
- 删除规则在服务端一处（`core/store.py: delete_refusal`）：秋招套餐的正式码一律 409 拒绝；测试码随时可删，已兑换的测试码删除时同一事务里把它换出的 key 置 `disabled=1`，之后 `/usage` 和 `/mcp` 都返回 401。bench 套餐保持原规则（只能删未兑换的）。数据库层另有触发器兜底：正式码删不掉、类别改不了、插入必须带类别。
- 早鸟名额只按“已兑换的秋招正式码”计数，阶梯只写在 `PLANS["qiuzhao-2026"]["early_bird"]` 一处；新增公开只读 `GET /api/pricing`，兑换页和后台都读它。页面上的价格、早鸟标签、剩余名额、阶梯高亮全部由接口渲染，接口失败时不显示任何价格和剩余数。
- 删除写一行 JSONL 到 `MCP_ADMIN_LOG_PATH`（默认 `/var/lib/mcp-suite/admin_actions.jsonl`），只记 hash 前 12 位；日志写不进去就回滚这次删除。
- 测试：全量 156 passed（基线 feat/v4 0098267 为 129 passed + 1 failed，rebase 后另一会话已修掉那 1 项）；新增 22 项全过；10 张截图。

## 提交

| 提交 | 内容 |
|---|---|
| `8031c29` | store：类别列与一次性迁移、三个触发器、删除规则、早鸟状态；CLI `generate-codes` 必须带 `--kind` |
| `9842293` | server + 后台：`/api/pricing`、管理接口带类别、删除日志；后台页面、admin.js、admin.css |
| `0355a60` | 兑换页：index.html 去掉写死的价格，app.js 读 `/api/pricing` 渲染 |
| `1b8ac2f` | `tests/test_codes_kind.py` |
| `46d8e88` | 截图脚本与截图、UI 核对记录 |
| 本收据所在提交 | RECEIPT.md、KIMI-DEPLOY.md、pytest 输出 |

没有改：`core/store.py` 文件头 docstring（rebase 后是另一会话 55bd3ee 的新版本）、`tests/test_core.py`、`qiuzhao/tools.py`、`qiuzhao/v4_fields.py`、`_dist_admin_ok`（Bearer 和 `?token=` 照旧）、`private/`、main、其他工作副本。

## 改动清单

| 文件 | 改动 |
|---|---|
| `core/store.py` | `PLANS["qiuzhao-2026"]` 加 `code_kinds: True` 和 `early_bird: ((10, 29.9), (50, 39.9), (100, 49.9))`，标准价仍取 `price_cny` 59.9。`redemption_codes` 加 `code_kind TEXT CHECK(code_kind IN ('test','formal'))`（新库建表即带，旧库迁移加列）。三个触发器：`redemption_codes_kind_required`（插入时类别为空就中止）、`redemption_codes_kind_fixed`（已有类别不许改）、`redemption_codes_formal_kept`（正式码不许删）。`generate_codes(count, plan, kind="test")` 显式写入类别，非法类别、bench 套餐要正式码都报 ValueError；`delete_code(code_hash, audit=None)` 返回删除记录，拒绝时抛 `AccessError`（409 正式码 / 400 bench 已兑换 / 404 不存在），`audit` 在提交前调用、抛错即回滚；新增 `price_state()`、`early_bird()`、`code_stats()`、`list_codes()`、`delete_refusal()`。 |
| `core/admin.py` | 本地批量生成加必填 `--kind test|formal`。 |
| `core/server.py` | `GET /api/pricing`（不鉴权，只返回聚合数；bench 进程返回 404）；`/api/admin/stats` 在原 `total/redeemed/pending` 外加 `kinds.formal/test/other` 和 `early_bird`；`/api/admin/codes` 每行加 `code_kind`、`kind_applies`、`deletable`、`delete_revokes_key`；`/api/admin/generate` 对秋招套餐必须带 `kind=test|formal`（缺省或非法 400），数量非整数 400，store 报错 400（原来是 500），bench 套餐不带 kind 照旧可用；`/api/admin/delete_code` 校验 64 位十六进制 hash、坏 JSON 400，按规则删并写管理日志。`/admin` 内联页面加类别下拉、提示语、类别筛选、类别列和概览里的正式 / 测试 / 早鸟三张卡。 |
| `core/static/admin.js` | `request()` 支持 method/body（原来删除请求被当 GET 发出，服务端 405，删除按钮一直不能用）；类别筛选与状态筛选叠加；删除按钮只看服务端给的 `deletable`；删除确认框对已兑换测试码写明“对应的 key 会同时作废”；生成正式码前确认“正式码生成后不能删除，将计入早鸟名额”，取消则不生成；每次生成后和每次打开页面，类别都回到“测试码”；统计区显示正式 / 测试的总数与已兑换数、早鸟进度（“已售 3 / 当前第 1 档，剩 7 个名额 · ¥29.9/月”）。 |
| `core/static/admin.css` | 类别徽标、筛选分隔线、提示语、删除按钮文字色（替代原来的 JS 行内颜色）。 |
| `core/static/index.html` | 价格卡和阶梯表不再写死任何价格或名额，只留占位和“正在读取…”。 |
| `core/static/app.js` | `loadPricing()`：同源 `fetch('api/pricing')`（外部 js，符合 `script-src 'self'`），校验字段后渲染“前 N 名早鸟价 · 剩 X 个名额”、当前价、标准价删除线和阶梯高亮（已满档灰显“已满”）；早鸟用完只显示标准价、去掉早鸟标签、高亮“100 名后恢复标准价”；请求失败或字段不对时只显示“暂时无法读取当前价格和剩余名额，请以购买渠道的报价为准”。文件头的接口清单同步改了。 |

## 接口

`GET /api/pricing`（公开，Guard 统一加 `cache-control: no-store`）：

```json
{"plan":"qiuzhao-2026","currency":"CNY","standard_price_cny":59.9,
 "tiers":[{"tier":1,"rank_from":1,"rank_to":10,"price_cny":29.9},{"tier":2,"rank_from":11,"rank_to":50,"price_cny":39.9},{"tier":3,"rank_from":51,"rank_to":100,"price_cny":49.9}],
 "sold":3,"early_bird_active":true,"current_tier":1,"current_tier_rank_to":10,"current_price_cny":29.9,"remaining":7}
```

`sold` = 秋招套餐里 `code_kind='formal' AND redeemed_at IS NOT NULL` 的行数。第 1–10 名 29.9、11–50 名 39.9、51–100 名 49.9，之后 59.9：sold=0→第 1 档剩 10；10→第 2 档剩 40；11→第 2 档剩 39；50→第 3 档剩 50；100、101→标准价、`early_bird_active=false`、剩 0。

## 迁移逻辑

`Store.__init__` 在原有 `code_plain` 迁移之后，每次启动执行：

1. `BEGIN IMMEDIATE` 拿写锁，在锁内读 `PRAGMA table_info(redemption_codes)`；
2. 没有 `code_kind` 列才 `ALTER TABLE ... ADD COLUMN code_kind TEXT CHECK(...)`；
3. `UPDATE redemption_codes SET code_kind='test' WHERE code_kind IS NULL`；
4. `CREATE TRIGGER IF NOT EXISTS` × 3；提交。

加列、回填、建触发器在同一个事务里，要么全做要么全不做。两个进程（qiuzhao、bench 共用一个库）同时启动时，后拿到锁的一方看到的已经是完成状态，什么也不改；测试里 4 个子进程同时对旧库启动验证过。之后每次重启：列已存在不再 ALTER，第 3 步没有空类别可填，触发器已存在，任何码的类别都不会变；已设定的类别即使有人手工 UPDATE 也会被 `kind_fixed` 触发器挡住。

第 3 步每次启动都跑，但只填空类别。正常情况下加列之后不会再有空类别（插入触发器挡住了）；它只在“回滚到旧代码期间旧代码生成了码、之后再部署本版本”时起作用，把那段时间生成的码记为测试码。见“需要 Max 决定”第 3 条。

新码：`generate_codes` 的 INSERT 显式带 `code_kind`；Python 参数默认 `test` 只是为了让现有测试和 `tests/_mcp_harness.py` 这些老调用不改也能跑，而且是无害的一边；生产入口（管理接口、CLI）都要求显式给类别。

### 在线上库上会发生什么（没有读线上库，按代码推断）

线上 `mcp-suite.service` 与 `mcp-suite-bench.service` 共用 `/var/lib/mcp-suite/access.sqlite3`（9/12 00:5x 看到文件 81,920 字节、最后修改 9/11 20:27）。部署后 `mcp-suite` 第一次启动时：

- **正常情况（没有 `code_kind` 列）**：加列，表里现有的每一行都记为 `test`，包括已兑换的、未兑换的，也包括 bench 的 `BM-` 码；建 3 个触发器。不删任何行，不改 `api_keys`、`entitlements`、`daily_usage`、`usage_log`，所有已发出的 key 照常可用。库很小，瞬间完成。
- `code_plain` 列有没有都行：没有的话 v4 的迁移先补上（旧行明文为空，后台显示 hash 前缀），然后同上。
- 迁移后 `/api/pricing` 返回 `sold 0`、第 1 档、剩 10；兑换页显示“前 10 名早鸟价 · 剩 10 个名额”、¥29.9。后台正式码 0、测试码 = 现有总数。
- **异常情况（有人在 21:26 之后已经加过 `code_kind` 列）**：不加列，只把空类别填成 `test`，已有值不动；如果那一列的取值不是 test/formal，列上也没有 CHECK。任务书第 2 步的只读结构检查遇到这种情况会让执行者停下，不部署。
- 迁移失败（比如库被锁 30 秒以上）：事务回滚，库不变，服务起不来，按回滚步骤恢复文件即可。

## 测试结果

命令：`MCP_JOBS_PATH=<v4 worktree>/qiuzhao/data/jobs.json .venv/bin/python -m pytest -q`（jobs.json 只读引用 v4 工作副本里的 9/11 数据；我的 worktree 没有 `qiuzhao/data/`）。

- 全量：**156 passed**（`evidence/pytest-full.txt`）。开工时在 feat/v4 0098267 的导出副本上跑的基线是 129 passed、1 failed（`test_atomic_redemption`）；rebase 到 2f0f070 后那一项已被另一会话的 55bd3ee 改好。156 = 134 个原有 + 22 个新增。
- 新增 `tests/test_codes_kind.py` **22 passed**（`evidence/pytest-codes-kind.txt`），全部用临时库，HTTP 测试起子进程 uvicorn，所有路径（库、分销库、调用日志、管理日志）在 pytest 临时目录，管理令牌随机生成、只经子进程环境变量传入：
  - 迁移：旧结构（有 / 没有 `code_plain` 各一遍）迁移后全部是测试码、3 个触发器在、key 照常能用；生成正式码后连续 3 次重新初始化，类别不变；旧的未兑换码兑换后仍是测试码、不计数；4 个进程同时启动迁移不报错。数据库层：不带类别插入、改类别（正→测、测→正）、直接删正式码都被触发器挡住。
  - 删除：正式码（已兑换 / 未兑换）409 拒绝；未兑换测试码删除成功；已兑换测试码删除成功且 key 在 `authorize`、`consume` 被拒，另一把 key 不受影响；管理日志写失败时删除回滚、key 仍可用；bench 保持“只删未兑换”。
  - 计数：`price_state` 在 0/10/11/50/100/101 的档位、价格、剩余；真实库里 101 个正式码逐个兑换，在这 6 个点核对；生成不计、测试码和 bench 兑换不计、删除已兑换测试码后计数不变。
  - 接口：4 个管理接口在无令牌、错误 Bearer、错误 `?token=` 下都是 401，且没有生成或删除任何码；`/api/pricing` 不带鉴权 200、`cache-control: no-store`、字段集合固定、与库里计数一致，响应里没有任何 code_hash、明文码或 key（也没有 `QZ-`、`qz_` 字样）；生成接口缺类别 / 类别非法 / 数量非法都是 400；HTTP 删除规则同上，删除后 `/usage` 和 `/mcp` 用那把 key 都是 401；管理日志字段固定为 `ts, action, code_hash_prefix, plan, code_kind, redeemed, key_revoked`，不含明文码、完整 hash、key，文件权限 600；后台统计与列表字段和 store 一致。
  - bench：`MCP_PRODUCT=bench` 正常启动，`/api/pricing` 404，`/config` 正常，删未兑换 bench 码成功、删已兑换的仍是原来的 400 文案，bench key 照常可用，生成 bench 码不带 kind 照旧可以。

### 截图（`evidence/`，本地临时库，脚本 `scripts/shots.py`）

脚本在临时目录起 qiuzhao 服务（`MCP_DB_PATH` 等全部指向临时目录），令牌取自环境变量 `CODES_KIND_ADMIN_TOKEN`，没有就在内存里生成，只经子进程环境变量交给服务、在浏览器里输入登录框，不落文件；结束后删掉临时目录。图里的兑换码是临时库里的假码。

| 文件 | 看点 |
|---|---|
| `01-redeem-sold3.png` | 已兑换 3 个正式码：“前 10 名早鸟价 · 剩 7 个名额”、¥29.9、标准价 ¥59.9 删除线，第 1 档高亮 |
| `02-admin-overview.png` | 正式码 5（已兑换 3 · 未兑换 2）、测试码 4（2 · 2）、早鸟进度“已售 3 / 当前第 1 档，剩 7 个名额 · ¥29.9/月” |
| `03-admin-filter-formal.png` | 类别筛选“正式”：5 行全是“正式”徽标，操作列都是“不可删除”，没有删除按钮 |
| `04-admin-filter-test.png` | 类别筛选“测试”：4 行都有删除按钮 |
| `05-admin-filter-test-redeemed.png` | “已兑换”+“测试”叠加：2 行 |
| `06-admin-generated-formal.png` | 生成 2 个正式码后的提示和列表；类别下拉已回到“测试码” |
| `07-redeem-sold10.png` | 已售 10：“前 50 名早鸟价 · 剩 40 个名额”、¥39.9，第 1 档灰显“已满” |
| `08-redeem-sold100.png` | 已售 100：只显示 ¥59.9，无早鸟标签、无删除线，“100 名后恢复标准价”高亮 |
| `09-admin-overview-sold100.png` | 后台“已售 100 / 早鸟名额已满，恢复标准价 ¥59.9/月” |
| `10-redeem-pricing-unavailable.png` | 拦截 `/api/pricing`：价格卡只有“暂时无法读取当前价格和剩余名额，请以购买渠道的报价为准”，阶梯表只有“暂时无法读取早鸟阶梯” |

`evidence/ui-checks.json` 记录每一步页面上实际显示的文字和接口返回（码已打码）。其中：删除已兑换测试码的确认框原文是“确定删除测试码 QZ-… 吗？删除后无法恢复。该码已兑换，对应的 key 会同时作废，之后用这把 key 的调用都会被拒绝。”，删除前那把 key 调 `/usage` 200、删除后 401，另一把测试 key 仍 200；删除未兑换测试码的确认框没有 key 那句；生成正式码的确认框“正式码生成后不能删除，将计入早鸟名额（兑换成功时计入）。确定生成 2 个正式码吗？”，点取消后正式码数不变（5），点确定后变 7；生成测试码不弹框。

浏览器控制台：每次打开兑换页有一条 CSP 报错 “Applying inline style violates … style-src 'self'”，来源是 `index.html` 第 117 行原有的 `style="margin-top: 16px;"`，feat/v4 和线上同样存在，不是本次引入；503 是本地故意不给 jobs.json 导致 `/health` 不可用；`ERR_FAILED` 是第 10 张图故意拦截的请求。后台页面没有控制台报错。

## 线上页面与 feat/v4 的差异

9/12 01:05 用 `ssh cat` 只读拉取，sha256 对比：

| 文件 | 线上 | main | feat/v4 | 结论 |
|---|---|---|---|---|
| `index.html` | `31db55d7…` | 同 | 同 | 三者一致 |
| `app.js` | `cb3d5e92…` | 同线上 | `cd30fbfd…` | 只差 v4 的 4118fe8 两行工具名文案（`jobs_deadlines`→`jobs_search … deadline_within_days=7`，`jobs_deadlines`→`jobs_stats`，`limit=1`→`page_size=1`） |
| `site.css` | `637f974a…` | 同 | 同 | 一致 |
| `admin.html` | `9782079e…` | 同 | 同 | 一致 |
| `admin.js` | `afd34e78…` | 同 | 同 | 一致 |
| `admin.css` | `15c775ce…` | 同 | 同 | 一致 |

线上的 `core/server.py`（`08143798…`）、`core/store.py`（`0348d335…`）、`core/admin.py`（`5675873a…`）也等于 main。也就是说豆包在线上改过的内容已经全部在 main 的 bc5d194（“production code snapshot 2026-09-11 21:26”）里，线上没有 main 之外的新增内容，按“以线上为底”处理和以 feat/v4 为底结果相同，本次改动直接叠在 feat/v4 版本上，没有丢任何线上内容。部署任务书第 1 步会在部署前再核一次哈希，不一致就停。

两处与页面有关的现状，没有改：

- 后台实际页面是 `core/server.py` 里 `/admin` 路由返回的内联 HTML；`core/static/admin.html` 没有任何路由提供（里面的 `onclick=` 在 CSP 下也不会执行），是死文件，本次没动。
- 后台“兑换码”区的说明“系统只存哈希；明文兑换码仅在生成时显示一次。”与现状不符（`code_plain` 存明文且列表可复制），本次没动文案。

## 部署方案

只写、未执行，见同目录 `KIMI-DEPLOY.md`（给 Kimi 的完整任务书）。要点：必须在 v4 部署之后；先确认 `feat/codes-kind` 包含已部署的 v4 提交、线上 7 个文件的哈希等于那个提交；只读检查库结构（只看列名、触发器名和计数）；在 `/opt/mcp-suite/deploy/` 下建一份完整代码的暂存副本，覆盖 7 个文件后用临时库 import 一次两个产品；停 `mcp-suite.service` → `cp -p` 复制 access.sqlite3（不读取）→ 备份并替换 7 个文件 → 启动 → 核验（`/api/pricing` 应为已售 0、剩 10；库里只看 `SELECT code_kind, count(*) ... GROUP BY 1` 这类聚合数）；回滚是恢复 7 个文件 + 删掉“插入必须带类别”这一个触发器 + 重启，库不需要恢复。

要替换的文件（本分支 46d8e88 起的 sha256）：

| 文件 | sha256 |
|---|---|
| `core/store.py` | `03d4c8438e0e4893105bbb1bb2d1cfeb4290e5af7410e747c4114d667428da40` |
| `core/server.py` | `0fce6e80a97c981dc4d72e8c130ebcaeab1263a372bb7bbbd1240b83ec1a943b` |
| `core/admin.py` | `7ccc97fc11e4a00f90eabb413a4b97462aa872bb79aac91d9f40c31add59e690` |
| `core/static/index.html` | `3d3c11b8b0aa55c69001868d08c39a8f83352da6319a5966d329ccb51ecd5fb4` |
| `core/static/app.js` | `b049adce57dd526ad41e2bec2da4ae277ce4b51e33c935fa284a31e4b02f7d6e` |
| `core/static/admin.js` | `944ee83210188904865330a3ebdbe51497e5b094768d0390be346d553d9f1f2a` |
| `core/static/admin.css` | `a78e92054ee8c9cc9fec1039fde4f29cdd3e014def9f749cb0bddac10eb2e765` |

不需要新依赖，不需要改 systemd 单元或 nginx（`/qiuzhao/` 整段反代到 8768、`proxy_cache off`，线上配置哈希与仓库 `deploy/mcp-suite-qiuzhao.conf` 一致），不需要新环境变量（`MCP_ADMIN_LOG_PATH` 可选，默认落在 `ReadWritePaths` 允许的 `/var/lib/mcp-suite/`）。

## 需要 Max 决定

1. **bench 服务要不要一起停 / 启。** 按你的要求任务书默认只重启 `mcp-suite.service`。bench 与它共用代码目录和库，bench 进程从 9/10 15:41 一直跑旧代码；它不会生成秋招码、也没有后台路由，和迁移后的库兼容，不重启没有功能问题。区别只在备份：bench 不停的话，复制库文件的那几毫秒里 bench 恰好写库会得到不一致的备份（概率很低）。任务书里留了开关 `STOP_BENCH`，默认 `no`。以后 bench 因任何原因重启都会加载新代码，已测过 bench 在新代码下行为不变。
2. **早鸟名额按“兑换成功”计。** 这是你定的规则，照做了。后果是：卖出但买家还没兑换的正式码不占名额，页面在这段时间会少算，比如卖了 12 个、兑换了 8 个，页面仍显示第 1 档剩 2 个。如果要按“卖出”算，需要另有“已售未兑换”的记录来源。
3. **空类别回填每次启动都跑。** 只把空类别填成测试码，不改已有类别。正常情况下是空操作；只有“回滚到旧代码期间用旧代码生成了码、然后再部署本版本”时，会把那段时间的码记为测试码（不计名额、可删）。如果那段时间卖出过码，重新部署前要告诉开发改成正式码的处理办法（触发器不允许事后改类别）。如果你要求严格“只在加列那一次”，改成只在第 2 步加列时回填即可，一行改动。
4. **回滚时保留两个触发器。** 回滚只删“插入必须带类别”那一个（否则 v4 的生成接口会失败），“类别不许改”“正式码不许删”留着，以免回滚期间误删已卖出的正式码。要彻底恢复原样的话也可以三个都删，任务书里写了。
5. **两处小现状要不要顺手改**：`index.html` 第 117 行的 `style="margin-top: 16px;"` 被 CSP 拦掉，线上这个间距实际从未生效；后台说明“系统只存哈希；明文兑换码仅在生成时显示一次。”与现状不符。另外 `core/static/admin.html` 是没人用的旧文件。
6. **列表只取最新 200 条**（原有行为）。筛选只在这 200 条里做；码多了以后旧码在列表里看不到，统计卡片不受影响。

另有两处行为变化，已按改动清单说明，不需要决定：删除不存在的码由 400 改为 404（两个产品都是）；生成接口参数错误由 500 改为 400。

## 文件

- 本目录：`RECEIPT.md`、`KIMI-DEPLOY.md`、`scripts/shots.py`
- `evidence/`：10 张截图、`ui-checks.json`、`pytest-full.txt`、`pytest-codes-kind.txt`
- 测试：`tests/test_codes_kind.py`
