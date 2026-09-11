# 秋招 MCP v4 部署任务书（给 Kimi Code）

写于 2026-09-12，由 v4 执行会话准备；**Max 批准后**才开始执行。

## 目标与范围

- 把 v4 接口（`jobs_search` / `jobs_stats` / `jobs_detail`；三档匹配，同一档内按匹配的具体程度排序）部署到 `root@114.215.188.109` 的 `mcp-suite.service`。
- **部署提交：`feat/v4 @ 2f0f070`**。之后的提交（本任务书所在的提交及以后）只改 `research/` 下的文档、证据和部署脚本，不改任何部署文件，第 1 步会核对这一点。
- **只替换下表 6 个文件**，服务器上别的文件都不动；**只重启 `mcp-suite.service`**。
- 本地：feat/v4 工作副本 `~/Projects/mcp-suite-wt-v4`，main 工作副本 `~/Projects/mcp-suite`。**不要进入 `~/Projects/mcp-suite-wt-collector`。**
- 服务器：代码 `/opt/mcp-suite`（venv `.venv`），数据 `/var/lib/mcp-suite`。qiuzhao 服务 `mcp-suite.service` 监听 `127.0.0.1:8768`，公网 `https://savegems.top/qiuzhao/`。`mcp-suite-bench.service` 不动。
- 全程不需要任何真实 key、兑换码或管理员令牌。某一步看起来需要它们：停下回报。
- 预计 20–30 分钟。北京时间 05:55–07:30 不要开始或进行（每天 06:10 有采集任务）。

| 文件 | 目标 sha256（2f0f070） | 线上现状应为（= main 1127cf7，2026-09-12 01:02 已核对） |
|---|---|---|
| `core/server.py` | `09e831800ab674f36e0e855b22ec1befd261d71133b6c78d55c4d73e2ab6f7c8` | `08143798a78ca401be294c7d3425b7f6398cd200cf93bf57b12a0e31f191dccd` |
| `qiuzhao/tools.py` | `5fe3d3d60e06b21ea5ea6ae73f327da6a2c8ba976859d8087a7e6bedeecc9d5b` | `77ffdb613a746636314e31786b2a451b57dd061670abba2542695e406ece0d52` |
| `qiuzhao/v4_fields.py`（新文件） | `ceb411808794ee6d742c73e4143cb15ea0b7ee52690e5d277e37368e80c25bd7` | 不存在 |
| `core/store.py` | `a43fe29325064352bbe69028359563d6dbc9dc3e162c7663acc94110e7f43c07` | `0348d335f28f8d11b81840e22aa25fedb7decb54f97745d0b227c90c5e3283c6` |
| `core/static/guide.html` | `a1e03aeaaf915bb72523f6a4cc3058fd66bc49804f367e7541d8cebec12813ec` | `4afa8338dd26965607f47386dcd8520dae1ac9d1b0a5d588be7faa075839b4d4` |
| `core/static/app.js` | `cd30fbfd46544fefd28bcb117b2f540f4e9ed826f41ecbc4ccb3f0e050e9aa15` | `cb3d5e92940d90a28860c965b5e40803ef252077f04c3f43838a20eef8b4af10` |

两个静态页只有在第 2 步发现线上已被改过时才换成“线上最新版 + 6 处替换”，目标哈希随之改为那两份文件的哈希，并写进收据。

## 0. 硬性禁止（每一步都适用）

1. **不读取、不输出**：`/var/lib/mcp-suite/access.sqlite3`（含 `-wal`、`-shm` 和所有 `access.sqlite3.bak*`）、`/var/lib/mcp-suite/distribution.db`、systemd 的 `override.conf`、任何 token、API key、兑换码。不运行 `systemctl cat`、`systemctl show`（只允许 `-p ActiveEnterTimestamp`）、`systemctl show -p Environment`，不 `cat` 任何 `/etc/systemd/system/mcp-suite*.service.d/*`。备份 `access.sqlite3` 只用 `cp -p`，不用 `sqlite3`、`strings`、`cat`、`head`、`xxd`、`file`。
2. **不碰** `mcp-suite-bench.service`（不 restart、stop、reload）、nginx（不 reload、不改配置）和服务器上的其他站点、服务、cron、`jobs.json`。
3. 服务器上只写这些位置：6 个部署文件、`/opt/mcp-suite/deploy/backup-pre-v4-<TS>/`、`/opt/mcp-suite/deploy/v4-pkg-<TS>/`、`/tmp/v4-verify-*`、`/tmp/v4-e2e-*`、`/var/lib/mcp-suite/call_logs/`（只建目录）。
4. 本地不读 `private/`、`*.sqlite3*`、文件名带 receipt 的 json、`*.mcp.json`、`tests/e2e_bench_online.py`。
5. 命令输出里如果出现形如 `qz_…`、`bm_…` 的 key、`QZ-…`、`BM-…` 的兑换码或 `Bearer …`，不要转述，写成 `[redacted]`。
6. 任何一步的结果和“期望”不一致：停下；已经替换过文件的，按第 11 步回滚；然后回报。不要自己改代码、改脚本或换别的做法。
7. 不 push，不改 main 以外的分支，不 rebase、不 force。

