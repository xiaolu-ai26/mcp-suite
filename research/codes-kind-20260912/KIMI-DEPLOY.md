# 任务书：上线“兑换码测试 / 正式分离”（codes-kind，给 Kimi Code）

写于 2026-09-12，由 codes-kind 执行会话准备；**Max 批准后**才开始执行，而且只能在 v4 部署（`research/qiuzhao-v4-impl/KIMI-DEPLOY.md`）成功之后执行。

## 目标与范围

- 把 `feat/codes-kind` 的 7 个文件部署到 `root@114.215.188.109` 的 `mcp-suite.service`：兑换码分正式 / 测试，正式码不能删，删已兑换的测试码同时作废它的 key，早鸟名额只按已兑换的正式码计，兑换页从 `GET /api/pricing` 读价格和剩余名额。背景见同目录 `RECEIPT.md`。
- 前提：线上是 v4 任务书写定的部署提交 **`2f0f070`**。本分支 = `2f0f070` + 本次 3 个代码提交（后面还有测试和文档提交，不部署），第 1 步会核对。
- **只替换下表 7 个文件**；不装依赖，不改 systemd 单元、nginx、cron、环境变量。默认**只停 / 启 `mcp-suite.service`**。
- 本地：仓库 `~/Projects/mcp-suite`（`feat/codes-kind` 分支就在这个仓库里，用 `git archive` 取文件，不依赖任何工作副本的文件状态）。不进入其他工作副本。
- 服务器：代码 `/opt/mcp-suite`（venv `.venv`），数据 `/var/lib/mcp-suite`；qiuzhao 服务监听 `127.0.0.1:8768`，公网 `https://savegems.top/qiuzhao/`。
- 全程不需要任何真实 key、兑换码或管理员令牌。某一步看起来需要它们：停下回报。
- 预计 15–20 分钟，其中秋招服务停机约 30 秒。北京时间 05:55–07:30 不要开始或进行（每天 06:10 有采集任务）。

| 文件 | 目标 sha256（`feat/codes-kind` 4cabf1d 起不变） | 线上现状应为（= v4 `2f0f070`） |
|---|---|---|
| `core/store.py` | `03d4c8438e0e4893105bbb1bb2d1cfeb4290e5af7410e747c4114d667428da40` | `a43fe29325064352bbe69028359563d6dbc9dc3e162c7663acc94110e7f43c07` |
| `core/server.py` | `0fce6e80a97c981dc4d72e8c130ebcaeab1263a372bb7bbbd1240b83ec1a943b` | `09e831800ab674f36e0e855b22ec1befd261d71133b6c78d55c4d73e2ab6f7c8` |
| `core/admin.py` | `7ccc97fc11e4a00f90eabb413a4b97462aa872bb79aac91d9f40c31add59e690` | `5675873a56eeb2a6d398083f775083030b29a41406cefd650e9d8a33d1c9c792` |
| `core/static/index.html` | `3d3c11b8b0aa55c69001868d08c39a8f83352da6319a5966d329ccb51ecd5fb4` | `31db55d727094bd187178998d910ac7e862f717f440c19db66dac14a68176bd3` |
| `core/static/app.js` | `b049adce57dd526ad41e2bec2da4ae277ce4b51e33c935fa284a31e4b02f7d6e` | `cd30fbfd46544fefd28bcb117b2f540f4e9ed826f41ecbc4ccb3f0e050e9aa15` |
| `core/static/admin.js` | `944ee83210188904865330a3ebdbe51497e5b094768d0390be346d553d9f1f2a` | `afd34e781cfafccd4b7640a79b9b44b68d3f9ec3b3d096faa06e8a7811fe5b56` |
| `core/static/admin.css` | `a78e92054ee8c9cc9fec1039fde4f29cdd3e014def9f749cb0bddac10eb2e765` | `15c775cef945e9818d682544cd55c8b4557b759303a7cadeeaca842c9f03458c` |

## 0. 硬性禁止（每一步都适用）

