"""Location chain (2026-09-28): raw -> normalize -> merge (P1 + run.py) -> refresh -> MCP / Feishu.

Evidence: tests/fixtures/lenovo/lenovo-81482.html is the official Lenovo detail page for Req
WD00104952 (Global Media Strategy Manager, B2B), fetched once with one GET on 2026-09-28T06:32:42Z
from https://jobs.lenovo.com/en_US/careers/JobDetail/Global-Media-Strategy-Manager-B2B/81482
(sha256 5951733d4f3112cb404f972d82b20f4eb27573d291792c995d7f1641b4b782ff). It states Country/Region
United States of America, State North Carolina, City Morrisville and "*This is a remote position".
The listing pages and the multi-location snippet below are synthetic test scaffolding, marked as
such; they are not evidence about any real posting.

OLD_ROW copies the location-relevant fields of p1-4e448b5631f14405b03f63c3 from the accepted
snapshot 07205aef0602eae144ed1888c97359ec8322623ae6eb69d6ed870647cb7b1f3a.jobs.json.
"""
import copy
import json
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from qiuzhao import normalize as N
from qiuzhao import tools as T
from qiuzhao import v4_fields as V
from qiuzhao.collector import p1_pipeline as p
from qiuzhao.collector import p1_sources_11_20 as lenovo_src
from qiuzhao.collector import sync_lark_multivalue as S

FIXTURE = Path(__file__).parent / "fixtures" / "lenovo" / "lenovo-81482.html"
URL = "https://jobs.lenovo.com/en_US/careers/JobDetail/Global-Media-Strategy-Manager-B2B/81482"

OLD_ROW = {
    "id": "p1-4e448b5631f14405b03f63c3", "p1_identity": "p1-4e448b5631f14405b03f63c3",
    "source_record_id": "81482", "recruitment_unit": "联想", "p1_company": "联想", "p1_scope": "social",
    "job_title": "Global Media Strategy Manager, B2B", "cities": ["Morrisville"],
    "cities_normalized": ["未披露"], "city_normalized": "未披露", "country": "中国", "region": "mainland",
    "overseas_flag": False, "recruitment_type": "社会招聘", "status": "open",
    "application_url": URL, "detail_url": URL, "source_url": URL, "published_at": None,
    "reviewed_at": "2026-09-18T08:39:37.227270+00:00", "source_name": "联想官方招聘",
    "description_raw": "Global Media Strategy Manager – B2B\n*This is a remote position\nTeam:\nGlobal Media COE",
}


class FakeLenovo:
    """Synthetic listing pages (scaffolding) + the real official detail page."""

    def get(self, url, name, payload=None):
        if "SearchJobsUniversity" in url:
            return "<p>0 - 0 of 0 jobs</p>", name
        if "SearchJobs" in url:
            return ('<p>1 - 1 of 1 jobs</p><article><h3><a href="' + URL
                    + '">Global Media Strategy Manager, B2B</a></h3></article>'), name
        assert url == URL
        return FIXTURE.read_text(encoding="utf-8"), "detail-81482"


def collected_lenovo():
    cov = {"errors": [], "pages_scanned": 0}
    jobs = lenovo_src._lenovo("联想", "social", FakeLenovo(), cov)
    assert not cov["errors"] and len(jobs) == 1
    return jobs[0]


def normalized(row):
    row = copy.deepcopy(row)
    N.normalize_records([row])
    return row


# ---------------------------------------------------------------- collector

def test_lenovo_detail_keeps_official_country_state_city():
    job = collected_lenovo()
    assert job["cities"] == ["Morrisville"]
    assert job["location_country_raw"] == "United States of America"
    assert job["location_state_raw"] == "North Carolina"
    assert job["locations_raw"] == [{"country": "United States of America", "state": "North Carolina",
                                     "city": "Morrisville"}]


def test_lenovo_additional_locations_keep_each_city_with_its_country():
    # Synthetic snippet in the official page's markup: two Additional Locations.
    html = ('<div class="article__content__view__field"><div class="article__content__view__field__label">'
            'Country/Region:</div><div class="article__content__view__field__value">United States of America'
            '</div></div><div class="article__content__view__field"><div class="article__content__view__field__label">'
            'City:</div><div class="article__content__view__field__value">Morrisville</div></div>'
            '<div class="article__content__view__field__value"><strong>Additional Locations</strong>:&nbsp;'
            '<div>* United States of America - North Carolina - Morrisville</div>'
            '<div>* China - Beijing - Beijing</div></div>')
    place = lenovo_src._lenovo_location(BeautifulSoup(html, "html.parser"))
    assert place["locations_raw"] == [
        {"country": "United States of America", "state": "North Carolina", "city": "Morrisville"},
        {"country": "China", "state": "Beijing", "city": "Beijing"}]
    loc = V.location_of({"cities": ["Morrisville", "Beijing"], "location_country_raw": place["country"],
                         "locations_raw": place["locations_raw"]})
    assert loc["locations"] == [{"country": "美国", "state": "North Carolina", "city": "Morrisville"},
                                {"country": "中国", "state": "Beijing", "city": "北京"}]
    assert loc["region"] == "中国大陆、海外"


# ---------------------------------------------------------------- normalize

def test_lenovo_81482_normalizes_to_usa_north_carolina_morrisville_remote():
    row = normalized({**OLD_ROW, **{k: v for k, v in collected_lenovo().items() if k != "id"}})
    assert row["cities_normalized"] == ["Morrisville"] and row["city_normalized"] == "Morrisville"
    assert (row["country"], row["location_state"], row["work_mode"]) == ("美国", "North Carolina", "远程")
    assert row["country_basis"] == ["source"]
    assert (row["region"], row["overseas_flag"]) == ("海外", True)


def test_old_row_default_china_signature_becomes_unknown_until_source_fields_arrive():
    """The accepted row carries the old normalizer's default signature (city_normalized 未披露 +
    country 中国, no raw country): that 中国 is not kept, so the country is unknown, not 中国大陆.
    Nothing in the code knows this id; the real country needs source fields (see migration test)."""
    it = V.convert(OLD_ROW)[0]
    assert (it["cities"], it["region"], "country" in it, it["work_mode"]) == (["Morrisville"], "", False, "远程")
    row = normalized(OLD_ROW)
    assert (row["country"], row["country_basis"], row["cities_normalized"]) == ("", [], ["Morrisville"])


