from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from collections import Counter

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "raw_data"
DEFAULT_DATASET_PATH = DATA_DIR / "choice_tool_raw.json"

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



def grade_to_num(grade: str) -> int:
    grade = str(grade).strip().upper()
    if grade == "K0":
        return -2
    if grade == "K1":
        return -1
    if grade == "K2":
        return 0
    return int(grade)


def normalize_id(value: Any) -> str:
    return str(value).strip()


def get_enrollment_periods() -> tuple[list[dict[str, Any]], str | None]:
    url = f"{BASE_URL}/enrollmentPeriods"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list):
            periods = data
        elif isinstance(data, dict):
            periods = data.get("enrollment_period", [])
        else:
            return [], f"Unexpected response type: {type(data).__name__}"

        if not isinstance(periods, list):
            return [], f"Unexpected enrollment_period type: {type(periods).__name__}"

        logger.info("Found %d enrollment period(s)", len(periods))
        return periods, None

    except Exception as e:
        logger.exception("Failed to fetch enrollment periods")
        return [], repr(e)


def find_eligibility(answers: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    url = f"{BASE_URL}/formTemplates/{FORM_TEMPLATE_ID}/findEligibility"
    payload = {
        "questionIdToAnswer": answers,
        "applicationType": "Explore",
    }
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return {"ineligibleSchools": []}, f"Unexpected response type: {type(data).__name__}"
        return data, None
    except Exception as e:
        logger.exception("Failed to check eligibility")
        return {"ineligibleSchools": []}, repr(e)


def load_school_catalog(dataset_path: str | Path) -> list[dict[str, Any]]:
    path = Path(dataset_path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected list in {dataset_path}")
    return rows


def serves_grade(row: dict[str, Any], target_grade_num: int) -> bool:
    grade_min = row.get("grade_min")
    grade_max = row.get("grade_max")

    if grade_min is not None and grade_max is not None:
        try:
            return int(grade_min) <= target_grade_num <= int(grade_max)
        except (TypeError, ValueError):
            pass

    grades_filter = row.get("grades_filter") or []
    if isinstance(grades_filter, list):
        normalized = {str(x).strip() for x in grades_filter}
        lookup = {
            -2: "3 yrs old (K0)",
            -1: "4 yrs old (K1)",
            0: "5 yrs old (K2)",
            1: "1",
            2: "2",
            3: "3",
            4: "4",
            5: "5",
            6: "6",
            7: "7",
            8: "8",
            9: "9",
            10: "10",
            11: "11",
            12: "12",
        }
        wanted = lookup.get(target_grade_num)
        if wanted:
            return wanted in normalized

    return False


# def is_bps_school(row: dict[str, Any]) -> bool:
#     return str(row.get("provider_type", "")).strip() == "Boston Public School"


def find_eligible_schools(
    grade_level: str,
    street_address: str,
    zip_code: str,
    city: str = "Boston",
    state: str = "MA",
    street_address_line2: str = "",
    home_language: str = "English",
    dataset_path: str = DEFAULT_DATASET_PATH,
    include_ineligible: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enrollment_period_name": None,
        "eligible_schools": [],
        "eligible_count": 0,
        "candidate_school_count": 0,
        "ineligible_count": 0,
        "matched_ineligible_count": 0,
        "eligible_provider_type_counts": {},
        "error": None,
    }

    grade_option_id = GRADE_TO_OPTION_ID.get(grade_level)
    if not grade_option_id:
        result["error"] = f"Invalid grade level '{grade_level}'."
        return result

    lang_option_id = LANGUAGE_TO_OPTION_ID.get(home_language)
    if not lang_option_id:
        for lang, lid in LANGUAGE_TO_OPTION_ID.items():
            if lang.lower() == home_language.lower():
                lang_option_id = lid
                break
    if not lang_option_id:
        lang_option_id = LANGUAGE_TO_OPTION_ID["Other"]

    periods, periods_error = get_enrollment_periods()
    if not periods:
        result["error"] = f"Could not fetch enrollment periods: {periods_error}"
        return result

    result["enrollment_period_name"] = periods[0].get("name", "Unknown")

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

    eligibility_result, eligibility_error = find_eligibility(answers)
    if eligibility_error:
        result["error"] = f"Eligibility API call failed: {eligibility_error}"
        return result

    ineligible_schools = eligibility_result.get("ineligibleSchools", [])
    ineligible_ids = {
        normalize_id(s.get("referenceId"))
        for s in ineligible_schools
        if s.get("referenceId") is not None
    }

    result["ineligible_count"] = len(ineligible_schools)

    all_rows = load_school_catalog(dataset_path)
    target_grade_num = grade_to_num(grade_level)

    candidate_schools = [
        row for row in all_rows
        # if is_bps_school(row) and serves_grade(row, target_grade_num)
        if serves_grade(row, target_grade_num)
    ]

    candidate_ids = {normalize_id(row.get("id")) for row in candidate_schools}
    matched_ineligible_ids = candidate_ids & ineligible_ids

    eligible_schools = []
    for row in candidate_schools:
        row_id = normalize_id(row.get("id"))
        if row_id not in matched_ineligible_ids:
            enriched = dict(row)
            enriched["eligibility_status"] = "eligible"
            eligible_schools.append(enriched)

    eligible_schools = sorted(eligible_schools, key=lambda s: str(s.get("school", "")).lower())

    result["candidate_school_count"] = len(candidate_schools)
    result["matched_ineligible_count"] = len(matched_ineligible_ids)
    result["eligible_schools"] = eligible_schools
    result["eligible_count"] = len(eligible_schools)
    provider_counts = Counter(str(s.get("provider_type", "")).strip() for s in eligible_schools)
    result["eligible_provider_type_counts"] = dict(provider_counts)

    if include_ineligible:
        result["ineligible_schools"] = ineligible_schools
        result["matched_ineligible_ids"] = sorted(matched_ineligible_ids)

    return result


TOOL_DEFINITION = {
    "type": "function",
    "name": "find_eligible_schools",
    "description": "Find eligible Boston Public Schools for a student based on grade, address, zip code, and home language. \
        Returns full school records from the catalog, including Boston Public Schools and non-BPS options when available.",
    "parameters": {
        "type": "object",
        "properties": {
            "grade_level": {
                "type": "string",
                "enum": ["K0", "K1", "K2", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
            },
            "street_address": {"type": "string"},
            "zip_code": {"type": "string"},
            "city": {"type": "string", "default": "Boston"},
            "state": {"type": "string", "default": "MA"},
            "street_address_line2": {"type": "string", "default": ""},
            "home_language": {"type": "string", "default": "English"},
        },
        "required": ["grade_level", "street_address", "zip_code"],
        "additionalProperties": False,
    },
}


def handle_tool_call(function_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if function_name == "find_eligible_schools":
        return find_eligible_schools(**args)
    raise ValueError(f"Unknown tool: {function_name}")


if __name__ == "__main__":
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

    print(json.dumps(example, indent=2))