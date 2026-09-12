"""Validate hashed official evidence bundles and merge them without replaying the crawl.

Import status is separate from daily collection status. Source observation times
are preserved; import/validation times are reported as separate events.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
from qiuzhao.collector import p1_pipeline as P


def safe_path(root, relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('bundle path escapes root')
    return path


def build(manifests, output):
    output=Path(output)
    if output.exists():raise ValueError('use a new bundle directory')
    output.mkdir(parents=True)
    entries=[];seen=set()
    for manifest_path in manifests:
        manifest=json.loads(Path(manifest_path).read_text())
        author_rows = manifest.get('rows')
        if author_rows is None:
            author_rows = [dict(r, candidate=r['candidate_path'], sha256=r['candidate_sha256'])
                           for r in manifest['candidates'] if r.get('candidate_path')]
        for row in author_rows:
            company,scope=row['company'],row['scope'];key=(company,scope)
            if company not in P.COMPANIES or scope not in P.SCOPES or key in seen:
                raise ValueError('unknown or repeated company/scope in input manifests')
            seen.add(key);candidate=Path(row['candidate']).resolve()
            raw=candidate.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']:
                raise ValueError('author candidate changed after receipt: '+str(candidate))
            payload=json.loads(raw);source=candidate.parent
            # Copy only this scope's official capture files, not its surrounding
            # research directory or development probes.
            target=output/f'{P.COMPANIES.index(company)+1:02d}'/scope
            target.mkdir(parents=True)
            for path in source.rglob('*'):
                if not path.is_file() or path.resolve()==candidate:continue
                if not path.resolve().is_relative_to(source):raise ValueError('capture symlink escaped source scope')
                dest=target/path.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
            def reference(value):
                if not isinstance(value,str):return value
                path=Path(value)
                if not path.is_absolute():return value
                if path.is_relative_to(source):return str(path.relative_to(source))
                shared=source.parent/'shared'
                if path.is_relative_to(shared) and path.is_file():
                    dest=target.parent/'shared'/path.relative_to(shared);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
                    return '../shared/'+str(path.relative_to(shared))
                # Descriptive evidence strings/URLs stay untouched; absolute
                # file references outside this company are rejected.
                raise ValueError('external evidence file reference: '+value)
            def rebase_metadata(value):
                if isinstance(value,list):
                    for item in value:rebase_metadata(item)
                elif isinstance(value,dict):
                    for key,item in list(value.items()):
                        if key in {'evidence_files','evidence'} and isinstance(item,list):
                            value[key]=[reference(x) if isinstance(x,str) and x.startswith('/') else x for x in item]
                        elif key in {'evidence_path','listing_evidence_path','detail_evidence_path','campaign_evidence_path','evidence_file','last_page_evidence'} and isinstance(item,str) and item.startswith('/'):
                            value[key]=reference(item)
                        else:rebase_metadata(item)
            rebase_metadata(payload)
            validated=P.validate_result(payload,company,scope,target)
            path=target/'candidate.json';P.atomic_json(path,validated)
            entries.append({'company':company,'scope':scope,'candidate':str(path.relative_to(output)),
                'author_sha256':row['sha256'],'source_candidate':str(candidate),
                'source_reviewed_at_min':min((j.get('reviewed_at','') for j in payload['jobs']),default=None),
                'source_reviewed_at_max':max((j.get('reviewed_at','') for j in payload['jobs']),default=None)})
    entries.sort(key=lambda x:(P.COMPANIES.index(x['company']),list(P.SCOPES).index(x['scope'])))
    hashes={str(p.relative_to(output)):P.sha(p) for p in output.rglob('*') if p.is_file()}
    P.atomic_json(output/'manifest.json',{'entries':entries,'files':hashes,'built_at':P.now()})
    return {'scopes':len(entries),'files':len(hashes),'bytes':sum(p.stat().st_size for p in output.rglob('*') if p.is_file())}


def import_bundle(bundle,data_dir,apply=False):
    bundle,data_dir=Path(bundle).resolve(),Path(data_dir)
    manifest=json.loads((bundle/'manifest.json').read_text())
    for relative,digest in manifest['files'].items():
        if P.sha(safe_path(bundle,relative))!=digest:raise ValueError('bundle hash mismatch: '+relative)
    seen=set();validated=[]
    for entry in manifest['entries']:
        key=(entry['company'],entry['scope'])
        if key in seen or key[0] not in P.COMPANIES or key[1] not in P.SCOPES:raise ValueError('invalid bundle scope selection')
        seen.add(key);path=safe_path(bundle,entry['candidate'])
        if entry['candidate'] not in manifest['files']:raise ValueError('unhashed candidate')
        payload=P.validate_result(json.loads(path.read_text()),*key,path.parent)
        for reference in payload['coverage'].get('evidence_files',[]):
            evidence=(path.parent/reference).resolve()
            if not evidence.is_relative_to(bundle) or str(evidence.relative_to(bundle)) not in manifest['files']:
                raise ValueError('unhashed evidence')
        for pending in payload.get('pending_index',[]):
            for key in ('listing_evidence_path','detail_evidence_path'):
                if not pending.get(key):continue
                evidence=(path.parent/pending[key]).resolve()
                if not evidence.is_relative_to(bundle) or str(evidence.relative_to(bundle)) not in manifest['files']:
                    raise ValueError('unhashed pending evidence')
        validated.append((entry,payload))
    validated.sort(key=lambda pair:(P.COMPANIES.index(pair[0]['company']),list(P.SCOPES).index(pair[0]['scope'])))
    if not apply:return {'validated_scopes':len(validated),'apply':False}
    data_dir.mkdir(parents=True,exist_ok=True)
    with (data_dir/'collector.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt_path=bundle/'import-receipt.json'
        receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else {'manifest_sha256':P.sha(bundle/'manifest.json'),'results':{}}
        if receipt['manifest_sha256']!=P.sha(bundle/'manifest.json'):raise ValueError('bundle changed after partial import')
        for entry,payload in validated:
            company,scope=entry['company'],entry['scope'];key=company+'/'+scope
            if key in receipt['results']:continue
            publication=None
            if payload['jobs'] or payload.get('pending_index') or payload['coverage'].get('complete'):
                publication=P.publish(data_dir,[(company,scope,payload)],bundle/'publication')
            receipt['results'][key]={'coverage':payload['coverage'],'publication':publication,
                'source_reviewed_at_min':entry.get('source_reviewed_at_min'),
                'source_reviewed_at_max':entry.get('source_reviewed_at_max'),'imported_at':P.now()}
            P.atomic_json(receipt_path,receipt)
            print(json.dumps({'imported':key,'status':payload['coverage']['status'],
                              'jobs':len(payload['jobs']),'published':publication is not None},ensure_ascii=False),flush=True)
        receipt['finished']=True;P.atomic_json(receipt_path,receipt)
        return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',action='append',help='author manifests for local bundle construction')
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,default=Path('/var/lib/mcp-suite'))
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.manifest:
        if args.apply:parser.error('build and apply must be separate steps')
        print(json.dumps(build(args.manifest,args.bundle)))
    else:
        result=import_bundle(args.bundle,args.data_dir,args.apply)
        if not args.apply:print(json.dumps(result))


if __name__=='__main__':main()