1. 不读取、不输出 `/var/lib/mcp-suite/access.sqlite3`（含 `-wal`、`-shm` 和所有备份）里的任何兑换码、hash、key。对库只允许执行第 2b、7b 步写出的只读查询（列名、触发器名、计数）和回滚 R2 的删触发器语句；备份库文件只用 `cp -p`，不用 `sqlite3`、`strings`、`cat`、`head`、`xxd`。不读 `distribution.db`。
2. 不输出任何 token：不运行 `systemctl cat`、`env`，`systemctl show` 只允许 `-p ActiveEnterTimestamp`，不 `cat` 任何 `/etc/systemd/system/mcp-suite*`。
3. 服务器上只写这些位置：7 个部署文件、`/opt/mcp-suite/deploy/backup-pre-codes-kind-<TS>/`（含库文件副本）、`/opt/mcp-suite/deploy/staging-codes-kind-<TS>/`、`/tmp/ck-verify-*`。`STOP_BENCH=no` 时不 stop / start / restart `mcp-suite-bench.service`；任何情况下不碰 nginx、cron、`jobs.json` 和其他站点。
4. 命令输出里如果出现形如 `qz_…`、`bm_…` 的 key、`QZ-…`、`BM-…` 的兑换码或 `Bearer …`，不要转述，写成 `[redacted]`。本任务书的命令本身不会输出它们。
5. 任何一步的结果和“期望”不一致：停下；已经停过服务或替换过文件的，按“回滚”做；然后回报。不要自己改代码、改脚本或换别的做法。
6. 不 push，不 merge，不 rebase，不改任何分支。

## 变量（每一步开始前都先执行；新开 shell 也一样）

本地命令在 bash 和 zsh 里都能照抄：本地命令里的文件清单都写成明文；`$FILES` 只出现在发给服务器的双引号字符串里，由服务器上的 bash 分词。

```bash
R=~/Projects/mcp-suite; H=root@114.215.188.109
V4=2f0f070                       # 线上的 v4 部署提交，以 v4 部署收据为准
CK=feat/codes-kind
STOP_BENCH=no                    # Max 决定；yes = 停机窗口里 bench 一起停、一起启
PKG=/tmp/codes-kind-pkg          # 本地部署包
FILES="core/store.py core/server.py core/admin.py core/static/index.html core/static/app.js core/static/admin.js core/static/admin.css"
ENVF=/tmp/codes-kind-deploy.env; [ -f $ENVF ] && . $ENVF    # 第 3 步写入 TS、BK、STG
```

## 1. 前置条件（只读；任何一项不满足：停下回报，后面都不做）

**1a. v4 已部署、两个服务在跑、时间合适。**

```bash
ssh $H 'TZ=Asia/Shanghai date "+%F %T"; test -f /opt/mcp-suite/qiuzhao/v4_fields.py && echo V4-FIELDS-PRESENT; grep -c "def jobs_stats" /opt/mcp-suite/core/server.py; systemctl is-active mcp-suite.service mcp-suite-bench.service; systemctl show -p ActiveEnterTimestamp mcp-suite-bench.service'
```

期望：北京时间不在 05:55–07:30；`V4-FIELDS-PRESENT`；计数至少 1；`active active`。记下 bench 的 `ActiveEnterTimestamp`，第 6 步要对比。

另外核对 v4 部署收据（`research/qiuzhao-v4-impl/DEPLOY-RECEIPT.md`，在 main 上）：部署结果是“成功”，部署提交是 `2f0f070`。收据写的提交不是 `2f0f070`：把上面的 `V4=` 改成收据里的提交号再做 1b（1b 会判断能不能继续）。没有收据，或 v4 失败已回滚：停。收据写着静态页来源是“线上 <时间> 版 + 6 处替换”：照常做第 2a 步，那一步会发现 `app.js` 与 `2f0f070` 不同并停下。

**1b. 本分支正好是 V4 加本次改动。**

```bash
git -C $R cat-file -e "$V4^{commit}" && echo V4-FOUND
git -C $R merge-base --is-ancestor $V4 $CK && echo CK-CONTAINS-V4
git -C $R log --format='%s' $V4..$CK -- core qiuzhao bench deploy requirements.txt
```

期望：`V4-FOUND`、`CK-CONTAINS-V4`；最后一条命令**正好**输出下面三行（顺序不限）：

```
redeem page: early-bird label, price and tier highlight from /api/pricing
admin: formal/test codes, kind filter, server-side delete rule, admin action log; public GET /api/pricing
store: formal/test redemption codes, one-time kind migration, delete rule, early-bird state
```

缺 `CK-CONTAINS-V4` 或多出任何一行：停。说明线上的 v4 与本分支的基线不一致，需要开发把 `feat/codes-kind` rebase 到已部署的提交上、重跑测试、重出任务书。

**1c. 从分支生成部署包（不用工作区里的文件）。**

