# 收据：闲鱼公司表 ATS 租户批量接入（Moka / 北森 / 飞书招聘）

> 生成时间：2026-09-18T09:54:36+00:00（UTC）  
> 分支：`feat/xianyu-slugs`（基于 `feat/banks-batch1`）；**未部署、未 push、未合并、未写任何生产库/精灵**。  
> 只读：飞书 Base 用 `lark-cli` 只读分页；适配器全部只读采集，未登录、未绕过验证码/签名、未写库。  

## 1. 结论（TL;DR）

- 闲鱼主表全量 **7801** 条（去重后，未见重复行）；提取出 ATS 租户：北森 701、Moka 457、飞书 138、大易 47、其他域名 1204 个。
- 与库内公司名去重后实测：**成功/部分且 ≥1 条岗位 → 写入配置 842 家**；被拒 248 家；库内已有跳过 206 家。
- 分平台加入：北森(zhiye.com) 473 家, Moka(mokahr.com) 298 家, 飞书招聘(jobs.feishu.cn) 71 家。
- 飞书招聘已配置化：`p1_feishu_public.py` 新增 `feishu` 段读取与 `merged_registry()`，`p1_pipeline.py` 仅追加一个独立注册块（`setdefault`，不覆盖硬编码/已注册公司）。
- 大易与「其他」域名仅输出清单（见 `xianyu-ats-others.json`），不做适配器。

## 2. 方法与口径

- 全表拉取：`lark-cli base +record-list --format ndjson`，每页 2000 条、页间隔 1s，共 4 页（2000/2000/2000/1801），未修改该表。
- 链接提取：扫描每条记录所有字段中的 `http(s)://`；按域名归类 mokahr / zhiye / jobs.feishu.cn / hotjob.cn / 其他。
- 去重：库内公司在精灵 `C:\mcp-suite-collector\data\jobs.json` 的 company 系列字段去重（只读 SSH 传 stdin 脚本，取回公司名去重清单），归一化后命中即跳过。
- 实测：每租户用对应适配器跑一次 `campus` 只读采集，每租户请求上限 15 次（`max_requests=15`），**租户之间 ≥2s**（任务书第 3 步的限速口径；单租户内为适配器自身的礼貌退避/0.2s 分页间隔）；不 `--apply`、不写库。
- 保留口径：`status ∈ {success, partial}` 且已采集岗位 ≥1 条才写入配置；否则记入 `xianyu-ats-rejected.json`。
- 公司名：优先官方站点显示名（飞书 `tenant_name` / 北森页面 title 去「招聘系统」等后缀），否则用表内名称。

## 3. 加入配置的公司（实测通过）

