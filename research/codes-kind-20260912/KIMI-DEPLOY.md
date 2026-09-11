# 任务书：上线“兑换码测试 / 正式分离”（codes-kind）

执行者：Kimi。所有命令在 Max 的 Mac 上执行（本机有仓库 `~/Projects/mcp-suite`，能免密 ssh 到服务器），服务器是 `root@114.215.188.109`。全程用同一个终端 shell，后面的步骤要用前面设的变量。预计 15 分钟，其中秋招服务停机约 30 秒，选访问少的时间做。

背景与改动说明见同目录 `RECEIPT.md`。本次替换 7 个文件：`core/store.py`、`core/server.py`、`core/admin.py`、`core/static/index.html`、`core/static/app.js`、`core/static/admin.js`、`core/static/admin.css`。不需要装依赖，不改 systemd 单元、nginx、cron、环境变量。

## 必须遵守

1. 任何一步的结果和“期望”不一致：**立即停下**，把这一步的完整输出交给 Max，不要自己修、不要跳过、不要继续。
2. 不读取、不输出 `access.sqlite3` 里的任何兑换码、hash 或 key。对库只执行本任务书写出来的查询（列名、触发器名、计数）。
3. 不输出、不记录任何 token；不要执行 `systemctl cat`、`env`、`cat` 服务配置之类会显示环境变量值的命令。
4. 只动这 7 个文件、一个暂存目录、一个代码备份目录、一份库文件副本。不删除任何已有文件（回滚第 R4 步除外，而且要先问 Max）。
5. 不重启 `mcp-suite-bench.service`，除非 Max 把下面的 `STOP_BENCH` 设成 `yes`。

## 前置条件

- **v4 已经部署到线上**，并且 v4 的部署收据写明了部署的是 `feat/v4` 的哪个提交。没有这个提交号：停。
- Max 已决定 `STOP_BENCH`（默认 `no`；`yes` 表示停机窗口里把 bench 一起停、一起启，库文件副本更稳妥）。

## 第 0 步：变量、分支检查、导出要上传的文件

```bash
R=~/Projects/mcp-suite
H=root@114.215.188.109
V4=__填v4部署收据里的提交号__
CK=feat/codes-kind
STOP_BENCH=no
TS=$(date +%Y%m%d-%H%M%S)
BK=/opt/mcp-suite/deploy/backup-pre-codes-kind-$TS
STG=/opt/mcp-suite/deploy/staging-codes-kind-$TS
DBK=/var/lib/mcp-suite/access.sqlite3.bak-pre-codes-kind-$TS
FILES="core/store.py core/server.py core/admin.py core/static/index.html core/static/app.js core/static/admin.js core/static/admin.css"
echo "TS=$TS"

cd $R && git rev-parse --verify "$V4^{commit}" && git rev-parse --short $CK
git merge-base --is-ancestor $V4 $CK && echo "CK contains V4"
git log --format='%s' $V4..$CK -- core qiuzhao bench deploy requirements.txt
```

期望：打印出两个提交号和 `CK contains V4`；最后一条命令**正好**输出下面三行（顺序不限）：

```
redeem page: early-bird label, price and tier highlight from /api/pricing
admin: formal/test codes, kind filter, server-side delete rule, admin action log; public GET /api/pricing
store: formal/test redemption codes, one-time kind migration, delete rule, early-bird state
```

`CK contains V4` 没出现，或多出任何一行：停。这说明线上的 v4 和本分支的基线不一致，需要开发把 `feat/codes-kind` rebase 到已部署的提交上并重跑测试。

```bash
S=$(mktemp -d /tmp/codes-kind-export-XXXXXX)
git -C $R archive $CK $FILES | tar -x -C $S
(cd $S && shasum -a 256 $FILES)
```

期望逐行等于下表（`feat/codes-kind` 46d8e88 起）。不一致：停。

