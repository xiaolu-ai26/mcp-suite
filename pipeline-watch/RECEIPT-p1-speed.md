# RECEIPT — p1 大厂官网管线提速(并发 + 超时收紧 + 失败单元次日优先)

- 日期:2026-09-18
- Worktree:`/Volumes/臭垃圾桶/生财MCP/_worktrees/p1-speed`
- 分支:`feat/p1-speed`(基于 `fix/collector-partial-keep`)
- 范围:只改调度层。生产改动仅 `qiuzhao/collector/p1_pipeline.py`;单测在 `tests/test_p1_pipeline.py`
- 状态:**已 commit,未部署、未 SSH、未 push、未合并**

---

## 0. 结论(先看这段)

1. **并发**:`run()` 改为「每公司一条 chain + `ThreadPoolExecutor`」,默认 `--workers 4`(上限 6)。同公司 scope 严格串行,不同公司并行;线程只阻塞在子进程 `wait`。任何单元结束即刻落盘 checkpoint。
2. **超时**:新增 `--scope-timeout`(默认 **600s**);`--max-run-seconds` 保持。旧 `--timeout` 保留兼容 —— 精灵链现在的 `--timeout 1200` 仍然生效,但一旦显式给 `--scope-timeout`,后者优先。
3. **失败次日优先**:当天非 success+complete 的单元写入 `data/p1-retry-queue.json`(公司/scope/原因/次数/连续天数);下次 `run()` 先跑队列单元;连续 3 天失败降级到最后跑并在 `status['retry']['demoted']` 列出,**不删任何公司**。
4. **未改动**:适配器 `p1_sources_*.py`、`publish()`/`merge_records()`/`validate_result()` 校验门、`windows_collector.py`、退出码语义(0/2/1)、`any_validated()`。
5. **单测**:新增 10 条全部通过;全量 `pytest tests/` 失败集合与基线**完全一致**,无新增失败。
6. **离线真实采集**:商汤科技 + 大华股份 campus 并发跑通,50s 内两家都产出 `result.json`/`validated.json` 且 `success+complete`(80 + 146 条),退出码 0,未 `--apply`。
7. **预估精灵耗时**(按 9-17 分布):`--workers 4 --scope-timeout 600` 约 **45–65 分钟**(原 ~5 小时,约 5–8×);若保留 `--timeout 1200`,约 80–95 分钟。

---

## 1. 改了什么

### 1.1 并发(`run()` 重构)

- 新增 `plan_chains(companies, scopes, queue)`:每个公司一条 chain,chain 内 scope 排序后**串行**执行;chain 之间由 `ThreadPoolExecutor(max_workers=workers)` 并行。
- 动态投递:每完成一条 chain 才提交下一条,`max_workers` 即「同时在跑的单元数上限」。`workers=1` 退化为原串行语义。
- `run_unit()` 内保留原逻辑:skip 已完成 / deadline 判定 / `collect_process(..., min(timeout, max(1, deadline-now)))` / `validated.json` 落盘。
- **状态写入加锁**:`threading.Lock` 串行化 `status['results']`、`status['publications']`、`status['retry']` 的修改与 `save_status()`;文件本身仍走 `atomic_json`(`mkstemp` + `os.replace`)原子替换。因此并发下每个单元恰好一条 checkpoint,不丢不重。
- 单元结束立即 `save_status()`,同时写三份:`run_dir/status.json`、`data_dir/p1-status.json`、`data_dir/p1-checkpoints/<key>.json`。
- `--workers` CLI 校验 `1..6`,默认 4(`main()` 用 `parser.error` 拦截越界)。
- `publish()` **完全未改**:仍靠 `p1-publish.lock` 的文件锁(`fcntl.flock LOCK_EX`)串行化多线程写入,CAS 复查/写前备份/原子替换逻辑原样;`status['publications']` 追加在 `state_lock` 内,避免丢账。

### 1.2 超时

- 新增 `--scope-timeout`(int,默认 600)。
- `--timeout` 保留为 legacy(default `None`);解析优先级:
  `--scope-timeout` > `--timeout` > 600。
