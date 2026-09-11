# Git 纳管收据 — 2026-09-11

## git log --oneline

```
bc5d194 sync: production code snapshot 2026-09-11 21:26
bf28b19 chore: import local project state (2026-09-11)
```

## 跟踪文件数与仓库体积

- 跟踪文件数（`git ls-files | wc -l`）: 1320
- `git count-objects -vH`:

```
count: 1325
size: 19.57 MiB
in-pack: 0
packs: 0
size-pack: 0 bytes
prune-packable: 0
garbage: 0
size-garbage: 0 bytes
```

## 最终 .gitignore

```gitignore
.venv/
__pycache__/
.pytest_cache/
private/
*.sqlite3*
.env
.mcp.json
qiuzhao/data/
bench/data/
bench/sources/
*.mcp.json
.DS_Store
*.bak
*.bak.*
*.pyc
deploy/*receipt*.json
deploy/final-online/
deploy/remote-latest/
deploy/backup*/
research/*/data/
research/*/tmp/

# 大文件
research/qiuzhao-expansion-20260910/staging/bytedance_pending/jobs.json
research/qiuzhao-expansion-20260910/staging/bytedance_jobs.json
research/qiuzhao-v3-launch-20260910/conditional_release/_bytedance_raw/harvest_from_700_full.json
research/qiuzhao-v3-launch-20260910/conditional_release/batch_bytedance_full.json
research/qiuzhao-v3-launch-20260910/conditional_release/qualified_jobs.json
research/qiuzhao-v3-launch-20260910/staging_adapters/bytedance/jobs.json
research/qiuzhao-v3-launch-20260910/job_mvp/staging_merged/jobs.json
research/qiuzhao-v3-launch-20260910/staging_run/jobs.json
research/qiuzhao-500-mvp/state/jobs_merged.json

# 疑似含凭据
tests/e2e_bench_online.py
```

## 凭据扫描命中并被排除的文件（只列文件名）

- tests/e2e_bench_online.py

扫描在第 3 步首次命中 1 个文件，git rm --cached 并加入 .gitignore 后复扫无命中；第 5 步同步后复扫同样无命中。暂存区无 >5MB 文件，`^private/|sqlite3` 检查为空。

## 同步时文件清单

来源: `research/qiuzhao-doubao-fix-20260911/live-baseline/`（SHA256SUMS 52 项全部 OK 后执行 rsync，无 --delete）。

被线上版本覆盖（8 个）:
- core/server.py
- core/store.py
- core/static/app.js
- core/static/guide.html
- core/static/index.html
- core/static/site.css
- qiuzhao/tools.py
- qiuzhao/collector/run.py

线上新增（15 个）:
- core/distribution.py
- core/static/admin.css
- core/static/admin.html
- core/static/admin.js
- core/static/changelog.json
- core/static/wechat-qr.png
- core/static/img/guide/doubao-1.png
- core/static/img/guide/doubao-2.png
- core/static/img/guide/qianwen-1.jpeg
- core/static/img/guide/qianwen-2.jpeg
- core/static/img/guide/workbuddy-1.png
- core/static/img/guide/workbuddy-2.png
- deploy/nginx-bench-previous.conf
- qiuzhao/collector/auto_collect.py
- qiuzhao/collector/export_csv.py

本地独有而线上没有（7 个）:
- qiuzhao/collector/alibaba_headless.py
- qiuzhao/collector/base_headless.py
- qiuzhao/collector/bytedance.py
- qiuzhao/collector/meituan.py
- qiuzhao/collector/midea.py
- qiuzhao/collector/mindray.py
- qiuzhao/collector/netease.py

## git status

提交 2 之后、本文件提交之前 `git status --porcelain` 输出为空（干净）。其他 Agent 仍在往 research/ 写文件，此后工作区出现未跟踪/修改属正常现象。

备注：requirements.txt 经 cp 覆盖后内容与本地一致，git 无变更；qiuzhao/collector/tencent.py 仅 mtime 变化，内容相同，未产生 diff。
