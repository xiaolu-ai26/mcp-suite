# RECEIPT: guopin-auto-campaigns(国聘专场从"写死 6 个"改为"每天自动发现 2027 届校招专场")

分支:`feat/guopin-auto-campaigns`(从 `main` HEAD `59dca7b` 开出,本地 commit,**未 push、未合并**)
日期:2026-09-18 14:2x  执行者:DeepSeek Harness  范围:动态专场发现 + 合并策略 + 可观测 + 单测 + 离线发现验证。**未部署、未 SSH、未碰阿里云、未调飞书、未写库、未 push。**

---

## 0. 结论摘要

- **只改"专场从哪来"**:新增 `discover_campaigns()` 从首页横幅接口发现专场;逐专场抓取、完整性校验、"缺席即下线"、按来源原子合并的既有逻辑**一行未改**。
- **动态发现成立**:用真实横幅接口(38 条)实测,发现 **14 个** `iguopin.com` 承载的 2027 届校招专场(保底 5 个全部在列);另有 **12 条** 2027 校招横幅指向**外部企业招聘站**(工行/农行/招行/邮储/华电/中远海运/中国电子/国新/电信/邮政/移动在线/北京地铁),因解析不出 `https://<alias>.iguopin.com` 而**如实记入 `skipped`,不猜**;其余 12 条为非 2027/非校招横幅被过滤。
- 生产采集集合从当前实际 **5 个**(6 减已下线的 cgnpc)提升到 **14 个**。
- 硬约束遵守:只改 `qiuzhao/collector/guopin.py` 与 `tests/`(加本收据);国聘横幅接口**共调用 2 次**(上限 2);未跑整套采集、未写库;Mac 磁盘未生成大文件(唯一落盘文件 `/tmp/guopin_banners_raw.json` 18,981 字节,在 /tmp)。

---

## 1. 必须先记录的分支基线矛盾(重要)

任务书写"从 `main` 开",且"`guopin` 有专场 success 即整体 `partial`,你不用碰这块"。**核实后发现事实与任务书不一致**:

- 当前 `main` HEAD = `59dca7b`;**不含**已上线精灵的 `fix/collector-partial-keep` 改动(该分支 HEAD `4155851`,`main` 是它的父提交,`git merge-base --is-ancestor 3bb0632 main` = NO)。
- 精灵上现役 `guopin.py` = partial-keep 版(sha256 前 8 `22e5f6ad`),它把整体状态从 `partial_failure` 改为 `partial`;`main` 版没有这一行。
- `main` 的 `run.py` 校验门本来就是 `status in {success, partial}`(与 partial-keep 版一致),所以**如果只把 main 版 guopin.py 覆盖上去,遇任一专场失败会退回 `partial_failure` → 被 run.py 拒收 → 静默回退已上线的"部分成功保留"修复**。

**处理**:按要求从 `main` 开分支;为保证"精灵上只需覆盖 guopin.py 一个文件"不回归,`guopin.py` 里**保留了那一行已上线的整体状态改动**(见 §2 diff 末尾),即本分支的 guopin.py = 精灵现役版 + 动态发现。`git diff main..HEAD` 因此只含 `guopin.py` / 新测试 / 本收据;若总控希望严格"不碰这块",可基于 `fix/collector-partial-keep` 重新取一次 diff,内容等价。

---

## 2. 改了什么(关键 diff)

唯一生产文件:`qiuzhao/collector/guopin.py`(+80 / -11)。要点:

**2.1 `CAMPAIGNS` 降级为保底清单,去掉已下线的 `cgnpc`;新增常量**

```python
CAMPAIGNS=(   # 保底清单,只在大盘发现失败时使用
    ('zgyd','中国移动通信集团有限公司'),
    ('ceec','中国能源建设集团有限公司'),
    ('cam2027','中国机械科学研究总院集团有限公司'),
    ('casicjob','中国航天科工集团有限公司'),
    ('zglt','中国联合网络通信集团有限公司'),
)
BANNER_ALIAS='GP_index_long_banner_rolling'
CAMPAIGN_HOST_SUFFIX='.iguopin.com'
CAMPAIGN_ALIAS_RE=re.compile(r'^[a-z0-9][a-z0-9-]*$')
YEAR_MARKER='2027'
CAMPUS_MARKERS=('校园招聘','校招','秋季招聘','秋招')
```

