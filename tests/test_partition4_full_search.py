"""
Partition 4: User provides all the information needed (grade, area, preferences).

Expected chatbot behavior:
- MUST mention >= 2 real school names
- SHOULD present results in a numbered or bulleted list
- SHOULD reference specific attributes (language, care, uniforms, etc.)
- At least 1 recommended school SHOULD overlap with database results for the same query

Requires: HF_TOKEN (skipped automatically if not set)
"""

import json
import pytest
from pathlib import Path
from helpers import (
    schools_overlap,
    has_list,
    references_specific_attributes,
    count_school_names,
)

TEST_DATA = json.loads(
    (Path(__file__).parent / "test_data" / "test_cases.json").read_text()
)["partition4_full_search"]

KNOWN_BPS_SCHOOLS = [
    "Hernandez", "Mozart", "Mission Hill", "Curley", "Condon",
    "Manning", "McKay", "Excel", "O'Bryant", "Boston Arts Academy",
    "Fenway", "Madison Park", "New Mission", "UP Academy",
    "Kennedy Academy", "Boston Day", "Boston Green Academy",
    "Dudley Street", "Lyndon", "Sumner", "Bates", "Edwards",
    "Dearborn", "Carter", "Brighton", "West Roxbury", "Snowden",
    "English High", "Community Academy", "Josiah Quincy",
]

pytestmark = pytest.mark.chatbot


# ── Helper: run the matching DB query for a test case ────────────────────────

def _run_db_query(db, case: dict) -> list:
    """Run the test case's db_query against the database."""
    q = case.get("db_query", {})
    return db.search(
        query=q.get("query", ""),
        grade=q.get("grade"),
        has_language_program=q.get("has_language_program"),
        surround_care=q.get("surround_care"),
        ADA=q.get("ADA"),
        top_k=q.get("top_k", 5),
    )


# ── Rule-based tests ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_recommends_multiple_schools(chatbot, db, case):
    """Response MUST name at least 2 schools when user provides full information."""
    response = chatbot.get_response(case["input"])
    db_results = _run_db_query(db, case)
    all_school_names = (
        KNOWN_BPS_SCHOOLS
        + [r["school"] for r in db_results if isinstance(r, dict) and "school" in r]
    )

    count = count_school_names(response, list(set(all_school_names)))
    min_expected = case.get("min_school_recommendations", 2)

    assert count >= min_expected, (
        f"[{case['id']}] Response mentioned {count} school(s); "
        f"expected at least {min_expected}.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_uses_list_format(chatbot, case):
    """Response SHOULD use a numbered or bulleted list when recommending schools."""
    response = chatbot.get_response(case["input"])
    assert has_list(response), (
        f"[{case['id']}] Response did not use a list format.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_references_attributes(chatbot, case):
    """Response SHOULD mention specific school attributes as evidence."""
    response = chatbot.get_response(case["input"])
    assert references_specific_attributes(response), (
        f"[{case['id']}] Response did not reference any specific school attributes "
        f"(language, after-school, uniforms, AP, arts, etc.).\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_is_not_empty(chatbot, case):
    """Response must be a non-empty string."""
    response = chatbot.get_response(case["input"])
    assert response and len(response.strip()) > 30, (
        f"[{case['id']}] Response is empty or too short.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


# ── Retrieval alignment tests ─────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_chatbot_overlaps_with_database_results(chatbot, db, case):
    """At least 1 recommended school should appear in database results."""
    response = chatbot.get_response(case["input"])
    db_results = _run_db_query(db, case)

    if not db_results:
        pytest.skip(f"[{case['id']}] DB returned no results — cannot validate overlap")

    assert schools_overlap(response, db_results, min_overlap=1), (
        f"[{case['id']}] No overlap between chatbot recommendations and DB results.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"DB top schools: {[r['school'] for r in db_results[:5]]}"
    )


# ── Embedding similarity tests ────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_similarity_to_db_context(chatbot, db, similarity_checker, case):
    """
    Response similarity to concatenated top-3 DB results must meet threshold.
    This checks if the chatbot's output is grounded in the actual database content.
    """
    response = chatbot.get_response(case["input"])
    db_results = _run_db_query(db, case)

    if not db_results:
        pytest.skip(f"[{case['id']}] DB returned no results — cannot check grounding")

    top3_context = " ".join(
        r.get("description", r.get("school", ""))
        for r in db_results[:3]
        if isinstance(r, dict)
    )

    if not top3_context.strip():
        pytest.skip(f"[{case['id']}] No description text in DB results")

    score = similarity_checker(response, top3_context)
    threshold = case.get("similarity_threshold", 0.45)
    assert score >= threshold, (
        f"[{case['id']}] Response-to-DB similarity {score:.3f} < threshold {threshold}.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"DB context (first 200 chars): {top3_context[:200]!r}"
    )


# ── LLM-as-judge tests ────────────────────────────────────────────────────────

@pytest.mark.llm_judge
@pytest.mark.parametrize("case", TEST_DATA[:2], ids=[c["id"] for c in TEST_DATA[:2]])
def test_llm_judge_full_search_response(chatbot, db, openai_judge, case):
    """GPT-4o judge evaluates quality of full-information school recommendations."""
    response = chatbot.get_response(case["input"])
    db_results = _run_db_query(db, case)
    db_schools = [r["school"] for r in db_results[:5] if isinstance(r, dict)]

    judge_prompt = f"""Rate this chatbot response on a 1-5 scale.
Return ONLY valid JSON with keys: relevance, completeness, accuracy, helpfulness.

User question: {case["input"]}
Chatbot response: {response}
Database results (top schools from same query): {db_schools}

Context: The user provided full information (grade, location, preferences).
A good response should: name 2+ specific schools, use a list format, mention
why each school fits the user's criteria, and be grounded in real database results.

Return JSON only. Example: {{"relevance": 4, "completeness": 3, "accuracy": 5, "helpfulness": 4}}"""

    completion = openai_judge.chat.completions.create(
        model=openai_judge._judge_model,
        messages=[{"role": "user", "content": judge_prompt}],
        temperature=0,
    )

    import json as _json
    try:
        scores = _json.loads(completion.choices[0].message.content.strip())
    except _json.JSONDecodeError:
        pytest.fail(f"Judge returned invalid JSON: {completion.choices[0].message.content}")

    assert scores.get("relevance", 0) >= 3, f"relevance too low: {scores}"
    assert scores.get("completeness", 0) >= 3, f"completeness too low: {scores}"
    assert scores.get("helpfulness", 0) >= 3, f"helpfulness too low: {scores}"
