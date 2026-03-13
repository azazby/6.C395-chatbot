"""
Data layer tests — runnable immediately without an LLM or HF_TOKEN.

These tests verify that BPSDatabase correctly filters, searches, and returns
results from the bps_schools.db + FAISS vector store.

Grade encoding: K0=-2, K1=-1, K2=0, 1-12 as integers.
Jamaica Plain (JP) approximate center: lat=42.3097, lon=-71.1065
"""

import pytest


# ── Grade / hard filter tests ─────────────────────────────────────────────────

class TestGradeFilters:

    def test_grade_3_returns_results(self, db):
        """hard_filter(grade=3) must return at least one school."""
        results = db.hard_filter(grade=3)
        assert len(results) > 0, "Expected schools serving grade 3"

    def test_grade_3_schools_span_grade(self, db):
        """Every result for grade=3 must have grade_min <= 3 <= grade_max."""
        results = db.hard_filter(grade=3)
        for school in results:
            assert school["grade_min"] <= 3 <= school["grade_max"], (
                f"{school['school']}: grade range "
                f"[{school['grade_min']}, {school['grade_max']}] "
                f"does not include 3"
            )

    def test_kindergarten_k2_returns_results(self, db):
        """K2 (grade=0) should return kindergarten schools."""
        results = db.hard_filter(grade=0)
        assert len(results) > 0, "Expected schools serving K2 (grade=0)"

    def test_high_school_grade_9_returns_results(self, db):
        """Grade 9 should return high schools."""
        results = db.hard_filter(grade=9)
        assert len(results) > 0, "Expected schools serving grade 9"

    def test_find_schools_by_grade_returns_list(self, db):
        """find_schools_by_grade(5) returns a non-empty list of dicts."""
        results = db.find_schools_by_grade(5)
        assert isinstance(results, list)
        assert len(results) > 0
        assert "school" in results[0]

    def test_grade_out_of_range_returns_empty(self, db):
        """Grade 99 should return no schools."""
        results = db.hard_filter(grade=99)
        assert results == [], f"Expected empty list for grade=99, got {results}"


# ── Semantic / vector search tests ───────────────────────────────────────────

class TestSemanticSearch:

    def test_spanish_language_returns_results(self, db):
        """semantic_search('Spanish dual language') should return results."""
        results = db.semantic_search("Spanish dual language", top_k=5)
        assert len(results) > 0, "Expected results for 'Spanish dual language'"

    def test_semantic_search_has_required_fields(self, db):
        """Each result should have id, school, score, and description fields."""
        results = db.semantic_search("arts program", top_k=3)
        assert len(results) > 0
        for r in results:
            assert "id" in r, f"Missing 'id' in result: {r}"
            assert "school" in r, f"Missing 'school' in result: {r}"
            assert "score" in r, f"Missing 'score' in result: {r}"
            assert "description" in r, f"Missing 'description' in result: {r}"

    def test_language_filter_finds_language_schools(self, db):
        """hard_filter with has_language_program=1 should return schools with language programs."""
        results = db.hard_filter(has_language_program=1)
        assert len(results) > 0, "Expected schools with language programs"
        for school in results:
            assert school["has_language_program"] == 1, (
                f"{school['school']} returned but has_language_program != 1"
            )

    def test_semantic_search_scores_are_sorted(self, db):
        """Semantic search results should be sorted by score descending."""
        results = db.semantic_search("math and science", top_k=5)
        if len(results) < 2:
            pytest.skip("Not enough results to check sort order")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), (
            "Semantic search results are not sorted by score descending"
        )

    def test_pre_filter_ids_respected(self, db):
        """semantic_search with pre_filter_ids should only return schools in the set."""
        all_results = db.hard_filter(grade=5)
        if len(all_results) < 2:
            pytest.skip("Need at least 2 grade-5 schools for this test")

        allowed_ids = {all_results[0]["id"]}
        results = db.semantic_search("school", top_k=5, pre_filter_ids=allowed_ids)
        for r in results:
            assert r["id"] in allowed_ids, (
                f"Result {r['school']} (id={r['id']}) not in pre_filter_ids"
            )


# ── Combined search tests ─────────────────────────────────────────────────────