**2.2 新增 `campaign_alias()` / `discover_campaigns()` / `merge_campaigns()`**

```python
def campaign_alias(row):
    for key in ('link_url','content_url'):
        host=urlsplit(str(row.get(key) or '')).hostname or ''
        if not host.endswith(CAMPAIGN_HOST_SUFFIX):continue
        label=host[:-len(CAMPAIGN_HOST_SUFFIX)]
        if label in ('www','gp-api') or '.' in label:continue
        if CAMPAIGN_ALIAS_RE.match(label):return label
    return None

def discover_campaigns(collector,ads=None):
    """返回 (campaigns, skipped):campaigns 为按 alias 去重、排序稳定的 [(alias,title)]。"""
    if ads is None:
        url=HOST+'/api/base/ads/v1/list?'+urlencode({'page':1,'page_size':100,'alias':BANNER_ALIAS})
        ads=public_api(collector,url)['list']
    found={};skipped=[]
    for row in ads or []:
        title=str(row.get('title') or '').strip()
        text=title+' '+str(row.get('link_url') or '')+' '+str(row.get('content_url') or '')
        if YEAR_MARKER not in text: skipped.append({...,'reason':'no 2027 marker in title/link'});continue
        if not any(m in text for m in CAMPUS_MARKERS): skipped.append({...,'reason':'not an unambiguous campus campaign'});continue
        alias=campaign_alias(row)
        if not alias: skipped.append({...,'reason':'cannot resolve a single-label iguopin campaign alias'});continue
        found.setdefault(alias,title)
    return sorted(found.items()),skipped

def merge_campaigns(discovered):   # 保底 ∪ 发现,setdefault 去重,alias 排序
    merged=dict(CAMPAIGNS)
    for alias,title in discovered:merged.setdefault(alias,title)
    return sorted(merged.items())
```

**2.3 `collect_guopin()`:横幅只取一次;发现失败退回保底 + alert**

```python
    discovered=[];skipped=[];fallback_used=False;directory_ok=False;adrows=[];adpath=None
    try:
        ads=public_api(collector,ads_url)                      # 唯一一次横幅调用
        adrows=[{k:r.get(k) for k in ('id','title','link_url','content_url')} for r in ads['list']]
        adpath=collector.evidence_file('guopin-official-campaign-directory.json', ...)
        directory_ok=True
        discovered,skipped=discover_campaigns(collector,ads=ads['list'])   # 不再二次请求
    except Exception as error:
        collector.alert('guopin:discovery',error);fallback_used=True       # 不整体失败
    ...
    for domain,group in merge_campaigns(discovered):
        try:
            ad=next((r for r in adrows if urlsplit(r['link_url'] or '').hostname==domain+'.iguopin.com' and YEAR_MARKER in str(r.get('title') or '')),None)
            if not ad:
                if directory_ok:raise ValueError('Current official directory no longer advertises this 2027 campaign')
                ad={'title':group,'link_url':''}          # 大盘不可用:保底清单不做目录证明,继续抓
```

**2.4 `source_state['guopin']` 可观测字段**

```python
    collector.states['guopin']={
        'status':'success' if complete else ('partial' if any(...) else 'partial_failure'),  # ← 保留已上线语义,避免回归
        'checked_at':now(),'complete':complete,'collected_jobs':len(alljobs),'campaigns':states,
        'discovered':[alias for alias,_ in discovered],   # alias 列表
        'skipped':skipped,                                # [{id,title,reason}...]
        'fallback_used':fallback_used,                    # bool
        'coverage':'guarantee list union auto-discovered 2027 campus campaigns; campus default track only'}
```

