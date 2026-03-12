# BPS School Finder - Database Schema & API Reference

## SQLite Table: `schools`

The database contains 1,027 schools (111 BPS + 916 non-BPS) stored in a single `schools` table.

### Fields

| Column | Type | Description | Useful if user wants to know about... |
|--------|------|-------------|---------------------------------------|
| `id` | TEXT (PK) | Unique identifier for the school | Looking up a specific school's full details |
| `school` | TEXT NOT NULL | Official school name | Searching for a school by name |
| `dba` | TEXT | "Doing Business As" — alternate/trade name for the school | Finding a school known by a different or informal name |
| `address` | TEXT | Street address of the school | Where a school is located, directions, or neighborhood |
| `latitude` | REAL | Geographic latitude coordinate | Finding schools near a specific location or address |
| `longitude` | REAL | Geographic longitude coordinate | Finding schools near a specific location or address |
| `provider_type` | TEXT | Category of school (e.g. "Boston Public School", "Family Child Care", "Center Based") | What type of school/program it is, filtering by school category |
| `grade_min` | INTEGER | Lowest grade served (BPS only). Encoding: K0=-2, K1=-1, K2=0, 1-12 as integers | Which schools serve their child's grade level (BPS) |
| `grade_max` | INTEGER | Highest grade served (BPS only). Same encoding as `grade_min` | Which schools serve their child's grade level (BPS) |
| `grade_min_sped` | INTEGER | Lowest grade for special education students (BPS only), if different from `grade_min` | Special education availability at earlier grade levels |
| `age_min_months` | INTEGER | Minimum age served in months (non-BPS only) | Which childcare/preschool accepts their child's age |
| `age_max_months` | INTEGER | Maximum age served in months (non-BPS only) | Which childcare/preschool accepts their child's age |
| `hours_of_operation` | TEXT | Operating hours | Drop-off/pick-up times, scheduling, work-life compatibility |
| `phone_number` | TEXT | Contact phone number | How to contact or call the school |
| `email` | TEXT | Contact email address | How to email or reach out to the school |
| `website` | TEXT | School website URL | Where to learn more, apply, or get additional information |
| `surround_care` | INTEGER | 1 if the school offers surround care (before/after school care), 0 otherwise | Before/after school care, extended day options for working parents |
| `curriculum` | TEXT | Description of curriculum used | Teaching approach, pedagogy, or educational philosophy |
| `tuition` | INTEGER | 1 if tuition is charged, 0 if not, NULL if unknown | Cost, whether the school is free, affordability |
| `headstart` | INTEGER | 1 if the school is a Head Start program, 0 otherwise | Free early childhood programs, federally funded options, low-income eligibility |
| `accepts_ccfa` | INTEGER | 1 if the school accepts CCFA (Child Care Financial Assistance) vouchers, 0 if not, NULL if unknown | Financial assistance, vouchers, subsidized childcare |
| `has_language_program` | INTEGER | 1 if the school offers a language/dual-language program, 0 otherwise | Bilingual education, dual-language immersion, learning a second language |
| `has_international_baccalaureate` | INTEGER | 1 if the school offers an IB program, 0 otherwise | IB programs, internationally recognized diplomas |
| `international_baccalaureate_text` | TEXT | Description of the IB program (empty if none or just "Yes") | Specific IB program details, which IB tracks are offered |
| `has_advanced_placement` | INTEGER | 1 if the school offers AP courses, 0 otherwise | AP classes, college-level coursework, college prep |
| `advanced_placement_text` | TEXT | Description of AP offerings (empty if none or just "Yes") | Which specific AP subjects are available |
| `uniform` | INTEGER | 1 if a uniform is required, 0 if not, NULL if unknown | Dress code, uniform requirements, what their child needs to wear |
| `UPK` | INTEGER | 1 if the school participates in Universal Pre-Kindergarten, 0 otherwise | Free pre-K, universal pre-kindergarten seats |
| `ADA` | INTEGER | 1 if the school is ADA accessible, 0 if not, NULL if unknown | Wheelchair accessibility, physical disability accommodations |
| `special_admission` | INTEGER | 1 if the school requires a special admissions process, 0 otherwise | Application requirements, exam schools, selective enrollment |
| `special_admission_link` | TEXT | URL to special admission application or information | How to apply to a special-admission school |
| `school_quality_framework` | TEXT | BPS school quality framework rating or report link | School ratings, performance, quality metrics |
| `state_report_card` | TEXT | Link to the state report card for the school | Test scores, accountability data, state evaluations |
| `point_of_contact` | TEXT | Name of the school's designated point of contact | Who to talk to, who to reach out to at the school |
| `school_leader` | TEXT | Name of the school's principal or leader | Who runs the school, principal name |
| `build_care` | INTEGER | 1 if the school participates in the BuildCare program, 0 otherwise | BuildCare program availability, additional childcare support |