## 变量（每一步开始前都先执行；新开 shell 也一样）

命令在 bash 和 zsh 里都能照抄执行：本地命令不依赖对 `$FILES`、`$OLD` 分词（zsh 默认不分词，本地文件列表都写成了明文），这两个变量只出现在发给服务器的双引号字符串里，由服务器上的 bash 展开。

```bash
W=~/Projects/mcp-suite-wt-v4; M=~/Projects/mcp-suite; H=root@114.215.188.109
C=2f0f070                                           # 部署提交
PKG=$W/research/qiuzhao-v4-impl/tmp/deploy-pkg      # 本地部署包（tmp/ 已被 .gitignore 忽略）
FILES="core/server.py qiuzhao/tools.py qiuzhao/v4_fields.py core/store.py core/static/guide.html core/static/app.js"
OLD="core/server.py qiuzhao/tools.py core/store.py core/static/guide.html core/static/app.js"   # 线上已有、会被替换的 5 个
ENVF=$W/research/qiuzhao-v4-impl/tmp/deploy.env; [ -f $ENVF ] && . $ENVF   # 第 4 步写入 TS、BK、STG
```

## 1. 前置条件（只读；任何一项不满足：停下回报，后面都不做）

**1a. 采集部署已完成，且现在没有采集在跑。**

```bash
ssh $H 'TZ=Asia/Shanghai date "+%F %T"; ps -eo pid,etimes,args | grep -E "[c]ollector-daily|[q]iuzhao[./]collector|[a]uto_collect|[q]iuzhao[./]normalize|[b]uild_normalize_tables" || echo NO-COLLECTOR-PROCESS; flock -n /var/lib/mcp-suite/collector.lock -c "echo LOCK-FREE" || echo LOCK-HELD'
ssh $H '/opt/mcp-suite/.venv/bin/python -' <<'PY'
import datetime as dt, json
s = json.load(open("/var/lib/mcp-suite/cron-status.json"))
done = dt.datetime.fromisoformat(s["completed_at"])          # 写的是 UTC，例如 2026-09-11T16:52:46+00:00
cut = dt.datetime.fromisoformat("2026-09-12T00:00:00+08:00")
print("completed_at(北京)", done.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
      "success", s.get("success"), "steps", s.get("steps"))
print("PRECONDITION", "OK" if done > cut else "FAIL")
PY
```

期望：北京时间不在 05:55–07:30；`NO-COLLECTOR-PROCESS`；`LOCK-FREE`；`PRECONDITION OK`。`completed_at` 是 UTC，必须按时区比较，不能按字符串比（2026-09-12 01:02 核对时为 `2026-09-11T16:52:46+00:00`，即北京时间 00:52:46，`success true`）。`success` 和 `steps` 只记进收据，不作为停下的条件。

**1b. 本地仓库。**

```bash
git -C $W branch --show-current; git -C $W log -1 --format='%h %s'
git -C $W merge-base --is-ancestor $C HEAD && echo C-IN-BRANCH
git -C $W diff --quiet $C HEAD -- core qiuzhao tests && echo NO-CODE-CHANGE-SINCE-C
git -C $W status --porcelain -- core qiuzhao tests; echo "(以上应为空)"
git -C $W merge-base --is-ancestor main feat/v4 && echo MAIN-IS-ANCESTOR || echo MAIN-NOT-ANCESTOR
```

