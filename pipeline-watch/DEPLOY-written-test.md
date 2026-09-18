# 部署说明 ·「笔试情况 / 免笔试」字段第一期

> 本文件是 `feat/written-test` 分支的部署清单。**本期不部署**:服务器侧与精灵侧的任何改动都必须由站长明确说"上线"后,按本文件执行,并遵守「备份 → 逐字节校验 → 覆盖 → py_compile/import → 次日观察 → 留回滚件」的既有流程。

## 1. 影响面一览

| 侧 | 不部署时 | 部署后 |
|---|---|---|
| 服务器 MCP | 现状不变 | `jobs_search`/`jobs_stats` 多一个 `written_test` 筛选与返回字段;老库自动按 `未注明` 返回,**向后兼容** |
| 精灵采集机 | 现状不变 | 每日 06:10 normalize 后岗位带 `written_test`;发布到服务器后 MCP 即生效 |
| 飞书 Base | 现状不变 | 映射代码就绪但**默认关闭**;站长确认建列后才开 `QIUSHAO_LARK_WRITTEN_TEST=1` |

## 2. 服务器侧(阿里云 114.215.188.109,**须站长确认后另行部署**)

| 文件 | 说明 | 回滚 |
|---|---|---|
| `core/server.py` | 工具 schema 新增 `WrittenTest` 参数、`GroupBy` 增加 `written_test`、工具描述补口径三句 | 备份原件即可回滚 |
| `qiuzhao/tools.py` | `FILTER_DEFAULTS`/`check_filters`/`evaluate` 增加 `written_test`;`Dataset` 增加 `written_test_as_of`;`search/stats/detail` 返回体加该字段 | 同上 |
| `qiuzhao/v4_fields.py` | `WRITTEN_TEST_VALUES` 常量;`CORE` 增加 `written_test`;`convert()` 增加 6 字段(缺字段按 `未注明`) | 同上 |
| `qiuzhao/written_test.py` | 新模块(常量兜底;`tools.py` 不直接依赖它,放上更稳) | 删除即可 |

要点:
- 服务器**不需要**标注表 `qiuzhao/data/written_test_labels.json`;标注由精灵在 normalize 阶段写进库,服务器只读。
- 老库(无 `written_test` 字段)行为:`written_test = 未注明`,其余 5 个附属字段不出现在返回里(空值丢弃)。
- 部署后建议自查:`jobs_stats(group_by="written_test")` 应返回 4 个组(免笔试/部分免笔试/有笔试/未注明)或至少 `未注明` 一组;`jobs_search(written_test="未注明")` 的 notices 必须带"不等于免笔试"提示。

## 3. 精灵侧(采集机 `C:\mcp-suite-collector`,**须站长确认后另行部署**)

| 文件 | 说明 |
|---|---|
| `qiuzhao/data/written_test_labels.json` | **标注真源**:62 条公司级标注(带逐字原文/官方 URL/核对时间) |
| `qiuzhao/written_test.py` | 查表 + 岗位描述明文覆盖 + 幂等写回 |
| `qiuzhao/normalize.py` | 新增 `_sync_written_test()`;标注表缺失时**一个字都不改** |
| `qiuzhao/v4_fields.py` | 字段定义(与服务器同版本) |
| `qiuzhao/collector/lark_sync_enrichment.py` | 可选:飞书 4 列映射函数(默认不写) |
| `qiuzhao/collector/lark_sync_index.py` | 可选:开关与字段列表;**必须以精灵现役版为底改**,不要整文件覆盖(现役版末尾同步段调 `lark_sync_daemon`) |

生效链路:06:10 `deploy\windows_collector.py` → normalize(写 `written_test`)→ 发布到服务器 → 飞书同步(如启用)。

验证建议(部署次日):
1. `runs\<日期>\receipt.json` 的 normalize 步骤返回里 `written_test` 计数 > 0。
2. 抽查库内:`科大讯飞` 的岗位应出现 `部分免笔试` 与两类原文;`中国邮政` 应出现 `有笔试` + "网上申请—简历接收和筛选—线上笔试—…"。
3. 线上 MCP:`jobs_search(written_test="免笔试")` 应返回长安跨越/悦联商业/益尔听力/安能一局/海南海大科技园这几家的岗位。

回滚:恢复 4 个文件的原件(部署前备份),标注表可直接删除——`normalize.py` 在标注表缺失时不改任何记录,库内已写入的 `written_test` 会保留,需要清理时用备份的 `jobs.json` 覆盖。

## 4. 飞书(可选,独立于本期)

1. 站长确认后在生产 Base 建 4 列:`笔试要求`(建议单选,选项锁定 `免笔试/部分免笔试/有笔试/未注明`)、`笔试依据原文`(多行文本)、`笔试原文链接`(文本/链接)、`笔试核对时间`(文本或日期)。
2. 在精灵侧设置环境变量 `QIUSHAO_LARK_WRITTEN_TEST=1` 后再跑同步。
3. 不建列就打开开关会因列不存在写入失败——**默认关闭就是这个原因**。

## 5. 本次没有做的事

未部署任何一侧、未 SSH 写文件、未改计划任务、未动生产 Base、未调写飞书接口、未合并 main、未 push、未读取或打印任何令牌、未终止任何进程。
