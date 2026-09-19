# 20260919h 部署说明(叠加在 20260919g 之后)

生成:2026-09-19(DSeek Harness 执行者,分支 `feat/multi-entrance`,基线 `feat/collector-next-4` 82af4f72)
状态:**未部署**。必须由站长明确说"上线"后才可覆盖精灵正式目录;且应在核对完 9-19 首轮实测之后。

## 前提
- 先决条件:精灵现役 = `pipeline-watch/deploy-artifacts/20260918k/`(已于 9-18 20:27 上线),
  且本目录要叠加在 `pipeline-watch/deploy-artifacts/20260919g/`(整合件,26 个运行时文件)之后。
- 本目录**只含相对 g 真正变化的运行时文件**,不含 g/k 已覆盖过的其它文件。

## 文件清单(1 个)
| 文件 | 目标路径(精灵) | 变化 |
|---|---|---|
| `p1_platform_companies.json` | `C:\mcp-suite-collector\qiuzhao\collector\p1_platform_companies.json` | 默认采集集合 **1056 → 1069 家**(+13),新增/合并见下 |

## 相对 g 的配置变化
新增 13 家公司(全部走既有适配器,无需改 Python):
- Moka:`nestlezgc/91899` 雀巢(3 个 site:91899/91898/124026)
- Moka:`bshg/140686` 博西家电、`ubr/117987` 北京环球度假区、`aviagesystems/144382` 昂际航电
- 北森:`csvw` 上汽大众、`spotlight` 光束汽车(新增 `categories {"4":"social"}`)
- Workday:`REDACTED` 杜邦、`aia/wd3/External` 友邦保险、`danaher/wd1/DanaherJobs` 丹纳赫、
  `genmills/wd1/GMI_External_Careers` 通用磨坊(替代被 robots 挡住的 iCIMS 门户)
- SuccessFactors:`careers.akzonobel.com` 阿克苏诺贝尔、`apply.careers.hsbc.com` 汇丰、
  `jobs.adidas-group.com` 阿迪达斯
多入口合并(不增公司):
- `moka["ey/166374"]` 由字符串改为对象,`sites` = 校招 `ey/166374` + 社招 `ey/102474`(官网 ey.com/zh_cn/careers 指向的另一个公开租户)
- `moka["nestlezgc/91899"]` 一行为雀巢合并 3 个公开 Moka 租户

同名/冲突已核对:REGISTRY = DEFAULT = **1069,0 重名**;tupu360 段保持全段 `enabled:false`(robots 全站 Disallow,含强生),iCIMS 段仍 0 家。
`_load_scope_opt_ins` / `PLATFORM_MODULES` / `PLATFORM_HOST_GROUPS` 无需改动:13 家全部落在既有 5 个平台适配器内。

## 无 Python 变化
相对 g,本分支**没有**运行时 `.py` / 别名表 / 适配器改动;测试文件(`tests/test_p1_platform_moka.py`、`tests/test_collector_next_integration.py`)与证据目录 `research/multi-entrance/` 不进精灵运行时。

## 覆盖步骤(沿用 k 的流程)
1. 备份精灵 `deploy` + `qiuzhao`(robocopy,退出码 0/1 均视为正常)。
2. 分片 base64 传 `p1_platform_companies.json`(scp 不可用,单条命令行 >8KB 会报错)。
3. 暂存区对 `SHA256SUMS.txt` 复核:1/1 一致。
4. 覆盖目标路径,覆盖后再复核 1/1 哈希一致。
5. `py_compile` 目标文件所在包 + import 闭包;确认 `REGISTRY = DEFAULT = 1069`。
6. 不改 `run.py`,不改计划任务;次日 06:10 观察。

## 回滚
用备份目录里的 `p1_platform_companies.json` 覆盖回即可(单文件),或直接回退到 g 的 JSON。
