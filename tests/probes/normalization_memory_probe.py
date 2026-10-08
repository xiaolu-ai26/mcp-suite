"""One-process bounded-memory probe of the actual normalize_file entry.

Usage (Linux only): python .../normalization_memory_probe.py --module path/to/normalize.py
    --input isolated/jobs.json --limit-mib 128
Business normalization is a no-op callback so this measures actual old/new I/O,
not memory consumed by the geography/mapping assets. Never pass production data.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import stat as stat_mod
import sys
import tempfile
import time

parser=argparse.ArgumentParser()
parser.add_argument('--module',type=Path,required=True)
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--limit-mib',type=int,default=128)
args=parser.parse_args()
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
node=next(n for n in ast.parse(args.module.read_text(encoding='utf-8')).body
          if isinstance(n,ast.FunctionDef) and n.name=='normalize_file')
class CN:
    @staticmethod
    def table_info():return {}
namespace={'json':json,'os':os,'Path':Path,'stat_mod':stat_mod,'tempfile':tempfile,
           'REPORTED_FIELDS':['normalized'],'_is_empty':lambda v:v in (None,'',[]),
           '_normalize_one':lambda row,stats:None,
           'normalize_records':lambda records:{'normalized':0},'_TABLES':{},'CN':CN}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(args.module),'exec'),namespace)
# The module source is now compiled; apply the same address-space limit to each run.
resource.setrlimit(resource.RLIMIT_AS,(args.limit_mib*1024**2,args.limit_mib*1024**2))
start=time.monotonic()
try:
    result=namespace['normalize_file'](args.input)
    outcome={'outcome':'passed','records':result['records'],'written':result['written']}
except MemoryError:
    outcome={'outcome':'MemoryError'}
outcome.update(limit_mib=args.limit_mib,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               elapsed_seconds=round(time.monotonic()-start,3),input_bytes=args.input.stat().st_size)
print(json.dumps(outcome))
raise SystemExit(0 if outcome['outcome']=='passed' else 2)
