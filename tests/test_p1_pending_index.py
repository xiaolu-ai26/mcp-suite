from __future__ import annotations

import copy
import unittest

from qiuzhao.collector import p1_pending_index as p


def pending_entry(source_record_id='1', **overrides):
    row = {
        'source_record_id': source_record_id,
        'job_title': '软件工程师',
        'detail_url': 'https://careers.example.com/jobs/1',
        'listing_evidence_path': 'listing.json',
        'created_at': '2026-09-13T00:00:00Z',
        'recruitment_unit': '深圳市示例科技有限公司',
        'pending_reason': 'source_empty_body',
        'detail_request_status': 'success',
        'source_missing_fields': ['responsibilities', 'requirements'],
    }
    row.update(overrides)
    return row


def job_entry(source_record_id='1', **overrides):
    row = {
        'source_record_id': source_record_id,
        'job_title': '软件工程师',
        'detail_url': 'https://careers.example.com/jobs/1',
        'description_raw': '原始说明',
        'recruitment_unit': '深圳市示例科技有限公司',
        'recruitment_type': '校园招聘',
        'checked_at': '2026-09-13T00:00:00Z',
    }
    row.update(overrides)
    return row


class P1PendingIndexTests(unittest.TestCase):
    def test_source_empty_vs_fetch_failed_are_valid(self):
        rows = p.normalize_pending_index([
            pending_entry('A', pending_reason='source_empty_body',
                          detail_request_status='success',
                          source_missing_fields=['responsibilities', 'requirements'],
                          listing_evidence_path='a.json'),
            pending_entry('B', pending_reason='fetch_failed', detail_request_status='failed', source_missing_fields=[],
                          detail_url='https://careers.example.com/jobs/2',
                          listing_evidence_path='b.json'),
        ], '大疆', 'campus', '校园招聘')

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['status'], 'unverified')
        self.assertEqual(rows[0]['description_raw'], '')
        self.assertTrue(rows[0]['index_only'])
        self.assertEqual(rows[1]['status'], 'unverified')

    def test_invalid_url_evidence_state_and_duplicate_are_rejected(self):
        company = '大疆'
        scope = 'campus'
        with self.assertRaisesRegex(ValueError, 'http'):
            p.normalize_pending_index([
                pending_entry('A', detail_url='notaurl', listing_evidence_path='a.json')
            ], company, scope, '校园招聘')
        with self.assertRaisesRegex(ValueError, 'listing_evidence_path'):
            p.normalize_pending_index([
                pending_entry('A', listing_evidence_path=None)
            ], company, scope, '校园招聘')
        with self.assertRaisesRegex(ValueError, 'source_empty_body'):
            p.normalize_pending_index([
                pending_entry('A', pending_reason='source_empty_body', detail_request_status='failed',
                              source_missing_fields=['responsibilities', 'requirements'])
            ], company, scope, '校园招聘')
        with self.assertRaisesRegex(ValueError, 'failed or blocked'):
            p.normalize_pending_index([
                pending_entry('A', pending_reason='fetch_failed', status='success')
            ], company, scope, '校园招聘')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            p.normalize_pending_index([
                pending_entry('A'),
                pending_entry('A', job_title='测试岗位'),
            ], company, scope, '校园招聘')

    def test_presence_keys_reads_jobs_and_pending(self):
        pending_rows = p.normalize_pending_index([
            pending_entry('pending-1', listing_evidence_path='a.json'),
        ], '大疆', 'campus', '校园招聘')
        result = {
            'jobs': [
                {'p1_identity': p.source_identity('大疆', 'campus', 'job-1')},
                {'id': 'ignore-me'},
            ],
            'pending_index': pending_rows,
        }
        self.assertEqual(
            p.presence_keys(result),
            {p.source_identity('大疆', 'campus', 'job-1'), pending_rows[0]['p1_identity']}
        )

    def test_partial_preserves_previous_and_updates_pending(self):
        previous = p.normalize_pending_index([
            pending_entry('A', job_title='旧岗位', listing_evidence_path='old.json',
                          extra={'nested': 1}),
        ], '大疆', 'campus', '校园招聘')
        payload = {
            'coverage': {'status': 'partial', 'complete': False},
            'jobs': [],
            'pending_index': [
                *p.normalize_pending_index([
                    pending_entry('A', job_title='更新岗位', listing_evidence_path='new.json',
                                  pending_reason='source_empty_body',
                                  detail_request_status='success',
                                  source_missing_fields=['responsibilities', 'requirements']),
                ], '大疆', 'campus', '校园招聘')
            ],
        }
        merged, stats = p.merge_pending_index(previous, [('大疆', 'campus', payload)])
        self.assertEqual(stats['removed'], 0)
        self.assertEqual(stats['updated'], 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['job_title'], '更新岗位')

    def test_complete_removes_only_same_scope_company_pending(self):
        current_scope = p.normalize_pending_index([
            pending_entry('A', listing_evidence_path='a.json',
                          pending_reason='source_empty_body', detail_request_status='success',
                          source_missing_fields=['responsibilities', 'requirements']),
        ], '大疆', 'campus', '校园招聘')
        other_scope = {
            'p1_company': '大疆', 'p1_scope': 'social', 'p1_identity': p.source_identity('大疆', 'social', 'B'),
            'id': p.source_identity('大疆', 'social', 'B'), 'pending_reason': 'source_empty_body',
            'job_title': '跨scope', 'detail_url': 'https://careers.example.com/jobs/social',
            'listing_evidence_path': 'b.json', 'detail_request_status': 'success',
            'source_missing_fields': ['responsibilities', 'requirements']
        }
        previous = current_scope + [other_scope]

        payload = {
            'coverage': {'status': 'success', 'complete': True},
            'jobs': [],
            'pending_index': [],
        }
        merged, stats = p.merge_pending_index(previous, [('大疆', 'campus', payload)])
        self.assertEqual(stats['removed'], 1)
        self.assertEqual(len([r for r in merged if r.get('p1_scope') == 'campus' and r.get('pending_reason')]), 0)
        self.assertEqual(len([r for r in merged if r.get('p1_scope') == 'social' and r.get('pending_reason')]), 1)

    def test_upgrade_real_job_replaces_pending_in_partial_and_counts_upgraded(self):
        previous = p.normalize_pending_index([
            pending_entry('A', listing_evidence_path='a.json',
                          pending_reason='source_empty_body', detail_request_status='success',
                          source_missing_fields=['responsibilities', 'requirements']),
        ], '大疆', 'campus', '校园招聘')
        payload = {
            'coverage': {'status': 'partial', 'complete': False},
            'jobs': [
                {
                    **job_entry(source_record_id='A', recruitment_type='校园招聘',
                               detail_url='https://careers.example.com/jobs/1'),
                    'p1_identity': p.source_identity('大疆', 'campus', 'A')
                }
            ],
            'pending_index': [],
        }
        merged, stats = p.merge_pending_index(previous, [('大疆', 'campus', payload)])
        self.assertEqual(stats['upgraded'], 1)
        self.assertEqual(merged, [])

    def test_cross_company_isolation_for_complete_cleanup(self):
        company_a = p.normalize_pending_index([
            pending_entry('A', listing_evidence_path='a.json',
                          pending_reason='source_empty_body',
                          detail_request_status='success',
                          source_missing_fields=['responsibilities', 'requirements']),
        ], '大疆', 'campus', '校园招聘')
        company_b = p.normalize_pending_index([
            pending_entry('A', listing_evidence_path='b.json',
                          pending_reason='source_empty_body',
                          detail_request_status='success',
                          source_missing_fields=['responsibilities', 'requirements']),
        ], '拼多多', 'campus', '校园招聘')

        payload = {
            'coverage': {'status': 'success', 'complete': True},
            'jobs': [],
            'pending_index': [],
        }
        merged, _ = p.merge_pending_index(company_a + company_b, [('大疆', 'campus', payload)])
        self.assertEqual(len([r for r in merged if r['p1_company'] == '大疆']), 0)
        self.assertEqual(len([r for r in merged if r['p1_company'] == '拼多多']), 1)

    def test_alias_stability_keeps_legacy_public_id(self):
        rows = p.normalize_pending_index([
            {
                **pending_entry('A', listing_evidence_path='a.json',
                               pending_reason='source_empty_body',
                               detail_request_status='success',
                               source_missing_fields=['responsibilities', 'requirements']),
                'id': 'legacy-id'
            }
        ], '大疆', 'campus', '校园招聘')
        identity = rows[0]['p1_identity']

        payload = {
            'coverage': {'status': 'partial', 'complete': False},
            'jobs': [],
            'pending_index': [
            *p.normalize_pending_index([
                pending_entry('A', listing_evidence_path='a2.json',
                              pending_reason='source_empty_body',
                              detail_request_status='success',
                              source_missing_fields=['responsibilities', 'requirements']),
            ], '大疆', 'campus', '校园招聘')
            ],
        }
        merged, _ = p.merge_pending_index(rows, [('大疆', 'campus', payload)], id_aliases={identity: 'legacy-id'})
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['id'], 'legacy-id')

    def test_merge_does_not_mutate_inputs(self):
        previous = [
            {
                'p1_company': '大疆',
                'p1_scope': 'campus',
                'p1_identity': 'p1-old',
                'id': 'p1-old',
                'job_title': '旧',
                'pending_reason': 'source_empty_body',
                'listing_evidence_path': 'a.json',
                'source_record_id': '1',
                'nested': {'x': 1},
            }
        ]
        previous_before = copy.deepcopy(previous)
        updates = [
            ('大疆', 'campus', {
                'coverage': {'status': 'partial', 'complete': False},
                'jobs': [
                    {
                        'p1_identity': 'p1-old',
                        'id': 'p1-old',
                        'p1_company': '大疆',
                        'p1_scope': 'campus',
                        'job_title': '新',
                        'source_record_id': '1',
                        'detail_url': 'https://careers.example.com/jobs/1',
                        'listing_evidence_path': 'a.json',
                        'nested': {'x': 99},
                    }
                ],
                'pending_index': [],
            })
        ]
        updates_before = copy.deepcopy(updates)

        merged, _ = p.merge_pending_index(previous, updates)
        merged[0]['nested']['x'] = 42

        self.assertEqual(previous, previous_before)
        self.assertEqual(updates, updates_before)