class TestCombinedSearch:

    def test_combined_search_grade_and_query(self, db):
        """search(query, grade) should return grade-appropriate results."""
        results = db.search(query="arts program", grade=5, top_k=5)
        assert isinstance(results, list)
        assert len(results) > 0
        for school in results:
            if "grade_min" in school and "grade_max" in school:
                assert school["grade_min"] <= 5 <= school["grade_max"], (
                    f"{school['school']} does not serve grade 5"
                )

    def test_combined_search_with_language_filter(self, db):
        """search with has_language_program=1 should only return language schools."""
        results = db.search(
            query="Spanish language", grade=3,
            has_language_program=1, top_k=5
        )
        for school in results:
            if "has_language_program" in school:
                assert school["has_language_program"] == 1

    def test_search_returns_dicts(self, db):
        """search() should return a list of dicts."""
        results = db.search(query="elementary school", grade=2, top_k=3)
        assert isinstance(results, list)
        if results:
            assert isinstance(results[0], dict)

    def test_search_no_query_uses_hard_filter_only(self, db):
        """search() with no query and a grade filter should still return results."""
        results = db.search(grade=4, top_k=10)
        assert len(results) > 0

    def test_get_all_provider_types_returns_list(self, db):
        """get_all_provider_types() should return a non-empty list of strings."""
        types = db.get_all_provider_types()
        assert isinstance(types, list)
        assert len(types) > 0
        assert all(isinstance(t, str) for t in types)
        assert "Boston Public School" in types, (
            f"Expected 'Boston Public School' in provider types, got: {types}"
        )


# ── Proximity search tests ────────────────────────────────────────────────────

class TestProximitySearch:

    # Jamaica Plain approximate center
    JP_LAT = 42.3097
    JP_LON = -71.1065

    def test_jp_proximity_returns_results(self, db):
        """find_schools_near(JP coords) should return at least one school."""
        results = db.find_schools_near(
            lat=self.JP_LAT, lon=self.JP_LON, radius_miles=2.0
        )
        assert len(results) > 0, (
            "Expected at least one school within 2 miles of Jamaica Plain"
        )

    def test_proximity_results_within_radius(self, db):
        """All proximity results should be within the requested radius."""
        radius = 1.5
        results = db.find_schools_near(
            lat=self.JP_LAT, lon=self.JP_LON, radius_miles=radius
        )
        for school in results:
            dist = school.get("distance_miles")
            if dist is not None:
                assert dist <= radius + 0.01, (
                    f"{school['school']} is {dist:.2f} miles away, "
                    f"exceeds radius of {radius}"
                )

    def test_proximity_results_sorted_by_distance(self, db):
        """Proximity results should be sorted nearest-first."""
        results = db.find_schools_near(
            lat=self.JP_LAT, lon=self.JP_LON, radius_miles=3.0
        )
        if len(results) < 2:
            pytest.skip("Not enough results to check sort order")
        distances = [r["distance_miles"] for r in results if "distance_miles" in r]
        assert distances == sorted(distances), (
            "Proximity results are not sorted by distance ascending"
        )

    def test_tiny_radius_returns_fewer_results(self, db):
        """A very small radius should return fewer results than a large radius."""
        small = db.find_schools_near(
            lat=self.JP_LAT, lon=self.JP_LON, radius_miles=0.1
        )
        large = db.find_schools_near(
            lat=self.JP_LAT, lon=self.JP_LON, radius_miles=5.0
        )
        assert len(small) <= len(large), (
            "Smaller radius returned more results than larger radius"
        )


# ── School detail tests ───────────────────────────────────────────────────────

class TestSchoolDetail:

    def test_get_school_detail_for_valid_id(self, db):
        """get_school_detail should return a dict for an existing school ID."""
        all_schools = db.hard_filter(grade=5)
        assert len(all_schools) > 0, "Need at least one school to test detail lookup"

        school_id = all_schools[0]["id"]
        detail = db.get_school_detail(school_id)
        assert isinstance(detail, dict)
        assert detail["id"] == school_id
        assert "school" in detail

    def test_get_school_detail_invalid_id_returns_none(self, db):
        """get_school_detail should return None for a non-existent ID."""
        result = db.get_school_detail("nonexistent-school-id-xyz-999")
        assert result is None