期望：`feat/v4`；`C-IN-BRANCH`；`NO-CODE-CHANGE-SINCE-C`；core、qiuzhao、tests 没有未提交的改动；`MAIN-IS-ANCESTOR`。出现 `MAIN-NOT-ANCESTOR` 时仍可部署，但要在回复里写明，第 12 步的快进会停下。

**1c. 从部署提交生成部署包（不用工作区里的文件）。**

```bash
rm -rf $PKG && mkdir -p $PKG
git -C $W archive $C core/server.py qiuzhao/tools.py qiuzhao/v4_fields.py core/store.py core/static/guide.html core/static/app.js | tar -x -C $PKG
(cd $PKG && shasum -a 256 core/server.py qiuzhao/tools.py qiuzhao/v4_fields.py core/store.py core/static/guide.html core/static/app.js)
```

期望：6 个值与上表“目标 sha256”逐一相同。

## 2. 核对线上要替换的文件（只读）

```bash
ssh $H "cd /opt/mcp-suite && sha256sum $OLD; ls -l qiuzhao/v4_fields.py 2>&1 | tail -1; systemctl is-active mcp-suite.service mcp-suite-bench.service; systemctl show -p ActiveEnterTimestamp mcp-suite-bench.service; free -m; df -h / | tail -1"
```

期望：5 个值与上表“线上现状”逐一相同；`v4_fields.py` 报 `No such file or directory`；`active active`；`free -m` 的 available 不低于 600 MB（01:02 时为 933 MB）。记下 bench 的 `ActiveEnterTimestamp`，第 8 步要对比。

- `core/server.py`、`qiuzhao/tools.py`、`core/store.py` 任何一个不同，或 `v4_fields.py` 已存在，或 available 低于 600 MB：停下回报。
- 只有 `guide.html` 或 `app.js` 不同（线上页面在 2026-09-11 21:26 以后被改过）：在线上最新版上重新套用 v4 的 6 处文字替换，用结果替换部署包里的两个文件：

```bash
L=$W/research/qiuzhao-v4-impl/tmp/live-static; rm -rf $L && mkdir -p $L
ssh $H 'cat /opt/mcp-suite/core/static/guide.html' > $L/guide.html
ssh $H 'cat /opt/mcp-suite/core/static/app.js' > $L/app.js
cp $L/guide.html $L/guide.html.live; cp $L/app.js $L/app.js.live
python3 $W/research/qiuzhao-v4-impl/scripts/reapply_static_edits.py $L   # 期望 re-applied 6 edits；出现 NOT WRITTEN 就停下
diff $L/guide.html.live $L/guide.html; diff $L/app.js.live $L/app.js    # 只能看到 jobs_deadlines→jobs_stats / jobs_search、limit=1→page_size=1 这 6 处
cp $L/guide.html $PKG/core/static/guide.html; cp $L/app.js $PKG/core/static/app.js
(cd $PKG && shasum -a 256 core/static/guide.html core/static/app.js)    # 这两个值是这两个文件新的目标哈希
```

后面各步核对这两个文件时用新的哈希，收据里写明来源“线上 <时间> 版 + 6 处替换”。

## 3. 用线上最新 jobs.json 做枚举检查（只读）

```bash
ssh $H 'nice -n 19 /opt/mcp-suite/.venv/bin/python -B - check /var/lib/mcp-suite/jobs.json' < $PKG/qiuzhao/v4_fields.py
```

期望：最后一行 `RESULT OK`，`"problems": []`，`items` 约 25,6xx（00:52 版为 25,631）。约 1 秒，峰值约 250 MB，不写任何文件。`FAIL` 说明数据里出现了枚举外的新值：停下回报（此时还没替换任何文件）。

## 4. 备份（只备份要替换的文件，另复制一份 access.sqlite3，只复制不读取）

```bash
TS=$(date +%Y%m%d-%H%M%S)
printf 'TS=%s\nBK=/opt/mcp-suite/deploy/backup-pre-v4-%s\nSTG=/opt/mcp-suite/deploy/v4-pkg-%s\n' $TS $TS $TS > $ENVF; . $ENVF; cat $ENVF
ssh $H "set -e; mkdir -p $BK; cd /opt/mcp-suite; cp -p --parents $OLD $BK/; cd $BK; sha256sum $OLD | tee SHA256SUMS"
ssh $H "set -e; install -d -m 700 $BK/data; for f in access.sqlite3 access.sqlite3-wal access.sqlite3-shm; do if [ -e /var/lib/mcp-suite/\$f ]; then cp -p /var/lib/mcp-suite/\$f $BK/data/; fi; done; ls -l $BK/data | awk 'NR>1{print \$1,\$3,\$4,\$5,\$9}'"
```

