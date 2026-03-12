# Plan: Rebuild bps_schools.db + Vector Store from choice_tool_raw.json

## Context
The current `build_database.py` builds from `public_schools.csv` (131 BPS-only schools) + hand-curated `school_descriptions.json`. We're replacing this with `choice_tool_raw.json` (1,027 schools: 111 BPS + 916 non-BPS early childhood) as the single source of truth. The data model (`our_data_model.md`) defines which fields become SQL columns, which become RAG embeddings, and which are excluded.

**Key decisions made:**
- Only BPS schools (111) get RAG vector embeddings
- All 1,027 schools go into the SQL database
- BPS uses integer grade encoding (K0=-2 through 12); non-BPS gets separate `age_min_months`/`age_max_months`
- BPS gets `grade_min_sped` column (NULL when no SpEd extension)
- `has_language_program` boolean: for non-BPS = union of `dual_language`, `language_programming_filter`, `language_programming_text`; for BPS = derived from `language_programming_text` (SLIFE/Newcomer/TBE/DL programs)
- CTE_Pathways_TXT included in RAG

---

## File to modify
`/Users/ld/6.C395-chatbot/data/build_database.py` — complete rewrite of the build pipeline

## Source data
`/Users/ld/6.C395-chatbot/data/raw_data/choice_tool_raw.json`

## Output artifacts
- `/Users/ld/6.C395-chatbot/data/bps_schools.db` — SQLite database (all 1,027 schools)
- `/Users/ld/6.C395-chatbot/data/vector_store/school_index.faiss` — FAISS index (111 BPS only)
- `/Users/ld/6.C395-chatbot/data/vector_store/documents.json` — RAG text descriptions
- `/Users/ld/6.C395-chatbot/data/vector_store/metadata.json` — school metadata per vector

---

## Part 1: SQLite Schema

### `schools` table — all 1,027 schools