**未改动**:`campaign_pages()`、逐专场 config/岗位请求、`FIELDS`、完整性校验 `len(seen)!=expected`、`global_seen` 去重、`guopin_excluded_records.json`、`run.py` 的"缺席即下线只对 success+complete 专场生效"。

---

## 3. 单测(`tests/test_guopin_auto_campaigns.py`,7 用例)

运行器说明:本机裸 `pytest tests/` 不会把仓库根加入 `sys.path`(仓库无根 conftest),会产生 30 个既有收集错误;正确运行方式是 `python -m pytest`(本收据统一用 `.venv/bin/python -m pytest`)。

```
$ .venv/bin/python -m pytest tests/test_guopin_auto_campaigns.py -q
.......                                                                  [100%]
7 passed in 0.13s
```

7 个用例覆盖任务要求:

1. `test_discover_keeps_only_2027_campus_and_reports_skips`:2027 校招 / 2027 社招 / 2026 校招 / 2027 招聘会 / 2027 问卷混合 → 只收校招,其余逐条有 reason。
2. `test_campaign_alias_accepts_single_label_iguopin_hosts` + `test_campaign_alias_never_guesses`:alias 解析成功/失败。
3. `test_banner_failure_falls_back_to_guarantee_list`:横幅接口抛异常 → 退回 5 个保底专场、`fallback_used=True`、alert=`guopin:discovery`、`cgnpc` 不在保底清单。
4. `test_alias_in_both_guarantee_and_discovered_is_collected_once`:同一 alias 同时出现在保底与发现里,`config` 只调一次。
5. `test_merge_campaigns_union_is_alias_sorted_and_deduped`:并集去重、排序稳定。
6. `test_advertised_2027_banner_is_discovered_end_to_end`:完全靠横幅发现一个非保底 alias 并抓到岗位。

### 全量基线对比(`git stash -u` 前后,失败清单逐行 diff)

| | failed | passed | 失败清单 |
|---|---|---|---|
| 基线 `main`(stash 掉改动) | **39** | 415 | 39 条(见 `/tmp/base_fail.txt`) |
| 分支 `feat/guopin-auto-campaigns` | **39** | **422**(=415+7) | **与基线逐行一致**,双向 `comm` 为空 |

```
$ .venv/bin/python -m pytest tests/ -q --tb=no -rf | tail -1
39 failed, 422 passed, 4 warnings in 14.01s
$ comm -13 base_fail.txt branch_fail.txt   # 仅分支新增
(空)
$ comm -23 base_fail.txt branch_fail.txt   # 仅基线有
(空)
```

**既有 flake 说明**:`tests/test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` 会随机失败(4 个并发子进程迁移 SQLite 时 `sqlite3.OperationalError: database is locked`)。实测:无改动基线 8 次跑失败 2 次,带改动 8 次跑失败 3 次,**与本改动无关**(该用例不 import guopin)。上表取 flake 通过的一轮,故 39 条完全一致;若不巧命中 flake 会显示 40 failed,多出的唯一一条就是它。

---

## 4. 离线发现清单(真实横幅,仅 2 次横幅调用)

方式:Mac 本地 `.venv/bin/python`,直接调 `discover_campaigns()` / 原始横幅接口,**未逐专场抓岗位、未写库**。
- 调用 1:`discover_campaigns(collector)`(内部 1 次 `/api/base/ads/v1/list?page=1&page_size=100&alias=GP_index_long_banner_rolling`)。
- 调用 2:原始横幅落盘 `/tmp/guopin_banners_raw.json`(18,981 B,仅在 /tmp);之后用该文件 `discover_campaigns(ads=...)` **离线重算**,不再联网。合计 2 次,达上限即止。

原始规模:**38 条横幅**;含"2027"+校招关键字的 **26 条**;解析出 alias 的 **14 条**;alias 解析失败 **12 条**;被过滤(无 2027 或非校招)**12 条**。

### 4.1 发现到的专场(14,`discovered`,按 alias 排序)