| 文件 | sha256 |
|---|---|
| `core/store.py` | `03d4c8438e0e4893105bbb1bb2d1cfeb4290e5af7410e747c4114d667428da40` |
| `core/server.py` | `0fce6e80a97c981dc4d72e8c130ebcaeab1263a372bb7bbbd1240b83ec1a943b` |
| `core/admin.py` | `7ccc97fc11e4a00f90eabb413a4b97462aa872bb79aac91d9f40c31add59e690` |
| `core/static/index.html` | `3d3c11b8b0aa55c69001868d08c39a8f83352da6319a5966d329ccb51ecd5fb4` |
| `core/static/app.js` | `b049adce57dd526ad41e2bec2da4ae277ce4b51e33c935fa284a31e4b02f7d6e` |
| `core/static/admin.js` | `944ee83210188904865330a3ebdbe51497e5b094768d0390be346d553d9f1f2a` |
| `core/static/admin.css` | `a78e92054ee8c9cc9fec1039fde4f29cdd3e014def9f749cb0bddac10eb2e765` |

## 第 1 步：线上这 7 个文件必须还是已部署的 v4 版本

```bash
for f in $FILES; do printf '%s %s\n' "$(git -C $R show $V4:$f | shasum -a 256 | cut -d' ' -f1)" "$f"; done > $S/expected-v4.sha256
ssh $H "cd /opt/mcp-suite && sha256sum $FILES" | awk '{print $1" "$2}' > $S/online.sha256
diff $S/expected-v4.sha256 $S/online.sha256 && echo "ONLINE == V4"
ssh $H 'test -f /opt/mcp-suite/qiuzhao/v4_fields.py && echo v4_fields-present; grep -c "def jobs_stats" /opt/mcp-suite/core/server.py; systemctl is-active mcp-suite.service mcp-suite-bench.service'
```

期望：`ONLINE == V4`、`v4_fields-present`、grep 计数至少 1、两行 `active`。

唯一允许的例外：`diff` 只报 `core/store.py` 不同，且线上那一行是 main 的 `0348d335f28f8d11b81840e22aa25fedb7decb54f97745d0b227c90c5e3283c6`（v4 部署时没传 store.py）。这种情况可以继续，第 4、R2 步照常备份、恢复这份线上文件。

其他任何不同：停，把 `diff` 输出交给 Max。那表示 v4 部署之后又有人直接改过线上文件（例如豆包），需要开发先把线上改动合进本分支、重出任务书。

## 第 2 步：只读检查库结构（只看列名、触发器名、计数）

```bash
ssh $H 'runuser -u mcp-suite -- /opt/mcp-suite/.venv/bin/python -B -' <<'PY'
import sqlite3
db = sqlite3.connect("file:/var/lib/mcp-suite/access.sqlite3?mode=ro", uri=True, timeout=30)
q = lambda sql: db.execute(sql).fetchall()
print("columns", [r[1] for r in q("PRAGMA table_info(redemption_codes)")])
print("triggers", sorted(r[0] for r in q("SELECT name FROM sqlite_master WHERE type='trigger'")))
print("codes_total", q("SELECT count(*) FROM redemption_codes")[0][0])
print("codes_redeemed", q("SELECT count(*) FROM redemption_codes WHERE redeemed_at IS NOT NULL")[0][0])
print("codes_by_plan", q("SELECT plan, count(*) FROM redemption_codes GROUP BY 1 ORDER BY 1"))
print("keys_active", q("SELECT count(*) FROM api_keys WHERE disabled=0")[0][0])
PY
```

期望：`columns` 里**没有 `code_kind`**（正常是 `['code_hash', 'plan', 'created_at', 'redeemed_at', 'key_id', 'code_plain']`，多出别的列也可以）；`triggers` 里没有以 `redemption_codes_` 开头的名字。记下 `codes_total`、`codes_redeemed`、`keys_active`，第 7 步要对照。

出现 `code_kind` 列或 `redemption_codes_*` 触发器：停（有人提前改过库结构，迁移会跳过加列，结果无法预期）。

## 第 3 步：暂存副本、上传、离线 import 检查（线上服务不受影响）

```bash
ssh $H "mkdir -p $STG && cd /opt/mcp-suite && rsync -a --exclude=__pycache__ --exclude=data --exclude=logs --exclude=sources core qiuzhao bench $STG/ && du -sh $STG"
for f in $FILES; do rsync -a --checksum --chmod=F644 $S/$f $H:$STG/$f; done
ssh $H "cd $STG && sha256sum $FILES"
```

