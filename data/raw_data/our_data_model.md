# School Data Model

## Field Reference

| Field | Status | Notes |
|-------|--------|-------|
| `id` | ✅ Included | |
| `school` | ✅ Included | |
| `DBA` | ✅ Included | |
| `address` | ✅ Included | |
| `slim_address` | ❌ Excluded | Unnecessary given `address` |
| `latitude` | ✅ Included | |
| `longitude` | ✅ Included | |
| `grade_span` | 🔀 Merged | Merged with `grade_range` and `grades_filter` into single `grade_min` to `grade_max` field |
| `grade_range` | 🔀 Merged | See `grade_span` |
| `grades_filter` | 🔀 Merged | See `grade_span` |
| `provider_type` | ✅ Included | |
| `surround_care` | ✅ Included | Filter only applicable to nonBPS schools; indicative of after/before school programs |
| `aftercare` | ❌ Excluded | Subset of `surround_care` |
| `extended_day` | ❌ Excluded | Empty field |
| `curriculum` | ✅ Included | Categorical enumeration; only applicable for nonBPS |
| `hours_of_operation` | ✅ Included | |
| `phone_number` | ✅ Included | |
| `email` | ✅ Included | |
| `website` | ✅ Included | |
| `bps_quality_tier` | ❌ Excluded | Better to refer to state_report_card and school_quality_framework |
| `programs` | ❌ Excluded | Only relevant for nonBPS; contains semantic data but avoiding RAG for nonBPS for now |
| `facility_features` | ❌ Excluded | Empty for all schools |
| `school_size` | ❌ Excluded | Empty for all schools |
| `sports` | 📚 RAG | Added to RAG for BPS schools; 106 unique values make it impractical as a filter, but useful for semantic queries |
| `tuition` | ✅ Included | 92% fill rate for nonBPS (BPS are free); usable as filter with caveat for empty values |
| `free_upk_hours` | ❌ Excluded | Strict subset of `UPK` boolean |
| `eligibility` | ❌ Excluded | LLM should not make eligibility decisions; directs user to choice tool |
| `separate_application` | ❌ Excluded | Links are defunct |
| `headstart` | ✅ Included | Filter for nonBPS; directs to [Boston ABCD Head Start](https://bostonabcd.org/service/head-start-childrens-services/) for eligibility |
| `accepts_ccfa` | ✅ Included | Useful for nonBPS financial assistance; directs to [CCFA info](https://www.mass.gov/child-care-financial-assistance) |
| `language_programming_text` | 📚 RAG and 🔀 Merged | for BPS we use as RAG, for nonBPS we union with `dual_language` and `language_programming_filter`  to create new boolean called `has_language_program`|
| `dual_language` | 🔀 Merged | See `language_programming_text` |
| `language_programming_filter` | 🔀 Merged | See `language_programming_text` |
| `stem_steam` | ❌ Excluded | Unreliable to use as filter.. better to rely on RAG from school mission/academic statements |
| `vocational_technology` | ❌ Excluded | Same reasoning as `stem_steam` |
| `early_college_dual_enrollment` | 📚 RAG | Semantic description of eligible colleges included in RAG |
| `international_baccalaureate` | ✅ Included | Very specific; only 3 schools offer it — model reports directly |
| `advanced_placement` | ✅ Included | Acts as filter; similar reasoning to `international_baccalaureate`; retrieval includes text description of available classes |
| `arts` | ❌ Excluded | Same reasoning as `stem_steam` |
| `clubs` | ❌ Excluded | Empty for all schools |
| `specialized_education_programs` | 📚 RAG | Semantic descriptions of SPED programs |
| `uniform` | ✅ Included | High fill rate for BPS (good filter); lower for nonBPS (include confidence caveat in LLM response) |
| `after_school_program` | 📚 RAG | Semantic descriptions |
| `overview_mission_statement` | 📚 RAG | Core identity of each school |
| `unique_features` | 📚 RAG | What sets the school apart |
| `arts_rooms` | ❌ Excluded | Empty across all schools |
| `athletic_field` | ❌ Excluded | Empty across all schools |
| `cafeteria` | ❌ Excluded | Empty across all schools |
| `gymnasium` | ❌ Excluded | Empty across all schools |
| `library` | ❌ Excluded | Empty across all schools |
| `music_room` | ❌ Excluded | Empty across all schools |
| `outdoor_classrooms` | ❌ Excluded | Empty across all schools |
| `playground` | ❌ Excluded | Empty across all schools |
| `pool` | ❌ Excluded | Empty across all schools |
| `science_lab` | ❌ Excluded | Empty across all schools |
| `partners` | 📚 RAG | Lists partner programs; good for semantic search |
| `partners_link` | ❌ Excluded | Informational for schools, not users |
| `UPK` | ✅ Included | Good filter for BPS and nonBPS; potential for additional UPK, LLM should concede the public data is scarce in this regard|
| `BPS_eligibility` | ❌ Excluded | Directing users to online choice tool |
| `ADA` | ✅ Included | Clean filter for BPS; fewer nonBPS list it — retrieval should note this caveat to LLM |
| `tiers_text` | ❌ Excluded | Never used in raw data |
| `transportation` | ❌ Excluded | Directs user to public school transportation system link |
| `prek_bps_connector` | ❌ Excluded | Never used in raw data |
| `special_admission_school` | 🔀 Merged | Merged with `special_admission_filter` and `special_admission_link`; includes link for more info |
| `special_admission_filter` | 🔀 Merged | See `special_admission_school` |
| `special_admission_link` | 🔀 Merged | See `special_admission_school` |
| `school_quality_framework` | ✅ Included | With `state_report_card`, directs users to compare school performance |
| `school_quality_tier` | ❌ Excluded | Unnecessary given `school_quality_framework` and `state_report_card` |
| `preview_session_1` | ❌ Excluded | Outdated |
| `preview_session_2` | ❌ Excluded | Outdated |
| `preview_session_3` | ❌ Excluded | Outdated |
| `point_of_contact` | ✅ Included | Important for retrieval |
| `school_leader` | ✅ Included | Important for retrieval |
| `before_school_program` | 📚 RAG | Semantic descriptions |
| `ada_description` | 📚 RAG | Semantic descriptions |
| `uniform_policy` | ❌ Excluded | Unnecessary given `uniform` filter |
| `extra_curriculars_text` | 📚 RAG | Common user question; good semantic content |
| `innovation_pathways` | ❌ Excluded | Unused in raw data |
| `specialized_education_filter` | ❌ Excluded | Redundant with `specialized_education_programs` |
| `announcement_text` | ❌ Excluded | Unused |
| `other_academic_programs` | ❌ Excluded | Unused |
| `show_eligibility_check` | ❌ Excluded | Unused |
| `BuildCare` | ✅ Included | Filter for nonBPS schools only |
| `family_engagement_opportunities` | 📚 RAG | Text descriptions; important for users curious about family engagement |
| `CTE_Pathways_TXT` | 📚 RAG | semantic descriptions of career options |
| `state_report_card` | ✅ Included | See `school_quality_framework` |

---

## Status Key

| Symbol | Meaning |
|--------|---------|
| ✅ Included | Used as a structured filter or direct retrieval field |
| ❌ Excluded | Not included in the data model |
| 🔀 Merged | Combined with other fields |
| 📚 RAG | Included in semantic RAG embeddings |