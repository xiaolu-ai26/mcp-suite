# 部署件 20260918j：外企第二批（名单驱动 + 大易/51job 适配器）

**叠加顺序：直接叠加在 `20260918h` 之后（整文件覆盖）。** 本包基线 `feat/collector-next-2`
的 `p1_pipeline.py` 与 `20260918h/p1_pipeline.py` 经 `diff` 验证**逐字节相同**，因此本包
`p1_pipeline.py` = 20260918h 全文 + 本批追加的 2 个独立注册块，可直接覆盖，不需要其它补丁。
本包**未部署、未 SSH、未碰阿里云、未调飞书、未写库、未 push**。

## 本包相对 20260918h 的变化

1. `qiuzhao/collector/p1_foreign_01.py`（新增）：**大易 hotjob.cn 通用适配器**。
   `POST /wecruit/positionInfo/listPosition/<SU>`（form 编码）+ `/listPositionDetail/<SU>`，
   官方 `recruitType` 映射 `1=campus 2=society 12=intern 13=overseas`（读自租户 SPA bundle，
   非猜测）。列表/详情交错拉取，预算耗尽仍发布已读岗位为 `partial`；重复分页视为终止页而非报错。
2. `qiuzhao/collector/p1_platform_51job.py`（新增）：**前程无忧企业校招专页适配器**。
   公开服务端渲染页（`campus.51job.com/<slug>/`），按官方投递锚点 `Apply.aspx?CtmID=`
   识别岗位，取锚点所在最小 `<li>/<tr>` 块中锚点之前的文本为岗位名；显式修正 UTF-8
   解码（页面只在 `<meta>` 声明 charset）。robots.txt 无禁止（302 → missing.php）。
3. `qiuzhao/collector/p1_platform_companies.json`（覆盖）：新增/调整配置行，见下表。
4. `qiuzhao/collector/p1_pipeline.py`（覆盖）：**仅在现有注册块之后追加 2 个独立注册块**
   （`p1_foreign_01`、`p1_platform_51job`），未改任何既有行。
5. 可选（仅测试）：`test_p1_foreign_01.py`、`test_p1_platform_51job.py`、
   `test_collector_next_integration.py`（顺序断言同步）、`fixtures/`。

## 配置变化（`p1_platform_companies.json`）

| 块 | 变化 |
|---|---|
| `moka` | **+15**：普华永道 `pwc/148260`、毕马威 `kpmg/74356`、高露洁棕榄 `colpal/28788`、德州仪器 `ti/142216`、拜耳 `bayer/148388`、特斯拉 `tesla/41460`、大众汽车集团(CARIAD) `vwa/142785`、达能 `danone/170511`、达美乐中国 `REDACTED`、伊顿 `eaton/166618`、阿特拉斯科普柯 `atlascopcogroup/150203`、神龙汽车 `dfmc/170464`、**安永 `ey/166374`** |
| `beisen` | **+1**：基恩士 `keyence` |
| `dayee`（新块） | **+7**：德勤、康师傅、ZARA、广汽集团、益海嘉里、迪卡侬、ZURU |
| `job51`（新块） | **+1**：百事 `pepsico2027` |
| `workday` | **+1**：英特尔 `intel/wd1/External` |
| 实测后剔除 | 博西家电、德莎（0 条）；Shopee（WAF）；Ameco/广汽丰田/美赞臣（北森 PortalId 缺失）；可口可乐/耐克/GSK/星巴克/摩根士丹利/安永 SF（当期中国岗位 0 条，参数已存档待复测） |

## 覆盖文件

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（= 20260918h 全文 + 2 个追加注册块） |
| `p1_platform_companies.json` | `qiuzhao/collector/p1_platform_companies.json` | 覆盖 |
| `p1_foreign_01.py` | `qiuzhao/collector/p1_foreign_01.py` | **新增** |
| `p1_platform_51job.py` | `qiuzhao/collector/p1_platform_51job.py` | **新增** |
| `test_*.py` + `fixtures/` | `tests/` | 可选（仅测试，生产可不覆盖） |

## 部署后注意

- 平台公司不在硬编码 50 家内，**不要**塞进 `--companies` 整批 `--apply` 跑法；
  走每公司一次的 `--adapter` 子进程调用（与批次 1 外企一致）。
- 大易/51job 的 8 家公司默认按三 scope 调度，其中 51job 非 campus scope 会返回
  `success/0 条 + note`（官网只发布校招），属预期。
- 礼貌限速：`QIUZHAO_PLATFORM_REQUEST_INTERVAL`（生产缺省 0，验证设 2.0）；
  预算 `QIUZHAO_PLATFORM_REQUEST_BUDGET`（生产缺省不限）。
- 建议后续把 `p1_foreign_01` 并入 `PLATFORM_MODULES` / `PLATFORM_HOST_GROUPS`
  （同 host 串行），该处非"追加块"，留给调度维护者。
