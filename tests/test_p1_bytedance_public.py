from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from qiuzhao.collector import p1_bytedance_public as B
from qiuzhao.collector import p1_pipeline as P


def mk_job(job_id, title=None, description='岗位职责：负责某方向研发工作。',
           requirement='任职要求：本科及以上学历，计算机相关专业。', recruit_id='201',
           recruit_name='正式', parent_id='2', parent_name='校招', publish_time=1788849785694):
    return {
        'id': job_id,
        'title': title or ('测试岗位-' + str(job_id)),
        'code': 'A' + str(job_id),
        'description': description,
        'requirement': requirement,
        'job_category': {'id': 'cat1', 'name': '研发'},
        'recruit_type': {'id': recruit_id, 'name': recruit_name,
                         'parent': {'id': parent_id, 'name': parent_name}},
        'city_info': {'name': '北京'},
        'city_list': [{'code': 'CT_11', 'name': '北京'}, {'code': 'CT_125', 'name': '上海'}],
        'publish_time': publish_time,
        'job_post_info': {'address_list': [{'name': '北京市海淀区'}]},
    }


class FakeTransport:
    """Serves pre-built pages by offset and records every request."""

    def __init__(self, pages, count=None):
        self.pages = pages
        self.count = count
        self.calls = []

    def __call__(self, profile, offset, interval, last_call):
        self.calls.append({'offset': offset, 'interval': interval, 'profile': dict(profile)})
        rows = self.pages.get(offset)
        if rows is None:
            rows = []
        total = self.count.get(offset, self.count.get('default')) if isinstance(self.count, dict) else self.count
        if total is None:
            total = sum(len(page) for page in self.pages.values())
        return {'code': 0, 'data': {'count': total, 'job_post_list': rows}}, 0.0


def run(scope, pages, count=None, out=None):
    transport = FakeTransport(pages, count)
    result = B.collect(B.COMPANY, scope, out, transport=transport, min_interval=1.0)
    return result, transport


