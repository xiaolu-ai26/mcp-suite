# RECEIPT — collector-next-5：g/h/i 合成唯一可部署包 20260920a（含已上线的 P0 热修；不部署）

**结论先行**：`feat/multi-entrance`（h，1056→1069）、`feat/normalize-adjust`（i，规范化收窄）、
`fix/p1-winlock`（20260919k P0 热修，**已上线精灵**）已依次并入 `feat/collector-next-5`。
**三次合并全部由 git 自动完成、零冲突、零人工改文件**；合并后的 `p1_pipeline.py` 与
`fix/p1-winlock` 的同一文件**逐字节一致**，且 `git diff 82af4f72 HEAD -- …p1_pipeline.py` 与
`git diff 82af4f72 fix/p1-winlock -- …p1_pipeline.py` **完全相同**——即
「collector-next-4 的文件 + 热修补丁」，g 的注册块与 h/i 的改动都在，热修一个字没丢。
`fix/p1-winlock` 的 **6 条锁相关单测全过**。最终默认公司集合 **1069 家**
（`len(REGISTRY)==len(set(DEFAULT))==1069`、0 重名、21 个模块）。`pytest tests/` =
**3 failed / 656 passed / 55 skipped**，失败清单与 `feat/collector-next-4` 基线逐条相同、**未新增**；
零网络探针 `pipeline-watch/collector-next5-probe.py` **PROBE OK**；源码断言
`'_publish_thread_lock' in p1_pipeline.py` → **True**。
唯一部署件 `pipeline-watch/deploy-artifacts/20260920a/`：**18 个运行时文件**
（10 覆盖 + 8 新增）+ `SHA256SUMS.txt`（`shasum -c` **18/18 OK**、与分支源码逐字节一致）+
`PROD-BACKUP-MANIFEST.txt`（前提哈希按精灵**当前真实值**，`p1_pipeline.py` = `13a5ec53…`）+
`DEPLOY-NOTES.md`。**本包取代 20260919g / h / i，那三个包作废。**
**未部署、未 SSH、未碰阿里云、未调飞书、未读取/打印任何令牌、未登录、未发任何外部网络请求、
未 push、未合并 main、未终止任何进程。**

工作区：`/Users/maxzhl/Projects/mcp-suite-next5`（分支 `feat/collector-next-5`；按任务书建在**本机**，
外接盘 `/Volumes/臭垃圾桶` 只剩约 502MB、未在其上建任何 worktree）。
Python：`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python`。

## 0. 分支与提交

| 项 | 值 |
|---|---|
| 起点 | `feat/collector-next-4` = `82af4f72`（累积部署件 20260919g，1056 家） |
| merge 1 | `feat/multi-entrance` `b6a81d83` — **fast-forward**（本分支起点即其父，git 无需新建提交） |
| merge 2 | `f7285553` ← `feat/normalize-adjust` `579c222d`（自动合并，**无冲突**） |
| merge 3 | `90b6f3e6` ← `fix/p1-winlock` `a2fb3bf4`（自动合并，**无冲突**） |
| merge 3 的父 | `90b6f3e6 parents=f7285553 a2fb3bf4` |
| 收尾提交 | 见本文件所在提交（探针 + 部署件 + 收据） |

`fix/p1-winlock` 取的是分支 HEAD `a2fb3bf4`（= 热修 `69cad4d6` + 20260919k 上线记录），
所以热修补丁与它的上线收据、证据目录一并进了本分支。

**为什么没有冲突**：`p1_pipeline.py` 只有 g（collector-next-4）和 `fix/p1-winlock` 动过；
h 只改 `p1_platform_companies.json` + Moka 适配器 + 测试，i 只改 `company_names.py` /
`company_aliases.json` / 测试。三条线的文件集不相交，git 三方合并直接取各自版本。
任务书按"会有冲突"预设的处置方案因此没有触发；但**热修必须保留**的验收照做，见 §2。

## 1. 合并与冲突处置

