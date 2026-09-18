# 部署件 20260919c：外企补齐 B —— Avature / iCIMS / Oracle Recruiting Cloud

**叠加顺序：一步覆盖在 `20260918k` 之后。** 精灵现役 = 20260918k（2026-09-18 20:27 上线、
17/17 哈希核对通过），本包只有这一种前提，部署前应有哈希写在 `PROD-BACKUP-MANIFEST.txt`。
`20260919a`（飞书镜像重载）、`20260919b`（Eightfold/Phenom）与本包互不覆盖对方的文件，
但三者都改 `p1_pipeline.py` / `p1_platform_companies.json`：**必须由总控按顺序合并或选择
一个累积包**，不要交叉叠加。本包**未部署、未 SSH、未碰阿里云、未调飞书、未写库、未 push**。

## 覆盖文件（6 个，全部运行时文件；不含测试与夹具）

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（k 版 + 3 个追加注册块 + `PLATFORM_MODULES`/`PLATFORM_HOST_GROUPS` 各 3 行 + `_load_scope_opt_ins` 段名 +3） |
| `p1_platform_companies.json` | `qiuzhao/collector/p1_platform_companies.json` | 覆盖（k 版 + `avature` 4 家 + `icims` 0 家（含原因说明）+ `orc` 9 家 + Workday 3 家 + SuccessFactors 1 家） |
| `p1_platform_successfactors.py` | `qiuzhao/collector/p1_platform_successfactors.py` | 覆盖（新增 unify 主题回退：`POST /services/recruiting/v1/jobs`） |
| `p1_platform_avature.py` | `qiuzhao/collector/` | **新增**（Avature 搜索门户适配器，5 家） |
| `p1_platform_icims.py` | `qiuzhao/collector/` | **新增**（iCIMS Career Portal 适配器，含 robots 闸门；本期 0 家，见下） |
| `p1_platform_orc.py` | `qiuzhao/collector/` | **新增**（Oracle Recruiting Cloud 适配器，9 家） |

`run.py`、`deploy/windows_collector.py`、`bytedance.py`、`guopin.py`、北森/Moka/Workday/
飞书/银行/大易/51job/字节/美的 适配器、`alibaba_headless.py`、`tencent_music.py`
**逐字节等同于 20260918k**，不在本包内。

## 默认集合规模

- `DEFAULT_COMPANIES` = **965 家**（20260918k 的 948 + 本批净增 17：Avature 4 + ORC 9 +
  Workday 3 + SuccessFactors 1）。
- 无重名、无覆盖：`德州仪器` 保持 Moka 校招租户 `ti/142216`（ORC 的
  `edbz.fa.us2.oraclecloud.com/CX_1` 有 95 条中国岗位，但同名会顶掉 Moka 槽位，本期**故意不注册**，
  原因写进配置 `orc._note`）；`毕马威` 维持旧 Moka 租户。
- 段内计数：beisen 478 / moka 316 / feishu 72 / dayee 7 / job51 1 / workday 13 /
  successfactors 4 / avature 4 / icims 0 / orc 9。

## 调度归类（本次唯一调度改动）

- `p1_platform_avature` / `p1_platform_icims` / `p1_platform_orc` 三个模块加入
  `PLATFORM_MODULES`，并各自进 `PLATFORM_HOST_GROUPS`（`avature` / `icims` / `oraclecloud`），
  因此受 `PlatformGate` 约束：同 host 并发 ≤ `--platform-workers`、同 host 单元启动间隔 ≥1s，
  默认三 scope。三个模块都**不**进 `ROTATING_MODULES`（每天全跑）。
- `_load_scope_opt_ins()` 增加 `avature` / `icims` / `orc` 三段，将来收窄某公司 scope
  写 `"scopes": [...]` 即生效。

## 新增模块的 import 闭包（本包已自洽）

- 三个新模块 → `qiuzhao.collector.p1_sources_01_10`（现役，未改）+ `requests`/`urllib3`（正式 venv 已有）。
- `p1_platform_successfactors.py` 新版只多一个 `urllib.parse.quote`（标准库）。
- `p1_pipeline.py` → 三个新模块（本包含）。覆盖后无悬空 import。
- Avature 适配器**不需要浏览器**（纯 HTTP + 官方页面自带的翻页链接）；iCIMS 适配器同样纯 HTTP，
  且在被 robots 禁止的租户上**一个内容请求都不会发**。

## 校验与回滚

```bash
cd 20260919c && shasum -a 256 -c SHA256SUMS.txt   # 6 个文件全部 OK
```

覆盖后用正式 venv（cwd=`C:\mcp-suite-collector`）跑
`python -c "import deploy.windows_collector, qiuzhao.collector.p1_pipeline as P; print(len(P.DEFAULT_COMPANIES), len(P.REGISTRY))"`
应输出 `965 965`。

回滚：按 `PROD-BACKUP-MANIFEST.txt` 恢复 3 个覆盖文件到 `C:\mcp-suite-backup-20260918-2020\`
的版本，并删除 `p1_platform_avature.py` / `p1_platform_icims.py` / `p1_platform_orc.py`。
回滚后本批 17 家自动退出日常链，其余 948 家不受影响。

## 已知边界

1. **Avature 4 家（目标 5 家）**：汇丰 portal 88 的 36 条 pipeline 在官方详情页上全部落在
   波兰(当期中国 0 条)→ 按"中国 ≥1 条"的入库条件不写入配置;IBM 的纯 HTTP 请求被 AWS WAF
   202 挑战拦下(浏览器渲染后 `search=China` 只有 2 条,且都是马来西亚岗位);IKEA/道达尔
   robots 全站 Disallow;CBRE/TSMC/IQVIA WAF 202/403。逐条证据写在配置 `avature._note`。
2. **iCIMS 本期 0 家**：站长点名的 AMD（`careers-amd.icims.com`）与施耐德
   （`careers-se.icims.com`）以及 PepsiCo / General Mills / Garmin / Keysight / Aon / ZS
   的 iCIMS 站点，`robots.txt` 全部是 `User-agent: * / Disallow: /`。按"不绕过"原则不采集；
   适配器已交付并带 robots 闸门，将来有放行租户时加一行即可。
3. **Avature 用各门户自带的 `?search=` 关键字 + 官方详情页地区做双重筛选**（Avature 的国家 facet
   参数按门户不同且为 POST，故走官方关键字检索）；Siemens 有 999+ 岗位，只扫关键字命中的集合，
   `coverage.search_total` 会如实记录命中总数。
4. **Workday 三家（可口可乐/耐克/GSK）只在中国社招有岗位**，campus/intern 仍为 0（真 0，非参数问题）。
5. **巴斯夫**走 SF 新版 unify 主题的公开 JSON 端点（`POST /services/recruiting/v1/jobs`），
   旧主题（SAP/ZF/勃林格）路径完全不变。
