# 部署件 20260919f：外企补齐 C —— tupu360 平台适配器

**叠加顺序：直接叠加在 `20260918k`（精灵现役）之后，整文件覆盖。**
本包基线 = `feat/collector-next-3` @ `2b123c2`，与精灵现役 `20260918k` 的 `p1_pipeline.py`
**逐字节相同**，因此本包的 `p1_pipeline.py` = 现役全文 + 本批追加的 **1 个独立注册块**
（`p1_platform_tupu360`，外加 `PLATFORM_MODULES` / `PLATFORM_HOST_GROUPS` / scope opt-in
的 3 处纯新增行），可直接覆盖，不需要其它补丁。

本包**未部署、未 SSH、未碰阿里云、未调飞书、未写库、未 push、未合并 main**。

> 若后续先叠加 `20260919b` / `20260919c` / `20260919d` / `20260919e`，请改走整合分支
> (`feat/collector-next-4`) 的累积部署件：`p1_pipeline.py` 与 `p1_platform_companies.json`
> 是多任务共同修改的文件，逐个叠加会互相覆盖。

## 本包相对 20260918k 的变化

1. `qiuzhao/collector/p1_platform_tupu360.py`（**新增**）：tupu360（图谱天下）多租户招聘站
   适配器。三种取法，按稳定性排序：
   - `html`（默认）：带完整浏览器请求头的 GET 打官方服务端渲染职位列表页
     `https://careersite.tupu360.com/<tenant>/position/index?recruitmentType=<TYPE>`，
     再调站点自带的 `POST /<tenant>/position/nextPageList`（`offset`/`max`）翻页；
   - `api`（回退）：跳过列表页，直接分页 POST `nextPageList`——这是列表路由被重定向到
     hash 路由 SPA 的租户（强生 `chinacampus.jnj.com.cn`）唯一的公开读法；
   - `headless`（兜底）：Playwright/Chromium 以普通访客身份打开列表页读渲染后 DOM
     （`QIUZHAO_TUPU360_HEADLESS=1` 或 `fetch_channel='headless'` 才启用）。
   列表有 A / B 两种模板，A 按表头**位置**取列（IQVIA 把 业务/职位类别/工作地点 三列
   复用同一个 `e-salary` class，按 class 取会串列），B 按卡片结构取 `pid`/标题/城市/
   职能/招聘人数/发布于。详情页取 `position-description` + `positionStatus`。
2. `qiuzhao/collector/p1_platform_companies.json`（覆盖）：新增 `tupu360` 段
   **15 行 = 14 家公司 + 1 行 `_README`**。其中 **6 家 enabled**（实测通过、进入日更），
   **8 家 `enabled: false`**（实测 blocked，保留调查行与入口 URL，翻一个开关即可启用）。
   `_load_companies()` 跳过 `_` 开头的键与 `"enabled": false` 的行，因此 disabled 行
   **不会**进 `REGISTRY`、不会进每日默认集合。
3. `qiuzhao/collector/p1_pipeline.py`（覆盖）：**仅在现有注册块之后追加 1 个独立注册块**，
   未改任何既有行。该块用 `REGISTRY.setdefault`（不是 `update`），因为 `强生` 已有既批
   准的 Workday 条目 `jj/wd5/JJ`，追加块不得顶替别的适配器已拥有的公司。
   另外 3 处纯新增：`PLATFORM_MODULES` + `p1_platform_tupu360`（同 host 并发门控）、
   `PLATFORM_HOST_GROUPS` + `'tupu360.com'`、`_load_scope_opt_ins()` 的 section 元组
   + `'tupu360'`。
4. 可选（仅测试）：`test_p1_platform_tupu360.py`（30 个夹具单测）、
   `test_collector_next_integration.py`（顺序/家数断言同步：948 → 953）、
   `fixtures/tupu360/`（9 个公开页面录制夹具）。生产可不覆盖。

## 配置变化（`p1_platform_companies.json` → 新 `tupu360` 段）

