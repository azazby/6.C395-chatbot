#!/usr/bin/env python3
"""
BPS School Finder - Database & Vector Store Builder
====================================================
Builds:
1. SQLite database (bps_schools.db) for hard filtering (location, grades, school type)
2. FAISS vector index + metadata JSON for soft filtering via RAG

Usage:
    python build_database.py                    # Build both DB and vector store
    python build_database.py --db-only          # Build only SQLite
    python build_database.py --vector-only      # Build only vector store

Requirements:
    pip install faiss-cpu sentence-transformers pandas numpy
"""

import csv
import sqlite3
import json
import math
import os
import sys
import re
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RAW_CSV = Path(__file__).parent / "raw_data" / "public_schools.csv"
ENRICHED_JSON = Path(__file__).parent / "raw_data" / "school_descriptions.json"
DB_PATH = Path(__file__).parent / "bps_schools.db"
VECTOR_DIR = Path(__file__).parent / "vector_store"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 80MB, fast, good quality

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_grade_range(sch_type: str, sch_name: str) -> tuple:
    """
    Convert SCH_TYPE like 'ES', 'MS', 'HS', 'K-8', 'K-12', '6/7-12', 'ELC', 'Special'
    into (grade_low, grade_high) integers.
    
    Grade encoding:
        K0 = -2, K1 = -1, K2 = 0, 1st = 1, ... 12th = 12
        ELC (Early Learning Center) = K0-K2 => (-2, 0)
    """
    sch_type = sch_type.strip()
    name_lower = sch_name.lower()
    
    # Check for explicit grade ranges in the school name
    # e.g., "Henderson Lower (K-3)", "Roosevelt Upper (2-7)", "Curley Lower (K1-5)"
    range_match = re.search(r'\(([Kk]\d?)-(\d+)\)', sch_name)
    if range_match:
        low_str, high_str = range_match.groups()
        low = _parse_grade(low_str)
        high = int(high_str)
        return (low, high)
    
    range_match2 = re.search(r'\((\d+)-(\d+)\)', sch_name)
    if range_match2:
        return (int(range_match2.group(1)), int(range_match2.group(2)))

    type_map = {
        'ELC': (-2, 0),    # Early Learning Center: K0-K2
        'ES': (-1, 5),     # Elementary: K1-5
        'MS': (6, 8),      # Middle: 6-8
        'HS': (9, 12),     # High: 9-12
        'K-8': (-1, 8),    # K1-8
        'K-12': (-1, 12),  # K1-12
        '6/7-12': (6, 12), # 6 or 7 through 12
        'Special': (None, None),
    }
    
    return type_map.get(sch_type, (None, None))


def _parse_grade(g: str) -> int:
    g = g.strip().upper()
    if g in ('K0', 'K'):
        return -2
    if g == 'K1':
        return -1
    if g == 'K2':
        return 0
    try:
        return int(g)
    except ValueError:
        return None


def infer_neighborhood(city: str, zipcode: str) -> str:
    """Map city/zip to BPS neighborhood zones."""
    zip_to_neighborhood = {
        '02128': 'East Boston',
        '02129': 'Charlestown',
        '02113': 'North End',
        '02109': 'North End',
        '02114': 'Beacon Hill',
        '02116': 'Back Bay/South End',
        '02118': 'South End',
        '02111': 'Chinatown/Downtown',
        '02115': 'Fenway/Longwood',
        '02215': 'Fenway/Longwood',
        '02119': 'Roxbury',
        '02120': 'Mission Hill',
        '02121': 'Dorchester (North)',
        '02122': 'Dorchester (South)',
        '02124': 'Dorchester (South)',
        '02125': 'Dorchester (North)',
        '02126': 'Mattapan',
        '02127': 'South Boston',
        '02130': 'Jamaica Plain',
        '02131': 'Roslindale',
        '02132': 'West Roxbury',
        '02134': 'Allston',
        '02135': 'Brighton',
        '02136': 'Hyde Park',
    }
    return zip_to_neighborhood.get(zipcode, city)


