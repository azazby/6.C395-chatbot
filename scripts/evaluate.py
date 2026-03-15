#!/usr/bin/env python3
"""
BPS Chatbot Evaluation Runner
==============================
Standalone script — does NOT modify chat.py or any team code.

What it does:
  1. Runs all 9 test cases through the chatbot (via Groq, free Llama 3.1 8B)
  2. Applies rule-based checks on each response
  3. Saves each conversation to evaluation_output/<case_id>.txt
  4. Grades each conversation with an LLM judge
  5. Writes evaluation_output/report.md with a full summary

Chatbot backend (pick one, add to .env):
  GROQ_API_KEY=gsk_...        Free at console.groq.com — uses Llama 3.1 8B

LLM judge (pick one, add to .env — first one found wins):
  GOOGLE_API_KEY=AIza...      Free at aistudio.google.com — uses gemini-2.0-flash
  OPENAI_API_KEY=sk-...       Paid  at platform.openai.com  — uses gpt-4o

Usage:
  python3 scripts/evaluate.py
"""

import os
import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY  = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
CHATBOT_MODEL   = "llama-3.1-8b-instant"   # Groq's free Llama 3.1 8B
JUDGE_MODEL     = None                      # Set at runtime by make_judge_client()
OUTPUT_DIR      = ROOT / "evaluation_output"
TEST_CASES_FILE = ROOT / "tests" / "test_data" / "test_cases.json"

# Known BPS school names for rule-based checks
KNOWN_SCHOOLS = [
    "Hernandez", "Mozart", "Mission Hill", "Curley", "Condon", "Manning",
    "McKay", "Excel", "O'Bryant", "Boston Arts Academy", "Fenway",
    "Madison Park", "New Mission", "UP Academy", "Kennedy Academy",
    "Boston Day", "Boston Green Academy", "Dudley Street", "Lyndon",
    "Sumner", "Bates", "Edwards", "Dearborn", "Carter", "Snowden",
    "English High", "Josiah Quincy",
]

ELIGIBILITY_KEYWORDS = [
    "discoverbps", "bostonpublicschools.org", "school choice",
    "avela", "eligibility", "eligible", "boston.explore",
]

# ── Import system prompt from team's code ────────────────────────────────────
try:
    from src.chat import SYSTEM_PROMPT, AGENT_NAME
    print("✓ Loaded system prompt from src/chat.py")
except Exception as e:
    print(f"⚠ Could not import system prompt: {e}")
    SYSTEM_PROMPT = "You are a helpful Boston school finder assistant."
    AGENT_NAME = "Boston School Finder"


# ── Groq chatbot client ───────────────────────────────────────────────────────

def make_chatbot_client():
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env — get a free key at console.groq.com")
    from openai import OpenAI
    return OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")


def get_chatbot_response(client, user_input, history=None):
    """Call the chatbot (Groq/Llama) with the team's system prompt."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=CHATBOT_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
    )
    return response.choices[0].message.content or ""


# ── Judge client (Google AI Studio OR OpenAI) ─────────────────────────────────

def make_judge_client():
    """
    Returns (client, model_name) for whichever judge key is available.
    Priority: GOOGLE_API_KEY (free) → OPENAI_API_KEY (paid).
    Returns (None, None) if neither is set.
    """
    global JUDGE_MODEL
    from openai import OpenAI

    if GOOGLE_API_KEY:
        JUDGE_MODEL = "gemini-2.0-flash"
        print("✓ Judge: Google Gemini (gemini-2.0-flash) via AI Studio")
        return OpenAI(
            api_key=GOOGLE_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), JUDGE_MODEL

    if OPENAI_API_KEY:
        JUDGE_MODEL = "gpt-4o"
        print("✓ Judge: OpenAI GPT-4o")
        return OpenAI(api_key=OPENAI_API_KEY), JUDGE_MODEL

    print("⚠ No judge key set (GOOGLE_API_KEY or OPENAI_API_KEY) — grading skipped")
    return None, None


def grade_with_gemini(judge, case_id, partition, user_input, response, rule_results):
    """Ask Gemini to grade a chatbot response. Returns dict of scores + comments."""
    if not judge:
        return None

    partition_context = {
        "partition1_eligibility": (
            "The user asked about school eligibility. A good response MUST mention "
            "the official eligibility tool (discoverbps.org, avela, or bostonpublicschools.org) "
            "and should NOT recommend specific schools (eligibility depends on home address)."
        ),
        "partition2_browsing": (
            "The user is browsing schools by preference. A good response MUST name at least "
            "one real Boston school and must NOT refuse to help without an address."
        ),
        "partition3_clarification": (
            "The user gave partial information (missing grade/age). A good response MUST "
            "ask a clarifying question (especially about grade level) before recommending schools."
        ),
        "partition4_full_search": (
            "The user provided full information (grade, area, preferences). A good response "
            "MUST recommend at least 2 specific schools in a list format and explain why each fits."
        ),
    }

    rule_summary = "\n".join(
        f"  - {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in rule_results.items()
    )

    prompt = f"""You are evaluating a Boston Public Schools chatbot response.