期望：最后的哈希逐行等于第 0 步的表。

```bash
for P in qiuzhao bench; do
ssh $H "cd $STG && T=\$(mktemp -d /tmp/ck-verify-XXXXXX) && PYTHONDONTWRITEBYTECODE=1 MCP_PRODUCT=$P MCP_DB_PATH=\$T/a.sqlite3 MCP_DIST_DB_PATH=\$T/d.db MCP_JOBS_PATH=\$T/none.json MCP_BENCH_PATH=\$T/none.json MCP_CALL_LOG_DIR=\$T/logs MCP_ADMIN_LOG_PATH=\$T/admin.jsonl /opt/mcp-suite/.venv/bin/python -W ignore - ; rm -rf \$T" <<'PY'
from starlette.testclient import TestClient
import core.server as s
c = TestClient(s.app)
r = c.get("/api/pricing")
body = r.json() if r.status_code == 200 else None
print(s.PRODUCT, "pricing", r.status_code, body and {k: body[k] for k in ("sold", "current_tier", "current_price_cny", "remaining")},
      r.headers.get("cache-control"))
print(s.PRODUCT, "admin_stats_without_token", c.get("/api/admin/stats").status_code)
print(s.PRODUCT, "admin_page_kind_filter", 'data-kind="formal"' in c.get("/admin").text)
ok = (r.status_code == 200 and body["sold"] == 0 and body["remaining"] == 10) if s.PRODUCT == "qiuzhao" else r.status_code == 404
print("RESULT", "OK" if ok else "FAIL")
PY
done
```

这一步只在 `/tmp` 下的临时空库上运行新代码，不碰线上库，不用任何 token。期望（`AuthlibDeprecationWarning` 两行提示可以忽略）：

```
qiuzhao pricing 200 {'sold': 0, 'current_tier': 1, 'current_price_cny': 29.9, 'remaining': 10} no-store
qiuzhao admin_stats_without_token 503
qiuzhao admin_page_kind_filter True
RESULT OK
bench pricing 404 None no-store
bench admin_stats_without_token 503
bench admin_page_kind_filter True
RESULT OK
```

出现 `Traceback` 或 `RESULT FAIL`：停。线上没有任何变化，执行 `ssh $H "rm -rf $STG"` 后交给 Max。

## 第 4 步：停服务、复制库文件、备份代码

从这里开始秋招服务停机，第 4–6 步连续做完。

```bash
ssh $H "systemctl stop mcp-suite.service; if [ '$STOP_BENCH' = yes ]; then systemctl stop mcp-suite-bench.service; fi; systemctl is-active mcp-suite.service mcp-suite-bench.service"
```

期望：第一行 `inactive`；第二行在 `STOP_BENCH=no` 时是 `active`，`yes` 时是 `inactive`。

库文件只用 `cp -p` 复制，不打开、不查询：

```bash
ssh $H "set -e; cd /var/lib/mcp-suite; for s in '' -wal -shm; do if [ -e access.sqlite3\$s ]; then cp -p access.sqlite3\$s $DBK\$s; fi; done; ls -l access.sqlite3 access.sqlite3-wal access.sqlite3-shm $DBK $DBK-wal $DBK-shm 2>/dev/null"
```

期望：每个存在的原文件都有一个同样大小的副本，属主 `mcp-suite`，权限 `-rw-------`。

```bash
ssh $H "set -e; mkdir -p $BK && cd /opt/mcp-suite && cp -p --parents $FILES $BK/ && cd $BK && find . -type f | sort | xargs sha256sum | tee SHA256SUMS"
```

期望：7 个文件，哈希与第 1 步 `$S/online.sha256` 相同。

## 第 5 步：替换 7 个文件

```bash
ssh $H "set -e; cd /opt/mcp-suite; for f in $FILES; do cp $STG/\$f \$f; done; sha256sum $FILES; stat -c '%U:%G %a %n' $FILES"
```

`cp` 覆盖已有文件，属主和权限沿用原文件。期望：哈希逐行等于第 0 步的表，权限都是 `644`。

## 第 6 步：启动（第一次启动时自动迁移）

