| # | 原字段 | 出现行数 | 非空行数 | 归类 | v4 输出为 | 理由 |
|---:|---|---:|---:|---|---|---|
| 1 | `id` | 27,506 | 27,506 | 业务 | `id` | 岗位唯一标识，jobs_detail 的入参来源；去重后唯一 |
| 2 | `job_title` | 27,506 | 27,506 | 业务 | `job_title` | 岗位名称 |
| 3 | `education_raw` | 27,506 | 18,248 | 业务 | `education_raw` | 学历原文，供核对；6 种乱码值输出为空 |
| 4 | `cohort_raw` | 27,506 | 15,148 | 业务 | `cohort_raw` | 届别/资格原文，是届别依据“岗位写明”的出处 |
| 5 | `application_url` | 27,506 | 27,506 | 业务 | `application_url` | 投递入口 |
| 6 | `source_url` | 27,506 | 27,506 | 业务 | `source_url` | 原公告或岗位页，回答必须附带 |
| 7 | `source_name` | 27,506 | 27,506 | 业务 | `source_name` | 来源名称 |
| 8 | `description_raw` | 27,506 | 27,506 | 业务 | `description_raw` | 岗位描述原文；约占 v4 每条字节的一半（size_description_share_v4），按决定 3 保留 |
| 9 | `recruitment_type` | 27,506 | 27,506 | 业务 | `recruitment_type` | 校园/实习/社会招聘，筛选与分组字段 |
| 10 | `industry` | 27,506 | 27,506 | 业务 | `industry` | 行业，筛选与分组字段 |
| 11 | `country` | 27,506 | 27,506 | 业务 | `country` | 国家 |
| 12 | `contracting_entity` | 27,302 | 1,117 | 业务 | `contracting_entity` | 签约主体，与招聘单位不同时学生需要知道 |
| 13 | `major_requirements_raw` | 27,157 | 13,664 | 业务 | `major_requirements_raw` | 专业要求原文 |
| 14 | `major_tags` | 26,953 | 977 | 业务 | `major_tags` | 专业标签 |
| 15 | `recruiting_unit_raw` | 26,696 | 21,442 | 业务 | `recruiting_unit_raw` | 具体用人单位（分公司、研究院） |
| 16 | `hiring_department_raw` | 26,211 | 20,358 | 业务 | `hiring_department_raw` | 用人部门 |
| 17 | `reviewed_at` | 21,694 | 20,180 | 业务 | `reviewed_at` | 该条核验时间；data_as_of 取全库最大值 |
| 18 | `campaign_url` | 13,739 | 11,076 | 业务 | `campaign_url` | 招聘专场链接 |
| 19 | `announcement_url` | 6,651 | 2,687 | 业务 | `announcement_url` | 招聘公告链接 |
| 20 | `job_listing_url` | 875 | 875 | 业务 | `job_listing_url` | 岗位列表页 |
| 21 | `status_note` | 836 | 836 | 业务 | `status_note` | 状态说明原文 |
| 22 | `industry_tags` | 828 | 807 | 业务 | `industry_tags` | 细分行业标签 |
| 23 | `parent_unit_raw` | 461 | 461 | 业务 | `parent_unit_raw` | 上级单位 |
| 24 | `recruitment_unit` | 27,506 | 27,506 | 改名 | `company` | 与筛选参数 company、分组 company 同名，组值可直接填回 |
| 25 | `cities` | 27,506 | 27,506 | 合并 | `cities` | 原文城市；与 cities_normalized 合成一个修正后的列表（区县信息不再输出） |
| 26 | `deadline` | 27,506 | 19,951 | 修正 | `deadline` | 统一为 YYYY-MM-DD 或 null；2099 占位日期置 null |
| 27 | `deadline_type` | 27,506 | 26,845 | 改名+修正 | `deadline_kind` | 8 种写法收成 明确日期 / 招满即止或长期 / 未注明 |
| 28 | `status` | 27,506 | 27,506 | 修正 | `status` | open/active/qualified→招聘中，unverified→未核验，截止日已过→已截止 |
| 29 | `overseas_flag` | 27,506 | 27,506 | 合并 | `region` | 与 region=海外 重复 |
| 30 | `region` | 27,506 | 26,881 | 合并+修正 | `region` | 五种大陆写法统一为 中国大陆；区县写进 region 的忽略 |
| 31 | `city_normalized` | 27,506 | 27,506 | 合并 | `cities` | 只存第一个城市，多城市岗位会漏；由 cities 取代 |
| 32 | `cities_normalized` | 27,506 | 27,506 | 合并+修正 | `cities` | 修复 area_code 字典串；中国→全国；未披露/未知→空列表 |
| 33 | `job_category_normalized` | 27,506 | 27,506 | 改名+修正 | `job_category` | 修正错分后输出，取值=筛选参数 job_category 的枚举 |
| 34 | `graduation_year_normalized` | 27,506 | 27,506 | 改名+改类型 | `graduation_years + graduation_year_basis` | 单值改多值并带依据；原字段把两届压成一届、把活动标题里的届别丢成未披露 |
| 35 | `major_normalized` | 27,506 | 27,506 | 改名+修正 | `major_category` | 与分组名一致；新增 不限、未注明 两个值 |
| 36 | `published_at` | 27,302 | 25,191 | 修正 | `published_at` | 三种格式统一为 YYYY-MM-DD |
| 37 | `job_category` | 27,157 | 23,615 | 改名 | `job_category_raw` | 原文类目；把 job_category 这个名字让给修正后的大类，与筛选参数取值一致 |
| 38 | `campaign_cohort_raw` | 7,563 | 7,563 | 改名 | `campaign_title` | 内容是招聘活动标题，不是届别 |
| 39 | `recruitment_type_raw` | 6,674 | 5,632 | 合并 | `recruitment_type` | 归一化来源，已体现在 recruitment_type |
| 40 | `nature_raw` | 6,666 | 6,666 | 合并 | `recruitment_type` | 同上，只有“校招”一个值 |
| 41 | `job_code` | 4,229 | 4,229 | 合并 | `job_code` | 岗位编号，国企投递时常要填 |
| 42 | `batch_name` | 477 | 477 | 合并 | `campaign_title` | 477 条阿里巴巴批次名，性质同活动标题 |
| 43 | `company` | 444 | 444 | 合并 | `company` | 444 条，值与 recruitment_unit 完全相同 |
| 44 | `title` | 204 | 204 | 合并 | `job_title` | 204 条，值与 job_title 完全相同 |
| 45 | `category` | 204 | 204 | 合并 | `job_category_raw` | 204 条，值与 job_category 完全相同 |
| 46 | `position_code` | 146 | 146 | 合并 | `job_code` | 146 条，性质同 job_code |
| 47 | `job_id` | 65 | 65 | 合并 | `id` | 65 条，值与 id 完全相同 |
| 48 | `detail_url` | 30 | 30 | 合并 | `source_url` | 30 条，值与 source_url 完全相同 |
| 49 | `source_record_id` | 26,835 | 26,835 | 内部 | — | 上游记录号，已拼进 id |
| 50 | `evidence_path` | 13,527 | 9,999 | 内部 | — | 服务器本地证据文件路径 |
| 51 | `deadline_scope` | 13,331 | 11,534 | 内部 | — | 采集流程标记：截止日取自岗位还是公告 |
| 52 | `published_at_scope` | 13,278 | 11,534 | 内部 | — | 采集流程标记：发布日取自哪一层 |
| 53 | `incomplete` | 13,000 | 13,000 | 内部 | — | 采集完整性标记，出现的 13,000 条全为 false |
| 54 | `announcement_evidence_path` | 10,812 | 8,745 | 内部 | — | 服务器本地证据文件路径 |
| 55 | `record_kind` | 7,563 | 7,563 | 内部 | — | 上游记录类型 |
| 56 | `source_status_raw` | 6,666 | 6,666 | 内部 | — | 上游状态码，已折算进 status |
| 57 | `source_is_apply_raw` | 6,666 | 6,666 | 内部 | — | 上游可投递标记，已折算进 status（false→未核验） |
| 58 | `source_group_key` | 6,666 | 6,666 | 内部 | — | 上游分组键 |
| 59 | `directory_evidence_path` | 6,058 | 6,058 | 内部 | — | 服务器本地证据文件路径 |
| 60 | `cohort_scope` | 5,837 | 4,527 | 内部 | — | 采集流程标记；信息已体现在 graduation_year_basis |
| 61 | `company_id` | 240 | 240 | 内部 | — | 上游企业 id |
| 62 | `first_seen_at` | 65 | 65 | 内部 | — | 采集时间戳 |
| 63 | `verified_at` | 65 | 65 | 内部 | — | 采集时间戳，与 reviewed_at 不一致 |
| 64 | `fortune_rank` | 65 | 0 | 内部 | — | 出现的 65 条全为 null |
| 65 | `requirements_scope` | 39 | 39 | 内部 | — | 39 条的采集范围标记 |
| 66 | `education_scope` | 39 | 39 | 内部 | — | 39 条的采集范围标记 |
| 67 | `job_title_scope` | 39 | 39 | 内部 | — | 39 条的采集范围标记 |
| 68 | `recruitment_scope_note` | 8 | 8 | 内部 | — | 8 条的采集范围标记 |
