"""Evidence-bound availability repairs without replacing public job content."""
from __future__ import annotations
import copy,fcntl,gzip,json,shutil
from pathlib import Path
from . import p1_pipeline as P

FIELDS={'source_list_status_raw','source_detail_status_raw','source_status_raw','source_status_evidence',
        'source_status_dates','status','source_is_active','status_note','source_status_conflict'}

def repair_rows(previous,patches):
    updates={}
    for patch in patches:
        key=(patch['company'],patch['scope'],patch['source_record_id'])
        value=patch['updates']
        if key in updates or not set(value)<=FIELDS:raise ValueError('duplicate patch or unauthorized field')
        if value.get('status')!='expired' or value.get('source_is_active') is not False:
            raise ValueError('repair may only mark explicitly inactive official roles')
        if not {value.get('source_list_status_raw'),value.get('source_detail_status_raw')}&{'pause','closed'}:
            raise ValueError('inactive official status evidence required')
        updates[key]=value
    result=list(previous);changed=[]
    for index,row in enumerate(previous):
        key=(row.get('p1_company'),row.get('p1_scope'),P.official_uuid(row))
        if key not in updates:continue
        if row.get('status')=='removed':continue
        value=updates[key]
        if all(row.get(k)==v for k,v in value.items()):continue
        fixed=copy.deepcopy(row);fixed.update(copy.deepcopy(value));result[index]=fixed
        changed.append({'id':row['id'],'company':key[0],'scope':key[1],'source_record_id':key[2],
                        'before_status':row.get('status'),'after_status':fixed['status']})
    return result,changed


def apply(bundle,data_dir):
    bundle=Path(bundle).resolve();data_dir=Path(data_dir);manifest=json.loads((bundle/'patch.json').read_text())
    for rel,digest in manifest['files'].items():
        path=(bundle/rel).resolve()
        if not path.is_relative_to(bundle) or P.sha(path)!=digest:raise ValueError('status evidence hash mismatch')
    for patch in manifest['patches']:
        ref=patch['updates']['source_status_evidence']['evidence_file']
        if ref not in manifest['files']:raise ValueError('unhashed status evidence')
    with (data_dir/'collector.lock').open('a') as outer,(data_dir/'p1-publish.lock').open('a') as inner:
        fcntl.flock(outer,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(inner,fcntl.LOCK_EX)
        jobs=data_dir/'jobs.json';before=P.sha(jobs);previous=json.loads(jobs.read_text())
        merged,changed=repair_rows(previous,manifest['patches'])
        backup=bundle/'jobs.before.json.gz';backup_meta=bundle/'backup.json'
        if not backup.exists():
            with jobs.open('rb') as source,gzip.open(backup,'wb',compresslevel=3) as dest:shutil.copyfileobj(source,dest)
            with gzip.open(backup,'rb') as source:backup_hash=P.stream_sha(source)
            if backup_hash!=before:raise ValueError('backup mismatch')
            P.atomic_json(backup_meta,{'sha256':backup_hash})
        else:
            backup_hash=json.loads(backup_meta.read_text())['sha256']
            with gzip.open(backup,'rb') as source:
                if P.stream_sha(source)!=backup_hash:raise ValueError('existing backup corrupt')
        if P.sha(jobs)!=before:raise ValueError('production changed during repair')
        P.atomic_json(jobs,merged)
        receipt={'before_sha256':before,'after_sha256':P.sha(jobs),'backup':str(backup),
                 'backup_sha256':backup_hash,'changed':changed,'count':len(changed),'finished_at':P.now()}
        P.atomic_json(bundle/'receipt.json',receipt);return receipt

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--data-dir',default='/var/lib/mcp-suite');a=p.parse_args()
    result=apply(a.bundle,a.data_dir);print(json.dumps({'changed':result['count'],'after_sha256':result['after_sha256']}))
