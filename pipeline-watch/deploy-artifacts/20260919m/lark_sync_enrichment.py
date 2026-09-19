"""Qualification text and exact-ID P1 append for the existing four-table Base."""
from __future__ import annotations
import json
import hashlib
import time
import re
from pathlib import Path
from urllib.parse import urlsplit
from qiuzhao import v4_fields as V
from qiuzhao.collector import sync_lark_multivalue as S
from qiuzhao.collector import lark_continuation as C

NOTE_FIELD = '届别条件说明'
NOTE_STATE = Path(__file__).resolve().parents[1] / 'data' / 'lark-note-ownership.json'
HARDWARE = {'大疆','华为','OPPO','vivo','荣耀','比亚迪','宁德时代','联想','海康威视','安克创新','影石Insta360',
            '中兴通讯','大华股份','汇川技术','TP-LINK普联','石头科技','科沃斯','理想汽车','小鹏汽车','蔚来汽车','吉利汽车','长城汽车','小米'}
PHARMA = {'迈瑞医疗','恒瑞医药','药明康德'}


def route_group(company):
    """(industry base table name, 行业 cell value) for a newly discovered row.

    Product categorization approved for NEW records only, not an official
    industry classification and never a reason to move an existing record. The
    concrete continuation table is resolved from the live Base inventory by
    ``lark_continuation.ensure_capacity`` instead of a hardcoded id.
    """
    if company in HARDWARE:
        return '制造工业岗', '制造/工业'
    if company in PHARMA:
        return '其他行业岗', '医药/医疗'
    return '互联网科技岗', '互联网/科技'


def route(company):
    """Compatibility shim: the historical *last* continuation id + industry.

    New code should use :func:`route_group` and let the continuation module pick
    the live highest-N table. Kept because older callers import it directly.
    """
    group, industry = route_group(company)
    legacy = {'制造工业岗': S.MANUFACTURING_CONTINUATION,
              '互联网科技岗': S.INTERNET_CONTINUATION,
              '其他行业岗': S.TABLES[3]}[group]
    return legacy, industry


def current_tables():
    """Every live industry table id, discovered by name (continuations included)."""
    return S.discovered_table_ids()


def qualification_note(raw):
    parts=[]
    if raw.get('pending_note'):parts.append(str(raw['pending_note']))
    if raw.get('application_link_type')=='list_entry' and raw.get('application_instructions'):
        parts.append('投递方式：'+str(raw['application_instructions']))
    cohort=str(raw.get('cohort_raw') or '').strip()
    scoped=raw.get('cohort_scope') in {'campaign_announcement','headquarters_campaign_announcement'}
    if cohort and raw.get('p1_company') and not scoped:
        parts.append('官方采集岗位资格字段：'+cohort)
    description = str(raw.get('description_raw') or '')
    sentences=[s.strip() for s in re.split(r'[。\n]',description) if s.strip()]
    extracts=[]
    for sentence in sentences:
        if re.search(r'20\d{2}[^。\n]{0,35}(?:届|毕业)|毕业(?:时间|日期|生范围)',V.expand_short_cohorts(sentence)):
            if sentence not in extracts:extracts.append(sentence)
    if extracts:
        prefix='官方采集岗位说明摘录：' if raw.get('p1_company') else '存量岗位说明摘录（请按原链接核验）：'
        parts.append(prefix+'\n'+'\n'.join(extracts))
    campaign=V.campaign_text(raw)
    if campaign and raw.get('p1_company'):
        if V.job_bound_campaign(raw):
            parts.append('绑定此岗位的官方专项条件：'+str(campaign))
        elif not parts or V.graduation_conflicts_of(raw):
            parts.append('一般活动条件（不覆盖更具体的岗位资格）：'+str(campaign))
    if raw.get('source_is_active') is False and raw.get('status_note'):
        parts.append('招聘状态说明：'+str(raw['status_note']))
    if parts:return '\n'.join(parts)
    if cohort:
        return '历史届别标签：'+cohort+'。缺少可核对的岗位资格原句，待回源核实。'
    _,_,note,_=V.graduation_of(raw)
    return (note or '未注明')+'；现有记录未提供明确毕业日期范围，请按原链接核验。'


