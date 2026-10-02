# 秋招采集与交付踩坑记录

本页只记录有真实收据的复发点；当前交付版本及验收口径以 [日更交付正文](qiuzhao-daily-delivery.md) 为准。私有收据根为 `/Users/maxzhl/Projects/mcp-suite-recovery-20260921/audit-20260928`。方法按来源整理在 [采集方法库](collection-methods/README.md)。

## 2026-10-02 新增调查：normalize 失败不等于缺表导致

**证据级别：交接报告 + 基线源码 + 本地合成回归；不是已证实的生产根因。** 交接报告的 05:42:11 终态为 normalize failed、collection stopped、publication pending；具体 normalize.log 和 staging 未读到，不给出猜测性的异常行号。

基线 `normalize_file` 同时持有整库 JSON 和已有字段快照，内存随整库增长；缺表则 fallback，并非直接抛出缺文件异常。正常 resume 在未完成 P1 的分支可能先再采一段才重新 normalize；现有独立 recover 又要求 normalize=0。这两个源码风险分别以流式 I/O 和 normalize-only 入口处理，不复用 10/1 精确候选 guard，不盲补旧地点表。

修复保留所有合法对象记录及重复次数，完整读到数组结束后才原子替换；截断尾部、坏记录、非对象记录、非 JSON 数值、超大记录、源漂移或磁盘失败均拒绝，不以合法前缀冒充完整成果。retry 只操作原 run 的 normalize 阶段，使用原锁、预算不变；成功仍不是已发布。退出 0 到校验完成之间如中断，unsafe_writer 校验屏障继续阻断恢复与发布。

实际本地测试和失败过程见 [验证报告](normalization-recovery-verification-20261002.md)；Linux 受限内存探针只证明 I/O 风险可复现，不证明 10/2 就是 MemoryError。独立审查待完成，Windows 和真实故障样本未运行，生产未部署。回滚仅恢复核验过的代码备份，不回滚 accepted 数据、不删 checkpoint、不伪改失败收据；步骤见 [操作手册](normalization-recovery-runbook-20261002.md)。

## 1. P1 零段时遗漏 normalize 导致已采成果未发布

- 现象：2026-10-01 原 run 的 basic 与腾讯已完成，P1 原截止已过，`p1_segments=[]`；末尾读取 `steps['normalize']` 抛出 KeyError。
- 影响：basic 新增12、更新1284与腾讯更新2留在 staging，publication pending；不能以 collection complete 宣称交付完成。
- 根因：正常 P1 段负责 normalize + publish；零段时没有任何段执行 normalize，末尾却假定该键存在。
- 最小修复：PR #21 仅为受审10/1源54fdd、基线8ab、依赖及prepared3e784开放 fail-closed publication-only恢复；不重开P1、不延deadline、不对未知run跳过normalize。
- 验证：历史独立 GPT-6 Sol 审查与Git集成PASS、22聚焦测试；2026-10-01 23:10:41 Windows原子部署回读SHA `1b5468413cabc9863cd7eab07f4da5a2d93e2b7b89257e86770397e3f6ef05f5`。实际发布和三层交付仍以随后收据确认。
- 回滚：部署前原件 `windows_collector.py.pre-eb66d69-20261001`，SHA fdb4565e；回滚前须无活动collector并复核生产接受状态。
- 是否复发：本次为首次明确零段触发；通用未知run仍拒绝，不宣称已覆盖所有将来运行。
- 收据：`run-terminal-20261001.json`、`collector-zero-segment-fix/deploy-gpt61-20261001.json`、`publication-only-start-gpt61-20261001.json`。

## 2. Excel 导入改变斜杠字段名并使 schema 修复复发

- 现象：9/28、9/29、9/30版本的Excel导入把“国家/地区”“州/省”改成竖线；后续字段类型或选项更新亦失败。
- 影响：自动起批后卡schema，需要人工修新待切换表并同版续跑；不能称全流程无人值守。
- 根因：fix按原名查字段；完整PUT还需保留选项元数据和默认值；CLI合法JSON错误遗漏stderr。独审另发现description遗漏及仅旧ID黑名单的staging限制不足。
- 最小修复：私有候选精确alias、完整选项/默认值/description保留、stderr捕获、当前批次正向ID绑定保护；未通过独审前不得进入共享运行依赖。
- 验证：原候选2026-10-01独立GPT-6.1 Sol low审查BLOCK，8聚焦通过但发现上述两项；修订版仍待复审和真实供应商回执。
- 回滚：受控部署清单仍冻结原版本；私有候选可撤销，不影响正式Base。
- 是否复发：已三轮复发；候选完成不等于线上修复。
- 收据：`base-final-2ddc-20260928.json`、`base-final-a8ad-20260929.json`、`base-schema-five-verify-8ab-20261001.json`、`schema-fix-candidate-20260929.json`。

## 3. 容量恢复与任务状态不是长期容量验收

- 现象：服务器9/25–28容量拒绝；Windows9/30再度不足；10/1归档收据running但进程已退出，只有5件deleted。
- 影响：待发布或提前停止；陈旧running可能掩盖未完成归档。
- 根因：发布备份持续增长；局部压缩只释放一次空间；中断未写最终outcome。
- 最小修复：服务器归档先按当前accepted/served/Base/在途重算保护及plan，逐件传回校验后精确删除；Windows按运行写入量实算预算，不降低门、不删未核归档。
- 验证：既有受审工具可用；新批次未运行前只报计划。10/1 23:13 C空闲约22.12GB、D约66.7GB是实时容量，不代表整日预算已满足。
- 回滚：删除前已核验归档可恢复；保留最新备份与当前/在途版本。
- 是否复发：双端已复发，长期有界策略仍待实测。
- 收据：`retention-apply-20261001.json`、`windows-capacity-projection-20260930T1117.json`、`windows-cold-930-compress-summary-20261001.json`。


## 4. 2026-10-02 normalize 整文件 UTF-8 解码 MemoryError

- 现象：第7段 P1 后 normalize 退出1；生产 traceback 为 `normalize.py:424 json.load(f)` → `fp.read()` → UTF-8 decode → `MemoryError`。receipt 为 collection stopped、publication pending；第7段 P1 成果保留但 normalize 回滚。
- 根因：直接失败点已证实为约800MB级 jobs.json 的整文件读取/文本解码内存分配失败。历史 RAM/pagefile 压力未知；20:54 的 806,915,187-byte staging 是回滚后版本，不证明与失败瞬间输入相同。
- 最小修复：PR #27 流式逐对象处理；第二轮把长对象改为增量边界扫描、完整对象只严格解码一次，并补齐安全依赖冻结门。normalize-only 恢复仍不采集、不发布、不改预算/截止/Base。
- 验证：第二轮网页沙盒聚焦84 passed；新字节仍待独审和 Windows 锁/Scheduler/NTFS/timeout/staging 重放。前6次成功 normalize 均 `tables_loaded=false`，不盲补历史 normalize_tables.json。