def migrate_with_saved_page(row):
    """What the private one-time migration helper does: parse the saved official page with the
    ordinary adapter parser and add only source-derived raw fields + provenance."""
    place = lenovo_src._lenovo_location(BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser"))
    return {**row, "location_country_raw": place["country"], "location_state_raw": place["state"],
            "locations_raw": place["locations_raw"],
            "location_raw_provenance": {"source_url": URL, "fetched_at": "2026-09-28T06:32:42Z",
                                        "sha256": "5951733d4f3112cb404f972d82b20f4eb27573d291792c995d7f1641b4b782ff"}}


def test_scoped_migration_source_fields_then_normal_normalize_and_merge():
    row = normalized(migrate_with_saved_page(OLD_ROW))
    assert (row["country"], row["country_basis"], row["location_state"], row["region"], row["work_mode"]) == \
        ("美国", ["source"], "North Carolina", "海外", "远程")
    assert (row["reviewed_at"], row["published_at"]) == (OLD_ROW["reviewed_at"], OLD_ROW["published_at"])
    # Later collections go through the normal merge: a place-less detail keeps the migrated raw place.
    bare = collected_lenovo()
    for field in ("cities", "location_country_raw", "location_state_raw", "locations_raw"):
        bare[field] = [] if field in ("cities", "locations_raw") else ""
    incoming = lenovo_result(bare)
    row["id"] = row["p1_identity"] = incoming["jobs"][0]["p1_identity"]
    merged, _ = p.merge_records([row], [("联想", "social", incoming)])
    assert (merged[0]["country"], merged[0]["location_state"], merged[0]["country_basis"]) == \
        ("美国", "North Carolina", ["source"])
    assert merged[0]["location_raw_provenance"]["sha256"].startswith("5951733d")


def test_region_of_follows_the_stated_country():
    assert V.region_of({"cities": ["Morrisville"], "location_country_raw": "United States"}) == "海外"
    assert V.region_of({"cities": ["Morrisville"]}) == ""
    assert V.city_region("Morrisville") == ""  # a 全国 row is no match for an unknown foreign city


def test_domestic_foreign_unknown_examples():
    cases = {
        ("北京（Beijing）",): (["北京"], ["中国"], "中国大陆"),
        ("Shanghai", "China"): (["上海"], ["中国"], "中国大陆"),
        ("浙江省杭州市桐庐县", "广东省·深圳市"): (["杭州", "深圳"], ["中国"], "中国大陆"),
        ("{'area_code': '000000.110000.110100.110108', 'area_cn': '北京-海淀区'}",): (["北京"], ["中国"], "中国大陆"),
        ("全国",): (["全国"], ["中国"], "中国大陆"),
        ("香港",): (["香港"], ["中国香港"], "港澳台"),
        ("东京",): (["东京"], ["日本"], "海外"),
        ("Sao Paulo - Brazil",): (["Sao Paulo"], ["巴西"], "海外"),
        ("SINGAPORE",): (["Singapore"], ["新加坡"], "海外"),
        ("Stuttgart",): (["Stuttgart"], ["德国"], "海外"),
        ("Morrisville",): (["Morrisville"], [], ""),
        # Chinese script is not China: an unlisted district or overseas name stays unknown.
        ("翠屏区",): (["翠屏区"], [], ""),
        ("惠灵顿",): (["惠灵顿"], [], ""),
        ("北京顺义区",): (["北京"], ["中国"], "中国大陆"),
        # 2026-09-28 migration finds: a 香港 token is a city, never a country stamped on 北京.
        ("北京市", "科威特城", "香港特别行政区"): (["北京", "科威特城", "香港"], ["中国", "科威特", "中国香港"],
                                             "中国大陆、港澳台、海外"),
        ("深圳", "中国香港"): (["深圳", "香港"], ["中国", "中国香港"], "中国大陆、港澳台"),
        ("北京", "美国"): (["北京"], ["中国", "美国"], "中国大陆、海外"),
        ("未知",): ([], [], ""),
        (): ([], [], ""),
    }
    for cities, (want_cities, want_countries, want_region) in cases.items():
        loc = V.location_of({"cities": list(cities)})
        assert (loc["cities"], loc["countries"], loc["region"]) == (want_cities, want_countries, want_region), cities


def test_remote_is_a_work_mode_and_only_a_named_country_bounds_it():
    remote_us = V.location_of({"cities": ["Remote US"]})
    assert (remote_us["cities"], remote_us["countries"], remote_us["work_modes"]) == ([], ["美国"], ["远程"])
    multi = V.location_of({"cities": ["Germany (Remote) ; Ireland (Remote)"]})
    assert multi["countries"] == ["德国", "爱尔兰"] and multi["work_modes"] == ["远程"]
    for token in ("Remote", "远程", "Remote: EMEA", "AmericasRemote"):
        loc = V.location_of({"cities": [token]})
        assert (loc["cities"], loc["countries"], loc["region"], loc["work_modes"]) == ([], [], "", ["远程"]), token
    assert V.location_of({"cities": ["Hybrid"]})["work_modes"] == ["混合"]
    wuhan = V.location_of({"cities": ["CN-Wuhan-Remote"]})
    assert (wuhan["cities"], wuhan["countries"], wuhan["work_modes"]) == (["武汉"], ["中国"], ["远程"])
    discord = V.location_of({"cities": ["San Francisco Bay Area or New York (Remote)"]})
    assert (discord["cities"], discord["countries"], discord["work_modes"]) == (["旧金山", "纽约"], ["美国"], ["远程"])


def test_global_hq_customer_travel_never_yield_a_country():
    row = {"cities": ["Morrisville"], "recruitment_unit": "联想", "job_title": "Global Media Strategy Manager",
           "description_raw": "Lenovo is headquartered in Beijing, China. Travel to customer sites in Shanghai "
                              "and work with remote teams worldwide; experience with remote sensing is a plus."}
    loc = V.location_of(row)
    assert (loc["countries"], loc["region"], loc["work_modes"]) == ([], "", [])
    for token in ("Global", "HQ", "总部", "Worldwide"):
        assert V.location_of({"cities": [token]}) == {"locations": [], "location_basis": [], "country_basis": [], "cities": [],
                                                      "countries": [], "states": [], "region": "",
                                                      "work_modes": []}, token
    # No place at all, even at a Chinese company: unknown, not 中国.
    row = normalized({"id": "x", "cities": [], "recruitment_unit": "中国移动", "job_title": "客户经理"})
    assert (row["country"], row["region"], row["overseas_flag"], row["cities_normalized"]) == ("", "", None, ["未披露"])


def test_location_sync_is_idempotent_and_leaves_timestamps_alone():
    row = normalized(OLD_ROW)
    before = copy.deepcopy(row)
    stats = N.normalize_records([row])
    assert row == before and all(stats[f] == 0 for f in N.LOCATION_FIELDS)
    assert (row["reviewed_at"], row["published_at"]) == (OLD_ROW["reviewed_at"], OLD_ROW["published_at"])


# ---------------------------------------------------------------- merge: P1 pipeline

def lenovo_result(job):
    job = {k: v for k, v in job.items() if k != "id"}
    payload = {"jobs": [job], "coverage": {
        "status": "success", "complete": True, "detail_complete": True, "expected_total": 1,
        "collected_jobs": 1, "pages_scanned": 1, "errors": [], "source_url": "https://jobs.lenovo.com/en_US/careers",
        "evidence": ["listing.json"], "scope_evidence": "official list"}}
    return p.validate_result(payload, "联想", "social")


def test_p1_merge_fixes_the_old_row_and_keeps_its_id():
    old = copy.deepcopy(OLD_ROW)
    incoming = lenovo_result(collected_lenovo())
    old["p1_identity"] = old["id"] = incoming["jobs"][0]["p1_identity"]
    merged, _ = p.merge_records([old], [("联想", "social", incoming)])
    assert len(merged) == 1 and merged[0]["id"] == old["id"]
    assert (merged[0]["country"], merged[0]["location_state"], merged[0]["region"]) == ("美国", "North Carolina", "海外")


def test_p1_merge_incoming_without_place_keeps_the_trusted_location():
    first = lenovo_result(collected_lenovo())
    previous, _ = p.merge_records([], [("联想", "social", first)])
    bare = collected_lenovo()
    for field in ("cities", "location_country_raw", "location_state_raw", "locations_raw"):
        bare[field] = [] if field in ("cities", "locations_raw") else ""
    bare["reviewed_at"] = "2026-09-29T00:00:00+00:00"
    merged, _ = p.merge_records(previous, [("联想", "social", lenovo_result(bare))])
    row = merged[0]
    assert row["cities"] == ["Morrisville"] and row["country"] == "美国" and row["location_state"] == "North Carolina"
    assert row["location_carried_from_reviewed_at"] == previous[0]["reviewed_at"]
    assert row["reviewed_at"] == "2026-09-29T00:00:00+00:00"  # the observation time is the new fetch's own


def test_p1_merge_new_raw_place_wins_over_old():
    previous, _ = p.merge_records([], [("联想", "social", lenovo_result(collected_lenovo()))])
    moved = collected_lenovo()
    moved.update(cities=["北京"], location_country_raw="China", location_state_raw="",
                 locations_raw=[{"country": "China", "state": "", "city": "北京"}])
    merged, _ = p.merge_records(previous, [("联想", "social", lenovo_result(moved))])
    assert (merged[0]["cities_normalized"], merged[0]["country"], merged[0]["region"]) == (["北京"], "中国", "中国大陆")
    assert "location_carried_from_reviewed_at" not in merged[0]


# ---------------------------------------------------------------- merge: run.py refresh

def run_postal(tmp_path, previous, rows):
    from qiuzhao.collector.run import Collector
    (tmp_path / "jobs.json").write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
    c = Collector(tmp_path, delay=0)

    def postal():
        c.states["postal"] = {"status": "partial", "checked_at": "2026-09-28T00:00:00+08:00"}
        return rows
    c.postal = postal
    c.run("postal", 0)
    return {j["id"]: j for j in json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))}


