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
print(type(result))
print(result.keys())
bps = [item for item in result['eligible_schools'] if item['provider_type']=='Boston Public School']

# what if we clean every row only only keep non-empty attributes
# print(bps)
print(json.dumps(bps, indent=2))