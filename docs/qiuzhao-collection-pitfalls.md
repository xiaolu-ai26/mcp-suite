# 秋招采集与交付踩坑记录

本页只记录有真实收据的复发点；当前交付版本及验收口径以 [日更交付正文](qiuzhao-daily-delivery.md) 为准。私有收据根为 `/Users/maxzhl/Projects/mcp-suite-recovery-20260921/audit-20260928`。方法按来源整理在 [采集方法库](collection-methods/README.md)。

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