def verified_backup(out):
    backup=json.loads((out/'backup.json').read_text(encoding='utf-8'))
    if backup.get('base')!=S.BASE or not S.valid_selection_for_snapshot(out,backup.get('tables',{})):
        raise ValueError('backup target mismatch')
    for meta in backup['tables'].values():
        for name in ['records','schema']:
            if S.digest(Path(meta[name]))!=meta[name+'_sha256']:
                raise ValueError('backup integrity mismatch')
    return backup


def read_id_matches(table, ids, path):
    if not ids:
        return {}
    result=S.cli('+record-list','--base-token',S.BASE,'--table-id',table,
        '--filter-json',json.dumps({'logic':'or','conditions':[['job_id','==',i] for i in ids]},ensure_ascii=False),
        '--field-id','job_id','--format','ndjson','--output',S.rel(path),'--overwrite','--limit','2000')
    if result.get('has_more'):
        raise ValueError('exact-ID reconciliation exceeded bounded result set')
    return {r['job_id']:r['record_id'] for r in (json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()) if r.get('job_id')}


def ensure_note_fields(out,tables=None):
    for table in (tables if tables is not None else current_tables()):
        fields=S.full_fields(table);existing=next((f for f in fields if f['name']==NOTE_FIELD),None)
        if existing is None:
            S.save(out/(table+'.note-schema.before.json'),fields)
            definition={'name':NOTE_FIELD,'type':'text','description':'保留毕业日期范围、优秀/未就业等资格限制；历史标签无原句时明确待回源核实。'}
            response=S.cli('+field-create','--base-token',S.BASE,'--table-id',table,'--json',json.dumps(definition,ensure_ascii=False))
            S.save(out/(table+'.note-field-create.json'),response)
            deadline=time.monotonic()+45
            while existing is None and time.monotonic()<deadline:
                fields=S.full_fields(table);existing=next((f for f in fields if f['name']==NOTE_FIELD),None)
                if existing is None:time.sleep(2)
        if existing is None or existing['type']!='text':
            raise ValueError('qualification note field not ready or incompatible')


def note_sync(out, jobs_path):
    ownership=json.loads(NOTE_STATE.read_text(encoding='utf-8')) if NOTE_STATE.exists() else {}
    backup=verified_backup(out)
    notes={};ambiguous=set()
    for raw in V.iter_json_file(jobs_path):
        identity=raw.get('id')
        if not identity:continue
        value=qualification_note(raw)
        if identity in notes and notes[identity]!=value:ambiguous.add(identity)
        notes[identity]=value
    ensure_note_fields(out,backup['tables'])
    for table in backup['tables']:
        records=json.loads(Path(backup['tables'][table]['records']).read_text(encoding='utf-8'))
        pairs=[(r['record_id'],r['job_id']) for r in records if r.get('job_id') in notes and r['job_id'] not in ambiguous]
        for start in range(0,len(pairs),200):
            batch=pairs[start:start+200];before=out/f'{table}.note-before-{start}.ndjson'
            S.cli('+record-get','--base-token',S.BASE,'--table-id',table,'--json',json.dumps({'record_id_list':[r for r,_ in batch]}),
                '--field-id',NOTE_FIELD,'--format','ndjson','--output',S.rel(before),'--overwrite')
            prior={r['record_id']:r.get(NOTE_FIELD) for r in (json.loads(x) for x in before.read_text(encoding='utf-8').splitlines())}
            updates={}
            for rid,jid in batch:
                previous=prior.get(rid) or '';key=table+'/'+rid
                owned=ownership.get(key)==hashlib.sha256(previous.encode()).hexdigest()
                if (not previous or owned) and previous!=notes[jid]:
                    updates[rid]={NOTE_FIELD:notes[jid]}
            if updates:
                body=out/f'{table}.note-batch-{start}.json';S.save(body,{'update_records':updates})
                response=S.cli('+record-batch-update','--base-token',S.BASE,'--table-id',table,'--json','@'+S.rel(body))
                if response.get('data',{}).get('ignored_fields'):raise ValueError('note field ignored')
                S.save(out/f'{table}.note-response-{start}.json',response)
                for rid,delta in updates.items():
                    ownership[table+'/'+rid]=hashlib.sha256(delta[NOTE_FIELD].encode()).hexdigest()
                S.save(NOTE_STATE,ownership)
        print(json.dumps({'note_table':table,'matched':len(pairs)}),flush=True)