def postal_row(ident, **kw):
    row = dict(id=ident, recruitment_unit="中国邮政集团有限公司", job_title="金融财务类", cities=[],
               application_url="https://x/" + ident, source_url="https://x/" + ident, status="open",
               reviewed_at="2026-09-28T00:00:00+08:00", source_name="中国邮政", description_raw="")
    row.update(kw)
    return row


def test_run_refresh_old_placeholder_never_masks_new_raw(tmp_path):
    old = postal_row("postal-1", cities=["未知"], cities_normalized=["未披露"], city_normalized="未披露",
                     country="中国", region="mainland", overseas_flag=False, reviewed_at="2026-09-20T00:00:00+08:00")
    new = postal_row("postal-1", cities=["Morrisville"], location_country_raw="United States of America")
    got = run_postal(tmp_path, [old], [new])["postal-1"]
    assert (got["cities_normalized"], got["country"], got["region"], got["overseas_flag"]) == \
        (["Morrisville"], "美国", "海外", True)


def test_run_refresh_missing_place_keeps_old_raw_only(tmp_path):
    old = normalized(postal_row("postal-2", cities=["北京市"], reviewed_at="2026-09-20T00:00:00+08:00",
                                job_title="旧岗位名"))
    new = postal_row("postal-2", cities=[], job_title="新岗位名")
    got = run_postal(tmp_path, [old], [new])["postal-2"]
    assert got["cities"] == ["北京市"] and got["cities_normalized"] == ["北京"] and got["country"] == "中国"
    assert got["job_title"] == "新岗位名"  # only the place is carried, not the old row
    assert got["location_carried_from_reviewed_at"] == "2026-09-20T00:00:00+08:00"


# ---------------------------------------------------------------- refresh -> MCP / Feishu

def serve(tmp_path, rows):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return T.Jobs(path, today=date(2026, 9, 28))


