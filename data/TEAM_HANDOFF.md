# Team Handoff: Data Layer — How to Use It

## What's Built

Two data stores that work together for the chatbot:

1. **SQLite database** (`bps_schools.db`) — 1,019 schools after dedup (111 BPS + 908 non-BPS) with structured fields for hard filtering (grade, age, location, provider type, boolean program flags).

2. **FAISS vector store** (`vector_store/school_index.faiss`) — 111 BPS schools with text descriptions embedded as 384-dim vectors for soft filtering / RAG (e.g., "I want a school with strong arts programs").

Source data: `raw_data/choice_tool_raw.json`.

The two layers combine: hard filter narrows to eligible schools, then semantic search ranks them by the user's preferences.

## How to Use in the Chatbot

Everything goes through one class:

```python
from database import BPSDatabase

db = BPSDatabase()
```

### Key methods:

**1. Hard filter** — concrete constraints:
```python
# BPS schools serving 3rd grade
results = db.hard_filter(grade=3)

# Schools within 1 mile of a location
results = db.hard_filter(grade=1, lat=42.35, lon=-71.06, radius_miles=1.0)

# Non-BPS schools for a 3-year-old (36 months)
results = db.find_schools_by_age(36)

# Boolean filters (UPK, ADA, accepts_ccfa, headstart, etc.)
results = db.find_schools_by_filters(accepts_ccfa=1, headstart=1)
```

**2. Semantic search** — fuzzy queries (BPS only):
```python
results = db.semantic_search("bilingual Spanish dual language", top_k=5)
```

**3. Combined search** — hard filter first, then rank by semantic match:
```python
results = db.search(
    query="arts programs visual arts music",
    grade=6,
    provider_type="Boston Public School",
    top_k=5
)
```

### Other useful methods:
```python
db.get_school_detail("school-id")   # Full record + RAG description
db.get_all_provider_types()          # List of distinct provider types
db.find_schools_near(42.35, -71.08)  # Proximity search
```

## Schema

Primary key is `id` (TEXT). Key columns:

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT | Primary key |
| `school` | TEXT | School name |
| `provider_type` | TEXT | "Boston Public School", "Family Child Care", etc. |
| `grade_min` / `grade_max` | INTEGER | BPS only. K0=-2, K1=-1, K2=0, 1-12 |
| `grade_min_sped` | INTEGER | BPS special education lower bound |
| `age_min_months` / `age_max_months` | INTEGER | Non-BPS only. Age range in months |
| `latitude` / `longitude` | REAL | For proximity search |
| Boolean flags | INTEGER | `UPK`, `ADA`, `accepts_ccfa`, `headstart`, `has_language_program`, `has_advanced_placement`, `has_international_baccalaureate`, `uniform`, `special_admission`, `surround_care`, `build_care`, `tuition` |

## Grade Encoding

| User says | Pass as |
|-----------|---------|
| K0 / Pre-K | `-2` |
| K1 / Kindergarten | `-1` |
| K2 | `0` |
| 1st grade | `1` |
| ... | ... |
| 12th grade | `12` |

Non-BPS schools use age in months instead of grades.

## File Structure

```
data/
├── database.py               # BPSDatabase class — import this
├── build_database.py         # Build pipeline (run once to rebuild)
├── bps_schools.db            # SQLite database (don't edit directly)
├── raw_data/
│   └── choice_tool_raw.json  # Source data (1,027 records, 1,019 after dedup)
├── vector_store/
│   ├── school_index.faiss    # FAISS vector index (BPS only, 111 schools)
│   ├── documents.json        # Text descriptions
│   └── metadata.json         # Structured metadata
└── TEAM_HANDOFF.md           # This file
```

## Setup

```bash
pip install faiss-cpu sentence-transformers numpy
```

The database and vector store are already built (committed to the repo). Only run `build_database.py` if you change the source data.

## Rebuilding

```bash
cd data
python build_database.py                # Build both DB and vector store
python build_database.py --db-only      # SQLite only
python build_database.py --vector-only  # Vector store only
```

## What's NOT in the Data

- Walk zone boundaries (approximated with radius search)
- Transportation eligibility rules
- School capacity / available seats
- MCAS scores / accountability ratings