def _build_fields(raw, industry):
    v,_=V.convert(raw)
    fields={'job_id':raw['id'],'岗位名称':v['job_title'],'公司名称':raw['p1_company'],
            '招聘单位':raw.get('recruiting_unit_raw') or raw.get('recruitment_unit') or raw['p1_company'],
            '行业':[industry],'招聘性质':[{'校园招聘':'校招','实习招聘':'实习','社会招聘':'社招'}[raw['recruitment_type']]],
            '岗位大类':[v['job_category']],'状态':[raw.get('status') or 'unverified'],
            '原链接':raw.get('source_url') or raw['detail_url'],'投递入口':raw.get('application_url') or raw['detail_url'],
            '复核时间':str(raw.get('reviewed_at') or ''),'来源':raw.get('source_name') or raw['p1_company']+'官方招聘',
            NOTE_FIELD:qualification_note(raw),**S.values_for(raw)}
    if raw.get('deadline'):fields['投递截止']=str(raw['deadline'])
    return fields


def new_fields(raw):
    """(legacy continuation id, fields) — compatibility for older callers."""
    table,industry=route(raw['p1_company'])
    return table,_build_fields(raw,industry)


def new_fields_for_group(raw):
    """(industry base table name, fields) — the dynamic-discovery routing used
    by :func:`append_p1` so the live highest-N continuation is the write target."""
    group,industry=route_group(raw['p1_company'])
    return group,_build_fields(raw,industry)


def quota_rejection(error):
    """Recognize an explicit no-capacity API refusal, never a transport failure."""
    try:
        payload=json.loads(str(error))
    except (ValueError, TypeError):
        return False
    detail=payload.get('error',{})
    return payload.get('ok') is False and detail.get('code')==800040832 and detail.get('subtype')=='quota_exceeded'