def mcp_rows():
    usa = normalized({**OLD_ROW, **{k: v for k, v in collected_lenovo().items() if k != "id"}})
    base = {k: OLD_ROW[k] for k in ("recruitment_type", "status", "source_name", "reviewed_at")}
    bj = normalized({**base, "id": "bj", "job_title": "北京岗", "cities": ["北京"],
                     "application_url": "https://x/bj", "source_url": "https://x/bj"})
    unknown = normalized({**base, "id": "unk", "job_title": "地点未写", "cities": [],
                          "application_url": "https://x/unk", "source_url": "https://x/unk"})
    return [usa, bj, unknown]


def test_mcp_returns_and_filters_country_state_work_mode(tmp_path):
    jobs = serve(tmp_path, mcp_rows())
    out = jobs.search(country="美国")
    by_id = {j["id"]: j for j in out["jobs"]}
    assert set(by_id) == {OLD_ROW["id"], "unk"}          # 北京 excluded, unknown kept as 未注明
    usa = by_id[OLD_ROW["id"]]
    assert (usa["country"], usa["state"], usa["work_mode"], usa["region"]) == ("美国", "North Carolina", "远程", "海外")
    assert usa["match"]["country"] == "岗位写明" and by_id["unk"]["match"]["country"] == V.UNSPECIFIED
    assert {j["id"] for j in jobs.search(country="USA", explicit_only=True)["jobs"]} == {OLD_ROW["id"]}
    assert {j["id"] for j in jobs.search(country="中国")["jobs"]} == {"bj", "unk"}
    assert {j["id"] for j in jobs.search(work_mode="remote", explicit_only=True)["jobs"]} == {OLD_ROW["id"]}
    moved = jobs.search(city="远程")
    assert moved["applied_filters"].get("work_mode") == "远程" and "city" not in moved["applied_filters"]
    moved = jobs.search(city="美国", explicit_only=True)
    assert moved["applied_filters"]["country"] == "美国" and [j["id"] for j in moved["jobs"]] == [OLD_ROW["id"]]
    stats = jobs.stats(group_by="country")
    assert {g["value"]: g["count"] for g in stats["groups"]} == {"美国": 1, "中国": 1, V.UNSPECIFIED: 1}


def test_feishu_excel_conversion_uses_the_stated_place(tmp_path):
    usa, bj, unknown = mcp_rows()
    assert S.values_for(OLD_ROW)["工作地点"] == ["Morrisville"]
    assert S.values_for(usa)["工作地点"] == ["Morrisville"]
    assert S.values_for({"cities": ["Remote US"]})["工作地点"] == ["美国"]
    assert S.values_for({"cities": ["远程"]})["工作地点"] == ["未注明"]
    assert S.values_for(unknown)["工作地点"] == ["未注明"]
    assert S.location_values_for(usa) == {"国家/地区": ["美国"], "州/省": "North Carolina", "办公方式": ["远程"],
                                          "地点明细": ""}
    assert S.location_values_for(unknown) == {"国家/地区": ["未注明"], "州/省": "", "办公方式": ["未注明"],
                                              "地点明细": ""}


# ---------------------------------------------------------------- R1 projection / Excel / schema verify

def r1(name):
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "deploy" / "feishu_r1" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"r1_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r1_projection_carries_location_columns_next_to_work_city():
    proj = r1("sprite_build_projection_r1")
    usa = mcp_rows()[0]
    row = proj.mirror_row(usa, "其他")
    cells = dict(zip(proj.COLUMNS, (proj.cell(row.get(n, "")) for n in proj.COLUMNS)))
    assert (cells["工作地点"], cells["国家/地区"], cells["州/省"], cells["办公方式"], cells["地点明细"]) == \
        ("Morrisville", "美国", "North Carolina", "远程", "")
    multi = {**usa, "cities": ["Morrisville", "Beijing"],
             "locations_raw": [{"country": "United States of America", "state": "North Carolina", "city": "Morrisville"},
                               {"country": "China", "state": "", "city": "Beijing"}]}
    cells = {n: proj.cell(v) for n, v in proj.mirror_row(multi, "其他").items()}
    assert cells["工作地点"] == "Morrisville,北京" and cells["国家/地区"] == "美国,中国"
    assert cells["地点明细"] == "美国/North Carolina/Morrisville；中国//北京"
    cells = {n: proj.cell(v) for n, v in proj.mirror_row(mcp_rows()[2], "其他").items()}
    assert (cells["工作地点"], cells["国家/地区"], cells["州/省"], cells["办公方式"]) == ("未注明", "未注明", "", "未注明")
    # An old unconfirmed country: 国家/地区 stays a standard option (未注明); provenance sits in 地点明细.
    base = {k: OLD_ROW[k] for k in ("recruitment_type", "status", "source_name", "reviewed_at")}
    legacy = {**base, "id": "legacy", "job_title": "旧国家", "application_url": "https://x/l", "source_url": "https://x/l",
              "cities": ["翠屏区"], "country": "中国", "cities_normalized": ["宜宾"]}         # a pre-migration raw row
    cells = {n: proj.cell(v) for n, v in proj.mirror_row(legacy, "其他").items()}
    assert (cells["工作地点"], cells["国家/地区"], cells["地点明细"]) == ("翠屏区", "未注明", "中国" + S.LEGACY_MARK + "//翠屏区")


def test_r1_excel_and_verify_column_contracts_include_location():
    import ast
    from types import SimpleNamespace
    proj, verify = r1("sprite_build_projection_r1"), r1("run_step3_schema_verify_r1")
    # build_xlsx_r1 needs openpyxl at import; read its column constants from the source instead.
    tree = ast.parse((Path(__file__).resolve().parents[1] / "deploy" / "feishu_r1" / "build_xlsx_r1.py")
                     .read_text(encoding="utf-8"))
    consts = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name) and t.id in ("LIVE_ORDER", "MULTI")}
    xlsx = SimpleNamespace(**consts)
    for name in S.LOCATION_COLUMNS:
        assert name in proj.COLUMNS and name in xlsx.LIVE_ORDER and name in verify.LIVE_ORDER
    assert set(xlsx.LIVE_ORDER) == set(verify.LIVE_ORDER) <= set(proj.COLUMNS)
    assert xlsx.MULTI == verify.MULTI == proj.MULTI
    assert {n for n, multiple in verify.SELECTS.items() if multiple} == verify.MULTI
    assert set(proj.SELECTS) == set(verify.SELECTS)
    ok, got, exp = verify.compare_cell("国家/地区", "美国,中国", ["中国", "美国"])
    assert ok and verify.compare_cell("州/省", "North Carolina", "North Carolina")[0]


