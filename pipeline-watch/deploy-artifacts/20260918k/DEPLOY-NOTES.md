# 部署件 20260918k：累积合并版（20260918h + 字节/美的 + 外企第二批）

**叠加顺序：一步覆盖。** 若精灵仍是 `20260918` 现役，直接覆盖本包；若精灵已经跑
`20260918h`，同样直接覆盖本包（两种前提的"部署前应有哈希"都写在
`PROD-BACKUP-MANIFEST.txt`）。`20260918b..j` 均**未部署**，本包已把它们全部累积进来，
不需要再逐个叠加。本包**未部署、未 SSH、未碰阿里云、未调飞书、未写库、未 push**。

## 为什么需要 k（而不是 h→i→j 逐个叠）

`20260918i`（字节跳动/美的集团）与 `20260918j`（外企第二批）都改了
`qiuzhao/collector/p1_pipeline.py`，两个补丁无法分别叠加（i 的注册块 + 稳定 id 规则、
j 的注册块 + 配置段都落在同一文件）。k 是二者按顺序 merge 后的**单一**版本：

1. 两个分支依次 merge（`feat/bytedance-daily` → `feat/foreign-batch2`），冲突只在
   `p1_pipeline.py` 注册块与 `tests/test_collector_next_integration.py` 顺序断言，
   两边的注册块**全部保留**：feishu → 字节跳动 → 美的集团 → 大易(`p1_foreign_01`)
   → 51job(`p1_platform_51job`)。
2. `p1_platform_companies.json` 合并所有段（`beisen` 478 / `moka` 317 / `feishu` 78 /
   `dayee` 7 / `job51` 1 / `workday` 10 / `successfactors` 3），无覆盖、无改名。
3. 调度归类（本次唯一新增的调度改动）：
   - **大易 `hotjob.cn`、51job 归平台模块**：加入 `PLATFORM_MODULES` 与
     `PLATFORM_HOST_GROUPS`（`hotjob.cn` / `51job.com`），因此受 `PlatformGate`
     约束——同平台并发 ≤ `--platform-workers 3`、同平台单元启动间隔 ≥1s，默认三 scope。
   - **字节跳动、美的集团是"每天必跑的专用适配器"**：**不**进 `PLATFORM_MODULES`，
     各自独立 gate 组（`company:字节跳动` / `company:美的集团`），三 scope，
     美的 `social` 按适配器设计返回 `blocked`（公开校招接口看不到社招岗位）。
   - 两者都不进 `ROTATING_MODULES`，默认不轮转（每天全跑）。
4. `p1_platform_companies.json` 的 `dayee`/`job51` 段也纳入 `_load_scope_opt_ins()`，
   将来如需收窄某公司 scope，写 `"scopes": [...]` 即生效。

## 默认集合规模

- 默认 `DEFAULT_COMPANIES` = **948 家**（20260918h 的 924 + 字节跳动 + 美的集团 +
  外企第二批新增 22 家），`REGISTRY` 同名唯一、无重复、无覆盖。
- 外企第二批配置新增 23 行，其中"毕马威"已由更早的 moka 租户注册，故净增 22 家。
- 硬编码 50、银行 5、阿里 6、腾讯音乐 1、Workday 10、SF 3、飞书 72、北森 478、
  Moka 316、大易 7、51job 1、字节 1、美的 1（`blocks` 里 Moka 显示 313，
  另 3 家（三七互娱/金山办公/鹰角网络）在硬编码槽内）。