def append_p1(out,jobs_path):
    from qiuzhao.collector.p1_pipeline import COMPANIES
    backup=verified_backup(out);known=set()
    if not set(S.TABLES) <= set(backup['tables']):
        raise ValueError('append requires complete backup including approved continuation table')
    all_tables=current_tables()
    ensure_note_fields(out,all_tables)
    for meta in backup['tables'].values():
        known.update(r.get('job_id') for r in json.loads(Path(meta['records']).read_text(encoding='utf-8')) if r.get('job_id'))
    candidates={};ambiguous=set()
    for raw in V.iter_json_file(jobs_path):
        if raw.get('p1_company') not in COMPANIES or raw.get('status')=='removed' or raw.get('id') in known:continue
        url=raw.get('detail_url') or raw.get('source_url') or ''
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc or (not raw.get('description_raw') and not raw.get('index_only')):continue
        group,fields=new_fields_for_group(raw);identity=raw['id']
        if identity in candidates and candidates[identity]!=(group,fields):ambiguous.add(identity)
        candidates[identity]=(group,fields)
    candidates={k:v for k,v in candidates.items() if k not in ambiguous}
    S.save(out/'append-plan.json',{'source_sha256':S.digest(jobs_path),'candidates':candidates,'ambiguous':sorted(ambiguous)})
    state_path=out/'append-status.json';state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'created':{},'pending':None}
    if state.get('pending'):
        ids=state['pending']['job_ids'];recovered={}
        for table in current_tables():
            for jid,rid in read_id_matches(table,ids,out/f'{table}.uncertain-append-check.ndjson').items():
                recovered[jid]={'table':table,'record_id':rid}
        if set(recovered)!=set(ids):
            raise ValueError('previous append remains uncertain; preserved pending intent, no duplicate retry')
        state['created'].update(recovered);state['pending']=None;S.save(state_path,state)
    capacity=S.cli('+table-list','--base-token',S.BASE,'--format','json')['data']
    S.save(out/'append-capacity-preflight.json',{'tables':capacity,'limit_not_exposed':True,
           'on_quota_rejection':'stop pending; the next continuation table is created automatically when the last one nears the cap'})
    continuation_state=out/'continuation-state.json'
    continuation_alerts=out/'continuation-alerts.jsonl'
    for group in C.BASE_TABLE_NAMES:
        rows=[f for g,f in candidates.values() if g==group and f['job_id'] not in state['created']]
        if not rows:continue
        try:
            ensured=C.ensure_capacity(S.cli,S.BASE,group,len(rows),
                                      state_path=continuation_state,alert_path=continuation_alerts)
        except C.ContinuationError as error:
            # Creation failed (or a live table failed validation): never write
            # into an unvalidated/unavailable table; the run stays pending.
            state.setdefault('capacity_blocked',{})[group]={
                'job_ids':[r['job_id'] for r in rows],'error':str(error)[:500]}
            S.save(state_path,state);continue
        state.setdefault('continuation_created',[]).extend(ensured['created'])
        table=ensured['table_id']
        fields={f['name']:f for f in S.full_fields(table)}
        if NOTE_FIELD not in fields:raise ValueError('create note field before appending P1')
        expected={}
        for name in S.TARGETS:
            definition=S.writable_schema(fields[name]);needed={v for row in rows for v in row[name]}
            available={v['name'] for v in definition['options']}
            if needed-available or not definition.get('multiple'):
                S.save(out/f'{table}.append-schema-{fields[name]["id"]}.before.json',fields[name])
                definition['options'] += [{'name':n,'hue':'Blue','lightness':'Lighter'} for n in sorted(needed-available)]
                definition['multiple']=True
                response=S.cli('+field-update','--base-token',S.BASE,'--table-id',table,'--field-id',fields[name]['id'],
                               '--json',json.dumps(definition,ensure_ascii=False),'--yes')
                S.save(out/f'{table}.append-schema-{fields[name]["id"]}.json',response)
                expected[fields[name]['id']]=definition
        S.wait_schema_ready(table,expected)
        for start in range(0,len(rows),50):
            batch=rows[start:start+50];ids=[r['job_id'] for r in batch];existing={}
            for other in current_tables():
                existing.update(read_id_matches(other,ids,out/f'{table}.{other}.append-check-{start}.ndjson'))
            batch=[r for r in batch if r['job_id'] not in existing]
            if not batch:continue
            # Persist intent before the non-idempotent request; reconciliation
            # across ALL tables precedes every retry, including after interruption.
            state['pending']={'table':table,'job_ids':[r['job_id'] for r in batch]};S.save(state_path,state)
            body=out/f'{table}.append-batch-{start}.json';S.save(body,{'create_records':batch})
            try:
                response=S.cli('+record-batch-create','--base-token',S.BASE,'--table-id',table,'--json','@'+S.rel(body))
            except RuntimeError as error:
                state['error']=str(error)
                if quota_rejection(error):
                    # This definitive rejection created no records. Save the
                    # remaining IDs for the group, then let other groups continue.
                    state.setdefault('capacity_blocked',{})[group]={
                        'job_ids':[r['job_id'] for r in rows[start:]],'error':str(error)}
                    state['pending']=None;S.save(state_path,state)
                    break
                S.save(state_path,state);raise
            record_ids=response.get('data',{}).get('record_id_list',[])
            if len(record_ids)!=len(batch) or response.get('data',{}).get('ignored_fields'):
                raise ValueError('uncertain append result; reconcile before retry')
            for row,rid in zip(batch,record_ids):state['created'][row['job_id']]={'table':table,'record_id':rid}
            state['pending']=None;S.save(state_path,state);S.save(out/f'{table}.append-response-{start}.json',response)
            print(json.dumps({'appended_table':table,'new_records':len(batch),'total_created':len(state['created'])}),flush=True)
    state['finished']=not bool(state.get('capacity_blocked'));S.save(state_path,state)


def source_lifecycle_state(row):
    if row.get('status') == 'removed' and row.get('removal_reason') in {
            'Absent from complete current company/scope official listing',
            'Absent from complete current enterprise campaign listing',
            'Absent from complete current public listing'}:
        return 'expired'
    flag=row.get('source_is_active');proof=row.get('source_status_evidence')
    if type(flag) is not bool or not isinstance(proof,dict) or not proof:return None
    states={proof.get('list_status'),proof.get('detail_status')} - {None,''}
    if row.get('source_status_raw') not in states:return None
    if states & {'pause','closed'}:
        return 'expired' if flag is False and row.get('status') in {'expired','removed'} else None
    if states=={'open'} and flag is True and row.get('status') in {'open','unverified'}:
        return row['status']
    return None