def haversine_miles(lat1, lon1, lat2, lon2):
    """Calculate distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# School Descriptions (enriched data for RAG)
# ---------------------------------------------------------------------------

def get_enriched_descriptions() -> dict:
    """
    Load enriched school descriptions from JSON if available.
    These are scraped/curated descriptions with program details, 
    language offerings, special ed info, activities, etc.
    
    Falls back to auto-generated descriptions from structured data.
    """
    if ENRICHED_JSON.exists():
        with open(ENRICHED_JSON) as f:
            return json.load(f)
    return {}


def generate_description(row: dict, enriched: dict) -> str:
    """
    Generate a rich text description for a school, suitable for embedding.
    Combines structured data with any enriched descriptions.
    """
    sch_id = str(row['SCH_ID'])
    name = row['SCH_NAME']
    label = row['SCH_LABEL']
    sch_type = row['SCH_TYPE']
    address = f"{row['ADDRESS']}, {row['CITY']}, MA {row['ZIPCODE']}"
    neighborhood = infer_neighborhood(row['CITY'], row['ZIPCODE'])
    
    grade_low, grade_high = parse_grade_range(sch_type, name)
    
    # Grade range as human-readable
    def grade_str(g):
        if g is None: return "N/A"
        if g == -2: return "K0"
        if g == -1: return "K1"
        if g == 0: return "K2"
        return str(g)
    
    grade_range = f"{grade_str(grade_low)} to {grade_str(grade_high)}"
    
    type_descriptions = {
        'ES': 'Elementary School',
        'MS': 'Middle School',
        'HS': 'High School',
        'K-8': 'K-8 School',
        'K-12': 'K-12 School',
        '6/7-12': 'Secondary School (grades 6/7-12)',
        'ELC': 'Early Learning Center',
        'Special': 'Special/Alternative Program',
    }
    type_desc = type_descriptions.get(sch_type, sch_type)
    
    parts = [
        f"{name} ({label}) is a {type_desc} located at {address} in the {neighborhood} neighborhood of Boston.",
        f"It serves grades {grade_range}.",
    ]
    
    if row.get('SHARED') and row['SHARED'].strip():
        parts.append("This school shares its building with another program.")
    
    # Add enriched description if available
    if sch_id in enriched:
        info = enriched[sch_id]
        if 'description' in info:
            parts.append(info['description'])
        if 'programs' in info:
            parts.append(f"Programs offered: {', '.join(info['programs'])}.")
        if 'languages' in info:
            parts.append(f"Language programs: {', '.join(info['languages'])}.")
        if 'special_ed' in info:
            parts.append(f"Special education services: {info['special_ed']}.")
        if 'activities' in info:
            parts.append(f"Student activities include: {', '.join(info['activities'])}.")
        if 'transportation' in info:
            parts.append(f"Transportation: {info['transportation']}.")
        if 'before_after_school' in info:
            parts.append(f"Before/after school programs: {info['before_after_school']}.")
        if 'special_admissions' in info:
            parts.append(f"Admissions: {info['special_admissions']}.")
    
    return " ".join(parts)


# ---------------------------------------------------------------------------
# 1. Build SQLite Database
# ---------------------------------------------------------------------------

def build_sqlite():
    """Build the SQLite database from the CSV data."""
    print("=" * 60)
    print("Building SQLite Database")
    print("=" * 60)
    
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    # Main schools table
    cur.execute("""
        CREATE TABLE schools (
            sch_id          INTEGER PRIMARY KEY,
            sch_name        TEXT NOT NULL,
            sch_label       TEXT,
            sch_type        TEXT,          -- ES, MS, HS, K-8, K-12, 6/7-12, ELC, Special
            type_description TEXT,         -- Human readable type
            address         TEXT,
            city            TEXT,
            zipcode         TEXT,
            neighborhood    TEXT,
            latitude        REAL,
            longitude       REAL,
            grade_low       INTEGER,       -- Lowest grade served (-2=K0, -1=K1, 0=K2, 1-12)
            grade_high      INTEGER,       -- Highest grade served
            is_shared_bldg  INTEGER DEFAULT 0,  -- 1 if building is shared
            bldg_id         INTEGER,
            bldg_name       TEXT,
            complex_name    TEXT
        )
    """)
    
    # Enrichment tables (for future scraping)
    cur.execute("""
        CREATE TABLE school_programs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sch_id      INTEGER REFERENCES schools(sch_id),
            program_type TEXT,   -- 'language', 'special_ed', 'activity', 'academic', 'arts', 'sports'
            program_name TEXT,
            description  TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE school_details (
            sch_id           INTEGER PRIMARY KEY REFERENCES schools(sch_id),
            phone            TEXT,
            email            TEXT,
            website          TEXT,
            principal        TEXT,
            hours_start      TEXT,
            hours_end        TEXT,
            transportation   TEXT,    -- 'yellow_bus', 'mbta_pass', 'walk', 'none'
            before_school    INTEGER DEFAULT 0,
            after_school     INTEGER DEFAULT 0,
            uniform_required INTEGER DEFAULT 0,
            special_admissions TEXT,  -- NULL for regular, description for exam/application schools
            description      TEXT    -- Full text description for the school
        )
    """)
    
    # Read CSV and insert
    with open(RAW_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        seen_ids = set()
        rows_inserted = 0
        
        for row in reader:
            sch_id = int(float(row['SCH_ID']))
            
            # Skip duplicates (some schools have multiple building entries)
            if sch_id in seen_ids:
                continue
            seen_ids.add(sch_id)
            
            grade_low, grade_high = parse_grade_range(row['SCH_TYPE'], row['SCH_NAME'])
            neighborhood = infer_neighborhood(row['CITY'], row['ZIPCODE'])
            
            type_descriptions = {
                'ES': 'Elementary School',
                'MS': 'Middle School', 
                'HS': 'High School',
                'K-8': 'K-8 School',
                'K-12': 'K-12 School',
                '6/7-12': 'Secondary School',
                'ELC': 'Early Learning Center',
                'Special': 'Special/Alternative Program',
            }
            
            try:
                lat = float(row['POINT_Y'])
                lon = float(row['POINT_X'])
            except (ValueError, TypeError):
                lat, lon = None, None
            
            cur.execute("""
                INSERT INTO schools (
                    sch_id, sch_name, sch_label, sch_type, type_description,
                    address, city, zipcode, neighborhood,
                    latitude, longitude, grade_low, grade_high,
                    is_shared_bldg, bldg_id, bldg_name, complex_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sch_id,
                row['SCH_NAME'],
                row['SCH_LABEL'],
                row['SCH_TYPE'].strip(),
                type_descriptions.get(row['SCH_TYPE'].strip(), row['SCH_TYPE'].strip()),
                row['ADDRESS'],
                row['CITY'],
                row['ZIPCODE'],
                neighborhood,
                lat, lon,
                grade_low, grade_high,
                1 if row.get('SHARED', '').strip() else 0,
                int(float(row['BLDG_ID'])) if row['BLDG_ID'] else None,
                row['BLDG_NAME'],
                row.get('COMPLEX', '').strip() or None,
            ))
            rows_inserted += 1
    
    # Create useful indexes
    cur.execute("CREATE INDEX idx_schools_type ON schools(sch_type)")
    cur.execute("CREATE INDEX idx_schools_neighborhood ON schools(neighborhood)")
    cur.execute("CREATE INDEX idx_schools_zipcode ON schools(zipcode)")
    cur.execute("CREATE INDEX idx_schools_grades ON schools(grade_low, grade_high)")
    cur.execute("CREATE INDEX idx_schools_latlon ON schools(latitude, longitude)")
    
    conn.commit()
    
    # Print summary
    cur.execute("SELECT COUNT(*) FROM schools")
    total = cur.fetchone()[0]
    
    cur.execute("SELECT sch_type, COUNT(*) FROM schools GROUP BY sch_type ORDER BY COUNT(*) DESC")
    type_counts = cur.fetchall()
    
    cur.execute("SELECT neighborhood, COUNT(*) FROM schools GROUP BY neighborhood ORDER BY COUNT(*) DESC")
    hood_counts = cur.fetchall()
    
    print(f"\nInserted {total} unique schools")
    print(f"\nBy type:")
    for t, c in type_counts:
        print(f"  {t:12s}: {c}")
    print(f"\nBy neighborhood:")
    for n, c in hood_counts:
        print(f"  {n:25s}: {c}")
    
    conn.close()
    print(f"\nDatabase saved to: {DB_PATH}")
    return total


