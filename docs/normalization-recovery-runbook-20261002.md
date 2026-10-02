# 精灵应用、验证、恢复与回滚手册

本手册是待审执行步骤，不是执行回执。基线 `bcae6e546a025a3a84c5bfe4aa9d619a38db9c79`；开发目录 `D:\qiuzhao-mcp-work\repo`，生产目录 `C:\mcp-suite-collector`。本轮未访问这两个目录。**独立审查待完成，所有生产写步骤暂不可执行。** 不改调度、不新开正常采集、不扩大旧 run 截止或预算、不安装旧地点资产。

## 1. 只在开发 checkout 应用补丁

PowerShell，先解压交付包；`$Package` 指向实际解压目录，不能照抄一个未存在的目录。

```powershell
$Dev = 'D:\qiuzhao-mcp-work\repo'
$Prod = 'C:\mcp-suite-collector'
$Base = 'bcae6e546a025a3a84c5bfe4aa9d619a38db9c79'
$Package = Read-Host '完整修改包的解压目录'
$Patch = Join-Path $Package 'qiuzhao-normalize-recovery.patch'
if (!(Test-Path $Patch)) { throw 'patch 不存在' }
if (git -C $Dev status --porcelain) { throw '开发树有未提交修改，先保存并审查；不要覆盖' }
git -C $Dev switch -c review/pro-normalize-recovery-20261002 $Base
if ($LASTEXITCODE) { throw '不能切到指定基线' }
git -C $Dev apply --check $Patch
if ($LASTEXITCODE) { throw '完整仓库 patch 检查失败' }
git -C $Dev apply --index $Patch
if ($LASTEXITCODE) { throw '应用失败' }
git -C $Dev diff --cached --check
if ($LASTEXITCODE) { throw 'diff 检查失败' }
```

已有远程修复分支可直接 fetch/check out 做审查，**不要对已包含修改的分支再应用同一 patch**。不得将生产 C 目录整体替换成开发树。

## 2. 开发环境验证（目标未运行项）

沿用项目原 venv，不新加付费 API 或供应商。开发 venv 不存在时先由精灵确认原项目解释器，不把系统 Python 通过当成部署账号通过。

```powershell
Set-Location $Dev
$Py = Join-Path $Dev '.venv\Scripts\python.exe'
if (!(Test-Path $Py)) { throw '需要现有项目解释器' }
& $Py -m py_compile qiuzhao/normalize.py qiuzhao/normalization_io.py deploy/windows_normalize_retry.py
if ($LASTEXITCODE) { throw '编译失败' }
& $Py -m pytest -q tests/test_normalization_io.py tests/test_windows_normalize_retry.py
if ($LASTEXITCODE) { throw '聚焦回归失败' }
$OldTests = @(git ls-files 'tests/*normaliz*.py' 'tests/test_windows_publication.py' 'tests/test_segmented_publish.py' 'tests/test_collector_partial_keep.py' 'tests/*recover*.py' 'tests/*portable*.py' 'tests/*location*.py')
if (!$OldTests.Count) { throw '未找到既有回归，不能默认为通过' }
& $Py -m pytest -q @OldTests
if ($LASTEXITCODE) { throw '既有回归失败：保留输出并在原基线重跑对照，不能忽略' }
& $Py deploy/windows_normalize_retry.py --help
```

缺夹具或依赖的用例逐项列未运行，不改成 passed。Linux RLIMIT 探针不适用于 Windows；Windows 要额外测真实 msvcrt 争锁、Scheduler 未知/queued/running、UTF-8 中文/空格路径、子进程 timeout/termination 和替换失败。完整字段回归用原地点/公司/招聘类型样例，不联网逐岗重采。

## 3. 一次取得本次必需证据

下列是定位 10/2 故障的最小缺失集合，不需要重打包全部历史：原 run 的 `normalize.log`（失败尝试完整 traceback）、`receipt.json`、`data/p1-status.json`；实际部署代码/资产 SHA 与 staging 大小/SHA。若 traceback 指向具体记录，再提供对应序号的最小脱敏记录及原/packed SHA 对照；若是 MemoryError，则提供当时资源日志，不用猜测坏行。

```powershell
$Run = Join-Path $Prod 'runs\20261002'
Get-Content (Join-Path $Run 'normalize.log') -Tail 200
Get-Content (Join-Path $Run 'receipt.json') -Raw
Get-Content (Join-Path $Run 'data\p1-status.json') -Raw
Get-Item (Join-Path $Run 'data\jobs.json') | Select-Object FullName,Length,LastWriteTimeUtc
Get-FileHash (Join-Path $Run 'data\jobs.json') -Algorithm SHA256
Get-FileHash (Join-Path $Run 'receipt.json') -Algorithm SHA256
```

