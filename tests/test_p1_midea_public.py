from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from qiuzhao.collector import p1_midea_public as M
from qiuzhao.collector import p1_pipeline as P


def project(rule_id, name, category, status=1):
    return {'projectRuleId': rule_id, 'projectRuleName': name,
            'employementCategory': category, 'status': status}


def position(position_id, title=None, duty='负责某方向研发工作。', req='本科及以上学历，机械相关专业。',
             category='研发技术类'):
    return {
        'positionId': position_id,
        'projectPositionName': title or ('岗位-' + position_id),
        'recruitCategoryName': category,
        'employementCategory': 1,
        'projectRuleId': 'r1',
        'workplaceDtoList': [{'workPlaceName': '佛山市'}, {'workPlaceName': '苏州市'}],
        'projectPositionDto': {'positionName': title or ('岗位-' + position_id),
                               'positionCode': 'P' + position_id,
                               'jobResponsibility': duty, 'jobRequirement': req},
    }


class FakeTransport:
    """Serves the project list plus paged position lists, and records requests."""

    def __init__(self, projects, pages, totals):
        self.projects = projects
        self.pages = pages          # (rule_id, page) -> rows
        self.totals = totals        # rule_id -> total
        self.calls = []

    def __call__(self, url, payload, interval, last_call):
        self.calls.append({'url': url, 'payload': payload, 'interval': interval})
        if url == M.PROJECT_URL:
            return {'code': '0', 'data': self.projects}, 0.0
        rule_id = payload['projectRuleId']
        rows = self.pages.get((rule_id, payload['pageIndex']), [])
        info = {'pageIndex': payload['pageIndex'],
                'totalPage': self.totals[rule_id]['pages'],
                'pageSize': 20}
        return {'code': '0', 'data': {'data': rows, 'total': self.totals[rule_id]['total'], 'info': info}}, 0.0


def campus_fixture():
    projects = [project('r1', '2027届美的星校园招聘', 1), project('r2', '2027应届博士校园招聘', 1),
                project('r3', '日常实习生招聘通道', 4), project('r4', '已关闭项目', 1, status=0)]
    pages = {('r1', 1): [position('a1'), position('a2')],
             ('r2', 1): [position('b1')]}
    totals = {'r1': {'total': 2, 'pages': 1}, 'r2': {'total': 1, 'pages': 1}}
    return projects, pages, totals