def test_mcp_schema_declares_country_and_work_mode_flat_and_shared():
    import asyncio
    import pytest
    server = pytest.importorskip("core.server")
    tools = asyncio.run(server.mcp.get_tools())
    search, stats = tools["jobs_search"].parameters["properties"], tools["jobs_stats"].parameters["properties"]
    for name in ("country", "state", "work_mode"):
        assert search[name] == stats[name] and search[name]["type"] == "string"
    assert search["work_mode"]["enum"] == ["", "远程", "混合", "现场", "未注明"]
    assert {"country", "state", "work_mode"} <= set(stats["group_by"]["enum"])


# ---------------------------------------------------------------- 2026-09-28 blocking review fixes

def test_existing_country_tiers_source_over_legacy_over_unknown():
    loc = V.location_of
    # A named legacy country next to a real place survives (no source says otherwise) ...
    kept = loc({"cities": ["蕉城区"], "country": "中国", "cities_normalized": ["宁德"], "city_normalized": "宁德"})
    assert (kept["countries"], kept["country_basis"], kept["region"]) == (["中国"], ["legacy"], "中国大陆")
    # ... known old defaults do not: 中国 beside 未披露, and 海外 (a region, never a country).
    # Only the demonstrable default signature (old city 未披露/未知/"" + 中国) is dropped ...
    assert loc({"cities": ["Morrisville"], "country": "中国", "cities_normalized": ["未披露"]})["countries"] == []
    # ... a 中国 the old normalizer wrote next to a real city stays, as legacy (uncertain).
    assert loc({"cities": ["Morrisville"], "country": "中国", "cities_normalized": ["Morrisville"]})["country_basis"] == ["legacy"]
    assert loc({"cities": ["Shanghai"], "country": "海外"})["countries"] == ["中国"]
    # Place knowledge and structured source fields outrank a contradicting legacy value.
    assert loc({"cities": ["Edinburgh"], "country": "美国", "cities_normalized": ["Edinburgh"]})["countries"] == ["英国"]
    assert loc({"cities": ["Stuttgart"], "country": "英国", "location_country_raw": "Germany"})["country_basis"] == ["source"]
    # A legacy country is never spread over several cities (kept as a country-only location).
    multi = loc({"cities": ["翠屏区", "蕉城区"], "country": "中国", "cities_normalized": ["宜宾", "宁德"]})
    assert multi["country_basis"] == ["legacy"] and {"country": "", "state": "", "city": "翠屏区"} in multi["locations"]
    # Values this module wrote are recomputed, not re-trusted (except those it kept as legacy).
    assert loc({"cities": ["Morrisville"], "country": "中国", "country_basis": ["place"]})["countries"] == []
    assert loc({"cities": ["蕉城区"], "country": "中国", "country_basis": ["legacy"]})["countries"] == ["中国"]


def test_state_rejects_status_words_and_numbers_and_keeps_named_geography():
    loc = V.location_of
    for status in ("open", "closed", "1", "0", "招聘中", "true"):
        assert loc({"cities": ["北京"], "state": status})["states"] == [], status
        assert not V.has_raw_location({"cities": [], "state": status}), status
    assert loc({"cities": ["Morrisville"], "state": "North Carolina"})["states"] == ["North Carolina"]
    only_state = loc({"cities": [], "province_raw": "广东省"})
    assert only_state["locations"] == [{"country": "中国", "state": "广东", "city": ""}]
    only_country = loc({"cities": [], "country_raw": "US"})
    assert only_country["locations"] == [{"country": "美国", "state": "", "city": ""}]
    assert loc({"cities": ["CN"]})["countries"] == ["中国"]
    assert loc({"cities": ["Remote in US"]})["countries"] == ["美国"]          # "in" is not India
    assert loc({"cities": ["CA"]})["countries"] == []                         # bare CA is ambiguous
    # San Diego is not a curated US city: without an explicit USA the country stays unknown.
    assert loc({"cities": ["San Diego, CA"]})["locations"] == [{"country": "", "state": "CA", "city": "San Diego"}]
    assert loc({"cities": ["San Diego, CA, USA"]})["locations"] == [{"country": "美国", "state": "California", "city": "San Diego"}]


def test_negated_work_mode_phrases_are_not_remote():
    for text in ("This is not a remote position.", "The role is not fully remote.", "No remote work.",
                 "Remote work is not available for this role.", "本岗位不支持远程办公", "非远程岗位，需坐班。"):
        assert "远程" not in V.location_of({"cities": ["北京"], "description_raw": text})["work_modes"], text
    assert V.location_of({"cities": ["Not Remote - Shanghai"]})["work_modes"] == []
    assert V.location_of({"description_raw": "This role is not fully remote; this is a hybrid role."})["work_modes"] == ["混合"]
    assert V.location_of({"description_raw": "*This is a remote position"})["work_modes"] == ["远程"]


def test_mixed_locations_keep_their_own_country_and_state():
    loc = V.location_of({"cities": ["Morrisville", "Beijing", "香港"], "location_country_raw": "United States",
                         "location_state_raw": "North Carolina"})
    assert {"country": "", "state": "", "city": "Morrisville"} in loc["locations"]   # not fanned
    assert {"country": "中国", "state": "", "city": "北京"} in loc["locations"]
    assert {"country": "中国香港", "state": "", "city": "香港"} in loc["locations"]
    assert {"country": "美国", "state": "", "city": ""} in loc["locations"]
    assert loc["region"] == "中国大陆、港澳台、海外"


