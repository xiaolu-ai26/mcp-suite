# RECEIPT — 修掉一直失败的单测 `test_timeout_publishes_only_validated_partial_checkpoint`

工作区：`/Volumes/臭垃圾桶/生财MCP/_worktrees/collector-next`（分支 `feat/collector-next`，基线 HEAD `4f055da`）。
全程未部署、未 SSH、未碰阿里云、未调飞书、未读取/打印任何令牌、未 push、未 `git stash`；只在本 worktree 工作。
外接盘 `._*` AppleDouble 文件未纳入任何提交。

---

## 结论（一句话）

**是测试过期，不是代码 bug**：这条单测的假进程 mock 把"父进程已退出、进程树终止无法确认"的情况误当成了"正常超时被杀"，而 `collect_process` 在终止无法确认时**有意**拒绝复用结果文件并返回 `blocked`——这是随 `stop_tree` 一起加入的安全闸，测试没有同步更新。

## 给 Max 的白话解释（5 句以内）

1. 这条测试不是在说代码错了，而是它自己搭的"假采集进程"搭错了：它默认让假进程一上来就显示"已经退出"，于是代码合理地判定"没杀干净，不能信这个结果文件"。
2. 真实生产里，采集单元超时后只要进程树确认被杀干净（Linux 的 `killpg`、精灵 Windows 的 `taskkill /T /F` 返回 0），代码就会把**已通过校验**的部分结果发布成 `partial`；只有杀不干净时才宁可返回 `blocked` 也不冒险。
3. 所以线上数据没有被这条"bug"污染；反过来说，`blocked` 是保护动作，不是丢失正常数据。
4. 这条测试从 9 月 17 日那个大提交给代码加上"终止确认"安全闸之后就一直是红的——改代码的人忘了改测试里的 mock，而不是线上行为坏了。
5. 我把 mock 改成能真实模拟"活着 → 被杀 → 确认死亡"，并补了两条测试，分别钉死"未通过校验的内容绝不发布"和"终止未确认时绝不发布"。

---

## 1. 证据

### 1.1 失败复现（改动前，HEAD `4f055da`）

```
$ /Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest \
    tests/test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint -x
...
>           self.assertEqual(len(collected['jobs']),1)
E           AssertionError: 0 != 1
tests/test_p1_pipeline.py:285: AssertionError
FAILED tests/test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint
```

- 期望：`len(collected['jobs']) == 1`、`coverage.status == 'partial'`。
- 实际：`len(collected['jobs']) == 0`、`coverage.status == 'blocked'`。
- 任务书里写的 `tests/test_p1_pipeline.py:282` 是**基线提交 `4155851`** 的行号（该版本断言恰在 282 行）；在当前 HEAD `4f055da` 同一条断言在 **285 行**。同一处、同一断言。

### 1.2 直接原因（逐行）

测试里：

```python
process = MagicMock(pid=1234)          # poll() 默认返回一个 truthy 的 MagicMock
process.wait.side_effect = [subprocess.TimeoutExpired('adapter', 1), 0]
```

`collect_process` 超时分支（`qiuzhao/collector/p1_pipeline.py:238-262`）：

```python
except subprocess.TimeoutExpired:
    cleanup = stop_tree(process, strict=False)        # 238-245
    atomic_json(output_dir / 'timeout-cleanup.json', cleanup)
    rc = 'timeout'
if rc:
    if result_path.exists() and not (cleanup and not cleanup.get('tree_termination_confirmed')):   # 249
        ... 复用 checkpoint -> partial ...
    failed = blocked(...)                             # 260
    return failed
```

`stop_tree`（`qiuzhao/collector/portable_runtime.py:26-33`）：

```python
report = {'pid': ..., 'already_exited': process.poll() is not None,
          'tree_termination_confirmed': False}
if report['already_exited']:
    report['process_terminated'] = True
    report['cleanup_error'] = 'parent already exited; descendant termination is unverified'
    if strict: raise RuntimeError(...)
    return report                                    # tree_termination_confirmed 保持 False
```

因为 `MagicMock.poll()` 返回 truthy → `already_exited=True` → `tree_termination_confirmed=False` →
第 249 行守卫 `not (cleanup and not False)` == `False` → **跳过 checkpoint** → 返回 `blocked`。
这正是测试看到 `jobs=0 / blocked` 的原因，**与生产语义无关，纯属 mock 失真**。

### 1.3 这是"代码有意加固、测试没跟上"（git 史）

