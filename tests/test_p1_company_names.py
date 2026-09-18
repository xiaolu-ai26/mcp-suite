"""Company-name cleanup for the platform config."""
import json
from pathlib import Path

from qiuzhao.collector import p1_company_names as C


def test_task_examples_use_xianyu_table_name():
    assert C.clean_company_name('海大官网招聘门户',
                                ['海大集团', '海大集团-鲸英计划']) == '海大集团'
    assert C.clean_company_name('AIVA汽车校园招聘门户网', ['AIVA汽车']) == 'AIVA汽车'


def test_clean_short_name_is_never_replaced_by_unrelated_row():
    # The artifact sorts names alphabetically, so the first name for the 安踏 tenant
    # is FILA. A curated short name must survive.
    assert C.clean_company_name('安踏集团', ['FILA', '安踏物流', '安踏集团']) == '安踏集团'
    assert C.is_site_title('安踏集团') is False


def test_site_title_without_table_match_is_stripped():
    assert C.clean_company_name('飞凌嵌入式招聘门户') == '飞凌嵌入式'
    assert C.clean_company_name('晶丰明源网申') == '晶丰明源'
    assert C.clean_company_name('科大国创云网招聘门户') == '科大国创云网'
    assert C.is_site_title('海大官网招聘门户') is True


def test_slogan_and_tagline_are_trimmed():
    assert C.strip_site_title('虹科招聘--Science leads Success') == '虹科'
    assert C.strip_site_title('“芯之所向 星耀未来”湖北星辰-2027') == '湖北星辰'
    assert C.strip_site_title('极客未来招聘门户（新）') == '极客未来'


def test_load_table_names_reads_artifact(tmp_path):
    artifact = tmp_path / 'slugs.json'
    artifact.write_text(json.dumps({'beisen': [
        {'slug': 'aiva', 'company': 'AIVA汽车', 'company_names': ['AIVA汽车']}],
        'moka': [], 'feishu': []}, ensure_ascii=False), encoding='utf-8')
    mapping = C.load_table_names(artifact)
    assert mapping[('beisen', 'aiva')] == ['AIVA汽车']


def test_apply_cleanup_is_idempotent_and_collision_safe():
    config = {
        '_README': 'x',
        'beisen': {
            'gccloud': '科大国创云网招聘门户',
            'kdgcsoft': '科大国创股份有限公司招聘门户',
            'haid1': '海大官网招聘门户',
        },
        'moka': {}, 'feishu': {}, 'workday': {}, 'successfactors': {},
    }
    tables = {('beisen', 'gccloud'): ['科大国创'],
              ('beisen', 'kdgcsoft'): ['科大国创'],
              ('beisen', 'haid1'): ['海大集团']}
    cleaned = C.apply_cleanup(config, tables)
    # Two tenants mapping to the same table company must not collapse into one name.
    names = list(cleaned['beisen'].values())
    assert len(set(names)) == len(names)
    assert cleaned['beisen']['gccloud'] == '科大国创云网'
    assert cleaned['beisen']['kdgcsoft'] == '科大国创股份有限公司'
    assert cleaned['beisen']['haid1'] == '海大集团'
    # Re-running over the cleaned config is a no-op.
    again = C.apply_cleanup(cleaned, tables)
    assert again == cleaned
    rows = C.plan_cleanup(config, tables)
    sources = {row['slug']: row['source'] for row in rows}
    assert sources['haid1'] == 'table'
    assert sources['gccloud'] == 'strip'