def test_partial_input_keeps_known_country_state_for_same_place():
    old = normalized({"id": "a", "cities": ["蕉城区"], "country": "中国", "cities_normalized": ["宁德"],
                      "city_normalized": "宁德", "reviewed_at": "2026-09-20T00:00:00+08:00"})
    assert old["country_basis"] == ["legacy"]
    new = {"id": "a", "cities": ["蕉城区"], "reviewed_at": "2026-09-28T00:00:00+08:00"}
    assert N.carry_forward_location(new, old)
    new = normalized(new)
    assert (new["country"], new["country_basis"], new["reviewed_at"]) == ("中国", ["legacy"], "2026-09-28T00:00:00+08:00")
    old = normalized({"id": "b", "cities": ["Morrisville"], "location_country_raw": "United States",
                      "location_state_raw": "North Carolina"})
    new = {"id": "b", "cities": ["Morrisville"]}
    assert N.carry_forward_location(new, old)
    assert normalized(new)["location_state"] == "North Carolina"
    moved = {"id": "b", "cities": ["Austin"]}                 # another place: nothing carried
    assert not N.carry_forward_location(moved, old) and "location_country_raw" not in moved


def test_mcp_state_filter_matches_the_same_location_only(tmp_path):
    base = {k: OLD_ROW[k] for k in ("recruitment_type", "status", "source_name", "reviewed_at")}
    mixed = normalized({**base, "id": "mixed", "job_title": "两地岗", "application_url": "https://x/m",
                        "source_url": "https://x/m", "cities": ["Morrisville", "深圳"],
                        "locations_raw": [{"country": "United States", "state": "North Carolina", "city": "Morrisville"},
                                          {"country": "China", "state": "广东", "city": "深圳"}]})
    jobs = serve(tmp_path, [mixed])
    hit = jobs.search(country="美国", state="North Carolina", explicit_only=True)["jobs"]
    assert [j["id"] for j in hit] == ["mixed"] and "_locs" not in hit[0]
    assert jobs.search(country="美国", state="广东")["total"] == 0          # no cross-pair match
    assert jobs.search(city="深圳", country="美国")["total"] == 0
    assert jobs.search(city="深圳", state="广东省", explicit_only=True)["total"] == 1
    assert jobs.stats(group_by="state")["groups"][0]["value"] in ("North Carolina", "广东")


def test_mcp_legacy_country_is_an_inferred_match(tmp_path):
    base = {k: OLD_ROW[k] for k in ("recruitment_type", "status", "source_name", "reviewed_at")}
    legacy = normalized({**base, "id": "legacy", "job_title": "旧国家", "application_url": "https://x/l",
                         "source_url": "https://x/l", "cities": ["翠屏区"], "country": "中国",
                         "cities_normalized": ["宜宾"]})
    out = serve(tmp_path, [legacy]).search(country="中国")
    assert out["jobs"][0]["match"] == {"level": "推断匹配", "country": "旧数据记录"}
    assert out["jobs"][0]["country_basis"] == ["legacy"]
    assert serve(tmp_path, [legacy]).search(country="中国", explicit_only=True)["total"] == 0


# ---------------------------------------------------------------- independent review 2026-09-28 (P1/P2 repros)

def test_review_p1_1_old_default_china_signature_is_not_kept():
    for row in ({"cities": ["未披露"], "city_normalized": "未披露", "country": "中国"},
                {"cities": ["Morrisville"], "city_normalized": "未披露", "country": "中国"},
                {"cities": ["翠屏区"], "country": "中国"},                     # no old city: same default
                {"cities": [], "cities_normalized": ["未知"], "country": "中国"}):
        loc = V.location_of(row)
        assert loc["countries"] == [] and loc["region"] == "", row
        assert S.values_for(row)["工作地点"] in (["未注明"], loc["cities"]), row
        assert S.location_values_for(row)["国家/地区"] == ["未注明"], row
    assert S.values_for({"cities": ["未披露"], "city_normalized": "未披露", "country": "中国"})["工作地点"] == ["未注明"]
    # A non-default legacy country stays internally (basis legacy) but is not a confirmed value:
    # Feishu 国家/地区 keeps only standard options; the uncertainty goes to 地点明细.
    us = {"cities": [], "city_normalized": "Morrisville", "cities_normalized": ["Morrisville"], "country": "美国"}
    assert V.location_of({**us, "cities": ["Morrisville"]})["country_basis"] == ["legacy"]
    only = {"cities": [], "cities_normalized": ["Anchorage"], "city_normalized": "Anchorage", "country": "美国"}
    legacy_cols = S.location_values_for({"country": "美国", "city_normalized": "X", "cities_normalized": ["X"]})
    assert legacy_cols["国家/地区"] == ["未注明"]
    assert legacy_cols["地点明细"] == "美国" + S.LEGACY_MARK + "//X"
    assert S.values_for({"country": "美国", "city_normalized": "X", "cities_normalized": ["X"]})["工作地点"] == ["X"]
    assert S.values_for({"country": "美国", "cities_normalized": [], "city_normalized": "Y"})["工作地点"] == ["未注明"]
    # carry_forward does not spread the old default to a new collection of the same place.
    old = {"id": "m", "cities": ["Morrisville"], "city_normalized": "未披露", "cities_normalized": ["未披露"], "country": "中国"}
    new = {"id": "m", "cities": ["Morrisville"]}
    N.carry_forward_location(new, old)
    assert normalized(new)["country"] == ""


def test_review_p1_2_us_state_codes_are_not_countries_and_cities_have_no_comma():
    # The country is US only when it is explicit (third part) or the city is a known US city ...
    cases = {"San Francisco, CA": ("旧金山", "California"), "Austin, TX, USA": ("Austin", "Texas"),
             "Kansas City, MO, United States": ("Kansas City", "Missouri"),
             "Raleigh, North Carolina, USA": ("Raleigh", "North Carolina")}
    for token, (city, state) in cases.items():
        loc = V.location_of({"cities": [token]})
        assert loc["locations"] == [{"country": "美国", "state": state, "city": city}], token
        assert loc["region"] == "海外"
    # ... otherwise city and state are kept as written and the country stays unknown (never 澳门/印度/德国).
    for token, (city, state) in {"Kansas City, MO": ("Kansas City", "MO"), "Indianapolis, IN": ("Indianapolis", "IN"),
                                 "Wilmington, DE": ("Wilmington", "DE")}.items():
        loc = V.location_of({"cities": [token]})
        assert loc["locations"] == [{"country": "", "state": state, "city": city}] and loc["region"] == "", token
    assert V.location_of({"cities": ["Toronto, ON"]})["locations"] == [{"country": "加拿大", "state": "Ontario", "city": "多伦多"}]
    odd = V.location_of({"cities": ["Foo, Bar"]})
    assert all("," not in c for c in odd["cities"]) and odd["countries"] == []
    assert S.values_for({"cities": ["San Francisco, CA"]})["工作地点"] == ["旧金山"]


