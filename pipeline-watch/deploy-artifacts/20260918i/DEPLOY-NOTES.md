# 部署件 20260918i：字节跳动接入日常链 + 美的集团接入 + 稳定 id 规则

**叠加顺序：必须叠加在 `20260918h` 之后（先覆盖 h，再覆盖本包）。**
本包只包含本次**新增/改动**的 4 个运行时文件，不重复打包 h 的其它 9 个文件；
h 未部署时直接上 i 会缺 `p1_platform_*` / `p1_feishu_public` 等模块。
本包未执行部署、未 SSH 写操作、未写库、未 push。

## 覆盖文件

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（在 h 版基础上追加 2 个注册块 + `stable_id_prefix` 稳定 id 规则） |
| `p1_bytedance_public.py` | `qiuzhao/collector/` | **新增**（字节跳动 p1 适配器，campus/intern/social） |
| `p1_midea_public.py` | `qiuzhao/collector/` | **新增**（美的集团 p1 适配器，campus/intern；social 为 blocked 设计） |
| `bytedance.py` | `qiuzhao/collector/` | 覆盖（`fetch_page` 新增 `recruitment_id_list` / `referer` 形参 + 口径注释；旧调用不受影响） |

`deploy/windows_collector.py`、`guopin.py`、`p1_platform_companies.json` 等 **不变**，
不在本包内。

## 关键说明

1. **新增公司自动进日常链，计划任务无需改参**：两家公司通过 `merged_registry()` 追加到
   `p1_pipeline.REGISTRY`，`DEFAULT_COMPANIES` 由 **924 家变 926 家**
   （50 硬编码 + 874 平台/其它 + 字节跳动 + 美的集团，无重复）。
   `windows_collector.py` 的 p1 步参数（`--workers 8 --platform-workers 3 --max-run-seconds 18000`）
   保持 h 版，不再改动。

2. **字节跳动 scope 口径（本次纠正的重大事实）**：
   `portal_type` 已**不再**决定门户——服务端对 portal_type 1..12 一律返回社招/experienced 结果集，
   这正是 `bytedance.py` 老路径产出「社招岗位被标成校招」的原因。
   真正生效的判别字段是 `recruitment_id_list`（取自官方岗位详情 `recruit_type.id`）：
   - `campus` 校招正式 → `['201']`，门户 `/campus/position`
   - `intern` 校招实习 → `['202']`，门户 `/campus/position`
   - `social` 社招 → `['101']`，门户 `/experienced/position`
   实测（2026-09-18）：campus 2663 条、intern 5578 条、social 命中接口 10000 条上限。

3. **稳定 id 规则（本次唯一共享逻辑改动）**：`validate_result` 原先把每条记录 id 强制写成
   `p1-<sha256>`。字节库里已有 4171 条 `bytedance-<职位id>`、美的已有 146 条 `midea-<positionId>`，
   换命名空间会造成全量重复。现在适配器可在 `coverage['stable_id_prefix']` 声明自己的历史前缀，
   `validate_result` 仅在「声明了前缀 **且** 记录自带 id 确以该前缀开头」时保留原 id；
   未声明的适配器行为与 h 版逐字节一致（有单测锁定）。

4. **完整性（缺席即下线）边界**：
   - 字节 campus/intern 低于接口 10000 上限 → 可达 `success + complete`，参与缺席下线；
   - 字节 social 命中 10000 上限 → 只能 `partial`，**永不**触发缺席下线（避免误删真实在招岗位）；
   - 美的 social 公开校招接口看不到 → `blocked`（空集不等于「没有岗位」）；
   - 美的 campus/intern 按官方 campaign 全量翻页，可 `success + complete`。

5. **请求节奏**：两个适配器默认请求间隔 ≥1.1s，并遵守 `QIUZHAO_PLATFORM_REQUEST_INTERVAL`
   （`p1_pipeline` 注入，下限 1.0s）；公司内 scope 串行（`plan_chains` 每公司一条链），
   不会并发压同一站点。

6. **首次跑对存量的影响（已按真实接口预演）**：字节 campus 快照 2663 条 vs 库里 2244 条校园记录
   → 交集 2222 条**原地更新**、441 条新增、22 条库内旧记录本次未被快照覆盖。
   那 22 条在首次合并时**不会被删除**（它们还没有 `p1_company`/`p1_scope`，缺席规则只管 p1 已接管行），
   从下一次完整快照起才进入正常的缺席下线流程；详见收据「遗留」。

## 校验与回滚

```bash
cd 20260918i && shasum -a 256 -c SHA256SUMS.txt   # 全部 OK
```

回滚：删除 `p1_bytedance_public.py` / `p1_midea_public.py`，并用 `20260918h/`（或 `20260918/`）
的同名文件恢复 `p1_pipeline.py` / `bytedance.py`。回滚后两家公司自动退出日常链，
其余 924 家不受影响。
