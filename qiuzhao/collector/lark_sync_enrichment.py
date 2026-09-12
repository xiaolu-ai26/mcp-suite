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

NOTE_FIELD = '届别条件说明'
NOTE_STATE = Path(__file__).resolve().parents[1] / 'data' / 'lark-note-ownership.json'
HARDWARE = {'大疆','华为','OPPO','vivo','荣耀','比亚迪','宁德时代','联想','海康威视','安克创新','影石Insta360',
            '中兴通讯','大华股份','汇川技术','TP-LINK普联','石头科技','科沃斯','理想汽车','小鹏汽车','蔚来汽车','吉利汽车','长城汽车','小米'}
PHARMA = {'迈瑞医疗','恒瑞医药','药明康德'}


def route(company):
    # Product categorization approved for NEW records only, not an official
    # industry classification and never a reason to move an existing record.
    if company in HARDWARE:
        return S.TABLES[2], '制造/工业'
    if company in PHARMA:
        return S.TABLES[3], '医药/医疗'
    return S.INTERNET_CONTINUATION, '互联网/科技'


def qualification_note(raw):
    parts=[]
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
    if parts:return '\n'.join(parts)
    if cohort:
        return '历史届别标签：'+cohort+'。缺少可核对的岗位资格原句，待回源核实。'
    _,_,note,_=V.graduation_of(raw)
    return (note or '未注明')+'；现有记录未提供明确毕业日期范围，请按原链接核验。'


def verified_backup(out):
    backup=json.loads((out/'backup.json').read_text())
    if backup.get('base')!=S.BASE or not S.valid_table_selection(backup.get('tables',{})):
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
    return {r['job_id']:r['record_id'] for r in (json.loads(x) for x in path.read_text().splitlines()) if r.get('job_id')}


def ensure_note_fields(out,tables=None):
    for table in (tables if tables is not None else S.TABLES):
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
    ownership=json.loads(NOTE_STATE.read_text()) if NOTE_STATE.exists() else {}
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
        records=json.loads(Path(backup['tables'][table]['records']).read_text())
        pairs=[(r['record_id'],r['job_id']) for r in records if r.get('job_id') in notes and r['job_id'] not in ambiguous]
        for start in range(0,len(pairs),200):
            batch=pairs[start:start+200];before=out/f'{table}.note-before-{start}.ndjson'
            S.cli('+record-get','--base-token',S.BASE,'--table-id',table,'--json',json.dumps({'record_id_list':[r for r,_ in batch]}),
                '--field-id',NOTE_FIELD,'--format','ndjson','--output',S.rel(before),'--overwrite')
            prior={r['record_id']:r.get(NOTE_FIELD) for r in (json.loads(x) for x in before.read_text().splitlines())}
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


def new_fields(raw):
    table,industry=route(raw['p1_company']);v,_=V.convert(raw)
    fields={'job_id':raw['id'],'岗位名称':v['job_title'],'公司名称':raw['p1_company'],
            '招聘单位':raw.get('recruiting_unit_raw') or raw.get('recruitment_unit') or raw['p1_company'],
            '行业':[industry],'招聘性质':[{'校园招聘':'校招','实习招聘':'实习','社会招聘':'社招'}[raw['recruitment_type']]],
            '岗位大类':[v['job_category']],'状态':[raw.get('status') or 'unverified'],
            '原链接':raw.get('source_url') or raw['detail_url'],'投递入口':raw.get('application_url') or raw['detail_url'],
            '复核时间':str(raw.get('reviewed_at') or ''),'来源':raw.get('source_name') or raw['p1_company']+'官方招聘',
            NOTE_FIELD:qualification_note(raw),**S.values_for(raw)}
    if raw.get('deadline'):fields['投递截止']=str(raw['deadline'])
    return table,fields


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
    if set(backup['tables'])!=set(S.TABLES):
        raise ValueError('append requires complete backup including approved continuation table')
    ensure_note_fields(out)
    for meta in backup['tables'].values():
        known.update(r.get('job_id') for r in json.loads(Path(meta['records']).read_text()) if r.get('job_id'))
    candidates={};ambiguous=set()
    for raw in V.iter_json_file(jobs_path):
        if raw.get('p1_company') not in COMPANIES or raw.get('status')=='removed' or raw.get('id') in known:continue
        url=raw.get('detail_url') or raw.get('source_url') or ''
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc or not raw.get('description_raw'):continue
        table,fields=new_fields(raw);identity=raw['id']
        if identity in candidates and candidates[identity]!=(table,fields):ambiguous.add(identity)
        candidates[identity]=(table,fields)
    candidates={k:v for k,v in candidates.items() if k not in ambiguous}
    S.save(out/'append-plan.json',{'source_sha256':S.digest(jobs_path),'candidates':candidates,'ambiguous':sorted(ambiguous)})
    state_path=out/'append-status.json';state=json.loads(state_path.read_text()) if state_path.exists() else {'created':{},'pending':None}
    if state.get('pending'):
        ids=state['pending']['job_ids'];recovered={}
        for table in S.TABLES:
            for jid,rid in read_id_matches(table,ids,out/f'{table}.uncertain-append-check.ndjson').items():
                recovered[jid]={'table':table,'record_id':rid}
        if set(recovered)!=set(ids):
            raise ValueError('previous append remains uncertain; preserved pending intent, no duplicate retry')
        state['created'].update(recovered);state['pending']=None;S.save(state_path,state)
    capacity=S.cli('+table-list','--base-token',S.BASE,'--format','json')['data']
    S.save(out/'append-capacity-preflight.json',{'tables':capacity,'limit_not_exposed':True,'on_quota_rejection':'stop pending; no upgrade or new table'})
    for table in S.TABLES:
        rows=[f for t,f in candidates.values() if t==table and f['job_id'] not in state['created']]
        if not rows:continue
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
            for other in S.TABLES:
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
                    # remaining IDs per table, then let other tables continue.
                    state.setdefault('capacity_blocked',{})[table]={
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
