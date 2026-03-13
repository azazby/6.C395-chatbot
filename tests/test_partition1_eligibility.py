"""
Partition 1: User doesn't know which schools they're eligible for.

Expected chatbot behavior:
- MUST mention the school choice / eligibility tool (discoverbps / avela)
- MUST NOT recommend specific schools (eligibility is address-based)
- Should be warm and helpful, not dismissive

Requires: HF_TOKEN (skipped automatically if not set)
"""

import json
import pytest
from pathlib import Path
from helpers import contains_any, contains_question, no_specific_school_recommendation

# Load test cases
TEST_DATA = json.loads(
    (Path(__file__).parent / "test_data" / "test_cases.json").read_text()
)["partition1_eligibility"]

# Schools that should NOT be recommended when eligibility is unknown
KNOWN_BPS_SCHOOLS = [
    "Hernandez", "Mozart", "Mission Hill", "Curley", "Condon",
    "Manning", "McKay", "Excel", "O'Bryant", "Boston Arts Academy",
    "Fenway", "Madison Park", "New Mission", "UP Academy",
    "Kennedy Academy", "Boston Day", "Boston Green Academy",
    "Dudley Street",
]

ELIGIBILITY_TOOL_KEYWORDS = [
    "discoverbps", "bostonpublicschools.org", "school choice",
    "avela", "eligibility", "eligible", "boston.explore",
]

pytestmark = pytest.mark.chatbot


# ── Individual test cases from JSON ──────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_references_eligibility_tool(chatbot, case):
    """Response MUST mention the eligibility/school choice tool."""
    response = chatbot.get_response(case["input"])
    assert contains_any(response, ELIGIBILITY_TOOL_KEYWORDS), (
        f"[{case['id']}] Response did not mention the eligibility tool.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"Expected one of: {ELIGIBILITY_TOOL_KEYWORDS}"
    )


@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_does_not_recommend_specific_schools(chatbot, case):
    """Response MUST NOT recommend specific BPS schools without knowing eligibility."""
    response = chatbot.get_response(case["input"])
    assert no_specific_school_recommendation(response, KNOWN_BPS_SCHOOLS), (
        f"[{case['id']}] Response recommended a specific school without knowing "
        f"the user's address/eligibility.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}"
    )


# ── Embedding similarity tests ────────────────────────────────────────────────

@pytest.mark.parametrize("case", TEST_DATA, ids=[c["id"] for c in TEST_DATA])
def test_response_similarity_to_reference(chatbot, similarity_checker, case):
    """Response semantic similarity to reference answer must meet threshold."""
    response = chatbot.get_response(case["input"])
    score = similarity_checker(response, case["reference_answer"])
    threshold = case.get("similarity_threshold", 0.55)
    assert score >= threshold, (
        f"[{case['id']}] Embedding similarity {score:.3f} < threshold {threshold}.\n"
        f"Input: {case['input']!r}\n"
        f"Response: {response!r}\n"
        f"Reference: {case['reference_answer']!r}"
    )


# ── LLM-as-judge tests ────────────────────────────────────────────────────────

@pytest.mark.llm_judge
@pytest.mark.parametrize("case", TEST_DATA[:2], ids=[c["id"] for c in TEST_DATA[:2]])
def test_llm_judge_eligibility_response(chatbot, openai_judge, case):
    """GPT-4o judge scores the response on helpfulness and accuracy."""
    response = chatbot.get_response(case["input"])

    judge_prompt = f"""Rate this chatbot response on a 1-5 scale for each criterion.
Return ONLY valid JSON with these keys: relevance, completeness, accuracy, helpfulness.

User question: {case["input"]}
Chatbot response: {response}

Context: The chatbot helps Boston parents find schools. For eligibility questions,
it should direct users to the official school choice tool rather than recommending
specific schools (since eligibility depends on home address).

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

    assert scores.get("relevance", 0) >= 3, f"relevance score too low: {scores}"
    assert scores.get("helpfulness", 0) >= 3, f"helpfulness score too low: {scores}"
    assert scores.get("accuracy", 0) >= 3, f"accuracy score too low: {scores}"