def test_review_p1_3_new_triples_are_not_mixed_with_old_record_country():
    old = normalized({"id": "d", "cities": ["Dublin"], "country_raw": "United States of America"})
    new = {"id": "d", "cities": ["Dublin"], "locations_raw": [{"country": "Ireland", "state": "", "city": "Dublin"}]}
    N.carry_forward_location(new, old)
    got = normalized(new)
    assert got["country"] == "爱尔兰" and got["locations_normalized"] == [{"country": "爱尔兰", "state": "", "city": "Dublin"}]
    # Even if both are present on one record, the triples win.
    both = V.location_of({"cities": ["Dublin"], "country_raw": "US",
                          "locations_raw": [{"country": "Ireland", "state": "", "city": "Dublin"}]})
    assert both["countries"] == ["爱尔兰"]


def test_review_p1_4_hmt_synonyms_and_legacy_counts_as_inferred(tmp_path):
    base = {k: OLD_ROW[k] for k in ("recruitment_type", "status", "source_name", "reviewed_at")}
    rows = [normalized({**base, "id": i, "job_title": i, "application_url": "https://x/" + i,
                        "source_url": "https://x/" + i, **extra})
            for i, extra in (("hk", {"cities": ["香港"]}), ("tw", {"cities": ["台北"]}), ("mo", {"cities": ["澳门"]}),
                             ("legacy", {"cities": ["蕉城区"], "country": "中国", "cities_normalized": ["宁德"]}))]
    jobs = serve(tmp_path, rows)
    for q, want in (("香港", "hk"), ("台湾", "tw"), ("澳门", "mo")):
        out = jobs.search(country=q)
        assert [j["id"] for j in out["jobs"]] == [want] and out["notices"], q
    groups = {g["value"]: g for g in jobs.stats(group_by="country")["groups"]}
    assert groups["中国"]["inferred_count"] == 1 and groups["中国"]["explicit_count"] == 0


def test_review_p2_2_multi_city_keeps_legacy_as_country_only_location():
    loc = V.location_of({"cities": ["Morrisville", "Raleigh"], "country": "美国",
                         "cities_normalized": ["Morrisville", "Raleigh"]})
    assert {"country": "美国", "state": "", "city": ""} in loc["locations"] and loc["country_basis"] == ["legacy"]
    assert {"country": "", "state": "", "city": "Morrisville"} in loc["locations"]   # not assigned to a city


def test_review_p2_3_explicit_province_prefix_and_english_province_keep_state(tmp_path):
    assert V.location_of({"cities": ["广东省·深圳市"]})["locations"] == [{"country": "中国", "state": "广东", "city": "深圳"}]
    assert V.location_of({"cities": ["浙江省杭州市桐庐县"]})["states"] == ["浙江"]
    en = V.location_of({"locations_raw": [{"country": "China", "state": "Guangdong Province", "city": "Shenzhen"}]})
    assert en["locations"] == [{"country": "中国", "state": "广东", "city": "深圳"}]
    base = {k: OLD_ROW[k] for k in ("recruitment_type", "status", "source_name", "reviewed_at")}
    row = normalized({**base, "id": "gd", "job_title": "深圳岗", "application_url": "https://x/gd",
                      "source_url": "https://x/gd", "cities": ["广东省·深圳市"]})
    jobs = serve(tmp_path, [row])
    assert jobs.search(state="广东", explicit_only=True)["total"] == jobs.search(state="Guangdong", explicit_only=True)["total"] == 1


# ---------------------------------------------------------------- P2-4 Tencent merge + P1 detail-cache hit