class ByteDanceAdapterTests(unittest.TestCase):
    def test_registry_registers_bytedance_with_three_scopes(self):
        self.assertEqual(B.merged_registry(), {B.COMPANY: B.MODULE_PATH})
        self.assertEqual(P.REGISTRY[B.COMPANY], B.MODULE_PATH)
        self.assertIn(B.COMPANY, P.DEFAULT_COMPANIES)
        self.assertEqual(P.DEFAULT_COMPANIES.count(B.COMPANY), 1)
        self.assertEqual(P.company_scopes(B.COMPANY), ['campus', 'intern', 'social'])

    def test_campus_profile_uses_campus_portal_and_recruitment_id_201(self):
        self.assertEqual(B.PROFILES['campus']['recruitment_id'], '201')
        self.assertEqual(B.PROFILES['campus']['portal_type'], 3)
        self.assertEqual(B.PROFILES['campus']['listing'], 'https://jobs.bytedance.com/campus/position')

    def test_intern_profile_uses_campus_portal_and_recruitment_id_202(self):
        self.assertEqual(B.PROFILES['intern']['recruitment_id'], '202')
        self.assertEqual(B.PROFILES['intern']['listing'], 'https://jobs.bytedance.com/campus/position')

    def test_social_profile_uses_experienced_portal_and_recruitment_id_101(self):
        self.assertEqual(B.PROFILES['social']['recruitment_id'], '101')
        self.assertEqual(B.PROFILES['social']['portal_type'], 2)
        self.assertEqual(B.PROFILES['social']['listing'], 'https://jobs.bytedance.com/experienced/position')

    def test_unknown_company_and_scope_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                B.collect('腾讯', 'campus', Path(tmp))
            with self.assertRaises(ValueError):
                B.collect(B.COMPANY, 'experienced', Path(tmp))

    def test_request_interval_is_never_below_one_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, transport = run('campus', {0: [mk_job('1')]}, out=Path(tmp))
        self.assertTrue(transport.calls)
        self.assertTrue(all(call['interval'] >= 1.0 for call in transport.calls))

    def test_complete_scope_keeps_bytedance_ids_and_validates(self):
        pages = {0: [mk_job('1'), mk_job('2')], 100: []}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result, transport = run('campus', pages, count={'0': 3, '100': 3}, out=out)
            self.assertTrue(result['coverage']['complete'], result['coverage']['errors'])
            self.assertEqual(result['coverage']['status'], 'success')
            self.assertEqual([job['id'] for job in result['jobs']], ['bytedance-1', 'bytedance-2'])
            self.assertEqual(result['coverage']['stable_id_prefix'], 'bytedance-')
            # Every job must carry the campus scope, the official detail URL and prose.
            for job in result['jobs']:
                self.assertEqual(job['recruitment_type'], '校园招聘')
                self.assertEqual(job['detail_url'],
                                 'https://jobs.bytedance.com/campus/position/%s/detail' % job['source_record_id'])
                self.assertTrue(job['description_raw'].strip())
            validated = P.validate_result(result, B.COMPANY, 'campus', out)
            self.assertEqual([row['id'] for row in validated['jobs']], ['bytedance-1', 'bytedance-2'])
            self.assertEqual({row['p1_identity'] for row in validated['jobs']}, {'bytedance-1', 'bytedance-2'})
            self.assertEqual({row['canonical_company'] for row in validated['jobs']}, {B.COMPANY})
            self.assertEqual(validated['coverage']['available_job_count'], 2)

    def test_other_adapters_without_prefix_still_get_hash_identity(self):
        row = mk_job('7')
        row.update(recruitment_type='校园招聘', source_record_id='7',
                   detail_url='https://example.com/7', source_url='https://example.com/7',
                   description_raw='职责', recruitment_unit='某公司',
                   job_title=row.pop('title'))
        payload = {'jobs': [row],
                   'coverage': {'status': 'partial', 'complete': False, 'collected_jobs': 1,
                                'scope_evidence': 'official api', 'errors': [], 'checked_at': 'now'}}
        validated = P.validate_result(payload, '某公司', 'campus')
        self.assertTrue(validated['jobs'][0]['id'].startswith('p1-'))

    def test_api_cap_scope_is_partial_and_never_complete(self):
        pages = {offset: [mk_job(str(offset + index)) for index in range(3)] for offset in range(0, 300, 100)}
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = run('social', pages, count=10000, out=Path(tmp))
        coverage = result['coverage']
        self.assertFalse(coverage['complete'])
        self.assertEqual(coverage['status'], 'partial')
        self.assertTrue(coverage['api_cap_limited'])
        self.assertIn('上限', coverage['status_note'])

    def test_count_drift_aborts_the_scope_with_an_error(self):
        pages = {0: [mk_job('1')], 100: [mk_job('2')]}
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = run('campus', pages, count={0: 2, 100: 5}, out=Path(tmp))
        coverage = result['coverage']
        self.assertFalse(coverage['complete'])
        self.assertTrue(any('count drift' in error for error in coverage['errors']))
        self.assertEqual([job['id'] for job in result['jobs']], ['bytedance-1'])

    def test_duplicate_source_id_is_reported_and_deduplicated(self):
        pages = {0: [mk_job('1'), mk_job('1', title='重复')]}
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = run('campus', pages, count=2, out=Path(tmp))
        coverage = result['coverage']
        self.assertEqual(len(result['jobs']), 1)
        self.assertEqual(coverage['duplicate_source_ids'], 1)
        self.assertFalse(coverage['complete'])
        self.assertTrue(any('duplicate source_record_id' in error for error in coverage['errors']))

    def test_row_without_description_is_excluded_and_blocks_complete(self):
        pages = {0: [mk_job('1'), mk_job('2', description='', requirement='')]}
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = run('campus', pages, count=2, out=Path(tmp))
        coverage = result['coverage']
        self.assertEqual([job['id'] for job in result['jobs']], ['bytedance-1'])
        self.assertEqual(coverage['skipped_empty_body'], 1)
        self.assertFalse(coverage['complete'])

    def test_network_failure_stops_the_scope_without_publishing_rows(self):
        def failing(profile, offset, interval, last_call):
            raise OSError('connection reset')
        with tempfile.TemporaryDirectory() as tmp:
            result = B.collect(B.COMPANY, 'campus', Path(tmp), transport=failing, min_interval=1.0)
        self.assertFalse(result['jobs'])
        self.assertEqual(result['coverage']['status'], 'blocked')
        self.assertTrue(result['coverage']['errors'])

    def test_evidence_files_and_scope_request_are_written_for_the_contract(self):
        pages = {0: [mk_job('1')]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result, _ = run('intern', pages, count=1, out=out)
            coverage = result['coverage']
            self.assertTrue(coverage['evidence_files'])
            for name in coverage['evidence_files']:
                path = out / name
                self.assertTrue(path.is_file() and path.stat().st_size)
                payload = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(payload['request_body']['recruitment_id_list'], ['202'])
                self.assertLessEqual(payload['returned'], 100)
            self.assertEqual(coverage['scope_request']['company'], B.COMPANY)
            self.assertEqual(coverage['scope_request']['scope'], 'intern')


class ByteDanceMergeTests(unittest.TestCase):
    """The 4171 live 'bytedance-*' rows must be updated, never duplicated."""

    def legacy_row(self, job_id):
        url = 'https://jobs.bytedance.com/campus/position/%s/detail' % job_id
        return {
            'id': 'bytedance-' + job_id,
            'source_record_id': job_id,
            'job_title': '旧标题-' + job_id,
            'recruitment_unit': '字节跳动',
            'recruitment_type': '校园招聘',
            'source_url': url,
            'application_url': url,
            'reviewed_at': '2026-09-10T12:00:00+08:00',
            'status': 'open',
        }

    def test_merge_updates_legacy_rows_in_place(self):
        previous = [self.legacy_row('1'), self.legacy_row('2')]
        pages = {0: [mk_job('1'), mk_job('2')], 100: []}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result, _ = run('campus', pages, count={'0': 2, '100': 2}, out=out)
            validated = P.validate_result(result, B.COMPANY, 'campus', out)
            merged, changes = P.merge_records(previous, [(B.COMPANY, 'campus', validated)])
        self.assertEqual(len(merged), 2, 'legacy rows must not be duplicated')
        self.assertEqual(changes['added'], 0)
        self.assertEqual({row['id'] for row in merged}, {'bytedance-1', 'bytedance-2'})
        for row in merged:
            self.assertEqual(row['p1_company'], B.COMPANY)
            self.assertEqual(row['p1_scope'], 'campus')
            self.assertNotEqual(row['reviewed_at'], '2026-09-10T12:00:00+08:00')

    def test_merge_adds_genuinely_new_jobs_only(self):
        previous = [self.legacy_row('1')]
        pages = {0: [mk_job('1'), mk_job('9')], 100: []}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result, _ = run('campus', pages, count={'0': 2, '100': 2}, out=out)
            validated = P.validate_result(result, B.COMPANY, 'campus', out)
            merged, changes = P.merge_records(previous, [(B.COMPANY, 'campus', validated)])
        self.assertEqual(len(merged), 2)
        self.assertEqual(changes['added'], 1)
        self.assertIn('bytedance-9', {row['id'] for row in merged})

    def test_legacy_rows_absent_from_the_first_complete_snapshot_are_left_alone(self):
        """No destructive first pass: un-adopted legacy rows keep their old status.

        The absence rule only ever applies to rows already owned by the P1 chain
        (``p1_company``/``p1_scope`` set).  A legacy ``bytedance-*`` row that the
        first complete snapshot does not list is therefore retained unchanged
        instead of being deleted on the strength of one snapshot.
        """
        previous = [self.legacy_row('1'), self.legacy_row('2')]
        pages = {0: [mk_job('1')], 100: []}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result, _ = run('campus', pages, count={'0': 1, '100': 1}, out=out)
            validated = P.validate_result(result, B.COMPANY, 'campus', out)
            merged, changes = P.merge_records(previous, [(B.COMPANY, 'campus', validated)])
        by_id = {row['id']: row for row in merged}
        self.assertEqual(set(by_id), {'bytedance-1', 'bytedance-2'})
        self.assertEqual(changes['removed'], 0)
        self.assertEqual(by_id['bytedance-2']['status'], 'open')
        self.assertEqual(by_id['bytedance-1']['p1_company'], B.COMPANY)

    def test_adopted_row_is_removed_once_a_later_complete_snapshot_drops_it(self):
        """Day 2 onwards the normal absence rule applies to adopted ByteDance rows."""
        previous = [self.legacy_row('1'), self.legacy_row('2')]
        pages = {0: [mk_job('1'), mk_job('2')], 100: []}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first, _ = run('campus', pages, count={'0': 2, '100': 2}, out=out)
            adopted, _ = P.merge_records(previous, [(B.COMPANY, 'campus',
                                                     P.validate_result(first, B.COMPANY, 'campus', out))])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            second, _ = run('campus', {0: [mk_job('1')], 100: []}, count={'0': 1, '100': 1}, out=out)
            merged, changes = P.merge_records(adopted, [(B.COMPANY, 'campus',
                                                         P.validate_result(second, B.COMPANY, 'campus', out))])
        removed = {row['id']: row for row in merged if row.get('status') == 'removed'}
        self.assertEqual(set(removed), {'bytedance-2'})
        self.assertEqual(removed['bytedance-2']['removal_reason'],
                         'Absent from complete current company/scope official listing')


if __name__ == '__main__':
    unittest.main()