| 提交 | 内容 |
|---|---|
| `df5e18b fix(qiuzhao): retain validated partial checkpoints after scoped collector timeouts` | **测试出生**（`test_timeout_publishes_only_validated_partial_checkpoint` + 同批 `test_timeout_does_not_reuse_preexisting_result`）。当时超时分支是裸的 `os.killpg(...); process.wait(); rc='timeout'`，条件只有 `if result_path.exists()`，所以 falsy/truthy 的 MagicMock 都能过。 |
| `850af32 wip: collector pipeline, lark sync, call-admission metering, admin/static, windows collector` | `p1_pipeline.py` 改为 `from .portable_runtime import fcntl, stop_tree`；超时分支改用 `cleanup = stop_tree(process, strict=False)`，并把复用条件加严为 `... and not (cleanup and not cleanup.get('tree_termination_confirmed'))`，同时写 `timeout-cleanup.json`。**测试未同步更新** → 从这天起一直红。 |

`stop_tree` 文件内注释即设计意图：

> `# Strict callers must not continue writing shared data while a writer is alive.`

并且 `pipeline-watch/RECEIPT-p1-speed.md:106` 早已把这条失败记录为既有权衡，不是新引入：

> 基线已存在的 4 条失败（与本次改动无关，其中第 3 条就在本文件，是 `stop_tree(strict=False)` 未确认 tree 终止时拒绝 partial 的既有权衡）

### 1.4 当前正确行为是什么、为什么

- **正确行为**：adapter 超时后，
  1. 先 `stop_tree(process, strict=False)` 杀进程树并记录 `timeout-cleanup.json`；
  2. 只有 `tree_termination_confirmed` 为真（确认没有写入者活着）时，才读取 adapter 落盘的 `result.json`，把它降级为 `partial`（`complete=False`、`detail_complete=False`）、追加 `adapter interrupted: timeout` 错误，再交给 `validate_result`；
  3. `validate_result` 通过 → 发布校验后的 partial；**不通过 → 落到 `blocked`，一行都不发布**；
  4. 终止未确认 → 直接 `blocked`，不碰 checkpoint。
- **为什么**：`result.json` 是 adapter 边跑边写的，只有确认写进程已死才可能读到完整/稳定的内容。复用未确认终止的 checkpoint 有读到半截文件、放进共享库的风险；`blocked` 会让该单元进 retry 队列次日优先重跑，代价远小于脏数据。这与产物名"只发布已通过校验的部分结果"完全一致，只是多了"确认写入者已死"这个前置条件。

### 1.5 生产影响：这个"bug"是否影响了线上数据？

- **没有数据被污染，也没有"该发布的正常结果被丢弃"的证据**。精灵现役链在超时后走同一段 `collect_process`：
  - Linux：`os.killpg(pid, SIGKILL)` 成功 → `tree_termination_confirmed=True` → 发布校验后的 partial；
  - 精灵 Windows：`taskkill /PID <pid> /T /F` 返回 0 → `tree_termination_confirmed=True` → 发布校验后的 partial。
- 只有"父进程在超时判定瞬间恰好已退出"或"killpg/taskkill 自身失败"时才会 `blocked`；这是**保守丢弃**（该单元进 retry 队列），不是错误发布。
- 规模参照：`pipeline-watch/RECEIPT-p1-speed.md:163` 记录 9-17 实测 `105 单元 / 12 次超时`（与任务书"每天 12 次左右超时"一致）。这些超时按上述路径处理，**线上数据未因此出错**。
- 边界说明（诚实标注）：我未 SSH、未读精灵日志（受硬约束），以上是从代码路径 + 本仓收据推断，不是对精灵当日日志的实证；若要 100% 坐实，需要总控在精灵上抽查 `timeout-cleanup.json` 的 `tree_termination_confirmed` 分布（只读，不在本次范围）。

---

## 2. 改动

**只改测试，未改任何生产源码**（因此未触碰 `pipeline-watch/deploy-artifacts/20260918b/` 与 `SHA256SUMS.txt`——见 2.2 一致性核对）。

### 2.1 `tests/test_p1_pipeline.py`

| 位置 | 改动 |
|---|---|
| 第 11 行 | `from unittest.mock import patch` → `from unittest.mock import MagicMock, patch` |
| 第 16-32 行 | 新增模块级 helper `timed_out_process()`：假进程初始 `poll()` 返回 `None`（活着），`os.killpg` 被调用后 `poll()` 才返回 0（被杀并确认）。 |
| 第 293-316 行 | 重写 `test_timeout_publishes_only_validated_partial_checkpoint`：用 helper 模拟真实"活着→被杀→确认死亡"，断言发布 1 条 partial、`tree_termination_confirmed=True`，并断言保留行带 `validate_result` 写入的 `p1_company/p1_scope/p1_identity`（证明经过了校验，不是原样发布）。 |
| 第 318-332 行 | **新增** `test_timeout_does_not_publish_unvalidated_checkpoint`：同样确认死亡，但 adapter 写的行缺 `description_raw`（违反契约）→ 断言 `blocked`、`jobs=[]`。直接钉死"只发布已通过校验的内容"。 |
| 第 334-350 行 | **新增** `test_timeout_with_unconfirmed_cleanup_does_not_publish_checkpoint`：父进程已退出、终止无法确认，但 `result.json` 是合法内容 → 断言仍 `blocked`、`jobs=[]`、`tree_termination_confirmed=False`。直接钉死安全闸。 |