| alias | 横幅标题 |
|---|---|
| cam2027 | 中国机械科学研究总院集团2027届校园招聘 |
| casicjob | 中国航天科工集团有限公司2027届校园招聘 |
| ceec | 中国能建2027届全球校园招聘 |
| chinalco2027 | 中国铝业集团有限公司2027年秋季招聘 |
| dec2027 | 东方电气集团2027届校园招聘 |
| hbyz | 河北邮政2027年度秋季校园招聘 |
| ltryy | 中国联通软件研究院2027年校园招聘 |
| ltsk | 联通数字科技有限公司2027届校园招聘 |
| spic2027 | 国家电投集团2027届校园招聘 |
| tslab | 天隼实验室2027届校园招聘 |
| yzw | 中建电商2027届校园招聘 |
| zgbq2027 | 中国兵器2027届校园招聘 |
| zglt | 中国联通2027校园招聘 |
| zgyd | 中国移动2027校园招聘 |

(保底 5 个 `zgyd/ceec/cam2027/casicjob/zglt` 全部在列,故实际采集集合 = 14。)

### 4.2 `skipped` 之"alias 解析不出"(12,reason=`cannot resolve a single-label iguopin campaign alias`)

| 横幅标题 | 实际链接(外部站 / 非专场页) |
|---|---|
| 北京地铁机电分公司2027届校园招聘 | bjsubway.zhiye.com |
| 中国农业银行北京分行2027校招 | career.abchina.com |
| 中国华电2027年度校园招聘 | www.chd.com.cn |
| 中远海运散货运输有限公司2027校园招聘 | www.iguopin.com/company/jobs?id=… |
| 招商银行烟台分行2027校园招聘 | cmb-recruitment-mobile.paas.cmbchina.com |
| 中国工商银行江苏省分行2027年度校园招聘 | job.icbc.com.cn |
| 中国移动在线营销服务中心2027校园招聘 | www.iguopin.com/company?id=… |
| 中国邮政2027年度联合校园招聘 | www.chinapost.com.cn |
| 中国邮政储蓄银行福建省分行2027校园招聘 | mp.weixin.qq.com |
| 中国电子2027届校园招聘 | career.cec.com.cn |
| 中国国新控股有限责任公司2027届校园招聘 | zp.crhc.cn |
| 中国电信2027校园招聘 | job.chinatelecom.com.cn |

说明:这 12 条都是**真实的 2027 校招活动**,但链接指向企业自有招聘系统或公众号,不是国聘承载的 `<alias>.iguopin.com` 专场;现有"逐专场 `exclusive/v1/info?domain=<alias>`"的抓取路径**无法寻址**它们,按任务要求"不猜"记入 `skipped`。这也解释了总控看到"26 个"与本次"发现 14 个"的差额。

### 4.3 `skipped` 之"关键字过滤"(12,非 2027 / 非校招)

`no 2027 marker in title/link` 共 12 条:中储棉花信息中心社招、2026上海社会组织联合招聘专区、湛江市海洋牧场产业人才调查问卷、新疆新业国有资产经营(集团)…社会招聘、中国航空发动机集团有限公司招聘、2026秋季厦门企业组团招聘会、2026年海南省"百万英才兴海南 四城同办"校招活动、"百万英才汇南粤"2026年N城联动秋季招聘活动(北京高校专场)、空军2026年下半年高层次人才引进、崖州湾国家实验室2026年度公开招聘、青春知行(0119)、青年人才创新创业基地。

---

## 5. 给总控的部署说明(仅覆盖 `guopin.py` 一个文件)

部署方式/备份/校验要求**沿用 `RECEIPT-collector-partial-keep.md` E3**;本任务不需要动 `run.py`/`p1_pipeline.py`/`windows_collector.py`(它们已是 9-18 上线的 partial-keep 版)。

**部署件**:

