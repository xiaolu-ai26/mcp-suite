"""Prove generic Moka adapter result superset of the dedicated adapter (id/title).

The dedicated control runs the *existing* p1_sources_21_30 code path but with the
detail seam stubbed to a no-network fixture, so the control only performs the
official list scan (<=20 requests/tenant). Its campus id/title set is then
compared with the generic adapter's full list observation.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from unittest.mock import patch

WORKTREE = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/platform-adapters')
sys.path.insert(0, str(WORKTREE))
OUT = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/platform-adapters-out')
VERIFY = OUT / 'verify'
COMPARE = OUT / 'compare'

from qiuzhao.collector import p1_sources_01_10 as shared
from qiuzhao.collector import p1_sources_21_30 as dedicated


class CountingSession:
    def __init__(self, inner, counter):
        self._inner = inner
        self._counter = counter

    def get(self, *args, **kwargs):
        self._counter['requests'] += 1
        return self._inner.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        self._counter['requests'] += 1
        return self._inner.post(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def stub_detail(company, scope, row, host, org, site, iv, output_dir):
    detail = {'id': row['id'], 'title': row.get('title'), 'jobDescription': '<p>control stub</p>',
              'hireMode': row.get('hireMode'), 'commitment': row.get('commitment'),
              'status': row.get('status'), 'openedAt': row.get('openedAt'),
              'updatedAt': row.get('updatedAt'), 'closedAt': row.get('closedAt'),
              'locations': row.get('locations') or []}
    return detail, 'control', False


TARGETS = [('三七互娱', '37_58016'), ('金山办公', 'wps_41436'), ('鹰角网络', 'hypergryph_26326')]


def main():
    results = []
    for company, slug in TARGETS:
        generic_path = VERIFY / 'moka' / slug / 'result.json'
        generic = json.loads(generic_path.read_text(encoding='utf-8'))
        coverage = generic['coverage']
        counter = {'requests': 0}
        real_make = shared.make_session
        with patch.object(shared, 'make_session', lambda: CountingSession(real_make(), counter)), \
             patch.object(shared, 'moka_detail_cached', side_effect=stub_detail):
            control = dedicated.collect(company, 'campus', COMPARE / slug / 'dedicated')
        dedicated_ids = sorted({job['source_record_id'] for job in control['jobs']})
        dedicated_titles = sorted({job['job_title'] for job in control['jobs']})
        observed_ids = coverage.get('list_observed_ids') or []
        observed_titles = coverage.get('list_observed_titles') or []
        generic_ids = sorted({job['source_record_id'] for job in generic['jobs']})
        record = {
            'company': company, 'slug': slug,
            'generic_status': coverage['status'], 'generic_complete': coverage['complete'],
            'generic_collected_jobs': len(generic['jobs']),
            'generic_request_budget': coverage.get('request_budget'),
            'dedicated_control_jobs': len(control['jobs']),
            'dedicated_control_requests': counter['requests'],
            'dedicated_ids': dedicated_ids,
            'dedicated_titles': dedicated_titles,
            'generic_list_observed_ids': observed_ids,
            'generic_list_observed_titles': observed_titles,
            'generic_capped_job_ids': generic_ids,
            'superset_ids': set(dedicated_ids) <= set(observed_ids),
            'superset_titles': set(dedicated_titles) <= set(observed_titles),
            'missing_ids': sorted(set(dedicated_ids) - set(observed_ids)),
            'capped_jobs_subset_of_dedicated': set(generic_ids) <= set(dedicated_ids),
        }
        results.append(record)
        print(json.dumps({k: v for k, v in record.items()
                          if k not in ('dedicated_ids', 'dedicated_titles',
                                       'generic_list_observed_ids', 'generic_list_observed_titles',
                                       'generic_capped_job_ids')}, ensure_ascii=False), flush=True)
        time.sleep(2.2)
    (OUT / 'compare-summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('COMPARE_WRITTEN', OUT / 'compare-summary.json')


if __name__ == '__main__':
    main()
