# 收据 · 按公司而不是按平台重查入口 + 多入口合并采集(2026-09-19)

分支 `feat/multi-entrance`(worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/multi-entrance`,基线 `feat/collector-next-4` 82af4f72)。
**未部署、未 push、未合并 main、未碰阿里云、未写飞书生产 Base、未读取/打印令牌、未登录、未绕验证码/签名、未终止任何进程。**

## 0. 一句话结论
上一轮"按平台"判死的公司里,**至少 13 家其实有公开可读的入口**:雀巢(3 个 Moka 租户)、安永(补社招租户)、博西家电、北京环球度假区、昂际航电、上汽大众、光束汽车、杜邦、友邦保险、丹纳赫、通用磨坊、阿克苏诺贝尔、汇丰、阿迪达斯——全部用**已有适配器**接上,默认采集集合 **1056 → 1069 家**;强生 Workday `jj/wd5/JJ` **不是空租户**(实测 campus 1 / intern 10 / social 195),维持启用,tupu360 仅作对照(18/4/322)因 robots 全站 Disallow 继续留档。抽样 8 家证明:**平台接口 = 该公司该 ATS 的官网全集**,差异只出现在"官网域名把多个 ATS 租户/系统聚合在一起"(雀巢、安永、强生),因此官网 careers 页应作为**入口发现通道**,不必对每家再并行采一遍官网。

## 1. 变更清单(相对 82af4f72)
| 文件 | 类型 | 说明 |
|---|---|---|
| `qiuzhao/collector/p1_platform_companies.json` | 运行时 | +13 家、1 家改多入口(`ey/166374`),默认集合 1056→1069;REGISTRY=DEFAULT=1069,0 重名 |
| `tests/test_p1_platform_moka.py` | 测试 | +3 条:雀巢三入口、EY 双租户、跨 site 合并去重 |
| `tests/test_collector_next_integration.py` | 测试 | 家数断言更新 1056→1069(注释同步) |
| `research/multi-entrance/` | 证据 | 探针脚本 + 各租户 `report.json`(原始 HTML/列表 JSON 已删,避免仓库膨胀) |
| `pipeline-watch/deploy-artifacts/20260919h/` | 部署件 | 见 §11 |
| `pipeline-watch/RECEIPT-multi-entrance.md` | 收据 | 本文件 |

无运行时 `.py`/适配器改动:13 家全部落在既有 Moka/北森/Workday/SuccessFactors 适配器内;`categories {"4":"social"}` 是既有配置能力。

## 2. 雀巢结论(实测明细)
**根因确认**:上一轮只看了 wxtemp 租户 `nestle.tupu360.com`(微信 OAuth),没有找官网的其它入口。

官方校园站 `stg.nestlecareers.cn`(Drupal 10 主题,未登录可读 HTTP 200)在导航与正文里给出的真实投递入口:
- `campus-recruitment/nestlezgc/91899` —— 校招/实习入口(trainee-programme、internship-programme 的"立即投递")
- `social-recruitment/nestlezgc/91898` —— 社招入口(导航 experienced-professionals)
- 站长实测的 `social-recruitment/nestlezgc/124026` —— 另一个公开社招租户

三站实测(列表接口 `POST /api/outer/ats-apply/website/jobs/v2`,完整浏览器头 + 站点自身 JSON):
| 入口 | HTTP | 列表总数 | 按 hireMode/commitment 分类 |
|---|---|---|---|
| `/campus-recruitment/nestlezgc/91899` | 200 | 68 | campus 55 / intern 13,全部 open |
| `/social-recruitment/nestlezgc/91898` | 200 | 225 | social 218 / intern 7,open 217 + pause 8 |
| `/social-recruitment/nestlezgc/124026` | 200 | 50 | social 50,全部 open |

`nestle.com.cn/jobs/search-jobs` 裸请求 403(Cloudflare/Akamai 类),不再追。
**处理**:`moka` 段新增一行 `nestlezgc/91899`,name=雀巢,`sites`=[91899, 91898, 124026];适配器扫全部 site、按 posting id 去重合并(合并后 campus 55 / intern 20 / social 218 ≈ 293,详见配置 note)。
**校招系统类型判明**:不是另一套系统,就是 Moka;`campus-home`/`trainee-programme` 均指向 `nestlezgc/91899`。

## 3. 全量复核表(foreign-universe `接不了` + `当期中国0条`,26 家)
方法:每家至少 3 种取法(完整浏览器头 GET / 站点自身 JSON 接口 / 必要时 Playwright),≤10 次请求、间隔 ≥2 秒。

| # | 公司 | 试过的入口 | 结论 | 中国条数(列表口径) |
|---|---|---|---|---|
| 1 | 雀巢 | stg.nestlecareers.cn 各子页 / Moka 91899·91898·124026 / nestle.com.cn(403) | ✅接入 Moka 3 入口 | campus 55 + intern 20 + social 218 |
| 2 | 上汽大众 | 北森 `csvw.zhiye.com`(桌面+移动) | ✅接入北森 | social 9 |
| 3 | 丹纳赫 | `jobs.danaher.com` → Workday CXS `danaher/wd1/DanaherJobs` | ✅接入 Workday | intern 1 + social 115 |
| 4 | 光束汽车 | 北森 `spotlight.zhiye.com`(category 4 生产招聘) | ✅接入北森(categories 4→social) | social 1 |
| 5 | 北京环球度假区 | Moka `ubr/117987` | ✅接入 Moka | intern 5 |
| 6 | 博西家电 | Moka `bshg/140686`(campus 404 / social 200) | ✅接入 Moka | intern 58 |
| 7 | 友邦保险 | `aia.com.cn` 官网 → Workday `aia/wd3/External` | ✅接入 Workday | campus 21 + social 129 |
| 8 | 巴斯夫 | SF `basf.jobs` | 已在库(此前已修) | social 36(旧值) |
| 9 | 昂际航电 | Moka `aviagesystems/144382` | ✅接入 Moka | intern 18 |
| 10 | 杜邦 | Workday `REDACTED` | ✅接入 Workday | social 4 |
| 11 | 汇丰 | SF `apply.careers.hsbc.com`(官方 emergingtalent) | ✅接入 SF | campus 6 + intern 7 + social 287 |
| 12 | 阿克苏诺贝尔 | SF `careers.akzonobel.com` | ✅接入 SF | social 14 |
| 13 | 阿迪达斯 | SF `jobs.adidas-group.com` | ✅接入 SF | campus 1 + intern 2 + social 65 |
| 14 | 德莎 | Moka `tesa/142951`(200 但 0 条)/ `jobs.tesa.com`(404)/ `careers.tesa.com`(SSL fail)/ tesa.com career(无 ATS 指纹) | 未接入 | 0 |
| 15 | 摩根士丹利 | `careers.morganstanley.com.cn`(jobs2web,search 0 行)/ `careers.morganstanley.com`(SSL EOF) | 未接入(适配器读不到) | 0 |
| 16 | 景顺长城基金 | 北森 `invescogreatwall`(桌面+移动 200,无 PortalId) | 未接入(WAF) | - |
| 17 | 沃茨 | `en.watts.cn/careers` → Cloudflare 403 | 未接入(403) | - |
| 18 | 美赞臣 | 北森 `meadjohnson` / `mj` / `meadjohnsonchina` 均 404 | 未接入(租户未找到) | - |
| 19 | 莱茵 TÜV | `tuv.com/jobs-and-career`(指向 classic SF `career5.successfactors.eu`,非 CSB)/ `jobs.tuv.com` 404 / `careers.tuv.com` SSL | 未接入(需 classic SF 或新适配器) | - |
| 20 | 西部数据 | SmartRecruiters `api.smartrecruiters.com/v1/companies/WesternDigital/postings?limit=100` → totalFound 338(公开) | 未接入(无 SmartRecruiters 适配器) | 338 全站,中国未筛 |
| 21 | 路易威登 | tupu360 `louisvuitton`(微信,disabled)/ `lvmh.com/en/join-us/our-job-offers`(Phenom) | 未接入(Phenom ref 未在匿名页解析出) | - |
| 22 | 辉瑞 | `pfizer.com.cn` 校招页 → Moka `pfizercampus/142244` + tupu360 `pfizercampus`;Moka 返回 `necromancer` 但页面不暴露 IV | 未接入(Moka 加密 IV 缺失;tupu360 robots Disallow) | - |
| 23 | 金佰利 | 51job 微站 `campus.51job.com/KCC2026MT`(无公开 CtmID) | 未接入 | - |
| 24 | BDA咨询 | `wx.bda.com/career/?cat=2`(200,JS 壳,自建) | 未接入(自建 JS) | - |
| 25 | BIW | 未找到官方招聘入口(仅聚合站) | 接不了(已试官网搜索与直接探测) | - |
| 26 | Ameco | 北森 `fjjwwx.zhiye.com`(桌面 200 / 移动 200,均无 PortalId) | 未接入(WAF) | - |

## 4. tupu360 14 家复核(全部保持 `enabled:false`)
| 公司 | 复核结论 |
|---|---|
| 雀巢 | ✅ 改由 Moka 接入(见 §2),tupu360 行继续留档 |
| 强生 | Workday 已启用(见 §6);tupu360 对照 18/4/322,robots 全站 Disallow 留档 |
| IQVIA / 礼来 / 舍弗勒 | 官网 `jobs.iqvia.com`、`careers.lilly.com`、`schaeffler.com/en/career` 均 403(WAF);无替代公开入口 → 留档 |
| 宝马 | `bmwgroup.jobs` 读取超时;tupu360 careersite 公开但 robots Disallow → 留档 |
| 茵梦达 | 未发现非 tupu360 公开入口 → 留档 |
| 德昌电机 | tupu360 租户三频道"共0个职位";官网 `johnsonelectric.com/en/careers` 未暴露 ATS → 留档 |
| 太太乐 | 官网 SSL 失败;与雀巢同集团(tupu360 nestle 租户)→ 留档 |
| 奥托立夫 / 科赴 / 路易威登 / Google / 博世华域转向 | 官网未暴露公开 ATS(科赴/路易威登/奥托立夫页面为 JS 壳)→ 留档 |

## 5. iCIMS 8 家复核
iCIMS 租户 robots 全站 Disallow(见 `RECEIPT-foreign-ats-b.md §6`),按公司找替代入口:
| 公司 | 替代入口结论 |
|---|---|
| 通用磨坊 General Mills | ✅ Workday `genmills/wd1/GMI_External_Careers`(实测中国 1 条)→ 已接入 |
| 百事 PepsiCo | 已在库:`job51 pepsico2027`(51job 校招微站),iCIMS 仍不碰 |
| AMD | `careers.amd.com` 仍指向 iCIMS(`careers-amd.icims.com`),无替代 → 留档 |
| 施耐德 | `se.com/.../careers` 403;无替代 → 留档 |
| 佳明 Garmin | 官网 JS 壳,未暴露 ATS → 留档 |
| 是德 Keysight / 怡安 Aon | 官网仍指向 iCIMS,无替代 → 留档 |
| ZS | 官网 JS 壳,未暴露 ATS → 留档 |

## 6. 强生专项
| 入口 | 实测结果 | 处置 |
|---|---|---|
| Workday `jj/wd5/JJ`(现役,此前"猜测租户") | campus **1**、intern **10**、social **195**(list_total 207) | **确认非空,维持启用**(实测通过) |
| tupu360 `jnj`(对照,robots 全站 Disallow) | campus **18**、intern **4**、social **322**(合计 344) | 仅对照,`enabled:false` 不变 |
| 官网 `chinacampus.jnj.com.cn` | 即 tupu360 careersite 自定义域(与上同一来源) | 不单独采 |

**结论**:tupu360 数据更全,但平台 robots 全站 Disallow,按与猎聘/BOSS/智联校园一致的口径不启用;Workday 租户有实数,继续作为强生的生产入口。是否为了这 138 条差异破例启用 tupu360,留给站长决策(见 §12)。

## 7. "官网 vs 平台哪个全"抽样(8 家)
| 公司 | 平台/租户 | 平台中国条数 | 官网 careers 入口 | 官网读数 vs 平台 |
|---|---|---|---|---|
| 英伟达 | Workday `nvidia/wd5/NVIDIAExternalCareerSite` | 200(6/40/154) | nvidia.com careers(同一 Workday) | 相等 |
| 花旗 | Workday `citi/wd5/2` | 55(0/3/52) | jobs.citi.com → `citi.wd5/2` | 相等 |
| 安永 | Moka `ey/166374` | 8(2/6) | ey.com/zh_cn/careers → 另指 `social-recruitment/ey/102474` | **官网多 221 条社招**;已合并 |
| 雀巢 | Moka 91899/91898/124026 | 293 | stg.nestlecareers.cn → 3 个 Moka 租户 | 合并后相等 |
| 恒安集团 | 北森 `hengan1` | 8(8/0/0) | hengan.com → `hengan1.zhiye.com` | 相等 |
| 宝洁 | Phenom `PGBPGCCN` | 56(12/4/40) | careers.pg.com.cn(同一 Phenom) | 相等 |
| 罗氏 | Phenom `ROCHGLOBAL` | 268(0/48/220) | careers.roche.com(同一 Phenom) | 相等 |
| 高通 | Eightfold `careers.qualcomm.com` | 96(1/18/77) | careers.qualcomm.com(同一 Eightfold) | 相等 |
| (附加)强生 | Workday `jj/wd5/JJ` | 206 | chinacampus.jnj.com.cn(tupu360) | 官网多 138 条,但 robots Disallow |

**结论**:对"官网就是该 ATS 租户"的公司,平台接口 = 官网全集(6/8 完全相等);差异只来自**官网域名聚合多个租户/系统**(安永、雀巢、强生)。因此正确做法是:**采平台接口为主,官网 careers 页只用于发现遗漏入口**,而不是对每家并行采官网。本轮已用此方法修好雀巢、安永。

## 8. 多入口合并与去重
- **同平台多入口**:沿用 Moka 段既有 `sites` 数组。`nestlezgc/91899` 一行合并 3 个租户、`ey/166374` 一行合并校招+社招;`p1_platform_moka.collect` 顺序扫 `sites_for(key)` 的全部 site,`seen` 集合按 posting id 去重,coverage 里记录每个 site 的 `source_list_totals`。
- **跨平台多入口**:强生是唯一候选(Workday + tupu360),但第二来源因 robots 全站 Disallow 继续 `enabled:false`;当前无需为跨平台 `sources` 引入新调度层(REGISTRY 是"公司名→单模块")。设计取舍与理由见 §12;后续若 Max 批准 tupu360,再按"两行不同 source_tag + 合并去重"扩展。
- **去重不会互删**:任务级去重在 `p1_pipeline.merge_records`,按 `p1_identity`(公司+来源记录 id)更新;同一公司不同 site/平台的记录 id 不同,互不覆盖;同 id 跨 site 在适配器层已去重。

## 9. 单测与回归
- 新增 3 条:`test_real_config_nestle_multi_entrance`、`test_real_config_ey_merges_campus_and_social_tenants`、`test_multi_site_merge_dedups_shared_ids`(伪造两个 site,共享 id 只出一次,两 site 均被扫)。
- `pytest tests/test_p1_platform_moka.py tests/test_collector_next_integration.py -q` = **24 passed**。
- 全量 `pytest tests/`:
  - 本分支 `feat/multi-entrance`:**4 failed / 642 passed / 55 skipped**
  - 基线 `feat/collector-next-4` 82af4f72:**4 failed / 639 passed / 55 skipped**
  - 失败清单逐条相同(`test_codes_kind` 已知 flaky + `test_core` + `test_p1_pipeline` + `test_schema` 3 条既有);**未新增失败**,多出的 3 条 passed = 本次新增单测。

## 10. 对外请求记账
口径:适配器调用按 `request_budget` 上限计,探针按 ledger 计;均间隔 ≥2 秒、无登录、无 cookie、无签名、无验证码绕过。**未逐请求落盘,以下为分批上限/估算。**
| 批次 | 估算请求 |
|---|---|
| 雀巢/EY Moka 列表探针 + 官网子页 | ~35 |
| Moka/北森/Workday 适配器实测(spec1/2/3 + EY/bshg) | ~600 |
| SuccessFactors 实测(akzonobel/MS CN/HSBC/adidas/tesa/tuv) | ~150 |
| 强生 Workday + tupu360 对照 | ~110 |
| 抽样 8 家平台实测 + 官网页抽取 | ~200 |
| iCIMS/tupu360 官网 ATS 抽取 + Workday 租户探活 | ~60 |
| **合计(估算区间)** | **约 850–1000,低于 1200 上限** |

注:没有单点超过"每家 ≤10 次"的**复核**探针;批量适配器实测是接入验证(与生产同一路径),预算由 `max_requests` 显式封顶。

## 11. 部署件 20260919h
`pipeline-watch/deploy-artifacts/20260919h/`:
- `p1_platform_companies.json`(唯一运行时变化;sha256 `cd4c403b…`)
- `SHA256SUMS.txt`(3/3 `shasum -c` OK)
- `DEPLOY-NOTES.md`(叠加在 20260919g 之后的说明)
- `PROD-BACKUP-MANIFEST.txt`(以 k + g 为前提;单文件回滚)

**未部署**;须站长明确说"上线"、且核对完 9-19 首轮实测后再按 k 的流程执行。

## 12. 遗留与待站长决策
1. **tupu360 合规**:该平台 robots 全站 Disallow。强生对照显示 tupu360 比 Workday 多 138 条、雀巢等 6 家也只在 tupu360 公开可读。是否允许这一来源(以及 wxtemp 微信租户)需 Max 明确;当前全部 `enabled:false`。
2. **按公司复核方法应固化**:建议在发现流程里加一步"官网 careers → ATS 租户/接口抽取",本轮靠它救回雀巢/安永/丹纳赫/友邦/汇丰等;可做成 SOP 或小脚本。
3. **待新适配器的来源**:SmartRecruiters(西部数据等,公开 API)、Phenom(LVMH 等,LVMH 匿名页 ref 未解析)、classic SuccessFactors(莱茵 `career5.successfactors.eu`)、Moka 新版加密(`pfizercampus/142244` 不暴露 IV,需从 app bundle 找 IV 来源)。
4. **仍读不到**:摩根士丹利 CN jobs2web、北森 WAF(Ameco/景顺长城)、Cloudflare(沃茨)、51job 无 CtmID(金佰利)、自建 JS(BDA)。
5. **播放件体积**:13 家新增约 +3% 请求;预计每日链总时长仍在 2–4.5h 内,建议首轮实测后核对 p1 起止时间。
