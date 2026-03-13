#!/usr/bin/env python3
"""
BPS School Finder - Database & Vector Store Builder
====================================================
Builds from choice_tool_raw.json (1,027 schools: 111 BPS + 916 non-BPS):
1. SQLite database (bps_schools.db) for hard filtering
2. FAISS vector index + metadata JSON for soft filtering via RAG (BPS only)

Usage:
    python build_database.py                    # Build both DB and vector store
    python build_database.py --db-only          # Build only SQLite
    python build_database.py --vector-only      # Build only vector store

Requirements:
    pip install faiss-cpu sentence-transformers numpy
"""

import sqlite3
import json
import math
import re
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RAW_JSON = Path(__file__).parent / "raw_data" / "choice_tool_raw.json"
DB_PATH = Path(__file__).parent / "bps_schools.db"
VECTOR_DIR = Path(__file__).parent / "vector_store"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

GRADE_MAP = {"K0": -2, "K1": -1, "K2": 0}
for i in range(1, 13):
    GRADE_MAP[str(i)] = i

IS_BPS = "Boston Public School"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_raw_data() -> list:
    with open(RAW_JSON, encoding="utf-8") as f:
        return json.load(f)


def safe_float(val):
    """Convert to float or return None."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def strip_or_empty(val):
    """Return stripped string or empty string."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()


def bool_yes(val) -> int:
    """1 if val is 'Yes'/'yes', 0 otherwise."""
    return 1 if strip_or_empty(val).lower() == "yes" else 0


def bool_yes_no_null(val):
    """1 if yes, 0 if no, None if empty."""
    v = strip_or_empty(val).lower()
    if v == "yes":
        return 1
    if v == "no":
        return 0
    return None


def bool_nonempty(val) -> int:
    """1 if val is non-empty string, 0 otherwise."""
    return 1 if strip_or_empty(val) else 0


def list_has_content(val) -> int:
    """1 if list contains at least one non-empty string, 0 otherwise."""
    if not isinstance(val, list):
        return bool_nonempty(val)
    return 1 if any(strip_or_empty(v) for v in val) else 0


def join_list(val) -> str:
    """Join a list field, filtering out empty strings."""
    if not isinstance(val, list):
        return strip_or_empty(val)
    items = [strip_or_empty(v) for v in val if strip_or_empty(v)]
    return "; ".join(items)


def clean_text(val) -> str:
    """Strip text and handle #VALUE! as empty."""
    t = strip_or_empty(val)
    if t == "#VALUE!":
        return ""
    return t


def haversine_miles(lat1, lon1, lat2, lon2):
    """Calculate distance in miles between two lat/lon points."""
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Grade / age parsing
# ---------------------------------------------------------------------------

def parse_grade_token(token: str) -> int:
    """Parse a single grade token like 'K0', 'K1', 'K2', '7' into an integer."""
    token = token.strip().upper()
    if token in GRADE_MAP:
        return GRADE_MAP[token]
    try:
        return int(token)
    except ValueError:
        return None


def parse_bps_grade_span(grade_span: str):
    """
    Parse BPS grade_span into (grade_min, grade_max, grade_min_sped).

    Examples:
        'K1 - 6; (K0 for special education)' -> (-1, 6, -2)
        'K0 - 6' -> (-2, 6, None)
        '7-12' -> (7, 12, None)
        'K0, K2 - 6' -> (-2, 6, None)
        '12' -> (12, 12, None)
    """
    gs = strip_or_empty(grade_span)
    if not gs:
        return None, None, None

    grade_min_sped = None

    # Extract special education extension
    sped_match = re.search(r'\((\w+)\s+for special education\)', gs)
    if sped_match:
        grade_min_sped = parse_grade_token(sped_match.group(1))
        gs = gs[:sped_match.start()].strip().rstrip(";").strip()

    # Handle "K0, K2 - 6" pattern: take min of first token and range start
    if "," in gs:
        parts = gs.split(",")
        first_token = parse_grade_token(parts[0].strip())
        # Parse the range part
        range_part = parts[-1].strip()
        if "-" in range_part:
            lo_str, hi_str = range_part.split("-", 1)
            lo = parse_grade_token(lo_str)
            hi = parse_grade_token(hi_str)
            grade_min = min(g for g in [first_token, lo] if g is not None)
            return grade_min, hi, grade_min_sped
        else:
            tokens = [parse_grade_token(p.strip()) for p in parts]
            tokens = [t for t in tokens if t is not None]
            return min(tokens), max(tokens), grade_min_sped

    # Handle range "K1 - 6" or "7-12"
    # Normalize spaces around dash
    range_match = re.match(r'(\w+)\s*-\s*(\w+)', gs)
    if range_match:
        lo = parse_grade_token(range_match.group(1))
        hi = parse_grade_token(range_match.group(2))
        return lo, hi, grade_min_sped

    # Single grade "12"
    g = parse_grade_token(gs)
    if g is not None:
        return g, g, grade_min_sped

    return None, None, None