| Column | Type | Source | Construction |
|--------|------|--------|-------------|
| `id` | TEXT PK | `id` | Direct copy (TEXT because IDs are 4-7 chars, not always numeric-meaningful) |
| `school` | TEXT NOT NULL | `school` | Direct copy |
| `dba` | TEXT | `DBA` | Direct copy |
| `address` | TEXT | `address` | Direct copy |
| `latitude` | REAL | `latitude` | `float(latitude)`, NULL if empty |
| `longitude` | REAL | `longitude` | `float(longitude)`, NULL if empty |
| `provider_type` | TEXT | `provider_type` | Direct copy. Values: `Boston Public School`, `Family Child Care`, `Community Based Organization`, `Independent School`, `Charter School`, `Center-Based Child Care, Independent Preschool`, `Independent Special Education School` |
| `grade_min` | INTEGER | `grade_span` + `grades_filter` | BPS only: parsed from grade_span. K0=-2, K1=-1, K2=0, 1-12. NULL for non-BPS |
| `grade_max` | INTEGER | `grade_span` + `grades_filter` | BPS only: parsed from grade_span. NULL for non-BPS |
| `grade_min_sped` | INTEGER | `grade_span` | BPS only: lower bound when "(K0 for special education)" present. NULL when no SpEd extension or non-BPS |
| `age_min_months` | INTEGER | `grade_span` | Non-BPS only: age in months. `0yr`→0, `1yr`→12, `15 months`→15, `0.2yr`→2, `3yr`→36, etc. NULL for BPS |
| `age_max_months` | INTEGER | `grade_span` | Non-BPS only: `5yr`→60, `4yr`→48, `3yr`→36, etc. NULL for BPS |
| `hours_of_operation` | TEXT | `hours_of_operation` | Direct copy, empty string if missing |
| `phone_number` | TEXT | `phone_number` | Direct copy |
| `email` | TEXT | `email` | Direct copy |
| `website` | TEXT | `website` | Direct copy |
| `surround_care` | INTEGER | `surround_care` | Boolean: 1 if list contains non-empty values, 0 otherwise. Non-BPS filter |
| `curriculum` | TEXT | `curriculum` | Direct copy. Non-BPS only (always empty for BPS) |
| `tuition` | INTEGER | `tuition` | 1 if "Yes"/"yes", 0 if "No"/"no", NULL if empty. BPS always NULL (free) |
| `headstart` | INTEGER | `headstart` | 1 if "Yes", 0 otherwise |
| `accepts_ccfa` | INTEGER | `accepts_ccfa` | 1 if "Yes", 0 if "No", NULL if empty |
| `has_language_program` | INTEGER | merged | BPS: 1 if `language_programming_text` is non-empty, 0 otherwise. Non-BPS: 1 if ANY of `dual_language` (not "No"), `language_programming_filter`="Yes", or `language_programming_text` non-empty; 0 otherwise |
| `has_international_baccalaureate` | INTEGER | `international_baccalaureate` | 1 if non-empty (includes "Yes" or text), 0 otherwise |
| `international_baccalaureate_text` | TEXT | `international_baccalaureate` | Full text description (e.g. Snowden's IB program details). Empty string if none or bare "Yes" |
| `has_advanced_placement` | INTEGER | `advanced_placement` | 1 if non-empty, 0 otherwise |
| `advanced_placement_text` | TEXT | `advanced_placement` | Full text description of AP courses. Empty string if none |
| `uniform` | INTEGER | `uniform` | 1 if "Yes", 0 if "No", NULL if empty |
| `UPK` | INTEGER | `UPK` | 1 if "Yes", 0 otherwise |
| `ADA` | INTEGER | `ADA` | 1 if "Yes", 0 if "No", NULL if empty |
| `special_admission` | INTEGER | `special_admission_filter` | 1 if "Yes", 0 if "No" |
| `special_admission_link` | TEXT | `special_admission_link` | URL, empty string if none |
| `school_quality_framework` | TEXT | `school_quality_framework` | URL, empty string if none |
| `state_report_card` | TEXT | `state_report_card` | URL, empty string if none |
| `point_of_contact` | TEXT | `point_of_contact` | Direct copy, empty string if missing |
| `school_leader` | TEXT | `school_leader` | Direct copy, empty string if missing |
| `build_care` | INTEGER | `BuildCare` | 1 if "Yes", 0 otherwise. Non-BPS filter |

### Indexes
- `idx_provider_type` on `provider_type`
- `idx_grades` on (`grade_min`, `grade_max`)
- `idx_age` on (`age_min_months`, `age_max_months`)
- `idx_latlon` on (`latitude`, `longitude`)

### Grade parsing logic for BPS `grade_span`

| Pattern | grade_min | grade_max | grade_min_sped |
|---------|-----------|-----------|----------------|
| `"K1 - 6; (K0 for special education)"` | -1 (K1) | 6 | -2 (K0) |
| `"K0 - 6"` | -2 (K0) | 6 | NULL |
| `"7-12"` | 7 | 12 | NULL |
| `"K0, K2 - 6"` | -2 (K0) | 6 | NULL (K0 is already min) |
| `"K0 - 1"` | -2 (K0) | 1 | NULL |
| `"9-11"` | 9 | 11 | NULL |
| `"12"` | 12 | 12 | NULL |
| `"2-6"` | 2 | 6 | NULL |

Grade encoding map: `K0`→-2, `K1`→-1, `K2`→0, `1`-`12`→1-12

### Age parsing logic for non-BPS `grade_span`

| Pattern | age_min_months | age_max_months |
|---------|----------------|----------------|
| `"0yr - 5yr"` | 0 | 60 |
| `"1yr - 5yr"` | 12 | 60 |
| `"3yr - 5yr"` | 36 | 60 |
| `"15 months - 5yr"` | 15 | 60 |
| `"0.2yr - 5yr"` | 2 | 60 |
| `"5yr"` | 60 | 60 |
| `"3yr- 4yr"` | 36 | 48 |
| `"0yr - 2.9yr"` | 0 | 35 |
| `"15 months - 4yr"` | 15 | 48 |

---

## Part 2: RAG Vector Embeddings (BPS only — 111 schools)

### Embedding model
- `all-MiniLM-L6-v2` (same as current)
- 384-dimensional vectors, FAISS IndexFlatIP with normalized embeddings

### Description template (natural language paragraphs)
For each BPS school, compose a description from non-empty fields in this order:

```
{school} is a Boston Public School located at {address}, serving grades {grade_span_human_readable}.

{overview_mission_statement}

{unique_features}  (joined from list)

[If specialized_education_programs non-empty:]
Specialized education programs: {specialized_education_programs}

[If language_programming_text non-empty:]
Language programs: {language_programming_text}

[If early_college_dual_enrollment non-empty:]
Early college and dual enrollment: {early_college_dual_enrollment}

[If CTE_Pathways_TXT non-empty:]
Career and technical education pathways: {CTE_Pathways_TXT}

[If after_school_program non-empty:]
After school: {after_school_program}

[If before_school_program non-empty:]
Before school: {before_school_program}

[If extra_curriculars_text non-empty:]
Extracurriculars: {extra_curriculars_text}

[If sports non-empty (list, joined):]
Sports: {sports}

[If partners non-empty (list, joined):]
Partners: {partners}

[If ada_description non-empty:]
Accessibility: {ada_description}

[If family_engagement_opportunities non-empty:]
Family engagement: {family_engagement_opportunities}
```

### RAG fields summary (all BPS-only)

| Source field | How used in description |
|---|---|
| `overview_mission_statement` | Core paragraph |
| `unique_features` | List → joined text |
| `specialized_education_programs` | Labeled section |
| `language_programming_text` | Labeled section |
| `early_college_dual_enrollment` | Labeled section |
| `CTE_Pathways_TXT` | Labeled section |
| `after_school_program` | Labeled section |
| `before_school_program` | Labeled section |
| `extra_curriculars_text` | Labeled section |
| `sports` | List → joined text |
| `partners` | List → joined text |
| `ada_description` | Labeled section |
| `family_engagement_opportunities` | Labeled section |

### Vector store metadata (per school)
Stored in `metadata.json` alongside the FAISS index for post-retrieval enrichment:
```json
{
  "id": "4361",
  "school": "Boston Latin School",
  "provider_type": "Boston Public School",
  "grade_min": 7,
  "grade_max": 12,
  "latitude": 42.345,
  "longitude": -71.098
}
```

---

## Part 3: BPSDatabase Query Class

Rewrite the query class to support the new schema:

### Hard filter methods
- `find_schools_by_grade(grade)` — `WHERE grade_min <= ? AND grade_max >= ?` (BPS)
- `find_schools_by_age(age_months)` — `WHERE age_min_months <= ? AND age_max_months >= ?` (non-BPS)
- `find_schools_near(lat, lon, radius_miles)` — haversine distance filter
- `find_schools_by_provider_type(provider_type)` — exact match
- `find_schools_by_filters(**kwargs)` — combined AND filter for boolean fields (UPK, ADA, accepts_ccfa, headstart, has_language_program, has_advanced_placement, has_international_baccalaureate, uniform, special_admission, surround_care, build_care, tuition)
- `hard_filter(grade, age_months, provider_type, lat, lon, radius_miles, **boolean_filters)` — combined method

### Semantic search methods (BPS only)
- `semantic_search(query, top_k, pre_filter_ids)` — FAISS vector search
- `_keyword_search(query, top_k, pre_filter_ids)` — fallback

### Combined search
- `search(query, grade, provider_type, lat, lon, radius_miles, top_k, **filters)` — hard filter → semantic re-rank

### Utility methods
- `get_school_detail(id)` — full school record + RAG description
- `get_all_provider_types()` — distinct provider types
- `haversine_miles(lat1, lon1, lat2, lon2)` — distance calculation

---

## Part 4: Implementation Steps

1. **Rewrite `build_database.py`** to:
   - Load `choice_tool_raw.json` as sole data source
   - Parse grades (BPS integer encoding + non-BPS age-in-months)
   - Create SQLite schema with new table definition
   - Insert all 1,027 schools
   - Generate RAG descriptions for 111 BPS schools
   - Build FAISS index from BPS descriptions
   - Save vector store files

2. **Data cleaning during build:**
   - Normalize `tuition`: "yes"/"Yes" → 1, "no"/"No" → 0
   - Normalize `specialized_education_filter`: "yes" → "Yes"
   - Handle `#VALUE!` in `overview_mission_statement` → treat as empty
   - Strip whitespace from all text fields

3. **No new files created** — rewrite `build_database.py` in place

4. **Copy plan to `data/build_plan.md`** for future reference

---

## Verification

1. Run `python data/build_database.py` — should complete without errors
2. Verify SQLite: `SELECT COUNT(*) FROM schools` → 1027
3. Verify BPS: `SELECT COUNT(*) FROM schools WHERE provider_type = 'Boston Public School'` → 111
4. Verify grades: `SELECT COUNT(*) FROM schools WHERE grade_min IS NOT NULL` → 111 (BPS only)
5. Verify ages: `SELECT COUNT(*) FROM schools WHERE age_min_months IS NOT NULL` → 916 (non-BPS only)
6. Verify vector store: `documents.json` has 111 entries
7. Test semantic search: query "arts and music programs" should return arts-focused BPS schools
8. Test hard filter: grade=9 should return high schools
9. Test age filter: age_months=36 should return early childhood providers serving 3-year-olds
10. Test combined: provider_type="Family Child Care" + accepts_ccfa=1 should return ~148 results

### Note on actual counts
The source JSON contains 8 duplicate ID pairs (16 records), so after deduplication the actual counts are:
- Total: 1,019 (not 1,027)
- Non-BPS with ages: 908 (not 916)
- Family Child Care + accepts_ccfa: 145
