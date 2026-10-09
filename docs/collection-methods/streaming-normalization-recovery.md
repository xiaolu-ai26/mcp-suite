# R3 流式归一化与单阶段恢复

最后验证：2026-10-08后续恢复。证据级别：**独立代码审查 + 真实Windows隔离重放 + 五文件受限生产normalize-only**。原10/2报告保留当时本地回归边界；后续以私有phase的review-manifest-c-normalize-only-cfa4ad28.json、production-install.json及production-normalize-driver-receipt.txt为准。生产输出f6f9ada…、normalize_exit=0、action=normalized-not-published；原预算/截止/采集状态保留，publication仍pending，不把归一化成功说成三层交付完成。

## 适用与选型

适用于已经合法获取并落盘的对象数组 JSON，需要逐条补字段，而整个数组解码及全量快照容易超过内存的任务：招聘、公告、商品目录、资讯均可复用。优先选择流式读取、逐条转换、同目录临时文件、完整验证后原子替换，转换规则通过回调传入，不在 I/O 层猜业务值。

不适用于必须跨记录全局排序/聚合/去重的转换，也不适用于还在被另一个进程写入的文件。JSONL、顶层对象、压缩文件、任意标量数组不能直接传给本实现；不能拿它修复网页分页遗漏、详情缺失、登录限制或尚未收完的快照。损坏输入必须先定位并审查恢复，不可自动跳过坏行。

来源选择仍按 [获取与入口选择](acquisition.md)，来源完整性仍按 [证据与身份](evidence-and-identity.md)；本方法解决的是已采之后的转换与安全恢复，而非新增 HTTP 采集能力。

## 输入、步骤与输出

输入为一个完整 UTF-8 JSON 对象数组、原始 SHA、现有业务转换函数、需要统计的字段，以及同一 writer 锁。实现见 [normalization_io.py](../../qiuzhao/normalization_io.py) 和 [normalize.py](../../qiuzhao/normalize.py)。

1. 对普通文件记录 stat 身份及 SHA；符号链接/目录拒绝。调用者必须持有统一 writer 锁，或者只操作独立副本。
2. 每次读取 64 Ki 字符，解析单个对象，保留每条原有字段及未知字段；不改 ID、顺序或重复次数。
3. 深拷贝该条已有非空统计字段，再调用原业务函数；统计填充、既有值变化，异常标出从 0 开始的记录序号并保留原始异常链。
4. 输出写同目录唯一临时文件。必须读到整个数组结束、确认无尾随文档后才 flush、fsync、关闭输入输出句柄；校验输入未漂移后 os.replace。
5. 返回行数、字段变化、输入/输出 SHA、是否写入及 I/O 模式。`--check` 不创建候选，但仍完整解析和运行转换统计。

任意解析、业务函数、序列化、磁盘、校验或替换错误均不报告成功。非 check 模式空间至少还需要一个输出副本，现有 runner 另有前置备份；不要因为内存降低就放宽磁盘容量门。

## 分页、游标、去重与完整性

本实现的游标是本地解析缓冲区位置，不是来源的 page/cursor。数组关闭符和文件尾全部验完才成功，合法前缀不能证明完整；测试覆盖跨块 Unicode/转义、多种块大小、缺关闭符、尾随逗号和第二个 JSON 文档。

JSON 数组里的重复记录不会去重，匿名记录也不丢弃。去重责任仍属于上游稳定身份与来源合同；不得在内存修复中顺手缩小计划分母或记录数。上游完整分页证据、明确无岗位、请求失败、解析失败、未开始、不适用与未知分类继续原样保留，读取完本地文件不能把它们改成成功。

不保存“归一化到第 N 行”的跨进程 checkpoint；失败重试只重新读已有本地数据，不重访来源，不重采已完成 basic/Tencent/P1。全文件转换不应假装为来源定向补采。

## 详情与字段校验

I/O 层不补伪造详情、不把 detail_fetch_errors 清空、不把 HTTP 200 当完整性成功。逐条回调完全沿用现有 `_normalize_one`，本次没有改招聘类型、行业、地点或新鲜度规则。已有字段快照改为逐条 deepcopy，可正确统计原地修改嵌套容器的情况。

业务规则和数据资产需要另外的真实样例回归，尤其是国家/州/城市、未知值、多地点、remote 与行业枚举；缺少 normalize_tables 的 fallback 不是受控补表。当前合成测试使用回调验证 I/O 和保留行为，不是完整业务字段验收。