| 文件 | 来源 | 处置 |
|---|---|---|
| `qiuzhao/collector/p1_pipeline.py` | collector-next-4 + `fix/p1-winlock` | 自动合并；= g 的注册块 + 热修补丁（§2 证明） |
| `qiuzhao/collector/p1_platform_companies.json` | h (`feat/multi-entrance`) | 取 h 版本；与 `20260919h/p1_platform_companies.json` **逐字节一致**（段并集天然成立，h 本就基于 g） |
| `qiuzhao/company_names.py` | i (`feat/normalize-adjust`) | 取 i 版本；与 `20260919i/company_names.py` **逐字节一致** |
| `qiuzhao/data/company_aliases.json` | i | 取 i 版本；与 `20260919i/company_aliases.json` **逐字节一致** |
| Moka 适配器（`p1_platform_moka.py`） | g（h 未改） | g 版本 |
| 其余 5 个适配器 / 8 个 k 文件 / `normalize.py` | g | g 版本 |

- **同名公司处置表沿用 collector-next-4**：惠普/应用材料 → Eightfold、飞利浦 → Phenom、
  强生 → Workday `jj/wd5/JJ`、毕马威 → 现役 Moka `kpmg/76195`，对应 workday / tupu360 留档行
  `enabled:false` 原样保留（探针逐个断言，见 §4）。
- **h 的多租户合并行保住**：`moka["nestlezgc/91899"]` 雀巢 **3 租户**
  （`91899` 校招 / `91898` 社招 / `124026` 社招，均 `enabled`），
  `moka["ey/166374"]` 安永 **2 租户**（`166374` 校招 / `102474` 社招）。
- **规范化以 i 的收窄版为准**：g 里被删的品牌合并/集团前缀合并**没有被带回来**——
  实测 `canonical_of('网易互娱')==('网易互娱','keep')`、`('网易互联网')==('网易互联网','keep')`、
  `('中国移动通信')==('中国移动通信','keep')`、`('中国联合网络通信')==('中国联合网络通信','keep')`、
  `('中国邮政')==('中国邮政','brand')`；同一实体归一保留
  `('腾讯科技（深圳）有限公司')==('腾讯','alias')`；1019 条配置公司名
  `names_normalization_would_rewrite == []`。
- `qiuzhao/normalize.py`、`p1_platform_moka.py` 等**没有**被任一后续分支再改（见 §3 的 18 文件清单）。

## 2. P0 热修保留的证据（本任务的核心）

### 2.1 合并后的文件 = collector-next-4 + 逐字节相同的热修补丁

```
$ git diff 82af4f72 HEAD            -- qiuzhao/collector/p1_pipeline.py > /tmp/a.diff
$ git diff 82af4f72 fix/p1-winlock  -- qiuzhao/collector/p1_pipeline.py > /tmp/b.diff
$ diff /tmp/a.diff /tmp/b.diff
HOTFIX DIFF IDENTICAL: merged = collector-next-4 + fix/p1-winlock patch, byte-for-byte
$ git diff --stat 82af4f72 HEAD -- qiuzhao/collector/p1_pipeline.py
 qiuzhao/collector/p1_pipeline.py | 121 ++++++++++++++++++++++-------------
 1 file changed, 82 insertions(+), 39 deletions(-)
$ git diff fix/p1-winlock HEAD -- qiuzhao/collector/p1_pipeline.py     # 空输出 = 逐字节一致
```

即：合并结果**没有任何第三方改动**，g 的注册块原样保留，热修两处原样保留。
`p1_pipeline.py` sha256 = **`093b237e852ba1d15717e97adc6b7de66f412c84c4005b3a72e79b4a108de12d`**，
与 `20260919k/DEPLOY-NOTES.md` 预告的「g + 修复」哈希 `093b237e…` 完全吻合。

### 2.2 热修两处都在源码里

第一处——`publish()` 外层模块级 `threading.Lock`（文件锁保留、`finally` 显式 `LOCK_UN`）：

