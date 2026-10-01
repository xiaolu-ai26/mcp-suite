# 容量、交付与监控

最后验证：2026-10-01（源码与历史收据）。这些方法适用于任何大文件快照与外部表格交付，具体门槛和平台限制以运行代码为准。

## D1 容量预估、有界保留与 NTFS 冷文件压缩

**输入与选型**：大快照、多次发布、备份累积、临时副本使空间不足。压缩适用于 Windows NTFS 的已完成冷文件；不等于搬移、删除或 ExFAT 修复。

**步骤**：测当前文件大小、上传上限、临时副本峰值与发布频率 → 计算预检门与保留目标 → 从 accepted/served/Base/回滚/在途状态冻结保护集合 → 只选择已完成且未保护的冷候选 → 归档传回、逐件 SHA 与原始内容验证 → 删除前重核保护集合及元数据 → 遇未知删除核对真实文件 → NTFS 场景仅原位压缩已授权冷文件，逐件核内容 SHA/大小/mtime → 重测空闲与运行峰值。

**代码与验证**：[gate_required、plan、secure_archive、apply、resolve_unknown](../../deploy/server_backup_retention.py)、[receiver 容量门](../../deploy/windows_receiver_rotation.py)、[Windows capacity_check](../../deploy/windows_collector.py)、[保留回归](../../tests/test_b1_backup_retention.py)。receiver 当前门为 `2 × jobs bytes + 上传上限 + 256 MiB`；整日容量还需按发布次数与临时空间评估，不能只满足一次门。

**运行案例**：运营正文第 3.3–3.5 节；私有 `retention-20260929T1818-final.json`、`windows-capacity-recovery-compression-summary-20260930.json`、`windows-cold-930-compress-summary-20261001.json`。压缩是一次性历史处置证据，仓库没有通用自动 NTFS 压缩工具，不提供无审查批量命令。

**失败反例**：复用昨天删除白名单；归档上传中就计已释放；压缩短窗口达标宣称整日容量足够；压缩活跃 run；降低门槛掩盖峰值。

**验收**：保护版本仍在；归档完整且可恢复；逐件删除有收据；未知结果核对；压缩前后逻辑内容不变；真实空闲与峰值足够才续跑。**费用/登录**：外盘与服务器容量、传输成本；既有 SSH 通道；不调用付费模型。删除仍按每次明确授权范围执行。

## D2 数据交付、schema 修复与幂等恢复

**输入与选型**：已 accepted 的快照要投影到用户平台，可能出现字段重命名、类型漂移、导入超时。用固定版本 staging，验收后切换。

**步骤**：核 accepted 及后继链 → gzip 流取回并 SHA 核验 → 冻结投影/运行依赖 manifest → 生成 Excel → 导入原 Base 的 staging 表 → 按字段 ID 核 schema，保留原属性修复 → 清空行、verify 行数/ID/单元格/视图 → switch → 更新 ledger；失败只续 active 的相同 SHA 与阶段。同版已 delivered 返回 up_to_date。自动起批必须读取真实 collection.state 与 settlement；不得把 stopped 当完整结算。

**代码与验证**：[deliver、deliver_latest、run_settlement、preflight](../../deploy/windows_excel_delivery.py)、[R1 阶段目录](../../deploy/feishu_r1)、[交付回归](../../tests/test_windows_excel_delivery.py)、[自动批次回归](../../tests/test_b1_deliver_latest.py)。

**运行案例**：运营正文第 3.3–3.5、8 节；Excel 导入斜杠列名变竖线、字段类型/选项失败、分页读取 EOF 后同版恢复。私有 `base-schema-slash-verify-8ab-20261001.json`、`base-schema-five-verify-8ab-20261001.json`。这是人工修复后实证，自动 schema 修复候选是否部署以执行线与运营正文为准。

**失败反例**：失败新开批再导入；只改字段名丢失类型属性；操作旧正式表而非 staging；未核 SHA 就下载活跃文件；手改阶段 ledger 跳过验证；把自动起批算无人值守全流程。

**验收**：同 SHA 幂等；所有 staging 表 schema、行数、ID 集合、单元格及视图通过；切换读回；active=null；三层同版；人工介入次数可见。**费用/登录**：现有飞书登录与权限、平台导入额度、openpyxl 依赖；不恢复逐行写 API 或创建新 Base，不新购 API。

## D3 监控真实阶段与持续改善

**输入与选型**：每日长流水线、来源成功率和用户可用性监控；success、进程退出码和业务交付不能混为同一指标。

**步骤**：按计划键对账结果键 → 分别记录已尝试/未开始/未知、success/partial/blocked → 核列表与详情分母 → 记录预算/锁/远端/schema 失败分类 → 核 collection、publication、accepted、served、Base 与各时间 → 报告人工介入、延期、冻结退役、资源缺失 → 将实际问题回填方法案例与回归证据。没有测到的量写未知，不推算为 0。

**代码与验证**：[unit_records、evaluate_alerts](../../qiuzhao/collector/collection_gap.py)、[缺口测试](../../tests/test_collection_gap.py)、[日更权威正文](../qiuzhao-daily-delivery.md)。AIHOT `sources/collect.ts`、`operations/alerts.ts`、`operations/reports.ts` 的来源健康、失败退避与告警仅参考；本项目不继承分钟调度、产出评分、单轮资讯上限或付费评分。

**运行案例**：运营正文第 3.5 节中 accepted/served/Base 同旧版，采集新变化尚未发布，证明服务在线不能代表今天已交付。Fable 两轮的来源级粗分与 SLO 是待核/建议；不复制其数量为当前事实。

**失败反例**：3372 个机械单元全部尝试叫 100% 数据完整；pending=[] 判成功；字段修复后直接宣布未来无人值守；旧收据当今日实时状态。

**验收**：每状态有对应收据与版本；分母定义清晰；未知与不适用保留；时间与人工动作可追溯；新 SLO 有自然运行证据才验收。**费用/登录**：优先读取小状态投影与既有收据，无需全库下载或付费模型；供应商实时查询需既有访问权限。