- `run(timeout=600, ...)` 默认值同步收紧到 600。
- 超时清理路径(子进程 `wait(timeout=)` → `stop_tree(strict=False)` → `timeout-cleanup.json` → partial/blocked)沿用 `collect_process`,未改一行。

### 1.3 失败单元次日优先队列

文件:`<data_dir>/p1-retry-queue.json`

```json
{
  "updated_at": "...",
  "entries": {
    "商汤科技/campus": {
      "company": "商汤科技", "scope": "campus",
      "reason": "timeout|ssl|blocked|incomplete",
      "count": 3,
      "consecutive_days": 3,
      "last_failed_date": "2026-09-17",
      "fail_dates": ["2026-09-15", "2026-09-16", "2026-09-17"],
      "first_failed_at": "...", "last_failed_at": "..."
    }
  }
}
```

- 判定:`success` 且 `complete is True` → 成功,出队;否则入队。
- 原因分类:`timeout_cleanup` 存在或 errors 含 timeout → `timeout`;含 SSL → `ssl`;`blocked` → `blocked`;其余 → `incomplete`。
- 连续天数按 **UTC 日界** 推进:同一 UTC 日重复失败不重复计数;隔一天 +1;断档重置为 1;成功则整条移除。
- 调度 tier:`-1`(失败但连续 <3 天)= 队列优先;`0` = 正常;`1`(连续 ≥3 天)= 最后。公司按 min(tier) 排序,公司内 scope 同序排序。降级列表写入 `status['retry']['demoted']`,收据/日志可查。
- 队列写入 best-effort(`except OSError`),`data_dir` 只读时也绝不阻断采集。

### 1.4 涉及函数一览

| 函数 | 状态 |
| --- | --- |
| `collect_process` / `validate_result` / `merge_records` / `publish` / `any_validated` / `checkpoint_path` | **零改动** |
| `run` | 重构为线程池调度;签名新增 `workers=4`,`timeout` 默认 3600→600 |
| `retry_queue_path` / `load_retry_queue` / `save_retry_queue` / `failure_reason` / `is_full_success` / `next_consecutive_days` / `record_retry_failure` / `record_retry_success` / `retry_tier` / `plan_chains` / `retry_summary` | 新增 |
| `main` | 新增 `--scope-timeout`/`--workers`;`--timeout` 默认改 `None`;超时优先级计算 |

---

## 2. 未改动清单(硬约束核对)

- 适配器:`qiuzhao/collector/p1_sources_*.py` 等 **0 文件改动**。
- 发布/校验门:`publish()`、`merge_records()`、`validate_result()` **0 改动**。
- `deploy/windows_collector.py` **0 改动**;`deploy/collector-daily.sh` **0 改动**。
- 退出码:`0` 全 success+complete / `2` 至少一个可信 partial 或 success / `1` 全无可信输出 —— 语义不变。
- 未部署、未 SSH、未碰阿里云、未调飞书、未读取/打印任何令牌、未 push、未合并。

---

## 3. 单测与基线对比

命令(worktree 根目录):

```
/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```

| | failed | passed | skipped |
| --- | --- | --- | --- |
| 基线(改前) | 4 | 336 | 55 |
| 改后 | 4 | **346** | 55 |

- `diff` 失败清单:**完全一致,无新增失败**;`passed` 增加 10 条(正好是新增测试数)。
- 说明:任务书写的基线是 39 failed,但本 worktree + 主仓 venv 实测基线是 **4 failed**(可能存在环境/依赖差异),以本机实测前后对比为准。
- 基线已存在的 4 条失败(**与本次改动无关**,其中第 3 条就在本文件,是 `stop_tree(strict=False)` 未确认 tree 终止时拒绝 partial 的既有权衡):

  ```
  tests/test_codes_kind.py::test_migration_is_safe_when_both_services_start_together
  tests/test_core.py::test_role_cohort_and_campaign_title_bases
  tests/test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint
  tests/test_schema.py::test_enum_check_fails_when_data_drifts
  ```

