# 部署件 20260918f:外企平台适配器(Workday CXS + SAP SuccessFactors)

**叠加顺序:在 `20260918e`(阿里/腾讯缺口批)之后覆盖。** 本包与 e 一样只做「append-only 注册块」,
不得回退 e 的阿里/腾讯块。

## 覆盖文件

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_platform_workday.py` | `qiuzhao/collector/p1_platform_workday.py` | 新增 |
| `p1_platform_successfactors.py` | `qiuzhao/collector/p1_platform_successfactors.py` | 新增 |
| `p1_platform_companies.json` | `qiuzhao/collector/p1_platform_companies.json` | 覆盖(在 b 版本上追加 `workday` / `successfactors` 两个块) |
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖(**累积版**:20260918e 全文 + 外企注册块) |

## 关键说明

1. **`p1_pipeline.py` 是累积版**:本分支从 `feat/banks-batch1` 分出,不含 e 的阿里/腾讯块。
   若直接覆盖本分支原文件会丢 e 的块,因此本包内的 `p1_pipeline.py` = `20260918e` 的
   `qiuzhao/collector/p1_pipeline.py` 全文 + 在最后一个注册块之后追加的外企块,可直接整文件覆盖。
   逐字校验:文件同时含 `alibaba_headless` / `tencent_music` / `p1_platform_workday` /
   `p1_platform_successfactors`,且 `py_compile` 通过。
2. **配置行**:`p1_platform_companies.json` 在原有 `beisen` / `moka` 基础上新增
   `workday`(9 家)与 `successfactors`(3 家:jobs.sap.com / jobs.zf.com /
   jobs.boehringer-ingelheim.com)。新增公司只需在对应块加一行。
3. **SF 主题兼容**:SuccessFactors CSB 列表页有两种主题——多数用 `<tr class="data-row">`,
   部分(如勃林格殷格翰)用 `<div class="row job job-row">` 且 `jobTitle-link` 带附加 class。
   适配器两种都解析,否则会把有岗位的租户静默读成 0 条。
4. **请求预算/限速**:`QIUZHAO_PLATFORM_REQUEST_BUDGET` 缺省为不限(生产全量);
   验证/试跑请显式设为 20。`QIUZHAO_PLATFORM_REQUEST_INTERVAL` 控制每请求间隔秒数,
   生产缺省 0,验证设 2。
5. **不写库、不改变每日整批**:两个适配器与平台适配器走同一条 `--adapter` 子进程路径,
   不进入硬编码 50 家的 `--companies` 整批 `--apply`。
6. 首批只读实测(预算 20/租户、请求间隔 2s):Workday 9 家(6 家校招 success + 3 家实习
   success)、SuccessFactors 3 家(SAP / ZF / Boehringer)均取到官方岗位;明细见
   `pipeline-watch/RECEIPT-foreign-companies.md`。
7. 测试与夹具在分支内提交,不属于运行时部署必需文件。