if __name__ == '__main__':
    unittest.main()

def test_failed_request_cannot_claim_official_empty_or_use_generic_status():
 import pytest
 for overrides in [
  {'pending_reason':'fetch_failed','status':'failed','detail_request_status':'success'},
  {'pending_reason':'fetch_failed','detail_request_status':'failed','source_missing_fields':['responsibilities']},
  {'pending_reason':'source_empty_body','detail_request_status':'blocked'},
  {'pending_reason':'source_empty_body','status':'failed'},
  {'pending_reason':''},
  {'pending_reason':None},
  {'source_missing_fields':{'responsibilities':True,'requirements':True}},
 ]:
  with pytest.raises(ValueError):p.normalize_pending_index([pending_entry(**overrides)],'A','campus','校园招聘')
 row=p.normalize_pending_index([pending_entry(pending_reason='fetch_failed',detail_request_status='blocked',source_missing_fields=[])],'A','campus','校园招聘')[0]
 assert row['detail_request_status']=='blocked' and row['status']=='unverified'
 assert row['source_missing_fields']==[] and row['unretrieved_fields']==['responsibilities','requirements']

def test_empty_source_detail_evidence_allowed_failed_requires_listing():
 import pytest
 row=pending_entry(listing_evidence_path=None,detail_evidence_path='detail.json')
 assert len(p.normalize_pending_index([row],'A','campus','校园招聘'))==1
 row.update(pending_reason='fetch_failed',detail_request_status='failed',source_missing_fields=[])
 with pytest.raises(ValueError):p.normalize_pending_index([row],'A','campus','校园招聘')

def test_real_jobs_never_enter_pending_and_empty_job_does_not_upgrade():
 old=p.normalize_pending_index([pending_entry('old')],'A','campus','校园招聘')
 result={'coverage':{'complete':False},'jobs':[{'p1_identity':p.source_identity('A','campus','new'),'description_raw':'actual role'},{'p1_identity':old[0]['p1_identity'],'description_raw':'  '}],'pending_index':[]}
 merged,stats=p.merge_pending_index(old,[('A','campus',result)])
 assert merged==old and stats=={'added':0,'updated':0,'removed':0,'upgraded':0}
 result['jobs'][1]['description_raw']='actual responsibility'
 result['pending_index']=old
 merged,stats=p.merge_pending_index(old,[('A','campus',result)])
 assert merged==[] and stats['upgraded']==1

def test_wrong_company_in_update_rejected_without_input_mutation():
 import pytest
 old=p.normalize_pending_index([pending_entry()],'A','campus','校园招聘');before=copy.deepcopy(old)
 wrong=copy.deepcopy(old[0]);wrong['p1_company']='B'
 with pytest.raises(ValueError):p.merge_pending_index(old,[('A','campus',{'jobs':[wrong]})])
 assert old==before