Tail 只用于就地查看；交给审查者的失败尝试须含完整异常链。保留原日志和原 staging，不让脱敏副本替换生产。若当前已是后继 run、已成功 normalize 或存在在途发布，不按历史状态强行执行本手册。

## 4. 审查最终字节与依赖（不自动批准）

在开发树生成部署候选身份：三个修改文件取开发树，其余依赖/资产取生产树，缺资产为 null。此动作只读取生产文件；输出存开发侧，不存永久 token。

```powershell
Set-Location $Dev
$Review = Join-Path (Split-Path $Dev) 'normalize-review.json'
@'
import json,sys
from pathlib import Path
from deploy.windows_normalize_retry import identities,digest
source,target,out=map(Path,sys.argv[1:])
files=identities(target)
for rel in ('qiuzhao/normalize.py','qiuzhao/normalization_io.py','deploy/windows_normalize_retry.py'):
    files[rel]=digest(source/rel)
if out.exists():raise SystemExit('refuse overwrite of review file')
out.write_text(json.dumps({'decision':'PENDING','reviewer':None,'files':files},ensure_ascii=False,indent=2),encoding='utf-8')
'@ | & $Py - $Dev $Prod $Review
if ($LASTEXITCODE) { throw '候选身份收集失败' }
```

这张清单只绑定代码与已知资产，不认证审查者身份，也不替代原项目完整部署清单。独立审查者必须读取最终 diff、测试和真实故障样本，完成必要 Windows 测试，才由其填写真实 reviewer/decision=PASS；不能机械地把 PENDING 替换为 PASS。

`deploy/qiuzhao-deploy-manifest.json` 仍冻结旧 normalize SHA。独审后应在实际受影响环境更新 normalize 的审查归属/SHA，并新增 normalization_io.py 的条目；恢复入口也纳入 windows_collector 环境。未审前保留拒绝，不跳过 frozen check，不把旧 GPT-6 Sol / GPT-6.1 Sol low 审查冒认成本次批准。旧的 10/1 ZERO_SEGMENT_RECOVERY 依赖 SHA 会拒绝新代码，这是安全边界，不能同步改其硬编码来绕过。

## 5. 受控安装三个代码文件（仅独审和目标测试通过后）

先确认没有 collector/recovery/publisher 活跃、有足够容量、具备既有授权。下面代码复用生产现有锁和 Scheduler 检查，先全部备份再按“新依赖 → 新工具 → 新入口”安装。**此安装片段在本轮没有 Windows 实测，需与修改一起审查。** 不复制 jobs、receipt、checkpoint、资产或 Base 配置，不重启正常采集。

```powershell
Set-Location $Prod
$ProdPy = Join-Path $Prod '.venv\Scripts\python.exe'
@'
import datetime,importlib.util,json,os,shutil,sys,tempfile
from pathlib import Path
src,dst,review=map(Path,sys.argv[1:])
sys.path.insert(0,str(dst))
from deploy import windows_collector as W
from deploy.windows_recover_run import task_is_running
spec=importlib.util.spec_from_file_location('candidate_retry',src/'deploy/windows_normalize_retry.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
order=('qiuzhao/normalization_io.py','deploy/windows_normalize_retry.py','qiuzhao/normalize.py')
with (dst/'data/windows-runner.lock').open('a+') as lock:
    W.fcntl.flock(lock,W.fcntl.LOCK_EX|W.fcntl.LOCK_NB)
    if task_is_running():raise SystemExit('daily not safely idle')
    W.capacity_check([dst/'data/jobs.json'])
    actual=R.identities(dst)
    for rel in order:actual[rel]=R.digest(src/rel)
    R.validate_manifest(review,actual)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=dst/'recovery'/('normalize-code-backup-'+stamp);backup.mkdir(parents=True)
    journal={'files':{},'new_sha256':{rel:actual[rel] for rel in order},'state':'backed-up-not-installed'}
    for rel in order:
        target=dst/rel;old=R.digest(target) if target.is_file() else None
        journal['files'][rel]=old
        if old is not None:
            saved=backup/rel;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
            if R.digest(saved)!=old:raise RuntimeError('backup hash mismatch')
    W.atomic_json(backup/'code-backup.json',journal)
    for rel in order:
        target=dst/rel;target.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix=target.name+'.install-',dir=target.parent);os.close(fd)
        try:
            shutil.copy2(src/rel,temp)
            if R.digest(temp)!=actual[rel]:raise RuntimeError('install candidate drift')
            os.replace(temp,target)
            if R.digest(target)!=actual[rel]:raise RuntimeError('installed hash mismatch')
        finally:
            if os.path.exists(temp):os.unlink(temp)
    journal['state']='installed-byte-verified';W.atomic_json(backup/'code-backup.json',journal)
    print(backup)
'@ | & $ProdPy - $Dev $Prod $Review
if ($LASTEXITCODE) { throw '安装失败：保留备份，禁止盲重启' }
```

