import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_netease_public as m
from qiuzhao.collector.p1_pipeline import validate_result


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class ScriptedSession:
    """Answers GET/POST calls from a list of canned payloads, one per call, keyed by call order.

    Records every call's (method, url, params, json_body) so tests can assert on the exact
    request shape sent (e.g. which page-number parameter name was actually used).
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def _next(self, method, url, params, json_body):
        self.calls.append({'method': method, 'url': url, 'params': params, 'json': json_body})
        if not self._responses:
            raise AssertionError(f'no more scripted responses for {method} {url}')
        return FakeResponse(self._responses.pop(0))

    def get(self, url, params=None, timeout=None):
        return self._next('GET', url, params, None)

    def post(self, url, params=None, json=None, timeout=None):
        return self._next('POST', url, params, json)


def campus_row(ident, desc='负责日常研发工作。', req='本科及以上学历。', **extra):
    row = {'id': ident, 'positionName': f'职位{ident}', 'positionTypeName': '技术',
           'workPlaceName': '杭州', 'positionDescription': desc, 'positionRequirement': req}
    row.update(extra)
    return row


def campus_list_payload(rows, total, pages, code=200):
    return {'code': code, 'data': {'total': total, 'pages': pages, 'list': rows}}


class CombineDescriptionTests(unittest.TestCase):
    def test_both_present_keeps_both_labeled(self):
        text, missing = m.combine_description('职责内容', '要求内容')
        self.assertIn('职责内容', text)
        self.assertIn('要求内容', text)
        self.assertEqual(missing, [])

    def test_one_missing_keeps_the_other_and_flags_it(self):
        text, missing = m.combine_description('职责内容', '')
        self.assertIn('职责内容', text)
        self.assertEqual(missing, ['requirement'])

    def test_both_missing_yields_empty_text_not_fabricated(self):
        text, missing = m.combine_description('', '')
        self.assertEqual(text, '')
        self.assertEqual(sorted(missing), ['requirement', 'responsibility'])

    def test_long_text_is_never_truncated(self):
        long_text = '责任描述。' * 2000  # far past the old 5000/3000-char truncation limits
        text, _ = m.combine_description(long_text, '')
        self.assertIn(long_text, text)


class MakeJobTests(unittest.TestCase):
    def test_required_contract_fields_present(self):
        job = m.make_job('netease-campus103-1', 'campus', '标题', '描述内容',
                          'https://campus.163.com/api/x', 'https://campus.163.com/app/detail/index?id=1',
                          ['杭州'])
        for field in ('job_title', 'source_record_id', 'recruitment_unit', 'description_raw',
                      'source_url', 'application_url', 'detail_url', 'cities', 'education_raw',
                      'major_requirements_raw', 'cohort_raw', 'reviewed_at', 'recruitment_type'):
            self.assertIn(field, job)
        self.assertEqual(job['recruitment_type'], '校园招聘')

    def test_missing_fields_tracked_not_silently_dropped(self):
        job = m.make_job('id', 'intern', 't', 'body', 'src', 'url', [], source_missing_fields=['requirement'])
        self.assertEqual(job['source_missing_fields'], ['requirement'])
        self.assertEqual(job['field_completeness'], 'partial')


class ClassificationTests(unittest.TestCase):
    def test_group_scope_from_title(self):
        self.assertEqual(m.group_scope('精英实习生'), 'intern')
        self.assertEqual(m.group_scope('日常实习生'), 'intern')
        self.assertEqual(m.group_scope('应届生'), 'campus')

    def test_greenhouse_scope_from_title(self):
        self.assertEqual(m.classify_greenhouse_scope('SG Campus Recruitment - Data Analyst'), 'campus')
        self.assertEqual(m.classify_greenhouse_scope('SG Campus Recruitment - General Intern Opportunities'), 'intern')
        self.assertEqual(m.classify_greenhouse_scope('Community Manager'), 'social')
        self.assertEqual(m.classify_greenhouse_scope('Marketing Intern'), 'intern')

    def test_parse_navigation_reads_scope_from_live_group_not_hardcoded_ids(self):
        navigation = [
            {'title': '应届生', 'children': [
                {'title': '网易互联网2027届校园招聘', 'link': 'https://campus.163.com/app/job/position?id=103'},
                {'title': '网易游戏雷火2027届校园招聘', 'link': 'https://leihuo.163.com/campus/#/full?channel=x'},
                {'title': '星火计划', 'link': 'https://campus.163.com/app/talents/stars'},
            ]},
            {'title': '精英实习生', 'children': [
                {'title': '蛋仔派对AI实习生专项', 'link': 'https://campus.game.163.com/app/job/position?id=75'},
            ]},
        ]
        projects, notes = m.parse_navigation(navigation)
        self.assertEqual(projects, {103: 'campus', 75: 'intern'})
        self.assertTrue(any('talents entry' in n for n in notes))


class CampusApiPaginationTests(unittest.TestCase):
    def test_uses_current_page_not_page_num_or_page_index(self):
        """Regression: the server accepts ``currentPage`` and silently ignores pageNum/pageIndex."""
        session = ScriptedSession([
            campus_list_payload([campus_row(1)], total=2, pages=2),
            campus_list_payload([campus_row(2)], total=2, pages=2),
            {'code': 200, 'data': {'id': 1, 'projectName': 'p', 'publishTime': '2026-01-01'}},
            {'code': 200, 'data': {'id': 2, 'projectName': 'p', 'publishTime': '2026-01-01'}},
        ])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_campus_api_project(session, 103, 'campus', result, Path(tmp))
        list_calls = [c for c in session.calls if 'getJobList' in c['url']]
        self.assertEqual([c['params']['currentPage'] for c in list_calls], [1, 2])
        for c in list_calls:
            self.assertNotIn('pageNum', c['params'])
            self.assertNotIn('pageIndex', c['params'])
        self.assertEqual(len(result.jobs), 2)
        self.assertTrue(result.exhausted['campus103'])

    def test_total_drift_keeps_rows_already_collected(self):
        """A live total changing mid-scan must not discard rows already paginated."""
        session = ScriptedSession([
            campus_list_payload([campus_row(1)], total=2, pages=2),
            campus_list_payload([campus_row(2)], total=3, pages=2),  # total drifted
            {'code': 200, 'data': {'id': 1, 'projectName': '', 'publishTime': ''}},
        ])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_campus_api_project(session, 103, 'campus', result, Path(tmp))
        self.assertEqual(len(result.jobs), 1)
        self.assertFalse(result.exhausted['campus103'])
        self.assertTrue(any('total changed' in e for e in result.errors))

    def test_both_fields_empty_goes_to_pending_review_not_fabricated(self):
        session = ScriptedSession([
            campus_list_payload([campus_row(1, desc='', req='')], total=1, pages=1),
            {'code': 200, 'data': {'id': 1, 'projectName': '', 'publishTime': ''}},
        ])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_campus_api_project(session, 103, 'campus', result, Path(tmp))
        self.assertEqual(result.jobs, [])
        self.assertEqual(result.pending_review, ['netease-campus103-1'])


class Hr163Tests(unittest.TestCase):
    def test_worktype_sent_as_string(self):
        """Regression: an integer workType makes the (correct) currentPage param look broken too."""
        session = ScriptedSession([
            {'code': 200, 'data': {'total': 1, 'pages': 1, 'list': [
                {'id': 9, 'name': '日常实习', 'workType': '1', 'description': '职责', 'requirement': '要求',
                 'reqEducationName': '不限', 'workPlaceNameList': ['上海市'], 'updateTime': 1700000000000}]}},
        ])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_hr163_worktype(session, '1', 'intern', result, Path(tmp))
        self.assertEqual(session.calls[0]['json']['workType'], '1')
        self.assertIsInstance(session.calls[0]['json']['workType'], str)
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0]['recruitment_type'], '实习招聘')

    def test_stops_at_official_last_page_despite_boundary_duplicate(self):
        """A sort-tie duplicate at a page boundary must not make the loop request a bogus extra
        page (observed live: the server answers an out-of-range page with total=0)."""
        session = ScriptedSession([
            {'code': 200, 'data': {'total': 3, 'pages': 2, 'list': [
                {'id': 1, 'name': 'a', 'workType': '0', 'description': 'd', 'requirement': 'r'},
                {'id': 2, 'name': 'b', 'workType': '0', 'description': 'd', 'requirement': 'r'}]}},
            {'code': 200, 'data': {'total': 3, 'pages': 2, 'list': [
                {'id': 2, 'name': 'b', 'workType': '0', 'description': 'd', 'requirement': 'r'},  # boundary repeat
                {'id': 3, 'name': 'c', 'workType': '0', 'description': 'd', 'requirement': 'r'}]}},
        ])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_hr163_worktype(session, '0', 'social', result, Path(tmp))
        self.assertEqual(len(session.calls), 2)  # never asked for a page 3
        self.assertEqual({j['source_record_id'] for j in result.jobs},
                         {'netease-hr163-1', 'netease-hr163-2', 'netease-hr163-3'})

    def test_confirmed_zero_is_exhausted_not_a_gap(self):
        session = ScriptedSession([{'code': 200, 'data': {'total': 0, 'pages': 0, 'list': []}}])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_hr163_worktype(session, '2', 'social', result, Path(tmp))
        self.assertEqual(result.jobs, [])
        self.assertTrue(result.exhausted['hr163-wt2'])
        self.assertEqual(result.errors, [])


class LeihuoScopeTests(unittest.TestCase):
    def test_scope_decided_per_row_not_per_project(self):
        """A leihuo project can mix ehr_job_type; scope must come from the row, not the id."""
        session = ScriptedSession([
            {'status': 200, 'data': {'count_number': 2, 'last_page': True, 'apply_job_list': [
                {'ehr_job_id': '1', 'job_name': 'a', 'job_description': 'd', 'job_requirement': 'r',
                 'ehr_job_type': '1', 'type_name': '全职', 'job_target': '2027届', 'work_place_name': '杭州'},
                {'ehr_job_id': '2', 'job_name': 'b', 'job_description': 'd', 'job_requirement': 'r',
                 'ehr_job_type': '2', 'type_name': '实习', 'job_target': '2026年及以后', 'work_place_name': '杭州'},
            ]}},
            {'status': 200, 'data': {'ehr_job_id': '1', 'job_detail_url': 'https://campus.163.com/app/detail/index?id=1&projectId=77'}},
        ])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_leihuo_project(session, 77, 'campus', result, Path(tmp))
        self.assertEqual([j['source_record_id'] for j in result.jobs], ['netease-leihuo77-1'])

    def test_unknown_ehr_job_type_is_flagged_not_silently_kept(self):
        session = ScriptedSession([
            {'status': 200, 'data': {'count_number': 1, 'last_page': True, 'apply_job_list': [
                {'ehr_job_id': '9', 'job_name': 'x', 'job_description': 'd', 'job_requirement': 'r',
                 'ehr_job_type': '9', 'type_name': '未知', 'work_place_name': ''},
            ]}},
        ])
        result = m.SystemResult()
        with tempfile.TemporaryDirectory() as tmp:
            m.fetch_leihuo_project(session, 77, 'campus', result, Path(tmp))
        self.assertEqual(result.jobs, [])
        self.assertTrue(any('unknown ehr_job_type' in e for e in result.errors))


class CollectContractTests(unittest.TestCase):
    def test_rejects_unknown_company(self):
        with self.assertRaises(ValueError):
            m.collect('拼多多', 'campus', Path('/tmp/unused'))

    def test_rejects_unknown_scope(self):
        with self.assertRaises(ValueError):
            m.collect('网易', 'all', Path('/tmp/unused'))

    def test_end_to_end_wiring_validates_against_pipeline_contract(self):
        """Patch every network boundary and confirm collect() output survives validate_result."""
        navigation_payload = {'code': 200, 'data': [
            {'title': '应届生', 'children': [
                {'title': '网易互联网2027届校园招聘', 'link': 'https://campus.163.com/app/job/position?id=103'}]},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m, 'make_session', return_value=ScriptedSession([])), \
                 patch.object(m, 'fetch_navigation', return_value=navigation_payload['data']), \
                 patch.object(m, 'fetch_campus_api_project') as fake_campus, \
                 patch.object(m, 'fetch_leihuo_project'), \
                 patch.object(m, 'fetch_greenhouse_board'):
                def fill(session, project_id, scope, result, output_dir):
                    job = m.make_job('netease-campus103-1', scope, '标题', '描述内容',
                                      'https://campus.163.com/api/x', 'https://campus.163.com/app/detail/index?id=1',
                                      ['杭州'])
                    result.jobs.append(job)
                    result.unique_seen += 1
                    result.exhausted['campus103'] = True
                    result.raw_totals['campus103'] = 1
                    result.evidence_files.append(m.save_json(output_dir, 'campus103-list-1.json', {'total': 1}))
                fake_campus.side_effect = fill
                payload = m.collect('网易', 'campus', Path(tmp))
            validated = validate_result(payload, '网易', 'campus', Path(tmp))
            self.assertEqual(len(validated['jobs']), 1)
            self.assertEqual(validated['coverage']['status'], 'success')
            self.assertTrue(validated['coverage']['complete'])


if __name__ == '__main__':
    unittest.main()