def status_sync(out,jobs_path):
    """Refresh machine lifecycle states only when explicit source evidence exists."""
    backup=verified_backup(out);desired={};conflicts=set();skipped=[];changed=0
    for row in V.iter_json_file(jobs_path):
        identity=row.get('id');status=source_lifecycle_state(row)
        if not identity or status not in {'open','expired','unverified'}:continue
        if identity in desired and desired[identity]!=status:conflicts.add(identity)
        desired[identity]=status
    for table,meta in backup['tables'].items():
        records=json.loads(Path(meta['records']).read_text(encoding='utf-8'))
        pairs=[(r['record_id'],r['job_id']) for r in records if r.get('job_id') in desired and r['job_id'] not in conflicts]
        if not pairs:continue
        fields=S.full_fields(table);definition=next((f for f in fields if f['name']=='状态'),None)
        if not definition or definition['type']!='select':raise ValueError('lifecycle status schema drift')
        S.save(out/(table+'.status-schema.before.json'),definition)
        options={v['name'] for v in definition.get('options',[])}
        if not {desired[jid] for _,jid in pairs}<=options:raise ValueError('source lifecycle status option missing')
        for start in range(0,len(pairs),200):
            batch=pairs[start:start+200];before=out/f'{table}.status-before-{start}.ndjson'
            S.cli('+record-get','--base-token',S.BASE,'--table-id',table,'--json',json.dumps({'record_id_list':[rid for rid,_ in batch]}),
                  '--field-id','状态','--field-id','job_id','--format','ndjson','--output',S.rel(before),'--overwrite')
            saved=[json.loads(line) for line in before.read_text(encoding='utf-8').splitlines()]
            prior={r['record_id']:r.get('状态') or [] for r in saved}
            saved_ids={r['record_id']:r.get('job_id') for r in saved}
            if any(saved_ids.get(rid)!=jid for rid,jid in batch):raise ValueError('record identity changed after snapshot')
            if set(prior)!={rid for rid,_ in batch}:raise ValueError('status backup records missing')
            updates={}
            for rid,jid in batch:
                old=prior[rid]
                if any(value not in {'open','expired','unverified'} for value in old):
                    skipped.append({'table':table,'record_id':rid,'reason':'human lifecycle value retained'});continue
                if old!=[desired[jid]]:updates[rid]={'状态':[desired[jid]]}
            if updates:
                # Re-read immediately before mutation; no stale backup overwrites.
                check=out/f'{table}.status-cas-{start}.ndjson'
                S.cli('+record-get','--base-token',S.BASE,'--table-id',table,'--json',json.dumps({'record_id_list':list(updates)}),
                      '--field-id','状态','--field-id','job_id','--format','ndjson','--output',S.rel(check),'--overwrite')
                current=[json.loads(line) for line in check.read_text(encoding='utf-8').splitlines()]
                live={r['record_id']:r.get('状态') or [] for r in current}
                live_ids={r['record_id']:r.get('job_id') for r in current}
                if any(live.get(rid)!=prior[rid] or live_ids.get(rid)!=saved_ids[rid] for rid in updates):raise ValueError('status changed after backup')
                body=out/f'{table}.status-batch-{start}.json';S.save(body,{'update_records':updates})
                response=S.cli('+record-batch-update','--base-token',S.BASE,'--table-id',table,'--json','@'+S.rel(body))
                if response.get('data',{}).get('ignored_fields'):raise ValueError('status field ignored')
                S.save(out/f'{table}.status-response-{start}.json',response);changed+=len(updates)
    S.save(out/'source-status-sync.json',{'changed':changed,'human_values_preserved':skipped,'conflicting_ids':sorted(conflicts),'finished':True})
    print(json.dumps({'source_status_updated':changed,'human_values_preserved':len(skipped)}),flush=True)