保存输出的精确 backup 路径。正常执行关闭句柄释放锁；中断则不能凭“有文件”宣称安装成功，须逐件回读。随后用生产账号/venv 重跑必要聚焦测试和私有隔离故障样本；不要在正被写入的 jobs 上裸跑 normalize。原部署清单冻结和运行环境兼容仍须正式核验，开发测试不替代它。

## 6. 只重试原 run 的 normalize

这是不采集、不发布的阶段操作。先原地保全失败日志、receipt、jobs 与工作基线的受核验副本；复制需要纳入原容量门，不对容量不足进行强制。若已有 unsafe_writer、active_batch、未确认发布或阶段备份残留，工具会拒绝，先按证据解决，不能删标志开路。

```powershell
Set-Location $Prod
$SourceSha = (Get-FileHash (Join-Path $Run 'data\jobs.json') -Algorithm SHA256).Hash.ToLower()
$ReceiptSha = (Get-FileHash (Join-Path $Run 'receipt.json') -Algorithm SHA256).Hash.ToLower()
& $ProdPy deploy/windows_normalize_retry.py --run $Run --expected-source-sha256 $SourceSha --expected-receipt-sha256 $ReceiptSha
if ($LASTEXITCODE) { throw '只读阶段检查失败' }
# 仅在审查和前置检查通过后执行一次；实际文件变化会因 SHA 不符被拒绝。
& $ProdPy deploy/windows_normalize_retry.py --run $Run --expected-source-sha256 $SourceSha --expected-receipt-sha256 $ReceiptSha --review-manifest $Review --apply
if ($LASTEXITCODE) { throw 'normalize 重试失败：保全现场，不采集、不发布' }
Get-Content (Join-Path $Run 'receipt.json') -Raw
Get-Content (Join-Path $Run 'normalize.log') -Tail 200
```

要求实际输出 `normalized-not-published`、steps.normalize=0，无 unsafe_writer；原 basic/Tencent/P1 历史、pending、预算、deadline、collection、completed_at 和 delivery 未被篡改。工具追加 normalization_retries，不改历史 segment 里的失败退出码，不把 collection stopped 改 completed，也不更新 data/windows-status.json；后者可能仍是历史快照，核验须看原 run receipt 和本次输出。

中断校验屏障 `unsafe_writer.normalization_retry_validation=true` 不是“已证明子进程活着”，是“未证明本次转换完成最终校验”。此时既不能直接普通 resume，也不能手改 normalize=0/清屏障；核验子进程、代码/资产、原备份和当前数据后，由独立审查决定重新转换或恢复前态。真实 termination unconfirmed 绝不可掩盖。

## 7. 后续恢复发布与三层交付（另外的写边界）

不要立即 `windows_collector --resume-run`：原 collection stopped 且 P1 尚未完成时，它可能先继续采集。先核最近真实 accepted 与父版本、未知发布、唯一 publisher，以及本次保留成果。只有在新的独立候选/数据审查通过后，才执行既有恢复器，不另启动正常采集：

```powershell
# 仅在已确认 accepted/冲突策略、无未知接受，且获准发布本次候选后。
$Recovery = Join-Path $Prod 'recovery\normalize-20261002-reviewed'
& $ProdPy deploy/windows_recover_run.py --run $Run --work-dir $Recovery
if ($LASTEXITCODE) { throw '恢复发布没有确认成功，先只读对账，禁止循环重发' }
```

该既有恢复器可能三方 rebase，**不是地点迁移单次 CAS 工具**。若审查要求只允许某个 prepared SHA 的一次 CAS，或最新 accepted 已变，不能把以上命令当替代：先重新构建/独审候选，按既有批准的一次 CAS 路线处理。本次没有新增单次发布器、放宽原 CAS 或伪造发布 receipt。

恢复器不修改源 run，而以 source-binding/发布收据供原 runner 日后采用。不要为“对齐显示”手写源 receipt；accepted 必须以 receiver、冻结产物和版本账本核验。served 通过原受控激活器实际加载 SHA 核验，Base 单独核验；历史版本哈希不能当当前值。

飞书只在实际交付机、原配置/原 Base/原 Excel 路线上运行。先确认 active：有则只续该版，没有再按最新 accepted 后继及原结算规则处理；Windows 飞书路径/登录适配仍未由本轮验证。下面参数存在于基线 CLI，但配置路径须用原调度的真实值，不在本手册编造：