```bash
rm -rf $PKG && mkdir -p $PKG
git -C $R archive $CK core/store.py core/server.py core/admin.py core/static/index.html core/static/app.js core/static/admin.js core/static/admin.css | tar -x -C $PKG
(cd $PKG && shasum -a 256 core/store.py core/server.py core/admin.py core/static/index.html core/static/app.js core/static/admin.js core/static/admin.css)
```

期望：7 个值与上表“目标 sha256”逐一相同。

## 2. 核对线上（只读）

**2a. 线上这 7 个文件必须还是 V4 版本。**

```bash
for f in core/store.py core/server.py core/admin.py core/static/index.html core/static/app.js core/static/admin.js core/static/admin.css; do printf '%s %s\n' "$(git -C $R show "${V4}:${f}" | shasum -a 256 | cut -d' ' -f1)" "$f"; done > $PKG/expected-v4.sha256
ssh $H "cd /opt/mcp-suite && sha256sum $FILES" | awk '{print $1" "$2}' > $PKG/online.sha256
cat $PKG/online.sha256; diff $PKG/expected-v4.sha256 $PKG/online.sha256 && echo ONLINE-EQUALS-V4
```

期望：`ONLINE-EQUALS-V4`（`V4=2f0f070` 时就是上表“线上现状应为”那一列）。任何一个不同：停，把 `diff` 输出交给 Max。那表示 v4 部署之后线上文件又被改过（例如豆包直接改页面），或 v4 部署时静态页用的是线上新版；需要开发把线上内容合进本分支、重出任务书。

**2b. 库结构（只看列名、触发器名、计数）。**

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

## 3. 暂存副本、上传、离线 import 检查（线上服务和线上文件都不动）

```bash
TS=$(date +%Y%m%d-%H%M%S)
printf 'TS=%s\nBK=/opt/mcp-suite/deploy/backup-pre-codes-kind-%s\nSTG=/opt/mcp-suite/deploy/staging-codes-kind-%s\n' $TS $TS $TS > $ENVF; . $ENVF; cat $ENVF
ssh $H "set -e; mkdir -p $STG; cd /opt/mcp-suite; rsync -a --exclude=__pycache__ --exclude=data --exclude=logs --exclude=sources core qiuzhao bench $STG/; du -sh $STG"
for f in core/store.py core/server.py core/admin.py core/static/index.html core/static/app.js core/static/admin.js core/static/admin.css; do scp -q $PKG/$f $H:$STG/$f || echo "SCP-FAILED $f"; done
ssh $H "cd $STG && sha256sum $FILES"
```

期望：没有 `SCP-FAILED`；7 个值等于目标 sha256。暂存目录是线上代码的完整副本再覆盖 7 个文件，下面在它上面试运行新代码。

