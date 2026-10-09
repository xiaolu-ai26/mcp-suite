# 数据采集方法库

最后核对：2026-10-09（增补平台 SOP 执行与证据绑定；各方法的历史验证时间分别保留）。范围：当前仓库源码、测试及历史运行收据；这是方法索引，不是今日运营状态。当前状态只维护在 [日更交付正文](../qiuzhao-daily-delivery.md)。本文不触发采集、付费调用、部署或平台写入。

方法可迁移到资讯、商品、公告、目录、岗位等数据。`company/scope/job` 在复用时分别对应来源主体、采集范围、记录；涉及招聘分类及飞书交付的契约仍是本项目专用，不能原样套到其他业务。

| 需求 | 方法与文档 |
|---|---|
| 选择入口、接口分页、HTML 列表详情、动态页面、RSS、多入口 | [获取与入口选择](acquisition.md)：A1–A5 |
| 完整性、空列表、不适用、schema 漂移、稳定身份、字段更新、缓存 | [证据与身份](evidence-and-identity.md)：E1–E3 |
| 断点、有界重试、失败隔离、单 writer、CAS、未知接受 | [恢复与发布](recovery-and-publication.md)：R1–R2 |
| 容量、保留、NTFS 压缩、幂等交付、真实阶段监控 | [容量与交付](capacity-and-delivery.md)：D1–D3 |
| 已采快照归一化失败、大 JSON 内存与原子恢复 | [流式归一化与单阶段恢复](streaming-normalization-recovery.md)：R3（本地回归，未生产验收） |
| 实际踩坑后回填 | [条目与验收模板](TEMPLATE.md) |

## 证据等级

- **本项目运行实证**：运营正文引用真实收据；仅证明对应历史事件，不证明下一次自然运行成功。
- **本次实际本地回归**：R3 的可运行测试与受限内存探针见 [验证报告](../normalization-recovery-verification-20261002.md)；不代表 Windows 或供应商实测，独立审查待完成。
- **本项目源码与回归覆盖**：存在实现、夹具或测试，本次文档工作核对源码和测试内容，未重新运行测试，也未访问供应商。
- **参考未实施**：AIHOT 固定只读快照 `f6c2952a9984d4840442558be114ac959b512b0c`；借鉴设计，未安装、运行或接入本项目。Fable 两轮建议也是建议，不能升格为部署事实。

私有证据根目录：`/Users/maxzhl/Projects/mcp-suite-recovery-20260921/audit-20260928/`。条目只列收据相对文件名；不复制原始岗位、密钥、身份凭据或完整每日计数。AIHOT 路径均相对其 `consult-fable51/reference/AIHOT/` 快照，故不用仓库内 Markdown 链接伪装成本项目文件。

## 持续扩充

解决一个实际问题后，在相关条目增加“触发条件 → 最小修复 → 回归证据 → 真实运行验收”，更新该条目的最后验证时间与证据等级。方法不同才新增条目；只是新租户、字段或失败样本时追加案例。所有新来源先隔离校验，不能靠改 `complete` 或隐藏未知类别来提高成功率。

维护者须核对代码符号、相对链接、适用边界、费用与登录条件；敏感收据留私有目录。交付中出现的每日数量或版本只链接运营正文，避免维护第二份事实。代码改动交给执行与独立审查线；本文不承诺未验收的优化（自然运行无人值守、24 小时缓存收益、来源级失败归因等）。

项目事故、复发与回滚证据维护在 [踩坑正文](../qiuzhao-collection-pitfalls.md)，当前版本与三层交付结果维护在 [日更交付正文](../qiuzhao-daily-delivery.md)。

## 2026-10-08 成功方法绑定标准

成功方法必须绑定正式运行同入口代码、可复用公司/租户/入口/scope配置、字段映射、可执行SOP及失败恢复、脱敏真实代表样本/回归、受审版本与真实运行终态证据。公司参数与method_id沿现有配置/生成清单维护；同平台共用一个SOP，不逐公司复制流程。配置/账本产生runtime状态，本库不重复每日计数。AI辅助修方法，不作为日更重新探索的依赖。固定范围与阶段状态见[唯一日更正文](../qiuzhao-daily-delivery.md#0-2026-10-08-实施方案与阶段状态入口)。


## 平台 SOP 导航（2026-10-09）

| 复用场景 | 唯一方法位置 |
|---|---|
| 北森完整同 run 列表缓存、字段融合与租户枚举 | [北森 SOP](acquisition.md#beisen-sop)、[执行与证据绑定](acquisition.md#platform-sop-execution) |
| Eightfold / Phenom 严格列表契约、分页与字段来源 | [完整性契约](evidence-and-identity.md#ef-phenom-contract)、[执行补充](evidence-and-identity.md#pagination-sop) |
| Workday 首总数与后页零哨兵 | [Workday 契约](evidence-and-identity.md#workday-contract)、[执行补充](evidence-and-identity.md#pagination-sop) |
| BOC 公告与原生岗位双粒度、嵌入正文及共同条件 | [BOC SOP](acquisition.md#boc-sop) |
| 理想汽车严格外包枚举与公开用工说明 | [LiAuto SOP](acquisition.md#liauto-sop) |

新增条目的私有证据根为 `/Users/maxzhl/Projects/qiuzhao-lzh-handoff-20261002/phase-20261008/`，正文只列脱敏收据文件名。方法初稿基线为公开 main `95bed58d77196af8905044022dbd34ef47662026`（含 PR37/38）；2026-10-09 最终核对的实际树 HEAD 为 `a2f40003b89981b58ec7466b5a3a52b939b4bec7`（PR39 merge，head `468c0b0da68d1b82ef4c56eb1da3acb9590bcbf8`）。只更新方法正文，不覆盖源码；具体实现仍按受审文件 SHA 绑定。独审与 Windows 隔离回归证明受审方法，尚不证明新版本生产安装、逐公司完整成功或请求节约比例。固定 1124 名称 / 3372 company-scope 的目标与每日真实状态仍仅维护在日更正文。

Dayee合法空列表的请求级性质证据与51job未验证scope纠错见[同一证据正文](evidence-and-identity.md#dayee-request-scope)，平台契约不可互套。