def business_fields(raw):
    """Only existing product-owned business columns; review time is never a trigger."""
    v, _ = V.convert(raw)
    return {'岗位名称':v['job_title'],
            '公司名称':raw.get('p1_company') or raw.get('canonical_company') or raw.get('recruitment_unit') or '',
            '招聘单位':raw.get('recruiting_unit_raw') or raw.get('recruitment_unit') or '',
            '原链接':raw.get('source_url') or raw.get('detail_url') or '',
            '投递入口':raw.get('application_url') or raw.get('detail_url') or '',
            '来源':raw.get('source_name') or '', '投递截止':str(raw.get('deadline') or ''),
            '岗位大类':[v['job_category']],
            '招聘性质':[{'校园招聘':'校招','实习招聘':'实习','社会招聘':'社招'}.get(raw.get('recruitment_type'), '未注明')],
            '岗位描述':str(raw.get('description_raw') or '')}


URL_MARKDOWN = re.compile(r'^\[[^\]]*\]\(([^()]+)\)$')
# The live Base declares 原链接/投递入口 as plain 'text' fields (confirmed against
# every table's *.fields.before.json in the 2026-09-17 run directory), not the
# dedicated Lark 'url' field type — Feishu still auto-linkifies a bare url typed
# into a text cell and echoes it back as markdown on read. Comparison therefore
# cannot rely on field_types alone; these two link-carrying field names (the
# same ones business_fields()/new_fields() populate from source_url/detail_url/
# application_url) are the authoritative source of truth, checked in addition
# to (never instead of) an actual schema type of 'url' should that ever change.
LINK_FIELD_NAMES = {'原链接', '投递入口'}


def normalize_url_field(value):
    """Reduce a Lark url-type cell echo to its bare link target.

    lark-cli's ndjson readback for a ``url`` field can come back as a
    markdown link ``[text](url)``, a bare url string, a ``{"link":...,
    "text":...}`` object, or a one-item list of any of those. Comparison
    must only care about the link target, never the display text, so this
    always resolves to that target (and to '' when there is none, so an
    empty old value still registers as a difference against a real url).
    """
    if isinstance(value, list):
        for item in value:
            normalized = normalize_url_field(item)
            if normalized:
                return normalized
        return ''
    if isinstance(value, dict):
        return normalize_url_field(value.get('link'))
    text = str(value or '').strip()
    match = URL_MARKDOWN.match(text)
    return match.group(1).strip() if match else text


def business_delta(old, desired, field_types=None):
    field_types = field_types or {}
    result = {}
    for name, value in desired.items():
        if isinstance(value, list):
            changed = set(old.get(name) or []) != set(value)
        elif field_types.get(name) == 'url' or name in LINK_FIELD_NAMES:
            changed = normalize_url_field(old.get(name)) != normalize_url_field(value)
        else:
            changed = str(old.get(name) or '') != value
        if changed:
            result[name] = value
    return result


def business_sync(out, jobs_path):
    """Update changed business fields after backup and identity/value CAS reads."""
    backup=verified_backup(out);desired={};ambiguous=set();changed=0
    for raw in V.iter_json_file(jobs_path):
        identity=raw.get('id')
        if not identity or raw.get('status') == 'removed':continue
        value=business_fields(raw)
        if identity in desired and desired[identity] != value:ambiguous.add(identity)
        desired[identity]=value
    for table,meta in backup['tables'].items():
        definitions={f['name']:f for f in S.full_fields(table)}
        names=[n for n in next(iter(desired.values()),{}) if n in definitions
               and definitions[n]['type'] in {'text','select','url'}]
        field_types={n:definitions[n]['type'] for n in names}
        records=json.loads(Path(meta['records']).read_text(encoding='utf-8'))
        pairs=[(r['record_id'],r['job_id']) for r in records if r.get('job_id') in desired and r['job_id'] not in ambiguous]
        def read(batch, path):
            args=['+record-get','--base-token',S.BASE,'--table-id',table,'--json',json.dumps({'record_id_list':[rid for rid,_ in batch]}),
                  '--format','ndjson','--output',S.rel(path),'--overwrite','--field-id','job_id']
            for name in names:args.extend(['--field-id',name])
            response=S.cli(*args)
            if response.get('record_not_found') or response.get('ignored_fields'):raise ValueError('business read incomplete')
            rows={r['record_id']:r for r in (json.loads(x) for x in path.read_text(encoding='utf-8').splitlines())}
            if set(rows)!={rid for rid,_ in batch} or any(rows[rid].get('job_id')!=jid for rid,jid in batch):
                raise ValueError('business record identity drift')
            return rows
        for start in range(0,len(pairs),200):
            batch=pairs[start:start+200];prior=read(batch,out/f'{table}.business-before-{start}.ndjson');updates={}
            for rid,jid in batch:
                wanted={n:desired[jid][n] for n in names}
                # Never invent a select option or silently reset a human vocabulary.
                for n in list(wanted):
                    if definitions[n]['type']=='select' and not set(wanted[n]) <= {o['name'] for o in definitions[n].get('options',[])}:
                        del wanted[n]
                delta=business_delta(prior[rid],wanted,field_types)
                if delta:updates[rid]=delta
            if not updates:continue
            check=read([(rid,jid) for rid,jid in batch if rid in updates],out/f'{table}.business-cas-{start}.ndjson')
            if any(check[rid]!=prior[rid] for rid in updates):raise ValueError('business values changed after backup')
            body=out/f'{table}.business-batch-{start}.json';S.save(body,{'update_records':updates})
            response=S.cli('+record-batch-update','--base-token',S.BASE,'--table-id',table,'--json','@'+S.rel(body))
            if response.get('data',{}).get('ignored_fields'):raise ValueError('business field ignored')
            S.save(out/f'{table}.business-response-{start}.json',response);changed+=len(updates)
    S.save(out/'business-sync.json',{'changed':changed,'conflicting_ids':sorted(ambiguous),'finished':True})


