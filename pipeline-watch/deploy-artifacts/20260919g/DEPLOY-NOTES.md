# 部署件 20260919g：tupu360 全站真实岗位采集（配置扩到 60 家）+ 分页硬截断修复 + 采集工具

**叠加顺序：必须在 `20260919f` 之后叠加。** 本包会覆盖 `20260919f` 送进去的
`p1_platform_tupu360.py`（见下"修了什么"），也覆盖 `p1_platform_companies.json`。
`p1_pipeline.py` **本轮没有改动**，不在本包内，也不需要覆盖。

本包**未部署、未 SSH、未碰阿里云、未调飞书、未写库、未 push、未合并 main**。

## 本包内容

| 文件 | 目标 | 类型 | SHA256(前 12) |
|---|---|---|---|
| `p1_platform_companies.json` | `qiuzhao/collector/` | 覆盖 | `bac15cf7bd23`… |
| `p1_platform_tupu360.py` | `qiuzhao/collector/` | 覆盖（= 20260919f 全文 + 分页修复） | `0130b3bbf006`… |
| `tupu360-fullsite-run.py` | `pipeline-watch/` | **新增** | `e83033b62390`… |
| `test_collector_next_integration.py` | `tests/` | 覆盖 | `d94cf410fe69`… |
| `test_p1_platform_tupu360.py` | `tests/` | 覆盖 | `0ec3615ea67e`… |
| `fixtures/tupu360/pharmaron-bj-*.html`（3 个） | `tests/fixtures/tupu360/` | **新增**（仅测试用） | 见 `SHA256SUMS.txt` |
| `DEPLOY-NOTES.md` | — | 本文件 | — |

`RECEIPT-tupu360-fullsite.md` 与表格产物（`pipeline-watch/tupu360-fullsite/*.xlsx|csv`）
留在分支里，**不进服务器部署包**（服务器不需要 4.5 MB 的 xlsx / 18 MB 的 csv）。

## 修了什么（相对 20260919f）

**分页硬截断 600/828**：`_fetch_next_pages(..., page_cap=40)` 把安全上限当成了目标页数，
40 页 × `PAGE_SIZE=15` = 恰好 600，把康龙化成社招的 828 条截成 600 条，而且触顶时
`pagination_exhausted` 还报 `true`。修法：

1. 页数改为站点自报（`共N页`，无页数图例时用 `ceil(共N个职位 / 每页条数)`）；
2. `PAGE_CAP = 120` 仅作安全阀；
3. `_fetch_next_pages` / `_fetch_direct_api` 都返回 `page_cap_hit`，`collect()` 在触顶时
   把 `pagination_exhausted` 置回 `False` 并写 `coverage['page_cap_hit']=True` + 一条错误说明；
4. 新增 3 个单测（真实 56 页夹具）。

同一份真实夹具本地复跑：`OLD(HEAD) 39 页/600 条` → `NEW 55 页/828 条`；
生产重采：`pharmaron-bj/social` = **828 条 / 884 请求 / success / complete=True**。

## 影响面

- `DEFAULT_COMPANIES` **953 → 1005**（+52）。60 行配置里 3 行的公司名已被更早的适配器占用
  （强生→workday、斯堪尼亚→moka、药明康德→硬编码 `p1_sources_41_50`），`setdefault` 保证不顶替。
- 日更请求量：tupu360 全量约 5,772 次公开请求（本轮实测）。日更自身的节流是
  `--platform-workers 2` + `PLATFORM_MIN_INTERVAL=1.0`（`collect_process` 注入的
  `QIUZHAO_PLATFORM_REQUEST_INTERVAL` 默认 `max(1.0, platform_min_interval)`），
  所以日更需要数小时；本轮采集用的是更严的 ≥2.0 s / 3 并发。
  **建议按收据 §5.2 走 `ROTATING_MODULES` + `--platform-rotation`，或窄化 `scopes`，
  或只给部分公司 `enabled`。** 这三条都改配置或 `p1_pipeline.py`，由站长拍板。
- 日更路由不变：tupu360 的 host group 仍是 `tupu360.com`，`PLATFORM_WORKERS` 仍是 2。

## 回退

把 `tupu360` 段里 60 行的 `"enabled"` 改成 `false`（或删掉本包追加的 54 行）即可；
若要连分页修复一起回退，用 `20260919f` 的 `p1_platform_tupu360.py` 覆盖回去
（代价是康龙化成社招会重新被截到 600 条）。

## 校验

```bash
cd pipeline-watch/deploy-artifacts/20260919g
shasum -a 256 -c SHA256SUMS.txt    # 8/8 OK
```

8 个文件与分支源码 `cmp` 逐字节一致（`p1_platform_companies.json`、`p1_platform_tupu360.py`、
`tupu360-fullsite-run.py`、2 个测试文件、3 个夹具）。