期望：`SHA256SUMS` 的 5 个值与第 2 步相同；`$BK/data/` 里有 `access.sqlite3`（`-rw------- mcp-suite mcp-suite`，大小与原文件相同；01:02 时没有 `-wal`、`-shm`），只看文件名和大小。这份数据库副本只供应急，恢复它要 Max 同意。

## 5. 预建调用日志目录

```bash
ssh $H 'runuser -u mcp-suite -- install -d -m 700 /var/lib/mcp-suite/call_logs && stat -c "%U:%G %a %n" /var/lib/mcp-suite/call_logs'
```

期望：`mcp-suite:mcp-suite 700 /var/lib/mcp-suite/call_logs`。服务第一次被调用时也会自己建，预建是为了现在就确认属主和权限。

## 6. 安装（只装 6 个文件，逐个核对 sha256）

先传到暂存目录并核对，核对通过才装到位：

```bash
ssh $H "mkdir -p $STG/core/static $STG/qiuzhao"
for f in core/server.py qiuzhao/tools.py qiuzhao/v4_fields.py core/store.py core/static/guide.html core/static/app.js; do scp -q $PKG/$f $H:$STG/$f || echo "SCP-FAILED $f"; done
ssh $H "cd $STG && sha256sum $FILES"
```

期望：6 个值等于目标哈希（静态页在第 2 步重新套用过的，用新哈希）。不一致：停下，`ssh $H "rm -rf $STG"`，回报（此时线上文件还没动）。

```bash
ssh $H "set -e; cd $STG; for f in $FILES; do install -m 644 \$f /opt/mcp-suite/\$f; done; cd /opt/mcp-suite; sha256sum $FILES; stat -c '%U:%G %a %n' $FILES"
```

期望：6 个值与上一条相同；每个文件 `root:root 644`。任何一个不同：按第 11 步 A 回滚。

## 7. 重启前在服务器上做 schema 核验（数据库和日志目录都指向 /tmp 临时目录，用完删除）

```bash
for P in qiuzhao bench; do
  ssh $H "cd /opt/mcp-suite && T=\$(mktemp -d /tmp/v4-verify-XXXXXX) && PYTHONDONTWRITEBYTECODE=1 MCP_PRODUCT=$P MCP_DB_PATH=\$T/access.sqlite3 MCP_DIST_DB_PATH=\$T/distribution.db MCP_JOBS_PATH=/var/lib/mcp-suite/jobs.json MCP_BENCH_PATH=/var/lib/mcp-suite/bench.json MCP_CALL_LOG_DIR=\$T/call_logs .venv/bin/python -W ignore - ; rm -rf \$T; ls -d /tmp/v4-verify-* 2>/dev/null || echo tmp-cleaned" < $W/research/qiuzhao-doubao-fix-20260911/scripts/verify_schema_snippet.py
done
```

期望（与本地 `evidence/verify_schema_v4.txt` 相同）：

```
qiuzhao jobs_detail: params=1 anyOf/oneOf=False missing_type=[]
qiuzhao jobs_search: params=15 anyOf/oneOf=False missing_type=[]
qiuzhao jobs_stats: params=14 anyOf/oneOf=False missing_type=[]
RESULT OK []
tmp-cleaned
bench bench_detail: params=1 anyOf/oneOf=False missing_type=[]
bench bench_search: params=8 anyOf/oneOf=False missing_type=[]
bench bench_taxonomy: params=0 anyOf/oneOf=False missing_type=[]
RESULT OK []
tmp-cleaned
```

任何一个不是 `RESULT OK []`：不要重启，按第 11 步 A 回滚（线上进程还在跑旧代码，不受影响）。

## 8. 只重启 mcp-suite.service

```bash
ssh $H 'systemctl restart mcp-suite.service; sleep 5; systemctl is-active mcp-suite.service mcp-suite-bench.service; systemctl show -p ActiveEnterTimestamp mcp-suite-bench.service; journalctl -u mcp-suite.service --since "-3 min" --no-pager | tail -20 | sed -E "s/(qz|bm)_[A-Za-z0-9_-]{8,}/\1_[redacted]/g; s/(QZ|BM)-[0-9A-Fa-f]{8,}/\1-[redacted]/g; s/[Bb]earer +[^ ]+/Bearer [redacted]/g"'
```

