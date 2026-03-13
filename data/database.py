"""
BPS School Finder - Database Query Interface
==============================================
Runtime query class for the chatbot. Import this module:

    from database import BPSDatabase
    db = BPSDatabase()
"""

import sqlite3
import json
import math
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "bps_schools.db"
VECTOR_DIR = Path(__file__).parent / "vector_store"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# Query Interface
# ---------------------------------------------------------------------------

class BPSDatabase:
    """Query interface for the chatbot."""

    def __init__(self, db_path=None, vector_dir=None):
        self.db_path = db_path or DB_PATH
        self.vector_dir = vector_dir or VECTOR_DIR
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

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
        """Find BPS schools that serve a specific grade level.
        Grade encoding: K0=-2, K1=-1, K2=0, 1-12 as integers."""
        cur = self.conn.execute(
            "SELECT * FROM schools WHERE grade_min <= ? AND grade_max >= ? ORDER BY school",
            (grade, grade),
        )
        return [dict(r) for r in cur.fetchall()]

    def find_schools_by_age(self, age_months: int) -> list:
        """Find non-BPS schools that serve a specific age in months."""
        cur = self.conn.execute(
            "SELECT * FROM schools WHERE age_min_months <= ? AND age_max_months >= ? ORDER BY school",
            (age_months, age_months),
        )
        return [dict(r) for r in cur.fetchall()]

    def find_schools_near(self, lat: float, lon: float, radius_miles: float = 1.0) -> list:
        """Find schools within radius_miles of a given lat/lon."""
        lat_delta = radius_miles / 69.0
        lon_delta = radius_miles / 53.0

        cur = self.conn.execute(
            """SELECT * FROM schools
               WHERE latitude BETWEEN ? AND ?
                 AND longitude BETWEEN ? AND ?""",
            (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta),
        )

        results = []
        for row in cur.fetchall():
            d = dict(row)
            if d["latitude"] and d["longitude"]:
                dist = haversine_miles(lat, lon, d["latitude"], d["longitude"])
                if dist <= radius_miles:
                    d["distance_miles"] = round(dist, 2)
                    results.append(d)

        results.sort(key=lambda x: x["distance_miles"])
        return results

    def find_schools_by_provider_type(self, provider_type: str) -> list:
        """Find schools by provider type (exact match)."""
        cur = self.conn.execute(
            "SELECT * FROM schools WHERE provider_type = ? ORDER BY school",
            (provider_type,),
        )
        return [dict(r) for r in cur.fetchall()]

    def find_schools_by_filters(self, **kwargs) -> list:
        """
        Combined AND filter for boolean/integer fields.
        Supported kwargs: UPK, ADA, accepts_ccfa, headstart, has_language_program,
        has_advanced_placement, has_international_baccalaureate, uniform,
        special_admission, surround_care, build_care, tuition.
        """
        allowed = {
            "UPK", "ADA", "accepts_ccfa", "headstart", "has_language_program",
            "has_advanced_placement", "has_international_baccalaureate", "uniform",
            "special_admission", "surround_care", "build_care", "tuition",
        }

        query = "SELECT * FROM schools WHERE 1=1"
        params = []

        for key, val in kwargs.items():
            if key in allowed and val is not None:
                query += f" AND {key} = ?"
                params.append(val)

        cur = self.conn.execute(query + " ORDER BY school", params)
        return [dict(r) for r in cur.fetchall()]

    def hard_filter(self, grade: int = None, age_months: int = None,
                    provider_type: str = None, lat: float = None, lon: float = None,
                    radius_miles: float = 1.0, **boolean_filters) -> list:
        """
        Combined hard filter. All specified conditions must match (AND logic).
        """
        query = "SELECT * FROM schools WHERE 1=1"
        params = []

        if grade is not None:
            query += " AND grade_min <= ? AND grade_max >= ?"
            params.extend([grade, grade])

        if age_months is not None:
            query += " AND age_min_months <= ? AND age_max_months >= ?"
            params.extend([age_months, age_months])

        if provider_type:
            query += " AND provider_type = ?"
            params.append(provider_type)

        allowed_bools = {
            "UPK", "ADA", "accepts_ccfa", "headstart", "has_language_program",
            "has_advanced_placement", "has_international_baccalaureate", "uniform",
            "special_admission", "surround_care", "build_care", "tuition",
        }
        for key, val in boolean_filters.items():
            if key in allowed_bools and val is not None:
                query += f" AND {key} = ?"
                params.append(val)

        cur = self.conn.execute(query + " ORDER BY school", params)
        results = [dict(r) for r in cur.fetchall()]

        # Post-filter by distance if location provided
        if lat is not None and lon is not None:
            filtered = []
            for r in results:
                if r["latitude"] and r["longitude"]:
                    dist = haversine_miles(lat, lon, r["latitude"], r["longitude"])
                    if dist <= radius_miles:
                        r["distance_miles"] = round(dist, 2)
                        filtered.append(r)
            results = sorted(filtered, key=lambda x: x["distance_miles"])

        return results

    # --- Soft Filtering (Vector Search / RAG) ---

    def semantic_search(self, query: str, top_k: int = 10,
                        pre_filter_ids: set = None) -> list:
        """
        Semantic search over BPS school descriptions.

        Args:
            query: Natural language query
            top_k: Number of results to return
            pre_filter_ids: If provided, only search within these school IDs
        """
        if self.index is None or self.model is None:
            return self._keyword_search(query, top_k, pre_filter_ids)

        import numpy as np

        query_vec = self.model.encode([query], normalize_embeddings=True)
        query_vec = np.array(query_vec).astype("float32")

        search_k = min(top_k * 5, self.index.ntotal) if pre_filter_ids else top_k
        scores, indices = self.index.search(query_vec, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            meta = self.metadata[idx]

            if pre_filter_ids and meta["id"] not in pre_filter_ids:
                continue

            results.append({
                "id": meta["id"],
                "school": meta["school"],
                "score": float(score),
                "description": self.documents[idx],
                "metadata": meta,
            })

            if len(results) >= top_k:
                break

        return results

    def _keyword_search(self, query: str, top_k: int = 10,
                        pre_filter_ids: set = None) -> list:
        """Fallback keyword search when FAISS/embeddings not available."""
        if not self.documents:
            return []

        query_words = set(query.lower().split())
        scored = []

        for i, (doc, meta) in enumerate(zip(self.documents, self.metadata)):
            if pre_filter_ids and meta["id"] not in pre_filter_ids:
                continue

            doc_lower = doc.lower()
            score = sum(1 for w in query_words if w in doc_lower)
            if score > 0:
                scored.append({
                    "id": meta["id"],
                    "school": meta["school"],
                    "score": score / len(query_words),
                    "description": doc,
                    "metadata": meta,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # --- Combined Hard + Soft Filter ---

    def search(self, query: str = None, grade: int = None, provider_type: str = None,
               lat: float = None, lon: float = None, radius_miles: float = 1.0,
               top_k: int = 10, **filters) -> list:
        """
        Full search pipeline:
        1. Apply hard filters (grade, provider_type, location, booleans)
        2. Within hard-filtered results, rank by semantic similarity to query
        """
        hard_results = self.hard_filter(
            grade=grade, provider_type=provider_type,
            lat=lat, lon=lon, radius_miles=radius_miles, **filters,
        )

        if not query or not query.strip():
            return hard_results[:top_k]

        eligible_ids = set(r["id"] for r in hard_results)

        if not eligible_ids:
            return self.semantic_search(query, top_k)

        soft_results = self.semantic_search(query, top_k, eligible_ids)

        dist_map = {r["id"]: r.get("distance_miles") for r in hard_results}
        for r in soft_results:
            if dist_map.get(r["id"]) is not None:
                r["distance_miles"] = dist_map[r["id"]]

        return soft_results

    # --- Filter Based on Preferences ---

    def filter_based_on_preferences(self, school_ids: list, **preferences) -> dict:
        """
        Filter eligible school IDs by preferences. Returns results split by
        BPS vs non-BPS, with BPS schools semantically ranked when a query is provided.

        Args:
            school_ids: List of school IDs (from find_eligible_schools). Required, cannot be empty.
            **preferences: Optional filters (query, top_k, ADA, UPK, has_language_program, etc.)

        Returns:
            Dict with bps_schools, non_bps_schools, bps_count, non_bps_count, notes.
        """
        if not school_ids:
            return {
                "error": "school_ids is required and cannot be empty. Call find_eligible_schools first to get eligible school IDs.",
                "bps_schools": [],
                "non_bps_schools": [],
                "notes": [],
            }

        query = preferences.pop("query", None)
        top_k = preferences.pop("top_k", 10)
        lat = preferences.pop("lat", None)
        lon = preferences.pop("lon", None)
        radius_miles = preferences.pop("radius_miles", 1.0)
        provider_type = preferences.pop("provider_type", None)

        # Build SQL with ID constraint + optional filters
        placeholders = ",".join("?" for _ in school_ids)
        sql = f"SELECT * FROM schools WHERE id IN ({placeholders})"
        params = list(school_ids)

        if provider_type:
            sql += " AND provider_type = ?"
            params.append(provider_type)

        allowed_bools = {
            "UPK", "ADA", "accepts_ccfa", "headstart", "has_language_program",
            "has_advanced_placement", "has_international_baccalaureate", "uniform",
            "special_admission", "surround_care", "build_care", "tuition",
        }
        for key, val in preferences.items():
            if key in allowed_bools and val is not None:
                sql += f" AND {key} = ?"
                params.append(val)

        cur = self.conn.execute(sql + " ORDER BY school", params)
        rows = [dict(r) for r in cur.fetchall()]

        # Post-filter by distance
        if lat is not None and lon is not None:
            filtered = []
            for r in rows:
                if r["latitude"] and r["longitude"]:
                    dist = haversine_miles(lat, lon, r["latitude"], r["longitude"])
                    if dist <= radius_miles:
                        r["distance_miles"] = round(dist, 2)
                        filtered.append(r)
            rows = sorted(filtered, key=lambda x: x["distance_miles"])

        # Split BPS vs non-BPS
        bps_rows = [r for r in rows if r["provider_type"] == "Boston Public School"]
        non_bps_rows = [r for r in rows if r["provider_type"] != "Boston Public School"]

        bps_count = len(bps_rows)
        non_bps_count = len(non_bps_rows)
        notes = []

        # Semantic ranking for BPS if query provided
        if query and bps_rows:
            bps_ids = set(str(r["id"]) for r in bps_rows)
            ranked = self.semantic_search(query, top_k=len(bps_rows), pre_filter_ids=bps_ids)

            ranked_ids = [r["id"] for r in ranked]
            score_map = {r["id"]: r["score"] for r in ranked}

            # Build ranked BPS list: ranked first, then unranked
            bps_by_id = {str(r["id"]): r for r in bps_rows}
            ranked_bps = []
            for rid in ranked_ids:
                if str(rid) in bps_by_id:
                    row = bps_by_id.pop(str(rid))
                    row["score"] = score_map[rid]
                    ranked_bps.append(row)
            # Append any BPS schools not in FAISS results
            for row in sorted(bps_by_id.values(), key=lambda x: x["school"]):
                ranked_bps.append(row)

            bps_rows = ranked_bps

        if query and non_bps_count > 0:
            notes.append(
                f"Non-BPS schools cannot be ranked by their semantic preference "
                f"'{query}' because detailed program descriptions are not publicly "
                f"available for these providers, tell this to the user."
            )

        if bps_count == 0 and non_bps_count == 0:
            notes.append(
                "No schools matched the given filters. Tell the user to broaden "
                "their criteria or to reach out to their eligible schools for more information."
            )

        return {
            "bps_schools": bps_rows[:top_k],
            "non_bps_schools": non_bps_rows[:top_k],
            "bps_count": bps_count,
            "non_bps_count": non_bps_count,
            "notes": notes,
        }

    # --- Utility methods ---

    def get_school_detail(self, school_id: str) -> dict:
        """Get full school record + RAG description if available."""
        cur = self.conn.execute("SELECT * FROM schools WHERE id = ?", (school_id,))
        row = cur.fetchone()
        if row:
            result = dict(row)
            if self.metadata:
                for i, m in enumerate(self.metadata):
                    if m["id"] == school_id:
                        result["description"] = self.documents[i]
                        break
            return result
        return None

    def get_all_provider_types(self) -> list:
        """Get distinct provider types."""
        cur = self.conn.execute(
            "SELECT DISTINCT provider_type FROM schools ORDER BY provider_type"
        )
        return [r[0] for r in cur.fetchall()]

    def close(self):
        self.conn.close()