# ---------------------------------------------------------------------------
# 2. Build Vector Store
# ---------------------------------------------------------------------------

def build_vector_store():
    """
    Build FAISS vector index from school descriptions.
    
    Each school gets a text description that combines structured data
    with any enriched descriptions. These are embedded using 
    sentence-transformers and stored in a FAISS index.
    """
    print("\n" + "=" * 60)
    print("Building Vector Store")
    print("=" * 60)
    
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load enriched descriptions
    enriched = get_enriched_descriptions()
    
    # Generate descriptions for all schools
    documents = []
    metadata = []
    
    with open(RAW_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        seen_ids = set()
        
        for row in reader:
            sch_id = int(float(row['SCH_ID']))
            if sch_id in seen_ids:
                continue
            seen_ids.add(sch_id)
            
            desc = generate_description(row, enriched)
            documents.append(desc)
            
            grade_low, grade_high = parse_grade_range(row['SCH_TYPE'], row['SCH_NAME'])
            
            metadata.append({
                'sch_id': sch_id,
                'sch_name': row['SCH_NAME'],
                'sch_type': row['SCH_TYPE'].strip(),
                'neighborhood': infer_neighborhood(row['CITY'], row['ZIPCODE']),
                'grade_low': grade_low,
                'grade_high': grade_high,
                'latitude': float(row['POINT_Y']) if row['POINT_Y'] else None,
                'longitude': float(row['POINT_X']) if row['POINT_X'] else None,
            })
    
    print(f"Generated {len(documents)} school descriptions")
    
    # Save documents and metadata (always useful even without embeddings)
    docs_path = VECTOR_DIR / "documents.json"
    meta_path = VECTOR_DIR / "metadata.json"
    
    with open(docs_path, 'w') as f:
        json.dump(documents, f, indent=2)
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Saved documents to: {docs_path}")
    print(f"Saved metadata to: {meta_path}")
    
    # Try to build FAISS index with sentence-transformers
    try:
        import numpy as np
        import faiss
        from sentence_transformers import SentenceTransformer
        
        print(f"\nLoading embedding model: {EMBEDDING_MODEL}")
        model = SentenceTransformer(EMBEDDING_MODEL)
        
        print("Encoding school descriptions...")
        embeddings = model.encode(documents, show_progress_bar=True, normalize_embeddings=True)
        embeddings = np.array(embeddings).astype('float32')
        
        print(f"Embedding shape: {embeddings.shape}")
        
        # Build FAISS index (Inner Product since we normalized = cosine similarity)
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
        
        index_path = VECTOR_DIR / "school_index.faiss"
        faiss.write_index(index, str(index_path))
        
        print(f"FAISS index saved to: {index_path}")
        print(f"Index contains {index.ntotal} vectors of dimension {dim}")
        
    except ImportError as e:
        print(f"\n⚠ Could not build FAISS index: {e}")
        print("  Documents and metadata saved — run this script with")
        print("  sentence-transformers installed to build the full index.")
        print("  pip install sentence-transformers faiss-cpu")


# ---------------------------------------------------------------------------
# 3. Query Utilities (for the chatbot to import)
# ---------------------------------------------------------------------------

class BPSDatabase:
    """Query interface for the chatbot to use."""
    
    def __init__(self, db_path=None, vector_dir=None):
        self.db_path = db_path or DB_PATH
        self.vector_dir = vector_dir or VECTOR_DIR
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        
        # Load vector store if available
        self.index = None
        self.documents = None
        self.metadata = None
        self.model = None
        self._load_vector_store()
    
    def _load_vector_store(self):
        """Load FAISS index and metadata."""
        try:
            meta_path = Path(self.vector_dir) / "metadata.json"
            docs_path = Path(self.vector_dir) / "documents.json"
            index_path = Path(self.vector_dir) / "school_index.faiss"
            
            if meta_path.exists():
                with open(meta_path) as f:
                    self.metadata = json.load(f)
                with open(docs_path) as f:
                    self.documents = json.load(f)
            
            if index_path.exists():
                import faiss
                self.index = faiss.read_index(str(index_path))
                
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(EMBEDDING_MODEL)
                
                print(f"Vector store loaded: {self.index.ntotal} schools indexed")
        except Exception as e:
            print(f"Vector store not fully loaded: {e}")
    
    # --- Hard Filtering (SQL) ---
    
    def find_schools_by_grade(self, grade: int) -> list:
        """Find all schools that serve a specific grade level.
        Grade encoding: K0=-2, K1=-1, K2=0, 1-12 as integers."""
        cur = self.conn.execute(
            "SELECT * FROM schools WHERE grade_low <= ? AND grade_high >= ? ORDER BY sch_name",
            (grade, grade)
        )
        return [dict(r) for r in cur.fetchall()]
    
    def find_schools_near(self, lat: float, lon: float, radius_miles: float = 1.0) -> list:
        """Find schools within radius_miles of a given lat/lon.
        Uses bounding box first then precise haversine filtering."""
        # Rough bounding box (1 degree lat ≈ 69 miles, 1 degree lon ≈ 53 miles at Boston's lat)
        lat_delta = radius_miles / 69.0
        lon_delta = radius_miles / 53.0
        
        cur = self.conn.execute("""
            SELECT * FROM schools 
            WHERE latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
        """, (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta))
        
        results = []
        for row in cur.fetchall():
            d = dict(row)
            dist = haversine_miles(lat, lon, d['latitude'], d['longitude'])
            if dist <= radius_miles:
                d['distance_miles'] = round(dist, 2)
                results.append(d)
        
        results.sort(key=lambda x: x['distance_miles'])
        return results
    
    def find_schools_by_type(self, sch_type: str) -> list:
        """Find schools by type (ES, MS, HS, K-8, etc.)."""
        cur = self.conn.execute(
            "SELECT * FROM schools WHERE sch_type = ? ORDER BY sch_name",
            (sch_type,)
        )
        return [dict(r) for r in cur.fetchall()]
    
    def find_schools_by_neighborhood(self, neighborhood: str) -> list:
        """Find schools in a given neighborhood."""
        cur = self.conn.execute(
            "SELECT * FROM schools WHERE neighborhood LIKE ? ORDER BY sch_name",
            (f"%{neighborhood}%",)
        )
        return [dict(r) for r in cur.fetchall()]
    
    def hard_filter(self, grade: int = None, neighborhood: str = None,
                    sch_type: str = None, lat: float = None, lon: float = None,
                    radius_miles: float = 1.0) -> list:
        """
        Combined hard filter. All specified conditions must match (AND logic).
        Returns list of school dicts.
        """
        query = "SELECT * FROM schools WHERE 1=1"
        params = []
        
        if grade is not None:
            query += " AND grade_low <= ? AND grade_high >= ?"
            params.extend([grade, grade])
        
        if neighborhood:
            query += " AND neighborhood LIKE ?"
            params.append(f"%{neighborhood}%")
        
        if sch_type:
            query += " AND sch_type = ?"
            params.append(sch_type)
        
        cur = self.conn.execute(query + " ORDER BY sch_name", params)
        results = [dict(r) for r in cur.fetchall()]
        
        # Post-filter by distance if location provided
        if lat is not None and lon is not None:
            filtered = []
            for r in results:
                if r['latitude'] and r['longitude']:
                    dist = haversine_miles(lat, lon, r['latitude'], r['longitude'])
                    if dist <= radius_miles:
                        r['distance_miles'] = round(dist, 2)
                        filtered.append(r)
            results = sorted(filtered, key=lambda x: x['distance_miles'])
        
        return results
    
    # --- Soft Filtering (Vector Search / RAG) ---
    
    def semantic_search(self, query: str, top_k: int = 10, 
                        pre_filter_ids: list = None) -> list:
        """
        Semantic search over school descriptions.
        
        Args:
            query: Natural language query (e.g., "school with strong arts program")
            top_k: Number of results to return
            pre_filter_ids: If provided, only search within these school IDs
                           (allows combining hard filter -> soft filter)
        
        Returns:
            List of dicts with 'sch_id', 'sch_name', 'score', 'description'
        """
        if self.index is None or self.model is None:
            return self._keyword_search(query, top_k, pre_filter_ids)
        
        import numpy as np
        
        # Encode query
        query_vec = self.model.encode([query], normalize_embeddings=True)
        query_vec = np.array(query_vec).astype('float32')
        
        # Search (get more results if we need to post-filter)
        search_k = min(top_k * 5, self.index.ntotal) if pre_filter_ids else top_k
        scores, indices = self.index.search(query_vec, search_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            meta = self.metadata[idx]
            
            if pre_filter_ids and meta['sch_id'] not in pre_filter_ids:
                continue
            
            results.append({
                'sch_id': meta['sch_id'],
                'sch_name': meta['sch_name'],
                'score': float(score),
                'description': self.documents[idx],
                'metadata': meta,
            })
            
            if len(results) >= top_k:
                break
        
        return results
    
    def _keyword_search(self, query: str, top_k: int = 10,
                        pre_filter_ids: list = None) -> list:
        """Fallback keyword search when FAISS/embeddings not available."""
        if not self.documents:
            return []
        
        query_words = set(query.lower().split())
        scored = []
        
        for i, (doc, meta) in enumerate(zip(self.documents, self.metadata)):
            if pre_filter_ids and meta['sch_id'] not in pre_filter_ids:
                continue
            
            doc_lower = doc.lower()
            score = sum(1 for w in query_words if w in doc_lower)
            if score > 0:
                scored.append({
                    'sch_id': meta['sch_id'],
                    'sch_name': meta['sch_name'],
                    'score': score / len(query_words),
                    'description': doc,
                    'metadata': meta,
                })
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:top_k]
    
    # --- Combined Hard + Soft Filter ---
    
    def search(self, query: str, grade: int = None, neighborhood: str = None,
               sch_type: str = None, lat: float = None, lon: float = None,
               radius_miles: float = 1.0, top_k: int = 10) -> list:
        """
        Full search pipeline:
        1. Apply hard filters (grade, neighborhood, type, location)
        2. Within hard-filtered results, rank by semantic similarity to query
        
        This is the main method the chatbot should call.
        """
        # Step 1: Hard filter
        hard_results = self.hard_filter(
            grade=grade, neighborhood=neighborhood,
            sch_type=sch_type, lat=lat, lon=lon, radius_miles=radius_miles
        )
        
        if not query or not query.strip():
            return hard_results[:top_k]
        
        # Step 2: Soft filter within hard results
        eligible_ids = set(r['sch_id'] for r in hard_results)
        
        if not eligible_ids:
            # No hard filter results — do pure semantic search
            return self.semantic_search(query, top_k)
        
        soft_results = self.semantic_search(query, top_k, eligible_ids)
        
        # Merge distance info from hard results into soft results
        dist_map = {r['sch_id']: r.get('distance_miles') for r in hard_results}
        for r in soft_results:
            if dist_map.get(r['sch_id']) is not None:
                r['distance_miles'] = dist_map[r['sch_id']]
        
        return soft_results
    
    def get_school_detail(self, sch_id: int) -> dict:
        """Get full details for a specific school."""
        cur = self.conn.execute("SELECT * FROM schools WHERE sch_id = ?", (sch_id,))
        row = cur.fetchone()
        if row:
            result = dict(row)
            # Add description from vector store
            if self.metadata:
                for i, m in enumerate(self.metadata):
                    if m['sch_id'] == sch_id:
                        result['description'] = self.documents[i]
                        break
            return result
        return None
    
    def get_all_neighborhoods(self) -> list:
        """Get list of all neighborhoods."""
        cur = self.conn.execute(
            "SELECT DISTINCT neighborhood FROM schools ORDER BY neighborhood"
        )
        return [r[0] for r in cur.fetchall()]
    
    def get_all_school_types(self) -> list:
        """Get list of all school types."""
        cur = self.conn.execute(
            "SELECT DISTINCT sch_type, type_description FROM schools ORDER BY sch_type"
        )
        return [(r[0], r[1]) for r in cur.fetchall()]
    
    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build BPS School Finder database and vector store")
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
    
    db = BPSDatabase()
    
    print("\n--- Schools serving grade 9 in Roxbury ---")
    results = db.hard_filter(grade=9, neighborhood="Roxbury")
    for r in results[:5]:
        print(f"  {r['sch_name']} ({r['sch_type']}) - {r['address']}")
    
    print("\n--- Elementary schools within 1 mile of Copley Square ---")
    # Copley Square: 42.3496, -71.0778
    results = db.hard_filter(grade=1, lat=42.3496, lon=-71.0778, radius_miles=1.0)
    for r in results[:5]:
        print(f"  {r['sch_name']} ({r['sch_type']}) - {r.get('distance_miles', '?')} mi")
    
    print("\n--- Semantic search: 'arts and music programs' ---")
    results = db.semantic_search("arts and music programs", top_k=5)
    for r in results[:5]:
        print(f"  {r['sch_name']} (score: {r['score']:.3f})")
    
    db.close()
    print("\nDone!")