原 `test_timeout_does_not_reuse_preexisting_result`（预先存在的 `result.json` 不得复用）未动，仍通过。

**为什么不"硬改测试让它绿"**：本次不是把断言改松或删掉，而是修正 mock 使其反映真实进程生命周期，并把原来看不到的两种边界（未校验、终止未确认）显式写成新断言；测试覆盖只增不减。

### 2.2 部署件一致性（未改源码，无需同步）

```
$ shasum -a 256 qiuzhao/collector/p1_pipeline.py pipeline-watch/deploy-artifacts/20260918b/p1_pipeline.py
78cf1f030dabbeb019cb620bfa1d1d89335c3d592b586fff14c9a82be35fbb2e  qiuzhao/collector/p1_pipeline.py
78cf1f030dabbeb019cb620bfa1d1d89335c3d592b586fff14c9a82be35fbb2e  pipeline-watch/deploy-artifacts/20260918b/p1_pipeline.py

$ grep p1_pipeline pipeline-watch/deploy-artifacts/20260918b/SHA256SUMS.txt
78cf1f030dabbeb019cb620bfa1d1d89335c3d592b586fff14c9a82be35fbb2e  p1_pipeline.py
```

源码、`20260918b` 部署件、`SHA256SUMS.txt` 三者哈希一致，部署件无需变更。因未改 `p1_pipeline.py`，按要求**未**在 `RECEIPT-collector-next.md` 追加源码变更节；该收据第 5 节失败清单里的第 2 条（本条测试）现已被本收据解决，特此交叉引用。

---

## 3. 测试输出

### 3.1 目标三文件（要求全绿）

```
$ /Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest \
    tests/test_p1_pipeline.py tests/test_collector_next_integration.py tests/test_collector_partial_keep.py -q
...................................................................      [100%]
67 passed in 2.47s
```

### 3.2 四条超时用例（逐条）

```
$ ... pytest tests/test_p1_pipeline.py -k "timeout" -v
tests/test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint PASSED
tests/test_p1_pipeline.py::P1Tests::test_timeout_does_not_publish_unvalidated_checkpoint PASSED
tests/test_p1_pipeline.py::P1Tests::test_timeout_with_unconfirmed_cleanup_does_not_publish_checkpoint PASSED
tests/test_p1_pipeline.py::P1Tests::test_timeout_does_not_reuse_preexisting_result PASSED
4 passed
```

（`tests/test_p1_pipeline.py` 单文件 `40 passed`。）

### 3.3 全量 `pytest tests/` 与基线对比

| 运行 | 结果 | 失败清单 |
|---|---|---|
| 基线（改动前，本 worktree 实测） | **4 failed, 373 passed, 55 skipped** | ① `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together`（既有 flaky）② `test_core.py::test_role_cohort_and_campaign_title_bases` ③ **`test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`** ④ `test_schema.py::test_enum_check_fails_when_data_drifts` |
| 改动后 | **3 failed, 376 passed, 55 skipped** | ① `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` ② `test_core.py::test_role_cohort_and_campaign_title_bases` ③ `test_schema.py::test_enum_check_fails_when_data_drifts` |

- 失败清单相对基线**只少目标这一条**；其余三条均为基线既有失败（`test_codes_kind` 收据里已注明是顺序依赖 flaky，本次两次全量都出现）。
- `passed` 由 373 → 376（+1 为原失败转绿，+2 为新增用例）。

---

## 4. 遗留与不确定点

1. **精灵侧实证缺口**：受"不 SSH/不碰阿里云"硬约束，未抽查精灵 `timeout-cleanup.json` 的 `tree_termination_confirmed` 实际分布（第 1.5 节）。代码路径与收据支持"未污染线上数据"的结论，但严格实证需总控只读抽查。
2. **"父进程恰好已退出"的保守丢弃**：超时判定瞬间父进程若已退出，`stop_tree` 会因"后代终止无法确认"返回 `blocked`，即使盘上有合法结果也不复用。这是安全侧设计（宁可次日重跑，不冒险读可能半截的文件），非本次引入、本次未改；若总控认为这类丢弃在精灵上偏多，可单独立项评估更细的终止确认（例如按 PID 树逐个确认），不建议在本测试修复里顺手改行为。
3. 本次未改源码，故未生成新部署件；`20260918b` 仍与源码一致（2.2）。
4. 外接盘 `._*` 与测试副作用文件 `research/qiuzhao-v4-impl/evidence/pytest/uvicorn-bench.log`（仅 PID/端口随测试运行变化）均已还原/不纳入提交；提交只含 `tests/test_p1_pipeline.py` 与本收据。