```bash
ssh $H "systemctl start mcp-suite.service; sleep 6; systemctl is-active mcp-suite.service; journalctl -u mcp-suite.service --since '-2 min' --no-pager | tail -20"
ssh $H "if [ '$STOP_BENCH' = yes ]; then systemctl start mcp-suite-bench.service; sleep 4; fi; systemctl is-active mcp-suite-bench.service"
```

期望：两次都是 `active`；journal 里没有 `Traceback`。`mcp-suite` 不是 `active`：直接执行下面的“回滚”。

## 第 7 步：核验

```bash
ssh $H 'curl -s http://127.0.0.1:8768/health; echo; curl -s -D - http://127.0.0.1:8768/api/pricing; echo'
curl -s https://savegems.top/qiuzhao/api/pricing; echo
curl -s -o /dev/null -w 'admin_stats_without_token %{http_code}\n' https://savegems.top/qiuzhao/api/admin/stats
curl -s -o /dev/null -w 'bench_pricing %{http_code}\n' https://savegems.top/bench/api/pricing
curl -s -o /dev/null -w 'bench_health %{http_code}\n' https://savegems.top/bench/health
printf 'tier_list=%s app_js_pricing=%s admin_kind_filter=%s\n' \
  "$(curl -s https://savegems.top/qiuzhao/ | grep -c 'id="tier-list"')" \
  "$(curl -s https://savegems.top/qiuzhao/app.js | grep -c 'api/pricing')" \
  "$(curl -s https://savegems.top/qiuzhao/admin | grep -c 'data-kind="formal"')"
```

期望：

- health 为 `{"status":"ok", ...}`（第一次请求要建缓存，1–2 秒）。
- 本机 `/api/pricing` 的响应头有 `cache-control: no-store`；本机和公网两次返回的正文都含 `"sold":0`、`"early_bird_active":true`、`"current_tier":1`、`"current_price_cny":29.9`、`"remaining":10`，正文里没有 `QZ-`、`qz_`。
- `admin_stats_without_token 401`、`bench_pricing 404`、`bench_health 200`。
- `tier_list`、`app_js_pricing`、`admin_kind_filter` 都至少为 1。

库里只看聚合计数，不输出任何码：

```bash
ssh $H 'runuser -u mcp-suite -- /opt/mcp-suite/.venv/bin/python -B -' <<'PY'
import sqlite3
db = sqlite3.connect("file:/var/lib/mcp-suite/access.sqlite3?mode=ro", uri=True, timeout=30)
q = lambda sql: db.execute(sql).fetchall()
print("columns", [r[1] for r in q("PRAGMA table_info(redemption_codes)")])
print("triggers", sorted(r[0] for r in q("SELECT name FROM sqlite_master WHERE type='trigger'")))
print("by_kind", q("SELECT code_kind, count(*) FROM redemption_codes GROUP BY 1 ORDER BY 1"))
print("by_kind_redeemed", q("SELECT code_kind, count(*) FROM redemption_codes WHERE redeemed_at IS NOT NULL GROUP BY 1 ORDER BY 1"))
print("codes_total", q("SELECT count(*) FROM redemption_codes")[0][0])
print("keys_active", q("SELECT count(*) FROM api_keys WHERE disabled=0")[0][0])
PY
```

期望：

- `columns` 比第 2 步多了最后一个 `code_kind`。
- `triggers` 包含 `redemption_codes_formal_kept`、`redemption_codes_kind_fixed`、`redemption_codes_kind_required`。
- `by_kind` 只有一行 `('test', N)`，N 等于第 2 步的 `codes_total`；没有 `formal`，没有 `None`。
- `by_kind_redeemed` 只有 `('test', M)`，M 不小于第 2 步的 `codes_redeemed`（第 2 步之后有人兑换会变大；为 0 时是空列表）。
- `codes_total` 等于第 2 步；`keys_active` 不小于第 2 步。

请 Max 自己用浏览器看（Kimi 不经手管理员令牌）：兑换页价格卡显示“前 10 名早鸟价 · 剩 10 个名额”、¥29.9、标准价 ¥59.9；管理后台登录后正式码 0、测试码等于 N、早鸟进度“已售 0 / 当前第 1 档，剩 10 个名额”，生成区“类别”默认是“测试码”。