```python
_publish_thread_lock = threading.Lock()          # 模块级，见 p1_pipeline.py:761

def publish(data_dir, results, run_dir):
    ...
    with _publish_thread_lock:                    # 同进程内串行化
        with open(data_dir / 'p1-publish.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)      # 跨进程互斥不变
            try:
                ...
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)  # 显式解锁
```

第二处——`run_unit()` 收敛 `publish()` 异常（记 `publish_error` / `published=False` /
进 retry-queue，不冒泡）；`any_validated()` / `failure_reason()` / 退出码相应适配：

```python
        publication = None
        publish_error = None
        if apply and (result['jobs'] or ...):
            try:
                publication = publish(data_dir, [(company, scope, result)], publication_dir)
            except Exception as error:
                publish_error = f'{type(error).__name__}: {error}'      # 不冒泡
        with state_lock:
            entry = {'coverage': result['coverage'], ...,
                     'published': bool(apply) and publish_error is None, 'attempted': True}
            if publish_error is not None:
                entry['publish_error'] = publish_error
                entry['publish_failed_at'] = now()
            ...
            if publish_error is not None:
                record_retry_failure(retry_queue, company, scope,
                                     {'status': 'blocked', 'errors': [publish_error],
                                      'publish_error': publish_error})
```

### 2.3 用 `fix/p1-winlock` 的 6 条锁单测验证

```
$ .../python -m pytest tests/test_p1_pipeline.py -k "P1WindowsPublishLockTests" -v
tests/test_p1_pipeline.py::P1WindowsPublishLockTests::test_all_publish_failures_return_fatal_without_aborting PASSED
tests/test_p1_pipeline.py::P1WindowsPublishLockTests::test_concurrent_run_with_windows_style_lock_publishes_every_unit PASSED
tests/test_p1_pipeline.py::P1WindowsPublishLockTests::test_eight_threads_publish_all_succeed_and_serialize PASSED
tests/test_p1_pipeline.py::P1WindowsPublishLockTests::test_fake_lock_reproduces_windows_same_process_reentry PASSED
tests/test_p1_pipeline.py::P1WindowsPublishLockTests::test_publish_still_waits_for_another_process_file_lock PASSED
tests/test_p1_pipeline.py::P1WindowsPublishLockTests::test_single_publish_failure_keeps_other_units_and_returns_partial PASSED
6 passed, 38 deselected
```

其中 `test_fake_lock_reproduces_windows_same_process_reentry` 用可注入的 Windows 语义假锁
（`_WindowsStyleFcntl`）复现 `msvcrt.locking` 同进程重入抛 `Errno 36`；
`test_publish_still_waits_for_another_process_file_lock` 另起真实进程证明跨进程互斥没被削弱。

另：`python -c "…; src=open('qiuzhao/collector/p1_pipeline.py').read();
print('_publish_thread_lock' in src)"` → **True**（任务书要求的额外断言）。

## 3. 最终规模

- 默认集合 **948（k）→ 1056（g）→ 1069（本包）**；`len(REGISTRY)==len(set(DEFAULT))==1069`，重名 0。
- 21 个模块的家数：

| 模块 | 家数 | 模块 | 家数 |
|---|---|---|---|
| 北森 | 481 | ORC | 9 |
| Moka | 333 | Phenom | 8 |
| 飞书 | 72 | SF | 7 |
| Workday | 69 | Eightfold | 5 |
| 大易 | 11 | Avature | 4 |
| 51job | 9 | tupu360 | **0**（全段留档，robots） |
| 大厂 sources 01–50 | 47 | iCIMS | **0**（robots 闸门） |
| 阿里系 | 6 | 银行 | 5 |
| 腾讯音乐 / 字节 / 美的 | 各 1 | | |

- h 的 13 家：Moka 雀巢（3 租户）/ 博西家电 / 北京环球度假区 / 昂际航电、
  北森 上汽大众 / 光束汽车、Workday 杜邦 / 友邦保险 / 丹纳赫 / 通用磨坊、
  SF 阿克苏诺贝尔 / 汇丰 / 阿迪达斯；安永补社招租户（不增公司）。