| key | 公司 | host / tenant | 状态 | 实测 |
|---|---|---|---|---|
| `iqvia` | IQVIA 艾昆纬 | careersite.tupu360.com / iqvia | enabled | campus 12 / intern 5 / social 12，全 success+complete |
| `lilly` | 礼来 | careersite.tupu360.com / lilly | enabled | campus 18 success；intern/social 官方 0 条 → blocked |
| `schaeffler` | 舍弗勒 | careersite.tupu360.com / schaeffler | enabled | social 70；intern 主频道 + 官方自定义频道 `TECHNOLOGYRUITMENT`；campus 0 条 |
| `bmw` | 宝马 | careersite.tupu360.com / bmw | enabled | social 19 success+complete；campus/intern 0 条 |
| `innomotics` | 茵梦达 | careersite.tupu360.com / innomotics | enabled | campus 3 / intern 5 / social 36 |
| `jnj` | 强生 | chinacampus.jnj.com.cn / jnj | enabled（`detail: list`） | campus 18 / intern 4 / social 322，全 success+complete |
| `johnsonelectric` | 德昌电机 | careersite.tupu360.com / johnsonelectric | **disabled** | 租户在，全部公开频道 0 条 |
| `nestle` | 雀巢 | nestle.tupu360.com | **disabled** | wxtemp 微信专属；careersite slug 已停用 |
| `taitaile` | 太太乐 | nestle.tupu360.com（同租户） | **disabled** | 同上 |
| `autoliv` | 奥托立夫 | autoliv.tupu360.com | **disabled** | wxtemp 微信专属 |
| `louisvuitton` | 路易威登 | louisvuitton.tupu360.com | **disabled** | wxtemp 微信专属 |
| `jntl` | 科赴 | jntl.tupu360.com | **disabled** | wxtemp 微信专属；slug `kenvue` 已停用 |
| `google` | Google 谷歌 | google.tupu360.com | **disabled** | wxtemp 微信专属 |
| `boschhuayu-steering` | 博世华域转向 | boschhuayu-steering.tupu360.com | **disabled** | wxtemp 微信专属 |

净增默认集合：**948 → 953**（+IQVIA 艾昆纬 / 礼来 / 舍弗勒 / 宝马 / 茵梦达；
强生因既有 Workday 条目同名，tupu360 条目按 `setdefault` 不生效，待站长定夺是否替换）。

## 覆盖文件

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（= 20260918k 全文 + 1 个追加注册块 + 3 处纯新增行） |
| `p1_platform_companies.json` | `qiuzhao/collector/p1_platform_companies.json` | 覆盖（= 现役全文 + 新 `tupu360` 段） |
| `p1_platform_tupu360.py` | `qiuzhao/collector/p1_platform_tupu360.py` | **新增** |
| `test_p1_platform_tupu360.py` | `tests/test_p1_platform_tupu360.py` | 可选（仅测试） |
| `test_collector_next_integration.py` | `tests/test_collector_next_integration.py` | 可选（仅测试） |
| `fixtures/tupu360/*.html` | `tests/fixtures/tupu360/` | 可选（仅测试） |

## 部署后注意

- 6 家 tupu360 公司都不在硬编码 50 家里，**不要**塞进 `--companies` 整批 `--apply` 跑法；
  走每公司一次的 `--adapter` 子进程调用（与批次 1/2 外企一致）。
- 三 scope 默认全跑。官方没有的频道返回 `blocked` + `note`（例如礼来 intern/social、
  宝马 campus/intern、舍弗勒 campus），这是设计内结果，不是故障。
- 礼貌限速：`QIUZHAO_PLATFORM_REQUEST_INTERVAL`（生产缺省 0；实测设 2.2）；
  预算 `QIUZHAO_PLATFORM_REQUEST_BUDGET`（生产缺省不限；实测每 租户×scope 25）。
- 大规模频道（强生 social 322 条、舍弗勒 social 70 条）在**无预算**时一次性拉全：
  强生走 `nextPageList` 分页（`detail: list`，不请求详情页，5 次请求拿满 322 条）；
  舍弗勒 social 需 1+5 次列表 + 70 次详情 ≈ 76 次请求，与其它平台适配器同量级。
- **robots.txt 合规提示**：`careersite.tupu360.com/robots.txt` 与每个租户 host 都返回
  `User-agent: * / Disallow: /`（平台级一刀切声明）。适配器按任务书只做公开只读 GET/POST、
  不登录、不做 OAuth、不绕验证码，并保留每租户预算与 ≥2s 间隔；**是否长期日更需站长按
  robots 声明拍板**（收据 §7 遗留 1）。
- tupu360 与 51job 一样是共享上游平台，已登记 `PLATFORM_HOST_GROUPS='tupu360.com'`，
  同 host 单元受 `PLATFORM_WORKERS` / `PLATFORM_MIN_INTERVAL` 门控。
- 强生：`PLATFORM_HOST_GROUPS` 里仍是 `myworkdayjobs.com`（现有 workday 条目生效）。
  若站长决定改用 tupu360 的 18 条校招 + 322 条社招，删掉 `workday` 段的 `jj/wd5/JJ`
  一行即可（`setdefault` 会让 tupu360 接管）。
