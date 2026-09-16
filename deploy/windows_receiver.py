#!/usr/bin/env python3
"""Forced-command SSH endpoint: export jobs or CAS-publish a bounded full snapshot."""
from collections import Counter
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
sys.path.insert(0, '/opt/mcp-suite')
from qiuzhao.v4_fields import iter_json_file
ROOT=Path('/var/lib/mcp-suite')
JOBS=ROOT/'jobs.json'
LIMIT=1024*1024*1024

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def identities(path):
    ids=Counter()
    for row in iter_json_file(path,chunk_bytes=65536,strict=True):
        if not isinstance(row,dict) or not row.get('job_title'):
            raise ValueError('invalid record')
        key=('id:'+str(row['id'])) if row.get('id') else 'legacy:'+hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if row.get('id'):ids[key]=1
        else:ids[key]+=1
    if not ids:raise ValueError('empty snapshot')
    return ids

def main():
    command=os.environ.get('SSH_ORIGINAL_COMMAND','')
    if command=='status':
        print(json.dumps(dict(sha256=digest(JOBS),bytes=JOBS.stat().st_size)));return
    if command=='snapshot':
        # The lock covers the entire stream and its accompanying hash receipt.
        with open(ROOT/'collector.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            before=digest(JOBS)
            sys.stdout.buffer.write((before+'\n').encode());sys.stdout.buffer.flush()
            with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=3) as out:
                with JOBS.open('rb') as source:shutil.copyfileobj(source,out,1024*1024)
        return
    match=re.fullmatch(r'publish ([0-9a-f]{64}) ([0-9a-f]{64})',command)
    if not match:raise ValueError('unsupported command')
    expected,after=match.groups()
    with open(ROOT/'collector.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if digest(JOBS)==after:
            print(json.dumps(dict(published=True,already_published=True,after_sha256=after)));return
        if digest(JOBS)!=expected:raise ValueError('production changed: pull and recollect')
        fd,name=tempfile.mkstemp(prefix='.windows-jobs.',dir=ROOT)
        incoming=Path(name)
        try:
            size=0
            with os.fdopen(fd,'wb') as out,gzip.GzipFile(fileobj=sys.stdin.buffer,mode='rb') as source:
                while True:
                    data=source.read(1024*1024)
                    if not data:break
                    size+=len(data)
                    if size>LIMIT:raise ValueError('snapshot too large')
                    out.write(data)
                out.flush();os.fsync(out.fileno())
            if digest(incoming)!=after:raise ValueError('upload hash mismatch')
            old_ids=identities(JOBS);new_ids=identities(incoming)
            if not old_ids<=new_ids:raise ValueError('snapshot drops existing identities')
            if digest(JOBS)!=expected:raise ValueError('CAS mismatch')
            backup=ROOT/('jobs.json.bak.windows.'+dt.datetime.now().strftime('%Y%m%dT%H%M%S'))
            shutil.copyfile(JOBS,backup)
            if digest(backup)!=expected:raise ValueError('backup mismatch')
            st=JOBS.stat();os.chmod(incoming,st.st_mode&0o777);os.chown(incoming,st.st_uid,st.st_gid)
            os.replace(incoming,JOBS)
            print(json.dumps(dict(published=True,before_sha256=expected,after_sha256=after,identities=len(new_ids),backup=str(backup))))
        finally:
            incoming.unlink(missing_ok=True)
if __name__=='__main__':main()
