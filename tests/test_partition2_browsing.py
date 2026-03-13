"""
Partition 2: User just wants to browse schools.

Expected chatbot behavior:
- MUST return at least 1 real school name
- MUST NOT gatekeep ("I can't help without your address")
- Should match what the database would return for the same query

Requires: HF_TOKEN (skipped automatically if not set)
"""

import json
import pytest
from pathlib import Path
from helpers import (
    contains_any,
    not_gatekeeping,
    schools_overlap,
    has_list,
)

TEST_DATA = json.loads(
    (Path(__file__).parent / "test_data" / "test_cases.json").read_text()
)["partition2_browsing"]

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
        top_k=q.get("top_k", 5),
    )


# ── Rule-based tests ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_contains_at_least_one_school_name(chatbot, db, case):
    """Response must mention at least one real school name from DB results."""
    response = chatbot.get_response(case["input"])
    db_results = _run_db_query(db, case)

    school_names = [r["school"] for r in db_results if isinstance(r, dict) and "school" in r]
    assert school_names, (
        f"[{case['id']}] DB returned no results for query — cannot validate school names.\n"
        f"DB query: {case.get('db_query')}"
    )

    assert schools_overlap(response, db_results, min_overlap=1), (
        f"[{case['id']}] Response did not mention any school from DB results.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"DB schools: {school_names}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_does_not_gatekeep(chatbot, case):
    """Response MUST NOT refuse to help without an address."""
    response = chatbot.get_response(case["input"])
    assert not_gatekeeping(response), (
        f"[{case['id']}] Response appeared to gatekeep (demanded address before helping).\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_is_not_empty(chatbot, case):
    """Response must be a non-empty string."""
    response = chatbot.get_response(case["input"])
    assert response and len(response.strip()) > 20, (
        f"[{case['id']}] Response is empty or too short.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


# ── Retrieval alignment tests ─────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_chatbot_schools_overlap_with_database(chatbot, db, case):
    """At least 1 school recommended by chatbot should appear in DB results."""
    response = chatbot.get_response(case["input"])
    db_results = _run_db_query(db, case)

    if not db_results:
        pytest.skip(f"[{case['id']}] DB returned no results for this query")

    assert schools_overlap(response, db_results, min_overlap=1), (
        f"[{case['id']}] No overlap between chatbot response and database results.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"DB top schools: {[r['school'] for r in db_results[:5]]}"
    )


# ── Embedding similarity tests ────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_similarity_to_reference(chatbot, similarity_checker, case):
    """Response semantic similarity to reference answer must meet threshold."""
    response = chatbot.get_response(case["input"])
    score = similarity_checker(response, case["reference_answer"])
    threshold = case.get("similarity_threshold", 0.45)
    assert score >= threshold, (
        f"[{case['id']}] Embedding similarity {score:.3f} < threshold {threshold}.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"Reference: {case['reference_answer']!r}"
    )


# ── LLM-as-judge tests ────────────────────────────────────────────────────────

@pytest.mark.llm_judge
@pytest.mark.parametrize("case", TEST_DATA[:2], ids=[c["id"] for c in TEST_DATA[:2]])
def test_llm_judge_browsing_response(chatbot, openai_judge, case):
    """GPT-4o judge evaluates helpfulness, completeness, and accuracy."""
    response = chatbot.get_response(case["input"])

    judge_prompt = f"""Rate this chatbot response on a 1-5 scale.
Return ONLY valid JSON with keys: relevance, completeness, accuracy, helpfulness.

User question: {case["input"]}
Chatbot response: {response}

Context: The chatbot helps Boston parents browse schools. It should name real
schools and NOT refuse to help because the user hasn't provided their address.

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
    assert scores.get("helpfulness", 0) >= 3, f"helpfulness too low: {scores}"
    assert scores.get("completeness", 0) >= 2, f"completeness too low: {scores}"