期望：`active active`；bench 的 `ActiveEnterTimestamp` 与第 2 步相同；journal 里没有 `Traceback`、`Error`、`mcp_call_log_warning`。不符合：按第 11 步 B 回滚。

## 9. /health 与内存

```bash
ssh $H 'time curl -s http://127.0.0.1:8768/health; echo; ps -o pid,rss,args -C uvicorn; free -m'
curl -s https://savegems.top/qiuzhao/health; echo
```

期望：两次都是 `{"status":"ok","jobs":<第 3 步的 items>,"data_as_of":"…"}`（v4 的 jobs 是去重、去测试记录后的条数；v3 报的是有效行数）。第一次请求要构建缓存，约 1–2 秒。qiuzhao 的 uvicorn RSS 预计 250–350 MB，available 不低于 400 MB。`status` 不是 ok：按第 11 步 B 回滚。

## 10. 端到端核验（不用任何真实 key）

在服务器上以 `mcp-suite` 身份、在进程内起应用：临时库（/tmp 下）里签发临时 key，调一次 `jobs_search`（成都 + 2027届 + 计算机类，page_size=5）和一次 `jobs_stats`（2027届，按城市分组，top=3），核对返回格式、同档排序和两行调用日志的格式；调用日志写到临时目录，不进生产日志；脚本结束时删除整个临时目录，输出里没有 key。

```bash
ssh $H 'cd /opt/mcp-suite && runuser -u mcp-suite -- env MCP_JOBS_PATH=/var/lib/mcp-suite/jobs.json nice -n 19 .venv/bin/python -B -W ignore -' < $W/research/qiuzhao-v4-impl/scripts/e2e_inprocess_check.py
ssh $H 'ls -d /tmp/v4-e2e-* 2>/dev/null || echo tmp-cleaned; ls -A /var/lib/mcp-suite/call_logs; echo "(call_logs 列表结束)"'
```

期望（00:52 数据下的样子；数据变了数字会变，格式和结论不变）：

```
health    {'status': 'ok', 'jobs': 25631, 'data_as_of': '2026-09-12T00:52:36+08:00'}
search    {'total': 1933, 'explicit_total': 244, 'inferred_total': 24, 'unspecified_total': 1665, 'excluded_social_total': 167}
           技术类校招岗位(2027届) | 成都,天津,北京,上海,深圳 | {"level": "明确匹配", "graduation_year": "岗位写明", "city": "岗位写明", "major": "岗位写明"}
           …共 5 行，城市依据都是“岗位写明”，没有“全国”…
stats     22525 [('北京', 5519), ('上海', 2907), ('深圳', 1609)]
call log  lines 2 modes ('0o700', ['0o600']) last {"ts": "…", "product": "qiuzhao", "tool": "jobs_stats", …, "outcome": "ok", "error_type": null, "result_total": 22525, "returned": 3, …}
tmp removed True
RESULT OK []
```

第二条命令期望 `tmp-cleaned`。生产的 `call_logs` 目录应为空，除非这期间有真实用户调用；本步不会往里写。不是 `RESULT OK []`：按第 11 步 B 回滚。

## 11. 失败时回滚

**A. 还没重启时失败（第 6、7 步）**：只恢复文件，线上进程一直在跑旧代码。

```bash
ssh $H "set -e; cd /opt/mcp-suite; for f in $OLD; do cp -p $BK/\$f \$f; done; rm -f qiuzhao/v4_fields.py; sha256sum $OLD; ls qiuzhao/v4_fields.py 2>&1 | tail -1; rm -rf $STG"
```

**B. 重启后失败（第 8–10 步）**：恢复文件，再只重启 mcp-suite.service。

```bash
ssh $H "set -e; cd /opt/mcp-suite; for f in $OLD; do cp -p $BK/\$f \$f; done; rm -f qiuzhao/v4_fields.py; sha256sum $OLD; systemctl restart mcp-suite.service; sleep 5; systemctl is-active mcp-suite.service; curl -s http://127.0.0.1:8768/health; echo; rm -rf $STG"
```

期望：哈希回到第 2 步的值（A 另有 `No such file or directory`）；B 为 `active`，health 为 ok（旧代码按有效行数计）。另外：