| 文件 | 来源 | sha256 | 字节 |
|---|---|---|---|
| `guopin.py` | 本分支 `feat/guopin-auto-campaigns` | `a6617c98783482d340b68076d4ac72ccf0b0be4984746908eacefe68ee79d335` | 17248 |
| (部署前基线)精灵现役 `guopin.py` | partial-keep 版 | `22e5f6ad0b66487ba7f6ccaee041da67c668d7ed98aeaa10408d7dc95a0abf89` | 13739 |

步骤:

1. **备份**:`robocopy C:\mcp-suite-collector\qiuzhao C:\mcp-suite-backup-<日期>\qiuzhao /E /R:2 /W:5`;对备份的 `qiuzhao\collector\guopin.py` 算 sha256,确认前 8 位 = `22e5f6ad`(若不符说明现役文件已被改过,**停下来找总控**)。
2. **传输**:因 scp 不可用,用分片 base64 + `powershell -NoProfile -EncodedCommand`(UTF-16LE)写入精灵临时位置;精灵侧 `Get-FileHash` 与上表 `a6617c98…` **逐字节核对通过后**再覆盖 `C:\mcp-suite-collector\qiuzhao\collector\guopin.py`。覆盖后再算一次 sha256 留证。
3. **编译检查**:`C:\mcp-suite-collector\.venv\Scripts\python.exe -m py_compile qiuzhao\collector\guopin.py` → 期望 exit 0。不需要重启服务,计划任务次日 06:10 自然生效。
4. **首日观察**:`runs\<日期>\data\source_state.json` 的 `guopin` 应出现 `discovered`(预期 14 个 alias)、`skipped`(预期 24 条,含 12 alias + 12 过滤)、`fallback_used=false`;`campaigns` 预期 14 个 key;`steps.basic` 为 0 或 2 均正常。**不要**用 main 原始 `guopin.py` 覆盖(会丢 partial 状态,回归整体拒收)。
5. **回滚**:拷回第 1 步备份的 `guopin.py`(即 `22e5f6ad…`);无需数据层回滚,被采集的数据有 evidence 链。

---

## 6. 遗留问题与不确定点

1. **12 条外部链接的 2027 校招无法覆盖**:工行/农行/招行/邮储/华电/中远海运/中国电子/国新/电信/邮政/移动在线/北京地铁。它们不在国聘承载的专场体系内,现有抓取路径不可寻址;若要覆盖需另开"外部招聘站"采集器,不在本任务范围。建议总控确认这 12 个是否值得后续单独立项。
2. **只验证了发现,未验证新专场的逐专场抓取**:9 个新增 alias(chinalco2027/dec2027/hbyz/ltryy/ltsk/spic2027/tslab/yzw/zgbq2027)的 `exclusive/v1/info?domain=<alias>` 是否可用,未在 Mac 实测(任务禁止跑整套采集)。它们就是横幅指向的真实前端地址,风险低;首日 06:10 后看 `campaigns` 里这些 key 的 `status`,失败会被 `partial` 化而不影响其他专场。
3. **alias 只接受单标签主机**:`https://a.b.iguopin.com` 会被拒。若官方改用多级子域,需要放宽规则(当前不猜是有意的)。
4. **横幅 `link_url` 缺失、靠 `content_url` 命中的专场**:`collect_guopin` 的目录核对仍按 `link_url` hostname 匹配,这类专场会走"目录不再广告"分支。实测 14 个发现全部由 `link_url` 命中,未触发;属理论边界。
5. **横幅分页**:仅请求 `page=1&page_size=100`,当前 38 条;若未来横幅超过 100 条会漏发现,需再评估。
6. **既有 flake 未修**:`test_codes_kind.py::test_migration_is_safe_when_both_services_start_together`(SQLite 并发迁移锁)与本任务无关,但会让"39 failed"偶发变"40 failed",建议后续单独加固。
7. **运行器差异**:裸 `pytest tests/` 在本 checkout 缺仓库根 sys.path(30 个既有收集错误),统一用 `python -m pytest`;未改 `pytest.ini`/根 conftest(超范围)。
