"""Internal backup maintenance only; receiver request/response/auth contracts stay unchanged."""
from pathlib import Path
import gzip,hashlib,json,os,re,shutil,stat,subprocess,tempfile,time
ROOT=Path('/var/lib/mcp-suite')
RAW=re.compile(r'^jobs\.json\.bak\.windows\.\d{8}T\d{6}$')
R0_BACKUP='jobs.json.bak.windows.20260921T181458'
UPLOAD_LIMIT=1024**3
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def raw_backups(root):
 found=[]
 for p in root.iterdir():
  if not RAW.fullmatch(p.name):continue
  st=p.lstat()
  if not stat.S_ISREG(st.st_mode) or p.is_symlink():raise ValueError('non-regular backup rejected: '+str(p))
  found.append(p)
 return sorted(found,key=lambda p:p.name)
def protected_names(paths):return {R0_BACKUP}|{p.name for p in paths[-2:]}
def sync_dir(root):
 fd=os.open(root,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
 try:os.fsync(fd)
 finally:os.close(fd)
def append_receipt(root,item):
 with (root/'jobs.json.bak.windows.rotation-receipts.jsonl').open('a',encoding='utf8') as f:
  f.write(json.dumps(item,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 sync_dir(root)
def validate_gzip(path,expected_hash,expected_size):
 subprocess.run(['gzip','-t','--',str(path)],capture_output=True,check=True,timeout=600)
 h=hashlib.sha256();size=0
 with gzip.open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b);size+=len(b)
 if h.hexdigest()!=expected_hash or size!=expected_size:raise ValueError('gzip content does not match original')
def plan(root=ROOT):
 paths=raw_backups(root);protected=protected_names(paths)
 return [{'source':str(p),'bytes':p.stat().st_size,'sha256':digest(p),'protected':p.name in protected} for p in paths]
def rotate_backups(root=ROOT):
 root=Path(root);paths=raw_backups(root);protected=protected_names(paths);done=[]
 if not (root/R0_BACKUP).is_file():raise ValueError('fixed R0 rollback original is missing')
 for source in paths:
  if source.name in protected:continue
  before=source.stat();original_hash=digest(source);dest=source.with_name(source.name+'.gz')
  record={'source':str(source),'source_bytes':before.st_size,'source_sha256':original_hash,'gzip_path':str(dest),'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'restore_command':"gzip -dk -- '"+str(dest)+"' && sha256sum '"+str(source)+"'"}
  if dest.exists():
   if dest.is_symlink() or not stat.S_ISREG(dest.lstat().st_mode):raise ValueError('non-regular gzip destination')
   validate_gzip(dest,original_hash,before.st_size)
  else:
   fd,name=tempfile.mkstemp(prefix=source.name+'.gz.tmp.',dir=root);tmp=Path(name)
   try:
    with os.fdopen(fd,'wb') as out:
     with gzip.GzipFile(filename='',fileobj=out,mode='wb',compresslevel=3,mtime=0) as zipped,source.open('rb') as inp:shutil.copyfileobj(inp,zipped,1024*1024)
     out.flush();os.fsync(out.fileno())
    validate_gzip(tmp,original_hash,before.st_size)
    os.chmod(tmp,before.st_mode&0o777);os.chown(tmp,before.st_uid,before.st_gid)
    if dest.exists():raise ValueError('gzip destination appeared concurrently')
    os.replace(tmp,dest)
   finally:tmp.unlink(missing_ok=True)
  with dest.open('rb') as f:os.fsync(f.fileno())
  sync_dir(root)
  after=source.stat()
  if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or digest(source)!=original_hash:raise ValueError('original backup drifted during compression')
  if source.name in protected_names(raw_backups(root)):raise ValueError('original became protected')
  record.update(gzip_bytes=dest.stat().st_size,gzip_sha256=digest(dest),status='verified_gzip_original_pending_removal')
  append_receipt(root,record)  # durable recovery map before removing the redundant original
  source.unlink();sync_dir(root)
  record['status']='rotated';append_receipt(root,record);done.append(record)
 return done
def ensure_capacity(root=ROOT,current_bytes=None):
 root=Path(root);current_bytes=current_bytes if current_bytes is not None else (root/'jobs.json').stat().st_size
 required=2*current_bytes+UPLOAD_LIMIT+256*1024**2
 free=shutil.disk_usage(root).free
 if free<required:raise ValueError(f'capacity gate: free={free} required={required}; publication stopped before upload')
 return {'free_bytes':free,'required_bytes':required}
if __name__=='__main__':
 import argparse,fcntl
 ap=argparse.ArgumentParser();ap.add_argument('--plan',action='store_true');ap.add_argument('--apply',action='store_true');ap.add_argument('--deferred',action='store_true');a=ap.parse_args()
 if a.plan:print(json.dumps({'plan':plan(),'space':ensure_capacity()},ensure_ascii=False))
 elif a.apply:
  with (ROOT/'collector.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX if a.deferred else fcntl.LOCK_EX|fcntl.LOCK_NB)
   try:
    done=rotate_backups();space=ensure_capacity();append_receipt(ROOT,{'status':'rotation_completed','rotated_count':len(done),'space':space,'at':time.strftime('%Y-%m-%dT%H:%M:%S%z')});print(json.dumps({'rotated':done,'space':space},ensure_ascii=False))
   except BaseException as exc:
    append_receipt(ROOT,{'status':'maintenance_failed','error':type(exc).__name__+': '+str(exc),'at':time.strftime('%Y-%m-%dT%H:%M:%S%z')});raise
 else:ap.error('choose --plan or --apply')