## 失败表现与根因边界

已实证的源码风险是整库 `json.load` + 整库 before 快照导致内存需求随文件增长。受限内存实验可复现旧入口 MemoryError；新入口对同样数据成功。**这不证明 2026-10-02 05:42:11 的真实失败就是 MemoryError**，该次 traceback 未读取。

反例：缺 normalize_tables 会走基线已有 fallback，不能仅看 resources.missing 就断言它导致进程失败；JSON 格式错误、字段函数异常、坏资产、权限、磁盘不足和超时必须分别由日志证实。新错误只带记录序号/异常类别，不把整条岗位或潜在敏感内容贴到摘要里；原日志仍需按私有证据管理。

## 重试、幂等与交付

[windows_normalize_retry.py](../../deploy/windows_normalize_retry.py) 默认检查原 run 和依赖身份，不写 jobs/receipt；它会打开公共锁文件，因此不宣称完全不触碰文件系统。apply 需要预期 jobs SHA、receipt SHA 和独立审查绑定；复用现有 Scheduler 检查、portable_runtime 锁、容量门、run_stage_step 的备份/超时/回滚。

只有 terminal partial-or-failed、collection stopped、明确失败的 normalize、已有 P1 段、无 active_batch/不明发布/悬空阶段备份时才允许。10/1 零段特例不扩展。原计划、P1 segments、预算、deadline 和历史 completed_at 保持不变；成功记录 normalized-not-published，不能写 accepted 或 delivered。

step 写退出 0 后仍有核验窗口，故重试前先持久化现有 unsafe_writer 校验屏障，最终校验成功与解除屏障一起落盘。进程中断或校验漂移时屏障保留，后续普通恢复/发布会拒绝；不能手删标志来冒充通过。真实子进程 termination unconfirmed 的安全标志也不得覆盖。

成功后重复调用会因不再是失败 normalize 被拒；失败仍保留原成果/证据，只有符合新一次检查与审查绑定才重试。后续发布仍走 [R2](recovery-and-publication.md)，accepted、served、Base 各有回执。地点纠错另按最终最新 accepted 重算、独审后单次 CAS；旧候选不得覆盖后继。飞书 active 优先同版 Excel 续跑，不改原 Base。

## 实际验证与未验证边界

本地实测、命令及数据身份见 [验证报告](../normalization-recovery-verification-20261002.md)，Windows 操作见 [runbook](../normalization-recovery-runbook-20261002.md)。合成 120000 行/127688890 字节，在 `python -S`、128 MiB 地址空间限制下旧入口失败，新入口通过；字节 SHA 保持一致。`-S` 隔离站点注入，业务回调为 no-op，不能外推为生产性能基准。

仍未验证：真实 10/2 traceback/样本；原业务字段全部回归；Windows msvcrt、NTFS ACL/防病毒、真实 Scheduler/账号/进程中断；断电后的目录项耐久性；超大单条记录性能；生产容量与三层交付。单条上限 64 Mi 字符，不是字节，超限整体拒绝；内存仍包含映射资产和最大记录。缓冲增量解析大记录可能重复解码，不能宣称严格线性时间。stat/SHA 校验不是对不遵守锁的外部写者的原子 CAS。

费用/登录：仅标准库与原项目运行环境，不新增付费 API、不要求认证令牌；本地归一化不需供应商登录。生产发布/飞书的原授权及登录仍是独立前提。


## 2026-10-02 生产实证补充

生产日志已把触发条件从合成风险升级为实际实证：旧入口在 `json.load(f)` 内 `fp.read()` 读取/UTF-8 解码整文件时抛 `MemoryError`。这证明应消除整库文本副本，但不证明当时 RAM/pagefile 的具体压力，也不证明新实现已在目标 Windows 通过。

长记录采用“增量识别对象边界 → 完整对象严格解码一次”，边界状态覆盖字符串、转义、嵌套对象/数组；边界扫描不是 JSON 校验，完整候选仍由严格 decoder 拒绝非法语法、非 JSON 常量和坏尾部。记录超限整批失败，不 salvage 前缀。

恢复安全依赖同样要绑定身份：实际 Scheduler 检查模块、锁、runner、rebase、deploy-manifest 检查器和业务转换依赖都进入冻结契约。独立目标字节 manifest 与仓库 frozen manifest 是两道门；更新前者不能绕过后者。目标机缺失且未经批准的资产保持“缺失”，不为满足 manifest 自动下载旧资产。
