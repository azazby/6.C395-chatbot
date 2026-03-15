import json
from src.chat import Chatbot

bot = Chatbot()
print(bot._execute_tool("find_eligible_schools", {
    "grade_level": "1",
    "street_address": "2300 Washington St",
    "zip_code": "02119",
    "home_language": "English"
}))