def deduplicate_exact(out, jobs_path):
    """Only collapse identical cells for the same known job ID; retain conflicts."""
    backup=verified_backup(out);known={str(r['id']) for r in V.iter_json_file(jobs_path) if r.get('id')}
    groups={}
    for table,meta in backup['tables'].items():
        for r in json.loads(Path(meta['records']).read_text(encoding='utf-8')):
            if r.get('job_id') in known:groups.setdefault(r['job_id'],[]).append((table,r['record_id']))
    duplicates={k:v for k,v in groups.items() if len(v)>1};deleted=[];conflicts=[]
    for number,(jid,pairs) in enumerate(sorted(duplicates.items())):
        saved=[]
        for pos,(table,rid) in enumerate(pairs):
            definitions=S.full_fields(table)
            if any(f['type'] not in {'text','select'} for f in definitions):
                saved=[];break  # Attachments, links or computed fields need separate review.
            names=sorted(f['name'] for f in definitions)
            path=out/f'duplicate-{number}-{pos}.before.ndjson'
            args=['+record-get','--base-token',S.BASE,'--table-id',table,'--record-id',rid,
                  '--format','ndjson','--output',S.rel(path),'--overwrite']
            for name in names:args.extend(['--field-id',name])
            response=S.cli(*args)
            if response.get('ignored_fields') or response.get('record_not_found') or response.get('data',{}).get('ignored_fields'):
                raise ValueError('duplicate read incomplete; no deletion')
            values=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
            if len(values)!=1 or values[0].get('job_id')!=jid:raise ValueError('duplicate identity drift')
            cells={n:values[0].get(n) for n in names}
            saved.append((table,rid,cells,args))
        if not saved or any(v[2]!=saved[0][2] for v in saved[1:]):
            conflicts.append({'job_id':jid,'records':pairs,'reason':'different cells/schema or protected field types'});continue
        # Recheck every member before deleting; all full cell backups remain on disk.
        for table,rid,cells,args in saved:
            check=list(args);path=out/f'duplicate-{number}-{rid}.cas.ndjson';check[check.index('--output')+1]=S.rel(path)
            response=S.cli(*check)
            if response.get('ignored_fields') or response.get('record_not_found') or response.get('data',{}).get('ignored_fields'):
                raise ValueError('duplicate CAS read incomplete; no deletion')
            values=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
            if len(values)!=1 or {n:values[0].get(n) for n in cells}!=cells:raise ValueError('duplicate changed after backup')
        for table,rid,_,_ in saved[1:]:
            response=S.cli('+record-delete','--base-token',S.BASE,'--table-id',table,'--record-id',rid,'--yes')
            S.save(out/f'duplicate-{number}-{rid}.delete.json',response);deleted.append({'job_id':jid,'table':table,'record_id':rid})
    S.save(out/'duplicate-reconciliation.json',{'duplicate_id_groups':len(duplicates),'deleted':deleted,'conflicts_retained':conflicts,'finished':True})