### 3.1 新增 10 条测试(`tests/test_p1_pipeline.py::P1ConcurrencyTests`)

用假的 `collect_process`(`sleep` 模拟 + 记录并发)覆盖:

1. `test_concurrent_run_is_bounded_by_longest_unit` — 4 家 × 0.25s,wall-clock < 串行总和的 75%,证 N=4 时总耗时 ≈ 最长单元而非总和。
2. `test_same_company_scopes_serialize_while_companies_overlap` — 观测同公司最大并发 = 1、跨公司最大并发 ≥ 2;证同公司 scope 串行 + 不同公司并行。
3. `test_concurrent_checkpoints_keep_one_entry_per_unit` — 3 家 × 2 scope,并发后 `status.json` 与 checkpoint 各恰好 6 条,`validated.json` 全部存在。
4. `test_failed_unit_enters_retry_queue_and_runs_first_next_time` — SSL 失败入队(reason/count/consecutive_days 正确);次日即使公司顺序反转为 `拼多多,大疆`,仍先跑队列里的 `大疆/campus`;成功后出队。
5. `test_three_day_failure_is_demoted_to_last` — 预置连续 3 天失败,跑完顺序把它排在最后;`status['retry']['demoted']` 含它;再次失败 consecutive_days → 4。
6. `test_resume_latest_reuses_concurrent_checkpoint_without_repeating` — 并发 2 家,一家先完成落盘、另一家 `KeyboardInterrupt`;`--resume-latest` 只补跑中断的那家,已完成的不重复。
7. `test_resume_latest_resumes_unfinished_concurrent_run` — deadline 中断的并发配置,`--resume-latest` 在 `--workers 3` 下补齐全部单元。
8. `test_concurrent_apply_publishes_every_unit_and_keeps_publish_lock` — `apply=True` 并发写:临时 `jobs.json` 落全 3 家、`publications` 3 条、写前备份存在(验证 `p1-publish.lock` 串行化)。
9. `test_scope_timeout_flag_precedence_and_workers_passed` — `--scope-timeout 600` 压过 `--timeout 1200`;legacy 单传 `--timeout 1200` 仍为 1200;`--workers` 默认 4 透传。
10. `test_retry_reason_classification` — timeout / ssl / blocked 分类正确。

---

## 4. 离线验证(真实采集,未 `--apply`)

命令(外接盘输出,未写任何库):

```bash
OUT=/Volumes/臭垃圾桶/生财MCP/_worktrees/p1-speed-out
RUN=$OUT/run-offline-20260918T153332
/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m qiuzhao.collector.p1_pipeline \
  --data-dir "$OUT/data" --run-dir "$RUN" \
  --companies 商汤科技,大华股份 --scopes campus \
  --workers 2 --scope-timeout 420 --max-run-seconds 1500
```

结果:

| 单元 | status | complete | jobs | pages | result.json | validated.json |
| --- | --- | --- | --- | --- | --- | --- |
| 大华股份/campus | success | true | 146 | 9 | ✔ | ✔ |
| 商汤科技/campus | success | true | 80 | 5 | ✔ | ✔ |

- **退出码 0**,总 wall-clock **50s**;`run_finished=true`,`pending=[]`。
- 并发证据:两家同一时刻(15:33:32 CST)启动;大华 `checked_at 07:33:56Z`(≈24s)、商汤 `07:34:22Z`(≈50s)。wall=50s≈max(24,50),而非串行和 ≈74s。
- 重试队列:`data/p1-retry-queue.json` 为 `entries: {}`(两家都成功,符合预期)。
- 产物目录:`/Volumes/臭垃圾桶/生财MCP/_worktrees/p1-speed-out/run-offline-20260918T153332/{31,33}/campus/`。
- 未 `--apply`、未写任何共享库、只跑 2 家。
- 备注:外接盘是 exFAT,macOS 生成的 `._*` AppleDouble 会被适配器 glob 进 evidence 列表;这是本机离线环境产物,现网 Windows 无此现象,不影响代码结论。

