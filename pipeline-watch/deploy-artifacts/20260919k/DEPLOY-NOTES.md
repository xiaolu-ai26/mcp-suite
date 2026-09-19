# 部署件 20260919k：p1 并发发布 Windows 死锁热修（单文件）

**叠加顺序：一步覆盖（只替换 1 个文件）。** 本包以**精灵现役 20260918k**为前提：
把 `p1_pipeline.py` 替换为 `20260918k + winlock 修复`。若精灵已经先部署了
**20260919g**，**不要**用本包的 `p1_pipeline.py`（它不含 g 的任何注册块/新适配器），
见下文「前提 G」。本包**未部署、未 SSH 写入正式目录、未碰阿里云、未调飞书、未写库、
未 push、未合并 main、未终止任何进程**。

## 根因

`publish()` 用文件锁 `p1-publish.lock` 做跨进程互斥。Windows 下
`portable_runtime.flock` 用 `msvcrt.locking` 模拟；`msvcrt.locking` 对**同一进程内已
持有该区域**的再次加锁会直接抛 `OSError [Errno 36] Resource deadlock avoided`，
不像 POSIX `flock` 那样阻塞等待。p1 改成 `ThreadPoolExecutor` 并发后，同一进程里
多个线程同时进 `publish()`，第二个线程立刻抛错 → 异常冒泡到 `run()` → 整个 p1 以 1
退出 → 外层按契约回滚整段。2026-09-19 06:10 首轮因此丢失了已采到的 18 个单元
（11 success / 6 blocked / 1 partial）。

## 修法（本包的 `p1_pipeline.py` 相对 20260918k 的改动）

1. **进程内串行**：新增模块级 `_publish_thread_lock = threading.Lock()`，`publish()`
   在拿文件锁**之前**先进入该锁；文件锁保留（跨进程互斥不变）。这样同一进程内任何
   时刻只有一个线程去碰 `msvcrt.locking`，Errno 36 不再可能发生。
2. **单个发布失败不再炸整段**：`run_unit()` 用 `try/except Exception` 收敛
   `publish()` 异常，把该单元记为失败（`published=False` + `publish_error`），
   其余单元照常发布；`any_validated`/`success` 不计入未发布的单元。退出码契约不变：
   **0 全成功 / 2 部分成功 / 1 致命（没有任何单元成功）**。
3. 未发布的单元进入 `p1-retry-queue.json`（`reason=publish`），次日优先重试；
   其 `validated.json` 已落盘，resume 时重试发布而不重采。

## 覆盖文件（仅 1 个运行时文件；测试与夹具不入包）

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（= 20260918k 逐字节 + winlock 修复） |

`portable_runtime.py` **不改**（审计结论见收据 §4：其它 `flock` 调用点都不在
多线程路径上）。`windows_collector.py` **不入包**：它原本就在 p1 步骤传
`--workers 8`，正是暴露问题的入口，无需改。

## 前提 K（推荐，当前实测状态）

精灵现役 = `20260918k`，`20260919g` **尚未部署**。直接覆盖本包的
`p1_pipeline.py`：

- 部署前应有哈希：`qiuzhao/collector/p1_pipeline.py` =
  `ff96be4d772847a0273003e2db0466d3ad698dc5cd719d968f40fb96abc8dc76`（已在精灵上实测）。
- 部署后应为：`13a5ec53a2b934809482a44f683bec6c5b2774bf96964cf57fb1df2d4cddacda`。
- 回滚：从 `C:\mcp-suite-backup-20260918-2020\qiuzhao\collector\p1_pipeline.py`
  （或任何 k 备份）还原，校验回 `ff96be4d…`。

## 前提 G（若站长先部署了 20260919g）

本包**不能**用。需把同一修复合入 g 后**重出一份**，或使用
`fix/p1-winlock` 分支上的 `qiuzhao/collector/p1_pipeline.py`
（= `20260919g` + 同一修复，sha256 `093b237e852ba1d15717e97adc6b7de66f412c84c4005b3a72e79b4a108de12d`）
覆盖到已经部署好的 g 树；其余 g 文件不动。回滚到 g 的 `5852f497…`。

## 校验

```bash
cd 20260919k && shasum -a 256 -c SHA256SUMS.txt    # 1 个文件 OK
```

覆盖后用正式 venv（cwd=`C:\mcp-suite-collector`）跑：

```
python -c "import qiuzhao.collector.p1_pipeline as P; print(P._publish_thread_lock is not None, len(P.DEFAULT_COMPANIES))"
```

应输出 `True 948`（前提 K）。次日 06:10 观察 `runs\<日期>\p1.log` 不再出现
`Errno 36`，`receipt.json` 的 `step_changes.p1` 为 `ok`/`partial`。

## 证据

- 单测：`tests/test_p1_pipeline.py` 新增 6 条（含可注入的 msvcrt 重入假锁），
  `pytest tests/` = 3 failed / 646 passed / 55 skipped，失败清单与
  `feat/collector-next-4` 基线逐条相同、无新增。
- 精灵临时目录实测（`C:\mcp-suite-winlock-test\`，正式目录只读）：真实并发 p1
  6 家 × campus × workers 4 × `--apply`，结果见
  `pipeline-watch/RECEIPT-p1-winlock.md`。