class MideaAdapterTests(unittest.TestCase):
    def test_registry_registers_midea(self):
        self.assertEqual(M.merged_registry(), {M.COMPANY: M.MODULE_PATH})
        self.assertEqual(P.REGISTRY[M.COMPANY], M.MODULE_PATH)
        self.assertIn(M.COMPANY, P.DEFAULT_COMPANIES)
        self.assertEqual(P.DEFAULT_COMPANIES.count(M.COMPANY), 1)

    def test_unknown_company_and_scope_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                M.collect('格力', 'campus', Path(tmp))
            with self.assertRaises(ValueError):
                M.collect(M.COMPANY, 'experienced', Path(tmp))

    def test_social_scope_is_blocked_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'social', Path(tmp))
        self.assertEqual(result['jobs'], [])
        self.assertEqual(result['coverage']['status'], 'blocked')
        self.assertFalse(result['coverage']['complete'])

    def test_campus_unions_every_matching_active_project(self):
        projects, pages, totals = campus_fixture()
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = M.collect(M.COMPANY, 'campus', out, transport=transport, min_interval=1.0)
            coverage = result['coverage']
            self.assertTrue(coverage['complete'], coverage['errors'])
            self.assertEqual(coverage['status'], 'success')
            self.assertEqual(sorted(job['id'] for job in result['jobs']),
                             ['midea-a1', 'midea-a2', 'midea-b1'])
            self.assertEqual(sorted(coverage['project_totals']), ['r1', 'r2'])
            self.assertEqual(coverage['stable_id_prefix'], 'midea-')
            self.assertEqual(coverage['unmapped_active_projects'], [])
            # only active category-1 projects are requested; r3 (intern) and r4 (closed) are not
            requested = {call['payload']['projectRuleId'] for call in transport.calls if call['payload']}
            self.assertEqual(requested, {'r1', 'r2'})
            self.assertTrue(all(call['interval'] >= 1.0 for call in transport.calls))
            validated = P.validate_result(result, M.COMPANY, 'campus', out)
            self.assertEqual({row['id'] for row in validated['jobs']},
                             {'midea-a1', 'midea-a2', 'midea-b1'})
            self.assertEqual({row['recruitment_type'] for row in validated['jobs']}, {'校园招聘'})

    def test_intern_scope_uses_the_intern_category(self):
        projects, pages, totals = campus_fixture()
        transport = FakeTransport(projects, pages, {'r3': {'total': 0, 'pages': 1}})
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'intern', Path(tmp), transport=transport, min_interval=1.0)
        requested = {call['payload']['projectRuleId'] for call in transport.calls if call['payload']}
        self.assertEqual(requested, {'r3'})
        self.assertEqual(result['coverage']['status'], 'blocked')

    def test_detail_url_and_title_come_from_the_official_payload(self):
        projects, pages, totals = campus_fixture()
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'campus', Path(tmp), transport=transport, min_interval=1.0)
        job = result['jobs'][0]
        self.assertEqual(job['detail_url'],
                         'https://careers.midea.com/campus/position/' + job['source_record_id'])
        self.assertEqual(job['application_url'], job['detail_url'])
        self.assertEqual(job['cities'], ['佛山市', '苏州市'])
        self.assertIn('【任职要求】', job['description_raw'])

    def test_project_total_mismatch_keeps_the_scope_partial(self):
        projects, pages, totals = campus_fixture()
        totals['r2'] = {'total': 4, 'pages': 1}
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'campus', Path(tmp), transport=transport, min_interval=1.0)
        coverage = result['coverage']
        self.assertFalse(coverage['complete'])
        self.assertEqual(coverage['status'], 'partial')
        self.assertEqual(len(result['jobs']), 3)

    def test_unmapped_active_project_downgrades_to_partial(self):
        projects, pages, totals = campus_fixture()
        projects.append(project('r9', '新类型项目', 7))
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'campus', Path(tmp), transport=transport, min_interval=1.0)
        coverage = result['coverage']
        self.assertFalse(coverage['complete'])
        self.assertTrue(any('outside the mapped recruitment categories' in e for e in coverage['errors']))
        self.assertEqual([p['projectRuleId'] for p in coverage['unmapped_active_projects']], ['r9'])

    def test_cross_project_duplicate_is_counted_once(self):
        projects, pages, totals = campus_fixture()
        pages[('r2', 1)] = [position('a1'), position('b1')]
        totals['r2'] = {'total': 2, 'pages': 1}
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'campus', Path(tmp), transport=transport, min_interval=1.0)
        coverage = result['coverage']
        self.assertEqual(coverage['cross_project_duplicates'], 1)
        self.assertEqual(coverage['expected_total'], 3)
        self.assertEqual(sorted(job['id'] for job in result['jobs']), ['midea-a1', 'midea-a2', 'midea-b1'])
        self.assertTrue(coverage['complete'], coverage['errors'])

    def test_row_without_prose_blocks_complete(self):
        projects, pages, totals = campus_fixture()
        pages[('r2', 1)] = [position('b1', duty='', req='')]
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'campus', Path(tmp), transport=transport, min_interval=1.0)
        coverage = result['coverage']
        self.assertFalse(coverage['complete'])
        self.assertEqual([job['id'] for job in result['jobs']], ['midea-a1', 'midea-a2'])

    def test_network_failure_is_blocked(self):
        def failing(url, payload, interval, last_call):
            raise OSError('connection reset')
        with tempfile.TemporaryDirectory() as tmp:
            result = M.collect(M.COMPANY, 'campus', Path(tmp), transport=failing, min_interval=1.0)
        self.assertEqual(result['jobs'], [])
        self.assertEqual(result['coverage']['status'], 'blocked')

    def test_evidence_and_scope_request_satisfy_the_contract(self):
        projects, pages, totals = campus_fixture()
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = M.collect(M.COMPANY, 'intern', out, transport=transport, min_interval=1.0)
            coverage = result['coverage']
            self.assertTrue((out / 'projects.json').is_file())
        self.assertEqual(coverage['scope_request']['company'], M.COMPANY)
        self.assertEqual(coverage['scope_request']['scope'], 'intern')


class MideaMergeTests(unittest.TestCase):
    def legacy_row(self, position_id):
        url = 'https://careers.midea.com/campus/position/' + position_id
        return {'id': 'midea-' + position_id, 'source_record_id': position_id,
                'job_title': '旧标题', 'recruitment_unit': '美的集团股份有限公司',
                'recruitment_type': '校园招聘', 'source_url': url, 'application_url': url,
                'reviewed_at': '2026-09-10T12:00:00+08:00', 'status': 'qualified'}

    def test_merge_updates_legacy_rows_in_place(self):
        previous = [self.legacy_row('a1')]
        projects, pages, totals = campus_fixture()
        transport = FakeTransport(projects, pages, totals)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = M.collect(M.COMPANY, 'campus', out, transport=transport, min_interval=1.0)
            validated = P.validate_result(result, M.COMPANY, 'campus', out)
            merged, changes = P.merge_records(previous, [(M.COMPANY, 'campus', validated)])
        by_id = {row['id']: row for row in merged}
        self.assertIn('midea-a1', by_id)
        self.assertEqual(changes['added'], 2)
        self.assertEqual(by_id['midea-a1']['p1_company'], M.COMPANY)
        self.assertNotEqual(by_id['midea-a1']['reviewed_at'], '2026-09-10T12:00:00+08:00')


if __name__ == '__main__':
    unittest.main()
