"""Unit tests for the foreign-employer discovery pipeline.

Covers the three things this batch added that can be tested offline:

1. ``tools/ingest_company_csv.py`` — canonicalising, filtering and de-duplicating a
   CSV that the site owner exports from their own paid company-data account;
2. the de-duplication key used by ``pipeline-watch/foreign-universe-build.py``;
3. the domain -> recruiting-system classifier shared by the probe and the universe build.
"""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'foreign' / 'sample_export_20.csv'


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def ingest_mod():
    return _load(ROOT / 'tools' / 'ingest_company_csv.py', 'foreign_ingest_csv')


@pytest.fixture(scope='module')
def universe_mod():
    return _load(ROOT / 'pipeline-watch' / 'foreign-universe-build.py', 'foreign_universe_build')


@pytest.fixture(scope='module')
def sample_csv():
    return FIXTURE.read_text(encoding='utf-8-sig')


def test_fixture_has_20_rows(sample_csv):
    assert len([l for l in sample_csv.strip().splitlines()[1:] if l.strip()]) == 20


def test_ingest_accepts_foreign_rows_and_rejects_others(ingest_mod, sample_csv):
    payload = ingest_mod.ingest(sample_csv, min_insured=200)
    names = {c['company_cn'] for c in payload['companies']}
    assert '巴斯夫新材料(上海)有限公司' in names  # 全角括号已规范化为半角
    assert '中外运敦豪国际航空快件有限公司' in names
    reasons = {r['reason'] for r in payload['rejected']}
    # 内资公司、注销公司、参保不足的分別被挡掉
    assert 'not_foreign_type' in reasons
    assert 'inactive_status' in reasons
    assert payload['summary']['accepted'] + payload['summary']['rejected'] == 20


def test_ingest_min_insured_filter(ingest_mod, sample_csv):
    strict = ingest_mod.ingest(sample_csv, min_insured=1000)
    loose = ingest_mod.ingest(sample_csv, min_insured=200)
    assert strict['summary']['accepted'] < loose['summary']['accepted']
    assert all((c['insured_count'] or 0) >= 1000 for c in strict['companies'])


def test_canonical_name_normalises_whitespace_and_width(ingest_mod):
    assert ingest_mod.canonical_name('  巴斯夫新材料（上海）有限公司  ') == '巴斯夫新材料(上海)有限公司'
    assert ingest_mod.canonical_name('ABB（中国）有限公司') == 'ABB(中国)有限公司'
    assert ingest_mod.canonical_name('') == ''


def test_dedupe_key_ignores_suffix_width_and_case(ingest_mod):
    key = ingest_mod.dedupe_key
    assert key('巴斯夫新材料（上海）有限公司') == key('巴斯夫新材料(上海)有限公司')
    assert key('ABB（中国）有限公司') == key('abb(中国)有限公司')
    assert key('西门子医疗系统有限公司') != key('西门子医疗系统(上海)有限公司')


def test_ingest_dedupes_duplicate_rows_and_keeps_largest_insured(ingest_mod):
    text = ('公司名称,企业类型,登记状态,参保人数,行业\n'
            '巴斯夫新材料（上海）有限公司,外商投资,存续,300,化工\n'
            '巴斯夫新材料(上海)有限公司,外商投资,存续,900,化工\n')
    payload = ingest_mod.ingest(text, min_insured=200)
    assert payload['summary']['accepted'] == 1
    rec = payload['companies'][0]
    assert rec['insured_count'] == 900
    assert '巴斯夫新材料(上海)有限公司' in rec['duplicate_names']


def test_ingest_marks_already_known_against_universe(ingest_mod, sample_csv, tmp_path):
    existing = tmp_path / 'universe.json'
    existing.write_text(json.dumps({'companies': [{'company_cn': '巴斯夫新材料(上海)有限公司'}]},
                                   ensure_ascii=False), encoding='utf-8')
    payload = ingest_mod.ingest(sample_csv, min_insured=200)
    known = {ingest_mod.dedupe_key(c['company_cn']) for c in json.loads(
        existing.read_text(encoding='utf-8'))['companies']}
    marked = [c for c in payload['companies'] if ingest_mod.dedupe_key(c['company_cn']) in known]
    assert len(marked) == 1


def test_ingest_keeps_extra_columns(ingest_mod):
    text = ('公司名称,企业类型,登记状态,参保人数,自定义列\n'
            '测试外资有限公司,外商投资,存续,500,保留我\n')
    payload = ingest_mod.ingest(text, min_insured=200)
    assert payload['companies'][0]['extra'].get('自定义列') == '保留我'


def test_classify_detects_every_adapter_platform(universe_mod):
    cases = {
        'https://app.mokahr.com/campus-recruitment/bosch/151492#/jobs': ('Moka', 'bosch/151492'),
        'https://frsh.zhiye.com/campus/jobs': ('北森', 'frsh'),
        'https://xiaopeng.jobs.feishu.cn/campus': ('飞书招聘', 'xiaopeng'),
        'https://wecruit.hotjob.cn/REDACTED/pb/school.html':
            ('大易', 'REDACTED'),
        'https://campus.51job.com/pepsico2027/': ('51job', 'pepsico2027'),
        'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite':
            ('Workday', 'nvidia/wd5/NVIDIAExternalCareerSite'),
        'https://careers-zoetis.icims.com/jobs': ('iCIMS', 'zoetis'),
        'https://bcg.eightfold.ai/careers': ('Eightfold', 'bcg'),
        'https://bloomberg.avature.net/careers': ('Avature', 'bloomberg'),
        'https://nestle.tupu360.com/position/list': ('tupu360', 'nestle'),
    }
    for url, (platform, key) in cases.items():
        got = universe_mod.classify([url])
        assert got[0] == platform, url
        assert got[1] == key, url


def test_classify_returns_empty_for_unknown_domain(universe_mod):
    platform, key, url = universe_mod.classify(['https://careers.example.com/jobs'])
    assert platform == '' and key == '' and url == 'https://careers.example.com/jobs'


def test_classify_prefers_first_matching_url(universe_mod):
    platform, key, _ = universe_mod.classify(
        ['https://mp.weixin.qq.com/s/abc', 'https://app.mokahr.com/campus-recruitment/ti/142216#/'])
    assert (platform, key) == ('Moka', 'ti/142216')
