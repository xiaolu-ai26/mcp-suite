# Pro normalize 修复验证记录（2026-10-02）

适用基线：`bcae6e546a025a3a84c5bfe4aa9d619a38db9c79`。**独立审查待完成，生产未部署。** 当前网页会话没有独立 Agent，没有把自查称为独审；用户对本轮 Pro 实现的授权覆盖旧任务书的执行模型限制，历史审查归属保留。

## 输入和能力

GitHub 连接器实际读取了公开源码、私有 README/TASK_PROMPT/READY、准备审查摘要、Release 附件元数据；Release 的二进制归档未下载，context-inventory 超大文件的内容未成功读取，不能声称逐项读过 5275 条。公开日更正文完整读取，踩坑正文和方法索引/R1/R2完整读取，源码按本次调用链读取；没有把整个仓库逐行审查。

实际可用：本地 Linux、Python 3.13.5、pytest、Git；GitHub 分支写入已验证。直接联网 clone/DNS 和 Release 二进制下载不可用。无法访问精灵 Windows、生产服务器、真实飞书或当前 Scheduler；没有读取或索取账号凭据。

精确重建的四个基线文件逐个以 Git blob 身份核验：

| 文件 | 基线 blob SHA |
|---|---|
| qiuzhao/normalize.py | ea251f9b5989aaa9f536b86264b38477afd30f1c |
| docs/qiuzhao-daily-delivery.md | 7cbc07310974bcfc6244bfc3888525b12ef73675 |
| docs/qiuzhao-collection-pitfalls.md | a6ff890ab9d056368a1b19ed4073e8d449d5f500 |
| docs/collection-methods/README.md | 12704949dbf4e6e119f9683ee34e1b8348d7f0cd |

本地验证树是上述精确文件和本次新增文件的聚焦 checkout，不是完整仓库，也没有伪造 bcae 提交。Git diff 的旧文件身份来自真实基线；应用/反向检查在此聚焦 checkout 执行，完整仓库检查另需在精灵执行。

## 已运行

`python -m pytest -q tests/test_normalization_io.py tests/test_windows_normalize_retry.py`：最终 79 passed。I/O 测试实际读写临时文件，覆盖分块解析、Unicode、完整结束、坏输入、回调失败、原记录/重复记录保留、模式、fsync/替换失败、漂移与 check 不写入。恢复测试使用真实文件与 Linux flock，但 runner 的阶段进程和 Scheduler 为 stub；覆盖只调用 normalize、计划/预算/截止保持、重复执行拒绝、未知发布/active_batch/锁/容量/资产漂移拒绝、中断校验屏障。

测试开发过程保留：第一次 75 passed/1 failed，失败是并发改写测试先触发“尾随内容”而不是预期“身份漂移”；改为等长外部改写后验证准确场景，第二次 76 passed。补充校验窗口中断、异常 exit 2 与屏障解除测试后为 79 passed。没有删掉失败安全场景或将失败隐藏为 skip。

静态检查：本次 Python 文件 py_compile；最终 diff 的 whitespace 和补丁正反向检查以包内 evidence 的实际日志为准。没有运行供应商 API、正常采集、发布、Base 写入或删除归档。

## 内存风险复现（合成，不是生产根因）

输入 120000 行、127688890 字节；SHA256 `3f9f87ba5af881528c1eb3c28ff41934f93f95236820676864dc235c0a63173e`。探针抽取真实旧/新 normalize_file 入口，业务回调为空操作，测量 I/O 而非完整业务归一化：

```bash
python -S tests/probes/normalization_memory_probe.py --module BEFORE/qiuzhao/normalize.py --input ISOLATED/jobs.json --limit-mib 128
python -S tests/probes/normalization_memory_probe.py --module qiuzhao/normalize.py --input ISOLATED/jobs.json --limit-mib 128
```

| 同样的隔离条件 | 结果 | 峰值 RSS KiB | 探针时间秒 |
|---|---|---:|---:|
| bcae 旧入口 | MemoryError | 14720 | 0.000（显示精度） |
| 新入口 | 成功，120000 行 | 16124 | 3.264 |

新入口完成后 SHA 与输入一致。最初不加 `-S` 的两次探针均失败：当前站点注入令 Python 初始虚拟内存约 413332 KiB，已超过 128 MiB 限制，不能用于算法对比。两次失败和后续隔离实测日志都保留，未挑选旧失败/新成功的不同限制条件。

## 未运行、阻断和非结论

10/2 normalize.log、完整 receipt 和真实 staging 未取得，因此实际错误可能是内存、数据、资产、权限、超时或其他异常，**仍未归因**。代码确认缺表本身走 fallback，不能断言缺表导致该次失败。流式修复不会自动解决坏数据或业务映射异常。

完整 normalize/v4/company 业务测试、已有分段/发布/partial-keep/recovery 回归、Windows 锁/进程/Scheduler/路径、NTFS、实际安装、原 run 重放、accepted/served/Base 检查均未运行。缺完整运行树、资产、历史夹具或目标环境；命令和前提见 runbook。79 项不等于全项目通过，不等于 HTTP 分页、详情、枚举、全部计划 key、长期容量已验收。

原 deploy/qiuzhao-deploy-manifest.json 保持不变；其 normalize 冻结 SHA 将与修复文件不同，原部署/交付门应继续拒绝。必须独审最终字节后明确更新涉及环境的冻结清单，并将新 normalization_io.py 纳入清单，而不是删除检查或把本地测试当审查 PASS。10/1 特例绑定旧 normalize SHA，修复后该特例也应 fail closed，不更新其硬编码身份来绕过。

## 独立审查清单

审查者需针对最终提交/补丁与 SHA 确认：逐条转换语义与原业务函数一致；严格输入变化可接受；坏尾部不提交；源/候选身份、并发和 Windows 句柄约束；新重试中 exit 0 与校验屏障的中断顺序；不改变原预算和计划；缺资产状态如实保留；新依赖部署冻结；真实故障重放及必要目标回归。审查结论只签对应最终字节，修改后重新审核。
