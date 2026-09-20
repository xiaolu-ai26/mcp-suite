# 采集缺口报告 20260920

生成时间:2026-09-20T04:00:17+00:00

**总缺口 2636 条 / 声称完整却少采 2 个单元(5 条)/ 缺口最大公司:美团 2588、米哈游 14、金山办公 7**

## 汇总

| 指标 | 值 |
| --- | --- |
| 单元总数 | 958 |
| 站点自报总数可比对 | 834 |
| 完全吻合 | 814 |
| 有缺口单元 | 20 |
| 声称 complete 却少采 | **2** |
| partial 且有缺口 | 18 |
| 站点不报总数 | 124 |
| 总缺口 | **2636** |

## 最严重:声称 complete 却少采

站点自报总数、我们却存得更少,却仍被标成 complete —— 这一类必须逐条核。

| 公司 | scope | status | expected_total | collected_jobs | gap | 错误摘要 |
| --- | --- | --- | --- | --- | --- | --- |
| 商汤科技 | intern | success | 70 | 66 | **4** | - |
| 商汤科技 | social | success | 87 | 86 | **1** | - |

## partial 缺口 TOP 20

| 公司 | scope | expected_total | collected_jobs | gap | 错误摘要 |
| --- | --- | --- | --- | --- | --- |
| 美团 | social | 2500 | 320 | **2180** | Network failure: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1000)> |
| 美团 | intern | 399 | 140 | **259** | Network failure: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1000)> |
| 美团 | campus | 189 | 40 | **149** | Network failure: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1000)> |
| 米哈游 | social | 663 | 650 | **13** | HTTPSConnectionPool(host='ats.openout.mihoyo.com', port=443): Max retries exceeded with url: /ats-portal/v1/job/info (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1000)'))) / HTTPSConnectionPool(host='ats.openout.mihoyo.com', po |
| 金山办公 | social | 255 | 248 | **7** | detail ae579a30-f471-4ef6-ad9a-c8b2c9fb586e: Incomplete Moka detail ae579a30-f471-4ef6-ad9a-c8b2c9fb586e / detail 22fcb737-e620-4a35-9150-7a052e88048c: Incomplete Moka detail 22fcb737-e620-4a35-9150-7a052e88048c / detail 2125075c-487c-4c9c-a007-27ce53f5d55b: Incomplete Moka detail 2125075c-487c-4c9c |
| 恒瑞医药 | intern | 332 | 329 | **3** | detail aac83ef6-60e3-4318-9617-83fe9e5a8e86: Incomplete Moka detail aac83ef6-60e3-4318-9617-83fe9e5a8e86 / detail 1e79834d-164d-412f-a047-e553e4068aba: Incomplete Moka detail 1e79834d-164d-412f-a047-e553e4068aba / detail e5cc286b-fded-40a5-8dd5-fde55ff8e08d: Incomplete Moka detail e5cc286b-fded-40a5 |
| 用友网络 | intern | 94 | 91 | **3** | HTTPSConnectionPool(host='career.yonyou.com', port=443): Max retries exceeded with url: /wecruit/positionInfo/listPositionDetail/SU67ac41886202cc7916ae3029?iSaJAx=isAjax&request_locale=zh_CN (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol |
| 神州信息 | social | 374 | 371 | **3** | No official description for 1f543aaa-55a5-4317-844a-4cd5e78624e6 / No official description for f56955fd-506e-4965-a815-c55016ea4322 / No official description for b55e3231-4e19-4df6-8a63-ac1112b8a4a9 |
| 哔哩哔哩 | campus | 89 | 87 | **2** | HTTPSConnectionPool(host='jobs.bilibili.com', port=443): Read timed out. (read timeout=30) / HTTPSConnectionPool(host='jobs.bilibili.com', port=443): Read timed out. (read timeout=30) |
| 百度 | campus | 158 | 156 | **2** | HTTPSConnectionPool(host='talent.baidu.com', port=443): Max retries exceeded with url: /httservice/getPostDetail?postId=211b04aa-696c-4d8e-9d89-bf324e4910c1&recruitType=GRADUATE (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1000 |
| 联想 | campus | 110 | 108 | **2** | HTTPSConnectionPool(host='jobs.lenovo.com', port=443): Max retries exceeded with url: /en_US/careers/JobDetail/AI-Enterprise-Engineer/80609 (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1000)'))) / HTTPSConnectionPool(host='jobs |
| 蚂蚁集团 | social | 1272 | 1270 | **2** | Only company/team/platform introduction, not role evidence 1945048 / Only company/team/platform introduction, not role evidence 260702010708743 / duplicate source ID across pages: 26010408212482 |
| 华为 | social | 387 | 386 | **1** | detail 37178: Huawei no usable complete role/intentions |
| 宁德时代 | intern | 6 | 5 | **1** | detail 3c780276-27c0-4692-a8e6-5be7ecb610cb: Incomplete Moka detail 3c780276-27c0-4692-a8e6-5be7ecb610cb |
| 恒瑞医药 | campus | 581 | 580 | **1** | detail 966d50f8-d4d9-4b9a-b8a6-e6f5b208eb32: Incomplete Moka detail 966d50f8-d4d9-4b9a-b8a6-e6f5b208eb32 |
| 海大集团 | social | 311 | 310 | **1** | No official description for ff4eb253-e867-4135-8cdc-e9c6b0555b5d |
| 用友网络 | campus | 8 | 7 | **1** | HTTPSConnectionPool(host='career.yonyou.com', port=443): Max retries exceeded with url: /wecruit/positionInfo/listPositionDetail/SU67ac41886202cc7916ae3029?iSaJAx=isAjax&request_locale=zh_CN (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol |
| 米哈游 | campus | 119 | 118 | **1** | HTTPSConnectionPool(host='ats.openout.mihoyo.com', port=443): Max retries exceeded with url: /ats-portal/v1/job/info (Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1000)'))) |

## 公司维度(有缺口的公司)

| 公司 | 合计缺口 | 缺口单元 | 其中声称 complete | scopes |
| --- | --- | --- | --- | --- |
| 美团 | **2588** | 3 | 0 | social:2180, intern:259, campus:149 |
| 米哈游 | **14** | 2 | 0 | social:13, campus:1 |
| 金山办公 | **7** | 1 | 0 | social:7 |
| 商汤科技 | **5** | 2 | 2 | intern:4, social:1 |
| 恒瑞医药 | **4** | 2 | 0 | intern:3, campus:1 |
| 用友网络 | **4** | 2 | 0 | intern:3, campus:1 |
| 神州信息 | **3** | 1 | 0 | social:3 |
| 哔哩哔哩 | **2** | 1 | 0 | campus:2 |
| 百度 | **2** | 1 | 0 | campus:2 |
| 联想 | **2** | 1 | 0 | campus:2 |
| 蚂蚁集团 | **2** | 1 | 0 | social:2 |
| 华为 | **1** | 1 | 0 | social:1 |
| 宁德时代 | **1** | 1 | 0 | intern:1 |
| 海大集团 | **1** | 1 | 0 | social:1 |

## 与前一天对比

基线:20260918

- 新出现的缺口:12 个
- 缺口变大的单元:3 个
- 缺口收窄:2 个
- 已消除:4 个

| 新缺口公司 | scope | gap | 备注 |
| --- | --- | --- | --- |
| 哔哩哔哩 | campus | 2 | 前日无缺口(0) |
| 宁德时代 | intern | 1 | 前日无缺口(0) |
| 恒瑞医药 | campus | 1 | 首次出现(前日无此单元) |
| 恒瑞医药 | intern | 3 | 首次出现(前日无此单元) |
| 海大集团 | social | 1 | 首次出现(前日无此单元) |
| 用友网络 | campus | 1 | 前日无缺口(0) |
| 神州信息 | social | 3 | 首次出现(前日无此单元) |
| 米哈游 | social | 13 | 前日无缺口(0) |
| 美团 | campus | 149 | 首次出现(前日无此单元) |
| 美团 | intern | 259 | 首次出现(前日无此单元) |
| 美团 | social | 2180 | 首次出现(前日无此单元) |
| 金山办公 | social | 7 | 前日无缺口(0) |

| 缺口变大公司 | scope | 前日 | 今日 | 增量 |
| --- | --- | --- | --- | --- |
| 商汤科技 | intern | 1 | 4 | **+3** |
| 百度 | campus | 1 | 2 | **+1** |
| 联想 | campus | 1 | 2 | **+1** |

## 站点不报总数的单元(124 个)

这些单元无法比对,缺口不可知 —— 需要的是给适配器补上"站点自报总数"这条证据。

| 公司 | scope | status | collected_jobs |
| --- | --- | --- | --- |
| JM华中华东区 | campus | blocked | 0 |
| JM华中华东区 | intern | blocked | 0 |
| JM华中华东区 | social | blocked | 0 |
| 中国通号研究设计院集团 | intern | blocked | 0 |
| 中海物业集团有限公司 | intern | blocked | 0 |
| 中茵微电子 | campus | blocked | 0 |
| 中茵微电子 | intern | blocked | 0 |
| 中茵微电子 | social | blocked | 0 |
| 九江金鹭硬质合金有限公司 | campus | blocked | 0 |
| 九牧王股份有限公司 | campus | blocked | 0 |
| 九牧王股份有限公司 | intern | blocked | 0 |
| 九牧王股份有限公司 | social | blocked | 0 |
| 凯金 | campus | blocked | 0 |
| 加多宝（中国）饮料有限公司 | campus | blocked | 0 |
| 加多宝（中国）饮料有限公司 | intern | blocked | 0 |
| 加多宝（中国）饮料有限公司 | social | blocked | 0 |
| 劲牌有限公司 | campus | blocked | 0 |
| 劲牌有限公司 | intern | blocked | 0 |
| 劲牌有限公司 | social | blocked | 0 |
| 华睿科技 | intern | blocked | 0 |
| 华睿科技 | social | blocked | 0 |
| 叠纸游戏 | campus | blocked | 0 |
| 叠纸游戏 | intern | blocked | 0 |
| 叠纸游戏 | social | blocked | 0 |
| 合合信息 | social | blocked | 0 |
| 吉利汽车 | campus | blocked | 0 |
| 吉利汽车 | social | blocked | 0 |
| 基准方中 | campus | blocked | 0 |
| 宁德时代 | campus | blocked | 0 |
| 宁德时代 | social | blocked | 0 |
| 安克创新 | campus | blocked | 0 |
| 安克创新 | intern | blocked | 0 |
| 安克创新 | social | blocked | 0 |
| 完美世界 | intern | partial | 65 |
| 完美世界 | social | partial | 295 |
| 小红书 | campus | blocked | 0 |
| 小鹏汽车 | social | blocked | 0 |
| 巨人网络 | social | partial | 83 |
| 巨鲨医疗 | campus | blocked | 0 |
| 巨鲨医疗 | intern | blocked | 0 |
| 建信融通 | campus | blocked | 0 |
| 建信融通 | intern | blocked | 0 |
| 得物 | campus | blocked | 0 |
| 得物 | intern | blocked | 0 |
| 得物 | social | blocked | 0 |
| 快手 | intern | blocked | 0 |
| 快手 | social | blocked | 0 |
| 恒瑞医药 | social | blocked | 0 |
| 恒运昌 | campus | blocked | 0 |
| 恒运昌 | intern | blocked | 0 |
| 拼多多 | social | partial | 0 |
| 捷顺科技 | campus | blocked | 0 |
| 捷顺科技 | intern | blocked | 0 |
| 捷顺科技 | social | blocked | 0 |
| 智慧星空(上海)工程技术有限公司 | intern | blocked | 0 |
| 智慧星空(上海)工程技术有限公司 | social | blocked | 0 |
| 杰峰物联 | campus | blocked | 0 |
| 杰峰物联 | intern | blocked | 0 |
| 杰峰物联 | social | blocked | 0 |
| 柏诚系统科技股份有限公司 | campus | blocked | 0 |
| 柏诚系统科技股份有限公司 | intern | blocked | 0 |
| 柏诚系统科技股份有限公司 | social | blocked | 0 |
| 树根科技 | intern | blocked | 0 |
| 树根科技 | social | blocked | 0 |
| 比亚迪 | campus | blocked | 0 |
| 比亚迪 | social | blocked | 0 |
| 汇川技术 | campus | blocked | 0 |
| 汇川技术 | intern | blocked | 0 |
| 汇川技术 | social | blocked | 0 |
| 江南造船（集团）有限责任公司 | campus | blocked | 0 |
| 江南造船（集团）有限责任公司 | intern | blocked | 0 |
| 江南造船（集团）有限责任公司 | social | blocked | 0 |
| 浙江京新药业股份有限公司 | campus | blocked | 0 |
| 浙江京新药业股份有限公司 | intern | blocked | 0 |
| 浙江京新药业股份有限公司 | social | blocked | 0 |
| 浙江水晶光电科技股份有限公司 | intern | blocked | 0 |
| 浙江水晶光电科技股份有限公司 | social | blocked | 0 |
| 浩鲸科技 | intern | blocked | 0 |
| 浩鲸科技 | social | blocked | 0 |
| 海康威视 | intern | partial | 87 |
| 海康威视 | social | blocked | 0 |
| 滴滴 | campus | partial | 146 |
| 滴滴 | intern | partial | 634 |
| 滴滴 | social | blocked | 0 |
| 用友网络 | social | blocked | 0 |
| 电建江西院 | campus | blocked | 0 |
| 电建江西院 | intern | blocked | 0 |
| 百度 | intern | blocked | 0 |
| 百度 | social | blocked | 0 |
| 科大讯飞 | campus | blocked | 0 |
| 科大讯飞 | intern | blocked | 0 |
| 科大讯飞 | social | blocked | 0 |
| 精研科技 | campus | blocked | 0 |
| 精研科技 | intern | blocked | 0 |
| 精研科技 | social | blocked | 0 |
| 纵横股份 | campus | blocked | 0 |
| 纵横股份 | intern | blocked | 0 |
| 纵横股份 | social | blocked | 0 |
| 继峰座椅 | campus | blocked | 0 |
| 继峰座椅 | intern | blocked | 0 |
| 继峰座椅 | social | blocked | 0 |
| 网易 | campus | partial | 191 |
| 网易 | intern | partial | 629 |
| 网易 | social | partial | 2112 |
| 联想 | social | blocked | 0 |
| 苏州吉天星舟空间技术有限公司 | campus | blocked | 0 |
| 苏州吉天星舟空间技术有限公司 | intern | blocked | 0 |
| 苏州吉天星舟空间技术有限公司 | social | blocked | 0 |
| 莉莉丝游戏 | campus | blocked | 0 |
| 莉莉丝游戏 | intern | blocked | 0 |
| 莉莉丝游戏 | social | blocked | 0 |
| 蔚来汽车 | campus | blocked | 0 |
| 蔚来汽车 | intern | blocked | 0 |
| 蔚来汽车 | social | blocked | 0 |
| 蚂蚁集团 | intern | partial | 177 |
| 西安奇点能源股份有限公司 | intern | blocked | 0 |
| 西安奇点能源股份有限公司 | social | blocked | 0 |
| 金山云 | campus | blocked | 0 |
| 金山云 | intern | blocked | 0 |
| 金山云 | social | blocked | 0 |
| 金杯电工股份有限公司 | campus | blocked | 0 |
| 金杯电工股份有限公司 | intern | blocked | 0 |
| 金杯电工股份有限公司 | social | blocked | 0 |
| 长城汽车 | social | blocked | 0 |

## 附:全部单元

| 公司 | scope | status | complete | expected_total | collected_jobs | gap |
| --- | --- | --- | --- | --- | --- | --- |
| 美团 | social | partial | no | 2500 | 320 | 2180 |
| 美团 | intern | partial | no | 399 | 140 | 259 |
| 美团 | campus | partial | no | 189 | 40 | 149 |
| 米哈游 | social | partial | no | 663 | 650 | 13 |
| 金山办公 | social | partial | no | 255 | 248 | 7 |
| 商汤科技 | intern | success | yes | 70 | 66 | 4 |
| 恒瑞医药 | intern | partial | no | 332 | 329 | 3 |
| 用友网络 | intern | partial | no | 94 | 91 | 3 |
| 神州信息 | social | partial | no | 374 | 371 | 3 |
| 哔哩哔哩 | campus | partial | no | 89 | 87 | 2 |
| 百度 | campus | partial | no | 158 | 156 | 2 |
| 联想 | campus | partial | no | 110 | 108 | 2 |
| 蚂蚁集团 | social | partial | no | 1272 | 1270 | 2 |
| 华为 | social | partial | no | 387 | 386 | 1 |
| 商汤科技 | social | success | yes | 87 | 86 | 1 |
| 宁德时代 | intern | partial | no | 6 | 5 | 1 |
| 恒瑞医药 | campus | partial | no | 581 | 580 | 1 |
| 海大集团 | social | partial | no | 311 | 310 | 1 |
| 用友网络 | campus | partial | no | 8 | 7 | 1 |
| 米哈游 | campus | partial | no | 119 | 118 | 1 |
| AIVA汽车 | campus | success | yes | 172 | 172 | 0 |
| AIVA汽车 | intern | success | yes | 2 | 2 | 0 |
| AIVA汽车 | social | success | yes | 0 | 0 | 0 |
| BMC瑞迈特 | campus | success | yes | 26 | 26 | 0 |
| BMC瑞迈特 | intern | success | yes | 0 | 0 | 0 |
| BMC瑞迈特 | social | success | yes | 0 | 0 | 0 |
| Babycare | campus | success | yes | 40 | 40 | 0 |
| Babycare | intern | success | yes | 87 | 87 | 0 |
| Babycare | social | success | yes | 135 | 135 | 0 |
| JM华中华东区 | campus | blocked | no | - | 0 | - |
| JM华中华东区 | intern | blocked | no | - | 0 | - |
| JM华中华东区 | social | blocked | no | - | 0 | - |
| KK集团 | campus | partial | no | 9 | 9 | 0 |
| KK集团 | intern | partial | no | 7 | 7 | 0 |
| KK集团 | social | blocked | no | 0 | 0 | 0 |
| LINSY 林氏 | campus | success | yes | 27 | 27 | 0 |
| LINSY 林氏 | intern | success | yes | 3 | 3 | 0 |
| LINSY 林氏 | social | success | yes | 155 | 155 | 0 |
| LST | campus | success | yes | 23 | 23 | 0 |
| LST | intern | success | yes | 0 | 0 | 0 |
| LST | social | success | yes | 7 | 7 | 0 |
| OPPO | campus | success | yes | 141 | 141 | 0 |
| OPPO | intern | success | yes | 105 | 105 | 0 |
| OPPO | social | success | yes | 149 | 149 | 0 |
| TP-LINK普联 | campus | success | yes | 121 | 121 | 0 |
| TP-LINK普联 | intern | blocked | no | 0 | 0 | 0 |
| TP-LINK普联 | social | success | yes | 48 | 48 | 0 |
| e签宝 | campus | success | yes | 7 | 7 | 0 |
| e签宝 | intern | success | yes | 2 | 2 | 0 |
| e签宝 | social | success | yes | 32 | 32 | 0 |
| vivo | campus | success | yes | 166 | 166 | 0 |
| vivo | intern | success | yes | 89 | 89 | 0 |
| vivo | social | success | yes | 137 | 137 | 0 |
| 一鸣 | campus | success | yes | 32 | 32 | 0 |
| 一鸣 | intern | success | yes | 77 | 77 | 0 |
| 一鸣 | social | success | yes | 58 | 58 | 0 |
| 七色纺商业连锁有限公司 | campus | success | yes | 1 | 1 | 0 |
| 七色纺商业连锁有限公司 | intern | success | yes | 0 | 0 | 0 |
| 七色纺商业连锁有限公司 | social | success | yes | 9 | 9 | 0 |
| 万有引力（宁波）电子科技有限公司 | campus | success | yes | 19 | 19 | 0 |
| 万有引力（宁波）电子科技有限公司 | intern | success | yes | 3 | 3 | 0 |
| 万有引力（宁波）电子科技有限公司 | social | success | yes | 57 | 57 | 0 |
| 三七互娱 | campus | success | yes | 24 | 24 | 0 |
| 三七互娱 | intern | success | yes | 0 | 0 | 0 |
| 三七互娱 | social | success | yes | 0 | 0 | 0 |
| 上海哈啰普惠科技有限公司 | campus | partial | no | 44 | 44 | 0 |
| 上海哈啰普惠科技有限公司 | intern | partial | no | 46 | 46 | 0 |
| 上海哈啰普惠科技有限公司 | social | partial | no | 350 | 350 | 0 |
| 东方算芯 | campus | success | yes | 28 | 28 | 0 |
| 东方算芯 | intern | success | yes | 6 | 6 | 0 |
| 东方算芯 | social | success | yes | 67 | 67 | 0 |
| 东阳光 | campus | success | yes | 68 | 68 | 0 |
| 东阳光 | intern | success | yes | 1 | 1 | 0 |
| 东阳光 | social | success | yes | 46 | 46 | 0 |
| 中信建投 | campus | success | yes | 29 | 29 | 0 |
| 中信建投 | intern | success | yes | 0 | 0 | 0 |
| 中信建投 | social | success | yes | 62 | 62 | 0 |
| 中信科移动 | campus | success | yes | 52 | 52 | 0 |
| 中信科移动 | intern | success | yes | 0 | 0 | 0 |
| 中信科移动 | social | success | yes | 8 | 8 | 0 |
| 中兴通讯 | campus | success | yes | 59 | 59 | 0 |
| 中兴通讯 | intern | success | yes | 40 | 40 | 0 |
| 中兴通讯 | social | success | yes | 253 | 253 | 0 |
| 中国三星 | campus | success | yes | 46 | 46 | 0 |
| 中国三星 | intern | success | yes | 20 | 20 | 0 |
| 中国三星 | social | success | yes | 33 | 33 | 0 |
| 中国化学东华公司 | campus | success | yes | 18 | 18 | 0 |
| 中国化学东华公司 | intern | success | yes | 0 | 0 | 0 |
| 中国化学东华公司 | social | success | yes | 0 | 0 | 0 |
| 中国南山 | campus | partial | no | 38 | 38 | 0 |
| 中国南山 | intern | blocked | no | 0 | 0 | 0 |
| 中国南山 | social | partial | no | 1 | 1 | 0 |
| 中国电建福建院 | campus | success | yes | 15 | 15 | 0 |
| 中国电建福建院 | intern | success | yes | 15 | 15 | 0 |
| 中国电建福建院 | social | success | yes | 4 | 4 | 0 |
| 中国电科三十六所 | campus | success | yes | 4 | 4 | 0 |
| 中国电科三十六所 | intern | success | yes | 0 | 0 | 0 |
| 中国电科三十六所 | social | success | yes | 18 | 18 | 0 |
| 中国航空制造技术研究院 | campus | success | yes | 23 | 23 | 0 |
| 中国航空制造技术研究院 | intern | success | yes | 0 | 0 | 0 |
| 中国航空制造技术研究院 | social | success | yes | 7 | 7 | 0 |
| 中国航空工业集团公司西安航空计算技术研究所 | campus | success | yes | 4 | 4 | 0 |
| 中国航空工业集团公司西安航空计算技术研究所 | intern | success | yes | 3 | 3 | 0 |
| 中国航空工业集团公司西安航空计算技术研究所 | social | success | yes | 7 | 7 | 0 |
| 中国航空无线电电子研究所 | campus | success | yes | 97 | 97 | 0 |
| 中国航空无线电电子研究所 | intern | success | yes | 0 | 0 | 0 |
| 中国航空无线电电子研究所 | social | success | yes | 0 | 0 | 0 |
| 中国船舶集团有限公司第七一二研究所 | campus | success | yes | 22 | 22 | 0 |
| 中国船舶集团有限公司第七一二研究所 | intern | success | yes | 0 | 0 | 0 |
| 中国船舶集团有限公司第七一二研究所 | social | success | yes | 3 | 3 | 0 |
| 中国通号研究设计院集团 | campus | success | yes | 7 | 7 | 0 |
| 中国通号研究设计院集团 | intern | blocked | no | - | 0 | - |
| 中国通号研究设计院集团 | social | success | yes | 3 | 3 | 0 |
| 中山大洋电机股份有限公司 | campus | success | yes | 9 | 9 | 0 |
| 中山大洋电机股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 中山大洋电机股份有限公司 | social | success | yes | 29 | 29 | 0 |
| 中山联合光电科技股份有限公司 | campus | success | yes | 20 | 20 | 0 |
| 中山联合光电科技股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 中山联合光电科技股份有限公司 | social | success | yes | 1 | 1 | 0 |
| 中机中联工程有限公司 | campus | success | yes | 24 | 24 | 0 |
| 中机中联工程有限公司 | intern | success | yes | 0 | 0 | 0 |
| 中机中联工程有限公司 | social | success | yes | 1 | 1 | 0 |
| 中海企业发展集团有限公司 | campus | partial | no | 43 | 43 | 0 |
| 中海企业发展集团有限公司 | intern | blocked | no | 0 | 0 | 0 |
| 中海企业发展集团有限公司 | social | blocked | no | 0 | 0 | 0 |
| 中海物业集团有限公司 | campus | partial | no | 52 | 52 | 0 |
| 中海物业集团有限公司 | intern | blocked | no | - | 0 | - |
| 中海物业集团有限公司 | social | partial | no | 504 | 504 | 0 |
| 中科宇航 | campus | success | yes | 65 | 65 | 0 |
| 中科宇航 | intern | success | yes | 12 | 12 | 0 |
| 中科宇航 | social | success | yes | 123 | 123 | 0 |
| 中航技 | campus | success | yes | 13 | 13 | 0 |
| 中航技 | intern | success | yes | 0 | 0 | 0 |
| 中航技 | social | success | yes | 4 | 4 | 0 |
| 中航科创 | campus | partial | no | 172 | 172 | 0 |
| 中航科创 | intern | blocked | no | 0 | 0 | 0 |
| 中航科创 | social | partial | no | 37 | 37 | 0 |
| 中茵微电子 | campus | blocked | no | - | 0 | - |
| 中茵微电子 | intern | blocked | no | - | 0 | - |
| 中茵微电子 | social | blocked | no | - | 0 | - |
| 中金公司 | campus | success | yes | 104 | 104 | 0 |
| 中金公司 | intern | success | yes | 159 | 159 | 0 |
| 中金公司 | social | success | yes | 227 | 227 | 0 |
| 临工重机 | campus | success | yes | 6 | 6 | 0 |
| 临工重机 | intern | success | yes | 0 | 0 | 0 |
| 临工重机 | social | success | yes | 18 | 18 | 0 |
| 乐动机器人 | campus | success | yes | 40 | 40 | 0 |
| 乐动机器人 | intern | success | yes | 0 | 0 | 0 |
| 乐动机器人 | social | success | yes | 38 | 38 | 0 |
| 九江金鹭硬质合金有限公司 | campus | blocked | no | - | 0 | - |
| 九江金鹭硬质合金有限公司 | intern | success | yes | 0 | 0 | 0 |
| 九江金鹭硬质合金有限公司 | social | success | yes | 0 | 0 | 0 |
| 九牧王股份有限公司 | campus | blocked | no | - | 0 | - |
| 九牧王股份有限公司 | intern | blocked | no | - | 0 | - |
| 九牧王股份有限公司 | social | blocked | no | - | 0 | - |
| 云圣智能 | campus | success | yes | 44 | 44 | 0 |
| 云圣智能 | intern | success | yes | 0 | 0 | 0 |
| 云圣智能 | social | success | yes | 28 | 28 | 0 |
| 云天励飞 | campus | success | yes | 14 | 14 | 0 |
| 云天励飞 | intern | success | yes | 0 | 0 | 0 |
| 云天励飞 | social | success | yes | 57 | 57 | 0 |
| 亘芯悦 | campus | success | yes | 14 | 14 | 0 |
| 亘芯悦 | intern | success | yes | 0 | 0 | 0 |
| 亘芯悦 | social | success | yes | 7 | 7 | 0 |
| 亚中医疗 | campus | success | yes | 4 | 4 | 0 |
| 亚中医疗 | intern | success | yes | 0 | 0 | 0 |
| 亚中医疗 | social | success | yes | 3 | 3 | 0 |
| 交控科技股份有限公司 | campus | success | yes | 36 | 36 | 0 |
| 交控科技股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 交控科技股份有限公司 | social | success | yes | 0 | 0 | 0 |
| 京东 | campus | success | yes | 179 | 179 | 0 |
| 京东 | intern | success | yes | 168 | 168 | 0 |
| 京东 | social | success | yes | 1758 | 1758 | 0 |
| 亿星软件 | campus | success | yes | 1 | 1 | 0 |
| 亿星软件 | intern | success | yes | 0 | 0 | 0 |
| 亿星软件 | social | success | yes | 8 | 8 | 0 |
| 仪电智算 | campus | success | yes | 18 | 18 | 0 |
| 仪电智算 | intern | success | yes | 0 | 0 | 0 |
| 仪电智算 | social | success | yes | 113 | 113 | 0 |
| 佰维存储 | campus | success | yes | 102 | 102 | 0 |
| 佰维存储 | intern | success | yes | 0 | 0 | 0 |
| 佰维存储 | social | success | yes | 143 | 143 | 0 |
| 光寶新創校園招募 | campus | success | yes | 19 | 19 | 0 |
| 光寶新創校園招募 | intern | success | yes | 0 | 0 | 0 |
| 光寶新創校園招募 | social | success | yes | 0 | 0 | 0 |
| 八马茶业股份有限公司 | campus | partial | no | 19 | 19 | 0 |
| 八马茶业股份有限公司 | intern | partial | no | 1 | 1 | 0 |
| 八马茶业股份有限公司 | social | partial | no | 10 | 10 | 0 |
| 公牛集团 | campus | success | yes | 35 | 35 | 0 |
| 公牛集团 | intern | success | yes | 0 | 0 | 0 |
| 公牛集团 | social | success | yes | 21 | 21 | 0 |
| 兰剑智能 | campus | success | yes | 34 | 34 | 0 |
| 兰剑智能 | intern | success | yes | 1 | 1 | 0 |
| 兰剑智能 | social | success | yes | 35 | 35 | 0 |
| 共创草坪 | campus | success | yes | 15 | 15 | 0 |
| 共创草坪 | intern | success | yes | 0 | 0 | 0 |
| 共创草坪 | social | success | yes | 12 | 12 | 0 |
| 凡拓数字 | campus | success | yes | 12 | 12 | 0 |
| 凡拓数字 | intern | success | yes | 2 | 2 | 0 |
| 凡拓数字 | social | success | yes | 28 | 28 | 0 |
| 凯泉 | campus | success | yes | 4 | 4 | 0 |
| 凯泉 | intern | success | yes | 0 | 0 | 0 |
| 凯泉 | social | success | yes | 28 | 28 | 0 |
| 凯瑞斯德集团 | campus | success | yes | 22 | 22 | 0 |
| 凯瑞斯德集团 | intern | success | yes | 0 | 0 | 0 |
| 凯瑞斯德集团 | social | success | yes | 1 | 1 | 0 |
| 凯莱英 | campus | success | yes | 29 | 29 | 0 |
| 凯莱英 | intern | success | yes | 11 | 11 | 0 |
| 凯莱英 | social | success | yes | 366 | 366 | 0 |
| 凯金 | campus | blocked | no | - | 0 | - |
| 凯金 | intern | success | yes | 1 | 1 | 0 |
| 凯金 | social | success | yes | 21 | 21 | 0 |
| 利元亨 | campus | success | yes | 35 | 35 | 0 |
| 利元亨 | intern | success | yes | 1 | 1 | 0 |
| 利元亨 | social | success | yes | 34 | 34 | 0 |
| 加多宝（中国）饮料有限公司 | campus | blocked | no | - | 0 | - |
| 加多宝（中国）饮料有限公司 | intern | blocked | no | - | 0 | - |
| 加多宝（中国）饮料有限公司 | social | blocked | no | - | 0 | - |
| 劲牌有限公司 | campus | blocked | no | - | 0 | - |
| 劲牌有限公司 | intern | blocked | no | - | 0 | - |
| 劲牌有限公司 | social | blocked | no | - | 0 | - |
| 北京地铁 | campus | success | yes | 3 | 3 | 0 |
| 北京地铁 | intern | success | yes | 0 | 0 | 0 |
| 北京地铁 | social | success | yes | 0 | 0 | 0 |
| 北斗星通 | campus | success | yes | 30 | 30 | 0 |
| 北斗星通 | intern | success | yes | 2 | 2 | 0 |
| 北斗星通 | social | success | yes | 24 | 24 | 0 |
| 北汽重卡 | campus | success | yes | 6 | 6 | 0 |
| 北汽重卡 | intern | success | yes | 0 | 0 | 0 |
| 北汽重卡 | social | success | yes | 13 | 13 | 0 |
| 北芯生命 | campus | success | yes | 31 | 31 | 0 |
| 北芯生命 | intern | success | yes | 1 | 1 | 0 |
| 北芯生命 | social | success | yes | 59 | 59 | 0 |
| 华丞电子 | campus | success | yes | 6 | 6 | 0 |
| 华丞电子 | intern | success | yes | 0 | 0 | 0 |
| 华丞电子 | social | success | yes | 22 | 22 | 0 |
| 华中数控 | campus | success | yes | 12 | 12 | 0 |
| 华中数控 | intern | success | yes | 0 | 0 | 0 |
| 华中数控 | social | success | yes | 4 | 4 | 0 |
| 华为 | campus | success | yes | 71 | 71 | 0 |
| 华为 | intern | success | yes | 38 | 38 | 0 |
| 华昱欣 | campus | success | yes | 26 | 26 | 0 |
| 华昱欣 | intern | success | yes | 0 | 0 | 0 |
| 华昱欣 | social | success | yes | 11 | 11 | 0 |
| 华测导航 | campus | success | yes | 40 | 40 | 0 |
| 华测导航 | intern | success | yes | 0 | 0 | 0 |
| 华测导航 | social | success | yes | 0 | 0 | 0 |
| 华海清科-2027 | campus | success | yes | 16 | 16 | 0 |
| 华海清科-2027 | intern | success | yes | 0 | 0 | 0 |
| 华海清科-2027 | social | success | yes | 0 | 0 | 0 |
| 华睿科技 | campus | success | yes | 56 | 56 | 0 |
| 华睿科技 | intern | blocked | no | - | 0 | - |
| 华睿科技 | social | blocked | no | - | 0 | - |
| 华硕科技（苏州）有限公司 | campus | success | yes | 3 | 3 | 0 |
| 华硕科技（苏州）有限公司 | intern | success | yes | 1 | 1 | 0 |
| 华硕科技（苏州）有限公司 | social | success | yes | 19 | 19 | 0 |
| 华立科技股份有限公司 | campus | success | yes | 21 | 21 | 0 |
| 华立科技股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 华立科技股份有限公司 | social | success | yes | 12 | 12 | 0 |
| 华阳通用 | campus | success | yes | 15 | 15 | 0 |
| 华阳通用 | intern | success | yes | 0 | 0 | 0 |
| 华阳通用 | social | success | yes | 37 | 37 | 0 |
| 南京康尼机电股份有限公司 | campus | success | yes | 29 | 29 | 0 |
| 南京康尼机电股份有限公司 | intern | success | yes | 5 | 5 | 0 |
| 南京康尼机电股份有限公司 | social | success | yes | 22 | 22 | 0 |
| 卡斯柯信号有限公司 | campus | success | yes | 25 | 25 | 0 |
| 卡斯柯信号有限公司 | intern | success | yes | 3 | 3 | 0 |
| 卡斯柯信号有限公司 | social | success | yes | 14 | 14 | 0 |
| 卡旺卡 | campus | partial | no | 28 | 28 | 0 |
| 卡旺卡 | intern | blocked | no | 0 | 0 | 0 |
| 卡旺卡 | social | blocked | no | 0 | 0 | 0 |
| 卫星创新院人才 | campus | success | yes | 87 | 87 | 0 |
| 厦门星纵物联 | campus | success | yes | 15 | 15 | 0 |
| 厦门金鹭 | campus | success | yes | 19 | 19 | 0 |
| 厦门金鹭 | intern | success | yes | 0 | 0 | 0 |
| 厦门金鹭 | social | success | yes | 0 | 0 | 0 |
| 叠纸游戏 | campus | blocked | no | - | 0 | - |
| 叠纸游戏 | intern | blocked | no | - | 0 | - |
| 叠纸游戏 | social | blocked | no | - | 0 | - |
| 合合信息 | campus | success | yes | 52 | 52 | 0 |
| 合合信息 | intern | success | yes | 13 | 13 | 0 |
| 合合信息 | social | blocked | no | - | 0 | - |
| 吉利汽车 | campus | blocked | no | - | 0 | - |
| 吉利汽车 | intern | success | yes | 234 | 234 | 0 |
| 吉利汽车 | social | blocked | no | - | 0 | - |
| 哈尔滨飞机工业集团有限责任公司 | campus | success | yes | 5 | 5 | 0 |
| 哈尔滨飞机工业集团有限责任公司 | intern | success | yes | 0 | 0 | 0 |
| 哈尔滨飞机工业集团有限责任公司 | social | success | yes | 3 | 3 | 0 |
| 哈药集团股份有限公司 | campus | success | yes | 74 | 74 | 0 |
| 哈药集团股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 哈药集团股份有限公司 | social | success | yes | 0 | 0 | 0 |
| 哈银消费金融 | campus | success | yes | 4 | 4 | 0 |
| 哈银消费金融 | intern | success | yes | 1 | 1 | 0 |
| 哈银消费金融 | social | success | yes | 0 | 0 | 0 |
| 哔哩哔哩 | intern | success | yes | 322 | 322 | 0 |
| 哔哩哔哩 | social | success | yes | 491 | 491 | 0 |
| 商汤科技 | campus | success | yes | 80 | 80 | 0 |
| 回天新材 | campus | success | yes | 12 | 12 | 0 |
| 回天新材 | intern | success | yes | 0 | 0 | 0 |
| 回天新材 | social | success | yes | 0 | 0 | 0 |
| 国信证券 | campus | success | yes | 60 | 60 | 0 |
| 国信证券 | intern | success | yes | 32 | 32 | 0 |
| 国信证券 | social | success | yes | 49 | 49 | 0 |
| 国科天迅 | campus | success | yes | 8 | 8 | 0 |
| 国科天迅 | intern | success | yes | 0 | 0 | 0 |
| 国科天迅 | social | success | yes | 0 | 0 | 0 |
| 基准方中 | campus | blocked | no | - | 0 | - |
| 基准方中 | intern | success | yes | 4 | 4 | 0 |
| 基准方中 | social | success | yes | 491 | 491 | 0 |
| 基恩士 | campus | success | yes | 1 | 1 | 0 |
| 基恩士 | intern | success | yes | 0 | 0 | 0 |
| 基恩士 | social | success | yes | 1 | 1 | 0 |
| 复宏汉霖Henlius | campus | success | yes | 24 | 24 | 0 |
| 复宏汉霖Henlius | intern | success | yes | 0 | 0 | 0 |
| 复宏汉霖Henlius | social | success | yes | 119 | 119 | 0 |
| 外高桥造船 | campus | success | yes | 6 | 6 | 0 |
| 外高桥造船 | intern | success | yes | 0 | 0 | 0 |
| 外高桥造船 | social | success | yes | 0 | 0 | 0 |
| 多氟多 | campus | success | yes | 15 | 15 | 0 |
| 多氟多 | intern | success | yes | 0 | 0 | 0 |
| 多氟多 | social | success | yes | 14 | 14 | 0 |
| 大信会计 | campus | success | yes | 43 | 43 | 0 |
| 大信会计 | intern | success | yes | 0 | 0 | 0 |
| 大信会计 | social | success | yes | 54 | 54 | 0 |
| 大华股份 | campus | success | yes | 146 | 146 | 0 |
| 大华股份 | intern | success | yes | 46 | 46 | 0 |
| 大华股份 | social | success | yes | 177 | 177 | 0 |
| 大王椰 | campus | success | yes | 3 | 3 | 0 |
| 大王椰 | intern | success | yes | 0 | 0 | 0 |
| 大王椰 | social | success | yes | 3 | 3 | 0 |
| 大疆 | campus | success | yes | 139 | 139 | 0 |
| 大疆 | intern | success | yes | 7 | 7 | 0 |
| 大疆 | social | success | yes | 494 | 494 | 0 |
| 大通宝富 | campus | success | yes | 12 | 12 | 0 |
| 大通宝富 | intern | success | yes | 0 | 0 | 0 |
| 大通宝富 | social | success | yes | 20 | 20 | 0 |
| 宁德时代 | campus | blocked | no | - | 0 | - |
| 宁德时代 | social | blocked | no | - | 0 | - |
| 安克创新 | campus | blocked | no | - | 0 | - |
| 安克创新 | intern | blocked | no | - | 0 | - |
| 安克创新 | social | blocked | no | - | 0 | - |
| 安凯 | campus | success | yes | 8 | 8 | 0 |
| 安凯 | intern | success | yes | 0 | 0 | 0 |
| 安凯 | social | success | yes | 13 | 13 | 0 |
| 安徽巡鹰新能源集团有限公司 | campus | success | yes | 42 | 42 | 0 |
| 安徽巡鹰新能源集团有限公司 | intern | success | yes | 0 | 0 | 0 |
| 安徽巡鹰新能源集团有限公司 | social | success | yes | 3 | 3 | 0 |
| 安徽康明斯 | campus | success | yes | 1 | 1 | 0 |
| 安徽康明斯 | intern | success | yes | 4 | 4 | 0 |
| 安徽康明斯 | social | success | yes | 11 | 11 | 0 |
| 安徽老乡鸡餐饮有限公司 | campus | success | yes | 13 | 13 | 0 |
| 安徽老乡鸡餐饮有限公司 | intern | success | yes | 0 | 0 | 0 |
| 安徽老乡鸡餐饮有限公司 | social | success | yes | 48 | 48 | 0 |
| 安脉盛 | campus | success | yes | 17 | 17 | 0 |
| 安脉盛 | intern | success | yes | 1 | 1 | 0 |
| 安脉盛 | social | success | yes | 33 | 33 | 0 |
| 完美世界 | campus | success | yes | 37 | 37 | 0 |
| 完美世界 | intern | partial | no | - | 65 | - |
| 完美世界 | social | partial | no | - | 295 | - |
| 宝宝巴士 | campus | success | yes | 29 | 29 | 0 |
| 宝宝巴士 | intern | success | yes | 8 | 8 | 0 |
| 宝宝巴士 | social | success | yes | 25 | 25 | 0 |
| 富芯半导体 | campus | success | yes | 8 | 8 | 0 |
| 富芯半导体 | intern | success | yes | 0 | 0 | 0 |
| 富芯半导体 | social | success | yes | 1 | 1 | 0 |
| 小米 | campus | partial | no | 1031 | 1031 | 0 |
| 小米 | intern | partial | no | 557 | 557 | 0 |
| 小米 | social | partial | no | 1841 | 1841 | 0 |
| 小红书 | campus | blocked | no | - | 0 | - |
| 小红书 | intern | success | yes | 295 | 295 | 0 |
| 小红书 | social | success | yes | 850 | 850 | 0 |
| 小鹏汽车 | campus | success | yes | 455 | 455 | 0 |
| 小鹏汽车 | intern | success | yes | 83 | 83 | 0 |
| 小鹏汽车 | social | blocked | no | - | 0 | - |
| 山石网科通信技术股份有限公司 | campus | success | yes | 3 | 3 | 0 |
| 山石网科通信技术股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 山石网科通信技术股份有限公司 | social | success | yes | 30 | 30 | 0 |
| 屹唐半导体 | campus | success | yes | 40 | 40 | 0 |
| 屹唐半导体 | intern | success | yes | 0 | 0 | 0 |
| 屹唐半导体 | social | success | yes | 32 | 32 | 0 |
| 巨人网络 | campus | success | yes | 25 | 25 | 0 |
| 巨人网络 | intern | success | yes | 16 | 16 | 0 |
| 巨人网络 | social | partial | no | - | 83 | - |
| 巨鲨医疗 | campus | blocked | no | - | 0 | - |
| 巨鲨医疗 | intern | blocked | no | - | 0 | - |
| 巨鲨医疗 | social | success | yes | 0 | 0 | 0 |
| 市城规公司 | campus | success | yes | 3 | 3 | 0 |
| 市城规公司 | intern | success | yes | 5 | 5 | 0 |
| 市城规公司 | social | success | yes | 6 | 6 | 0 |
| 希奥端 | campus | success | yes | 21 | 21 | 0 |
| 希奥端 | intern | success | yes | 0 | 0 | 0 |
| 希奥端 | social | success | yes | 51 | 51 | 0 |
| 帝奥微 | campus | success | yes | 20 | 20 | 0 |
| 帝奥微 | intern | success | yes | 0 | 0 | 0 |
| 帝奥微 | social | success | yes | 0 | 0 | 0 |
| 帝迈生物 | campus | partial | no | 26 | 26 | 0 |
| 帝迈生物 | intern | blocked | no | 0 | 0 | 0 |
| 帝迈生物 | social | partial | no | 8 | 8 | 0 |
| 广东奥马冰箱有限公司 | campus | success | yes | 30 | 30 | 0 |
| 广东奥马冰箱有限公司 | intern | success | yes | 0 | 0 | 0 |
| 广东奥马冰箱有限公司 | social | success | yes | 39 | 39 | 0 |
| 广之旅 | campus | success | yes | 2 | 2 | 0 |
| 广之旅 | intern | success | yes | 3 | 3 | 0 |
| 广之旅 | social | success | yes | 0 | 0 | 0 |
| 广合科技 | campus | success | yes | 33 | 33 | 0 |
| 广合科技 | intern | success | yes | 0 | 0 | 0 |
| 广合科技 | social | success | yes | 117 | 117 | 0 |
| 广州旭之源科技有限公司 | campus | success | yes | 1 | 1 | 0 |
| 广州旭之源科技有限公司 | intern | success | yes | 0 | 0 | 0 |
| 广州旭之源科技有限公司 | social | success | yes | 9 | 9 | 0 |
| 广州金域医学检验中心有限公司 | campus | success | yes | 35 | 35 | 0 |
| 广州金域医学检验中心有限公司 | intern | success | yes | 1 | 1 | 0 |
| 广州金域医学检验中心有限公司 | social | success | yes | 36 | 36 | 0 |
| 建信融通 | campus | blocked | no | - | 0 | - |
| 建信融通 | intern | blocked | no | - | 0 | - |
| 建信融通 | social | success | yes | 34 | 34 | 0 |
| 强度所 | campus | success | yes | 23 | 23 | 0 |
| 强度所 | intern | success | yes | 0 | 0 | 0 |
| 强度所 | social | success | yes | 0 | 0 | 0 |
| 影石Insta360 | campus | success | yes | 225 | 225 | 0 |
| 影石Insta360 | intern | success | yes | 126 | 126 | 0 |
| 影石Insta360 | social | success | yes | 277 | 277 | 0 |
| 得物 | campus | blocked | no | - | 0 | - |
| 得物 | intern | blocked | no | - | 0 | - |
| 得物 | social | blocked | no | - | 0 | - |
| 德业 | campus | success | yes | 61 | 61 | 0 |
| 德业 | intern | success | yes | 0 | 0 | 0 |
| 德业 | social | success | yes | 105 | 105 | 0 |
| 德方纳米 | campus | success | yes | 38 | 38 | 0 |
| 德方纳米 | intern | success | yes | 0 | 0 | 0 |
| 德方纳米 | social | success | yes | 0 | 0 | 0 |
| 快乐学习 | campus | success | yes | 6 | 6 | 0 |
| 快乐学习 | intern | success | yes | 5 | 5 | 0 |
| 快乐学习 | social | success | yes | 31 | 31 | 0 |
| 快手 | campus | success | yes | 476 | 476 | 0 |
| 快手 | intern | blocked | no | - | 0 | - |
| 快手 | social | blocked | no | - | 0 | - |
| 思必驰科技股份有限公司 | campus | partial | no | 38 | 38 | 0 |
| 思必驰科技股份有限公司 | intern | partial | no | 16 | 16 | 0 |
| 思必驰科技股份有限公司 | social | partial | no | 7 | 7 | 0 |
| 恒安集团 | campus | success | yes | 8 | 8 | 0 |
| 恒安集团 | intern | success | yes | 0 | 0 | 0 |
| 恒安集团 | social | success | yes | 0 | 0 | 0 |
| 恒瑞医药 | social | blocked | no | - | 0 | - |
| 恒运昌 | campus | blocked | no | - | 0 | - |
| 恒运昌 | intern | blocked | no | - | 0 | - |
| 恒运昌 | social | success | yes | 6 | 6 | 0 |
| 恩井智控 | campus | success | yes | 9 | 9 | 0 |
| 恩井智控 | intern | success | yes | 0 | 0 | 0 |
| 恩井智控 | social | success | yes | 12 | 12 | 0 |
| 悍高集团 | campus | success | yes | 11 | 11 | 0 |
| 悍高集团 | intern | success | yes | 0 | 0 | 0 |
| 悍高集团 | social | success | yes | 10 | 10 | 0 |
| 成都奕成科技股份有限公司 | campus | success | yes | 26 | 26 | 0 |
| 成都奕成科技股份有限公司 | intern | success | yes | 1 | 1 | 0 |
| 成都奕成科技股份有限公司 | social | success | yes | 75 | 75 | 0 |
| 成都新易盛通信技术股份有限公司 | campus | partial | no | 26 | 26 | 0 |
| 成都新易盛通信技术股份有限公司 | intern | blocked | no | 0 | 0 | 0 |
| 成都新易盛通信技术股份有限公司 | social | partial | no | 60 | 60 | 0 |
| 扬腾创新 | campus | success | yes | 17 | 17 | 0 |
| 扬腾创新 | intern | success | yes | 1 | 1 | 0 |
| 扬腾创新 | social | success | yes | 0 | 0 | 0 |
| 招商船舶 | campus | partial | no | 147 | 147 | 0 |
| 招商船舶 | intern | blocked | no | 0 | 0 | 0 |
| 招商船舶 | social | partial | no | 54 | 54 | 0 |
| 拼多多 | campus | success | yes | 36 | 36 | 0 |
| 拼多多 | intern | success | yes | 2 | 2 | 0 |
| 拼多多 | social | partial | no | - | 0 | - |
| 捷顺科技 | campus | blocked | no | - | 0 | - |
| 捷顺科技 | intern | blocked | no | - | 0 | - |
| 捷顺科技 | social | blocked | no | - | 0 | - |
| 携程 | campus | partial | no | 64 | 64 | 0 |
| 携程 | intern | partial | no | 51 | 51 | 0 |
| 携程 | social | partial | no | 649 | 649 | 0 |
| 数字政通 | campus | success | yes | 16 | 16 | 0 |
| 数字政通 | intern | success | yes | 0 | 0 | 0 |
| 数字政通 | social | success | yes | 22 | 22 | 0 |
| 新奥集团 | campus | success | yes | 1 | 1 | 0 |
| 新奥集团 | intern | success | yes | 0 | 0 | 0 |
| 新奥集团 | social | success | yes | 117 | 117 | 0 |
| 方科PCB | campus | success | yes | 6 | 6 | 0 |
| 方科PCB | intern | success | yes | 40 | 40 | 0 |
| 方科PCB | social | success | yes | 6 | 6 | 0 |
| 方达中国 | campus | success | yes | 5 | 5 | 0 |
| 方达中国 | intern | success | yes | 0 | 0 | 0 |
| 方达中国 | social | success | yes | 32 | 32 | 0 |
| 日立能源 | campus | success | yes | 24 | 24 | 0 |
| 日立能源 | intern | success | yes | 75 | 75 | 0 |
| 日立能源 | social | success | yes | 319 | 319 | 0 |
| 昆仑芯 | campus | success | yes | 19 | 19 | 0 |
| 昆仑芯 | intern | success | yes | 9 | 9 | 0 |
| 昆仑芯 | social | success | yes | 30 | 30 | 0 |
| 昊一源 | campus | success | yes | 43 | 43 | 0 |
| 昊一源 | intern | success | yes | 1 | 1 | 0 |
| 昊一源 | social | success | yes | 53 | 53 | 0 |
| 易盛信息 | campus | success | yes | 1 | 1 | 0 |
| 易盛信息 | intern | success | yes | 0 | 0 | 0 |
| 易盛信息 | social | success | yes | 1 | 1 | 0 |
| 星海图 | campus | success | yes | 4 | 4 | 0 |
| 星海图 | intern | success | yes | 10 | 10 | 0 |
| 星海图 | social | success | yes | 26 | 26 | 0 |
| 晶丰明源 | campus | success | yes | 77 | 77 | 0 |
| 晶丰明源 | intern | success | yes | 6 | 6 | 0 |
| 晶丰明源 | social | success | yes | 58 | 58 | 0 |
| 晶易医药 | campus | success | yes | 20 | 20 | 0 |
| 晶易医药 | intern | success | yes | 0 | 0 | 0 |
| 晶易医药 | social | success | yes | 0 | 0 | 0 |
| 晶晨半导体 | campus | success | yes | 33 | 33 | 0 |
| 晶晨半导体 | intern | success | yes | 2 | 2 | 0 |
| 晶晨半导体 | social | success | yes | 142 | 142 | 0 |
| 智岩科技 | campus | success | yes | 44 | 44 | 0 |
| 智岩科技 | intern | success | yes | 0 | 0 | 0 |
| 智岩科技 | social | success | yes | 13 | 13 | 0 |
| 智慧星空(上海)工程技术有限公司 | campus | success | yes | 18 | 18 | 0 |
| 智慧星空(上海)工程技术有限公司 | intern | blocked | no | - | 0 | - |
| 智慧星空(上海)工程技术有限公司 | social | blocked | no | - | 0 | - |
| 朗坤科技 | campus | success | yes | 20 | 20 | 0 |
| 朗坤科技 | intern | success | yes | 0 | 0 | 0 |
| 朗坤科技 | social | success | yes | 24 | 24 | 0 |
| 杭州迪普科技股份有限公司 | campus | success | yes | 11 | 11 | 0 |
| 杭州迪普科技股份有限公司 | intern | success | yes | 5 | 5 | 0 |
| 杭州迪普科技股份有限公司 | social | success | yes | 388 | 388 | 0 |
| 杰峰物联 | campus | blocked | no | - | 0 | - |
| 杰峰物联 | intern | blocked | no | - | 0 | - |
| 杰峰物联 | social | blocked | no | - | 0 | - |
| 极客未来 | campus | success | yes | 5 | 5 | 0 |
| 极客未来 | intern | success | yes | 5 | 5 | 0 |
| 极客未来 | social | success | yes | 17 | 17 | 0 |
| 柏楚电子 | campus | success | yes | 35 | 35 | 0 |
| 柏楚电子 | intern | success | yes | 17 | 17 | 0 |
| 柏楚电子 | social | success | yes | 75 | 75 | 0 |
| 柏诚系统科技股份有限公司 | campus | blocked | no | - | 0 | - |
| 柏诚系统科技股份有限公司 | intern | blocked | no | - | 0 | - |
| 柏诚系统科技股份有限公司 | social | blocked | no | - | 0 | - |
| 树根科技 | campus | success | yes | 39 | 39 | 0 |
| 树根科技 | intern | blocked | no | - | 0 | - |
| 树根科技 | social | blocked | no | - | 0 | - |
| 核桃编程 | campus | success | yes | 10 | 10 | 0 |
| 核桃编程 | intern | success | yes | 1 | 1 | 0 |
| 核桃编程 | social | success | yes | 39 | 39 | 0 |
| 格见半导体 | campus | success | yes | 11 | 11 | 0 |
| 格见半导体 | intern | success | yes | 1 | 1 | 0 |
| 格见半导体 | social | success | yes | 21 | 21 | 0 |
| 格通智联 | campus | success | yes | 10 | 10 | 0 |
| 格通智联 | intern | success | yes | 0 | 0 | 0 |
| 格通智联 | social | success | yes | 21 | 21 | 0 |
| 桦洁商贸（上海）有限公司 | campus | success | yes | 85 | 85 | 0 |
| 桦洁商贸（上海）有限公司 | intern | success | yes | 22 | 22 | 0 |
| 桦洁商贸（上海）有限公司 | social | success | yes | 134 | 134 | 0 |
| 横店集团控股有限公司 | campus | success | yes | 175 | 175 | 0 |
| 横店集团控股有限公司 | intern | success | yes | 0 | 0 | 0 |
| 横店集团控股有限公司 | social | success | yes | 231 | 231 | 0 |
| 比亚迪 | campus | blocked | no | - | 0 | - |
| 比亚迪 | intern | success | yes | 6 | 6 | 0 |
| 比亚迪 | social | blocked | no | - | 0 | - |
| 汇川技术 | campus | blocked | no | - | 0 | - |
| 汇川技术 | intern | blocked | no | - | 0 | - |
| 汇川技术 | social | blocked | no | - | 0 | - |
| 江南造船（集团）有限责任公司 | campus | blocked | no | - | 0 | - |
| 江南造船（集团）有限责任公司 | intern | blocked | no | - | 0 | - |
| 江南造船（集团）有限责任公司 | social | blocked | no | - | 0 | - |
| 江波龙 | campus | success | yes | 85 | 85 | 0 |
| 江波龙 | intern | success | yes | 10 | 10 | 0 |
| 江波龙 | social | success | yes | 39 | 39 | 0 |
| 江苏华创微系统有限公司 | campus | success | yes | 12 | 12 | 0 |
| 江苏华创微系统有限公司 | intern | success | yes | 0 | 0 | 0 |
| 江苏华创微系统有限公司 | social | success | yes | 50 | 50 | 0 |
| 江苏海四达电源有限公司 | campus | partial | no | 21 | 21 | 0 |
| 江苏海四达电源有限公司 | intern | blocked | no | 0 | 0 | 0 |
| 江苏海四达电源有限公司 | social | partial | no | 54 | 54 | 0 |
| 江西洪都航空工业集团有限责任公司 | campus | success | yes | 8 | 8 | 0 |
| 江西洪都航空工业集团有限责任公司 | intern | success | yes | 0 | 0 | 0 |
| 江西洪都航空工业集团有限责任公司 | social | success | yes | 2 | 2 | 0 |
| 沛塬电子 | campus | success | yes | 10 | 10 | 0 |
| 沪东中华造船集团 | campus | success | yes | 17 | 17 | 0 |
| 沪东中华造船集团 | intern | success | yes | 0 | 0 | 0 |
| 沪东中华造船集团 | social | success | yes | 0 | 0 | 0 |
| 法士特 | campus | success | yes | 22 | 22 | 0 |
| 法士特 | intern | success | yes | 0 | 0 | 0 |
| 法士特 | social | success | yes | 20 | 20 | 0 |
| 法本信息 | campus | success | yes | 19 | 19 | 0 |
| 法本信息 | intern | success | yes | 0 | 0 | 0 |
| 法本信息 | social | success | yes | 15 | 15 | 0 |
| 泛联新安 | campus | success | yes | 12 | 12 | 0 |
| 泛联新安 | intern | success | yes | 5 | 5 | 0 |
| 泛联新安 | social | success | yes | 0 | 0 | 0 |
| 济南邦德激光股份有限公司 | campus | success | yes | 54 | 54 | 0 |
| 济南邦德激光股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 济南邦德激光股份有限公司 | social | success | yes | 218 | 218 | 0 |
| 浙江京新药业股份有限公司 | campus | blocked | no | - | 0 | - |
| 浙江京新药业股份有限公司 | intern | blocked | no | - | 0 | - |
| 浙江京新药业股份有限公司 | social | blocked | no | - | 0 | - |
| 浙江横店进出口有限公司 | campus | success | yes | 2 | 2 | 0 |
| 浙江横店进出口有限公司 | intern | success | yes | 1 | 1 | 0 |
| 浙江横店进出口有限公司 | social | success | yes | 2 | 2 | 0 |
| 浙江民泰商业银行 | campus | success | yes | 16 | 16 | 0 |
| 浙江民泰商业银行 | intern | success | yes | 0 | 0 | 0 |
| 浙江民泰商业银行 | social | success | yes | 97 | 97 | 0 |
| 浙江水晶光电科技股份有限公司 | campus | success | yes | 24 | 24 | 0 |
| 浙江水晶光电科技股份有限公司 | intern | blocked | no | - | 0 | - |
| 浙江水晶光电科技股份有限公司 | social | blocked | no | - | 0 | - |
| 浩鲸科技 | campus | partial | no | 58 | 58 | 0 |
| 浩鲸科技 | intern | blocked | no | - | 0 | - |
| 浩鲸科技 | social | blocked | no | - | 0 | - |
| 海亮教育集团 | campus | success | yes | 5 | 5 | 0 |
| 海亮教育集团 | intern | success | yes | 0 | 0 | 0 |
| 海亮教育集团 | social | success | yes | 0 | 0 | 0 |
| 海光芯正集团 | campus | success | yes | 31 | 31 | 0 |
| 海光芯正集团 | intern | success | yes | 0 | 0 | 0 |
| 海光芯正集团 | social | success | yes | 0 | 0 | 0 |
| 海大集团 | campus | success | yes | 167 | 167 | 0 |
| 海大集团 | intern | success | yes | 0 | 0 | 0 |
| 海康威视 | campus | success | yes | 169 | 169 | 0 |
| 海康威视 | intern | partial | no | - | 87 | - |
| 海康威视 | social | blocked | no | - | 0 | - |
| 海栎创 | campus | success | yes | 11 | 11 | 0 |
| 海栎创 | intern | success | yes | 0 | 0 | 0 |
| 海栎创 | social | success | yes | 0 | 0 | 0 |
| 海格通信 | campus | partial | no | 18 | 18 | 0 |
| 海格通信 | intern | partial | no | 6 | 6 | 0 |
| 海格通信 | social | partial | no | 6 | 6 | 0 |
| 海正药业 | campus | success | yes | 9 | 9 | 0 |
| 海正药业 | intern | success | yes | 0 | 0 | 0 |
| 海正药业 | social | success | yes | 18 | 18 | 0 |
| 深圳市康冠科技股份有限公司 | campus | success | yes | 61 | 61 | 0 |
| 深圳市康冠科技股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 深圳市康冠科技股份有限公司 | social | success | yes | 68 | 68 | 0 |
| 深圳市李森智能有限公司 | campus | success | yes | 5 | 5 | 0 |
| 深圳市李森智能有限公司 | intern | success | yes | 0 | 0 | 0 |
| 深圳市李森智能有限公司 | social | success | yes | 1 | 1 | 0 |
| 深圳新宙邦科技股份有限公司 | campus | success | yes | 68 | 68 | 0 |
| 深圳新宙邦科技股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 深圳新宙邦科技股份有限公司 | social | success | yes | 0 | 0 | 0 |
| 湖北星辰技术有限公司 | campus | success | yes | 52 | 52 | 0 |
| 湖北星辰技术有限公司 | intern | success | yes | 0 | 0 | 0 |
| 湖北星辰技术有限公司 | social | success | yes | 0 | 0 | 0 |
| 湖北绿色家园材料技术股份有限公司 | campus | success | yes | 11 | 11 | 0 |
| 湖北绿色家园材料技术股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 湖北绿色家园材料技术股份有限公司 | social | success | yes | 9 | 9 | 0 |
| 湖南国科微电子股份有限公司 | campus | success | yes | 39 | 39 | 0 |
| 湖南国科微电子股份有限公司 | intern | success | yes | 4 | 4 | 0 |
| 湖南国科微电子股份有限公司 | social | success | yes | 73 | 73 | 0 |
| 滨化集团 | campus | success | yes | 6 | 6 | 0 |
| 滨化集团 | intern | success | yes | 0 | 0 | 0 |
| 滨化集团 | social | success | yes | 0 | 0 | 0 |
| 滴滴 | campus | partial | no | - | 146 | - |
| 滴滴 | intern | partial | no | - | 634 | - |
| 滴滴 | social | blocked | no | - | 0 | - |
| 潮宏基 | campus | success | yes | 34 | 34 | 0 |
| 潮宏基 | intern | success | yes | 0 | 0 | 0 |
| 潮宏基 | social | success | yes | 0 | 0 | 0 |
| 灵明光子 | campus | success | yes | 11 | 11 | 0 |
| 灵明光子 | intern | success | yes | 8 | 8 | 0 |
| 灵明光子 | social | success | yes | 3 | 3 | 0 |
| 灵猴机器人 | campus | success | yes | 54 | 54 | 0 |
| 灵猴机器人 | intern | success | yes | 0 | 0 | 0 |
| 灵猴机器人 | social | success | yes | 30 | 30 | 0 |
| 灿芯半导体 | campus | success | yes | 8 | 8 | 0 |
| 灿芯半导体 | intern | success | yes | 0 | 0 | 0 |
| 灿芯半导体 | social | success | yes | 24 | 24 | 0 |
| 炬芯科技 | campus | success | yes | 13 | 13 | 0 |
| 炬芯科技 | intern | success | yes | 0 | 0 | 0 |
| 炬芯科技 | social | success | yes | 17 | 17 | 0 |
| 爱慕集团 | campus | success | yes | 17 | 17 | 0 |
| 爱慕集团 | intern | success | yes | 1 | 1 | 0 |
| 爱慕集团 | social | success | yes | 3 | 3 | 0 |
| 牛芯半导体企业 | campus | success | yes | 10 | 10 | 0 |
| 牛芯半导体企业 | intern | success | yes | 0 | 0 | 0 |
| 牛芯半导体企业 | social | success | yes | 13 | 13 | 0 |
| 理想汽车 | campus | partial | no | 649 | 649 | 0 |
| 理想汽车 | intern | partial | no | 412 | 412 | 0 |
| 理想汽车 | social | partial | no | 738 | 738 | 0 |
| 用友网络 | social | blocked | no | - | 0 | - |
| 电建江西院 | campus | blocked | no | - | 0 | - |
| 电建江西院 | intern | blocked | no | - | 0 | - |
| 电建江西院 | social | partial | no | 82 | 82 | 0 |
| 百度 | intern | blocked | no | - | 0 | - |
| 百度 | social | blocked | no | - | 0 | - |
| 省建院 | campus | success | yes | 22 | 22 | 0 |
| 省建院 | intern | success | yes | 16 | 16 | 0 |
| 省建院 | social | success | yes | 29 | 29 | 0 |
| 睿智医药 | campus | success | yes | 22 | 22 | 0 |
| 睿智医药 | intern | success | yes | 13 | 13 | 0 |
| 睿智医药 | social | success | yes | 64 | 64 | 0 |
| 石头科技 | campus | blocked | no | 0 | 0 | 0 |
| 石头科技 | intern | success | yes | 3 | 3 | 0 |
| 石头科技 | social | success | yes | 55 | 55 | 0 |
| 砺星工业科技 | campus | success | yes | 27 | 27 | 0 |
| 砺星工业科技 | intern | success | yes | 0 | 0 | 0 |
| 砺星工业科技 | social | success | yes | 9 | 9 | 0 |
| 碧橙数字 | campus | success | yes | 5 | 5 | 0 |
| 碧橙数字 | intern | success | yes | 2 | 2 | 0 |
| 碧橙数字 | social | success | yes | 13 | 13 | 0 |
| 礼意久久 | campus | success | yes | 13 | 13 | 0 |
| 礼意久久 | intern | success | yes | 0 | 0 | 0 |
| 礼意久久 | social | success | yes | 0 | 0 | 0 |
| 神州信息 | campus | success | yes | 34 | 34 | 0 |
| 神州信息 | intern | success | yes | 12 | 12 | 0 |
| 神州数码集团 | campus | partial | no | 78 | 78 | 0 |
| 神州数码集团 | intern | partial | no | 19 | 19 | 0 |
| 神州数码集团 | social | partial | no | 235 | 235 | 0 |
| 禾望电气 | campus | success | yes | 13 | 13 | 0 |
| 禾望电气 | intern | success | yes | 0 | 0 | 0 |
| 禾望电气 | social | success | yes | 15 | 15 | 0 |
| 科大国创云网 | campus | success | yes | 3 | 3 | 0 |
| 科大国创云网 | intern | success | yes | 1 | 1 | 0 |
| 科大国创云网 | social | success | yes | 0 | 0 | 0 |
| 科大国创股份有限公司 | campus | success | yes | 10 | 10 | 0 |
| 科大国创股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 科大国创股份有限公司 | social | success | yes | 4 | 4 | 0 |
| 科大讯飞 | campus | blocked | no | - | 0 | - |
| 科大讯飞 | intern | blocked | no | - | 0 | - |
| 科大讯飞 | social | blocked | no | - | 0 | - |
| 科威尔 | campus | success | yes | 12 | 12 | 0 |
| 科威尔 | intern | success | yes | 0 | 0 | 0 |
| 科威尔 | social | success | yes | 0 | 0 | 0 |
| 科捷智能 | campus | success | yes | 16 | 16 | 0 |
| 科捷智能 | intern | success | yes | 0 | 0 | 0 |
| 科捷智能 | social | success | yes | 5 | 5 | 0 |
| 科沃斯 | campus | success | yes | 10 | 10 | 0 |
| 科沃斯 | intern | success | yes | 1 | 1 | 0 |
| 科沃斯 | social | success | yes | 3 | 3 | 0 |
| 立讯技术 | campus | success | yes | 45 | 45 | 0 |
| 立讯技术 | intern | success | yes | 7 | 7 | 0 |
| 立讯技术 | social | success | yes | 20 | 20 | 0 |
| 立达信物联科技 | campus | success | yes | 33 | 33 | 0 |
| 立达信物联科技 | intern | success | yes | 0 | 0 | 0 |
| 立达信物联科技 | social | success | yes | 45 | 45 | 0 |
| 米哈游 | intern | success | yes | 140 | 140 | 0 |
| 精研科技 | campus | blocked | no | - | 0 | - |
| 精研科技 | intern | blocked | no | - | 0 | - |
| 精研科技 | social | blocked | no | - | 0 | - |
| 紫讯科技 | campus | success | yes | 9 | 9 | 0 |
| 紫讯科技 | intern | success | yes | 0 | 0 | 0 |
| 紫讯科技 | social | success | yes | 6 | 6 | 0 |
| 纵横股份 | campus | blocked | no | - | 0 | - |
| 纵横股份 | intern | blocked | no | - | 0 | - |
| 纵横股份 | social | blocked | no | - | 0 | - |
| 纵维立方 | campus | success | yes | 26 | 26 | 0 |
| 纵维立方 | intern | success | yes | 0 | 0 | 0 |
| 纵维立方 | social | success | yes | 41 | 41 | 0 |
| 继峰座椅 | campus | blocked | no | - | 0 | - |
| 继峰座椅 | intern | blocked | no | - | 0 | - |
| 继峰座椅 | social | blocked | no | - | 0 | - |
| 绿城房地产建设管理集团有限公司 | campus | success | yes | 6 | 6 | 0 |
| 绿城房地产建设管理集团有限公司 | intern | success | yes | 1 | 1 | 0 |
| 绿城房地产建设管理集团有限公司 | social | success | yes | 48 | 48 | 0 |
| 绿能慧充 | campus | success | yes | 15 | 15 | 0 |
| 绿能慧充 | intern | success | yes | 0 | 0 | 0 |
| 绿能慧充 | social | success | yes | 15 | 15 | 0 |
| 网易 | campus | partial | no | - | 191 | - |
| 网易 | intern | partial | no | - | 629 | - |
| 网易 | social | partial | no | - | 2112 | - |
| 翰博高新材料（合肥）股份有限公司 | campus | success | yes | 72 | 72 | 0 |
| 翰博高新材料（合肥）股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 翰博高新材料（合肥）股份有限公司 | social | success | yes | 1 | 1 | 0 |
| 联发科技 | campus | success | yes | 18 | 18 | 0 |
| 联发科技 | intern | success | yes | 0 | 0 | 0 |
| 联想 | intern | success | yes | 13 | 13 | 0 |
| 联想 | social | blocked | no | - | 0 | - |
| 联芸科技 | campus | success | yes | 38 | 38 | 0 |
| 联芸科技 | intern | success | yes | 0 | 0 | 0 |
| 联芸科技 | social | success | yes | 0 | 0 | 0 |
| 聚和材料 | campus | success | yes | 12 | 12 | 0 |
| 聚和材料 | intern | success | yes | 0 | 0 | 0 |
| 聚和材料 | social | success | yes | 1 | 1 | 0 |
| 航天五院遥感部 | campus | success | yes | 9 | 9 | 0 |
| 航天五院遥感部 | intern | success | yes | 0 | 0 | 0 |
| 航天五院遥感部 | social | success | yes | 0 | 0 | 0 |
| 航空工业宝胜 | campus | success | yes | 3 | 3 | 0 |
| 航空工业宝胜 | intern | success | yes | 0 | 0 | 0 |
| 航空工业宝胜 | social | success | yes | 2 | 2 | 0 |
| 航空工业自控所 | campus | partial | no | 14 | 14 | 0 |
| 航空工业自控所 | intern | partial | no | 3 | 3 | 0 |
| 航空工业自控所 | social | partial | no | 16 | 16 | 0 |
| 航空工业计量所 | campus | success | yes | 39 | 39 | 0 |
| 航空工业计量所 | intern | success | yes | 0 | 0 | 0 |
| 航空工业计量所 | social | success | yes | 0 | 0 | 0 |
| 艾为电子 | campus | success | yes | 45 | 45 | 0 |
| 艾为电子 | intern | success | yes | 0 | 0 | 0 |
| 艾为电子 | social | success | yes | 58 | 58 | 0 |
| 艾诺仪器公司 | campus | success | yes | 14 | 14 | 0 |
| 艾诺仪器公司 | intern | success | yes | 0 | 0 | 0 |
| 艾诺仪器公司 | social | success | yes | 3 | 3 | 0 |
| 芯上微装 | campus | success | yes | 25 | 25 | 0 |
| 芯上微装 | intern | success | yes | 0 | 0 | 0 |
| 芯上微装 | social | success | yes | 8 | 8 | 0 |
| 芯动科技 | campus | success | yes | 20 | 20 | 0 |
| 芯动科技 | intern | success | yes | 2 | 2 | 0 |
| 芯动科技 | social | success | yes | 58 | 58 | 0 |
| 芯海科技 | campus | success | yes | 21 | 21 | 0 |
| 芯海科技 | intern | success | yes | 1 | 1 | 0 |
| 芯海科技 | social | success | yes | 62 | 62 | 0 |
| 芯碁微装 | campus | success | yes | 27 | 27 | 0 |
| 芯碁微装 | intern | success | yes | 0 | 0 | 0 |
| 芯碁微装 | social | success | yes | 15 | 15 | 0 |
| 苏州吉天星舟空间技术有限公司 | campus | blocked | no | - | 0 | - |
| 苏州吉天星舟空间技术有限公司 | intern | blocked | no | - | 0 | - |
| 苏州吉天星舟空间技术有限公司 | social | blocked | no | - | 0 | - |
| 苏州极易科技股份有限公司 | campus | success | yes | 8 | 8 | 0 |
| 苏州极易科技股份有限公司 | intern | success | yes | 5 | 5 | 0 |
| 苏州极易科技股份有限公司 | social | success | yes | 7 | 7 | 0 |
| 英搏尔 | campus | success | yes | 58 | 58 | 0 |
| 英搏尔 | intern | success | yes | 1 | 1 | 0 |
| 英搏尔 | social | success | yes | 15 | 15 | 0 |
| 英杰晨晖官方 | campus | success | yes | 28 | 28 | 0 |
| 英杰晨晖官方 | intern | success | yes | 1 | 1 | 0 |
| 英杰晨晖官方 | social | success | yes | 29 | 29 | 0 |
| 英洛华科技股份有限公司 | campus | success | yes | 21 | 21 | 0 |
| 英洛华科技股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 英洛华科技股份有限公司 | social | success | yes | 39 | 39 | 0 |
| 英维克 | campus | success | yes | 65 | 65 | 0 |
| 英维克 | intern | success | yes | 1 | 1 | 0 |
| 英维克 | social | success | yes | 183 | 183 | 0 |
| 荣耀 | campus | success | yes | 139 | 139 | 0 |
| 荣耀 | intern | success | yes | 18 | 18 | 0 |
| 荣耀 | social | success | yes | 380 | 380 | 0 |
| 药明康德 | campus | success | yes | 198 | 198 | 0 |
| 药明康德 | intern | success | yes | 26 | 26 | 0 |
| 药明康德 | social | success | yes | 378 | 378 | 0 |
| 莉莉丝游戏 | campus | blocked | no | - | 0 | - |
| 莉莉丝游戏 | intern | blocked | no | - | 0 | - |
| 莉莉丝游戏 | social | blocked | no | - | 0 | - |
| 菇娘家 | campus | success | yes | 6 | 6 | 0 |
| 菇娘家 | intern | success | yes | 1 | 1 | 0 |
| 菇娘家 | social | success | yes | 6 | 6 | 0 |
| 菲利斯太阳能 | campus | success | yes | 14 | 14 | 0 |
| 菲利斯太阳能 | intern | success | yes | 0 | 0 | 0 |
| 菲利斯太阳能 | social | success | yes | 53 | 53 | 0 |
| 蔚来汽车 | campus | blocked | no | - | 0 | - |
| 蔚来汽车 | intern | blocked | no | - | 0 | - |
| 蔚来汽车 | social | blocked | no | - | 0 | - |
| 虹科 | campus | success | yes | 72 | 72 | 0 |
| 虹科 | intern | success | yes | 48 | 48 | 0 |
| 虹科 | social | success | yes | 30 | 30 | 0 |
| 蚂蚁集团 | campus | success | yes | 148 | 148 | 0 |
| 蚂蚁集团 | intern | partial | no | - | 177 | - |
| 西安奇点能源股份有限公司 | campus | success | yes | 27 | 27 | 0 |
| 西安奇点能源股份有限公司 | intern | blocked | no | - | 0 | - |
| 西安奇点能源股份有限公司 | social | blocked | no | - | 0 | - |
| 西安奕斯伟材料科技股份有限公司 | campus | partial | no | 46 | 46 | 0 |
| 西安奕斯伟材料科技股份有限公司 | intern | partial | no | 2 | 2 | 0 |
| 西安奕斯伟材料科技股份有限公司 | social | partial | no | 17 | 17 | 0 |
| 诺德凯（苏州）智能装备有限公司 | campus | success | yes | 10 | 10 | 0 |
| 诺德凯（苏州）智能装备有限公司 | intern | success | yes | 0 | 0 | 0 |
| 诺德凯（苏州）智能装备有限公司 | social | success | yes | 7 | 7 | 0 |
| 豪迈 | campus | success | yes | 51 | 51 | 0 |
| 豪迈 | intern | success | yes | 0 | 0 | 0 |
| 豪迈 | social | success | yes | 371 | 371 | 0 |
| 豪鹏科技 | campus | success | yes | 22 | 22 | 0 |
| 豪鹏科技 | intern | success | yes | 0 | 0 | 0 |
| 豪鹏科技 | social | success | yes | 0 | 0 | 0 |
| 贵州磷化集团 | campus | partial | no | 46 | 46 | 0 |
| 贵州磷化集团 | intern | blocked | no | 0 | 0 | 0 |
| 贵州磷化集团 | social | blocked | no | 0 | 0 | 0 |
| 达力普石油专用管有限公司 | campus | success | yes | 14 | 14 | 0 |
| 达力普石油专用管有限公司 | intern | success | yes | 0 | 0 | 0 |
| 达力普石油专用管有限公司 | social | success | yes | 24 | 24 | 0 |
| 迅销（上海）企业管理咨询有限公司 | campus | partial | no | 1 | 1 | 0 |
| 迅销（上海）企业管理咨询有限公司 | intern | blocked | no | 0 | 0 | 0 |
| 迅销（上海）企业管理咨询有限公司 | social | partial | no | 2 | 2 | 0 |
| 迈瑞医疗 | campus | success | yes | 58 | 58 | 0 |
| 迈瑞医疗 | intern | success | yes | 19 | 19 | 0 |
| 迈瑞医疗 | social | success | yes | 182 | 182 | 0 |
| 迪阿股份有限公司 | campus | success | yes | 1 | 1 | 0 |
| 迪阿股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 迪阿股份有限公司 | social | success | yes | 5 | 5 | 0 |
| 遨森电商 | campus | success | yes | 35 | 35 | 0 |
| 遨森电商 | intern | success | yes | 2 | 2 | 0 |
| 遨森电商 | social | success | yes | 76 | 76 | 0 |
| 邯药公司 | campus | success | yes | 10 | 10 | 0 |
| 邯药公司 | intern | success | yes | 0 | 0 | 0 |
| 邯药公司 | social | success | yes | 30 | 30 | 0 |
| 都正生物 | campus | success | yes | 9 | 9 | 0 |
| 都正生物 | intern | success | yes | 2 | 2 | 0 |
| 都正生物 | social | success | yes | 13 | 13 | 0 |
| 金山云 | campus | blocked | no | - | 0 | - |
| 金山云 | intern | blocked | no | - | 0 | - |
| 金山云 | social | blocked | no | - | 0 | - |
| 金山办公 | campus | success | yes | 25 | 25 | 0 |
| 金山办公 | intern | success | yes | 24 | 24 | 0 |
| 金杜 | campus | success | yes | 1 | 1 | 0 |
| 金杜 | intern | success | yes | 54 | 54 | 0 |
| 金杜 | social | success | yes | 62 | 62 | 0 |
| 金杯电工股份有限公司 | campus | blocked | no | - | 0 | - |
| 金杯电工股份有限公司 | intern | blocked | no | - | 0 | - |
| 金杯电工股份有限公司 | social | blocked | no | - | 0 | - |
| 金蝶 | campus | success | yes | 222 | 222 | 0 |
| 金蝶 | intern | success | yes | 0 | 0 | 0 |
| 金蝶 | social | success | yes | 32 | 32 | 0 |
| 钜泉科技 | campus | success | yes | 16 | 16 | 0 |
| 钜泉科技 | intern | success | yes | 0 | 0 | 0 |
| 钜泉科技 | social | success | yes | 11 | 11 | 0 |
| 镁伽 | campus | success | yes | 17 | 17 | 0 |
| 镁伽 | intern | success | yes | 0 | 0 | 0 |
| 长城汽车 | campus | success | yes | 545 | 545 | 0 |
| 长城汽车 | intern | success | yes | 61 | 61 | 0 |
| 长城汽车 | social | blocked | no | - | 0 | - |
| 长城电源 | campus | success | yes | 78 | 78 | 0 |
| 长城电源 | intern | success | yes | 0 | 0 | 0 |
| 长城电源 | social | success | yes | 0 | 0 | 0 |
| 长强系统 | campus | success | yes | 14 | 14 | 0 |
| 长强系统 | intern | success | yes | 0 | 0 | 0 |
| 长强系统 | social | success | yes | 21 | 21 | 0 |
| 长江证券研究所暑期实习 | campus | success | yes | 3 | 3 | 0 |
| 长江证券研究所暑期实习 | intern | success | yes | 0 | 0 | 0 |
| 长江证券研究所暑期实习 | social | success | yes | 0 | 0 | 0 |
| 陈克明食品股份有限公司 | campus | success | yes | 6 | 6 | 0 |
| 陈克明食品股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 陈克明食品股份有限公司 | social | success | yes | 15 | 15 | 0 |
| 陕西汉德车桥有限公司 | campus | partial | no | 4 | 4 | 0 |
| 陕西汉德车桥有限公司 | intern | blocked | no | 0 | 0 | 0 |
| 陕西汉德车桥有限公司 | social | partial | no | 27 | 27 | 0 |
| 飞凌嵌入式 | campus | success | yes | 9 | 9 | 0 |
| 飞凌嵌入式 | intern | success | yes | 0 | 0 | 0 |
| 飞凌嵌入式 | social | success | yes | 13 | 13 | 0 |
| 飞博共创 | campus | success | yes | 7 | 7 | 0 |
| 飞博共创 | intern | success | yes | 0 | 0 | 0 |
| 飞博共创 | social | success | yes | 1 | 1 | 0 |
| 骆驼集团股份有限公司 | campus | success | yes | 50 | 50 | 0 |
| 骆驼集团股份有限公司 | intern | success | yes | 1 | 1 | 0 |
| 骆驼集团股份有限公司 | social | success | yes | 7 | 7 | 0 |
| 高德红外 | campus | success | yes | 22 | 22 | 0 |
| 高德红外 | intern | success | yes | 2 | 2 | 0 |
| 高德红外 | social | success | yes | 186 | 186 | 0 |
| 高拓讯达(北京)微电子股份有限公司 | campus | success | yes | 6 | 6 | 0 |
| 高拓讯达(北京)微电子股份有限公司 | intern | success | yes | 0 | 0 | 0 |
| 高拓讯达(北京)微电子股份有限公司 | social | success | yes | 1 | 1 | 0 |
| 高松电子 | campus | success | yes | 19 | 19 | 0 |
| 高松电子 | intern | success | yes | 0 | 0 | 0 |
| 高松电子 | social | success | yes | 1 | 1 | 0 |
| 高标 | campus | success | yes | 26 | 26 | 0 |
| 高标 | intern | success | yes | 0 | 0 | 0 |
| 高标 | social | success | yes | 12 | 12 | 0 |
| 高能环境 | campus | success | yes | 21 | 21 | 0 |
| 高能环境 | intern | success | yes | 0 | 0 | 0 |
| 高能环境 | social | success | yes | 2 | 2 | 0 |
| 高露洁 | campus | success | yes | 16 | 16 | 0 |
| 高露洁 | intern | success | yes | 0 | 0 | 0 |
| 高露洁 | social | success | yes | 0 | 0 | 0 |
| 鹏城新能 | campus | success | yes | 7 | 7 | 0 |
| 鹏城新能 | intern | success | yes | 0 | 0 | 0 |
| 鹏城新能 | social | success | yes | 19 | 19 | 0 |
| 鹰角网络 | campus | success | yes | 61 | 61 | 0 |
| 鹰角网络 | intern | success | yes | 44 | 44 | 0 |
| 鹰角网络 | social | success | yes | 0 | 0 | 0 |
| 鹿客科技 | campus | success | yes | 11 | 11 | 0 |
| 鹿客科技 | intern | success | yes | 1 | 1 | 0 |
| 鹿客科技 | social | success | yes | 11 | 11 | 0 |
| 麦田能源 | campus | success | yes | 70 | 70 | 0 |
| 麦田能源 | intern | success | yes | 1 | 1 | 0 |
| 麦田能源 | social | success | yes | 103 | 103 | 0 |
| 麦科田医疗 | campus | success | yes | 49 | 49 | 0 |
| 麦科田医疗 | intern | success | yes | 2 | 2 | 0 |
| 麦科田医疗 | social | success | yes | 40 | 40 | 0 |
| 龙蟠科技 | campus | success | yes | 132 | 132 | 0 |
| 龙蟠科技 | intern | success | yes | 1 | 1 | 0 |
| 龙蟠科技 | social | success | yes | 53 | 53 | 0 |