Rate the response on each criterion from 1 (very poor) to 5 (excellent).
Return ONLY valid JSON — no other text.

=== CONTEXT ===
{partition_context.get(partition, "General school finder chatbot.")}

=== CONVERSATION ===
User: {user_input}
Chatbot: {response}

=== RULE-BASED CHECK RESULTS ===
{rule_summary}

=== SCORING CRITERIA ===
- relevance: Does the response directly address what the user asked?
- accuracy: Is the information factually correct and grounded (no made-up schools/facts)?
- helpfulness: Would a Boston parent find this genuinely useful?
- completeness: Does it fully address the user's need, or leave important gaps?
- eligibility_handling: (1-5) Does it correctly handle eligibility — directing to the tool when needed, not gatekeeping when browsing?

Return JSON only, example:
{{"relevance": 4, "accuracy": 4, "helpfulness": 5, "completeness": 3, "eligibility_handling": 4, "comments": "Brief summary of strengths and weaknesses."}}"""

    try:
        r = judge.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = r.choices[0].message.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


# ── Rule-based checks ─────────────────────────────────────────────────────────

def run_rule_checks(partition, response, case):
    """Returns dict of {check_name: True/False}."""
    results = {}
    lower = response.lower()

    if partition == "partition1_eligibility":
        results["mentions_eligibility_tool"] = any(k in lower for k in ELIGIBILITY_KEYWORDS)
        results["no_specific_school_recommended"] = not any(
            s.lower() in lower for s in KNOWN_SCHOOLS
        )
        results["response_not_empty"] = len(response.strip()) > 20

    elif partition == "partition2_browsing":
        results["names_at_least_one_school"] = any(s.lower() in lower for s in KNOWN_SCHOOLS)
        results["no_gatekeeping"] = not bool(re.search(
            r"can'?t help without.{0,20}address|need.{0,20}address.{0,20}(first|before)",
            lower
        ))
        results["response_not_empty"] = len(response.strip()) > 20

    elif partition == "partition3_clarification":
        results["asks_clarifying_question"] = "?" in response
        results["asks_grade_or_age"] = bool(re.search(
            r'grade|\bage\b|year.{0,5}old|how old|kindergarten', lower
        ))
        results["does_not_list_3plus_schools"] = sum(
            1 for s in KNOWN_SCHOOLS if s.lower() in lower
        ) <= 2
        results["response_not_empty"] = len(response.strip()) > 20

    elif partition == "partition4_full_search":
        school_count = sum(1 for s in KNOWN_SCHOOLS if s.lower() in lower)
        results["recommends_2plus_schools"] = school_count >= 2
        results["uses_list_format"] = bool(re.search(r'^\s*\d+[.)]\s+\S|^\s*[-*•]\s+\S', response, re.MULTILINE))
        results["references_attributes"] = bool(re.search(
            r'language|spanish|bilingual|after.?school|surround care|uniform|arts|stem|math|science|ap\b|ib\b',
            lower
        ))
        results["response_not_empty"] = len(response.strip()) > 20

    return results


# ── File saving ───────────────────────────────────────────────────────────────

def save_conversation(case_id, partition, user_input, response, rule_results, grades):
    """Save a single conversation + results to a text file."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    filepath = OUTPUT_DIR / f"{case_id}.txt"

    rule_lines = "\n".join(
        f"  {'✓' if v else '✗'} {k}" for k, v in rule_results.items()
    )

    if grades and "error" not in grades:
        avg = sum(v for k, v in grades.items() if isinstance(v, (int, float))) / max(
            1, sum(1 for v in grades.values() if isinstance(v, (int, float)))
        )
        grade_lines = "\n".join(
            f"  {k}: {v}/5" if isinstance(v, (int, float)) else f"  {k}: {v}"
            for k, v in grades.items()
        )
        grade_lines += f"\n  AVERAGE: {avg:.1f}/5"
    elif grades and "error" in grades:
        grade_lines = f"  Error: {grades['error']}"
    else:
        grade_lines = "  (Gemini grading not run)"

    content = f"""=== BPS Chatbot Evaluation — {case_id} ===
Partition : {partition}
Timestamp : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Model     : {CHATBOT_MODEL} (via Groq)

--- USER INPUT ---
{user_input}

--- CHATBOT RESPONSE ---
{response}

--- RULE-BASED CHECKS ---
{rule_lines}

--- GEMINI GRADE ({JUDGE_MODEL}) ---
{grade_lines}
"""
    filepath.write_text(content)
    return filepath