```powershell
# 在既有交付机设置其真实解释器、checkout 与配置；不是默认在生产 C 目录执行。
$DeliveryPython = Read-Host '原交付调度的 Python 路径'
$DeliveryScript = Read-Host '原交付 checkout 的 deploy\windows_excel_delivery.py 路径'
$DeliveryConfig = Read-Host '原 deliver-latest --config 路径'
& $DeliveryPython $DeliveryScript deliver-latest --config $DeliveryConfig --apply
```

不加 force-new-batch，不走逐行 API。运行前 frozen manifest、openpyxl、lark-cli、账号权限与 active 必须确认；无 apply 的 deliver-latest 也可能建立本地交付状态，不把它称为完全只读探针。

## 8. 回滚（只回滚代码，不倒退 accepted 数据）

开发树未提交时可反向检查/应用本包补丁；已提交则在干净分支用 git revert 明确修复提交，不能 reset 覆盖其他人工作。生产代码回滚须在同样 runner 锁与 Scheduler 安全状态下，使用第 5 步真实 code-backup.json：先确认当前三个文件仍与 journal.new_sha256 一致（有后继修改则停止）；先用核验过的备份原子恢复旧 normalize.py，再恢复/移除两个新文件，原本不存在的只在确认仍为本次 SHA 后精确移除。保留备份日志及本次转换数据；不删 run、checkpoint、在途产物或归档对象。

下面是独立的回滚命令，仍只在生产空闲、独审允许的窗口执行。`$Backup` 必须取第 5 步真实输出，不能按示例猜测；支持安装中断后仅部分文件已替换的情形，任何文件不是原 SHA 或本次新 SHA 均拒绝。**本片段未在 Windows 实测。**

```powershell
$Dev = 'D:\qiuzhao-mcp-work\repo'
$Prod = 'C:\mcp-suite-collector'
$ProdPy = Join-Path $Prod '.venv\Scripts\python.exe'
$Backup = Read-Host '第 5 步生成的真实代码备份目录'
Set-Location $Prod
@'
import importlib.util,json,os,shutil,sys,tempfile
from pathlib import Path
src,dst,backup=map(Path,sys.argv[1:])
sys.path.insert(0,str(dst))
from deploy import windows_collector as W
from deploy.windows_recover_run import task_is_running
spec=importlib.util.spec_from_file_location('candidate_retry',src/'deploy/windows_normalize_retry.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
order=('qiuzhao/normalize.py','deploy/windows_normalize_retry.py','qiuzhao/normalization_io.py')
with (dst/'data/windows-runner.lock').open('a+') as lock:
    W.fcntl.flock(lock,W.fcntl.LOCK_EX|W.fcntl.LOCK_NB)
    if task_is_running():raise SystemExit('daily not safely idle')
    if not backup.resolve().is_relative_to((dst/'recovery').resolve()):
        raise RuntimeError('backup is outside collector recovery directory')
    journal=json.loads((backup/'code-backup.json').read_text(encoding='utf-8'))
    if set(journal['files'])!=set(order) or set(journal['new_sha256'])!=set(order):
        raise RuntimeError('unexpected backup manifest')
    for rel in order:
        target=dst/rel;old=journal['files'][rel];new=journal['new_sha256'][rel]
        current=R.digest(target) if target.is_file() else None
        if current not in (old,new):raise RuntimeError('successor/drift: refuse rollback '+rel)
        if old is not None and R.digest(backup/rel)!=old:
            raise RuntimeError('backup drift: '+rel)
    for rel in order:
        target=dst/rel;old=journal['files'][rel]
        current=R.digest(target) if target.is_file() else None
        if current==old:continue
        if old is None:
            target.unlink()  # exact verified new code file only; never data/assets
        else:
            fd,temp=tempfile.mkstemp(prefix=target.name+'.rollback-',dir=target.parent);os.close(fd)
            try:
                shutil.copy2(backup/rel,temp)
                if R.digest(temp)!=old:raise RuntimeError('rollback copy drift')
                os.replace(temp,target)
                if R.digest(target)!=old:raise RuntimeError('rollback mismatch')
            finally:
                if os.path.exists(temp):os.unlink(temp)
    journal['state']='code-rolled-back-byte-verified'
    W.atomic_json(backup/'code-backup.json',journal)
    print('code rollback verified; accepted/staging/receipts/checkpoints untouched')
'@ | & $ProdPy - $Dev $Prod $Backup
if ($LASTEXITCODE) { throw '回滚未确认成功，保留现场，不启动采集' }
```

生产已经接受的版本绝不通过恢复旧 jobs 文件倒退。必要数据纠错另按最新 accepted、字段差异、独审和 CAS 处理。容量归档另核保护对象/锁，验证副本后才精确删除；本补丁未修改容量门或实现长期容量闭环。