def tencent_merge(tmp_path, previous, incoming):
    from unittest.mock import patch
    from qiuzhao.collector import auto_collect as ac
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
    with patch.object(ac, "JOBS_FILE", path), patch.object(ac, "log"):
        ac.merge_tencent_jobs(incoming)
    return {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8"))}


def test_tencent_merge_keeps_trusted_place_and_new_triples_win(tmp_path):
    base = {"source_name": "腾讯校园招聘官方网站", "detail_url": "https://t/1", "source_url": "https://t/1",
            "application_url": "https://t/1", "reviewed_at": "2026-09-20T00:00:00+08:00"}
    old = normalized({**base, "id": "tencent-1", "job_title": "旧名", "cities": ["Morrisville"],
                      "location_country_raw": "United States of America", "location_state_raw": "North Carolina"})
    # A detail without its place: the old raw place is kept, the business field refreshes, no timestamp rewrite.
    got = tencent_merge(tmp_path, [old], [{**base, "id": "tencent-1", "job_title": "新名", "cities": [],
                                          "reviewed_at": "2026-09-28T00:00:00+08:00"}])["tencent-1"]
    assert (got["job_title"], got["cities"], got["country"], got["location_state"]) == \
        ("新名", ["Morrisville"], "美国", "North Carolina")
    assert got["reviewed_at"] == "2026-09-28T00:00:00+08:00"   # the new observation, not a fabricated one
    # New structured triples: the old record-level country/state never sit next to them.
    got = tencent_merge(tmp_path, [old], [{**base, "id": "tencent-1", "job_title": "旧名", "cities": ["Dublin"],
                                          "locations_raw": [{"country": "Ireland", "state": "", "city": "Dublin"}]}])["tencent-1"]
    assert got["country"] == "爱尔兰" and "location_country_raw" not in got and "location_state_raw" not in got
    # Same place again: nothing to update, the row is untouched.
    same = tencent_merge(tmp_path, [old], [dict(old)])["tencent-1"]
    assert same == old


def test_p1_moka_detail_cache_hit_keeps_the_same_geography_through_merge(tmp_path, monkeypatch):
    from unittest.mock import patch
    from qiuzhao.collector import p1_platform_moka as moka
    from qiuzhao.collector import p1_sources_01_10 as src
    monkeypatch.setenv("QIUZHAO_P1_DETAIL_CACHE_ROOT", str(tmp_path / "cache"))
    row = {"id": "m1", "updatedAt": "2026-09-27T00:00:00", "title": "软件工程师", "hireMode": 2, "commitment": "全职"}
    detail = {"id": "m1", "title": "软件工程师", "hireMode": 2, "commitment": "全职", "updatedAt": row["updatedAt"],
              "jobDescription": "<p>岗位职责：开发。</p>",
              "locations": [{"cityName": "深圳", "provinceName": "广东省", "country": "中国"}]}
    out = tmp_path / "campus"
    out.mkdir()
    with patch.object(src, "request_json", return_value=detail):
        fresh = src.moka_detail_cached("dji", "campus", row, "https://example.com", "dji", "1", None, out)
    with patch.object(src, "request_json", side_effect=AssertionError("cache hit must not refetch")):
        hit = src.moka_detail_cached("dji", "campus", row, "https://example.com", "dji", "1", None, out)
    assert (fresh[2], hit[2]) == (False, True)

    def built(result):
        return moka._job(row, result[0], result[1], result[2], "https://example.com/campus", "official", "dji",
                         "campus", "2026-09-28T00:00:00+00:00")
    first, again = built(fresh), built(hit)
    geo = ("cities", "location", "city")
    assert {k: first.get(k) for k in geo} == {k: again.get(k) for k in geo}
    payload = lambda j: {"jobs": [j], "coverage": {"status": "success", "complete": True, "detail_complete": True,
                         "expected_total": 1, "collected_jobs": 1, "pages_scanned": 1, "errors": [],
                         "source_url": "https://example.com", "evidence": ["l.json"], "scope_evidence": "official"}}
    previous, _ = p.merge_records([], [("大疆", "campus", p.validate_result(payload(first), "大疆", "campus"))])
    merged, _ = p.merge_records(previous, [("大疆", "campus", p.validate_result(payload(again), "大疆", "campus"))])
    keys = ("cities_normalized", "country", "country_basis", "location_state", "region")
    assert {k: merged[0][k] for k in keys} == {k: previous[0][k] for k in keys}
    assert (merged[0]["cities_normalized"], merged[0]["country"]) == (["深圳"], "中国")


# ---------------------------------------------------------------- final review P2 (state codes in context; Georgia)

def test_final_p2_state_code_expands_only_in_its_typed_country(tmp_path):
    us = V.location_of({"locations_raw": [{"country": "US", "state": "NC", "city": "Morrisville"}]})
    assert us["locations"] == [{"country": "美国", "state": "North Carolina", "city": "Morrisville"}]
    ca = V.location_of({"locations_raw": [{"country": "Canada", "state": "ON", "city": "Toronto"}]})
    assert ca["locations"] == [{"country": "加拿大", "state": "Ontario", "city": "多伦多"}]
    assert V.location_of({"cities": ["Morrisville"], "location_country_raw": "United States",
                          "location_state_raw": "NC"})["states"] == ["North Carolina"]
    # Without the country context a code stays as written; MO is never Macau.
    assert V.location_of({"cities": ["X"], "location_state_raw": "MO"})["locations"] == [{"country": "", "state": "MO", "city": "X"}]
    base = {k: OLD_ROW[k] for k in ("recruitment_type", "status", "source_name", "reviewed_at")}
    rows = [normalized({**base, "id": "us", "job_title": "us", "application_url": "https://x/us", "source_url": "https://x/us",
                        "locations_raw": [{"country": "US", "state": "NC", "city": "Morrisville"}]}),
            normalized({**base, "id": "mo", "job_title": "mo", "application_url": "https://x/mo", "source_url": "https://x/mo",
                        "cities": ["Kansas City, MO, USA"]}),
            normalized({**base, "id": "macau", "job_title": "macau", "application_url": "https://x/ma", "source_url": "https://x/ma",
                        "cities": ["澳门"]})]
    jobs = serve(tmp_path, rows)
    for q in ("NC", "North Carolina"):
        assert [j["id"] for j in jobs.search(state=q, explicit_only=True)["jobs"]] == ["us"], q
    assert [j["id"] for j in jobs.search(country="美国", state="NC", explicit_only=True)["jobs"]] == ["us"]
    assert [j["id"] for j in jobs.search(state="MO", explicit_only=True)["jobs"]] == ["mo"]   # Missouri, not 澳门
    assert jobs.search(country="中国澳门", state="MO", explicit_only=True)["total"] == 0
    # Country unknown: the code is kept as written and never guessed to be a US state.
    unknown = serve(tmp_path, [normalized({**base, "id": "nc?", "job_title": "nc?", "application_url": "https://x/n",
                                           "source_url": "https://x/n", "cities": ["Foo, NC"]})])
    assert unknown.search(state="NC", explicit_only=True)["total"] == 1
    assert unknown.search(state="North Carolina", explicit_only=True)["total"] == 0
    assert unknown.search(country="美国", state="NC", explicit_only=True)["total"] == 0


def test_final_p2_state_full_name_alone_does_not_make_a_us_city():
    tbilisi = V.location_of({"cities": ["Tbilisi, Georgia"]})
    assert tbilisi["locations"] == [{"country": "", "state": "Georgia", "city": "Tbilisi"}] and tbilisi["region"] == ""
    assert V.location_of({"cities": ["Raleigh, North Carolina"]})["countries"] == []          # no US evidence
    assert V.location_of({"cities": ["Atlanta, Georgia, USA"]})["locations"] == \
        [{"country": "美国", "state": "Georgia", "city": "Atlanta"}]                                # explicit USA
    assert V.location_of({"cities": ["Seattle, Washington"]})["locations"] == \
        [{"country": "美国", "state": "Washington", "city": "西雅图"}]                              # known US city
    assert V.location_of({"cities": ["Atlanta, GA"]})["countries"] == ["美国"]                  # US state code
