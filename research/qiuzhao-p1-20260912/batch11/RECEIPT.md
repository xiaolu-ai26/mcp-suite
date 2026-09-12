# P1 batch 11–20 receipt

All 30 scopes were attempted against official public sources. No production writes. Candidates are read-only staging; completeness varies by scope.

|Company|Scope|Jobs|Expected|Status|
|---|---|---:|---:|---|
|米哈游|campus|118|118|success|
|米哈游|intern|144|144|success|
|米哈游|social|662|663|partial|
|哔哩哔哩|campus|0|None|blocked|
|哔哩哔哩|intern|0|None|blocked|
|哔哩哔哩|social|0|None|blocked|
|蚂蚁集团|campus|148|148|success|
|蚂蚁集团|intern|257|257|success|
|蚂蚁集团|social|1234|1234|partial|
|百度|campus|10|None|partial|
|百度|intern|10|None|partial|
|百度|social|10|None|partial|
|滴滴|campus|151|151|success|
|滴滴|intern|611|611|partial|
|滴滴|social|1028|1028|partial|
|携程|campus|57|57|success|
|携程|intern|48|48|partial|
|携程|social|662|662|partial|
|联想|campus|113|113|success|
|联想|intern|11|11|success|
|联想|social|1011|1012|partial|
|海康威视|campus|170|170|success|
|海康威视|intern|483|483|success|
|海康威视|social|1551|1551|success|
|安克创新|campus|237|237|success|
|安克创新|intern|250|250|success|
|安克创新|social|618|657|partial|
|影石Insta360|campus|0|None|blocked|
|影石Insta360|intern|0|None|blocked|
|影石Insta360|social|0|None|blocked|

Adapter: qiuzhao/collector/p1_sources_11_20.py. Depends on collect_moka_sites from p1_sources_01_10 for Didi campus/intern (latest version continues after individual detail errors).

Validation: 8 focused tests; git diff --check. CHECKPOINT.json has exact candidate paths and SHA-256 hashes. Every candidate has a real role source ID, role description, scoped recruitment type and official detail/application link.

Remaining gaps: Bilibili official API -101/login or 412; Baidu full listing API no-auth (10 real SSR jobs per scope retained); miHoYo one official blank detail; Ant social 8 repeated pagination IDs (partial prevents delisting); Didi internship one empty detail and global backend TLS certificate chain failure; Anker social 39 missing complete role evidence; Lenovo one role empty in English and official Japanese alternative; Ctrip 18 official unspecified recruitment types; Insta360 official Feishu endpoint HTTP405.

Updated field extraction preserves full original cohort/graduate-date phrases and exact major/degree requirement snippets; batch_name is the v4 campaign field, and Baidu cohort_scope is campaign_announcement rather than role evidence. No blanket 2027 defaults.