def parse_age_span(grade_span: str):
    """
    Parse non-BPS grade_span into (age_min_months, age_max_months).

    Examples:
        '0yr - 5yr' -> (0, 60)
        '15 months - 5yr' -> (15, 60)
        '0.2yr - 5yr' -> (2, 60)
        '5yr' -> (60, 60)
        '3yr- 4yr' -> (36, 48)
        '0yr - 2.9yr' -> (0, 35)
    """
    gs = strip_or_empty(grade_span)
    if not gs:
        return None, None

    def age_token_to_months(token: str) -> int:
        token = token.strip()
        # "15 months" or "15months"
        m = re.match(r'([\d.]+)\s*months?', token, re.IGNORECASE)
        if m:
            return int(float(m.group(1)))
        # "0.2yr" or "5yr" or "0yr"
        m = re.match(r'([\d.]+)\s*yr', token, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            months = round(val * 12)
            return months
        return None

    # Try range: "Xyr - Yyr" (with possibly missing space around dash)
    range_match = re.match(r'(.+?)\s*-\s*(.+)', gs)
    if range_match:
        lo = age_token_to_months(range_match.group(1))
        hi = age_token_to_months(range_match.group(2))
        return lo, hi

    # Single value: "5yr"
    val = age_token_to_months(gs)
    if val is not None:
        return val, val

    return None, None


# ---------------------------------------------------------------------------
# has_language_program logic
# ---------------------------------------------------------------------------

def compute_has_language_program(school: dict) -> int:
    """
    BPS: 1 if language_programming_text is non-empty.
    Non-BPS: 1 if ANY of dual_language (not "No"), language_programming_filter="Yes",
             or language_programming_text non-empty.
    """
    is_bps = school.get("provider_type") == IS_BPS
    lpt = strip_or_empty(school.get("language_programming_text"))

    if is_bps:
        return 1 if lpt else 0

    dl = strip_or_empty(school.get("dual_language"))
    lpf = strip_or_empty(school.get("language_programming_filter"))

    if lpt:
        return 1
    if dl and dl.lower() != "no":
        return 1
    if lpf.lower() == "yes":
        return 1
    return 0


# ---------------------------------------------------------------------------
# IB / AP text extraction
# ---------------------------------------------------------------------------

def extract_ib_text(val: str) -> str:
    """Return IB text description, empty string if just 'Yes' or empty."""
    v = strip_or_empty(val)
    if not v or v.lower() == "yes":
        return ""
    return v


def extract_ap_text(val: str) -> str:
    v = strip_or_empty(val)
    if not v or v.lower() == "yes":
        return ""
    return v


# ---------------------------------------------------------------------------
# 1. Build SQLite Database
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE schools (
    id                          TEXT PRIMARY KEY,
    school                      TEXT NOT NULL,
    dba                         TEXT,
    address                     TEXT,
    latitude                    REAL,
    longitude                   REAL,
    provider_type               TEXT,
    grade_min                   INTEGER,
    grade_max                   INTEGER,
    grade_min_sped              INTEGER,
    age_min_months              INTEGER,
    age_max_months              INTEGER,
    hours_of_operation          TEXT,
    phone_number                TEXT,
    email                       TEXT,
    website                     TEXT,
    surround_care               INTEGER,
    curriculum                  TEXT,
    tuition                     INTEGER,
    headstart                   INTEGER,
    accepts_ccfa                INTEGER,
    has_language_program        INTEGER,
    has_international_baccalaureate INTEGER,
    international_baccalaureate_text TEXT,
    has_advanced_placement      INTEGER,
    advanced_placement_text     TEXT,
    uniform                     INTEGER,
    UPK                         INTEGER,
    ADA                         INTEGER,
    special_admission           INTEGER,
    special_admission_link      TEXT,
    school_quality_framework    TEXT,
    state_report_card           TEXT,
    point_of_contact            TEXT,
    school_leader               TEXT,
    build_care                  INTEGER,
    description                 TEXT
);

CREATE INDEX idx_provider_type ON schools(provider_type);
CREATE INDEX idx_grades ON schools(grade_min, grade_max);
CREATE INDEX idx_age ON schools(age_min_months, age_max_months);
CREATE INDEX idx_latlon ON schools(latitude, longitude);
"""

INSERT_SQL = """
INSERT INTO schools VALUES (
    :id, :school, :dba, :address, :latitude, :longitude, :provider_type,
    :grade_min, :grade_max, :grade_min_sped,
    :age_min_months, :age_max_months,
    :hours_of_operation, :phone_number, :email, :website,
    :surround_care, :curriculum, :tuition, :headstart, :accepts_ccfa,
    :has_language_program,
    :has_international_baccalaureate, :international_baccalaureate_text,
    :has_advanced_placement, :advanced_placement_text,
    :uniform, :UPK, :ADA,
    :special_admission, :special_admission_link,
    :school_quality_framework, :state_report_card,
    :point_of_contact, :school_leader, :build_care, :description
)
"""


def transform_school(s: dict) -> dict:
    """Transform a raw school record into a database row dict."""
    is_bps = s.get("provider_type") == IS_BPS

    # Grade / age parsing
    grade_min = grade_max = grade_min_sped = None
    age_min = age_max = None

    if is_bps:
        grade_min, grade_max, grade_min_sped = parse_bps_grade_span(s.get("grade_span", ""))
    else:
        age_min, age_max = parse_age_span(s.get("grade_span", ""))

    ib_raw = strip_or_empty(s.get("international_baccalaureate"))
    ap_raw = strip_or_empty(s.get("advanced_placement"))

    return {
        "id": strip_or_empty(s.get("id")),
        "school": strip_or_empty(s.get("school")),
        "dba": strip_or_empty(s.get("DBA")),
        "address": strip_or_empty(s.get("address")),
        "latitude": safe_float(s.get("latitude")),
        "longitude": safe_float(s.get("longitude")),
        "provider_type": strip_or_empty(s.get("provider_type")),
        "grade_min": grade_min,
        "grade_max": grade_max,
        "grade_min_sped": grade_min_sped,
        "age_min_months": age_min,
        "age_max_months": age_max,
        "hours_of_operation": strip_or_empty(s.get("hours_of_operation")),
        "phone_number": strip_or_empty(s.get("phone_number")),
        "email": strip_or_empty(s.get("email")),
        "website": strip_or_empty(s.get("website")),
        "surround_care": list_has_content(s.get("surround_care")),
        "curriculum": strip_or_empty(s.get("curriculum")),
        "tuition": bool_yes_no_null(s.get("tuition")),
        "headstart": bool_yes(s.get("headstart")),
        "accepts_ccfa": bool_yes_no_null(s.get("accepts_ccfa")),
        "has_language_program": compute_has_language_program(s),
        "has_international_baccalaureate": 1 if ib_raw else 0,
        "international_baccalaureate_text": extract_ib_text(ib_raw),
        "has_advanced_placement": 1 if ap_raw else 0,
        "advanced_placement_text": extract_ap_text(ap_raw),
        "uniform": bool_yes_no_null(s.get("uniform")),
        "UPK": bool_yes(s.get("UPK")),
        "ADA": bool_yes_no_null(s.get("ADA")),
        "special_admission": bool_yes(s.get("special_admission_filter")),
        "special_admission_link": strip_or_empty(s.get("special_admission_link")),
        "school_quality_framework": strip_or_empty(s.get("school_quality_framework")),
        "state_report_card": strip_or_empty(s.get("state_report_card")),
        "point_of_contact": strip_or_empty(s.get("point_of_contact")),
        "school_leader": strip_or_empty(s.get("school_leader")),
        "build_care": bool_yes(s.get("BuildCare")),
        "description": build_description(s) if is_bps else None,
    }


def build_sqlite():
    """Build the SQLite database from choice_tool_raw.json."""
    print("=" * 60)
    print("Building SQLite Database")
    print("=" * 60)

    data = load_raw_data()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    seen_ids = set()
    for s in data:
        sid = strip_or_empty(s.get("id"))
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        row = transform_school(s)
        cur.execute(INSERT_SQL, row)

    conn.commit()

    # Summary
    cur.execute("SELECT COUNT(*) FROM schools")
    total = cur.fetchone()[0]
    cur.execute("SELECT provider_type, COUNT(*) FROM schools GROUP BY provider_type ORDER BY COUNT(*) DESC")
    type_counts = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM schools WHERE grade_min IS NOT NULL")
    graded = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM schools WHERE age_min_months IS NOT NULL")
    aged = cur.fetchone()[0]

    print(f"\nInserted {total} schools")
    print(f"  With grade_min/grade_max (BPS): {graded}")
    print(f"  With age_min/age_max (non-BPS): {aged}")
    print(f"\nBy provider_type:")
    for t, c in type_counts:
        print(f"  {t:45s}: {c}")

    conn.close()
    print(f"\nDatabase saved to: {DB_PATH}")
    return total


# ---------------------------------------------------------------------------
# 2. Build Vector Store (BPS only)
# ---------------------------------------------------------------------------

def grade_span_human_readable(grade_min, grade_max, grade_min_sped):
    """Convert integer grades back to human-readable string."""
    def g(v):
        if v == -2: return "K0"
        if v == -1: return "K1"
        if v == 0: return "K2"
        return str(v)

    if grade_min is None or grade_max is None:
        return "unknown grades"

    base = f"{g(grade_min)} to {g(grade_max)}"
    if grade_min_sped is not None:
        base += f" ({g(grade_min_sped)} for special education)"
    return base


def build_description(s: dict) -> str:
    """Build a RAG description for a BPS school."""
    grade_min, grade_max, grade_min_sped = parse_bps_grade_span(s.get("grade_span", ""))
    grades_hr = grade_span_human_readable(grade_min, grade_max, grade_min_sped)

    parts = [
        f"{strip_or_empty(s.get('school'))} is a Boston Public School located at "
        f"{strip_or_empty(s.get('address'))}, serving grades {grades_hr}."
    ]

    overview = clean_text(s.get("overview_mission_statement"))
    if overview:
        parts.append(overview)

    unique = join_list(s.get("unique_features"))
    if unique:
        parts.append(unique)

    field_sections = [
        ("specialized_education_programs", "Specialized education programs"),
        ("language_programming_text", "Language programs"),
        ("early_college_dual_enrollment", "Early college and dual enrollment"),
        ("CTE_Pathways_TXT", "Career and technical education pathways"),
        ("after_school_program", "After school"),
        ("before_school_program", "Before school"),
        ("extra_curriculars_text", "Extracurriculars"),
    ]

    for field, label in field_sections:
        val = clean_text(s.get(field))
        if val:
            parts.append(f"{label}: {val}")

    # List fields
    sports = join_list(s.get("sports"))
    if sports:
        parts.append(f"Sports: {sports}")

    partners = join_list(s.get("partners"))
    if partners:
        parts.append(f"Partners: {partners}")

    ada_desc = clean_text(s.get("ada_description"))
    if ada_desc:
        parts.append(f"Accessibility: {ada_desc}")

    family = clean_text(s.get("family_engagement_opportunities"))
    if family:
        parts.append(f"Family engagement: {family}")

    return "\n\n".join(parts)


def build_vector_store():
    """Build FAISS vector index and metadata from BPS school descriptions."""
    print("\n" + "=" * 60)
    print("Building Vector Store (BPS only)")
    print("=" * 60)

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    data = load_raw_data()
    bps_schools = [s for s in data if s.get("provider_type") == IS_BPS]

    documents = []
    metadata = []

    for s in bps_schools:
        desc = build_description(s)
        documents.append(desc)

        grade_min, grade_max, _ = parse_bps_grade_span(s.get("grade_span", ""))

        metadata.append({
            "id": strip_or_empty(s.get("id")),
            "school": strip_or_empty(s.get("school")),
            "provider_type": IS_BPS,
            "grade_min": grade_min,
            "grade_max": grade_max,
            "latitude": safe_float(s.get("latitude")),
            "longitude": safe_float(s.get("longitude")),
        })

    print(f"Generated {len(documents)} BPS school descriptions")

    # Save documents and metadata
    docs_path = VECTOR_DIR / "documents.json"
    meta_path = VECTOR_DIR / "metadata.json"

    with open(docs_path, "w") as f:
        json.dump(documents, f, indent=2)
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Saved documents to: {docs_path}")
    print(f"Saved metadata to: {meta_path}")

    # Build FAISS index
    try:
        import numpy as np
        import faiss
        from sentence_transformers import SentenceTransformer

        print(f"\nLoading embedding model: {EMBEDDING_MODEL}")
        model = SentenceTransformer(EMBEDDING_MODEL)

        print("Encoding school descriptions...")
        embeddings = model.encode(documents, show_progress_bar=True, normalize_embeddings=True)
        embeddings = np.array(embeddings).astype("float32")

        print(f"Embedding shape: {embeddings.shape}")

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        index_path = VECTOR_DIR / "school_index.faiss"
        faiss.write_index(index, str(index_path))

        print(f"FAISS index saved to: {index_path}")
        print(f"Index contains {index.ntotal} vectors of dimension {dim}")

    except ImportError as e:
        print(f"\nCould not build FAISS index: {e}")
        print("  Documents and metadata saved. Install deps to build index:")
        print("  pip install sentence-transformers faiss-cpu")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build school database and vector store")
    parser.add_argument("--db-only", action="store_true", help="Build only SQLite database")
    parser.add_argument("--vector-only", action="store_true", help="Build only vector store")
    args = parser.parse_args()

    if args.db_only:
        build_sqlite()
    elif args.vector_only:
        build_vector_store()
    else:
        build_sqlite()
        build_vector_store()

    # Quick test
    print("\n" + "=" * 60)
    print("Quick Test")
    print("=" * 60)

    from database import BPSDatabase
    db = BPSDatabase()

    print("\n--- BPS schools serving grade 9 ---")
    results = db.hard_filter(grade=9)
    for r in results[:5]:
        print(f"  {r['school']} (grades {r['grade_min']} to {r['grade_max']})")
    print(f"  ... {len(results)} total")

    print("\n--- Non-BPS schools serving 3-year-olds (36 months) ---")
    results = db.find_schools_by_age(36)
    print(f"  {len(results)} schools found")
    for r in results[:3]:
        print(f"  {r['school']} ({r['provider_type']})")

    print("\n--- Family Child Care + accepts CCFA ---")
    results = db.hard_filter(provider_type="Family Child Care", accepts_ccfa=1)
    print(f"  {len(results)} schools found")

    print("\n--- Schools within 1 mile of Copley Square ---")
    results = db.find_schools_near(42.3496, -71.0778, 1.0)
    for r in results[:5]:
        print(f"  {r['school']} ({r['provider_type']}) - {r['distance_miles']} mi")

    print("\n--- Semantic search: 'arts and music programs' ---")
    results = db.semantic_search("arts and music programs", top_k=5)
    for r in results:
        print(f"  {r['school']} (score: {r['score']:.3f})")

    db.close()
    print("\nDone!")
