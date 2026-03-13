"""
BPS Eligible School Finder Tool
================================
Wraps the Avela Explore REST API (boston.explore.avela.org) to compute
ELIGIBLE schools for a student.

What this does differently from the original script:
  1. Calls the same Avela eligibility endpoint, which returns INELIGIBLE schools.
  2. Loads your local school database (choice_tool_raw.json by default).
  3. Restricts the universe to Boston Public School rows.
  4. Computes eligible = all candidate BPS schools - ineligible schools.
  5. Returns enriched school objects that an LLM can rank/filter downstream.

Usage:
  pip install requests

  from check_eligibility_eligible import find_eligible_schools

  result = find_eligible_schools(
      grade_level="K2",
      street_address="123 Main St",
      zip_code="02118",
      city="Boston",
      state="MA",
      home_language="English",
      dataset_path="choice_tool_raw.json",
  )
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# API Configuration
# =============================================================================

BASE_URL = "https://prod.execute-api.apply.avela.org/eligibility/organizations/boston"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://boston.explore.avela.org",
    "Referer": "https://boston.explore.avela.org/",
}

FORM_TEMPLATE_ID = "cd0501a5-eb9c-4aa5-a7ff-6402280a5b51"

GRADE_QUESTION_ID = "59e28093-6c84-496d-b37a-a68162a75d36"
ADDRESS_QUESTION_ID = "b9fb2ac3-40d8-4d6a-85a9-da0f6d0a2762"
LANGUAGE_QUESTION_ID = "f8552cb9-099a-412a-9f69-69e6a77176ee"

GRADE_TO_OPTION_ID = {
    "K0": "a409dc76-94cc-471c-bc68-c7b68d05147d",
    "K1": "9e1e0cbf-c147-48ac-a961-34fc97a0be67",
    "K2": "4134373f-5e12-4a03-b36f-c0a545db9eb7",
    "1": "eaf903c1-b6c5-4c9d-8905-dc6152ac9f5e",
    "2": "fb580408-4db9-4e54-8191-cdd6bd95a4fe",
    "3": "f59adf0b-69d4-4b5b-8a40-5e87886eaba7",
    "4": "bd63e458-16cc-46ed-a260-c936a85fdc55",
    "5": "12746de8-ab87-4af5-b8ef-abcb83285467",
    "6": "bb81c16d-2f72-41a9-929c-9316f2143780",
    "7": "92efe874-5e03-4037-aefd-1edded298e46",
    "8": "f2529c1b-c1c1-4fb6-bf2d-c2de261d3b5b",
    "9": "f6b26370-247e-4ef3-8144-0b1eddc86849",
    "10": "d98e3523-82c7-4940-9177-a4d92807914f",
    "11": "5d40fd74-63bd-49ce-8439-8b3a55ed0864",
    "12": "2ce44985-23b2-438a-906e-e56369300467",
}

LANGUAGE_TO_OPTION_ID = {
    "English": "c188baa2-f2e8-4015-80ee-a42514617585",
    "Spanish": "3b523e63-a0a8-4782-9ec8-ba9e5ee16b04",
    "Arabic": "10b89d82-0751-47f5-8216-66574f7b0bac",
    "Burmese": "050bcd41-f06f-4808-9c91-96afc25e1fa7",
    "Cambodian": "6732674b-78d2-4e65-8397-66a6fdd9e68b",
    "Cantonese": "5d9314ac-54cb-4c2f-ba11-70df2cb2a7a9",
    "Cape Verdean": "254a5e6e-e553-40f3-b9be-c4fd949f2e07",
    "French": "1f13bc17-9f93-4d7d-ae27-90476b01b19e",
    "Greek": "4d7ff032-53ed-4893-be1f-a4ec813f2679",
    "Haitian Creole": "562093f6-b3bd-4003-bb85-e51210eb2a35",
    "H'Mong": "a92fd31d-8f56-4d1c-a465-da4a083f0285",
    "Italian": "89c38e6d-b9b7-4516-a2c7-661a66452684",
    "Korean": "61b2a192-594c-4f4f-b9fb-f5e7d3c2df91",
    "Mandarin": "5f5820d8-f3c9-40cf-8e3e-9730961c7bf7",
    "Portuguese": "28d7754c-e035-4ef0-b942-a501ca6e91ad",
    "Russian": "2969bff1-dd46-402c-92a9-cb713deeddd6",
    "Somali": "fce808a3-f366-409e-9c2b-863b4f7c3b67",
    "Toishanese": "96cee9f4-b960-4f9a-ad6c-6f8a03c4a5e7",
    "Vietnamese": "9f580e8e-ca8e-4142-a3c2-5336fab3d1e1",
    "Other": "b81ceb21-2504-41b8-a433-97ee4aea4944",
}

GRADE_NORMALIZATION = {
    "K0": -2,
    "K1": -1,
    "K2": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "11": 11,
    "12": 12,
}


# =============================================================================
# Avela API helpers
# =============================================================================

def get_enrollment_periods() -> list[dict[str, Any]]:
    url = f"{BASE_URL}/enrollmentPeriods"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        periods = data.get("enrollment_period", [])
        logger.info("Found %s enrollment period(s)", len(periods))
        return periods
    except requests.RequestException as exc:
        logger.error("Failed to fetch enrollment periods: %s", exc)
        return []


def find_eligibility(question_id_to_answer: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE_URL}/formTemplates/{FORM_TEMPLATE_ID}/findEligibility"
    payload = {
        "questionIdToAnswer": question_id_to_answer,
        "applicationType": "Explore",
    }
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("Failed to check eligibility: %s", exc)
        return {"ineligibleSchools": [], "error": str(exc)}


# =============================================================================
# Local data helpers
# =============================================================================

def _normalize_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_grade_for_compare(grade_level: str) -> int:
    if grade_level not in GRADE_NORMALIZATION:
        raise ValueError(f"Unsupported grade_level '{grade_level}'")
    return GRADE_NORMALIZATION[grade_level]


def load_school_catalog(dataset_path: str | Path) -> list[dict[str, Any]]:
    path = Path(dataset_path)
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"Expected list in {path}, got {type(rows).__name__}")
    return rows


def filter_candidate_bps_schools(
    all_rows: list[dict[str, Any]],
    grade_level: str,
) -> list[dict[str, Any]]:
    target_grade = _normalize_grade_for_compare(grade_level)
    candidates: list[dict[str, Any]] = []

    for row in all_rows:
        if row.get("provider_type") != "Boston Public School":
            continue

        grades_filter = row.get("grades_filter") or []
        if isinstance(grades_filter, list) and grades_filter:
            normalized_grades_filter = {str(x).strip() for x in grades_filter}
            grade_display = {
                "K0": "3 yrs old (K0)",
                "K1": "4 yrs old (K1)",
                "K2": "5 yrs old (K2)",
            }.get(grade_level, grade_level)
            if grade_display not in normalized_grades_filter:
                continue
            candidates.append(row)
            continue

        # Fallback if grades_filter is missing but metadata-style min/max exists.
        grade_min = row.get("grade_min")
        grade_max = row.get("grade_max")
        if isinstance(grade_min, int) and isinstance(grade_max, int):
            if grade_min <= target_grade <= grade_max:
                candidates.append(row)
            continue

        # If no grade info exists, keep the school rather than accidentally dropping it.
        candidates.append(row)

    return candidates


def build_school_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = _normalize_id(row.get("id"))
        if row_id:
            index[row_id] = row
    return index


def parse_ineligible_ids(ineligible_schools: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for row in ineligible_schools:
        ref_id = row.get("referenceId")
        school_id = row.get("id")
        if ref_id is not None:
            ids.add(_normalize_id(ref_id))
        elif school_id is not None:
            ids.add(_normalize_id(school_id))
    return ids


def enrich_school_for_output(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "school": row.get("school"),
        "provider_type": row.get("provider_type"),
        "address": row.get("address"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "grade_span": row.get("grade_span"),
        "grades_filter": row.get("grades_filter"),
        "language_programming_text": row.get("language_programming_text"),
        "specialized_education_programs": row.get("specialized_education_programs"),
        "special_admission_filter": row.get("special_admission_filter"),
        "special_admission_school": row.get("special_admission_school"),
        "dual_language": row.get("dual_language"),
        "after_school_program": row.get("after_school_program"),
        "before_school_program": row.get("before_school_program"),
        "uniform": row.get("uniform"),
        "transportation": row.get("transportation"),
        "website": row.get("website"),
        "phone_number": row.get("phone_number"),
        "overview_mission_statement": row.get("overview_mission_statement"),
        "family_engagement_opportunities": row.get("family_engagement_opportunities"),
        "raw": row,
    }


# =============================================================================
# Main function for the LLM/tool layer
# =============================================================================

def find_eligible_schools(
    grade_level: str,
    street_address: str,
    zip_code: str,
    city: str = "Boston",
    state: str = "MA",
    street_address_line2: str = "",
    home_language: str = "English",
    dataset_path: str = "raw_data/choice_tool_raw.json",
    include_ineligible: bool = False,
) -> dict[str, Any]:
    """
    Return ELIGIBLE Boston Public Schools for the given student profile.
    """
    result: dict[str, Any] = {
        "eligible_schools": [],
        "eligible_count": 0,
        "ineligible_schools": [],
        "ineligible_count": 0,
        "candidate_school_count": 0,
        "matched_ineligible_count": 0,
        "unmatched_ineligible_ids": [],
        "enrollment_period": None,
        "error": None,
    }

    grade_option_id = GRADE_TO_OPTION_ID.get(grade_level)
    if not grade_option_id:
        result["error"] = (
            f"Invalid grade level '{grade_level}'. "
            f"Valid options: {', '.join(GRADE_TO_OPTION_ID.keys())}"
        )
        return result

    lang_option_id = LANGUAGE_TO_OPTION_ID.get(home_language)
    if not lang_option_id:
        for lang, option_id in LANGUAGE_TO_OPTION_ID.items():
            if lang.lower() == home_language.lower():
                lang_option_id = option_id
                break
        if not lang_option_id:
            lang_option_id = LANGUAGE_TO_OPTION_ID["Other"]
            logger.warning("Language '%s' not recognized, using 'Other'", home_language)

    periods = get_enrollment_periods()
    if not periods:
        result["error"] = (
            "Could not fetch enrollment periods. The BPS enrollment system may be "
            "temporarily unavailable."
        )
        return result
    result["enrollment_period"] = periods[0].get("name", "Unknown")

    answers = {
        GRADE_QUESTION_ID: grade_option_id,
        ADDRESS_QUESTION_ID: {
            "streetAddress": street_address,
            "streetAddressLine2": street_address_line2,
            "city": city,
            "state": state,
            "zipCode": zip_code,
        },
        LANGUAGE_QUESTION_ID: lang_option_id,
    }

    eligibility_result = find_eligibility(answers)
    if "error" in eligibility_result:
        result["error"] = eligibility_result["error"]
        return result

    ineligible_rows = eligibility_result.get("ineligibleSchools", [])
    result["ineligible_count"] = len(ineligible_rows)

    all_rows = load_school_catalog(dataset_path)
    candidate_rows = filter_candidate_bps_schools(all_rows, grade_level=grade_level)
    result["candidate_school_count"] = len(candidate_rows)

    candidate_index = build_school_index(candidate_rows)
    ineligible_ids = parse_ineligible_ids(ineligible_rows)

    matched_ineligible_ids = sorted(i for i in ineligible_ids if i in candidate_index)
    unmatched_ineligible_ids = sorted(i for i in ineligible_ids if i not in candidate_index)

    eligible_rows = [
        enrich_school_for_output(row)
        for school_id, row in candidate_index.items()
        if school_id not in ineligible_ids
    ]
    eligible_rows.sort(key=lambda r: (str(r.get("school") or "").lower(), str(r.get("id") or "")))

    result["eligible_schools"] = eligible_rows
    result["eligible_count"] = len(eligible_rows)
    result["matched_ineligible_count"] = len(matched_ineligible_ids)
    result["unmatched_ineligible_ids"] = unmatched_ineligible_ids

    if include_ineligible:
        result["ineligible_schools"] = [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "referenceId": row.get("referenceId"),
            }
            for row in ineligible_rows
        ]

    logger.info(
        "Eligibility check complete: %s eligible / %s candidates / %s ineligible returned / %s matched to catalog",
        result["eligible_count"],
        result["candidate_school_count"],
        result["ineligible_count"],
        result["matched_ineligible_count"],
    )
    return result


TOOL_DEFINITION = {
    "type": "function",
    "name": "find_eligible_schools",
    "description": (
        "Return the Boston Public Schools a student is eligible to apply to, "
        "based on grade, address, and home language. This tool calls the Avela "
        "eligibility API, subtracts ineligible schools from the uploaded BPS catalog, "
        "and returns enriched eligible school objects for downstream ranking/filtering."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "grade_level": {
                "type": "string",
                "enum": ["K0", "K1", "K2", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
                "description": "Grade the student is entering.",
            },
            "street_address": {
                "type": "string",
                "description": "Street address, e.g. '224 Albany St'",
            },
            "zip_code": {
                "type": "string",
                "description": "ZIP code, e.g. '02118'",
            },
            "city": {
                "type": "string",
                "default": "Boston",
            },
            "state": {
                "type": "string",
                "default": "MA",
            },
            "street_address_line2": {
                "type": "string",
                "default": "",
            },
            "home_language": {
                "type": "string",
                "default": "English",
            },
            "dataset_path": {
                "type": "string",
                "default": "choice_tool_raw.json",
                "description": "Path to the local school catalog JSON to join against.",
            },
            "include_ineligible": {
                "type": "boolean",
                "default": False,
                "description": "Whether to also include the raw ineligible list in the response.",
            },
        },
        "required": ["grade_level", "street_address", "zip_code"],
    },
}


if __name__ == "__main__":
    print("=" * 60)
    print("BPS Eligible School Finder — Example")
    print("=" * 60)

    example = find_eligible_schools(
        grade_level="K2",
        street_address="2300 Washington St",
        zip_code="02119",
        city="Boston",
        state="MA",
        home_language="English",
        dataset_path="raw_data/choice_tool_raw.json",
        include_ineligible=False,
    )

    if example["error"]:
        print("ERROR:", example["error"])
    else:
        print("Enrollment Period:", example["enrollment_period"])
        print("Candidate BPS schools for grade:", example["candidate_school_count"])
        print("Eligible count:", example["eligible_count"])
        print("Eligible schools:")
        for i, school in enumerate(sorted(example["eligible_schools"], key=lambda s: s["school"]), start=1):
            print(f"{i}. {school['school']} (id: {school['id']})")
