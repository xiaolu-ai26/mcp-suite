# 恢复、失败隔离与发布

最后验证：2026-10-01（源码与历史收据）。采集恢复、发布恢复、交付恢复各使用自己的状态和版本。

## R1 断点续采、有界重试与失败隔离

**输入与选型**：长批次、分段采集、网络临时错误或本地资源争用。目标是保留已采成果并在原预算内继续。

**步骤**：启动时持久化逻辑 run、配置绑定、deadline、预算、单元结果 → 每段 checkpoint → 成功阶段不重跑 → 区分远端瞬时、本地锁/资源、预算耗尽、结构性范围不支持与访问阻断 → 仅符合策略的失败有界重试 → 保存 retry queue 与次数 → resume 校验计划兼容、沿用原截止 → 输出 success/partial/blocked/未开始/未知 → 出错仍记录真实终态与未发布成果。

**代码与验证**：[checkpoint、resume_compatible、failure_reason、retry_tier、is_full_success](../../qiuzhao/collector/p1_pipeline.py)、[_retry_transient 与运行阶段](../../deploy/windows_collector.py)、[恢复器](../../deploy/windows_recover_run.py)、[调度回归](../../tests/test_p1_scheduling.py)、[部分成果回归](../../tests/test_collector_partial_keep.py)。

**运行案例**：运营正文第 3.3、3.5 节：原 run 续跑保留预算与成功腾讯阶段；容量阻断/零 P1 段仍须按真终态报告，未开始不转为完成。容量拒绝用延期继续采集的历史部署见第 3.1 节。

**失败反例**：重置 checkpoint 或新预算重跑旧日更；所有失败统一 timeout；4xx、认证限制无界重试；锁 busy 提高平台并发；停止采集却直接标全流程 completed。

**验收**：恢复 run 身份和原截止不变；已成功阶段不重复；失败有明确原因与上限；预算错误不冒充来源失败；pending publication 与 collection.state 分开。有界二次尝试/更精细原因码的建议须先实现与回归，不能把 Fable 建议写成投产。

**费用/登录**：预算内重试消耗网络与运行时间；现有公开来源不新增付费服务；登录、验证码、签名协议不是自动重试可解决的问题。

## R2 冻结快照、单 writer、CAS 与未知接受核对

**输入与选型**：持续数据集上传、多个采集段、人工恢复或迁移可能与线上版本冲突；写入必须能证明父版本和接受结果。

**步骤**：冻结候选并计算 SHA → 检查 writer 锁与 unsafe_writer → 读取 expected_base → 容量预检 → CAS 上传 → 明确接受后推进工作基线与 lineage → 冲突时使用 baseline/collected/latest 三方 rebase，有限次数重试 → 回执丢失或上传超时标 unknown/unconfirmed → 读取服务器真实 SHA/父版本并核对候选，确认后才推进或重试 → 另核 served 与最终交付。

**代码与验证**：[publish_snapshot、accept_publication、unconfirmed_alignment、refuse_unsafe_writer](../../deploy/windows_collector.py)、[rebase_files、publish_with_rebase](../../deploy/windows_rebase.py)、[receiver](../../deploy/windows_receiver.py)、[发布回归](../../tests/test_windows_publication.py)、[分段回归](../../tests/test_segmented_publish.py)。

**运行案例**：运营正文第 4 节记录一次 CAS 与父版本链；第 3.3 节 accepted 后定时服务曾仍旧版；私有 `first-CAS-20260930T0358.json` 是可复查证据索引，不在此复制数据。源码 `freeze_new_removed` 保持发布边界的下架冻结；不得借迁移顺便开放退役。

**失败反例**：超时立即再发导致不明重复；上传进度当 accepted；多个 writer；旧基线覆盖新版本；整行 rebase 被描述为字段合并；放宽 complete 触发缺席下架。

**验收**：候选 SHA、accepted SHA、lineage 与工作基线吻合；未知接受已核对；冲突处理有上限；当前下架冻结与来源守卫生效；served 必须是进程实际加载的 SHA。**费用/登录**：上传与快照存储；生产通道按既有授权凭据执行，方法文档不存密钥、不要求新 API 账单。
