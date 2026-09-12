import unittest
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector.p1_dewu_public import collect, SITES_BY_SCOPE, CAMPUS_SITE, SOCIAL_SITE, COMPANY, LOCK_BUSY_RETRIES


class SiteMapTests(unittest.TestCase):
    def test_campus_scope_uses_only_the_578078_site(self):
        self.assertEqual(SITES_BY_SCOPE['campus'], [CAMPUS_SITE])

    def test_social_scope_uses_only_the_index_site(self):
        self.assertEqual(SITES_BY_SCOPE['social'], [SOCIAL_SITE])

    def test_intern_scope_scans_both_sites_since_intern_ids_are_split(self):
        self.assertEqual(SITES_BY_SCOPE['intern'], [CAMPUS_SITE, SOCIAL_SITE])

    def test_each_site_has_verified_tenant_and_portal_type(self):
        for site in (CAMPUS_SITE, SOCIAL_SITE):
            self.assertEqual(site['tenant_names'], ['上海得物信息集团有限公司'])
            self.assertEqual(site['portal_type'], 6)

    def test_two_sites_are_distinct_urls(self):
        self.assertNotEqual(CAMPUS_SITE['url'], SOCIAL_SITE['url'])


class CollectDispatchTests(unittest.TestCase):
    def test_unsupported_company_rejected_before_any_network_call(self):
        with patch('qiuzhao.collector.p1_dewu_public.collect_feishu') as mocked:
            with self.assertRaises(ValueError):
                collect('拼多多', 'campus', Path('/tmp/unused'))
            mocked.assert_not_called()

    def test_unknown_scope_rejected_before_any_network_call(self):
        with patch('qiuzhao.collector.p1_dewu_public.collect_feishu') as mocked:
            with self.assertRaises(ValueError):
                collect(COMPANY, 'all', Path('/tmp/unused'))
            mocked.assert_not_called()

    def test_campus_scope_forwards_company_scope_sites_and_output_dir(self):
        with patch('qiuzhao.collector.p1_dewu_public.collect_feishu') as mocked:
            mocked.return_value = {'jobs': [], 'coverage': {'status': 'blocked'}}
            out = Path('/tmp/dewu-test-campus')
            result = collect(COMPANY, 'campus', out)
            mocked.assert_called_once_with(COMPANY, 'campus', [CAMPUS_SITE], out.resolve())
            self.assertEqual(result, {'jobs': [], 'coverage': {'status': 'blocked'}})

    def test_intern_scope_forwards_both_sites(self):
        with patch('qiuzhao.collector.p1_dewu_public.collect_feishu') as mocked:
            mocked.return_value = {'jobs': [], 'coverage': {'status': 'blocked'}}
            out = Path('/tmp/dewu-test-intern')
            collect(COMPANY, 'intern', out)
            mocked.assert_called_once_with(COMPANY, 'intern', [CAMPUS_SITE, SOCIAL_SITE], out.resolve())

    def test_result_is_returned_unmodified(self):
        sentinel = {'jobs': [{'id': 'x'}], 'coverage': {'status': 'success'}}
        with patch('qiuzhao.collector.p1_dewu_public.collect_feishu', return_value=sentinel) as mocked:
            result = collect(COMPANY, 'social', Path('/tmp/dewu-test-social'))
            self.assertIs(result, sentinel)
            mocked.assert_called_once_with(COMPANY, 'social', [SOCIAL_SITE], Path('/tmp/dewu-test-social').resolve())


class LockBusyRetryTests(unittest.TestCase):
    def test_retries_on_busy_lock_then_succeeds(self):
        sentinel = {'jobs': [], 'coverage': {'status': 'blocked'}}
        with patch('qiuzhao.collector.p1_dewu_public.time.sleep') as slept, \
             patch('qiuzhao.collector.p1_dewu_public.collect_feishu',
                    side_effect=[TimeoutError('single public careers browser is busy'), sentinel]) as mocked:
            result = collect(COMPANY, 'campus', Path('/tmp/dewu-test-retry'))
            self.assertEqual(result, sentinel)
            self.assertEqual(mocked.call_count, 2)
            slept.assert_called_once_with(30)

    def test_gives_up_after_bounded_retries(self):
        with patch('qiuzhao.collector.p1_dewu_public.time.sleep'), \
             patch('qiuzhao.collector.p1_dewu_public.collect_feishu',
                    side_effect=TimeoutError('single public careers browser is busy')) as mocked:
            with self.assertRaises(TimeoutError):
                collect(COMPANY, 'campus', Path('/tmp/dewu-test-retry-exhaust'))
            self.assertEqual(mocked.call_count, LOCK_BUSY_RETRIES)

    def test_non_lock_errors_are_not_retried(self):
        with patch('qiuzhao.collector.p1_dewu_public.time.sleep') as slept, \
             patch('qiuzhao.collector.p1_dewu_public.collect_feishu', side_effect=ValueError('bad envelope')) as mocked:
            with self.assertRaises(ValueError):
                collect(COMPANY, 'campus', Path('/tmp/dewu-test-no-retry'))
            self.assertEqual(mocked.call_count, 1)
            slept.assert_not_called()


if __name__ == '__main__':
    unittest.main()