## 第 8 步：清理、交收据

```bash
ssh $H "rm -rf $STG; ls -d /opt/mcp-suite/deploy/staging-codes-kind-* 2>/dev/null || echo staging-removed"
rm -rf $S
echo "BK=$BK DBK=$DBK"
```

保留 `$BK`（代码备份）和 `$DBK*`（库文件副本），回滚要用。收据交给 Max：`TS`、`BK`、`DBK` 的值，第 0–7 步的输出，停机和启动的时间。以上命令都不会输出 token、兑换码或 key，原样粘贴即可。

## 回滚

第 6、7 步任何一项不符合期望，或 Max 要求回滚时执行。需要同一个 shell 里的 `$BK`、`$FILES`、`$STOP_BENCH`；换了 shell 就先按收据里的值重新设这几个变量。

R1. 停服务并恢复 7 个文件：

```bash
ssh $H "set -e; systemctl stop mcp-suite.service; if [ '$STOP_BENCH' = yes ]; then systemctl stop mcp-suite-bench.service; fi; cd /opt/mcp-suite; for f in $FILES; do cp -p $BK/\$f \$f; done; sha256sum $FILES"
```

期望：哈希等于第 1 步的 `$S/online.sha256`（`$S` 已删的话，对照 `$BK/SHA256SUMS`）。

R2. 删掉“插入必须带类别”这一个触发器（否则 v4 代码生成兑换码会失败）：

```bash
ssh $H 'runuser -u mcp-suite -- /opt/mcp-suite/.venv/bin/python -B -' <<'PY'
import sqlite3
db = sqlite3.connect("/var/lib/mcp-suite/access.sqlite3", timeout=30)
db.execute("DROP TRIGGER IF EXISTS redemption_codes_kind_required")
db.commit()
print("triggers", sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")))
PY
```

期望：`triggers` 里没有 `redemption_codes_kind_required`。

R3. 启动并确认：

```bash
ssh $H "systemctl start mcp-suite.service; sleep 6; systemctl is-active mcp-suite.service; if [ '$STOP_BENCH' = yes ]; then systemctl start mcp-suite-bench.service; sleep 4; fi; systemctl is-active mcp-suite-bench.service; curl -s http://127.0.0.1:8768/health; echo; curl -s -o /dev/null -w 'pricing %{http_code}\n' http://127.0.0.1:8768/api/pricing"
```

期望：两行 `active`，health 为 ok，`pricing 404`（v4 没有这个接口），兑换页恢复 v4 写死的价格。

说明：

- `code_kind` 列、`redemption_codes_kind_fixed`、`redemption_codes_formal_kept` 两个触发器留在库里。v4 代码插入时写明了列名，不受这一列影响；“正式码不许删”在回滚期间继续保护已卖出的正式码。要完全回到部署前的结构，再以 mcp-suite 身份执行 `DROP TRIGGER IF EXISTS redemption_codes_kind_fixed` 和 `DROP TRIGGER IF EXISTS redemption_codes_formal_kept`，列不用删。
- 回滚期间用 v4 生成的码没有类别，以后再部署本版本时会自动记为测试码。那段时间如果卖出过码，重新部署前告诉开发。
- 数据库不需要恢复：迁移只加了一列、把已有码记为测试码、建了触发器，没有删改其他数据。

R4. 只有库文件损坏时才用库文件副本，而且**必须先得到 Max 同意**：这样会丢掉部署之后的所有兑换、新 key 和调用计数。

```bash
ssh $H "set -e; systemctl stop mcp-suite.service mcp-suite-bench.service; cd /var/lib/mcp-suite; rm -f access.sqlite3-wal access.sqlite3-shm; cp -p $DBK access.sqlite3; for s in -wal -shm; do if [ -e $DBK\$s ]; then cp -p $DBK\$s access.sqlite3\$s; fi; done; systemctl start mcp-suite.service mcp-suite-bench.service; sleep 6; systemctl is-active mcp-suite.service mcp-suite-bench.service"
```

用库文件副本恢复后：如果代码还是本版本，启动时会重新迁移（副本里的码全部记为测试码）；如果代码已按 R1 恢复成 v4，副本里本来就没有类别列和触发器，不需要再做 R2。