| # | 平台 | 公司（官方/表内） | slug | 岗位数 | status | 请求数 |
|---|---|---|---|---|---|---|
| 1 | 北森(zhiye.com) | 瑞众人寿保险有限责任公司（瑞众保险总公司） | `ruiinsurance` | 301 | success | 15 |
| 2 | 北森(zhiye.com) | 容百集团（容百集团） | `ronbay` | 280 | success | 14 |
| 3 | 北森(zhiye.com) | 杭州泰格医药科技股份有限公司（泰格医药） | `tigermed` | 214 | success | 15 |
| 4 | 北森(zhiye.com) | 横店集团控股有限公司（横店集团） | `hengdian` | 177 | success | 15 |
| 5 | 北森(zhiye.com) | AIVA汽车校园招聘门户网（AIVA汽车） | `aiva` | 172 | success | 11 |
| 6 | 北森(zhiye.com) | 中航科创（中航科创） | `avicsz` | 172 | partial | 13 |
| 7 | 北森(zhiye.com) | 海大官网招聘门户（海大集团） | `haid1` | 167 | success | 15 |
| 8 | 北森(zhiye.com) | 招商船舶（招商局船舶工业技术（上海）有限公司） | `cmi` | 147 | partial | 12 |
| 9 | 北森(zhiye.com) | 龙蟠科技（龙蟠科技） | `lopal` | 132 | success | 11 |
| 10 | 北森(zhiye.com) | 上实集团招聘门户（上实集团） | `siic` | 132 | partial | 11 |
| 11 | 北森(zhiye.com) | 永达集团【新】（永达汽车） | `yonda1` | 122 | partial | 15 |
| 12 | 北森(zhiye.com) | 上海医药人才（上海医药） | `sph` | 114 | partial | 12 |
| 13 | 北森(zhiye.com) | 天职国际（天职国际） | `tzcpa` | 111 | success | 15 |
| 14 | 北森(zhiye.com) | 佰维存储（佰维存储） | `biwin1` | 102 | success | 12 |
| 15 | 北森(zhiye.com) | 中国航空无线电电子研究所（中国航空无线电电子研究所） | `intelligents` | 97 | success | 9 |
| 16 | 北森(zhiye.com) | 上海启源芯动力科技有限公司（启源芯动力） | `spicqyxdl` | 95 | success | 12 |
| 17 | 北森(zhiye.com) | 长江存储（长江存储） | `ymtc` | 95 | success | 15 |
| 18 | 北森(zhiye.com) | 厦门象屿集团有限公司（象屿海装） | `xiangyu` | 94 | success | 13 |
| 19 | 北森(zhiye.com) | 浙江新和成股份有限公司（新和成） | `xinhecheng1` | 94 | partial | 12 |
| 20 | 北森(zhiye.com) | 电建江西院（国电建集团江西省电力设计院有限公司） | `jxepdipowerchina` | 92 | partial | 11 |
| 21 | 北森(zhiye.com) | 凯金（广东凯金新能源） | `kaijin2` | 92 | success | 10 |
| 22 | 北森(zhiye.com) | 普渡机器人（普渡机器人） | `pudutech` | 92 | success | 14 |
| 23 | 北森(zhiye.com) | 赛轮集团（赛轮集团） | `sailuntire` | 89 | success | 9 |
| 24 | 北森(zhiye.com) | 卫星创新院人才（中国科学院微小卫星创新研究院） | `microsatehr` | 87 | success | 10 |
| 25 | 北森(zhiye.com) | 桦洁商贸（上海）有限公司（CHARLES & KEITH GROUP） | `charleskeith` | 85 | success | 12 |
| 26 | 北森(zhiye.com) | 江波龙（江波龙电子） | `longsys` | 85 | success | 10 |
| 27 | 北森(zhiye.com) | 豪威科技（上海）有限公司（豪威集团） | `ovt-omnivision` | 80 | success | 12 |
| 28 | 北森(zhiye.com) | 神州数码集团（神州数码集团） | `digitalchina` | 78 | partial | 14 |
| 29 | 北森(zhiye.com) | 长城电源（长城电源） | `gwpst` | 78 | success | 9 |
| 30 | 北森(zhiye.com) | 先临三维（先临三维） | `shining3d` | 78 | success | 11 |
| 31 | 北森(zhiye.com) | 晶丰明源网申（晶丰明源） | `bpsemi` | 77 | success | 10 |
| 32 | 北森(zhiye.com) | 稳健医疗（稳健医疗） | `winnermedical` | 75 | success | 9 |
| 33 | 北森(zhiye.com) | 哈药集团股份有限公司（哈药集团） | `hayao` | 74 | success | 9 |
| 34 | 北森(zhiye.com) | 圣湘生物科技股份有限公司（圣湘生物） | `sansurehr` | 73 | success | 10 |
| 35 | 北森(zhiye.com) | 翰博高新材料（合肥）股份有限公司（翰博高新） | `hibr` | 72 | success | 9 |
| 36 | 北森(zhiye.com) | 虹科招聘--Science leads Success（虹科） | `hkaco` | 72 | success | 11 |
| 37 | 北森(zhiye.com) | 优必选科技（优必选科技） | `ubtrobot` | 72 | success | 10 |
| 38 | 北森(zhiye.com) | 麦田能源（麦田能源） | `fox-ess` | 70 | success | 11 |
| 39 | 北森(zhiye.com) | 博腾制药（博腾股份） | `porton` | 70 | success | 9 |
| 40 | 北森(zhiye.com) | 劲牌有限公司（劲牌有限公司） | `jingpai` | 69 | success | 9 |
| 41 | 北森(zhiye.com) | 深圳新宙邦科技股份有限公司（新宙邦） | `capchem` | 68 | success | 9 |
| 42 | 北森(zhiye.com) | 东阳光（东阳光集团） | `hec` | 68 | success | 10 |
| 43 | 北森(zhiye.com) | 浙江京新药业股份有限公司（京新药业） | `jingxinpharm1` | 68 | success | 10 |
| 44 | 北森(zhiye.com) | 友山科技（友山科技） | `youshan` | 67 | success | 9 |
| 45 | 北森(zhiye.com) | 中科宇航（中科宇航） | `cas-space` | 65 | success | 11 |
| 46 | 北森(zhiye.com) | 英维克（英维克） | `envicool` | 65 | success | 12 |
| 47 | 北森(zhiye.com) | 旭阳集团（旭阳集团） | `risun` | 65 | success | 10 |
| 48 | 北森(zhiye.com) | 北京四方继保自动化股份有限公司（四方股份） | `sf-auto` | 65 | partial | 9 |
| 49 | 北森(zhiye.com) | 拓荆科技（拓荆科技） | `piotech` | 64 | success | 11 |
| 50 | 北森(zhiye.com) | 富创精密（富创精密） | `syamt` | 62 | success | 10 |
| 51 | 北森(zhiye.com) | 深圳市康冠科技股份有限公司（康冠科技） | `careerktc` | 61 | success | 10 |
| 52 | 北森(zhiye.com) | 德业（德业股份） | `deye` | 61 | success | 11 |
| 53 | 北森(zhiye.com) | 清华四川能源互联网研究院（清华四川能源互联网研究院（清华四川院）） | `tsinghua-eiri` | 61 | partial | 10 |
| 54 | 北森(zhiye.com) | 中乔体育股份有限公司（中乔体育） | `qiaodantiyu` | 60 | success | 10 |
| 55 | 北森(zhiye.com) | 深南电路（深南电路） | `scc` | 59 | success | 9 |
| 56 | 北森(zhiye.com) | 英搏尔（英搏尔电气） | `enpower` | 58 | success | 9 |
| 57 | 北森(zhiye.com) | 浩鲸科技（浩鲸科技） | `iwhalecloud1` | 58 | partial | 9 |
| 58 | 北森(zhiye.com) | 安徽省能源集团（安徽省能源集团有限公司） | `wenergy1` | 58 | success | 9 |
| 59 | 北森(zhiye.com) | 厦钨新能源（厦钨新能） | `xtc-xny1` | 58 | success | 10 |
| 60 | 北森(zhiye.com) | 亿联网络（亿联网络） | `yealink` | 57 | success | 10 |
| 61 | 北森(zhiye.com) | 长飞光纤光缆股份有限公司 27届校招（长飞光纤） | `yofc2` | 57 | success | 9 |
| 62 | 北森(zhiye.com) | 华睿科技（华睿科技） | `irayple` | 56 | success | 10 |
| 63 | 北森(zhiye.com) | 金杯电工股份有限公司（金杯电工） | `jinbei` | 56 | success | 12 |
| 64 | 北森(zhiye.com) | 摩尔线程招聘门户（摩尔线程） | `mthreads` | 55 | success | 13 |
| 65 | 北森(zhiye.com) | 济南邦德激光股份有限公司（Bodor邦德激光） | `bodor` | 54 | success | 13 |
| 66 | 北森(zhiye.com) | 灵猴机器人2027（灵猴机器人） | `linkhou` | 54 | success | 9 |
| 67 | 北森(zhiye.com) | 豪迈（豪迈） | `himile` | 53 | success | 15 |
| 68 | 北森(zhiye.com) | 睿创微纳（睿创微纳） | `raytrontek` | 53 | partial | 13 |
| 69 | 北森(zhiye.com) | 中信科移动（中信科移动） | `cictmobile` | 52 | success | 10 |
| 70 | 北森(zhiye.com) | 中海物业集团有限公司（中海物业） | `copm` | 52 | partial | 15 |
| 71 | 北森(zhiye.com) | “芯之所向 星耀未来”湖北星辰-2027（湖北星辰技术有限公司） | `hsingchen` | 52 | success | 9 |
| 72 | 北森(zhiye.com) | 合合信息招聘门户（合合信息） | `intsig` | 52 | success | 9 |
| 73 | 北森(zhiye.com) | 威迈斯（威迈斯） | `vmax` | 51 | partial | 10 |
| 74 | 北森(zhiye.com) | 骆驼集团股份有限公司（骆驼集团） | `chinacamel1` | 50 | success | 9 |
| 75 | 北森(zhiye.com) | 纳思达（奔图科技） | `ninestar` | 50 | success | 9 |
| 76 | 北森(zhiye.com) | 麦科田医疗（麦科田医疗） | `medcaptain` | 49 | success | 9 |
| 77 | 北森(zhiye.com) | 联友科技（联友科技） | `szly` | 49 | partial | 9 |
| 78 | 北森(zhiye.com) | 清微智能（清微智能） | `tsingmicro` | 49 | success | 10 |
| 79 | 北森(zhiye.com) | 瑞普生物股份有限公司（瑞普生物） | `ringpu1` | 48 | success | 9 |
| 80 | 北森(zhiye.com) | 中国三星（三星(中国)半导体） | `dearsamsung` | 46 | success | 9 |
| 81 | 北森(zhiye.com) | 西安奕斯伟材料科技股份有限公司（奕斯伟材料） | `eswin-si` | 46 | partial | 9 |
| 82 | 北森(zhiye.com) | 贵州磷化集团（贵州磷化） | `gzlhjt` | 46 | partial | 8 |
| 83 | 北森(zhiye.com) | 加多宝（中国）饮料有限公司（加多宝集团） | `jdbchina` | 46 | success | 10 |
| 84 | 北森(zhiye.com) | 艾为电子|中国数模龙头|艾为（艾为电子） | `awinic1` | 45 | success | 10 |
| 85 | 北森(zhiye.com) | 立讯技术（立讯技术） | `luxshare-tech` | 45 | success | 9 |
| 86 | 北森(zhiye.com) | 雪川农业集团（雪川农业集团） | `snowvalleyfood` | 45 | success | 9 |
| 87 | 北森(zhiye.com) | 深圳燃气（深圳燃气） | `szgas` | 45 | success | 8 |
| 88 | 北森(zhiye.com) | 特锐德（特锐德） | `tgood` | 45 | success | 10 |
| 89 | 北森(zhiye.com) | 绿联（绿联科技） | `ugreen` | 45 | success | 8 |
| 90 | 北森(zhiye.com) | 壹连招聘门户（壹连科技） | `uniconn` | 45 | success | 10 |
| 91 | 北森(zhiye.com) | 赢合科技校招（赢合科技） | `yhwins2` | 45 | success | 8 |
| 92 | 北森(zhiye.com) | 智岩科技（智岩科技） | `govee` | 44 | success | 9 |
| 93 | 北森(zhiye.com) | 上海哈啰普惠科技有限公司（哈啰） | `hellobike` | 44 | partial | 15 |
| 94 | 北森(zhiye.com) | 云圣智能--招聘门户（云圣智能） | `ikingtec` | 44 | success | 9 |
| 95 | 北森(zhiye.com) | 浙江天宇药业股份有限公司（天宇股份） | `tianyupharm` | 44 | success | 9 |
| 96 | 北森(zhiye.com) | 振石控股集团有限公司（振石控股集团） | `zhenshigroup` | 44 | success | 9 |
| 97 | 北森(zhiye.com) | 中海企业发展集团有限公司（中海地产） | `coli688` | 43 | partial | 8 |
| 98 | 北森(zhiye.com) | 大信会计（大信会计师事务所） | `daxincpa` | 43 | success | 9 |
| 99 | 北森(zhiye.com) | 昊一源（昊一源） | `hollyland` | 43 | success | 9 |
| 100 | 北森(zhiye.com) | MOVA（MOVA） | `mova` | 43 | success | 15 |
| 101 | 北森(zhiye.com) | 上饶银行（上饶银行） | `shangraoyinhang` | 43 | success | 9 |
| 102 | 北森(zhiye.com) | 康恒环境（康恒环境） | `shsus` | 43 | success | 14 |
| 103 | 北森(zhiye.com) | 西安电子工程研究所（中国兵器工业第二〇六研究所） | `xadzgc` | 43 | partial | 8 |
| 104 | 北森(zhiye.com) | 优艾智合（优艾智合） | `youibot1` | 43 | success | 9 |
| 105 | 北森(zhiye.com) | 安徽巡鹰新能源集团有限公司（巡鹰集团） | `ahxunying` | 42 | success | 8 |
| 106 | 北森(zhiye.com) | 苏纳SUNA（苏纳） | `suna-opto` | 41 | success | 11 |
| 107 | 北森(zhiye.com) | 新芯股份-招聘门户（新芯股份） | `whxmc` | 41 | success | 9 |
| 108 | 北森(zhiye.com) | 衣臻时装有限公司（衣臻时装） | `yiconcept` | 41 | success | 9 |
| 109 | 北森(zhiye.com) | Babycare招聘官网-今天你投简历了吗？（Babycare） | `babycare` | 40 | success | 13 |
| 110 | 北森(zhiye.com) | 屹唐半导体（屹唐半导体） | `bestsemi` | 40 | success | 9 |
| 111 | 北森(zhiye.com) | 华测导航（华测导航） | `huace` | 40 | success | 8 |
| 112 | 北森(zhiye.com) | 乐动机器人（乐动机器人） | `ldrobot` | 40 | success | 9 |
| 113 | 北森(zhiye.com) | 心田花开（心田花开） | `xintianhuakai1` | 40 | success | 10 |
| 114 | 北森(zhiye.com) | 航空工业计量所（航空工业计量所） | `cimm` | 39 | success | 8 |
| 115 | 北森(zhiye.com) | 湖南国科微电子股份有限公司（国科微电子） | `goke1` | 39 | success | 10 |
| 116 | 北森(zhiye.com) | 树根科技（树根科技） | `irootech` | 39 | success | 10 |
| 117 | 北森(zhiye.com) | 苏州高创运动控制技术有限公司（高创传动） | `servotronix` | 39 | success | 8 |
| 118 | 北森(zhiye.com) | 思必驰科技股份有限公司（思必驰） | `aispeech` | 38 | partial | 10 |
| 119 | 北森(zhiye.com) | 中国南山（中国南山） | `cndi` | 38 | partial | 8 |
| 120 | 北森(zhiye.com) | 德方纳米2027届校招（德方纳米） | `dynanonic3` | 38 | success | 8 |
| 121 | 北森(zhiye.com) | 联芸科技（联芸科技） | `maxio-tech1` | 38 | success | 8 |
| 122 | 北森(zhiye.com) | 广州金升阳科技有限公司（金升阳） | `mornsun` | 38 | success | 12 |
| 123 | 北森(zhiye.com) | 深蓝航天-2027届校园（深蓝航天） | `shenlan1` | 38 | success | 10 |
| 124 | 北森(zhiye.com) | 江南造船（集团）有限责任公司（江南造船） | `jnzhaopin` | 37 | success | 8 |
| 125 | 北森(zhiye.com) | 精研科技（精研科技） | `jsgian` | 37 | success | 9 |
| 126 | 北森(zhiye.com) | 金开新能（金开新能源） | `nyocor` | 37 | success | 9 |
| 127 | 北森(zhiye.com) | 东方空间（东方空间） | `orienspace` | 37 | success | 9 |
| 128 | 北森(zhiye.com) | 永芯科技（永芯科技） | `yongxinbj` | 37 | success | 8 |
| 129 | 北森(zhiye.com) | 交控科技股份有限公司（交控科技） | `bj-tct` | 36 | success | 8 |
| 130 | 北森(zhiye.com) | 瑞沃德（瑞沃德） | `rwdls` | 36 | success | 8 |
| 131 | 北森(zhiye.com) | 东明石化（东明石化） | `sddmsh` | 36 | partial | 10 |
| 132 | 北森(zhiye.com) | 长园深瑞继保自动化有限公司（长园深瑞） | `sznari` | 36 | success | 9 |
| 133 | 北森(zhiye.com) | 曦诺未来（曦诺未来） | `xynovatech` | 36 | success | 9 |
| 134 | 北森(zhiye.com) | 遨森电商（遨森电商） | `aosom1` | 35 | success | 10 |
| 135 | 北森(zhiye.com) | 柏楚电子（柏楚电子） | `fscut` | 35 | success | 10 |
| 136 | 北森(zhiye.com) | 公牛集团（公牛集团） | `gongniu` | 35 | success | 9 |
| 137 | 北森(zhiye.com) | 广州金域医学检验中心有限公司（金域医学） | `kingmed` | 35 | success | 9 |
| 138 | 北森(zhiye.com) | 利元亨（利元亨） | `liyuanheng` | 35 | success | 9 |
| 139 | 北森(zhiye.com) | 福建雪人集团股份有限公司（雪人集团） | `snowman` | 35 | success | 9 |
| 140 | 北森(zhiye.com) | 兰剑智能（兰剑智能） | `blueswords` | 34 | success | 9 |
| 141 | 北森(zhiye.com) | 潮宏基（潮宏基） | `chjgroup` | 34 | success | 8 |
| 142 | 北森(zhiye.com) | 神州信息（神州信息） | `dcits` | 34 | success | 15 |
| 143 | 北森(zhiye.com) | 永业行（永业行） | `realhom` | 34 | success | 10 |
| 144 | 北森(zhiye.com) | 锐明技术（锐明技术） | `streamax` | 34 | success | 9 |
| 145 | 北森(zhiye.com) | 宇树科技（宇树科技） | `unitree` | 34 | success | 9 |
| 146 | 北森(zhiye.com) | 晶晨半导体（晶晨半导体） | `amlogicsh` | 33 | success | 11 |
| 147 | 北森(zhiye.com) | 广合招聘门户（广合科技） | `delton` | 33 | success | 10 |
| 148 | 北森(zhiye.com) | 立达信物联科技（立达信集团） | `leedarson` | 33 | success | 9 |
| 149 | 北森(zhiye.com) | 天孚通信招聘门户（天孚通信） | `tfcsz` | 33 | partial | 10 |
| 150 | 北森(zhiye.com) | 一鸣（一鸣食品） | `inm` | 32 | success | 11 |
| 151 | 北森(zhiye.com) | 南京圣和药业股份有限公司（圣和药业） | `sanhome` | 32 | success | 9 |
| 152 | 北森(zhiye.com) | 公司官网投递（祥承科技） | `xchengtech` | 32 | success | 9 |
| 153 | 北森(zhiye.com) | 海光芯正集团（海光芯正） | `crealights` | 31 | success | 8 |
| 154 | 北森(zhiye.com) | 北芯生命（北芯生命） | `insight-med` | 31 | success | 9 |
| 155 | 北森(zhiye.com) | 微纳星空（微纳星空） | `minospace` | 31 | success | 9 |
| 156 | 北森(zhiye.com) | 深圳市德明利技术股份有限公司（德明利） | `twsc` | 31 | success | 8 |
| 157 | 北森(zhiye.com) | 北斗星通（北斗星通） | `bdstar` | 30 | success | 9 |
| 158 | 北森(zhiye.com) | 广东奥马冰箱有限公司（奥马冰箱） | `homa-hr` | 30 | success | 9 |
| 159 | 北森(zhiye.com) | 昇维旭（昇维旭） | `swaysure` | 30 | success | 10 |
| 160 | 北森(zhiye.com) | 凯莱英（凯莱英医药集团） | `asymchem` | 29 | success | 15 |
| 161 | 北森(zhiye.com) | 宝宝巴士（宝宝巴士） | `babybus` | 29 | success | 9 |
| 162 | 北森(zhiye.com) | 南京康尼机电股份有限公司（康尼机电） | `kangni` | 29 | success | 9 |
| 163 | 北森(zhiye.com) | 新大陆科技集团（新大陆科技集团） | `newland` | 29 | success | 8 |
| 164 | 北森(zhiye.com) | 信捷电气（信捷电气） | `xinje` | 29 | success | 9 |
| 165 | 北森(zhiye.com) | 卡旺卡（卡旺卡） | `comewonka` | 28 | partial | 8 |
| 166 | 北森(zhiye.com) | 东方算芯（东方算芯） | `ecosda` | 28 | success | 10 |
| 167 | 北森(zhiye.com) | 英杰晨晖官方（英杰晨晖） | `injet-instrument` | 28 | success | 9 |
| 168 | 北森(zhiye.com) | 合肥晶合集成电路股份有限公司（晶合集成） | `nexchip` | 28 | success | 11 |
| 169 | 北森(zhiye.com) | 信得科技（信得科技） | `sinder` | 28 | success | 9 |
| 170 | 北森(zhiye.com) | 量旋科技（量旋科技） | `spinq` | 28 | success | 8 |
| 171 | 北森(zhiye.com) | 平行线教育（平行线教育） | `zzpxx` | 28 | success | 9 |
| 172 | 北森(zhiye.com) | 芯碁微装（芯碁微装） | `cfmee` | 27 | success | 8 |
| 173 | 北森(zhiye.com) | 西安奇点能源股份有限公司（奇点能源） | `jd-energy` | 27 | success | 9 |
| 174 | 北森(zhiye.com) | 巨鲨医疗校园招聘门户（巨鲨医疗） | `jusha` | 27 | success | 8 |
| 175 | 北森(zhiye.com) | 砺星工业科技（砺星Leetx） | `leetx` | 27 | success | 8 |
| 176 | 北森(zhiye.com) | LINSY 林氏（林氏家居） | `linshimuye` | 27 | success | 11 |
| 177 | 北森(zhiye.com) | 碧澄能源（碧澄能源） | `pcgpower` | 27 | success | 8 |
| 178 | 北森(zhiye.com) | 儒意电影（儒意电影） | `ruyifilm` | 27 | success | 9 |
| 179 | 北森(zhiye.com) | 航天恒星（航天恒星） | `spacestar` | 27 | success | 8 |
| 180 | 北森(zhiye.com) | 一飞院（航空工业一飞院） | `yfy` | 27 | success | 8 |
| 181 | 北森(zhiye.com) | 纵维立方（纵维立方） | `anycubic` | 26 | success | 9 |
| 182 | 北森(zhiye.com) | BMC瑞迈特集团招聘门户（BMC瑞迈特） | `bmc-medical` | 26 | success | 8 |
| 183 | 北森(zhiye.com) | 帝迈生物（帝迈生物） | `dymind` | 26 | partial | 8 |
| 184 | 北森(zhiye.com) | 成都奕成科技股份有限公司（奕成科技） | `echint` | 26 | success | 10 |
| 185 | 北森(zhiye.com) | 成都新易盛通信技术股份有限公司（新易盛） | `eoptolink` | 26 | partial | 9 |
| 186 | 北森(zhiye.com) | 华昱欣招聘门户（华昱欣） | `hyxipower` | 26 | success | 8 |
| 187 | 北森(zhiye.com) | 高标（高标科技） | `kjgb` | 26 | success | 8 |
| 188 | 北森(zhiye.com) | 赛赋医药（赛赋医药） | `safeglp` | 26 | success | 9 |
| 189 | 北森(zhiye.com) | 神农集团（神农集团） | `ynsnjt` | 26 | success | 9 |
| 190 | 北森(zhiye.com) | 芯上微装（芯上微装） | `amies` | 25 | success | 8 |
| 191 | 北森(zhiye.com) | 卡斯柯信号有限公司（卡斯柯） | `casco` | 25 | success | 8 |
| 192 | 北森(zhiye.com) | 上海精测招聘门户（上海精测半导体） | `pmish-tech` | 25 | success | 10 |
| 193 | 北森(zhiye.com) | 招聘门户（承葛医药集团） | `treatgut` | 25 | success | 9 |
| 194 | 北森(zhiye.com) | 中机中联工程有限公司（中机中联） | `cmcu` | 24 | success | 8 |
| 195 | 北森(zhiye.com) | 浙江水晶光电科技股份有限公司（水晶光电） | `crystal-optech1` | 24 | success | 9 |
| 196 | 北森(zhiye.com) | 复宏汉霖Henlius（复宏汉霖） | `henlius` | 24 | success | 10 |
| 197 | 北森(zhiye.com) | 日立能源（日立能源） | `hitachienergy` | 24 | success | 15 |
| 198 | 北森(zhiye.com) | 洲明科技（洲明科技） | `unilumin` | 24 | partial | 8 |
| 199 | 北森(zhiye.com) | 强度所（中国飞机强度研究所） | `avicasri` | 23 | success | 8 |
| 200 | 北森(zhiye.com) | 中国航空制造技术研究院（中国航空制造技术研究院） | `avicmti` | 23 | success | 8 |
| 201 | 北森(zhiye.com) | LST（联眺科技） | `leapsightech` | 23 | success | 8 |
| 202 | 北森(zhiye.com) | 辰显光电（辰显光电） | `vistar` | 23 | success | 9 |
| 203 | 北森(zhiye.com) | YASC招聘门户（长飞先进半导体） | `yasc` | 23 | success | 10 |
| 204 | 北森(zhiye.com) | 深圳力维智联技术有限公司（力维智联） | `znvhr1` | 23 | success | 8 |
| 205 | 北森(zhiye.com) | 睿智医药（睿智医药） | `chempartner` | 22 | success | 9 |
| 206 | 北森(zhiye.com) | 凯瑞斯德集团（凯瑞斯德） | `cqpharm` | 22 | success | 8 |
| 207 | 北森(zhiye.com) | 中国船舶集团有限公司第七一二研究所（中船七一二所） | `cssc712` | 22 | success | 8 |
| 208 | 北森(zhiye.com) | 法士特（法士特） | `fast` | 22 | success | 8 |
| 209 | 北森(zhiye.com) | 省建院（广东省建筑设计研究院集团） | `gdadri` | 22 | success | 9 |
| 210 | 北森(zhiye.com) | 高德红外（高德红外） | `gdhw` | 22 | success | 12 |
| 211 | 北森(zhiye.com) | 豪鹏科技（豪鹏科技） | `highpowertech` | 22 | success | 8 |
| 212 | 北森(zhiye.com) | 纵横股份（纵横股份） | `jouav` | 22 | success | 8 |
| 213 | 北森(zhiye.com) | 日月股份（日月股份） | `riyue` | 22 | success | 9 |
| 214 | 北森(zhiye.com) | 青岛乾程科技股份有限公司（乾程） | `techen` | 22 | success | 8 |
| 215 | 北森(zhiye.com) | 高能环境（高能环境） | `bgechina1` | 21 | success | 8 |
| 216 | 北森(zhiye.com) | 芯海科技（芯海科技） | `chipsea` | 21 | success | 9 |
| 217 | 北森(zhiye.com) | 英洛华科技股份有限公司（英洛华科技） | `hengdian2` | 21 | success | 9 |
| 218 | 北森(zhiye.com) | 江苏海四达电源有限公司（海四达） | `highstar` | 21 | partial | 9 |
| 219 | 北森(zhiye.com) | 华立科技股份有限公司（华立科技） | `holley` | 21 | success | 8 |
| 220 | 北森(zhiye.com) | 希奥端（希奥端） | `lecarc` | 21 | success | 9 |
| 221 | 北森(zhiye.com) | 渠梁电子有限公司（渠梁电子） | `qleltd1` | 21 | partial | 8 |
| 222 | 北森(zhiye.com) | 鼎阳科技（鼎阳科技） | `siglent` | 21 | success | 8 |
| 223 | 北森(zhiye.com) | 上海微电子装备有限公司（上海微电子装备） | `smee` | 21 | success | 8 |
| 224 | 北森(zhiye.com) | 皖仪科技人才（皖仪科技） | `wayeal` | 21 | success | 8 |
| 225 | 北森(zhiye.com) | 武汉船机（中船集团武汉船用机械有限责任公司） | `wmmp` | 21 | success | 8 |
| 226 | 北森(zhiye.com) | 校招（帝奥微） | `dioo` | 20 | success | 8 |
| 227 | 北森(zhiye.com) | 芯动科技（芯动科技） | `innosilicon` | 20 | success | 10 |
| 228 | 北森(zhiye.com) | 晶易医药（晶易医药） | `king-eagle` | 20 | success | 9 |
| 229 | 北森(zhiye.com) | 朗坤科技（朗坤科技） | `leoking` | 20 | success | 8 |
| 230 | 北森(zhiye.com) | 中山联合光电科技股份有限公司（联合光电科技） | `lianheguangdian` | 20 | success | 8 |
| 231 | 北森(zhiye.com) | 雷特科技（雷特科技） | `morningfast` | 20 | success | 8 |
| 232 | 北森(zhiye.com) | 人福医药（人福医药） | `renfu` | 20 | success | 9 |
| 233 | 北森(zhiye.com) | 雷迪奥ROE（雷迪奥） | `roe` | 20 | success | 8 |
| 234 | 北森(zhiye.com) | 卫星化学股份有限公司招聘网申（卫星集团） | `satlpec` | 20 | partial | 9 |
| 235 | 北森(zhiye.com) | 深圳市崧盛电子股份有限公司（崧盛股份） | `sosen` | 20 | success | 8 |
| 236 | 北森(zhiye.com) | 北京清华同衡规划设计研究院有限公司（清华同衡） | `thupdi` | 20 | success | 10 |
| 237 | 北森(zhiye.com) | 八马茶业股份有限公司（八马茶业） | `bamatea` | 19 | partial | 8 |
| 238 | 北森(zhiye.com) | 高松电子（高松技术） | `degson` | 19 | success | 8 |
| 239 | 北森(zhiye.com) | 法本信息（法本信息） | `farben` | 19 | success | 8 |
| 240 | 北森(zhiye.com) | 厦门金鹭（厦门钨业-厦门金鹭） | `gesac` | 19 | success | 8 |
| 241 | 北森(zhiye.com) | 万有引力（宁波）电子科技有限公司（万有引力GravityXR） | `gravityxr` | 19 | success | 9 |
| 242 | 北森(zhiye.com) | 杰峰物联（杰峰科技） | `jftech` | 19 | success | 8 |
| 243 | 北森(zhiye.com) | 深圳市捷顺科技实业股份有限公司（校园招聘）（捷顺科技） | `jieshun` | 19 | success | 8 |
| 244 | 北森(zhiye.com) | 苏州吉天星舟空间技术有限公司（吉天星舟） | `jtxzspace` | 19 | success | 8 |
| 245 | 北森(zhiye.com) | 昆仑芯招聘门户（昆仑芯） | `kunlunxin1` | 19 | success | 9 |
| 246 | 北森(zhiye.com) | 光寶新創校園招募（光宝中国研发中心） | `liteon` | 19 | success | 8 |
| 247 | 北森(zhiye.com) | 优博讯科技（优博讯） | `urovo` | 19 | success | 8 |
| 248 | 北森(zhiye.com) | 深圳市永联科技股份有限公司（永联科技） | `winline` | 19 | success | 8 |
| 249 | 北森(zhiye.com) | 志邦家居（志邦家居） | `zbom` | 19 | success | 8 |
| 250 | 北森(zhiye.com) | 仪电智算（仪电智算） | `aipower` | 18 | success | 10 |
| 251 | 北森(zhiye.com) | 中国化学东华公司（中国化学工程东华公司） | `chinaecec` | 18 | success | 8 |
| 252 | 北森(zhiye.com) | 海格通信（海格通信） | `haige` | 18 | partial | 8 |
| 253 | 北森(zhiye.com) | 智慧星空(上海)工程技术有限公司（星空科技） | `istar-group` | 18 | success | 8 |
| 254 | 北森(zhiye.com) | 联发科技（联发科技） | `mediatek` | 18 | success | 9 |
| 255 | 北森(zhiye.com) | 普利特（普利特） | `pret` | 18 | success | 8 |
| 256 | 北森(zhiye.com) | 大连科苑同芳（大连科苑同芳学校） | `pxjydl1` | 18 | success | 8 |
| 257 | 北森(zhiye.com) | 听潮阁（听潮阁传媒） | `tingchaoge` | 18 | success | 8 |
| 258 | 北森(zhiye.com) | 爱慕集团（爱慕股份） | `aimer` | 17 | success | 8 |
| 259 | 北森(zhiye.com) | 安脉盛（安脉盛） | `aimsphm` | 17 | success | 9 |
| 260 | 北森(zhiye.com) | 扬腾创新（扬腾创新） | `cht-group3` | 17 | success | 8 |
| 261 | 北森(zhiye.com) | 沪东中华造船集团（沪东中华造船） | `hudong` | 17 | success | 8 |
| 262 | 北森(zhiye.com) | 镁伽（镁伽科技） | `megarobo` | 17 | success | 9 |
| 263 | 北森(zhiye.com) | 北森平台-博瑞电力招聘专场（博瑞电力） | `nrec1` | 17 | success | 8 |
| 264 | 北森(zhiye.com) | 日出集团（日出集团） | `sfcc` | 17 | success | 8 |
| 265 | 北森(zhiye.com) | 宁波赛柯国际贸易有限公司（赛柯） | `sklinter` | 17 | success | 8 |
| 266 | 北森(zhiye.com) | 元琛科技（元琛科技） | `yckjgf` | 17 | success | 8 |
| 267 | 北森(zhiye.com) | 高露洁校园招聘门户（高露洁） | `colgate` | 16 | success | 8 |
| 268 | 北森(zhiye.com) | 数字政通（数字政通） | `egova` | 16 | success | 8 |
| 269 | 北森(zhiye.com) | 钜泉科技招聘网（钜泉科技） | `hitrendtech1` | 16 | success | 8 |
| 270 | 北森(zhiye.com) | 华海清科-2027（华海清科） | `hwatsing1` | 16 | success | 8 |
| 271 | 北森(zhiye.com) | 科捷智能招聘门户（科捷智能） | `kengic` | 16 | success | 8 |
| 272 | 北森(zhiye.com) | 薇美姿（薇美姿集团） | `weimeizi` | 16 | success | 9 |
| 273 | 北森(zhiye.com) | 共创草坪（共创草坪） | `ccgrass` | 15 | success | 8 |
| 274 | 北森(zhiye.com) | 多氟多（多氟多新材料股份有限公司） | `dfdchem1` | 15 | success | 8 |
| 275 | 北森(zhiye.com) | 华阳通用-招聘门户（华阳通用） | `foryouge` | 15 | success | 9 |
| 276 | 北森(zhiye.com) | 绿能慧充招聘门户（绿能慧充） | `gresgying` | 15 | success | 8 |
| 277 | 北森(zhiye.com) | 厦门星纵物联（星纵物联） | `milesight` | 15 | success | 9 |
| 278 | 北森(zhiye.com) | 眸芯（眸芯科技） | `molchip` | 15 | success | 8 |
| 279 | 北森(zhiye.com) | 新大陆支付技术（新大陆支付技术公司） | `newlandpayment` | 15 | success | 8 |
| 280 | 北森(zhiye.com) | 电建西北院（中国电建西北院） | `nwh` | 15 | success | 8 |
| 281 | 北森(zhiye.com) | 东方电缆（东方电缆） | `orientcable` | 15 | success | 8 |
| 282 | 北森(zhiye.com) | 日丰（日丰企业集团） | `rifengdz` | 15 | success | 8 |
| 283 | 北森(zhiye.com) | 认养一头牛驿站（认养一头牛集团） | `ryytn` | 15 | success | 8 |
| 284 | 北森(zhiye.com) | 上海农村商业银行股份有限公司（上海农商银行） | `shrcb` | 15 | success | 8 |
| 285 | 北森(zhiye.com) | 南方测绘集团（南方测绘集团） | `southsurvey` | 15 | success | 8 |
| 286 | 北森(zhiye.com) | 艾诺仪器公司（艾诺仪器） | `ainuo` | 14 | success | 8 |
| 287 | 北森(zhiye.com) | 长强系统（长强系统） | `chang-qiang` | 14 | success | 8 |
| 288 | 北森(zhiye.com) | 达力普石油专用管有限公司（达力普公司） | `dalipal` | 14 | success | 8 |
| 289 | 北森(zhiye.com) | 菲利斯太阳能（菲利斯） | `felicitysolar` | 14 | success | 9 |
| 290 | 北森(zhiye.com) | 亘芯悦（无锡亘芯悦科技有限公司） | `genxinyuecom` | 14 | success | 8 |
| 291 | 北森(zhiye.com) | 航空工业自控所（上海民用航空控制与导航系统有限公司） | `h618` | 14 | partial | 12 |
| 292 | 北森(zhiye.com) | 云天励飞（云天励飞） | `intellif` | 14 | success | 9 |
| 293 | 北森(zhiye.com) | 国能日新（国能日新） | `sprixin` | 14 | success | 8 |
| 294 | 北森(zhiye.com) | 广州敏视（敏视） | `stonkam` | 14 | success | 8 |
| 295 | 北森(zhiye.com) | 炬芯科技（炬芯科技） | `actionstech` | 13 | success | 8 |
| 296 | 北森(zhiye.com) | 中航技（中航技） | `catic` | 13 | success | 8 |
| 297 | 北森(zhiye.com) | 禾望电气（禾望电气） | `hopewind` | 13 | success | 8 |
| 298 | 北森(zhiye.com) | JM华中华东区（OPPO JM华中华东区） | `jmgroup-o` | 13 | success | 12 |
| 299 | 北森(zhiye.com) | 中茵微电子（中茵微电子） | `joinsilicon` | 13 | success | 9 |
| 300 | 北森(zhiye.com) | 融通供应链招聘门户（建信融通） | `jxrt` | 13 | success | 9 |
| 301 | 北森(zhiye.com) | 礼意久久（礼意久久） | `liyi99` | 13 | success | 8 |
| 302 | 北森(zhiye.com) | 安徽老乡鸡餐饮有限公司（老乡鸡） | `lxjchina1` | 13 | success | 9 |
| 303 | 北森(zhiye.com) | 东江北森招聘门户（东江控股） | `tkgroup` | 13 | success | 8 |
| 304 | 北森(zhiye.com) | 亚特电器（亚特电器） | `yat-pro` | 13 | success | 8 |
| 305 | 北森(zhiye.com) | 得一微电子（得一微电子） | `yeestor` | 13 | success | 8 |
| 306 | 北森(zhiye.com) | 中荣股份2027届（中荣股份） | `zrpgroup` | 13 | success | 8 |
| 307 | 北森(zhiye.com) | 九江金鹭硬质合金有限公司（九江金鹭） | `cxtc-jt2` | 12 | success | 8 |
| 308 | 北森(zhiye.com) | 大通宝富（大通宝富） | `dartrich` | 12 | success | 8 |
| 309 | 北森(zhiye.com) | 中国电建福建院（中国电建福建院） | `fedi` | 12 | success | 8 |
| 310 | 北森(zhiye.com) | 泛联新安x校招门户（泛联新安） | `flyaitalent` | 12 | success | 8 |
| 311 | 北森(zhiye.com) | 凡拓数字（凡拓数创） | `frontop` | 12 | success | 8 |
| 312 | 北森(zhiye.com) | 聚和材料（聚和材料集团） | `fusion-materials` | 12 | success | 8 |
| 313 | 北森(zhiye.com) | 华创微官方网申渠道（江苏华创微系统有限公司） | `hcmicro` | 12 | success | 9 |
| 314 | 北森(zhiye.com) | 招聘门户网站（回天新材） | `huitian1` | 12 | success | 8 |
| 315 | 北森(zhiye.com) | 华中数控（华中数控） | `hzncc` | 12 | success | 8 |
| 316 | 北森(zhiye.com) | 科威尔（科威尔技术） | `kewell` | 12 | success | 8 |
| 317 | 北森(zhiye.com) | 洽洽食品股份有限公司（洽洽食品） | `qiaqiafood` | 12 | success | 8 |
| 318 | 北森(zhiye.com) | 天锐星通招聘门户（天锐星通） | `t-ray` | 12 | success | 8 |
| 319 | 北森(zhiye.com) | 桃李未来（桃李未来） | `taoliweilai` | 12 | success | 8 |
| 320 | 北森(zhiye.com) | 维亚（维亚生物） | `viva` | 12 | success | 8 |
| 321 | 北森(zhiye.com) | 华纳大药厂（华纳药厂） | `warrant` | 12 | success | 8 |
| 322 | 北森(zhiye.com) | 万联（万联证券） | `wlzq` | 12 | partial | 10 |
| 323 | 北森(zhiye.com) | 灵明光子（灵明光子） | `adaps-ph` | 11 | success | 8 |
| 324 | 北森(zhiye.com) | 杭州迪普科技股份有限公司（迪普科技） | `dptech` | 11 | success | 15 |
| 325 | 北森(zhiye.com) | 苏州极易科技股份有限公司（极易科技） | `ecmax` | 11 | success | 8 |
| 326 | 北森(zhiye.com) | 格见半导体（格见半导体） | `gejian-semi` | 11 | success | 8 |
| 327 | 北森(zhiye.com) | 悍高集团（悍高集团） | `higold` | 11 | success | 8 |
| 328 | 北森(zhiye.com) | 海栎创（海栎创） | `hynitron` | 11 | success | 8 |
| 329 | 北森(zhiye.com) | 鹿客科技（鹿客科技） | `lockin` | 11 | success | 8 |
| 330 | 北森(zhiye.com) | 湖北绿色家园材料技术股份有限公司（湖北绿色家园） | `lsjyzp` | 11 | success | 8 |
| 331 | 北森(zhiye.com) | 齐物科技（iGPSPORT迹驰） | `qwkj` | 11 | success | 8 |
| 332 | 北森(zhiye.com) | 优理奇（优理奇机器人） | `unix-group` | 11 | success | 8 |
| 333 | 北森(zhiye.com) | 智慧芽信息科技（苏州）有限公司（智慧芽） | `zhihuiya` | 11 | success | 8 |
| 334 | 北森(zhiye.com) | 格通智联（格通智联） | `gention` | 10 | success | 8 |
| 335 | 北森(zhiye.com) | 邯药公司（邯郸制药-校园大使） | `hanyao` | 10 | success | 8 |
| 336 | 北森(zhiye.com) | 核桃编程（核桃编程） | `hetao101` | 10 | success | 8 |
| 337 | 北森(zhiye.com) | 诺德凯（苏州）智能装备有限公司（诺德凯） | `hrnordkete` | 10 | success | 8 |
| 338 | 北森(zhiye.com) | 科大国创股份有限公司招聘门户（科大国创） | `kdgcsoft` | 10 | success | 8 |
| 339 | 北森(zhiye.com) | 牛芯半导体企业（牛芯半导体） | `kniulink` | 10 | success | 8 |
| 340 | 北森(zhiye.com) | 沛塬电子（沛塬电子） | `metapwr` | 10 | success | 8 |
| 341 | 北森(zhiye.com) | 国芯微nationalchip（国芯微电子） | `nationalchip` | 10 | success | 8 |
| 342 | 北森(zhiye.com) | 南京我乐家居股份有限公司（我乐家居） | `olo-home` | 10 | success | 8 |
| 343 | 北森(zhiye.com) | 三未信安（三未信安） | `sansec` | 10 | success | 8 |
| 344 | 北森(zhiye.com) | 天正电气（天正电气） | `tengen` | 10 | success | 8 |
| 345 | 北森(zhiye.com) | 芯合电子（芯合电子） | `unisemipower` | 10 | success | 8 |
| 346 | 北森(zhiye.com) | 山东五征集团有限公司（五征集团） | `wuzheng1` | 10 | success | 8 |
| 347 | 北森(zhiye.com) | 中国建筑西南设计研究院有限公司（中建西南院） | `xnjz` | 10 | success | 8 |
| 348 | 北森(zhiye.com) | 汉阳科技（汉阳科技） | `yarbo` | 10 | success | 8 |
| 349 | 北森(zhiye.com) | 中红医疗（中红医疗） | `zhonghongpulin` | 10 | success | 8 |
| 350 | 北森(zhiye.com) | 中山大洋电机股份有限公司（大洋电机集团） | `bomc` | 9 | success | 8 |
| 351 | 北森(zhiye.com) | 航天五院遥感部（航天科技集团五院遥感卫星总体部） | `cast` | 9 | success | 8 |
| 352 | 北森(zhiye.com) | 都正生物（都正生物） | `duxact` | 9 | success | 8 |
| 353 | 北森(zhiye.com) | 飞凌嵌入式招聘门户（飞凌嵌入式） | `forlinx1` | 9 | success | 8 |
| 354 | 北森(zhiye.com) | 富芯半导体招聘网申（富芯半导体） | `fullsemi` | 9 | success | 8 |
| 355 | 北森(zhiye.com) | 紫讯科技（紫讯技术） | `fzzixun` | 9 | success | 8 |
| 356 | 北森(zhiye.com) | 海正药业（海正药业） | `hisunpharm` | 9 | success | 8 |
| 357 | 北森(zhiye.com) | 恩井智控（恩井智控） | `ingin` | 9 | success | 8 |
| 358 | 北森(zhiye.com) | 基准方中（基准方中） | `jzfz` | 9 | success | 15 |
| 359 | 北森(zhiye.com) | 噢易云（噢易云计算） | `oseasy` | 9 | success | 8 |
| 360 | 北森(zhiye.com) | 翼菲科技（翼菲科技） | `robotphoenix` | 9 | success | 8 |
| 361 | 北森(zhiye.com) | 对外招聘门户（神驰机电） | `senci` | 9 | partial | 11 |
| 362 | 北森(zhiye.com) | 希夕智能-校招（希夕智能） | `sunseed` | 9 | success | 8 |
| 363 | 北森(zhiye.com) | 天俱时工程科技集团有限公司（天俱时集团） | `tianjushi` | 9 | success | 8 |
| 364 | 北森(zhiye.com) | 格创通信（浙江）有限公司（格创通信） | `unigroup-gt` | 9 | success | 8 |
| 365 | 北森(zhiye.com) | 益丰校招（益丰集团） | `yfdyf1` | 9 | success | 9 |
| 366 | 北森(zhiye.com) | 藏格矿业股份有限公司（藏格矿业集团） | `zgky` | 9 | success | 8 |
| 367 | 北森(zhiye.com) | 中迅农科（中迅农科） | `zhxcn` | 9 | success | 9 |
| 368 | 北森(zhiye.com) | 安凯（安凯客车） | `ankai` | 8 | success | 8 |
| 369 | 北森(zhiye.com) | 灿芯半导体（灿芯半导体） | `britesemi` | 8 | success | 8 |
| 370 | 北森(zhiye.com) | 国科天迅（国科天迅） | `gktx` | 8 | success | 8 |
| 371 | 北森(zhiye.com) | 恒安集团（恒安集团） | `hengan1` | 8 | success | 8 |
| 372 | 北森(zhiye.com) | 江西洪都航空工业集团有限责任公司（航空工业洪都） | `hongdu` | 8 | success | 8 |
| 373 | 北森(zhiye.com) | KK集团（kk集团） | `kkguan` | 8 | partial | 10 |
| 374 | 北森(zhiye.com) | 招聘公众号（和元生物） | `obiosh` | 8 | success | 11 |
| 375 | 北森(zhiye.com) | 傲雷集团（傲雷集团） | `olight` | 8 | success | 8 |
| 376 | 北森(zhiye.com) | 盛吉盛（盛吉盛半导体） | `sgssemi` | 8 | success | 9 |
| 377 | 北森(zhiye.com) | 圣泉集团（圣泉集团） | `shengquan` | 8 | success | 8 |
| 378 | 北森(zhiye.com) | 赛乐医疗（赛乐医疗） | `sifary` | 8 | success | 8 |
| 379 | 北森(zhiye.com) | 石犀科技（石犀科技&众云网） | `srhino` | 8 | success | 8 |
| 380 | 北森(zhiye.com) | 东莞市盛雄激光先进装备股份有限公司（盛雄激光） | `stronglaser` | 8 | success | 8 |
| 381 | 北森(zhiye.com) | 天地和兴（天地和兴） | `tdhx` | 8 | success | 8 |
| 382 | 北森(zhiye.com) | 深圳泰德激光招聘门户（泰德激光） | `tetelaser` | 8 | success | 8 |
| 383 | 北森(zhiye.com) | 中达集团（厦门中达集团） | `xmzoda` | 8 | success | 8 |
| 384 | 北森(zhiye.com) | 中汇会计师事务所（特殊普通合伙）（中汇会计师事务所） | `zhcpa` | 8 | success | 9 |
| 385 | 北森(zhiye.com) | 中国通号研究设计院集团（中国通号研究设计院集团） | `crscd` | 7 | success | 8 |
| 386 | 北森(zhiye.com) | e签宝招聘官网-杭州天谷信息科技有限公司（e签宝） | `esign` | 7 | success | 8 |
| 387 | 北森(zhiye.com) | 飞博共创（飞博共创） | `feibo` | 7 | success | 8 |
| 388 | 北森(zhiye.com) | 鹏城新能（鹏城新能） | `luxpowertek` | 7 | success | 8 |
| 389 | 北森(zhiye.com) | 新大陆自动识别（新大陆自动识别） | `nlscan` | 7 | success | 8 |
| 390 | 北森(zhiye.com) | 格蓝若（格蓝若） | `oetsky` | 7 | success | 8 |
| 391 | 北森(zhiye.com) | 赛夫集团2026校招（赛夫集团） | `seif1` | 7 | success | 8 |
| 392 | 北森(zhiye.com) | 仕佳光子（仕佳光子） | `sjphotons1` | 7 | success | 8 |
| 393 | 北森(zhiye.com) | 高拓讯达(北京)微电子股份有限公司（高拓讯达） | `altobeam` | 6 | success | 8 |
| 394 | 北森(zhiye.com) | 北汽重卡（北汽重卡） | `baictruck` | 6 | success | 8 |
| 395 | 北森(zhiye.com) | 滨化集团（滨化集团） | `befar` | 6 | success | 8 |
| 396 | 北森(zhiye.com) | 华丞电子（华丞电子） | `bfhc1` | 6 | success | 8 |
| 397 | 北森(zhiye.com) | 外高桥造船（外高桥造船） | `csscsws` | 6 | success | 8 |
| 398 | 北森(zhiye.com) | 方科PCB（方正科技） | `founderpcb` | 6 | success | 9 |
| 399 | 北森(zhiye.com) | 快乐学习（快乐学习） | `histudy` | 6 | success | 8 |
| 400 | 北森(zhiye.com) | 菇娘家（菇娘家） | `hzgnj` | 6 | success | 8 |
| 401 | 北森(zhiye.com) | 九牧王股份有限公司（九牧王集团） | `joeone` | 6 | success | 8 |
| 402 | 北森(zhiye.com) | 柏诚系统科技股份有限公司（柏诚股份） | `jsboth` | 6 | success | 8 |
| 403 | 北森(zhiye.com) | 陈克明食品股份有限公司（陈克明食品） | `kemen` | 6 | success | 8 |
| 404 | 北森(zhiye.com) | 绿城房地产建设管理集团有限公司（绿城管理） | `lcgljt` | 6 | success | 9 |
| 405 | 北森(zhiye.com) | 临工重机（临工重机） | `lgmg` | 6 | success | 8 |
| 406 | 北森(zhiye.com) | 鸣石私募基金（鸣石基金） | `mingshiim` | 6 | success | 8 |
| 407 | 北森(zhiye.com) | 并行集团（并行科技） | `paratera` | 6 | partial | 9 |
| 408 | 北森(zhiye.com) | 瑞鹄股份（瑞鹄集团） | `rayhoo` | 6 | success | 8 |
| 409 | 北森(zhiye.com) | 深圳市尚水智能股份有限公司（尚水智能） | `ss-smartech` | 6 | success | 8 |
| 410 | 北森(zhiye.com) | 航空工业津电（航空工业津电） | `tjaemc` | 6 | partial | 8 |
| 411 | 北森(zhiye.com) | 途牛旅游网（途牛旅游网） | `tuniu` | 6 | success | 8 |
| 412 | 北森(zhiye.com) | 卧安机器人-（卧安机器人） | `woanhome` | 6 | success | 8 |
| 413 | 北森(zhiye.com) | 哈尔滨飞机工业集团有限责任公司（航空工业哈飞） | `aviczp` | 5 | success | 8 |
| 414 | 北森(zhiye.com) | 碧橙数字（碧橙数字） | `bicheng` | 5 | success | 8 |
| 415 | 北森(zhiye.com) | 方达中国（方达医药） | `frontagelab` | 5 | success | 8 |
| 416 | 北森(zhiye.com) | 极客未来招聘门户（新）（极客未来） | `geek3` | 5 | success | 8 |
| 417 | 北森(zhiye.com) | 海亮教育集团（海亮教育科技服务集团） | `hailiang8` | 5 | success | 8 |
| 418 | 北森(zhiye.com) | 继峰座椅（上海继峰座椅有限公司） | `jifengseat` | 5 | success | 8 |
| 419 | 北森(zhiye.com) | 深圳市李森智能有限公司（李森智能） | `lisen` | 5 | success | 8 |
| 420 | 北森(zhiye.com) | 半岛医疗（半岛医疗） | `peninsulalaser` | 5 | success | 10 |
| 421 | 北森(zhiye.com) | 上汽大通汽车有限公司（上汽大通） | `saicmaxus` | 5 | success | 8 |
| 422 | 北森(zhiye.com) | wayon energy campus recruitment for 2027（惟远能源） | `wasionelectric` | 5 | success | 9 |
| 423 | 北森(zhiye.com) | 中国航空工业集团公司西安航空计算技术研究所（航空工业计算所） | `actri` | 4 | success | 7 |
| 424 | 北森(zhiye.com) | 亚中医疗（亚中医疗） | `asiacore` | 4 | success | 7 |
| 425 | 北森(zhiye.com) | 中国电子科技集团公司第三十六研究所0607（中国电科三十六所） | `cetc36` | 4 | success | 7 |
| 426 | 北森(zhiye.com) | 恒运昌校园（恒运昌） | `csl-vacuum` | 4 | success | 7 |
| 427 | 北森(zhiye.com) | 星海图（星海图） | `galaxea` | 4 | success | 7 |
| 428 | 北森(zhiye.com) | 陕西汉德车桥有限公司（汉德车桥） | `hdcq` | 4 | partial | 7 |
| 429 | 北森(zhiye.com) | 哈银消费金融（哈银消费金融） | `hrbbcf1` | 4 | success | 7 |
| 430 | 北森(zhiye.com) | 凯泉（凯泉集团） | `kaiquanhr` | 4 | success | 7 |
| 431 | 北森(zhiye.com) | 明毅私募基金管理有限公司（明毅基金） | `myfund` | 4 | success | 7 |
| 432 | 北森(zhiye.com) | 沈阳飞机工业（航空工业沈飞） | `sacavic` | 4 | success | 7 |
| 433 | 北森(zhiye.com) | WAGO万可（万可中国） | `wago` | 4 | success | 7 |
| 434 | 北森(zhiye.com) | 威卡中国（威卡集团） | `wika` | 4 | success | 7 |
| 435 | 北森(zhiye.com) | 厦门虹鹭（厦门虹鹭钨钼工业有限公司） | `xiamen-honglu` | 4 | success | 7 |
| 436 | 北森(zhiye.com) | 星翰材料（星翰材料） | `xinghanmaterials` | 4 | success | 7 |
| 437 | 北森(zhiye.com) | 云帐房（云帐房） | `yunzhangfang` | 4 | success | 7 |
| 438 | 北森(zhiye.com) | 时代新材（中国中车时代新材） | `zztrp1` | 4 | success | 7 |
| 439 | 北森(zhiye.com) | 华硕科技（苏州）有限公司（华硕） | `asustek` | 3 | success | 6 |
| 440 | 北森(zhiye.com) | 航空工业宝胜（航空工业宝胜） | `avicbs` | 3 | success | 6 |
| 441 | 北森(zhiye.com) | 北京地铁（北京地铁公司） | `bjsubway` | 3 | success | 6 |
| 442 | 北森(zhiye.com) | 长江证券研究所暑期实习（长江证券研究所） | `cjzq3` | 3 | success | 6 |
| 443 | 北森(zhiye.com) | 大王椰（大王椰控股集团） | `dwywood1` | 3 | success | 6 |
| 444 | 北森(zhiye.com) | 科大国创云网招聘门户（科大国创） | `gccloud` | 3 | success | 6 |
| 445 | 北森(zhiye.com) | 市城规公司（广州市城市规划设计有限公司） | `gzupdc` | 3 | success | 6 |
| 446 | 北森(zhiye.com) | 山石网科通信技术股份有限公司（山石网科） | `hillstonenet` | 3 | success | 6 |
| 447 | 北森(zhiye.com) | 诺普信（诺普信） | `noposion` | 3 | success | 6 |
| 448 | 北森(zhiye.com) | 普力通（普力通） | `polyton` | 3 | success | 6 |
| 449 | 北森(zhiye.com) | 青木科技（青木科技） | `qingmutec` | 3 | partial | 9 |
| 450 | 北森(zhiye.com) | 三井住友银行（中国）有限公司（三井住友银行(中国)） | `smbccn` | 3 | success | 6 |
| 451 | 北森(zhiye.com) | 双瑞环境（青岛双瑞海洋环境工程股份有限公司） | `sunrui` | 3 | success | 6 |
| 452 | 北森(zhiye.com) | 浙江横店进出口有限公司（横店进出口） | `hengdian-ie` | 2 | success | 5 |
| 453 | 北森(zhiye.com) | 广之旅（广之旅） | `lngzl` | 2 | success | 5 |
| 454 | 北森(zhiye.com) | 南华期货（南华期货） | `nawaa` | 2 | success | 5 |
| 455 | 北森(zhiye.com) | 上汽通用汽车有限公司（上汽通用&泛亚） | `sgm` | 2 | success | 6 |
| 456 | 北森(zhiye.com) | 兴趣岛（兴趣岛） | `xingqudao` | 2 | success | 5 |
| 457 | 北森(zhiye.com) | 厦门轨道建设发展集团有限公司（厦门地铁） | `xmgdjt` | 2 | success | 6 |
| 458 | 北森(zhiye.com) | 正海磁材-（正海磁材） | `zhmag` | 2 | success | 5 |
| 459 | 北森(zhiye.com) | 七色纺商业连锁有限公司（七色纺） | `7sef` | 1 | success | 4 |
| 460 | 北森(zhiye.com) | 安徽康明斯（安徽康明斯） | `acpl-cummins` | 1 | success | 4 |
| 461 | 北森(zhiye.com) | 广州旭之源科技有限公司（旭之源科技） | `atazpower` | 1 | success | 4 |
| 462 | 北森(zhiye.com) | 迪阿股份有限公司（DR珠宝） | `darryring` | 1 | success | 4 |
| 463 | 北森(zhiye.com) | 新奥集团（新奥能源研究院） | `enn` | 1 | success | 6 |
| 464 | 北森(zhiye.com) | 易盛信息（郑州易盛信息技术有限公司） | `esunny` | 1 | success | 4 |
| 465 | 北森(zhiye.com) | 亿星软件（亿星软件） | `esunsoft` | 1 | success | 4 |
| 466 | 北森(zhiye.com) | 迅销（上海）企业管理咨询有限公司（优衣库全球供应链生产管培） | `frsh` | 1 | partial | 4 |
| 467 | 北森(zhiye.com) | 金山云（金山云） | `jssoft` | 1 | success | 15 |
| 468 | 北森(zhiye.com) | 金杜（金杜律师事务所） | `kwmcareer` | 1 | success | 6 |
| 469 | 北森(zhiye.com) | 无锡理奇（理奇&罗斯） | `richsys1` | 1 | success | 4 |
| 470 | 北森(zhiye.com) | 赛美特招聘门户（赛美特集团） | `semi` | 1 | success | 4 |
| 471 | 北森(zhiye.com) | 国瓷材料招聘门户（国瓷材料） | `sinocera1` | 1 | success | 4 |
| 472 | 北森(zhiye.com) | 韦立国际（韦立国际集团） | `winninggroup` | 1 | success | 4 |
| 473 | 北森(zhiye.com) | 星纵数字（星纵数字） | `yeastar` | 1 | success | 4 |
| 474 | Moka(mokahr.com) | 思瑞浦（思瑞浦） | `3peakic/67894` | 12 | partial | 15 |
| 475 | Moka(mokahr.com) | 芯源微（芯源微） | `688037/144533` | 12 | partial | 15 |
| 476 | Moka(mokahr.com) | 光迅科技（光迅科技） | `accelink/139973` | 12 | partial | 15 |
| 477 | Moka(mokahr.com) | 容知日新（容知日新） | `anhuirohgzhirixin/73950` | 12 | partial | 15 |
| 478 | Moka(mokahr.com) | 安路科技（安路科技） | `anlogic/46366` | 12 | partial | 15 |
| 479 | Moka(mokahr.com) | 安凯微电子（安凯微电子） | `anyka/147131` | 12 | partial | 15 |
| 480 | Moka(mokahr.com) | 爱瑞无线（爱瑞无线） | `arraycomm/70372` | 12 | success | 15 |
| 481 | Moka(mokahr.com) | 翱捷科技（翱捷科技） | `asrmicro/71887` | 12 | partial | 15 |
| 482 | Moka(mokahr.com) | 星尘智能（星尘智能） | `astribot/144862` | 12 | partial | 15 |
| 483 | Moka(mokahr.com) | 宇石空间（宇石空间） | `astronstone/168327` | 12 | partial | 15 |
| 484 | Moka(mokahr.com) | 智源研究院（智源研究院） | `baai/42174` | 12 | partial | 15 |
| 485 | Moka(mokahr.com) | 巴德富集团（巴德富集团） | `batf/144997` | 12 | partial | 15 |
| 486 | Moka(mokahr.com) | 贝瑞基因（贝瑞基因） | `berrygenomics/24086` | 12 | partial | 15 |
| 487 | Moka(mokahr.com) | 倍思奇（倍思奇） | `bestqi/45208` | 12 | partial | 15 |
| 488 | Moka(mokahr.com) | 碧桂园服务（碧桂园服务） | `bgyfw/47073` | 12 | partial | 15 |
| 489 | Moka(mokahr.com) | 玻色量子（玻色量子） | `boseq/140969` | 12 | partial | 15 |
| 490 | Moka(mokahr.com) | 贝泰妮集团（贝泰妮集团） | `botanee/95426` | 12 | partial | 15 |
| 491 | Moka(mokahr.com) | 中国东信（中国东信） | `caih/6773` | 12 | partial | 15 |
| 492 | Moka(mokahr.com) | 加特兰微电子（加特兰微电子） | `calterah/1109` | 12 | partial | 15 |
| 493 | Moka(mokahr.com) | 天华新能（天华新能） | `canmax/140246` | 12 | partial | 15 |
| 494 | Moka(mokahr.com) | 灿瑞科技（灿瑞科技） | `canrui/42687` | 12 | success | 15 |
| 495 | Moka(mokahr.com) | 时代上汽（时代上汽） | `catlhr/142020` | 12 | partial | 15 |
| 496 | Moka(mokahr.com) | 时代天源（时代天源） | `catlhr/182326` | 12 | partial | 15 |
| 497 | Moka(mokahr.com) | 中国网安/三十所（中国网安/三十所） | `cetc30/36270` | 12 | partial | 15 |
| 498 | Moka(mokahr.com) | 科百特（科百特） | `cobetterfilter/141059` | 12 | partial | 15 |
| 499 | Moka(mokahr.com) | 武汉楚兴技术有限公司（武汉楚兴技术有限公司） | `cxtwh/54032` | 12 | partial | 15 |
| 500 | Moka(mokahr.com) | 赛业生物（赛业生物） | `cyagen/100175` | 12 | partial | 15 |
| 501 | Moka(mokahr.com) | DapuStor大普微（DapuStor大普微） | `dapustor/54046` | 12 | partial | 15 |
| 502 | Moka(mokahr.com) | 智新科技股份有限公司（智新科技股份有限公司） | `dfmc/164558` | 12 | partial | 15 |
| 503 | Moka(mokahr.com) | 东风汽车研发总院（东风汽车研发总院） | `dfmc/168424` | 12 | partial | 15 |
| 504 | Moka(mokahr.com) | 多维联合集团（多维联合集团） | `duowei/142740` | 12 | partial | 15 |
| 505 | Moka(mokahr.com) | 燧原科技（燧原科技） | `enflame/168420` | 12 | partial | 15 |
| 506 | Moka(mokahr.com) | 易控智驾（易控智驾） | `eqhr/39786` | 12 | partial | 15 |
| 507 | Moka(mokahr.com) | 力芯微电子（力芯微电子） | `etek/170559` | 12 | partial | 15 |
| 508 | Moka(mokahr.com) | 富特科技（富特科技） | `evtech/47503` | 12 | partial | 15 |
| 509 | Moka(mokahr.com) | 菲亚兰德集团（菲亚兰德集团） | `fairlandgroup/75892` | 12 | partial | 15 |
| 510 | Moka(mokahr.com) | 傅利叶（傅利叶） | `fftai/147078` | 12 | partial | 15 |
| 511 | Moka(mokahr.com) | 丰疆智能（丰疆智能） | `fjdynamics/70012` | 12 | partial | 15 |
| 512 | Moka(mokahr.com) | 复旦微电子集团（复旦微电子集团） | `fmsh/172387` | 12 | partial | 15 |
| 513 | Moka(mokahr.com) | 沃飞长空（沃飞长空） | `geely/94419` | 12 | partial | 15 |
| 514 | Moka(mokahr.com) | 大族激光（大族激光） | `hanslaser/46383` | 12 | partial | 15 |
| 515 | Moka(mokahr.com) | 黑白调集团（黑白调集团） | `heibaidiao/54126` | 12 | partial | 15 |
| 516 | Moka(mokahr.com) | 中国航空工业发展研究中心（中国航空工业发展研究中心） | `hkgyxxzx/148787` | 12 | partial | 15 |
| 517 | Moka(mokahr.com) | 华勤技术（华勤技术） | `hq/101896` | 12 | partial | 15 |
| 518 | Moka(mokahr.com) | 华虹宏力（华虹宏力） | `huahong/74036` | 12 | success | 15 |
| 519 | Moka(mokahr.com) | 航嘉集团（航嘉集团） | `huntkey/172055` | 12 | partial | 15 |
| 520 | Moka(mokahr.com) | 虎牙（虎牙） | `huya/4112` | 12 | partial | 15 |
| 521 | Moka(mokahr.com) | 海光信息（海光信息） | `hygon/169939` | 12 | partial | 15 |
| 522 | Moka(mokahr.com) | ICRD上海集成电路研发中心（ICRD上海集成电路研发中心） | `icrd/126587` | 12 | partial | 15 |
| 523 | Moka(mokahr.com) | 德邦证券（德邦证券） | `imtebon/74049` | 12 | partial | 15 |
| 524 | Moka(mokahr.com) | 盈峰环境（盈峰环境） | `inforeenviro/182015` | 12 | partial | 15 |
| 525 | Moka(mokahr.com) | 青禾晶元（青禾晶元） | `isaber/187877` | 12 | partial | 15 |
| 526 | Moka(mokahr.com) | 易思维（易思维） | `isv-tech/170471` | 12 | partial | 15 |
| 527 | Moka(mokahr.com) | 晶泰科技（晶泰科技） | `jingtai/2143` | 12 | partial | 15 |
| 528 | Moka(mokahr.com) | 景旺电子（景旺电子） | `jingwang/170520` | 12 | partial | 15 |
| 529 | Moka(mokahr.com) | 北京润科（北京润科） | `jingweirunke/170057` | 12 | partial | 15 |
| 530 | Moka(mokahr.com) | 九洲药业（九洲药业） | `jiuzhoupharma/74059` | 12 | partial | 15 |
| 531 | Moka(mokahr.com) | 景嘉微（景嘉微） | `jjw/143541` | 12 | partial | 15 |
| 532 | Moka(mokahr.com) | 江南布衣（江南布衣） | `jnby/94912` | 12 | partial | 15 |
| 533 | Moka(mokahr.com) | 均胜安全（均胜安全） | `joyson/94374` | 12 | success | 15 |
| 534 | Moka(mokahr.com) | 晶盛机电（晶盛机电） | `jsjd/118048` | 12 | partial | 15 |
| 535 | Moka(mokahr.com) | 苏交科（苏交科） | `jsti/144121` | 12 | partial | 15 |
| 536 | Moka(mokahr.com) | 聚芯微电子（聚芯微电子） | `jxw/166492` | 12 | partial | 15 |
| 537 | Moka(mokahr.com) | 科达制造（科达制造） | `kedachina/78371` | 12 | partial | 15 |
| 538 | Moka(mokahr.com) | 电科金仓（电科金仓） | `kingbase/47259` | 12 | partial | 15 |
| 539 | Moka(mokahr.com) | 联软科技（联软科技） | `leagsoft/44599` | 12 | partial | 15 |
| 540 | Moka(mokahr.com) | 雷赛智能（雷赛智能） | `leisai/146886` | 12 | partial | 15 |
| 541 | Moka(mokahr.com) | 领益智造（领益智造） | `lingyiitech/182049` | 12 | partial | 15 |
| 542 | Moka(mokahr.com) | 力勤资源（力勤资源） | `lygend/72100` | 12 | partial | 15 |
| 543 | Moka(mokahr.com) | 玫德集团（玫德集团） | `meidegroup/142830` | 12 | partial | 15 |
| 544 | Moka(mokahr.com) | 佑驾创新（佑驾创新） | `minieye/118571` | 12 | partial | 15 |
| 545 | Moka(mokahr.com) | 得力集团（得力集团） | `nbdeli/70019` | 12 | partial | 15 |
| 546 | Moka(mokahr.com) | 维信诺（维信诺） | `newvisionox/24735` | 12 | partial | 15 |
| 547 | Moka(mokahr.com) | 精臣（精臣） | `niimbot/45368` | 12 | partial | 15 |
| 548 | Moka(mokahr.com) | 华诺星空（华诺星空） | `novasky/146544` | 12 | partial | 15 |
| 549 | Moka(mokahr.com) | 松下集团（松下集团） | `REDACTED` | 12 | partial | 15 |
| 550 | Moka(mokahr.com) | 太平鸟（太平鸟） | `peacebird-women/172603` | 12 | partial | 15 |
| 551 | Moka(mokahr.com) | 菲尼克斯电气（菲尼克斯电气） | `phoenixcontact/172581` | 12 | partial | 15 |
| 552 | Moka(mokahr.com) | 品驰医疗（品驰医疗） | `pinsmedical/2726` | 12 | partial | 15 |
| 553 | Moka(mokahr.com) | 群核科技（群核科技） | `qunhemail/2832` | 12 | partial | 15 |
| 554 | Moka(mokahr.com) | 睿能科技（睿能科技） | `raynen/115955` | 12 | partial | 15 |
| 555 | Moka(mokahr.com) | 仁洁智能科技有限公司（仁洁智能科技有限公司） | `rjzn/144501` | 12 | success | 15 |
| 556 | Moka(mokahr.com) | 森特股份（森特股份） | `sente/151238` | 12 | partial | 15 |
| 557 | Moka(mokahr.com) | 盛趣游戏（盛趣游戏） | `shengqu/96336` | 12 | success | 15 |
| 558 | Moka(mokahr.com) | 时创意（时创意） | `shichuangyi/172086` | 12 | partial | 15 |
| 559 | Moka(mokahr.com) | 欣锐科技（欣锐科技） | `shinry/172541` | 12 | partial | 15 |
| 560 | Moka(mokahr.com) | Shopee（AI Star Program 顶尖技术人）（Shopee（AI Star Program 顶尖技术人）） | `shopee/170008` | 12 | partial | 15 |
| 561 | Moka(mokahr.com) | 舒华体育（舒华体育） | `shuhua/68312` | 12 | partial | 15 |
| 562 | Moka(mokahr.com) | 盛弘股份（盛弘股份） | `sinexcel/74287` | 12 | partial | 15 |
| 563 | Moka(mokahr.com) | 仙乐健康（仙乐健康） | `sirio/166467` | 12 | partial | 15 |
| 564 | Moka(mokahr.com) | 盛合晶微（盛合晶微） | `sjsemi/144842` | 12 | partial | 15 |
| 565 | Moka(mokahr.com) | 深智城集团（深智城集团） | `smartcitysz/95466` | 12 | partial | 15 |
| 566 | Moka(mokahr.com) | 思谋科技（思谋科技） | `smartmore/40506` | 12 | partial | 15 |
| 567 | Moka(mokahr.com) | 晟通集团（晟通集团） | `snto/100022` | 12 | partial | 15 |
| 568 | Moka(mokahr.com) | 开立医疗（开立医疗） | `REDACTED` | 12 | partial | 15 |
| 569 | Moka(mokahr.com) | 中国十五冶（中国十五冶） | `swy/172554` | 12 | partial | 15 |
| 570 | Moka(mokahr.com) | 时代新安（时代新安） | `synland/43559` | 12 | partial | 15 |
| 571 | Moka(mokahr.com) | 腾盾科创（腾盾科创） | `tengden/164567` | 12 | partial | 15 |
| 572 | Moka(mokahr.com) | 天虹数科（天虹数科） | `REDACTED` | 12 | partial | 15 |
| 573 | Moka(mokahr.com) | 星环科技（星环科技） | `transwarp/3196` | 12 | partial | 15 |
| 574 | Moka(mokahr.com) | 紫光同芯（紫光同芯） | `tsinghuaic/39656` | 12 | partial | 15 |
| 575 | Moka(mokahr.com) | UWANT友望（UWANT友望） | `uwant/149092` | 12 | success | 15 |
| 576 | Moka(mokahr.com) | 唯捷创芯（唯捷创芯） | `vanchip/47239` | 12 | partial | 15 |
| 577 | Moka(mokahr.com) | 唯品会（唯品会） | `vipshophr/10039` | 12 | partial | 15 |
| 578 | Moka(mokahr.com) | 烽火通信（烽火通信） | `whfhtx/73922` | 12 | partial | 15 |
| 579 | Moka(mokahr.com) | 微泰医疗（微泰医疗） | `wt/182139` | 12 | partial | 15 |
| 580 | Moka(mokahr.com) | 舞肌科技（舞肌科技） | `wuji/145173` | 12 | partial | 15 |
| 581 | Moka(mokahr.com) | 传化智联（传化智联） | `wynca/118027` | 12 | partial | 15 |
| 582 | Moka(mokahr.com) | 传化集团（传化集团） | `wynca/141115` | 12 | partial | 15 |
| 583 | Moka(mokahr.com) | 星邦智能（星邦智能） | `xingbang/67958` | 12 | partial | 15 |
| 584 | Moka(mokahr.com) | 欣贺股份（欣贺股份） | `xinhee/168514` | 12 | partial | 15 |
| 585 | Moka(mokahr.com) | 希望学（希望学） | `xiwang/146380` | 12 | partial | 15 |
| 586 | Moka(mokahr.com) | 银华基金（银华基金） | `yhfund/143004` | 12 | partial | 15 |
| 587 | Moka(mokahr.com) | 融捷能源（融捷能源） | `youngy/166533` | 12 | partial | 15 |
| 588 | Moka(mokahr.com) | 日邮物流（日邮物流） | `yusen/73956` | 12 | partial | 15 |
| 589 | Moka(mokahr.com) | 宇通集团（宇通集团） | `yutong/172567` | 12 | partial | 15 |
| 590 | Moka(mokahr.com) | 德佑（德佑） | `yxws/168223` | 12 | partial | 15 |
| 591 | Moka(mokahr.com) | 紫金矿业（紫金矿业） | `zijinmining/117957` | 12 | partial | 15 |
| 592 | Moka(mokahr.com) | 杉川集团（杉川集团） | `3irobotics/147137` | 11 | partial | 15 |
| 593 | Moka(mokahr.com) | 兄弟科技（兄弟科技） | `brother/150716` | 11 | partial | 15 |
| 594 | Moka(mokahr.com) | 太平洋产险安徽分公司（太平洋产险安徽分公司） | `cpicproperty/150956` | 11 | partial | 15 |
| 595 | Moka(mokahr.com) | 东风汽车-猛士汽车（东风汽车-猛士汽车） | `dfmc/168535` | 11 | partial | 15 |
| 596 | Moka(mokahr.com) | 燕东微（燕东微） | `dkjc/142338` | 11 | partial | 15 |
| 597 | Moka(mokahr.com) | 快仓机器人（快仓机器人） | `flashhold/40527` | 11 | success | 14 |
| 598 | Moka(mokahr.com) | 福特中国（福特中国） | `ford/43706` | 11 | success | 14 |
| 599 | Moka(mokahr.com) | 兆易创新（兆易创新） | `gigadevice/92215` | 11 | partial | 15 |
| 600 | Moka(mokahr.com) | 国泰君安期货（国泰君安期货） | `gtjaqh/136276` | 11 | success | 14 |
| 601 | Moka(mokahr.com) | 禾迈股份（禾迈股份） | `hoymiles/70377` | 11 | partial | 15 |
| 602 | Moka(mokahr.com) | 上海华力（上海华力） | `huahong/70000` | 11 | partial | 15 |
| 603 | Moka(mokahr.com) | 华虹集团（华虹集团） | `huahong/78009` | 11 | partial | 15 |
| 604 | Moka(mokahr.com) | 智融科技（智融科技） | `ismartware/69961` | 11 | success | 14 |
| 605 | Moka(mokahr.com) | 清原农冠（清原农冠） | `kingagroot/56082` | 11 | partial | 15 |
| 606 | Moka(mokahr.com) | 顾家家居（顾家家居） | `kuka/172508` | 11 | partial | 15 |
| 607 | Moka(mokahr.com) | 中国联塑集团（中国联塑集团） | `lesso/70303` | 11 | success | 14 |
| 608 | Moka(mokahr.com) | 敏芯股份（敏芯股份） | `memsensing/45045` | 11 | success | 14 |
| 609 | Moka(mokahr.com) | 沐曦股份（沐曦股份） | `metax-tech/58131` | 11 | partial | 15 |
| 610 | Moka(mokahr.com) | 伏达半导体（伏达半导体） | `nuvoltatech/29077` | 11 | success | 14 |
| 611 | Moka(mokahr.com) | 奇瑞捷豹路虎-FREELANDER神行者（奇瑞捷豹路虎-FREELANDER神行者） | `REDACTED` | 11 | partial | 15 |
| 612 | Moka(mokahr.com) | 锐捷网络（锐捷网络） | `ruijie/136206` | 11 | partial | 15 |
| 613 | Moka(mokahr.com) | 三福（三福） | `sanfu/46833` | 11 | partial | 15 |
| 614 | Moka(mokahr.com) | 精智达（精智达） | `seichitech/140888` | 11 | partial | 15 |
| 615 | Moka(mokahr.com) | 申菱环境（申菱环境） | `shenling/164368` | 11 | partial | 15 |
| 616 | Moka(mokahr.com) | 艾罗能源（艾罗能源） | `solaxpower/151401` | 11 | partial | 15 |
| 617 | Moka(mokahr.com) | 阶跃星辰（阶跃星辰） | `step/141903` | 11 | success | 14 |
| 618 | Moka(mokahr.com) | 申通快递（申通快递） | `sto/126265` | 11 | partial | 15 |
| 619 | Moka(mokahr.com) | 钛动科技（钛动科技） | `tec-do/41717` | 11 | partial | 15 |
| 620 | Moka(mokahr.com) | 微步在线（微步在线） | `threatbook/39679` | 11 | partial | 15 |
| 621 | Moka(mokahr.com) | 万物云（万物云） | `vanke/147055` | 11 | partial | 15 |
| 622 | Moka(mokahr.com) | 温氏股份（温氏股份） | `wens/92366` | 11 | partial | 15 |
| 623 | Moka(mokahr.com) | 药明合联（药明合联） | `wuxixdc/164236` | 11 | partial | 15 |
| 624 | Moka(mokahr.com) | 迅雷X-PEP产品星计划（迅雷X-PEP产品星计划） | `xunlei/26600` | 11 | success | 14 |
| 625 | Moka(mokahr.com) | 源氏木语（源氏木语） | `yeswood/142521` | 11 | partial | 15 |
| 626 | Moka(mokahr.com) | 银河通用机器人（银河通用机器人） | `yinhetongyong/165930` | 11 | partial | 15 |
| 627 | Moka(mokahr.com) | 银轮股份（银轮股份） | `yinlun/128571` | 11 | partial | 15 |
| 628 | Moka(mokahr.com) | 中创智领集团（中创智领集团） | `zczl/172433` | 11 | partial | 15 |
| 629 | Moka(mokahr.com) | 紫龙游戏（紫龙游戏） | `zlongame/140110` | 11 | success | 14 |
| 630 | Moka(mokahr.com) | 博思软件（博思软件） | `bosssoft/68370` | 10 | success | 13 |
| 631 | Moka(mokahr.com) | 中国能建葛洲坝集团（中国能建葛洲坝集团） | `cggc/145102` | 10 | partial | 15 |
| 632 | Moka(mokahr.com) | 芯慧微（芯慧微） | `cwisemicro/182011` | 10 | success | 13 |
| 633 | Moka(mokahr.com) | 德康集团（德康集团） | `dekangmuye/151636` | 10 | partial | 15 |
| 634 | Moka(mokahr.com) | 当升科技（当升科技） | `easpring/102152` | 10 | partial | 15 |
| 635 | Moka(mokahr.com) | 极智嘉（极智嘉） | `REDACTED` | 10 | partial | 15 |
| 636 | Moka(mokahr.com) | 吉客印（吉客印） | `giikin/94708` | 10 | partial | 14 |
| 637 | Moka(mokahr.com) | 古茗茶饮（古茗茶饮） | `guming/39377` | 10 | partial | 15 |
| 638 | Moka(mokahr.com) | 方舟健客（方舟健客） | `jianke-fangzhou/44310` | 10 | success | 13 |
| 639 | Moka(mokahr.com) | 九牧集团（九牧集团） | `jomoo/142937` | 10 | partial | 15 |
| 640 | Moka(mokahr.com) | 立敏达科技（立敏达科技） | `lingyiitech/172618` | 10 | success | 13 |
| 641 | Moka(mokahr.com) | 龙旗科技（龙旗科技） | `longcheer/166561` | 10 | partial | 15 |
| 642 | Moka(mokahr.com) | 舜宇集团（舜宇集团） | `sunnyoptical/45602` | 10 | partial | 15 |
| 643 | Moka(mokahr.com) | 天马微电子（天马微电子） | `tianma/170490` | 10 | partial | 15 |
| 644 | Moka(mokahr.com) | 衡泰技术（衡泰技术） | `xquant/45053` | 10 | success | 13 |
| 645 | Moka(mokahr.com) | 中控信息（中控信息） | `zkxx/182327` | 10 | success | 13 |
| 646 | Moka(mokahr.com) | 巨一科技（巨一科技） | `ahjy/168235` | 9 | partial | 15 |
| 647 | Moka(mokahr.com) | 安捷利美维（安捷利美维） | `akmmv/45089` | 9 | partial | 15 |
| 648 | Moka(mokahr.com) | 安谋科技（安谋科技） | `REDACTED` | 9 | partial | 15 |
| 649 | Moka(mokahr.com) | 芯粤能半导体（芯粤能半导体） | `ascenpower/166280` | 9 | success | 12 |
| 650 | Moka(mokahr.com) | 百诺医药（百诺医药） | `bestcomm/43337` | 9 | partial | 13 |
| 651 | Moka(mokahr.com) | BIGO（BIGO） | `bigo/1018` | 9 | partial | 15 |
| 652 | Moka(mokahr.com) | 蓝光智能（蓝光智能） | `blovelight/45215` | 9 | success | 12 |
| 653 | Moka(mokahr.com) | 博世中国（博世中国） | `bosch/168626` | 9 | partial | 15 |
| 654 | Moka(mokahr.com) | 邦盛科技（邦盛科技） | `bsfit/1076` | 9 | success | 12 |
| 655 | Moka(mokahr.com) | DolphinDB（DolphinDB） | `dolphindb/101962` | 9 | success | 15 |
| 656 | Moka(mokahr.com) | 云和恩墨（云和恩墨） | `enmotech/47098` | 9 | partial | 15 |
| 657 | Moka(mokahr.com) | 飞步科技（飞步科技） | `fabu/56114` | 9 | success | 12 |
| 658 | Moka(mokahr.com) | 海艺互娱（海艺互娱） | `haiyi/150699` | 9 | partial | 15 |
| 659 | Moka(mokahr.com) | 和而泰（和而泰） | `het0000001/142804` | 9 | partial | 15 |
| 660 | Moka(mokahr.com) | 禾丰股份（禾丰股份） | `hfsp/37149` | 9 | success | 12 |
| 661 | Moka(mokahr.com) | 挚文集团（挚文集团） | `immomo/54299` | 9 | partial | 15 |
| 662 | Moka(mokahr.com) | 因诺资产（因诺资产） | `innoam/142310` | 9 | success | 12 |
| 663 | Moka(mokahr.com) | 无忧传媒（无忧传媒） | `joymedia/7674` | 9 | partial | 15 |
| 664 | Moka(mokahr.com) | 有道领世（有道领世） | `lingshi/144566` | 9 | partial | 15 |
| 665 | Moka(mokahr.com) | 凌云光（凌云光） | `lusterinc/44882` | 9 | partial | 15 |
| 666 | Moka(mokahr.com) | 茉莉数科集团（茉莉数科集团） | `molimediagrouphr/171878` | 9 | success | 15 |
| 667 | Moka(mokahr.com) | 绿盟科技（绿盟科技） | `nsfocus/29118` | 9 | partial | 15 |
| 668 | Moka(mokahr.com) | NVIDIA英伟达（NVIDIA英伟达） | `nvidia/47111` | 9 | partial | 15 |
| 669 | Moka(mokahr.com) | 人形机器人（人形机器人） | `openloong/164448` | 9 | partial | 15 |
| 670 | Moka(mokahr.com) | 深信服（深信服） | `sangfor/27944` | 9 | partial | 15 |
| 671 | Moka(mokahr.com) | SGS（SGS） | `sgs/74104` | 9 | partial | 15 |
| 672 | Moka(mokahr.com) | 顺络电子（顺络电子） | `sunlord/172521` | 9 | success | 12 |
| 673 | Moka(mokahr.com) | 九坤投资（九坤投资） | `ubiquantrecruit/37031` | 9 | partial | 15 |
| 674 | Moka(mokahr.com) | 维谛技术(Vertiv)（维谛技术(Vertiv)） | `vertiv/118713` | 9 | partial | 15 |
| 675 | Moka(mokahr.com) | 为旌科技（为旌科技） | `visinextek/41636` | 9 | partial | 15 |
| 676 | Moka(mokahr.com) | 新达盟-珠海万达商管|银翼投资（新达盟-珠海万达商管|银翼投资） | `wandacm/164049` | 9 | partial | 15 |
| 677 | Moka(mokahr.com) | 奥特维集团（奥特维集团） | `wxautowell/45558` | 9 | partial | 15 |
| 678 | Moka(mokahr.com) | 驭势科技（驭势科技） | `yushi/3773` | 9 | partial | 15 |
| 679 | Moka(mokahr.com) | 众安保险（众安保险） | `zhongan/71908` | 9 | partial | 15 |
| 680 | Moka(mokahr.com) | 智谱（智谱） | `zphz/148984` | 9 | success | 12 |
| 681 | Moka(mokahr.com) | 跨维智能（跨维智能） | `dexforce/149228` | 8 | success | 11 |
| 682 | Moka(mokahr.com) | 飞鱼科技（飞鱼科技） | `feiyu/142123` | 8 | success | 11 |
| 683 | Moka(mokahr.com) | 鸿芯微纳（鸿芯微纳） | `giga-da/26752` | 8 | success | 11 |
| 684 | Moka(mokahr.com) | 微源半导体（微源半导体） | `lowpowersemi/168412` | 8 | success | 11 |
| 685 | Moka(mokahr.com) | 梅塞尔中国（梅塞尔中国） | `messer/92849` | 8 | success | 11 |
| 686 | Moka(mokahr.com) | 南孚集团（南孚集团） | `nanfu/39842` | 8 | success | 11 |
| 687 | Moka(mokahr.com) | 杉数科技（杉数科技） | `shanshu/57987` | 8 | partial | 15 |
| 688 | Moka(mokahr.com) | 天弘基金（天弘基金） | `thfund/46219` | 8 | success | 14 |
| 689 | Moka(mokahr.com) | 腾竞体育（腾竞体育） | `tjsports/142880` | 8 | success | 11 |
| 690 | Moka(mokahr.com) | 天津雅迪（天津雅迪） | `yadea/26985` | 8 | partial | 15 |
| 691 | Moka(mokahr.com) | 玉柴集团（玉柴集团） | `yuchai/140075` | 8 | partial | 15 |
| 692 | Moka(mokahr.com) | 正定私募（正定私募） | `zding/117879` | 8 | success | 11 |
| 693 | Moka(mokahr.com) | 中环领先半导体（中环领先半导体） | `zhlx/146852` | 8 | success | 11 |
| 694 | Moka(mokahr.com) | 爱德万测试（爱德万测试） | `advantest/144999` | 7 | success | 10 |
| 695 | Moka(mokahr.com) | 道远咨询（道远咨询） | `blackhills/76097` | 7 | partial | 11 |
| 696 | Moka(mokahr.com) | 博世中国•智行学院（博世中国•智行学院） | `bosch/151492` | 7 | partial | 15 |
| 697 | Moka(mokahr.com) | 达梦数据（达梦数据） | `dameng/170579` | 7 | success | 10 |
| 698 | Moka(mokahr.com) | 佛吉亚（佛吉亚） | `REDACTED` | 7 | partial | 15 |
| 699 | Moka(mokahr.com) | 福龙马集团（福龙马集团） | `fjlm/128157` | 7 | success | 13 |
| 700 | Moka(mokahr.com) | 广电运通集团（广电运通集团） | `grgbanking/39448` | 7 | partial | 15 |
| 701 | Moka(mokahr.com) | 海能达（海能达） | `REDACTED` | 7 | partial | 15 |
| 702 | Moka(mokahr.com) | 科华集团（科华集团） | `kehua/92510` | 7 | partial | 15 |
| 703 | Moka(mokahr.com) | 九号公司（九号公司） | `ninebot/45627` | 7 | partial | 15 |
| 704 | Moka(mokahr.com) | 睿励（睿励） | `ruili/43376` | 7 | success | 10 |
| 705 | Moka(mokahr.com) | 芯驰科技（芯驰科技） | `semidrive/42941` | 7 | success | 10 |
| 706 | Moka(mokahr.com) | 广立微（广立微） | `semitronix/140043` | 7 | partial | 15 |
| 707 | Moka(mokahr.com) | 水星家纺（水星家纺） | `shuixing/68039` | 7 | success | 10 |
| 708 | Moka(mokahr.com) | 思摩尔国际（思摩尔国际） | `smoore/150918` | 7 | partial | 15 |
| 709 | Moka(mokahr.com) | 天演资本（天演资本） | `tianyancapital/98902` | 7 | success | 13 |
| 710 | Moka(mokahr.com) | 未来一手（未来一手） | `weilaiyishou/145029` | 7 | success | 10 |
| 711 | Moka(mokahr.com) | 杭州炎魂网络（杭州炎魂网络） | `yanhun/24017` | 7 | partial | 15 |
| 712 | Moka(mokahr.com) | 微观博易（微观博易） | `bjwgby/118127` | 6 | success | 15 |
| 713 | Moka(mokahr.com) | 邦戴数科（邦戴数科） | `bonditech/143553` | 6 | success | 9 |
| 714 | Moka(mokahr.com) | 东风汽车集团有限公司（东风汽车集团有限公司） | `dfmc/164438` | 6 | partial | 15 |
| 715 | Moka(mokahr.com) | 鸿钧微电子（鸿钧微电子） | `hjmicro/54317` | 6 | success | 9 |
| 716 | Moka(mokahr.com) | 见山科技（见山科技） | `jianshankeji/100134` | 6 | success | 9 |
| 717 | Moka(mokahr.com) | 招银云创（招银云创） | `mbcloud/150116` | 6 | success | 9 |
| 718 | Moka(mokahr.com) | 明源云（明源云） | `mingyuan/168644` | 6 | success | 9 |
| 719 | Moka(mokahr.com) | Monee（Monee） | `shopee/2962` | 6 | partial | 15 |
| 720 | Moka(mokahr.com) | 平方和投资（平方和投资） | `alpha2fund/151124` | 5 | success | 8 |
| 721 | Moka(mokahr.com) | 保融科技（保融科技） | `baorong/25901` | 5 | success | 8 |
| 722 | Moka(mokahr.com) | 复星财富控股（复星财富控股） | `fosunwealth/146703` | 5 | success | 8 |
| 723 | Moka(mokahr.com) | GE医疗（GE医疗） | `gehc/142250` | 5 | success | 11 |
| 724 | Moka(mokahr.com) | 均胜（均胜） | `joyson/94311` | 5 | partial | 15 |
| 725 | Moka(mokahr.com) | 睿恩新能源（睿恩新能源） | `ruien/140574` | 5 | success | 8 |
| 726 | Moka(mokahr.com) | 舜宇-校园大使（舜宇-校园大使） | `sunnyoptical/146167` | 5 | success | 8 |
| 727 | Moka(mokahr.com) | 申万宏源证券分支机构（申万宏源证券分支机构） | `swhysc-job/166086` | 5 | partial | 15 |
| 728 | Moka(mokahr.com) | 星德科（星德科） | `syntegon/42656` | 5 | success | 8 |
| 729 | Moka(mokahr.com) | 大众汽车集团（中国）（大众汽车集团（中国）） | `vwa/168597` | 5 | partial | 13 |
| 730 | Moka(mokahr.com) | 多比特信息（多比特信息） | `wedobest/46167` | 5 | success | 8 |
| 731 | Moka(mokahr.com) | 雅砻江水电（雅砻江水电） | `ylhdc/95551` | 5 | success | 8 |
| 732 | Moka(mokahr.com) | 中国电科28所（中国电科28所） | `cetcles/40889` | 4 | success | 7 |
| 733 | Moka(mokahr.com) | 寅成智能（寅成智能） | `chaocanshu/45562` | 4 | success | 10 |
| 734 | Moka(mokahr.com) | 望尘科技（望尘科技） | `galasports/98034` | 4 | success | 7 |
| 735 | Moka(mokahr.com) | 乐元素SH工作室（乐元素SH工作室） | `leyuansu/2357` | 4 | success | 7 |
| 736 | Moka(mokahr.com) | 牧原（牧原） | `muyuan/145076` | 4 | partial | 15 |
| 737 | Moka(mokahr.com) | 新中大科技（新中大科技） | `newgrand/151701` | 4 | success | 7 |
| 738 | Moka(mokahr.com) | 联咏科技（联咏科技） | `novatek/182224` | 4 | success | 7 |
| 739 | Moka(mokahr.com) | 行芯科技（行芯科技） | `phlexing/100123` | 4 | success | 7 |
| 740 | Moka(mokahr.com) | 斯堪尼亚（斯堪尼亚） | `scania/168376` | 4 | success | 10 |
| 741 | Moka(mokahr.com) | 信雅达（信雅达） | `sunyard/43203` | 4 | success | 7 |
| 742 | Moka(mokahr.com) | 中微公司（中微公司） | `amec/4362` | 3 | partial | 15 |
| 743 | Moka(mokahr.com) | 嘉士伯中国（嘉士伯中国） | `REDACTED` | 3 | success | 6 |
| 744 | Moka(mokahr.com) | 中信戴卡（中信戴卡） | `dicastal/140651` | 3 | success | 6 |
| 745 | Moka(mokahr.com) | Garena（Garena） | `REDACTED` | 3 | partial | 15 |
| 746 | Moka(mokahr.com) | 格兰云天（格兰云天） | `gshm/172184` | 3 | success | 6 |
| 747 | Moka(mokahr.com) | 中科光电（中科光电） | `hdzn/151324` | 3 | partial | 15 |
| 748 | Moka(mokahr.com) | 毕马威（毕马威） | `kpmg/76195` | 3 | partial | 15 |
| 749 | Moka(mokahr.com) | Peet's皮爷咖啡（Peet's皮爷咖啡） | `peets/118888` | 3 | success | 6 |
| 750 | Moka(mokahr.com) | 卓识基金（卓识基金） | `zsquant/36544` | 3 | partial | 15 |
| 751 | Moka(mokahr.com) | 世纪前沿（世纪前沿） | `centuryfrontier/24842` | 2 | success | 5 |
| 752 | Moka(mokahr.com) | 华钧广汇（华钧广汇） | `genwealth/142156` | 2 | success | 5 |
| 753 | Moka(mokahr.com) | 厨芯科技（厨芯科技） | `honganrobots/150155` | 2 | success | 8 |
| 754 | Moka(mokahr.com) | 天岳先进（天岳先进） | `sicc/140187` | 2 | success | 5 |
| 755 | Moka(mokahr.com) | 搜狐（搜狐） | `sohu/28313` | 2 | success | 10 |
| 756 | Moka(mokahr.com) | 途拓（途拓） | `totopcreatives/102100` | 2 | success | 5 |
| 757 | Moka(mokahr.com) | 阿吉豆（阿吉豆） | `yunhonggroup/140309` | 2 | partial | 6 |
| 758 | Moka(mokahr.com) | 众安（众安） | `zhongan/148589` | 2 | success | 5 |
| 759 | Moka(mokahr.com) | 阿斯利康中国（阿斯利康中国） | `REDACTED` | 1 | success | 4 |
| 760 | Moka(mokahr.com) | 点众科技（点众科技） | `dianzhong/28122` | 1 | success | 4 |
| 761 | Moka(mokahr.com) | 涵德投资（涵德投资） | `handetouzi/46040` | 1 | success | 4 |
| 762 | Moka(mokahr.com) | 进芯科技（进芯科技） | `hnjxkjgf/168579` | 1 | partial | 9 |
| 763 | Moka(mokahr.com) | IXM埃珂森（IXM埃珂森） | `ixmetals/182262` | 1 | success | 4 |
| 764 | Moka(mokahr.com) | 鲸灵（鲸灵） | `jingling/125951` | 1 | success | 4 |
| 765 | Moka(mokahr.com) | 曼伦（曼伦） | `manon/94861` | 1 | success | 4 |
| 766 | Moka(mokahr.com) | 昂立教育（昂立教育） | `onlyedu/144926` | 1 | partial | 10 |
| 767 | Moka(mokahr.com) | Sea（Sea） | `shopee/170435` | 1 | success | 4 |
| 768 | Moka(mokahr.com) | 沃尔沃汽车（沃尔沃汽车） | `REDACTED` | 1 | success | 4 |
| 769 | Moka(mokahr.com) | 延锋（延锋） | `yanfeng/45086` | 1 | partial | 15 |
| 770 | Moka(mokahr.com) | 姚品国际（姚品国际） | `ypgj/164305` | 1 | success | 4 |
| 771 | Moka(mokahr.com) | 紫金矿业-校园大使（紫金矿业-校园大使） | `zijinmining/166497` | 1 | success | 4 |
| 772 | 飞书招聘(jobs.feishu.cn) | 黑湖科技（黑湖科技） | `blacklake` | 13 | success | 15 |
| 773 | 飞书招聘(jobs.feishu.cn) | 湖北三宁化工股份有限公司（三宁化工） | `ealklohoih0` | 13 | success | 15 |
| 774 | 飞书招聘(jobs.feishu.cn) | 黑格科技（黑格科技） | `heygears` | 13 | success | 15 |
| 775 | 飞书招聘(jobs.feishu.cn) | 亚信（亚信安全） | `asiainfo-sec` | 12 | success | 14 |
| 776 | 飞书招聘(jobs.feishu.cn) | 智遨通（天津）信息技术股份有限公司（新紫光集团前沿技术研究院） | `brightchip` | 12 | partial | 14 |
| 777 | 飞书招聘(jobs.feishu.cn) | 北京电子数智科技有限责任公司（北电数智） | `caz6yhvgk5z` | 12 | partial | 14 |
| 778 | 飞书招聘(jobs.feishu.cn) | 永卓控股有限公司（永卓控股） | `everrising` | 12 | partial | 14 |
| 779 | 飞书招聘(jobs.feishu.cn) | Flexiv（穹彻智能） | `flexivrobotics` | 12 | partial | 14 |
| 780 | 飞书招聘(jobs.feishu.cn) | 广发基金（广发基金） | `gffunds` | 12 | partial | 14 |
| 781 | 飞书招聘(jobs.feishu.cn) | 高域科技（广汽高域） | `govy` | 12 | success | 14 |
| 782 | 飞书招聘(jobs.feishu.cn) | 北京趣拿软件科技有限公司（去哪儿旅行） | `hf7l9aiqzx` | 12 | partial | 14 |
| 783 | 飞书招聘(jobs.feishu.cn) | 华娱网络（华娱游戏） | `huayugames` | 12 | partial | 14 |
| 784 | 飞书招聘(jobs.feishu.cn) | 北京发那科机电有限公司（北京发那科） | `iwhih7is28` | 12 | partial | 14 |
| 785 | 飞书招聘(jobs.feishu.cn) | 深圳艾麦供应链服务有限公司（iMile） | `j1szxceol43` | 12 | partial | 14 |
| 786 | 飞书招聘(jobs.feishu.cn) | 江苏国泰汉帛实业发展有限公司（国泰汉帛） | `jvvyvrptdzz` | 12 | partial | 14 |
| 787 | 飞书招聘(jobs.feishu.cn) | 卡尔动力（卡尔动力） | `kargobot` | 12 | partial | 14 |
| 788 | 飞书招聘(jobs.feishu.cn) | 北京乐信圣文科技有限责任公司（乐信圣文） | `learnings` | 12 | success | 14 |
| 789 | 飞书招聘(jobs.feishu.cn) | 美宜佳控股有限公司（美宜佳） | `meiyijia` | 12 | partial | 14 |
| 790 | 飞书招聘(jobs.feishu.cn) | OBSBOT寻影（OBSBOT寻影） | `n8r2cr07gk` | 12 | partial | 15 |
| 791 | 飞书招聘(jobs.feishu.cn) | 国民技术股份有限公司（国民技术） | `nsingtech` | 12 | partial | 14 |
| 792 | 飞书招聘(jobs.feishu.cn) | 启元业务部（启元机器人） | `primebot` | 12 | partial | 15 |
| 793 | 飞书招聘(jobs.feishu.cn) | 鸿擎科技（鸿擎科技） | `qcnhg4ksaiwt` | 12 | partial | 14 |
| 794 | 飞书招聘(jobs.feishu.cn) | 新石器（新石器） | `r3c0qt6yjw` | 12 | partial | 14 |
| 795 | 飞书招聘(jobs.feishu.cn) | 雷鸟科技（雷鸟科技） | `rcnrrgo8je7j` | 12 | partial | 14 |
| 796 | 飞书招聘(jobs.feishu.cn) | 思朗科技（思朗科技） | `smartlogictech` | 12 | partial | 14 |
| 797 | 飞书招聘(jobs.feishu.cn) | 致欧家居（致欧家居） | `songmicshome` | 12 | partial | 14 |
| 798 | 飞书招聘(jobs.feishu.cn) | 上海星环聚能科技有限公司（星环聚能） | `startorus` | 12 | partial | 14 |
| 799 | 飞书招聘(jobs.feishu.cn) | 算苗科技（北京）有限公司（算苗科技） | `sunmmio1104` | 12 | partial | 14 |
| 800 | 飞书招聘(jobs.feishu.cn) | 水羊（水羊集团） | `syounggroup` | 12 | partial | 14 |
| 801 | 飞书招聘(jobs.feishu.cn) | 电子所（上海航天电子技术研究所） | `toa7dmu9bq` | 12 | partial | 14 |
| 802 | 飞书招聘(jobs.feishu.cn) | 紫光青藤（紫光青藤） | `tsingtengms` | 12 | success | 14 |
| 803 | 飞书招聘(jobs.feishu.cn) | 记忆科技（深圳）有限公司（记忆科技） | `varp4lp3dbc` | 12 | partial | 15 |
| 804 | 飞书招聘(jobs.feishu.cn) | 九方智投控股（九方智投） | `vcnuqm4lv2uh` | 12 | partial | 14 |
| 805 | 飞书招聘(jobs.feishu.cn) | 水滴公司（水滴公司） | `wdh` | 12 | partial | 14 |
| 806 | 飞书招聘(jobs.feishu.cn) | 桂林啄木鸟医疗（啄木鸟医疗） | `z1zgmci7a8s` | 12 | partial | 14 |
| 807 | 飞书招聘(jobs.feishu.cn) | 苏州旭创科技有限公司（中际旭创） | `zj-innolight` | 12 | partial | 15 |
| 808 | 飞书招聘(jobs.feishu.cn) | 洋葱学园（洋葱学园） | `guanghe` | 11 | partial | 14 |
| 809 | 飞书招聘(jobs.feishu.cn) | 仙工智能（仙工智能） | `seer-group` | 11 | success | 13 |
| 810 | 飞书招聘(jobs.feishu.cn) | 远峰科技股份有限公司（远峰科技） | `yftech2012` | 11 | success | 13 |
| 811 | 飞书招聘(jobs.feishu.cn) | 顾诺集团（顾诺集团） | `gunuojituan` | 10 | success | 12 |
| 812 | 飞书招聘(jobs.feishu.cn) | Uni-MIND（美恒公司） | `intellicrane` | 10 | success | 12 |
| 813 | 飞书招聘(jobs.feishu.cn) | 乐刻运动（乐刻运动） | `leoao-inc` | 10 | success | 12 |
| 814 | 飞书招聘(jobs.feishu.cn) | Bambulab（拓竹科技） | `bambulab` | 9 | partial | 14 |
| 815 | 飞书招聘(jobs.feishu.cn) | 波克科技集团（波克） | `boke` | 9 | partial | 13 |
| 816 | 飞书招聘(jobs.feishu.cn) | 上海大裂谷智能科技有限公司（Sharpa） | `fcn5hvc5qbfs` | 9 | partial | 13 |
| 817 | 飞书招聘(jobs.feishu.cn) | 中邮消费金融有限公司（中邮消费金融） | `is35svcbne` | 9 | success | 11 |
| 818 | 飞书招聘(jobs.feishu.cn) | 会通新材料股份有限公司（会通股份） | `orinko-ht` | 9 | success | 11 |
| 819 | 飞书招聘(jobs.feishu.cn) | 微派网络（微派网络） | `wepie` | 9 | success | 11 |
| 820 | 飞书招聘(jobs.feishu.cn) | 永辉超市（永辉超市） | `yonghui` | 9 | partial | 14 |
| 821 | 飞书招聘(jobs.feishu.cn) | 歌尔丹拿（歌尔丹拿） | `k13pqewe7i` | 8 | success | 10 |
| 822 | 飞书招聘(jobs.feishu.cn) | 千曙科技（千曙科技） | `tranxmart` | 8 | success | 10 |
| 823 | 飞书招聘(jobs.feishu.cn) | 深圳市其域创新科技有限公司（其域创新） | `pecivkvtit` | 7 | partial | 14 |
| 824 | 飞书招聘(jobs.feishu.cn) | 清程极智（清程极智） | `chitu-ai` | 6 | success | 8 |
| 825 | 飞书招聘(jobs.feishu.cn) | 海亮集团有限公司（海亮教育科技服务集团） | `hailiang` | 6 | success | 8 |
| 826 | 飞书招聘(jobs.feishu.cn) | 天竺灵山（舒客电商） | `tianzhulingshan` | 6 | success | 8 |
| 827 | 飞书招聘(jobs.feishu.cn) | 无问芯穹（无问芯穹） | `infinigence` | 5 | success | 7 |
| 828 | 飞书招聘(jobs.feishu.cn) | 梅花生物科技集团股份有限公司（梅花集团） | `j8fq0c3gg7` | 5 | success | 7 |
| 829 | 飞书招聘(jobs.feishu.cn) | 深圳众擎机器人科技股份有限公司（众擎机器） | `dx3a2bminsq` | 4 | success | 6 |
| 830 | 飞书招聘(jobs.feishu.cn) | 回响科技（千岛） | `echotech` | 4 | success | 6 |
| 831 | 飞书招聘(jobs.feishu.cn) | MetaApp（MetaApp） | `meta` | 4 | success | 6 |
| 832 | 飞书招聘(jobs.feishu.cn) | 博瑞精芯（珠海博瑞精芯） | `ucn8mrbdnw7i` | 4 | success | 6 |
| 833 | 飞书招聘(jobs.feishu.cn) | 灵动时刻（VivixAI） | `vivix-ai` | 4 | success | 6 |
| 834 | 飞书招聘(jobs.feishu.cn) | GameAle（游戏精酿） | `gamealestudio` | 3 | success | 5 |
| 835 | 飞书招聘(jobs.feishu.cn) | 厦门极致互动网络技术股份有限公司（极致游戏） | `jzyxgames` | 3 | success | 5 |
| 836 | 飞书招聘(jobs.feishu.cn) | XD Inc.（心动×TapTap） | `xd-legacy` | 3 | success | 5 |
| 837 | 飞书招聘(jobs.feishu.cn) | 英雄游戏（英雄游戏） | `herogames` | 2 | success | 4 |
| 838 | 飞书招聘(jobs.feishu.cn) | 小马智行（小马智行[Pony.ai](http://Pony.ai)） | `ponyai` | 2 | success | 4 |
| 839 | 飞书招聘(jobs.feishu.cn) | 琻捷电子科技（江苏）股份有限公司（SENASIC） | `sen-asic` | 2 | success | 4 |
| 840 | 飞书招聘(jobs.feishu.cn) | 巴奴集团（巴奴） | `banu` | 1 | success | 3 |
| 841 | 飞书招聘(jobs.feishu.cn) | 吉家宠物集团（吉家宠物） | `jijiapets` | 1 | success | 3 |
| 842 | 飞书招聘(jobs.feishu.cn) | 上海创智学院（上海创智学院） | `sii-czxy` | 1 | success | 6 |

## 4. 被拒清单摘要

| 平台 / 原因 | 数量 |
|---|---|
| beisen / blocked (WAF / missing portal identity / no usable list) | 68 |
| moka / zero campus jobs (official list returned 0 for this scope) | 63 |
| moka / blocked (WAF / missing portal identity / no usable list) | 28 |
| feishu / zero campus jobs (official list returned 0 for this scope) | 22 |
| beisen / zero campus jobs (official list returned 0 for this scope) | 21 |
| feishu / blocked (WAF / missing portal identity / no usable list) | 14 |
| beisen / duplicate/ambiguous company name already covered: 中国电建集团北京勘测设计研究院有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 中电科芯片技术(集团)有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 中金公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 珠海冠宇电池股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 中国铁建国际集团有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 中电科蓝天科技股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 北京通嘉宏瑞科技股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 广州地铁集团有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 豪迈 | 1 |
| beisen / duplicate/ambiguous company name already covered: 华峰集团有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 汇中仪表股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 联宝（合肥）电子科技有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 蒙牛 | 1 |
| beisen / duplicate/ambiguous company name already covered: 浙江民泰商业银行股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 庆安集团 | 1 |
| beisen / duplicate/ambiguous company name already covered: 北京四方继保自动化股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 沈阳新松机器人自动化股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 芯联集成电路制造股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 曙光信息产业股份有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 威高集团有限公司 | 1 |
| beisen / duplicate/ambiguous company name already covered: 扬腾创新 | 1 |
| beisen / duplicate/ambiguous company name already covered: 一飞院 | 1 |
| beisen / duplicate/ambiguous company name already covered: 中冶建筑研究总院有限公司 | 1 |
| moka / duplicate/ambiguous company name already covered: 小天才 | 1 |
| moka / duplicate/ambiguous company name already covered: 华勤技术 | 1 |
| moka / duplicate/ambiguous company name already covered: 毕马威 | 1 |
| moka / duplicate/ambiguous company name already covered: 牧原集团 | 1 |
| moka / duplicate/ambiguous company name already covered: 深信服 | 1 |
| moka / duplicate/ambiguous company name already covered: 搜狐集团 | 1 |
| moka / duplicate/ambiguous company name already covered: 阶跃星辰 | 1 |
| moka / duplicate/ambiguous company name already covered: 心田花开 | 1 |
| feishu / duplicate/ambiguous company name already covered: 沐瞳科技 | 1 |

完整逐租户原因（含错误样本）见 `pipeline-watch/xianyu-ats-rejected.json`。

## 5. 大易（hotjob.cn）清单（不做适配器）

共 **47** 个域名。

| 域名 | 公司 | 示例链接 |
|---|---|---|
| `ampace.hotjob.cn` | 新能安 | https://ampace.hotjob.cn/ |
| `anton.hotjob.cn` | 安东油田服务集团 | https://anton.hotjob.cn/ |
| `bidr.hotjob.cn` | 中水北方公司 | https://bidr.hotjob.cn/ |
| `bkhr.hotjob.cn` | 欧莱雅百库 | https://bkhr.hotjob.cn/ |
| `bosera.hotjob.cn` | 博时基金 | https://bosera.hotjob.cn/ |
| `cgn.hotjob.cn` | 中广核集团 | https://cgn.hotjob.cn/ |
| `chinalogisticsgroup.hotjob.cn` | 中国物流 | https://chinalogisticsgroup.hotjob.cn/ |
| `cngr.hotjob.cn` | 中伟股份 | http://cngr.hotjob.cn/ |
| `crrc-kcgs.hotjob.cn` | 中车科创公司 | https://crrc-kcgs.hotjob.cn/ |
| `crrc-pz.hotjob.cn` | 中车浦镇公司 | https://crrc-pz.hotjob.cn/ |
| `crrc-qqhe.hotjob.cn` | 中车齐车集团有限公司 | https://crrc-qqhe.hotjob.cn/ |
| `crrc-qsys.hotjob.cn` | 中车戚墅堰所 | https://crrc-qsys.hotjob.cn/ |
| `crrc-sfs.hotjob.cn` | 中车四方所(中车制动) | https://crrc-sfs.hotjob.cn/ |
| `crrc-ts.hotjob.cn` | 中车唐山公司 | https://crrc-ts.hotjob.cn/ |
| `crrc.hotjob.cn` | 中国中车 | https://crrc.hotjob.cn/ |
| `dfmc.hotjob.cn` | 东风商用车、东风汽车研发总院、奕派科技 | https://dfmc.hotjob.cn/SU61d501d92f9d24431f65f608/mc/position/campus?sharePostKey=13283f580f504f8f82bfcc348bb90ecf |
| `essence.hotjob.cn` | 国投证券 | https://essence.hotjob.cn/ |
| `faw-zhaopin.hotjob.cn` | 一汽大众、一汽富华、一汽解放、中国一汽 | https://faw-zhaopin.hotjob.cn/mobile/brand?recruitType=1 |
| `fbwecruit.hotjob.cn` | 第一曼哈顿 第一北京 | https://fbwecruit.hotjob.cn/SU67ae91bb1eb80555b79f6730/pb/posDetail.html?postId=699eabfbbe908548be1dd49e&postType=campus |
| `gcoreinc.hotjob.cn` | 格科 | https://gcoreinc.hotjob.cn/ |
| `goertek.hotjob.cn` | 歌尔、歌尔-精英计划 | https://goertek.hotjob.cn/ |
| `goodwe.hotjob.cn` | 固德威 | https://goodwe.hotjob.cn/ |
| `gyasset.hotjob.cn` | 高毅资产 | https://gyasset.hotjob.cn/ |
| `gzcb.hotjob.cn` | 广州银行 | https://gzcb.hotjob.cn/ |
| `haday.hotjob.cn` | 海天味业 | https://haday.hotjob.cn/ |
| `hexagonhms.hotjob.cn` | 海克斯康（深圳） | https://hexagonhms.hotjob.cn/?sessionid= |
| `hmgc.hotjob.cn` | 现代汽车研发中心 | https://hmgc.hotjob.cn/ |
| `icbcubs.hotjob.cn` | 工银瑞信 | https://icbcubs.hotjob.cn/ |
| `ief.hotjob.cn` | IEF爱依服 | https://ief.hotjob.cn/ |
| `jingdiao.hotjob.cn` | 精雕科技 | https://jingdiao.hotjob.cn/ |
| `kejiajidian.hotjob.cn` | 科佳股份 | https://kejiajidian.hotjob.cn/ |
| `luxcaseict.hotjob.cn` | 立铠精密 | https://luxcaseict.hotjob.cn/ |
| `opt.hotjob.cn` | OPT奥普特 | https://opt.hotjob.cn/ |
| `positec.hotjob.cn` | 宝时得 | https://positec.hotjob.cn/ |
| `sc.hotjob.cn` | 中广核集团 | https://sc.hotjob.cn/wt/CGN/web/index/CompCGNPagecompanyList?projectId=302601&bgPic=recruit1 |
| `scbank.hotjob.cn` | 四川银行 | https://scbank.hotjob.cn/ |
| `seavo.hotjob.cn` | 信步科技 | https://seavo.hotjob.cn/ |
| `sec.hotjob.cn` | 上海电气、上海电气集团 | https://sec.hotjob.cn/SU60de8350bef57c519874bd36/pb/posDetail.html?postId=6a30ecd03d5b657f38c89a26&postType=overseas |
| `sinochem.hotjob.cn` | 中化商务、中化泉州石化、中化蓝天、中国中化 | https://sinochem.hotjob.cn/SU611a641a0dcad4106f04950e/mc/position/intern?sharePostKey=REDACTED |
| `skyworth.hotjob.cn` | 创维集团 | https://skyworth.hotjob.cn/wt/Skyworth/web/index/campus |
| `wecruit.hotjob.cn` | Ampace新能安、TCL华星、TCL实业大显示制造管理平台、TCL茂佳科技 | https://wecruit.hotjob.cn/SU62b2ae672f9d24458d72f9cc/pb/school.html |
| `whchem.hotjob.cn` | 万华化学 | https://whchem.hotjob.cn/ |
| `www.hotjob.cn` | 中铁建设集团、众合科技、航空工业特种所、财通证券 | https://www.hotjob.cn/wt/CT/web/index/campus |
| `xayjy.hotjob.cn` | 中移量子公司 | https://xayjy.hotjob.cn/ |
| `xemc.hotjob.cn` | 湘电集团 | https://xemc.hotjob.cn/ |
| `zts.hotjob.cn` | 中泰证券 | https://zts.hotjob.cn/ |
| `zyjob.hotjob.cn` | 卓越教育 | https://zyjob.hotjob.cn/ |

## 6. 「其他」域名 Top（共 1204 个，完整见 xianyu-ats-slugs.json）

| 域名 | 公司数 | 代表公司 | 示例链接 |
|---|---|---|---|
| `mp.weixin.qq.com` | 5947 | 2026湖南卫视、芒果TV春节联欢晚会、21世纪数字传媒、21世纪经济报道 | https://mp.weixin.qq.com/s/d_yzv-jqsiFhvXBzqa0CNQ |
| `zhaopin.cnpc.com.cn` | 113 | 《中国石油报》社、中国寰球工程、中国昆仑工程 | https://zhaopin.cnpc.com.cn/ |
| `campus.51job.com` | 94 | ASIL阿斯麦光刻、ENGEL中国、Molex莫仕 | https://campus.51job.com/zhaoxin2027/job.html |
| `career.huawei.com` | 81 | 华为、华为 终端BG、华为(ICT云核心网产品线) | https://career.huawei.com/cn/campus-recruitment-job-list?categoryList=JFC1 |
| `v.wjx.cn` | 67 | TP-Link联洲、三宝集团、中冶焦耐 | https://v.wjx.cn/vm/Ocb5ftq.aspx# |
| `www.iguopin.com` | 62 | 三沙市天勤服务管理有限公司、上海丰昌船务、上海船研所 | https://www.iguopin.com/job/detail?id=210638480026372343 |
| `wetalent.pingan.com` | 50 | 平安人寿、平安人寿上海分公司、平安人寿云南公司 | https://wetalent.pingan.com/b69618aabe9e33c3aa2a57186bdabab8/campus/home |
| `xiaoyuan.zhaopin.com` | 48 | vivo苏皖、东软睿驰、中国移动九天人工智能科技公司 | https://xiaoyuan.zhaopin.com/company/KA1511175220D90000001000 |
| `campus.yingjiesheng.com` | 41 | 中信期货、中信期货上海世纪大道分公司、中信期货上海分公司 | https://campus.yingjiesheng.com/citicsf/zongbu.html |
| `xyz.51job.com` | 38 | BURBERRY博柏利、中国能建国际集团、中国航发黎阳 | https://xyz.51job.com/External/Apply.aspx?CtmID=6547352 |
| `recruit.cscec.com` | 37 | 中国建筑基础设施事业部、中国建筑集团、中建一局 | https://recruit.cscec.com/recruit#/portal_job_list?job_class=campus&filter_dict={ |
| `job.icbc.com.cn` | 31 | 中国工商银行、中国工商银行上海市分行、中国工商银行业务研发中心 | https://job.icbc.com.cn/pc/index.html#/main/internship/home/struct |
| `cmb-recruitment-mobile.paas.cmbchina.com` | 31 | 招商银行上海分行、招商银行东莞分行、招商银行乌鲁木齐分行 | https://cmb-recruitment-mobile.paas.cmbchina.com/positionList/school?recruitmentTypeId=DF94FD6D-26D3-4A19-9E69-577C4BA1DE82&orgId=105030&sessionid= |
| `career.abchina.com.cn` | 29 | 中国农业银行、中国农业银行上海市分行、中国农业银行北京市分行 | https://career.abchina.com.cn/build/index.html#/103 |
| `www.wjx.top` | 25 | 中国邮政储蓄银行连云港市分行、乐亦思、凯邦电机制造 | https://www.wjx.top/vm/tFMrhjw.aspx |
| `join.qq.com` | 24 | 光子工作室群、腾讯、腾讯-AI技术岗 | https://join.qq.com/m/qingyun.html |
| `m.zhaopin.com` | 24 | 上海华谊集团、上海发那科、中信泰富特钢集团（中信特钢） | https://m.zhaopin.com/xiaoyuan/company/detail?refcode=4444&comid=KA0838625839P90000005000 |
| `job.citicbank.com` | 24 | 中信银行、中信银行上海分行、中信银行兰州分行 | https://job.citicbank.com/ |
| `jsj.top` | 23 | Og(天耘科技)、TCL、中广核 | https://jsj.top/f/r8bNbC |
| `xym.51job.com` | 23 | 上海华瑞银行、中国特种飞行器研究所、中国电子科技集团公司第五十三研究所 | https://xym.51job.com/wechat/vuectmjobs/#/index?id=AFED40F9-5331-44EA-8B59-E0AF5BDDDE06&color=31BE88&prd=yddzy |
| `campus-talent.alibaba.com` | 22 | Token Foundry、优酷少儿、平头哥 | https://campus-talent.alibaba.com/campus/position?campusShareCode=DOQKrNrjlD1hjORz15pzDacFKZm%2FIj6ib0MwttgW1Zk%3D&batchId=100000760001 |
| `young.yingjiesheng.com` | 22 | Qnity启诺迪、三湘银行、上海家化 | https://young.yingjiesheng.com/xyzlogin?ctmid=3301c7f1-2aac-41f6-a659-3d230ba7916e&ehirejobid=&jumpurl=https%3A%2F%2Fxyz.51job.com%2FExternal%2FOthers%2FLogin51.aspx%3FCtmID%3D3301c7f1-2aac-41f6-a659-3d230ba7916e%26prd%3Dyddzy%26prp%3D%26cd%3D%26cp%3D%26r |
| `career.cmbchina.com` | 21 | 招商银行、招商银行信用卡、招商银行厦门分行 | https://career.cmbchina.com/positionlist/DF94FD6D-26D3-4A19-9E69-577C4BA1DE82 |
| `jobs.51job.com` | 20 | 中交天津港湾工程研究院、中交天津港湾工程设计院、中交天津设计院 | https://jobs.51job.com/all/coBWYFaF48DjQOaARvBWg.html |
| `doc.weixin.qq.com` | 20 | 中联航运、仕佳光子、凯发电气 | https://doc.weixin.qq.com/smartsheet/form/1_wpwkBpCAAA1ZwX7J2VQTXjLpttZ0pRXg_d47b6f |
| `zhaopin.ccccltd.cn` | 20 | 上海振华重工集团、中交一航院、中交三航局四公司（宁波） | https://zhaopin.ccccltd.cn/custom/xzbk?hideMenu=1 |
| `campus.pingan.com` | 19 | 中国平安、平安产险、平安产险科技中心 | https://campus.pingan.com/ |
| `rsj.beijing.gov.cn` | 18 | 北京京北职业技术学院、北京信息科技大学（第二批）、北京农商银行 | https://rsj.beijing.gov.cn/ |
| `job.10086.cn` | 18 | 中国移动、中国移动九天公司、中国移动云公司 | https://job.10086.cn/touch/personal/trainee/trainee_job_list.html?cId=83 |
| `wejob.chinatelecom.com.cn` | 18 | 中国电信云计算研究院、中国电信新疆公司、中国电信新疆分公司 | https://wejob.chinatelecom.com.cn/wt/TELE/web/index#/postinquiry?data=eyJrZXkiOjgxMDEwMSwidHlwZSI6MX0 |
| `mp.weixinbridge.com` | 17 | DJI 大疆、OPPO、京东-新锐之星 | https://mp.weixinbridge.com/mp/wapredirect?url=httpsjoin.qq.compost.htmlkeywordinfraqueryp_14p_20b_29294&action=appmsg_redirect&uin=MTQyNzcwMzg2Mg&biz=MzIwMTUxMjk3Ng==&mid=2647640126&idx=1&type=2&scene=0 |
| `cctegjob.iguopin.com` | 17 | 中国煤科杭州研究院、中煤科工开采研究院有限公司、中煤科工智能储装技术有限公司 | https://cctegjob.iguopin.com/campus |
| `alidocs.dingtalk.com` | 15 | 东海半导体、中润医药(集团)、云南金浔资源 | https://alidocs.dingtalk.com/notable/share/form/v011X3lE5jNAM2j4lJb_dv19yqvsgs3oebp3pcjys_1qX0QQ0?utm_source=qrcode_form&source=qrcode |
| `www.cqrc.net` | 15 | 三峡人寿保险股份有限公司、中垦牧乳业（集团）股份有限公司、安诚财产保险股份有限公司 | https://www.cqrc.net/gzw/index/ |
| `xyzp.51job.com` | 14 | 东吴证券、中国广电-补录、中国移动 | https://xyzp.51job.com/cbncjsz2026/ |
| `webapp.zhaopin.com` | 13 | 中国大地保险、中国电科第四十、四十一研究所、中国联通吉林省分公司 | https://webapp.zhaopin.com/2025/hd/wfyhg1015ZL82493/ |
| `www.zhaopin.com` | 13 | 七彩化学、东安动力、中国电科八所 | https://www.zhaopin.com/companydetail/jobs-CZ211325910/ |
| `myjob.hzbank.com.cn` | 13 | 杭州银行、杭州银行上海分行、杭州银行北京分行 | https://myjob.hzbank.com.cn/hzzp-apply-web/static/index.html#/employ/ungraduate |
| `www.snhrm.com` | 12 | 中国东方资产管理股份有限公司、中国水利水电第三工程局有限公司、中国西电集团有限公司 | https://www.snhrm.com/ygqzp/8327834.jhtml |
| `gzw.cq.gov.cn` | 12 | 三峡人寿保险股份有限公司、中垦牧乳业（集团）股份有限公司、民生集团 | https://gzw.cq.gov.cn/gqzp/202607/t20260710_15815782.html |

## 7. 请求总数

| 平台 | 实测租户 | 采集请求数 | 飞书发现额外 1 次/租户 | 库内跳过 |
|---|---|---|---|---|
| 北森(zhiye.com) | 585 | 4682 | 0 | 116 |
| Moka(mokahr.com) | 397 | 4535 | 0 | 60 |
| 飞书招聘(jobs.feishu.cn) | 108 | 928 | 108 | 30 |
| **合计** | | **10145** | **108** | **206** |

## 8. 单测与基线

- 新增 `tests/test_p1_platform_feishu.py`（6 项）：配置驱动注册、默认项保留、站点解析、缺站点 blocked、pipeline 追加注册块、请求预算早停。
- 全量 `pytest tests/` 各跑 3 次（基线 `feat/banks-batch1` 与本次）：确定性失败集合**完全一致**，均为既有环境性 3 项：`test_core.py::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline.py::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema.py::test_enum_check_fails_when_data_drifts`。
- 通过数：基线 388 → 本次 394（+6 = 新增 `test_p1_platform_feishu.py`）。
- 第 4 项 `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` 为**两分支共有的 flaky**（多进程并起 sqlite 迁移偶发 database is locked）：基线 3 次中出现 1 次、本次出现 2 次，隔离复跑基线 5 次 3 过 2 败、本次 5 次 1 过 4 败，与本次改动无关（`core/store.py` 未改）。

## 9. 部署件

`pipeline-watch/deploy-artifacts/20260918d/`：须**叠加在 20260918c 之后**。

| 文件 | 说明 |
|---|---|
| `p1_feishu_public.py` | 新增配置驱动 `feishu` 段 + `collect_platform` + `merged_registry` + 可选 `max_requests` 预算 |
| `p1_pipeline.py` | 仅在现注册块之后追加飞书注册块（`setdefault`） |
| `p1_platform_companies.json` | 现有 6 家飞书迁入 `feishu` 段 + 本次实测通过的租户 |
| `tests/test_p1_platform_feishu.py`（可选） | 新增单测 |
| `tests/test_collector_next_integration.py`、`tests/test_p1_banks.py`（可选） | 因追加飞书注册块，顺序断言由「银行在末尾」改为「银行紧随 beisen/moka 之后、允许后续追加块」 |

## 10. 遗留与风险

- 北森 `PortalId` 缺失（WAF/多门户落地页）与 Moka 404/`orgId` 参数错误是主要被拒原因；不代表公司没有校招，只是当前公开入口不可稳定采集。
- 每租户 15 次请求是礼貌上限：大型租户在列表顺序不利时可能因预算提前停止而记 0 条（被拒），属**假阴性**，后续可提高预算复测。
- 飞书 `collect_feishu` 对未知 `recruit_type` 一律记错误、不猜测；未知枚举较多的租户会被判 blocked。
- 其他域名中含自定义域名的飞书招聘站点（如商汤/叠纸/得物/小米），仍由既有专用适配器覆盖，未纳入本次 `*.jobs.feishu.cn` 配置化范围。
- 新增数百家平台公司会让每日整批的 `DEFAULT_COMPANIES` 变大，需在调度侧评估每轮耗时与限速。
