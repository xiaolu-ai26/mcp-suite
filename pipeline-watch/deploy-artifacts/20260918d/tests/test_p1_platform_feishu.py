"""Fixture tests for the config-driven Feishu platform adapter.

No network: ``collect_feishu`` is stubbed and the only real browser is replaced by
a fake, so the suite never leaves the machine.
"""
import importlib
import json
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_feishu_public as feishu
from qiuzhao.collector import p1_platform_beisen as beisen
from qiuzhao.collector import p1_platform_moka as moka

MODULE = 'qiuzhao.collector.p1_feishu_public'


def new_tenant_config():
    return {'feishu': {'newtenant': {
        'name': '新飞书公司',
        'sites': [{'url': 'https://newtenant.jobs.feishu.cn/campus/position/list',
                   'tenant_names': ['新飞书公司'], 'portal_type': 6}]}}}


def test_default_sites_preserved_without_json_section(tmp_path):
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps({'beisen': {}, 'moka': {}}), encoding='utf-8')
    with patch.object(feishu, 'CONFIG_PATH', config):
        feishu.reload_config()
        assert feishu.COMPANIES['xiaopeng'] == '小鹏汽车'
        assert feishu.sites_for('xiaopeng')[0]['tenant_names'] == ['小鹏集团']
    feishu.reload_config()
    assert 'newtenant' not in feishu.COMPANIES


def test_config_line_registers_feishu_company(tmp_path):
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps(new_tenant_config(), ensure_ascii=False), encoding='utf-8')
    with patch.object(feishu, 'CONFIG_PATH', config):
        feishu.reload_config()
        assert feishu.COMPANIES['newtenant'] == '新飞书公司'
        assert feishu.merged_registry()['新飞书公司'] == MODULE
    feishu.reload_config()
    assert '新飞书公司' not in feishu.NAME_TO_SLUG


def test_collect_platform_passes_configured_sites(tmp_path):
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps(new_tenant_config(), ensure_ascii=False), encoding='utf-8')
    sentinel = {'jobs': [{'source_record_id': '1'}], 'coverage': {'status': 'success'}}
    with patch.object(feishu, 'CONFIG_PATH', config):
        feishu.reload_config()
        with patch.object(feishu, 'collect_feishu', return_value=sentinel) as mocked:
            result = feishu.collect_platform('新飞书公司', 'campus', tmp_path / 'out')
        assert result is sentinel
        args, _ = mocked.call_args
        assert args[0] == '新飞书公司' and args[1] == 'campus'
        assert args[2][0]['tenant_names'] == ['新飞书公司']
    feishu.reload_config()


def test_missing_sites_is_blocked(tmp_path):
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps({'feishu': {'emptyco': {'name': '空站点公司'}}},
                                 ensure_ascii=False), encoding='utf-8')
    with patch.object(feishu, 'CONFIG_PATH', config):
        feishu.reload_config()
        result = feishu.collect_platform('emptyco', 'campus', tmp_path / 'out')
        assert result['jobs'] == []
        assert result['coverage']['status'] == 'blocked'
        assert 'no verified Feishu site' in result['coverage']['errors'][0]
    feishu.reload_config()


def test_appended_pipeline_block_registers_new_feishu_line(tmp_path):
    from qiuzhao.collector import p1_pipeline
    config = tmp_path / 'p1_platform_companies.json'
    config.write_text(json.dumps(new_tenant_config(), ensure_ascii=False), encoding='utf-8')
    try:
        with patch.object(feishu, 'CONFIG_PATH', config), \
                patch.object(beisen, 'CONFIG_PATH', config), \
                patch.object(moka, 'CONFIG_PATH', config):
            feishu.reload_config()
            beisen.reload_config()
            moka.reload_config()
            reloaded = importlib.reload(p1_pipeline)
            assert reloaded.REGISTRY['新飞书公司'] == MODULE
    finally:
        feishu.reload_config()
        beisen.reload_config()
        moka.reload_config()
        importlib.reload(p1_pipeline)
    assert '新飞书公司' not in p1_pipeline.REGISTRY
    # the hardcoded dedicated adapter still owns its company
    assert p1_pipeline.REGISTRY['小鹏汽车'] == 'qiuzhao.collector.p1_sources_31_40'


def test_request_budget_stops_before_any_job(tmp_path):
    row = {'id': '1', 'title': '工程师', 'recruit_type': {'id': '201', 'name': '校招'},
           'description': '开发软件', 'requirement': '技能熟练', 'channel_online_status': 1,
           'job_post_info': {}}

    class Page:
        def on(self, *args):
            pass

        def remove_listener(self, *args):
            pass

        def goto(self, *args, **kwargs):
            pass

        def wait_for_function(self, *args, **kwargs):
            pass

        def wait_for_timeout(self, *args):
            pass

        def evaluate(self, expression, args=None):
            if 'JSON.parse(document' in expression:
                return {'tenant_info': {'tenant_name': 'Fixture'},
                        'website_info': {'id': '1', 'path': 'campus', 'process_type': 2}}
            if expression == feishu.INSTALL_SDK:
                return True
            if expression == feishu.LIST_CALL:
                return {'code': 0, 'data': {'count': 1, 'job_post_list': [row]}}
            raise AssertionError(expression)

    class Browser:
        def __init__(self, *args, **kwargs):
            self.page = Page()

        def _ensure(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    sites = [{'url': 'https://example.com/campus/position/list',
              'tenant_names': ['Fixture'], 'portal_type': 6}]
    with patch.object(feishu, 'AnonymousBrowser', Browser), \
            patch.dict(feishu.os.environ, {'QIUZHAO_BROWSER_LOCK': str(tmp_path / 'b.lock')}):
        result = feishu.collect_feishu('Fixture', 'campus', sites, tmp_path / 'out', max_requests=1)
    coverage = result['coverage']
    assert coverage['request_budget_exhausted'] is True
    assert coverage['request_budget']['used'] <= 1
    assert coverage['status'] != 'success'
