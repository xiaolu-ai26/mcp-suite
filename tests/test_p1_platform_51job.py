"""Fixture tests for the 51job corporate campus micro-site adapter.

The fixtures are the recorded public pages: ``51job_pepsico.html`` is a
server-rendered posting list (three application anchors) and
``51job_adidas_no_list.html`` is a landing page that carries no posting anchor.
No live page is fetched here.
"""
import json
from pathlib import Path

from qiuzhao.collector import p1_platform_51job as job51

FIXTURES = Path(__file__).parent / 'fixtures' / 'platform'


def page(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


def run(company, scope, tmp_path, html=None, calls=None):
    html = page('51job_pepsico.html') if html is None else html
    seen = calls if calls is not None else []

    def fake_get(session, url, budget):
        if budget is not None:
            if budget['limit'] is not None and budget['used'] >= budget['limit']:
                raise job51.BudgetExhausted('reached')
            budget['used'] += 1
        seen.append(url)
        return html

    original = job51._get
    job51._get = fake_get
    try:
        return job51.collect(company, scope, tmp_path)
    finally:
        job51._get = original


def test_recorded_micro_site_lists_official_postings(tmp_path):
    result = run('百事', 'campus', tmp_path)
    coverage = result['coverage']
    assert coverage['status'] == 'success' and coverage['complete'] is True
    assert coverage['expected_total'] == 3
    titles = [job['job_title'] for job in result['jobs']]
    assert titles == ['综合管理培训生', '供应链管理培训生', '农业培训生']
    urls = [job['source_url'] for job in result['jobs']]
    assert urls == ['https://xyz.51job.com/External/Apply.aspx?CtmID=9549063',
                    'https://xyz.51job.com/External/Apply.aspx?CtmID=9549079',
                    'https://xyz.51job.com/External/Apply.aspx?CtmID=9549088']
    first = result['jobs'][0]
    # The announcement carries no dates and no cohort, so they stay blank.
    assert first['published_at'] == '' and first['deadline_raw'] == ''
    assert first['cohort_raw'] == ''
    assert first['campaign_cohort_raw'] == '百事集团2027校园招聘'
    assert first['description_source'] == 'official announcement micro-site text'
    assert '综合管理培训生' in first['description_raw']


def test_landing_page_without_application_anchor_is_blocked(tmp_path):
    result = run('百事', 'campus', tmp_path, html=page('51job_adidas_no_list.html'))
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'blocked'
    assert any('CtmID' in error for error in result['coverage']['errors'])


def test_scope_without_a_micro_site_page_is_empty_success(tmp_path):
    calls = []
    result = run('百事', 'intern', tmp_path, calls=calls)
    assert calls == []                          # never fetches a page that cannot exist
    assert result['jobs'] == []
    assert result['coverage']['status'] == 'success'
    assert 'campus' in result['coverage']['note']


def test_budget_is_honoured(tmp_path):
    """A one-request budget still yields a partial-but-usable single GET."""
    result = run('百事', 'campus', tmp_path)
    assert result['coverage']['request_budget']['used'] == 1


def test_real_config_registers_only_verified_sites():
    assert job51.COMPANIES['pepsico2027'] == '百事'
    assert job51.merged_registry()['百事'] == 'qiuzhao.collector.p1_platform_51job'
    assert job51.resolve('百事') == 'pepsico2027'
    assert job51.site_url('pepsico2027') == 'https://campus.51job.com/pepsico2027/'


def test_postings_are_deduplicated_by_application_id(tmp_path):
    html = page('51job_pepsico.html')
    duplicated = html + html
    result = run('百事', 'campus', tmp_path, html=duplicated)
    ids = [job['source_record_id'] for job in result['jobs']]
    assert len(ids) == len(set(ids)) == 3


# --- evidence is only this call's official responses (2026-09-24: 9 units rejected) -------
import pytest

from qiuzhao.collector import p1_pipeline as P


def validate(result, tmp_path):
    return P.validate_result(result, '百事', 'campus', tmp_path)


@pytest.mark.parametrize('log', ['', 'adapter started\n'])
def test_the_pipeline_log_is_never_listed_as_evidence(tmp_path, log):
    (tmp_path / 'adapter.log').write_text(log)  # collect_process opens it before the adapter runs
    result = run('百事', 'campus', tmp_path)
    assert result['coverage']['evidence_files'] == ['pepsico2027-list-1.html']
    assert result['coverage']['evidence'] == result['coverage']['evidence_files']
    validated = validate(result, tmp_path)
    assert validated['coverage']['complete'] is True and len(validated['jobs']) == 3


def test_files_of_earlier_attempts_are_not_listed(tmp_path):
    for name, body in [('pepsico2027-list-mobile.html', '<html>old</html>'), ('result.json', '{}'),
                       ('validated.json', '{}'), ('timeout-cleanup.json', '{}')]:
        (tmp_path / name).write_text(body)
    result = run('百事', 'campus', tmp_path)
    assert result['coverage']['evidence_files'] == ['pepsico2027-list-1.html']


def test_a_fetched_mobile_page_is_listed_with_the_landing_page(tmp_path, monkeypatch):
    entry = dict(job51._entry('pepsico2027'), mobile_path='m/list')
    monkeypatch.setattr(job51, '_entry', lambda key: entry)
    pages = iter([page('51job_adidas_no_list.html'), page('51job_pepsico.html')])
    monkeypatch.setattr(job51, '_get', lambda session, url, budget: next(pages))
    (tmp_path / 'adapter.log').write_text('')
    result = job51.collect('百事', 'campus', tmp_path)
    assert result['coverage']['evidence_files'] == ['pepsico2027-list-1.html', 'pepsico2027-list-mobile.html']
    assert len(validate(result, tmp_path)['jobs']) == 3


@pytest.mark.parametrize('damage', ['missing', 'empty'])
def test_missing_or_empty_official_response_still_fails_closed(tmp_path, damage):
    result = run('百事', 'campus', tmp_path)
    target = tmp_path / 'pepsico2027-list-1.html'
    if damage == 'missing':
        target.unlink()
    else:
        target.write_text('')
    with pytest.raises(ValueError, match='nonempty current scope'):
        validate(result, tmp_path)


# --- generic application buttons and shared application forms (2026-09-24 saved pages) -----
import hashlib

# Verbatim official pages saved by run 20260924 (p1-runs/20260924T013005/<unit>/campus/), read
# with universal newlines (line ends as LF); the saved files' own sha256 are noted.
# ENGEL engel2027-list-1.html (file sha256 d3c2c74c...): one "投递申请" button, CtmID 9528969,
# under a free-form programme description; the old parser made that label a job title.
ENGEL_SAVED = """<!DOCTYPE html>


<html>





<head>


  <title>ENGEL中国2027届校园招聘</title>


  <meta content="FIRST OF ALL：智塑无界 链接未来" name="description" />


  <meta content="FIRST OF ALL：智塑无界 链接未来" name="keywords" />


  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />


  <meta name="viewport"


content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0" />


  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />


  <meta http-equiv="Pragma" content="no-cache" />


  <meta http-equiv="Expires" content="0" />


  <meta name="viewport" content="width=1280">


  <meta name="format-detection" content="telephone=no">


  <meta http-equiv="X-UA-Compatible" content="IE=edge" />


  <meta http-equiv="cache-control" content="no-cache">


  <meta name="robots" content="all" />


  <!--相对路径代码 -->


  <link href="css/reset.min.css" rel="stylesheet" type="text/css">


  <link href="css/style.css" rel="stylesheet" type="text/css">


  <!--swiper轮播-->


  <link rel='stylesheet' href='https://campus.51job.com/51job-ideal-cdn/swiper/2022d5d2d0/swiper.min.css'>


  <!--swiper轮播-->


  <script src="https://res.wx.qq.com/open/js/jweixin-1.6.0.js"></script>


  <script type='text/javascript' src='https://campus.51job.com/51job-ideal-cdn/ienv/2022d1d1d5/ienv.min.js'></script>


  <script type='text/javascript' src='https://campus.51job.com/51job-ideal-cdn/jquery/2022d1d12d4/jquery.min.js'>


  </script>


</head>





<body>


  <div id="wrap">


<div class="banner">


  <!-- <img src="./images/logo.png" class="logo" alt=""> -->


  <div class="swiper">


    <div class="swiper-wrapper">


      <div class="swiper-slide"><img src="./images/banner.png" alt=""></div>


      <div class="swiper-slide"><img src="./images/banner1.jpg" alt=""></div>


      <div class="swiper-slide"><img src="./images/banner2.jpg" alt=""></div>


      <div class="swiper-slide"><img src="./images/banner3.jpg" alt=""></div>


      <div class="swiper-slide"><img src="./images/banner4.jpg" alt=""></div>


      <div class="swiper-slide"><img src="./images/banner5.jpg" alt=""></div>





      <div class="swiper-slide"><img src="./images/banner6.gif" alt=""></div>


    </div>


  </div>


</div>


<div class="main">


  <!-- <div class="main_bg1"></div>


<div class="main_bg2" style="top: auto;bottom: 20%;"></div>


<div class="main_bg3"></div> -->


  <div class="w">


    <div class="content">


      <ul class="nav">


        <li><a href="about.html"><span>01 About Us</span><span>集团介绍</span></a></li>


        <li><a href="engel.html"><span>02 ENGEL CHINA</span><span>ENGEL中国</span></a></li>


        <li class="on"><a href="introduction.html"><span>03 recruiting</span><span>校招介绍</span></a></li>


      </ul>


      <div class="inner">


        <div class="nav2">


          <a href="introduction.html" class="on  on1">职位介绍</a>


          <a href="introduction1.html">福利介绍</a>


          <!-- <a href="introduction2.html">校招地图</a> -->


          <a href="introduction3.html">了解更多</a>


        </div>


        <div class="about">


          <div class="jobtit"><b>技术培训生</b><img src="./images/i19.png" alt=""></div>


          <div class="about_info" style="padding-top: 0;">


            <p class="p" style="margin-bottom: 10px;"><b>清晰定位适合的技术岗位</b></p>


            <div class="about_list" style="background:none; width: 75%;"><img src="./images/x1.png"


                alt="">量身定制的24个月培训计划</div>


            <div class="about_list" style="background:none;width: 75%;"><img src="./images/x2.png"


                alt="">技术导师+HR全程护航，实现学生到职场人的无缝过渡</div>


            <div class="about_list mb40" style="background:none;width: 75%;"><img src="./images/x3.png"


                alt="">拥有广阔多元的职业发展空间</div>


            <p class="p mb0"><b>需求专业</b></p>


            <p class="mb40"><br>机械设计及其自动化、机械电子工程、电气工程及其自动化、流动与力学、<br>


              过程装备与控制工程、自动化、软件工程、高分子材料与工程、无机非金属材料工程等相关专业。</p>


            <p class="p mb0"><b>工作城市</b></p>


            <p class="mb40">上海/常州</p>


            <p class="p mb0"><b>未来定岗的方向</b></p>


            <p class="mb40">注塑机技术、注塑机供应链、注塑机销售、注塑工艺及应用</p>


            <p class="p mb0"><b>定岗工作地</b></p>


            <p class="mb40">上海 / 北京 / 深圳 / 常州</p>


            <a class="btn" href="https://xyz.51job.com/External/Apply.aspx?CtmID=9528969" target="_blank"


              rel="noopener noreferrer">投递申请</a>


          </div>





          <img src="images/b3.png" alt="" class="bbbb">


        </div>


        <!-- <div class="btn">


        <span>ENGEL上海  技术培生</span>


        <span><img src="./images/i17.png" alt="">工作地：上海</span>


        <a href="" target="_blank" rel="noopener noreferrer">投&nbsp;&nbsp;&nbsp;&nbsp;递</a>


      </div>


      <div class="btn">


        <span>ENGEL常州 技术培训生</span>


        <span><img src="./images/i17.png" alt="">工作地：常州</span>


        <a href="" target="_blank" rel="noopener noreferrer">投&nbsp;&nbsp;&nbsp;&nbsp;递</a>


      </div> -->


      </div>


    </div>


  </div>


</div>


<!-- 主体区域end -->


<!--版权信息区域-->


<div class="copyright">&nbsp;未经51job.com同意，不得转载本网站之所有招聘信息及作品；无忧工作网版权所有&copy;1999-


  <script>


    document.write((new Date()).getFullYear())


  </script>


</div>


<!--版权信息区域end-->


  </div>


  <!--职位数据接口-->


  <!--<script type="text/javascript" src="https://js.51jobcdn.com/in/js/2018/coapi/coapi.min.js"></script>-->


  <!--职位数据接口-->


  <!--swiper轮播-->


  <script type='text/javascript'


src='https://campus.51job.com/51job-ideal-cdn/swiper/2022d5d2d0/swiper.min.js'></script>


  <!--swiper轮播-->


  <script type="text/javascript" src="js/main.js"></script>


  <script type="text/javascript">


  </script>


</body>





</html>"""
ENGEL_SAVED_TEXT_SHA256 = '2d1b83bdbfc8098bfa0bd59cb4dc941d7f48f03d663f6b6dd7c4c5d073915b85'
# 马夸特 marquardt-list-1.html (file sha256 b7f976cd...): real titles as link texts in div
# slides, four of them on the same application form CtmID 6071810.
MARQUARDT_SAVED = """<!DOCTYPE html>


<html>





<head>


  <!-- 制作人信息 -->


  <!-- 是否使用数据接口：否 -->


  <!-- JTNDIS0tUE06JTVCJUU1JUFEJTk5JUU2JUFGJTg1JTVEJTIwRGVzaWduZXI6JTVCeHh4JTVEJTIwRGV2ZWxvcGVyOiU1QiVFOSU4MiVCMSVFNSU4NSVCNCVFNSU5RiVCOSU1RCUyMGRhdGU6MjAyMTEwMTUtLSUzRQ== -->


  <title>马夸特上海2022校园招聘</title>


  <meta content="***校园招聘 前程无忧官方网站，提供最新***校园招聘职位，校园招聘信息，***面试技巧等。帮助您顺利踏入***的大门，与众多***精英们开启一段崭新的职业生涯。" name="description">


  <meta content="人才，招聘，简历，工作，求职，面试，应聘，跳槽，高薪，兼职，猎头，薪酬，薪资，培训，测评，人事" name="keywords">


  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />


  <meta name="viewport"


    content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0" />


  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />


  <meta http-equiv="Pragma" content="no-cache" />


  <meta http-equiv="Expires" content="0" />


  <meta name="viewport" content="width=1280">


  <meta name="format-detection" content="telephone=no">


  <meta http-equiv="X-UA-Compatible" content="IE=edge" />


  <meta http-equiv="cache-control" content="no-cache">


  <meta name="robots" content="all" />








  <!--相对路径代码 -->


  <link href="css/reset.min.css" rel="stylesheet" type="text/css">


  <link href="css/style.css" rel="stylesheet" type="text/css">


  <link rel="stylesheet" href="css/swiper.min.css">


  <link rel="stylesheet" type="text/css" href="css/certify.css" />


  <link rel="stylesheet" href="css/main.css">


  <script type="text/javascript">


    if (/(iPhone|iPad|iPod|iOS|Android)/i.test(navigator.userAgent)) {


      // window.location.href = "./index.html";


    } else {


      // window.location.href = "http://campus.51job.com/marquardt";


    }


  </script>


  <style>


    /* 自定义分页器 */


    .swiper-pagination {


      position: absolute;


      text-align: center;


      -webkit-transition: .3s opacity;


      -o-transition: .3s opacity;


      transition: .3s opacity;


      -webkit-transform: translate3d(0, 0, 0);


      transform: translate3d(0, 0, 0);


      z-index: 10;


      text-align: center;


      width: 100%;


      margin: 0 4px;


      margin-top: 30px;


    }





    /* 自定义分页器 */


    .swiper-pagination1 {


      position: absolute;


      text-align: center;


      -webkit-transition: .3s opacity;


      -o-transition: .3s opacity;


      transition: .3s opacity;


      -webkit-transform: translate3d(0, 0, 0);


      transform: translate3d(0, 0, 0);


      z-index: 10;


      text-align: center;


      width: 100%;


      margin: 0 4px;


      margin-top: 30px;


    }





    /* 分页器的大小 */


    .swiper-pagination-bullet {


      width: 10px;


      height: 10px;


      border-radius: 50%;


      display: inline-block;


      opacity: .2;


      margin: 0 8px;


    }





    /* 颜色 */


    .swiper-pagination-bullet-active {


      opacity: 1;


      background: #215696;


      width: 40px;


      border-radius: 10px;


    }


  </style>


  <script>


    var sId = "c4ef9c39b300931b69a36fb3dbb8d60e";


    show = document.createElement("script");


    show.src = "//analysis.51family.com.cn/show.js?" + sId;


    var headElement = document.getElementsByTagName("head")[0];


    headElement.appendChild(show);


  </script>


</head>





<body ctmid="" baseUrl="" jobdata="js/main.js">





  <div id="wrap">


    <!--头部区域-->


    <div class="header">


      <div class="top">


        <div class="inner clearfix">


          <!-- logo -->


          <div class="logo">


            <img src="images/logo.png" alt="" />


          </div>


          <!-- logo end -->





          <!-- nav1 -->


          <ul class="nav1 clearfix">


            <li><a href="#t1" forCheck="nav" class="on">公司简介</a></li>


            <li><a href="#t2" forCheck="nav">公司产品</a></li>


            <li><a href="#t3" forCheck="nav">公司文化</a></li>


            <li><a href="#t4" forCheck="nav">核心价值</a></li>


            <li><a href="#t5" forCheck="nav">多元化剪影</a></li>


            <li><a href="#t6" forCheck="nav">职位介绍</a></li>


            <li><a href="#t7" forCheck="nav">招聘流程</a></li>


            <li><a href="#t8" forCheck="nav">公司官网</a></li>


          </ul>


          <!-- nav1 end -->


        </div>


      </div>


      <!-- banner -->


      <div class="banner">


        <img src="images/banner.jpg" alt="" />


      </div>


      <!-- banner end -->


    </div>


    <!--头部区域end-->


    <!-- 主体区域 -->


    <div class="main inner">





      <div class="clearfix">


        <!-- 内容区域 -->


        <div class="content">


          <div class="title" id="t1">


            <img src="./images/title1.png" alt="">


          </div>


          <div class="word">


            <p>


              <span>马夸特集团</span>


              是全球机电、电子开关和开关系统的领先制造商。在全球四个洲的20个地区设立分公司，员工超过10000人。在2021年，全球销售额达到了15.4亿欧元。马夸特集团每年将10%的营业额投入到创新研发中，以确保公司产品和市场竞争力。


            </p>


          </div>


          <div class="pic">


            <img src="./images/pic101.png" alt="">


          </div>


          <div class="pic">


            <img src="./images/pic102.png" alt="">


          </div>


          <div class="word">


            <p>


              全球化思维，本地化行动：马夸特开关（上海）有限公司于1996年成立，位于浦东合庆工业园区。截止到2021年底，马夸特中国已拥有1200多名员工，持续被评为合庆地区最佳雇主之一，并连续4年荣获由前程无忧颁发的“中国100典范雇主”称号。


            </p>


          </div>


          <div class="title" id="t2">


            <img src="./images/title2.png" alt="">


          </div>


          <div class="word">


            <p>


              作为机电一体化专家，汽车行业众多知名客户使用马夸特的产品，包括：操作部件、车辆接入、驾驶员授权系统和电池管理系统。马夸特的系统解决方案同样应用于家用电器、工业应用、电动工具和电动代步工具<span>（更多应用场景，请点击下方图标）</span>。


            </p>


          </div>


          <div class="hover">


            <div class="hv">


              <div class="pic">


                <img src="./images/icon1.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/1.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon2.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/2.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon3.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/3.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon4.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/4.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon5.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/5.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon6.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/6.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon7.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/7.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon8.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/8.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon9.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/9.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon10.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/10.jpg" alt="">


              </div>


            </div>


            <div class="hv">


              <div class="pic">


                <img src="./images/icon11.png" alt="">


              </div>


              <div class="tp center">


                <img src="./images/11.jpg" alt="">


              </div>


            </div>


            <div class="demo">


              <a href="https://ideal.chinaceotv.com/2021/mkthp15/mkt.mp4" target="_blank" class="apply">


                <div class="pic">


                  <img src="./images/icon12.png" alt="">


                </div>


              </a>


            </div>


          </div>


          <div class="title" id="t3">


            <img src="./images/title3.png" alt="">


          </div>


          <div class="word">


            <p>


              作为一家百年历史的家族企业，马夸特集团致力于成为具有吸引力的雇主并时刻反思。我们坚信是那些能为员工提供更多的机会和收获的公司，无论这些机会和收获是与员工个人或职业发展相关，还是能使每个个人的长处及能力得到充分发挥。因此，我们积极倡导：


            </p>


          </div>


          <div class="pic">


            <img src="./images/pic103.png" alt="">


          </div>


          <div class="title" id="t4">


            <div class="pic">


              <img src="./images/title4.png" alt="">


            </div>


          </div>


          <div class="pic">


            <img src="./images/pic104.png" alt="">


          </div>


          <div class="title" id="t5">


            <img src="./images/title5.png" alt="">


          </div>


          <div class="lb">


            <div class="swiper_fater" id="one">


              <div class="swiper-container">


                <div class="swiper-wrapper">


                  <div class="swiper-slide">


                    <img src="images/lb1 (1).jpg" />


                  </div>


                  <div class="swiper-slide">


                    <img src="images/lb1 (2).jpg" />


                  </div>


                  <div class="swiper-slide">


                    <img src="images/lb1 (3).JPG" />


                  </div>


                  <div class="swiper-slide">


                    <img src="images/lb1 (4).jpg" />


                  </div>


                  <div class="swiper-slide">


                    <img src="images/lb1 (5).jpg" />


                  </div>


                  <div class="swiper-slide">


                    <img src="images/lb1 (6).jpg" />


                  </div>


                </div>


              </div>


              <div id="title">


                <span></span>





                <span></span>


              </div>


              <div class="swiper-pagination"></div>


              <div class="swiper-button-prev"></div>


              <div class="swiper-button-next"></div>


            </div>


          </div>


          <div class="title" id="t6">


            <img src="./images/title8.png" alt="">


          </div>


          <div class="title">


            <h1>热招职位</h1>


          </div>


          <div class="job">


            <div class="job_name">


              <a href="https://xyz.51job.com/external/apply.aspx?jobid=139222482&ctmid=6071810" target="_blank"


                class="apply">


                <b>


                  质量部培训生（质量管理）


                </b>


              </a>


            </div>


            <div class="job_name">


              <a href="https://xyz.51job.com/external/apply.aspx?jobid=139222905&ctmid=6071810" target="_blank"


                class="apply">


                <b>


                  工程技术部培训生（软件工程）


                </b>


              </a>


            </div>


            <div class="job_name">


              <a href="https://xyz.51job.com/external/apply.aspx?jobid=139222836&ctmid=6071810" target="_blank"


                class="apply">


                <b>


                  工程技术部培训生（研发）


                </b>


              </a>


            </div>


            <div class="job_name">


              <a href="https://xyz.51job.com/external/apply.aspx?jobid=139222712&ctmid=6071810" target="_blank"


                class="apply">


                <b>


                  工业制造部培训生（工业制造）


                </b>


              </a>


            </div>














            <div class="center">


              <b style="color: #00ccdf;">点击职位名称投递简历</b>


            </div>


          </div>


          <div class="title">


            <h1>我们期待这样的你</h1>


          </div>


          <div class="word" style="width: 60%; text-align: center; margin: 0 auto;">


            <p style="text-indent: 0;"><span>理工类专业：</span>机械、电子信息、软件工程、机电一体化、电气类等</p>


            <!-- <p><img src="./images/fk.png" alt=""><span>文科类专业：</span>英语或语言类、人力资源及社会保障， 物流管理，国际经济与贸易</p> -->


          </div>


          <div class="title">


            <h1>工作地点</h1>


          </div>


          <div class="box center" style="width: auto; padding: 15px 20px;">


            <span>上海浦东</span>


          </div>


          <div class="title">


            <h1>你将获得</h1>


          </div>


          <div class="pic">


            <img src="./images/pic105.png" alt="">


          </div>


          <div class="title" id="t7">


            <img src="./images/title6.png" alt="">


          </div>


          <div class="pic">


            <img src="./images/pic106.png" alt="">


          </div>


          <!-- <div class="pic">


            <a href="http://xyz.51job.com/External/Apply.aspx?CtmID=5805454" target="_blank" class="apply">


              <img src="./images/pic107.png" alt="">


            </a>


          </div> -->


          <!-- <div class="title">


            <h1>活动预告</h1>


          </div>


          <div class="box center" style="width: auto; padding: 15px 20px;">


            <span>马夸特星际校招之旅 10月16日</span>


          </div>


          <div class="word">


            <p><span>


                突破每个关卡的成功都能为你们储备相应的能量值，获取通往下一个没有硝烟的经济战场的钥匙，成为终极赢家, 得到神秘大奖！





              </span></p>


          </div>


          <div class="pic">


            <a href="https://lemy-h5.top/MSC/" target="_blank" class="apply" class="gw">


              <img src="./images/erweima1.png" alt="">


            </a>


          </div> -->


          <div class="box center" style="width: auto; padding: 15px 20px;">


            <span>网申通道</span>


          </div>


          <div class="pic">


            <img src="./images/ws_qrcode.png" alt="">


          </div>


          <div class="box center" style="width: auto; padding: 15px 20px;">


            <span>空中宣讲会</span>


          </div>


          <div class="pic">


            <a href="https://video.51job.com/watch/2605832" target="_blank" class="apply">


              <img src="./images/erweima2.png" alt="">


            </a>


          </div>


          <!-- <div class="box center" style="width: auto; padding: 15px 20px;">


            <span>沉浸式谈判竞技类活动 11月13日</span>


          </div>


          <div class="word center">


            <p><span>


                在没有硝烟的经济战场上，你是主导一切，还是崇尚合作？你是深谋远虑，还是步步为营？我们拭目以待… …


              </span></p>


            <p class="center"><span>


                活动细节将持续更新，敬请期待！


              </span></p>


          </div> -->


          <div class="pic">


            <img src="./images/pic108.png" alt="">


          </div>


          <div class="title" id="t8">


            <img src="./images/title7.png" alt="">


          </div>


          <div class="word">


            <p><span>欢迎访问公司网站：</span>https://www.marquardt.com</p>


          </div>


        </div>


        <!-- 内容区域end -->


      </div>


    </div>


    <!-- 主体区域end -->








    <!--版权信息区域-->


    <div class="copyright">


      <img src="images/hand.png" />&nbsp;未经51job.com同意，不得转载本网站之所有招聘信息及作品；无忧工作网版权所有&copy;1999-<script>


        document.write((new Date()).getFullYear())


      </script>


    </div>


    <!--版权信息区域end-->








  </div>





  <script type="text/javascript" src="js/jquery-1.12.3.min.js"></script>


  <script src="js/trackPrd.js"></script>





  <!--swiper轮播-->


  <script type="text/javascript" src="js/swiper.js"></script>


  <!--swiper轮播-->





  <!--页面滚动内容元素动画特效-->


  <script type="text/javascript" src="js/jquery.smoove.js"></script>


  <!--页面滚动内容元素动画特效-->


  <!-- 微信分享图片 -->


  <!--<script src="https://sdk.51job.com/js/jweixin-1.0.0.js"></script>-->





  <script type="text/javascript" src="js/main.js"></script>


  <script type="text/javascript">


    $('.hv').mouseover(function () {


      $(this).find('.pic img').css('display', 'none')


      $(this).find('.tp').css('display', 'block')


    })


    $('.hv').mouseout(function () {


      $(this).find('.pic img').css('display', 'block')


      $(this).find('.tp').css('display', 'none')





    })


  </script>


  <script>


    // const titleList = ['沌口六村项目','苏州湾文化中心','汉南厂','郑州博物馆','重庆西工大EPC项目','纱帽八村项目'];


    var swiper = new Swiper('#one .swiper-container', {


      //重置Swiper监听器


      observer: true,


      observeParents: true,


      //切换效果   3d流


      effect: 'coverflow',


      //显示的数量


      slidesPerView: 2,


      //为true默认居中 默认居左


      centeredSlides: true,


      coverflowEffect: {


        //3d旋转角度


        rotate: 0,


        //每个slide之间的拉伸，越大靠的越紧


        stretch: 20,


        //深度值，越大距离越远，看起来越小


        depth: 100,


        //值越大，效果越明显


        modifier: 3,


        //是否开启阴影


        slideShadows: false,


      },


      //环路 循环播放


      loop: true,


      // 分页器


      pagination: {


        el: '.swiper-pagination',


        // 点击分页器切换


        clickable: true,


      },


      //自动播放和暂停


      autoplay: {


        stopOnLastSlide: false,


        disableOnInteraction: false,


      },


      //左右箭头


      navigation: {


        nextEl: '.swiper-button-next',


        prevEl: '.swiper-button-prev',


      }


    });


    /*外链*/


    document.querySelector('.gw').addEventListener('click', function (e) {


      e.preventDefault();


      if (window.confirm('您即将离开前程无忧官方招聘网站，前往第三方页面。是否确认前往？')) {


        window.location.href = "https://lemy-h5.top/MSC/"


      } else {


        return false


      }


    })


  </script>


</body>





</html>"""
MARQUARDT_SAVED_TEXT_SHA256 = '6d9078a4d58ea43078793d8d2c36daafe340dc7c5134e7e35f4c7cd5e988d479'


def test_embedded_pages_are_the_recorded_official_responses():
    assert hashlib.sha256(ENGEL_SAVED.encode('utf-8')).hexdigest() == ENGEL_SAVED_TEXT_SHA256
    assert hashlib.sha256(MARQUARDT_SAVED.encode('utf-8')).hexdigest() == MARQUARDT_SAVED_TEXT_SHA256


def test_engel_generic_application_button_is_not_a_job(tmp_path):
    (tmp_path / 'adapter.log').write_text('')
    result = run('ENGEL', 'campus', tmp_path, html=ENGEL_SAVED)
    coverage = result['coverage']
    assert result['jobs'] == [] and coverage['status'] == 'blocked' and coverage['complete'] is False
    assert coverage['application_link_problems'] == [
        {'ctm_id': '9528969', 'text': '投递申请', 'reason': 'generic application button, not a posting title'}]
    assert any('9528969' in error for error in coverage['errors'])
    assert coverage['evidence_files'] == ['engel2027-list-1.html']  # the official page stays as evidence
    validated = P.validate_result(result, 'ENGEL', 'campus', tmp_path)
    assert validated['coverage']['status'] == 'blocked' and validated['jobs'] == []


def test_marquardt_real_title_in_div_layout_is_kept_but_not_claimed_complete(tmp_path):
    (tmp_path / 'adapter.log').write_text('')
    result = run('马夸特', 'campus', tmp_path, html=MARQUARDT_SAVED)
    coverage = result['coverage']
    assert [j['job_title'] for j in result['jobs']] == ['质量部培训生（质量管理）']
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    [problem] = coverage['application_link_problems']
    assert problem['ctm_id'] == '6071810' and len(problem['titles']) == 4
    validated = P.validate_result(result, '马夸特', 'campus', tmp_path)
    assert [j['job_title'] for j in validated['jobs']] == ['质量部培训生（质量管理）']
    assert validated['coverage']['status'] == 'partial'


LIST = '<ul>{}</ul>'
ITEM = ('<li><p>{title}</p><a href="https://xyz.51job.com/External/Apply.aspx?CtmID={ctm}">'
        '点击投递</a></li>')


def test_real_titles_that_contain_apply_words_are_kept(tmp_path):
    html = LIST.format(ITEM.format(title='申请专员（投递中心）', ctm=101)
                       + '<li><a href="https://xyz.51job.com/External/Apply.aspx?CtmID=102">'
                         '投递管理培训生</a></li>')
    result = run('百事', 'campus', tmp_path, html=html)
    assert [j['job_title'] for j in result['jobs']] == ['申请专员（投递中心）', '投递管理培训生']
    assert result['coverage']['complete'] is True and 'application_link_problems' not in result['coverage']


def test_a_generic_button_next_to_a_real_list_keeps_the_postings_but_not_completeness(tmp_path):
    html = (LIST.format(ITEM.format(title='综合管理培训生', ctm=201))
            + '<div><a class="btn" href="https://xyz.51job.com/External/Apply.aspx?CtmID=202">投递申请</a></div>')
    result = run('百事', 'campus', tmp_path, html=html)
    coverage = result['coverage']
    assert [j['job_title'] for j in result['jobs']] == ['综合管理培训生']
    assert coverage['status'] == 'partial' and coverage['complete'] is False
    assert len(P.validate_result(result, '百事', 'campus', tmp_path)['jobs']) == 1


# --- four saved page templates the parser misreads are quarantined (review 2026-09-24) -------
import copy

# 英格索兰 IR2027-list-1.html (file sha256 563b92b4...), same run: the parser returned
# "英语CET-6或以上。 工作城市 上海、山东淄博" as a title and claimed the listing complete.
IR_SAVED = """<!DOCTYPE html>





<html lang="en">





<head>


  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />


  <meta name="viewport" content="width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,user-scalable=no" />


  <title>【英格索兰2027校园招聘】</title>


  <meta content="英格索兰（中国）投资有限公司校园招聘 前程无忧官方网站，提供最新校园招聘职位，校园招聘信息，面试技巧等。帮助您顺利踏入的大门，与众多精英们开启一段崭新的职业生涯。"


    name="description" />


  <meta content="人才，招聘，简历，工作，求职，面试，应聘，跳槽，高薪，兼职，猎头，薪酬，薪资，培训，测评，人事" name="keywords" />


  <meta http-equiv="expires" content="0" />


  <meta http-equiv="pragma" content="no-cache" />


  <meta http-equiv="cache-control" content="no-cache" />


  <meta name="format-detection" content="telephone=no" />


  <meta name="robots" content="all" />


  <meta name="viewport" content="width=1280" />


  <meta http-equiv="cache-control" content="no-siteapp" />


  <meta name="render" content="webkit|ie-comp|ie-stand" />


  <meta http-equiv="x-ua-compatible" content="IE=edge,chrome=1" />


  <link rel="stylesheet" href="./css/reset.css" />


  <link rel="stylesheet" href="./css/common.css" />


  <link rel="stylesheet" href="./css/about.css" />


</head>





<body>


  <!-- 顶部 -->


  <div class="banner">


    <img class="img100" src="./images/banner.png" alt="" />


  </div>


  <!-- 中部 -->


  <div class="bgcontainer">


    <div class="header" id="top">


      <ul class="nav">


        <li>


          <a href="./about.html#top">了解英格索兰</a>


        </li>


        <li class="actived">


          <a href="./job.html#top">加入英格索兰</a>


        </li>


        <li>


          <a href="./talents.html#top">人才体系</a>


        </li>


        <li>


          <a href="./process.html#top">招聘流程</a>


        </li>


        <li>


          <a href="./qa.html#top">Q&A</a>


        </li>


      </ul>


    </div>


    <div class="details">


      <!-- 总览 -->


      <div class="content">


        <div class="title">


          <p>招聘职位</p>


        </div>


        <div class="job">


          <h1>英格索兰星锐扬帆计划</h1>


          <hr />


          <p>旨在为研发、市场部门<br />培养技术专业人才及未来领导者</p>


        </div>


        <img src="./images/p4.png" />


        <div class="job_info">


          <p class="gw">招聘岗位</p>


          <p>产品研发工程师、市场产品管理专员</p>


          <p class="gw jl">岗位要求</p>


          <li class="font14">


            2027年应届毕业生；同时欢迎具有二年以内工作经验的候选人；


          </li>


          <li class="font14">


            主修机械、动力工程及工程热物理、热能与动力工程、流体、真空泵、过程装备与控制工程、航天工程、自动化、电气等理工科专业；


          </li>


          <li class="font14">


            富有创新精神，具有强烈的主人翁精神，善于思辨且学习能力优秀，有志于长期从事技术或市场产品管理工作；


          </li>


          <li class="font14">英语CET-6或以上。</li>


          <p class="gw jl">工作城市</p>


          <p class="font14">上海、山东淄博</p>


          <a href="https://xyz.51job.com/External/Apply.aspx?CtmID=9519383" class="apply"><img


              src="./images/btn.png" /></a>


          <img src="./images/mark1.png" class="mark mark1" />


          <img src="./images/mark4.png" class="mark mark4" />


        </div>


        <div class="job">


          <h1>英格索兰销售新星培养计划</h1>


          <hr class="hr1" />


          <p>


            旨在为不断增长的业务需求<br />


            与不断变化的市场环境<br />


            储备未来销售精英、培养技术支持专家<br />


            成就销售与技术强强结合的顾问式销售团队


          </p>


        </div>


        <img src="./images/p5.png" style="margin: 0 auto" />


        <div class="job_info">


          <p class="gw">招聘岗位</p>


          <p>销售工程师、产品应用工程师</p>


          <p class="gw jl">岗位要求</p>


          <li class="font14">


            2027年应届毕业生，同时欢迎具有二年以内工作经验的候选人；


          </li>


          <li class="font14">


            主修机械、能源、暖通、自动化、流体、真空、过程装备与控制工程等理工科专业；


          </li>


          <li class="font14">英语CET-4或以上；接受区域内出差；</li>


          <li class="font14">


            较强的人际交往能力和抗压力，勤思考重结果，对于长期从事销售工作充满热情。


          </li>


          <!-- <li class="font14">英语CET-4或以上；接受区域内出差；</li>


          <li class="font14">较强的人际交往能力和抗压能力、勤思考重结果、对于长期从事销售工作充满热情。</li> -->


          <p class="gw jl">工作城市</p>


          <p class="font14">


            上海、北京、广州、深圳、天津、苏州、杭州、无锡、西安、武汉、重庆、成都、石家庄、昆明、合肥


          </p>


          <a href="https://xyz.51job.com/External/Apply.aspx?CtmID=9519383" class="apply"><img


              src="./images/btn.png" /></a>


        </div>


      </div>


    </div>


    <div class="footer">


      <p>


        未经51job.com 同意，不得转载本网站之所有招聘信息及作品


        ；无忧工作网版权所有 ©1999-


        <script>


          document.write(new Date().getFullYear());


        </script>


      </p>


    </div>


  </div>


  <script src="./src/jquery.min.js"></script>


  <script src="./js/common.js"></script>


</body>





</html>"""
IR_SAVED_TEXT_SHA256 = 'b7d3b7a5cb818e383aa54a8fd7d30f4d4a4041b1b8741a5e2fb238698bed365b'


def test_quarantine_is_pinned_to_the_four_reviewed_sources():
    assert hashlib.sha256(IR_SAVED.encode('utf-8')).hexdigest() == IR_SAVED_TEXT_SHA256
    assert {key: url for key, (url, _) in job51.QUARANTINED_TEMPLATES.items()} == {
        'DellEmc': 'https://campus.51job.com/DellEmc/', 'te': 'https://campus.51job.com/te/p2.html',
        'Covestro2027': 'http://campus.51job.com/Covestro2027/job.html',
        'IR2027': 'https://campus.51job.com/IR2027/job.html#top'}
    for key, (url, _) in job51.QUARANTINED_TEMPLATES.items():
        assert job51.site_url(key) == url  # the configured source is exactly the reviewed one


def test_ingersoll_saved_page_yields_no_job_and_no_completeness(tmp_path):
    (tmp_path / 'adapter.log').write_text('')
    result = run('英格索兰', 'campus', tmp_path, html=IR_SAVED)
    coverage = result['coverage']
    assert result['jobs'] == [] and '英语CET-6' not in json.dumps(result['jobs'], ensure_ascii=False)
    assert coverage['status'] == 'blocked' and coverage['complete'] is False and coverage['detail_complete'] is False
    assert coverage['template_quarantine']['key'] == 'IR2027'
    assert any('IR2027 quarantined' in error for error in coverage['errors'])
    assert coverage['evidence_files'] == ['IR2027-list-1.html'] and (tmp_path / 'IR2027-list-1.html').read_text() == IR_SAVED
    validated = P.validate_result(result, '英格索兰', 'campus', tmp_path)
    assert validated['coverage']['status'] == 'blocked' and validated['jobs'] == []
    # The pipeline's merge skips a blocked unit: an earlier 英格索兰 row is neither changed nor retired.
    earlier = {'id': 'p1-ir-earlier', 'job_title': '产品研发工程师', 'p1_company': '英格索兰',
               'p1_scope': 'campus', 'status': 'open'}
    merged, changes = P.merge_records([copy.deepcopy(earlier)], [('英格索兰', 'campus', validated)])
    assert merged == [earlier] and changes['removed'] == 0 and changes['added'] == 0


@pytest.mark.parametrize('company', ['易安信', '泰科电子 (TE Connectivity）', '科思创'])
def test_the_other_quarantined_sources_produce_no_row_even_from_a_clean_list(tmp_path, company):
    result = run(company, 'campus', tmp_path, html=LIST.format(ITEM.format(title='研发工程师', ctm=301)))
    coverage = result['coverage']
    assert result['jobs'] == [] and coverage['status'] == 'blocked' and coverage['complete'] is False
    assert coverage['template_quarantine']['key'] == job51.resolve(company)


def test_a_quarantined_key_with_another_configured_url_is_parsed_normally(tmp_path, monkeypatch):
    entry = dict(job51._entry('IR2027'), url='https://campus.51job.com/IR2028/job.html')
    monkeypatch.setattr(job51, '_entry', lambda key: entry)
    result = run('英格索兰', 'campus', tmp_path, html=LIST.format(ITEM.format(title='产品研发工程师', ctm=401)))
    assert [j['job_title'] for j in result['jobs']] == ['产品研发工程师']
    assert 'template_quarantine' not in result['coverage'] and result['coverage']['complete'] is True


def test_other_sources_are_never_quarantined():
    others = [key for key in job51.COMPANIES if key not in job51.QUARANTINED_TEMPLATES]
    assert others and all(job51.quarantine_reason(key, job51.site_url(key)) is None for key in others)
    assert job51.quarantine_reason('te', 'https://campus.51job.com/te/') is None
