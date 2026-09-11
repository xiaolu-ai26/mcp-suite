import json
from datetime import date

import pytest

from _mcp_harness import JOBS_PATH, TMP, TODAY, Server

BENCH_FIXTURE = {
    "data_as_of": "2026-09-03", "taxonomy": {"topic_category": ["AI工具"]},
    "records": [
        {"id": "a", "url": "https://example.org/a", "platform": "小红书", "note_type": "图文",
         "title": "标题A", "published_at": "2026-08-01", "topic_category": "AI工具",
         "title_formula": "数字清单+必备感", "observed_at": "2026-09-01", "tagging": {"mode": "ai_filled"}},
        {"id": "c", "url": "https://example.org/c", "platform": "抖音", "note_type": "视频",
         "title": "标题C", "published_at": "", "topic_category": "AI变现", "observed_at": "2026-09-03",
         "tagging": {"mode": "url_only"}},
    ],
}

needs_data = pytest.mark.skipif(not JOBS_PATH.is_file(), reason=f"{JOBS_PATH} missing (copy the 2026-09-11 jobs.json)")


@pytest.fixture(scope="session")
def qz():
    if not JOBS_PATH.is_file():
        pytest.skip(f"{JOBS_PATH} missing")
    server = Server("qiuzhao").start()
    yield server
    server.stop()


@pytest.fixture(scope="session")
def bench_server():
    TMP.mkdir(parents=True, exist_ok=True)
    path = TMP / "bench-fixture.json"
    path.write_text(json.dumps(BENCH_FIXTURE, ensure_ascii=False))
    server = Server("bench", bench_path=path).start()
    yield server
    server.stop()
    path.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def raw_rows():
    if not JOBS_PATH.is_file():
        pytest.skip(f"{JOBS_PATH} missing")
    return json.loads(JOBS_PATH.read_text())


@pytest.fixture(scope="session")
def jobs_inproc():
    """The same Jobs the server builds, in-process, with the harness's fixed today."""
    if not JOBS_PATH.is_file():
        pytest.skip(f"{JOBS_PATH} missing")
    from qiuzhao.tools import Jobs
    jobs = Jobs(JOBS_PATH, today=date.fromisoformat(TODAY))
    jobs.dataset()
    return jobs