- **相对 k 的运行时改动恰好 18 个文件**（`git diff --stat f423084 HEAD -- qiuzhao/ deploy/`
  只列出这 18 个；`deploy/` **零改动**，`windows_collector.py` 与 `run.py` 不在包内），
  `qiuzhao/`、`deploy/` 下无未跟踪运行时文件。

## 4. 验证

| 检查 | 结果 |
|---|---|
| `pytest tests/`（本包） | **3 failed / 656 passed / 55 skipped** |
| `pytest tests/`（`feat/collector-next-4` 82af4f72 基线，同机同 venv） | **3 failed / 640 passed / 55 skipped** |
| 失败清单比对 | 逐条相同：`test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts`；**新增失败 0** |
| 新增测试 | 收集数 698 → **714**（+16 = h `test_p1_platform_moka.py` +3、i `test_company_names.py` +7、热修 `test_p1_pipeline.py` +6） |
| 已知 flaky `test_codes_kind` | 单跑 8 次：本包失败 3 次、基线失败 5 次，**失败的都是同一条** `test_migration_is_safe_when_both_services_start_together`（两服务同时启动的时序竞争），与本合并无关 |
| 6 条锁单测 | **6 passed** |
| 零网络探针 | `pipeline-watch/collector-next5-probe.py` → **PROBE OK**（无任何适配器调用/HTTP） |
| 部署件 `shasum -c` | **18/18 OK** |
| 部署件 vs 分支源码 | 18/18 **逐字节一致**（`cmp`） |
| import 闭包 | `IMPORT_OK 1069 1069`；`THREAD_LOCK_PRESENT True`；6 个新适配器全部 import 成功；tupu360/iCIMS 注册 0 家 |
| 冲突残留 | 全树 grep `<<<<<<<` / `=======` / `>>>>>>>` → 无 |

探针断言覆盖：默认集合与重名、REGISTRY/DEFAULT 集合相等、6 个新适配器的
`PLATFORM_MODULES`/`PLATFORM_HOST_GROUPS` 归属、同名冲突处置、留档行不进注册表、
h 的多租户行、i 的收窄规范化（含 `config_names_rewritten == []`）、以及
**热修的 6 个源码标记**（`_publish_thread_lock`、`with _publish_thread_lock`、`fcntl.LOCK_UN`、
`entry['publish_error']`、`return 'publish'`、`status['success'] = all(`）。

## 5. 唯一部署件 `pipeline-watch/deploy-artifacts/20260920a/`

**18 个运行时文件 = 10 覆盖 + 8 新增**（相对精灵**当前真实状态**：
20260918k 的 17 个文件 + 20260919k 热修后的 `p1_pipeline.py` = `13a5ec53…`；
g/h/i 从未部署，其新增文件在精灵上 ABSENT）：

| 动作 | 文件 |
|---|---|
| 覆盖(10) | `p1_pipeline.py`(`093b237e…`)、`p1_platform_companies.json`(`cd4c403b…`)、`p1_feishu_public.py`、`p1_platform_beisen.py`、`p1_platform_moka.py`、`p1_platform_successfactors.py`、`p1_platform_workday.py`、`p1_foreign_01.py`、`p1_platform_51job.py`、`normalize.py`(`52fb48f7…`，不在 k 清单，**VERIFY** 前提) |
| 新增(8) | `p1_platform_eightfold.py`、`p1_platform_phenom.py`、`p1_platform_avature.py`、`p1_platform_icims.py`、`p1_platform_orc.py`、`p1_platform_tupu360.py`、`company_names.py`、`data/company_aliases.json` |
| 验证但**不进包**(8) | `guopin.py`、`alibaba_headless.py`、`p1_banks_01.py`、`tencent_music.py`、`bytedance.py`、`p1_bytedance_public.py`、`p1_midea_public.py`、`deploy/windows_collector.py`（8 个哈希实测仍等于 k 值） |

`PROD-BACKUP-MANIFEST.txt` 的前提哈希**没有照抄旧清单**，是逐条重算/重核的：

