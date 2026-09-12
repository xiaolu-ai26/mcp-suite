"""Anonymous public collector for 得物 (Dewu) campus/intern/social recruitment.

Thin wrapper around the shared anonymous Feishu careers SDK helper
(p1_feishu_public.collect_feishu). No login, no saved cookies/signatures.

Verified 2026-09-13 from the live https://campus.dewu.com homepage (real
DOM hrefs, not guessed):
  "校招职位" -> https://campus.dewu.com/578078/position/list
  "社会招聘" -> https://campus.dewu.com/index/
Both resolve (via #js-websiteInfo) to tenant "上海得物信息集团有限公司" but are
two distinct Feishu websites (ids 6956554465088866591 / 6938685787626326285)
with zero job-ID overlap across full pagination:
  578078 (campus site): recruit_type 201 正式=campus, 202 实习=intern
  index   (social site): recruit_type 101 全职/102 外包=social, 301 实习=intern
poizon.jobs.feishu.cn resolves to the identical "index" website (same id,
same tenant) so it is not a separate source and is not used here.
"""
from __future__ import annotations
import time
from pathlib import Path

from qiuzhao.collector.p1_feishu_public import collect_feishu

COMPANY = '得物'
TENANT_NAMES = ['上海得物信息集团有限公司']

CAMPUS_SITE = {'url': 'https://campus.dewu.com/578078/position/list', 'tenant_names': TENANT_NAMES, 'portal_type': 6}
SOCIAL_SITE = {'url': 'https://campus.dewu.com/index/', 'tenant_names': TENANT_NAMES, 'portal_type': 6}

# Intern roles are split across both sites with disjoint IDs (202 on the
# campus site, 301 on the social site); campus/social each live on one site
# only (confirmed by full-pagination recruit_type breakdowns on both sites).
SITES_BY_SCOPE = {
    'campus': [CAMPUS_SITE],
    'intern': [CAMPUS_SITE, SOCIAL_SITE],
    'social': [SOCIAL_SITE],
}

# The shared anonymous browser lock is process-wide, not per-company: other
# companies' daily Feishu collections can legitimately hold it. collect_feishu
# already waits up to 120s per call before raising TimeoutError('...busy');
# retry a bounded few times instead of treating one busy window as failure.
LOCK_BUSY_RETRIES = 3
LOCK_BUSY_BACKOFF_SECONDS = 30


def collect(company: str, scope: str, output_dir: Path) -> dict:
    if company != COMPANY:
        raise ValueError('unsupported company')
    if scope not in SITES_BY_SCOPE:
        raise ValueError('unknown scope')
    sites = SITES_BY_SCOPE[scope]
    out = Path(output_dir).resolve()
    for attempt in range(LOCK_BUSY_RETRIES):
        try:
            return collect_feishu(company, scope, sites, out)
        except TimeoutError:
            if attempt == LOCK_BUSY_RETRIES - 1:
                raise
            time.sleep(LOCK_BUSY_BACKOFF_SECONDS)


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', choices=sorted(SITES_BY_SCOPE))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    for scope in ([args.scope] if args.scope else sorted(SITES_BY_SCOPE)):
        result = collect(COMPANY, scope, args.output_dir / scope)
        summary = {k: v for k, v in result['coverage'].items() if k not in {'evidence', 'evidence_files'}}
        print(json.dumps({'company': COMPANY, 'scope': scope, **summary}, ensure_ascii=False), flush=True)