## 覆盖文件（17 个，全部运行时文件；不含测试与夹具）

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（h + i + j 合并版：注册块全保留 + `stable_id_prefix` + 大易/51job 入平台 gate） |
| `p1_platform_companies.json` | `qiuzhao/collector/p1_platform_companies.json` | 覆盖（= 20260918j 版：h 全段 + 外企第二批新增行） |
| `windows_collector.py` | `deploy/windows_collector.py` | 覆盖（与 20260918h **逐字节相同**，sha256 9eaf97cc…） |
| `guopin.py` | `qiuzhao/collector/guopin.py` | 覆盖（= 20260918h 版） |
| `p1_platform_beisen.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `p1_platform_moka.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `p1_platform_workday.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `p1_platform_successfactors.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `p1_feishu_public.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `p1_banks_01.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `alibaba_headless.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `tencent_music.py` | `qiuzhao/collector/` | 覆盖（= 20260918h 版） |
| `bytedance.py` | `qiuzhao/collector/` | 覆盖（`fetch_page` 新增 `recruitment_id_list`/`referer` 形参；精灵上应已有旧版） |
| `p1_bytedance_public.py` | `qiuzhao/collector/` | **新增**（字节跳动 p1 适配器，campus/intern/social） |
| `p1_midea_public.py` | `qiuzhao/collector/` | **新增**（美的集团 p1 适配器，campus/intern；social 为 blocked 设计） |
| `p1_foreign_01.py` | `qiuzhao/collector/` | **新增**（大易 hotjob.cn 通用适配器，7 家） |
| `p1_platform_51job.py` | `qiuzhao/collector/` | **新增**（51job 企业校招专页适配器，1 家） |

`run.py` 本次不变（现役 sha256 5e94f91b…，不在本包内）。测试文件与 `fixtures/` 一律**不**放进本包。

## 新增模块的 import 闭包（本包已自洽）

- `p1_bytedance_public.py` → `qiuzhao.collector.bytedance`（本包含新版）→ `.run`（现役，未改）。
- `p1_foreign_01.py` / `p1_platform_51job.py` → `.p1_sources_01_10`（现役，未改）、
  `requests` / `urllib3`（正式 venv 已有）。
- `p1_midea_public.py` → 仅标准库。
- 因此 17 个文件覆盖后没有悬空 import；无需额外补文件。

## 关键说明

1. **默认全量**：不加 `--platform-rotation` 时 `companies_for_day()` 返回全部 **948 家**；
   大易/51job 受平台 gate（同 host 并发 ≤3、间隔 ≥1s），字节/美的走各自独立组。
2. **首次跑对存量的影响**（预演数据见 20260918i 的 DEPLOY-NOTES）：字节 campus 快照
   2663 条 vs 库里 2244 条校园记录 → 交集 2222 条**原地更新**、441 条新增；
   美的 campus 214 / intern 321 条。`stable_id_prefix` 保证 `bytedance-<id>` /
   `midea-<positionId>` 原 id 不换命名空间、不产生重复。
3. **计划任务参数无需改**：p1 参数都写在 `deploy/windows_collector.py` 里，
   覆盖后次日 06:10 自然生效，不重启任何服务。
4. **Headless 依赖（阿里系 + 飞书招聘）与 h 相同**：精灵 `%LOCALAPPDATA%\ms-playwright`
   不存在时需要先 `C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium`，
   否则阿里系/飞书公司 blocked。大易、51job、字节、美的、北森/Moka、Workday/SF、
   银行、腾讯音乐都是纯 HTTP，不需要浏览器。
5. **礼貌限速**：`QIUZHAO_PLATFORM_REQUEST_INTERVAL`（生产缺省 0，验证设 2.0）、
   `QIUZHAO_PLATFORM_REQUEST_BUDGET`（生产缺省不限）。

## 校验与回滚

```bash
cd 20260918k && shasum -a 256 -c SHA256SUMS.txt   # 17 个文件全部 OK
```

覆盖后用正式 venv（cwd=`C:\mcp-suite-collector`）跑
`python -c "import deploy.windows_collector, qiuzhao.collector.p1_pipeline as P; print(len(P.DEFAULT_COMPANIES), len(P.REGISTRY))"`
应输出 `948 948`。

回滚：按 `PROD-BACKUP-MANIFEST.txt` 的两种前提执行（恢复 `p1_pipeline.py` /
`guopin.py` / `windows_collector.py` / h 的 9 个新文件 / `bytedance.py`，
并删除本包 4 个新文件）。回滚后字节、美的、大易、51job 自动退出日常链，其余公司不受影响。