# ── Main evaluation loop ──────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  BPS CHATBOT EVALUATION")
    print("="*60 + "\n")

    # Load test cases
    test_cases = json.loads(TEST_CASES_FILE.read_text())

    # Init clients
    try:
        chatbot = make_chatbot_client()
        print(f"✓ Chatbot client ready (Groq / {CHATBOT_MODEL})\n")
    except RuntimeError as e:
        print(f"✗ {e}\n")
        sys.exit(1)

    judge, judge_model_name = make_judge_client()
    if judge:
        print()

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Collect results for report
    all_results = []

    for partition_key, cases in test_cases.items():
        partition_label = partition_key.replace("_", " ").title()
        print(f"\n── {partition_label} ──────────────────────────")

        for case in cases:
            case_id = case["id"]
            user_input = case["input"]
            print(f"  [{case_id}] {user_input[:60]}...")

            # Get chatbot response
            try:
                response = get_chatbot_response(chatbot, user_input)
                time.sleep(3)  # avoid Groq rate limits (free tier: 30 req/min)
            except Exception as e:
                response = f"[ERROR: {e}]"
                print(f"    ✗ Chatbot error: {e}")

            # Rule checks
            rule_results = run_rule_checks(partition_key, response, case)
            pass_count = sum(rule_results.values())
            total = len(rule_results)
            print(f"    Rules: {pass_count}/{total} passed")

            # Gemini grading
            grades = grade_with_gemini(judge, case_id, partition_key, user_input, response, rule_results)
            if grades and "error" not in grades:
                nums = [v for v in grades.values() if isinstance(v, (int, float))]
                avg = sum(nums) / len(nums) if nums else 0
                print(f"    Gemini avg: {avg:.1f}/5")
            elif grades and "error" in grades:
                print(f"    Gemini error: {grades['error']}")

            time.sleep(1)  # avoid rate limits

            # Save conversation file
            filepath = save_conversation(
                case_id, partition_key, user_input, response, rule_results, grades
            )

            all_results.append({
                "case_id": case_id,
                "partition": partition_key,
                "input": user_input,
                "response": response,
                "rules": rule_results,
                "grades": grades,
            })

    # ── Write report.md ───────────────────────────────────────────────────────
    write_report(all_results)
    print(f"\n✓ Report saved to {OUTPUT_DIR}/report.md")
    print(f"✓ Conversations saved to {OUTPUT_DIR}/\n")


def write_report(all_results):
    lines = [
        "# BPS Chatbot Evaluation Report",
        f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Model tested:** {CHATBOT_MODEL} (Groq / Llama 3.1 8B)  ",
        f"**Judge:** {JUDGE_MODEL} (Gemini)  ",
        "\n---\n",
        "## Summary Table\n",
        "| Case | Partition | Rules | Gemini Avg | Top Issue |",
        "|------|-----------|-------|------------|-----------|",
    ]

    for r in all_results:
        rules = r["rules"]
        pass_count = sum(rules.values())
        total = len(rules)
        failed = [k for k, v in rules.items() if not v]
        top_issue = failed[0] if failed else "—"

        grades = r.get("grades") or {}
        nums = [v for v in grades.values() if isinstance(v, (int, float))]
        avg_str = f"{sum(nums)/len(nums):.1f}" if nums else "N/A"

        partition_short = r["partition"].replace("partition", "P").replace("_eligibility","").replace("_browsing","").replace("_clarification","").replace("_full_search","")
        lines.append(
            f"| {r['case_id']} | {partition_short} | {pass_count}/{total} | {avg_str}/5 | {top_issue} |"
        )

    lines += [
        "\n---\n",
        "## Detailed Results\n",
    ]

    for r in all_results:
        lines += [
            f"### {r['case_id']} — {r['partition']}",
            f"\n**Input:** {r['input']}\n",
            f"**Response:**\n> {r['response'][:400]}{'...' if len(r['response']) > 400 else ''}\n",
            "**Rule checks:**",
        ]
        for check, passed in r["rules"].items():
            lines.append(f"- {'✓' if passed else '✗'} `{check}`")

        grades = r.get("grades") or {}
        if grades and "error" not in grades:
            lines.append("\n**Gemini scores:**")
            for k, v in grades.items():
                if k == "comments":
                    lines.append(f"- **Comments:** {v}")
                elif isinstance(v, (int, float)):
                    bar = "█" * int(v) + "░" * (5 - int(v))
                    lines.append(f"- {k}: {bar} {v}/5")
        lines.append("\n---\n")

    (OUTPUT_DIR / "report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