- `/var/lib/mcp-suite/call_logs/` 保留，旧代码不读它。
- 数据库不需要回滚：线上库本来就有 `code_plain` 列，新 `store.py` 的迁移只在列不存在时执行，不会改库。`$BK/data/` 里的副本只供应急，恢复要 Max 同意（会丢掉备份之后的兑换记录）。
- 如果 bench 的 `ActiveEnterTimestamp` 在第 2 步之后变过（说明 bench 被重启过，正在跑新的 `core/server.py`），不要动 bench，写进回复由 Max 决定。
- 回滚后不做第 12 步，直接按第 13 步回复。

## 12. 成功后：清理暂存、main 快进、部署收据

**12a. 服务器暂存目录。** `ssh $H "rm -rf $STG; ls -d $BK"`，备份目录保留。

**12b. main 快进到 feat/v4。** main 工作副本里有未跟踪的 `research/qiuzhao-v4-interface-20260911/` 原稿和改过没提交的 `scripts/v4lib.py`，它们和已提交的版本逐字节相同，但 git 仍会拒绝快进。先用脚本核对，全部相同才移开：

```bash
git -C $M branch --show-current                                           # 期望 main
git -C $M merge-base --is-ancestor main feat/v4 && echo MAIN-IS-ANCESTOR  # 没有这行：停下，不要 merge、rebase 或 force
python3 $W/research/qiuzhao-v4-impl/scripts/prepare_main_ff.py $M          # 只读 dry run
```

期望：dry run 最后是 `blockers=N safe=N different=0` 和 `dry run: nothing moved`（2026-09-12 01:3x 本地实测 N=18）。`different` 不为 0：停下回报。为 0 时：

```bash
python3 $W/research/qiuzhao-v4-impl/scripts/prepare_main_ff.py $M --apply   # 移到 ~/Projects/mcp-suite-preff-backup-<时间>/
git -C $M merge --ff-only feat/v4
git -C $M rev-parse HEAD feat/v4; git -C $M log -1 --format='%h %s'
```

期望：`moved N file(s) to …`；`Fast-forward`；两个 hash 相同。快进失败：停下回报原始输出，不用其他合并方式。

**12c. 部署收据。** 在 main 工作副本写 `research/qiuzhao-v4-impl/DEPLOY-RECEIPT.md`，风格参照 `research/collector-fix-20260911/DEPLOY-RECEIPT.md`，写明：开始和结束时间（北京时间）、执行者、部署提交 `2f0f070`、第 1 步三项前置条件的实际输出、6 个文件部署前后的 sha256（静态页有没有重新套用、来源是什么）、枚举检查的 items、两段 schema 核验结果、重启前后的 `free -m` 和 qiuzhao RSS、两次 /health 的返回、端到端核验的完整输出（按第 0 节第 5 条脱敏）、备份目录、`prepare_main_ff.py` 的输出和移走文件的目录、main 快进前后的 hash，以及任何与本任务书不一致的地方。然后：

```bash
git -C $M add research/qiuzhao-v4-impl/DEPLOY-RECEIPT.md
git -C $M commit -m "docs: v4 deploy receipt $(date +%F)"
git -C $M log --oneline -3
rm -rf $PKG $W/research/qiuzhao-v4-impl/tmp/live-static $ENVF
```

不 push。

## 13. 最后回复的格式

```
部署：成功 / 失败已回滚（第 N 步：原因）/ 未开始（前置条件：哪一项、实际输出）
提交：部署 2f0f070；main <旧 hash> → <新 hash>（快进）；部署收据 <hash>
文件：6 个 sha256 与目标一致 / 列出不一致的；静态页来源：feat/v4 原样 / 线上 <时间> 版 + 6 处替换（新哈希 …）
核验：枚举 RESULT OK（items N）；schema qiuzhao OK、bench OK；/health {...}；端到端 RESULT OK（search total …，前 5 条城市依据 …；stats total …；调用日志 2 行、700/600）
内存：重启前 available … MB；重启后 qiuzhao RSS … MB、available … MB
备份：/opt/mcp-suite/deploy/backup-pre-v4-<TS>（含 data/access.sqlite3 副本，未读取）
main 快进：prepare_main_ff 移走 N 个文件到 …；或停在哪一步、原因
异常与需要 Max 决定：…（没有写“无”）
```