### Indexes

- `idx_provider_type` — on `provider_type`
- `idx_grades` — on `(grade_min, grade_max)`
- `idx_age` — on `(age_min_months, age_max_months)`
- `idx_latlon` — on `(latitude, longitude)`

---

## BPSDatabase Public Methods

### Hard Filtering (SQL)

#### `find_schools_by_grade(grade: int) -> list`
Find BPS schools that serve a specific grade level. Uses the integer grade encoding (K0=-2, K1=-1, K2=0, 1-12). Returns all schools where the given grade falls within their `grade_min` to `grade_max` range.

#### `find_schools_by_age(age_months: int) -> list`
Find non-BPS schools that serve a specific age given in months. Returns all schools where the given age falls within their `age_min_months` to `age_max_months` range.

#### `find_schools_near(lat: float, lon: float, radius_miles: float = 1.0) -> list`
Find schools within `radius_miles` of a given latitude/longitude. Uses a bounding-box pre-filter for efficiency, then applies exact Haversine distance. Results are sorted by distance (ascending) and include a `distance_miles` field.

#### `find_schools_by_provider_type(provider_type: str) -> list`
Find schools by exact match on `provider_type` (e.g. "Boston Public School", "Family Child Care").

#### `find_schools_by_filters(**kwargs) -> list`
Combined AND filter across boolean/integer fields. Supported keyword arguments: `UPK`, `ADA`, `accepts_ccfa`, `headstart`, `has_language_program`, `has_advanced_placement`, `has_international_baccalaureate`, `uniform`, `special_admission`, `surround_care`, `build_care`, `tuition`. Only non-None values are applied.

#### `hard_filter(grade, age_months, provider_type, lat, lon, radius_miles, **boolean_filters) -> list`
Combined hard filter that applies all specified conditions with AND logic. Combines grade, age, provider type, location proximity, and boolean filters into a single query. If location is provided, results are post-filtered by Haversine distance and sorted by distance.

### Soft Filtering (Vector Search / RAG)

#### `semantic_search(query: str, top_k: int = 10, pre_filter_ids: set = None) -> list`
Semantic search over BPS school descriptions using FAISS and sentence embeddings. Returns the top-k most relevant schools ranked by cosine similarity. If `pre_filter_ids` is provided, only considers schools with those IDs. Falls back to keyword search if the vector store is not loaded. Each result includes `id`, `school`, `score`, `description`, and `metadata`.

### Combined Pipeline

#### `search(query, grade, provider_type, lat, lon, radius_miles, top_k, **filters) -> list`
Full search pipeline that first applies hard filters, then ranks the matching results by semantic similarity to the query. If no query is provided, returns hard-filtered results directly. If hard filtering returns no results, falls back to a pure semantic search.

---

## RAG Descriptions (BPS Schools Only)

RAG descriptions are generated only for BPS schools during the vector store build process (`build_database.py:build_description`). Each description is a multi-paragraph text document assembled by concatenating the following fields from the raw JSON data, in order:

1. **Header sentence** — School name, address, and human-readable grade span (e.g. "K1 to 6 (K0 for special education)")
2. **Overview / mission statement** — From `overview_mission_statement`, if non-empty (excludes `#VALUE!` artifacts)
3. **Unique features** — From `unique_features`, joined if a list
4. **Specialized education programs** — From `specialized_education_programs`
5. **Language programs** — From `language_programming_text`
6. **Early college / dual enrollment** — From `early_college_dual_enrollment`
7. **CTE pathways** — From `CTE_Pathways_TXT`, prefixed with "Career and technical education pathways:"
8. **After school program** — From `after_school_program`
9. **Before school program** — From `before_school_program`
10. **Extracurriculars** — From `extra_curriculars_text`
11. **Sports** — From `sports`, joined if a list
12. **Partners** — From `partners`, joined if a list
13. **Accessibility** — From `ada_description`
14. **Family engagement** — From `family_engagement_opportunities`

Each section is separated by a double newline. Empty or missing fields are silently omitted. These descriptions are then embedded using the `all-MiniLM-L6-v2` sentence transformer model and indexed in a FAISS inner-product index for semantic search.

---

### Utility Methods

#### `get_school_detail(school_id: str) -> dict`
Get the full database record for a single school by its ID. If a vector store description exists for the school, it is included in the result under the `description` key. Returns `None` if no school is found.

#### `get_all_provider_types() -> list`
Get a sorted list of all distinct `provider_type` values in the database.

#### `close()`
Close the underlying SQLite database connection.