```bash
for P in qiuzhao bench; do
ssh $H "cd $STG && T=\$(mktemp -d /tmp/ck-verify-XXXXXX) && PYTHONDONTWRITEBYTECODE=1 MCP_PRODUCT=$P MCP_DB_PATH=\$T/a.sqlite3 MCP_DIST_DB_PATH=\$T/d.db MCP_JOBS_PATH=\$T/none.json MCP_BENCH_PATH=\$T/none.json MCP_CALL_LOG_DIR=\$T/logs MCP_ADMIN_LOG_PATH=\$T/admin.jsonl /opt/mcp-suite/.venv/bin/python -W ignore - ; rm -rf \$T; ls -d /tmp/ck-verify-* 2>/dev/null || echo tmp-cleaned" <<'PY'
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

这里只在 `/tmp` 下的临时空库上运行新代码，不碰线上库，不用任何 token（没配管理员令牌，所以后台接口是 503）。期望（`AuthlibDeprecationWarning` 两行提示可以忽略）：

```
qiuzhao pricing 200 {'sold': 0, 'current_tier': 1, 'current_price_cny': 29.9, 'remaining': 10} no-store
qiuzhao admin_stats_without_token 503
qiuzhao admin_page_kind_filter True
RESULT OK
tmp-cleaned
bench pricing 404 None no-store
bench admin_stats_without_token 503
bench admin_page_kind_filter True
RESULT OK
tmp-cleaned
```

出现 `Traceback` 或 `RESULT FAIL`：停，执行 `ssh $H "rm -rf $STG"`，回报（线上什么都没变）。

## 4. 停服务、备份代码、复制库文件（从这里开始停机，4–6 步连续做完）

```bash
ssh $H "systemctl stop mcp-suite.service; if [ '$STOP_BENCH' = yes ]; then systemctl stop mcp-suite-bench.service; fi; TZ=Asia/Shanghai date '+stopped %F %T'; systemctl is-active mcp-suite.service mcp-suite-bench.service"
```

期望：`mcp-suite` 一行是 `inactive`；bench 一行在 `STOP_BENCH=no` 时是 `active`，`yes` 时是 `inactive`。

```bash
ssh $H "set -e; mkdir -p $BK; cd /opt/mcp-suite; cp -p --parents $FILES $BK/; cd $BK; sha256sum $FILES | tee SHA256SUMS"
ssh $H "set -e; install -d -m 700 $BK/data; for f in access.sqlite3 access.sqlite3-wal access.sqlite3-shm; do if [ -e /var/lib/mcp-suite/\$f ]; then cp -p /var/lib/mcp-suite/\$f $BK/data/; fi; done; ls -l $BK/data | awk 'NR>1{print \$1,\$3,\$4,\$5,\$9}'; ls -l /var/lib/mcp-suite/access.sqlite3 /var/lib/mcp-suite/access.sqlite3-wal /var/lib/mcp-suite/access.sqlite3-shm 2>/dev/null | awk '{print \$1,\$3,\$4,\$5,\$9}'"
```

期望：`SHA256SUMS` 的 7 个值等于第 2a 步的 `online.sha256`；`$BK/data/` 里每个副本的大小、属主（`mcp-suite mcp-suite`）、权限（`-rw-------`）都与后面列出的原文件相同。只看文件名和大小，不打开。

## 5. 替换 7 个文件

```bash
ssh $H "set -e; cd /opt/mcp-suite; for f in $FILES; do install -m 644 $STG/\$f \$f; done; sha256sum $FILES; stat -c '%U:%G %a %n' $FILES"
```

期望：7 个值等于目标 sha256；每个文件 `root:root 644`（与 v4 的安装方式一致）。任何一个不同：按“回滚”R1 起做。

## 6. 启动（第一次启动时自动迁移）

```bash
ssh $H 'systemctl start mcp-suite.service; sleep 6; TZ=Asia/Shanghai date "+started %F %T"; systemctl is-active mcp-suite.service; journalctl -u mcp-suite.service --since "-3 min" --no-pager | tail -20 | sed -E "s/(qz|bm)_[A-Za-z0-9_-]{8,}/\1_[redacted]/g; s/(QZ|BM)-[0-9A-Fa-f]{8,}/\1-[redacted]/g; s/[Bb]earer +[^ ]+/Bearer [redacted]/g"'
ssh $H "if [ '$STOP_BENCH' = yes ]; then systemctl start mcp-suite-bench.service; sleep 4; fi; systemctl is-active mcp-suite-bench.service; systemctl show -p ActiveEnterTimestamp mcp-suite-bench.service"
```

期望：`mcp-suite` 为 `active`，journal 里没有 `Traceback`、`Error`；bench 为 `active`；`STOP_BENCH=no` 时 bench 的 `ActiveEnterTimestamp` 与第 1a 步相同。`mcp-suite` 不是 `active`：按“回滚”R1 起做。

## 7. 核验

**7a. 接口和页面。**

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
- 本机 `/api/pricing` 响应头有 `cache-control: no-store`；本机和公网两次正文都含 `"sold":0`、`"early_bird_active":true`、`"current_tier":1`、`"current_price_cny":29.9`、`"remaining":10`，正文里没有 `QZ-`、`qz_`。
- `admin_stats_without_token 401`、`bench_pricing 404`、`bench_health 200`。
- `tier_list`、`app_js_pricing`、`admin_kind_filter` 都至少为 1。

不符合：按“回滚”R1 起做。

**7b. 库里只看聚合计数，不输出任何码。**

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

- `columns` 比第 2b 步多了最后一个 `code_kind`。
- `triggers` 包含 `redemption_codes_formal_kept`、`redemption_codes_kind_fixed`、`redemption_codes_kind_required`。
- `by_kind` 只有一行 `('test', N)`，N 等于第 2b 步的 `codes_total`；没有 `formal`，没有 `None`。
- `by_kind_redeemed` 只有 `('test', M)`，M 不小于第 2b 步的 `codes_redeemed`（第 2b 步到停机之间有人兑换会变大；为 0 时是空列表）。
- `codes_total` 等于第 2b 步；`keys_active` 不小于第 2b 步。

不符合：停下回报，服务保持运行（库只加了一列和触发器，没有删改数据），由 Max 决定是否回滚。

**7c. 请 Max 用浏览器看（Kimi 不经手管理员令牌）。** 兑换页价格卡是“前 10 名早鸟价 · 剩 10 个名额”、¥29.9、标准价 ¥59.9 删除线；管理后台登录后正式码 0、测试码 N、早鸟进度“已售 0 / 当前第 1 档，剩 10 个名额”，生成区“类别”默认“测试码”。

## 8. 成功后清理

```bash
ssh $H "rm -rf $STG; ls -d $BK"
rm -rf $PKG $ENVF
```

备份目录 `$BK`（含 `data/` 库文件副本）保留，回滚要用。不提交、不写仓库；按第 9 节格式回复 Max。

## 回滚

第 5–7a 步任何一项不符合期望，或 Max 要求回滚时执行。先执行“变量”那一段（会从 `$ENVF` 读回 `TS`、`BK`、`STG`）；`$ENVF` 已删的话，按回复里的 `TS` 手工设 `BK=/opt/mcp-suite/deploy/backup-pre-codes-kind-<TS>`、`STG=/opt/mcp-suite/deploy/staging-codes-kind-<TS>`。

R1. 停服务，恢复 7 个文件：

```bash
ssh $H "set -e; systemctl stop mcp-suite.service; if [ '$STOP_BENCH' = yes ]; then systemctl stop mcp-suite-bench.service; fi; cd /opt/mcp-suite; for f in $FILES; do cp -p $BK/\$f \$f; done; sha256sum $FILES; rm -rf $STG"
```

期望：7 个值等于 `$BK/SHA256SUMS`（即 v4 版本）。

R2. 删掉“插入必须带类别”这一个触发器（否则 v4 代码生成兑换码会失败；新代码没启动过时它不存在，这条语句什么也不做）：

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

期望：两行 `active`，health 为 ok，`pricing 404`（v4 没有这个接口）；兑换页回到 v4 写死的价格。

说明：

- `code_kind` 列和 `redemption_codes_kind_fixed`、`redemption_codes_formal_kept` 两个触发器留在库里。v4 代码插入时写明了列名，不受这一列影响；“正式码不许删”在回滚期间继续保护已卖出的正式码（v4 后台删到正式码会报错，删不掉）。要完全回到部署前的结构，再以 mcp-suite 身份执行 `DROP TRIGGER IF EXISTS redemption_codes_kind_fixed` 和 `DROP TRIGGER IF EXISTS redemption_codes_formal_kept`，列不用删。
- 回滚期间用 v4 生成的码没有类别，以后再部署本版本时会自动记为测试码。那段时间如果卖出过码，重新部署前告诉开发。
- 数据库不需要恢复：迁移只加了一列、把已有码记为测试码、建了触发器，没有删改其他数据。

R4. 只有库文件损坏时才用 `$BK/data/` 里的副本，而且**必须先得到 Max 同意**：会丢掉部署之后的所有兑换、新 key 和调用计数；这一步两个服务都要停。

```bash
ssh $H "set -e; systemctl stop mcp-suite.service mcp-suite-bench.service; cd /var/lib/mcp-suite; rm -f access.sqlite3-wal access.sqlite3-shm; for f in access.sqlite3 access.sqlite3-wal access.sqlite3-shm; do if [ -e $BK/data/\$f ]; then cp -p $BK/data/\$f \$f; fi; done; systemctl start mcp-suite.service mcp-suite-bench.service; sleep 6; systemctl is-active mcp-suite.service mcp-suite-bench.service"
```

用副本恢复后：如果代码还是本版本，启动时会重新迁移（副本里的码全部记为测试码）；如果代码已按 R1 恢复成 v4，副本里本来就没有类别列和触发器，不需要再做 R2。

## 9. 最后回复的格式

```
部署：成功 / 失败已回滚（第 N 步：原因）/ 未开始（哪一项前置条件、实际输出）
提交：V4 <hash>；codes-kind <hash>（7 个文件来自这里）
文件：部署前 7 个 sha256 = V4 / 部署后 = 目标，或列出不一致的
库：2b codes_total / codes_redeemed / keys_active；7b by_kind / by_kind_redeemed / triggers
核验：/api/pricing（sold、current_tier、current_price_cny、remaining、cache-control）；admin 401；bench 404 / 200；页面三个计数
停机：stopped / started 时间（北京时间）；STOP_BENCH=…；bench ActiveEnterTimestamp 前后
备份：/opt/mcp-suite/deploy/backup-pre-codes-kind-<TS>（含 data/access.sqlite3 副本，未读取）
异常与需要 Max 决定：…（没有写“无”）
```