---

## 5. 预估精灵上的耗时(按 9-17 分布推算)

9-17 事实:35 家 / 105 单元 / ~5 小时(≈18000s);60 success、23 partial、22 blocked;14 SSLError、12 超时;`timeout=1200`。

推算假设:`12 次超时吃满 1200s` → 超时墙钟 ≈ `12 × 1200 = 14400s`;其余 93 单元 ≈ `18000 − 14400 = 3600s`(≈39s/单元,含串行与重试开销)。

| 配置 | 串行工作量估算 | workers=4 | workers=6 |
| --- | --- | --- | --- |
| 9-17 基线(串行,timeout=1200) | ~18000s | ~5h | — |
| 仅并发,保留 timeout=1200 | ~18000s | ~75 min | ~50 min |
| 并发 + `--scope-timeout 600` | ~10800s | **~45 min** | **~30 min** |

- 计入公司内 scope 串行带来的关键路径与调度尾巴,实际取区间:
  - `--workers 4 --scope-timeout 600`:**约 45–65 分钟**(相对 5 小时约 5–8×);
  - `--workers 6 --scope-timeout 600`:约 30–45 分钟;
  - 若总控保留 `--timeout 1200`:约 80–95 分钟(workers=4)。
- 风险:家用带宽被 4–6 单元分摊,单单元可能变慢;600s 可能把少量原本 600–1200s 才完成的单元切成 partial/blocked —— 这类单元会被重试队列次日优先补跑,不会静默丢公司。

---

## 6. 部署说明

- **只需覆盖一个文件**:`qiuzhao/collector/p1_pipeline.py` → 精灵(Windows)现网对应位置。
- 精灵链现状(见 `deploy/windows_collector.py`,本次未改):
  `... p1_pipeline --data-dir <stage> --apply --resume-latest --timeout 1200 --max-run-seconds 18000`
- **兼容性**:部署后即使链上仍写 `--timeout 1200`,行为不变(1200s/单元);`--workers` 默认 4 自动生效,链不改也能提速。
- **由总控决定**:是否把链上的 `--timeout 1200` 改成 `--scope-timeout 600`(可再加 `--workers 4` 或 `6`)。改与不改都兼容,原因是 `--scope-timeout` 优先、`--timeout` 兜底。
- **注意默认值变化**:原 `--timeout` 默认 3600;现在不传时有效超时为 **600**。任何依赖旧 3600 默认的调用会受影响,例如 `deploy/collector-daily.sh`(未传 timeout)默认从 3600 → 600。请总控确认该链是否接受。
- 重试队列 `p1-retry-queue.json` 与 `p1-status.json` 同目录(Windows stage / `/var/lib/mcp-suite`),首次运行自动创建;只读目录下静默跳过,不阻断采集。
- 不需要改 `windows_collector.py`、不需要改退出码、不需要改发布逻辑。

---

## 7. 遗留 / 已知边界

1. **旧默认超时变更**:`--timeout` 默认 3600 → 未传即 600;`deploy/collector-daily.sh` 未显式传值,行为会变(需总控确认)。
2. **中断语义保持原样**:`KeyboardInterrupt` 时不写 `status['pending']`(沿用旧实现),恢复依赖 `run_finished=false` + `--resume-latest`。
3. **队列是超集**:除 blocked/超时/SSL 外,`partial`(即使带了行)与其它非 complete 单元也会入队并次日优先,便于收敛覆盖率;原因字段可区分。
4. **连续天数按 UTC 日界**;跨时区部署需知悉。
5. **`--workers` 只允许 1–6**;更高的并发被 CLI 拒绝(家用带宽保护)。
6. 并发 `apply` 的最终串行化依赖 `p1-publish.lock` 文件锁与 `state_lock`;已用临时目录单测覆盖,但未在精灵上实跑 `--apply`(按任务要求不部署)。
7. 本机离线验证的 exFAT `._*` 证据噪音仅限该环境。
8. 未 push、未合并 —— 分支 `feat/p1-speed` 上 commit,等总控评审。