- `p1_pipeline.py` 前提 = **`13a5ec53a2b934809482a44f683bec6c5b2774bf96964cf57fb1df2d4cddacda`**
  （2026-09-20 00:40 上线后的实测值），**不是** k 清单里的 `ff96be4d…`；
- 其余 9 个覆盖文件前提 = 各自 20260918k SHA256SUMS 值；
- 8 个新增文件前提 = **ABSENT**；
- `normalize.py` = **VERIFY**（不在 k 清单，期望 `a53adaf3…`，部署前必须读真实哈希并备份）；
- 另列 8 个 VERIFY ONLY 文件的期望哈希，可用来证明"精灵 = k + 热修、零漂移"。

## 6. 部署步骤

沿用 `pipeline-watch/TASK-collector-next-4-deploy.md` 的流程，**文件清单按 20260920a**
（该任务书正文写的是 20260919g，派发部署任务时以 20260920a 的 `DEPLOY-NOTES.md` 为准）：
等空闲 → 按 manifest 逐文件核对前提哈希（含 VERIFY ONLY 8 个）→ robocopy 备份 `deploy` + `qiuzhao`
（退出码 ≤7，不全目录）→ 分片 base64 传 18 个文件到暂存区并 `SHA256SUMS` 复核 18/18 →
覆盖 18 个路径并复核 → `py_compile` + import 闭包（`IMPORT_OK 1069 1069`、
`THREAD_LOCK_PRESENT True`）→ 不重启服务、不改计划任务、不手动补跑 → 次日 06:10 首次实测。
**前提之一：必须在站长明确说"上线"之后才能执行，且建议先核对完 9-20 06:10 的首轮实测。**

## 7. 次日观察项

`runs\20260920\receipt.json` 的 `steps`/`step_changes`：p1 应为 `exit 2`（或 0）且带
added/updated，**不再是 `rolled_back`**；`p1.log` 0 次 `Errno 36` / `Resource deadlock`；
`data\p1-retry-queue.json` 与 `p1-last-attempt.json` 应生成；p1 起止时间（1069 家，估 2–3.5h、
上界 ≈4.5h）；新平台各家 `coverage.status`（Eightfold/Phenom/ORC/Avature + h 新接的
雀巢/汇丰/阿迪达斯/安永/友邦/丹纳赫等）；**强生三 scope 若全 0 要升级处理**；normalize 后
三个公司名字段空值应为 0、记录数与 id 集合不变（i 的干跑：三字段全空 26258 → 0、改名 35 对 /
11296 行、展示名去重 4016 → 4006）；库总量；飞书同步耗时。

## 8. 回滚

从部署第 3 步的备份恢复 10 个覆盖文件、删除 8 个新增文件（`normalize.py` 是**恢复**不是删除），
逐字节校验：`p1_pipeline.py` 必须回到 **`13a5ec53…`**（热修不能丢——这是 20260920 06:10
那轮不再整段回滚的唯一原因），其余回到 k 值。回滚件同时有现成的
`C:\mcp-suite-backup-20260920-0033\`（含热修前的 `ff96be4d…`，**若要连热修一起回滚才用它**）
与 `C:\mcp-suite-backup-20260918-2020\`（k 全量）。

## 9. 包作废声明

**本包（20260920a）取代 20260919g、20260919h、20260919i 三个包；那三个包作废，不要再单独部署。**
理由：三个包分别从 `feat/collector-next-4` 分叉、各自带一份不含热修的 `p1_pipeline.py`，
按原顺序叠加会把已上线的 `13a5ec53…` 覆盖回 `ff96be4d`/`5852f497`，9-21 早上 p1 会再次整段回滚。
本包的 `p1_pipeline.py` 是它们的并集 + 热修。

## 10. 约束遵守

未部署、未 SSH 精灵、未碰阿里云、未写飞书生产 Base、未读取或打印任何令牌、未登录任何站点、
未发任何外部网络请求（探针零网络、单测用夹具）、未 push、未合并 main、未用 `git stash`、
未终止任何进程。部署件写在**本机** worktree；外接盘只用于读取交接文档与既有产物，未在其上建
worktree、未写入大文件。
