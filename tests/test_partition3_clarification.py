"""
Partition 3: User has some preferences but is missing hard requirements (grade/age).

Expected chatbot behavior:
- MUST ask at least one clarifying question (contains "?")
- SHOULD ask about grade or age
- MUST NOT give a ranked list of 3+ specific schools (not enough info yet)

Requires: HF_TOKEN (skipped automatically if not set)
"""

import json
import pytest
from pathlib import Path
from helpers import (
    contains_question,
    asks_about_grade_or_age,
    count_school_names,
    has_numbered_list,
)

TEST_DATA = json.loads(
    (Path(__file__).parent / "test_data" / "test_cases.json").read_text()
)["partition3_clarification"]

# All known BPS schools — used to count how many the bot recommended
KNOWN_BPS_SCHOOLS = [
    "Hernandez", "Mozart", "Mission Hill", "Curley", "Condon",
    "Manning", "McKay", "Excel", "O'Bryant", "Boston Arts Academy",
    "Fenway", "Madison Park", "New Mission", "UP Academy",
    "Kennedy Academy", "Boston Day", "Boston Green Academy",
    "Dudley Street", "Lyndon", "Sumner", "Bates", "Edwards",
    "Dearborn", "Carter", "Brighton", "West Roxbury",
]

pytestmark = pytest.mark.chatbot


# ── Rule-based tests ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_asks_clarifying_question(chatbot, case):
    """Response MUST contain a '?' — the bot should ask for more info."""
    response = chatbot.get_response(case["input"])
    assert contains_question(response), (
        f"[{case['id']}] Response did not ask a clarifying question (no '?').\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_asks_about_grade_or_age(chatbot, case):
    """Response SHOULD ask about grade or age before recommending schools."""
    response = chatbot.get_response(case["input"])
    assert asks_about_grade_or_age(response), (
        f"[{case['id']}] Response did not ask about grade or age.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_does_not_give_long_school_list(chatbot, case):
    """Response MUST NOT give a ranked list of 3+ schools — not enough info yet."""
    response = chatbot.get_response(case["input"])
    max_schools = case.get("max_school_recommendations", 2)
    school_count = count_school_names(response, KNOWN_BPS_SCHOOLS)

    assert school_count <= max_schools, (
        f"[{case['id']}] Response named {school_count} schools; "
        f"expected at most {max_schools} before gathering grade info.\n"
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


# ── Embedding similarity tests ────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_similarity_to_reference(chatbot, similarity_checker, case):
    """Response semantic similarity to reference answer must meet threshold."""
    response = chatbot.get_response(case["input"])
    score = similarity_checker(response, case["reference_answer"])
    threshold = case.get("similarity_threshold", 0.50)
    assert score >= threshold, (
        f"[{case['id']}] Embedding similarity {score:.3f} < threshold {threshold}.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"Reference: {case['reference_answer']!r}"
    )


# ── LLM-as-judge tests ────────────────────────────────────────────────────────

@pytest.mark.llm_judge
@pytest.mark.parametrize("case", TEST_DATA[:2], ids=[c["id"] for c in TEST_DATA[:2]])
def test_llm_judge_clarification_response(chatbot, openai_judge, case):
    """GPT-4o judge evaluates whether the bot appropriately seeks clarification."""
    response = chatbot.get_response(case["input"])

    judge_prompt = f"""Rate this chatbot response on a 1-5 scale.
Return ONLY valid JSON with keys: relevance, completeness, accuracy, helpfulness.

User question: {case["input"]}
Chatbot response: {response}

Context: The chatbot helps Boston parents find schools. When the user gives
incomplete information (e.g., missing grade level), the bot should ask
clarifying questions rather than immediately listing specific schools.
A good response asks about grade/age and shows it understood the user's interests.

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
