# BPS Eligible School Tool

## Overview

This tool lets an LLM or backend service find **eligible Boston Public Schools** for a student based on:

- grade level
- home address
- ZIP code
- city/state
- home language

It uses the Boston Explore / Avela eligibility API to get the list of **ineligible** schools, then joins that result with our local school catalog and returns the remaining **eligible** BPS schools.

In other words:

```text
eligible schools = candidate BPS schools for the grade - ineligible schools returned by Avela
```

---

## Why this tool exists

The original `check_eligibility.py` script successfully called the Avela API, but it returned only the API's `ineligibleSchools` list.

That was not enough for the chatbot pipeline, because the chatbot needs a list of schools the student **can actually apply to**.

The new tool solves that by:

1. calling the eligibility API
2. loading the local school data
3. filtering to Boston Public Schools only
4. filtering to schools that serve the requested grade
5. subtracting ineligible schools
6. returning the final eligible school list

---

## Main file

The current tool implementation lives in:

```text
check_eligibility_tool.py
```

---

## Main function

```python
find_eligible_schools(
    grade_level: str,
    street_address: str,
    zip_code: str,
    city: str = "Boston",
    state: str = "MA",
    street_address_line2: str = "",
    home_language: str = "English",
    dataset_path: str = "raw_data/choice_tool_raw.json",
    include_ineligible: bool = False,
) -> dict[str, Any]
```

### What it returns

A dictionary with fields like:

```json
{
  "enrollment_period_name": "2026-2027 School Year",
  "eligible_schools": [...],
  "eligible_count": 16,
  "candidate_school_count": 73,
  "ineligible_count": 913,
  "matched_ineligible_count": 57,
  "error": null
}
```

### Important return fields

- `eligible_schools`: the final list the chatbot should use
- `eligible_count`: number of eligible schools returned
- `candidate_school_count`: number of BPS schools in the local dataset that serve the requested grade
- `ineligible_count`: total number of ineligible providers returned by Avela
- `matched_ineligible_count`: number of those ineligible providers that matched candidate BPS schools in our local dataset
- `error`: error message if something failed

---

## Tool definition for LLM function calling

The file exposes:

```python
TOOL_DEFINITION
```

This is the function schema the LLM can use to call the tool.

Tool name:

```text
find_eligible_schools
```

Expected user-facing parameters:

- `grade_level`
- `street_address`
- `zip_code`
- `city`
- `state`
- `street_address_line2`
- `home_language`

Note: `dataset_path` should stay internal and should **not** be exposed to the model in production.

---

## Minimal dispatcher

The file also exposes:

```python
handle_tool_call(function_name: str, args: dict[str, Any])
```

This makes it easy to plug into a future chatbot tool handler.

Example:

```python
args = {
    "grade_level": "K2",
    "street_address": "2300 Washington St",
    "zip_code": "02119",
    "city": "Boston",
    "state": "MA",
    "home_language": "English",
}

result = handle_tool_call("find_eligible_schools", args)
```

---

## Data sources used

### 1. Avela API

Used to determine which schools are **ineligible** for the student.

Endpoints used:

- `GET /enrollmentPeriods`
- `POST /formTemplates/{FORM_TEMPLATE_ID}/findEligibility`

### 2. Local dataset

Used to map API references back to school metadata and produce the final eligible list.

Current catalog path:

```text
raw_data/choice_tool_raw.json
```

This dataset includes more than just BPS schools, so the tool filters to:

```python
provider_type == "Boston Public School"
```

---

## Eligibility logic

The tool works in this order:

1. validate grade and language inputs
2. fetch enrollment periods
3. build the eligibility API payload
4. call Avela's `findEligibility`
5. collect `referenceId` values from `ineligibleSchools`
6. load the local catalog
7. filter the catalog to BPS schools that serve the requested grade
8. subtract matching ineligible school IDs
9. return the remaining schools as eligible

### Set logic

```text
candidate_ids = all BPS school IDs for the requested grade
matched_ineligible_ids = candidate_ids ∩ Avela_ineligible_ids
eligible_ids = candidate_ids - matched_ineligible_ids
```

---

## Testing

### Direct script test

Run:

```bash
python3 check_eligibility_tool.py
```

This runs an example address through the tool and prints the result.

### Manual tool-call test

Use `test_tool_call.py`:

```python
import json
import check_eligibility_tool
from check_eligibility_tool import TOOL_DEFINITION, handle_tool_call, get_enrollment_periods

print("Imported from:", check_eligibility_tool.__file__)
print("Tool name:", TOOL_DEFINITION["name"])

periods, periods_error = get_enrollment_periods()
print("Enrollment periods error:", periods_error)
print("Enrollment periods count:", len(periods))

args = {
    "grade_level": "K2",
    "street_address": "2300 Washington St",
    "zip_code": "02119",
    "city": "Boston",
    "state": "MA",
    "home_language": "English",
    "dataset_path": "raw_data/choice_tool_raw.json",
}

result = handle_tool_call("find_eligible_schools", args)
print(json.dumps(result, indent=2))
```

Run:

```bash
python3 test_tool_call.py
```

---

## Validation that the tool is correct

The tool was validated in a few ways:

### 1. Count math

For the tested input:

- `candidate_school_count = 73`
- `matched_ineligible_count = 57`
- `eligible_count = 16`

Check:

```text
73 - 57 = 16
```

### 2. Website comparison

The eligible school results matched the Boston Explore website for the tested address.

### 3. Join logic sanity

The tool only subtracts schools whose local `id` matches an Avela `referenceId` after normalization.

---

## Example tested input

```python
result = find_eligible_schools(
    grade_level="K2",
    street_address="2300 Washington St",
    zip_code="02119",
    city="Boston",
    state="MA",
    home_language="English",
    dataset_path="raw_data/choice_tool_raw.json",
    include_ineligible=False,
)
```

Observed result summary:

- enrollment period fetched successfully
- 73 candidate BPS schools for K2
- 57 matched as ineligible
- 16 eligible schools returned

---

## Known implementation details

### Enrollment periods response format

The Avela `enrollmentPeriods` endpoint may return a dictionary instead of a raw list.

The tool handles both of these cases:

- list response
- dict response containing `enrollment_period`

### UUID mappings

The grade and language option UUIDs must match the values from the original working `check_eligibility.py` implementation.

These mappings were preserved because the original script successfully returned working eligibility results.

---

## Recommended production usage

In production, the chatbot pipeline should work like this:

```text
User question
-> LLM extracts structured args
-> find_eligible_schools tool call
-> return eligible_schools
-> ranking/filtering/retrieval over eligible_schools
-> final chatbot answer
```

The chatbot should use:

```python
result["eligible_schools"]
```

as the input to ranking and school recommendation logic.

---

## Suggested follow-up improvements

1. Hide `dataset_path` from the LLM-facing tool interface.
2. Add optional debug mode for returning matched ineligible IDs.
3. Add unit tests for:
   - grade filtering
   - ID normalization
   - candidate minus ineligible set subtraction
4. Add ranking layer on top of `eligible_schools`.
5. Wrap the tool in the actual chatbot tool handler.

---

## Summary

This new tool converts the old “return ineligible schools” flow into a chatbot-ready “return eligible Boston Public Schools” flow.

It is now verified to:

- call the API correctly
- join against local school data correctly
- return eligible BPS schools correctly
- support LLM tool-calling via `TOOL_DEFINITION`
- support backend execution via `handle_tool_call`
