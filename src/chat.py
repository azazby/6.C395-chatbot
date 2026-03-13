"""
Boston School Finder — Chatbot core
====================================
Designed for Llama 3.1 8B Instruct.

Instead of native tool calling (which 8B models handle unreliably),
the model outputs a simple tag like:
    [TOOL: search | grade=2 | provider_type=Boston Public School]

Our code detects the tag, parses it, executes the query against
BPSDatabase, and feeds the results back for the model to summarize.
"""

import json
import re
from huggingface_hub import InferenceClient
from config import BASE_MODEL, MY_MODEL, HF_TOKEN
from data.database import BPSDatabase
from data.check_eligibility import find_eligible_schools

# ────────────────────────────────────────────────────────────────
# CONSTANTS
# ────────────────────────────────────────────────────────────────
AGENT_NAME = "Boston School Finder"
MAX_TOOL_ROUNDS = 4          # max tool-call loops per user message
MAX_TOOL_RESULT_ITEMS = 15   # truncate large result lists
MAX_CLEAN_RETRIES = 2        # re-prompt attempts if output still has tags

# ────────────────────────────────────────────────────────────────
# SYSTEM PROMPT  — kept concise for 8B model
# ────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are {agent_name}, a friendly guide that helps parents in Boston \
find and register for schools.

TONE: Warm, professional, concise (3-6 sentences). Occasional emoji OK (📚🏫✅).

---

HOW TO LOOK UP SCHOOL DATA

When you need information from our school database, output ONLY a tool tag \
on its own line. Do NOT write anything else in that response — just the tag. \
The system will run the query and give you the results, then you respond.

Format:
[TOOL: function_name | arg1=value1 | arg2=value2]

Available functions and their arguments:

1. search | query=text | grade=int | provider_type=text | top_k=int | \
has_advanced_placement=1 | has_language_program=1 | surround_care=1 | ADA=1 | \
has_international_baccalaureate=1 | special_admission=1
   (Main search. Grade encoding: K0=-2, K1=-1, K2=0, 1-12 as integers.)

2. find_schools_by_grade | grade=int
   (List BPS schools for a grade.)

#TODO add find_eligibility

3. find_schools_by_age | age_months=int
   (List non-BPS programs for a child's age in months.)

4. semantic_search | query=text | top_k=int
   (Search school descriptions by topic, e.g. "strong arts and soccer".)

5. get_school_detail | school_id=text
   (Get full details for one school by its ID.)

6. get_all_provider_types
   (List all school/program categories.)

Examples:
[TOOL: search | grade=2 | provider_type=Boston Public School]
[TOOL: semantic_search | query=strong math and soccer program | top_k=5]
[TOOL: get_school_detail | school_id=bps-1234]
[TOOL: find_schools_by_grade | grade=7]
[TOOL: get_all_provider_types]

RULES:
- Output ONLY the [TOOL: ...] tag when you need data. No other text.
- NEVER invent school details. You know nothing about a school until you get results.
- After you receive results, respond to the user in plain friendly language. \
  Never show raw data, JSON, or tool tags in your response to the user.
- If results are empty, say so honestly and suggest next steps.
- Always end informational responses with a Source: line and link when possible.

---

BEFORE LOOKING UP SCHOOLS, ASK THESE QUESTIONS FIRST

You must collect this info from the user before calling a tool:
- What grade or age is the child?
- Are they looking for a Boston Public School specifically?
If they want school recommendations, also ask:
- What are the child's interests? (sports, subjects, programs, etc.)

Do NOT call a tool until you have the needed information. Ask one question at a time.

---

REGISTRATION PROCESS

When helping with registration, walk through these steps in order. Give each step one at a time. Do not give all the steps at once:

Step 1 — Grade Level
Ask what grade or age the child is?

After the user responds, use this table to confirm the grade is valid for their child's age (age as of Sep 1, 2026):
Age 3=K0, 4=K1, 5=K2, 6=1st, 7=2nd, 8=3rd, 9=4th, 10=5th, 11=6th, \
12=7th, 13=8th, 14=9th, 15=10th, 16=11th, 17=12th, 18-22=Overage
Source: https://www.bostonpublicschools.org/enrollment/welcome-services/registration

Step 2 — Special Admissions
Ask if they want a special admissions school. These have separate applications. Give some examples of what a special school is from the following list:
- Boston Arts Academy: https://bostonartsacademy.org/admissions
- Boston Day & Evening Academy: https://bdea.org/admissions/
- Boston Green Academy: https://www.bostongreenacademy.org/apply
- Dudley Street Neighborhood Charter: https://dsncs.schoolmint.com/login
- Fenway High School: https://www.fenwayhs.org/admissions.html
- Kennedy Academy for Health Careers: https://www.kennedyacademy.org/apps/pages/index.jsp?uREC_ID=87797&type=d&termREC_ID=&pREC_ID=166090&hideMenu=0
- New Mission High School: https://www.newmissionhigh.org/application-for-admission
- Madison Park: https://madisonpark.bostonpublicschools.org/admissions/admissions-process/
- UP Academy Dorchester: https://upacademy.schoolmint.net/welcome
Deadlines: https://drive.google.com/file/d/1gGyHPkABbLMNXd9rbUZ3I6MekU3F9zW0/view

Step 3 — Required Documents
Ask if they have these ready:
1. Child's birth certificate, I-94, or passport
2. Up-to-date immunization record
3. Physical exam record (within past year)
4. Parent/Guardian photo ID
5. Two proofs of Boston residency from different categories: utility bill, \
deed/mortgage, W-2/payroll stub, bank statement, government agency letter, or lease
(High school students should also bring their most recent transcript.)

If the user has any questions about these documents, provide help on where they could find them or point them towards the registration website and BPS Welcome Center contact for more help.

Step 4 — IEP
Ask if the child has an Individualized Education Program. 

If the user responds yes, tell them to have a copy ready when registering.

---

FINDING THE RIGHT SCHOOL

Step 1: Ask if they want BPS or non-BPS (childcare/preschool).
Step 2 (BPS): Tell them to check eligibility at https://boston.explore.avela.org/ \
and ask them to share their list of eligible schools.
Step 3: Ask about the child's interests (sports, academics, programs, practical needs).
Step 4: Use a tool to look up the schools, then recommend the top 5 with reasons.

---

CONTACT INFO (share when relevant or when you can't answer a question)

- BPS Welcome Centers: https://www.bostonpublicschools.org/enrollment/welcome-services/welcome-centers-locations
- Phone: 617-635-9010
- Registration info: https://www.bostonpublicschools.org/enrollment/welcome-services/registration
- School info sessions: https://www.bostonpublicschools.org/enrollment/welcome-services/school-information-sessions
- Info session schedule: https://drive.google.com/file/d/1M-fkgEs1gGrhA60-Yrc-rinfng14hnlV/view
- Eligibility map: https://boston.explore.avela.org/

---

SAFETY: Never invent facts. Never fabricate URLs. If unsure, say so and share \
the most relevant contact link above.
""".format(agent_name=AGENT_NAME)


# ────────────────────────────────────────────────────────────────
# CHATBOT CLASS
# ────────────────────────────────────────────────────────────────

class Chatbot:
    """
    Tag-based tool-calling chatbot designed for small (8B) models.

    The model outputs [TOOL: fn | arg=val] tags. Our code parses them,
    runs the query, and feeds results back as a system message.
    No native tool calling is used.
    """

    # All recognized tool names
    TOOL_NAMES = {
        "search", "find_schools_by_grade", "find_schools_by_age",
        "find_schools_near", "find_schools_by_provider_type",
        "find_schools_by_filters", "semantic_search",
        "get_school_detail", "get_all_provider_types",
    }

    # Regex to match [TOOL: function_name | arg=val | arg=val]
    TOOL_TAG_RE = re.compile(
        r'\[TOOL:\s*(\w+)'                      # function name
        r'((?:\s*\|\s*\w+=?[^|\]]*)*)'           # optional | arg=val pairs
        r'\s*\]',
        re.IGNORECASE
    )

    def __init__(self):
        model_id = MY_MODEL if MY_MODEL else BASE_MODEL
        self.client = InferenceClient(model=model_id, token=HF_TOKEN)
        self.db = BPSDatabase()

    # ── Parse [TOOL: ...] tags ────────────────────────────────

    @classmethod
    def _parse_tool_tag(cls, text):
        """
        Parse a [TOOL: fn_name | arg=val | ...] tag from text.

        Returns (fn_name, args_dict) or None.
        """
        if not text:
            return None

        match = cls.TOOL_TAG_RE.search(text)
        if not match:
            return None

        fn_name = match.group(1).strip().lower()
        if fn_name not in cls.TOOL_NAMES:
            return None

        raw_pairs = match.group(2).strip()
        args = {}

        if raw_pairs:
            for segment in raw_pairs.split("|"):
                segment = segment.strip()
                if not segment or "=" not in segment:
                    continue
                key, _, val = segment.partition("=")
                key = key.strip()
                val = val.strip()

                if not val or val.lower() in ("null", "none"):
                    continue

                # Try numeric conversion
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass  # keep as string

                args[key] = val

        return (fn_name, args)

    @classmethod
    def _has_tool_tag(cls, text):
        """Check if text contains a [TOOL: ...] tag."""
        return cls.TOOL_TAG_RE.search(text or "") is not None

    @classmethod
    def _strip_tool_tags(cls, text):
        """Remove [TOOL: ...] tags from text, keeping surrounding prose."""
        if not text:
            return ""
        cleaned = cls.TOOL_TAG_RE.sub("", text)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    @classmethod
    def _contains_artifacts(cls, text):
        """
        Check if text contains anything the user shouldn't see:
        tool tags, raw JSON blobs with tool names, function-call syntax.
        """
        if not text:
            return False

        if cls._has_tool_tag(text):
            return True

        tool_names_pat = "|".join(cls.TOOL_NAMES)
        patterns = [
            rf'\{{\s*"(?:name|function)"\s*:\s*"(?:{tool_names_pat})"',
            rf'"(?:arguments|parameters)"\s*:\s*\{{',
            r"<T>",
        ]
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return True
        return False

    # ── Tool execution ────────────────────────────────────────

    def _execute_tool(self, fn_name, args):
        """Dispatch a tool call to BPSDatabase. Returns JSON string."""
        try:
            if fn_name == "search":
                result = self.db.search(**args)
            elif fn_name == "find_schools_by_grade":
                result = self.db.find_schools_by_grade(**args)
            elif fn_name == "find_schools_by_age":
                result = self.db.find_schools_by_age(**args)
            elif fn_name == "find_schools_near":
                result = self.db.find_schools_near(**args)
            elif fn_name == "find_schools_by_provider_type":
                result = self.db.find_schools_by_provider_type(**args)
            elif fn_name == "find_schools_by_filters":
                result = self.db.find_schools_by_filters(**args)
            elif fn_name == "semantic_search":
                if "pre_filter_ids" in args and args["pre_filter_ids"] is not None:
                    args["pre_filter_ids"] = set(args["pre_filter_ids"])
                result = self.db.semantic_search(**args)
            elif fn_name == "get_school_detail":
                result = self.db.get_school_detail(**args)
            elif fn_name == "get_all_provider_types":
                result = self.db.get_all_provider_types()
            else:
                return json.dumps({"error": f"Unknown tool: {fn_name}"})

            if isinstance(result, list) and len(result) > MAX_TOOL_RESULT_ITEMS:
                total = len(result)
                result = result[:MAX_TOOL_RESULT_ITEMS]
                result.append({"_note": f"Showing {MAX_TOOL_RESULT_ITEMS} of {total} results"})

            return json.dumps(result, default=str)

        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Message building ──────────────────────────────────────

    def _build_messages(self, user_input, history=None):
        """
        Build messages list from Gradio history + current input.
        Handles both Gradio 3.x (pair lists) and 4.x (dict lists).
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if history:
            if isinstance(history[0], dict):
                for msg in history:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role in ("user", "assistant") and content:
                        messages.append({"role": role, "content": content})
            else:
                for user_msg, assistant_msg in history:
                    if user_msg:
                        messages.append({"role": "user", "content": user_msg})
                    if assistant_msg:
                        messages.append({"role": "assistant", "content": assistant_msg})

        messages.append({"role": "user", "content": user_input})
        return messages

    # ── Main response loop ────────────────────────────────────

    def get_response(self, user_input, history=None):
        """
        Generate a response to the user's message.

        Loop:
        1. Call model (no native tools — plain text generation).
        2. If output contains [TOOL: ...], parse + execute + inject
           results as a system message, then loop.
        3. If output is plain text, sanitize and return.
        """
        messages = self._build_messages(user_input, history)

        for _round in range(MAX_TOOL_ROUNDS):
            response = self.client.chat_completion(
                messages=messages,
                max_tokens=2048,
            )

            content = response.choices[0].message.content or ""

            # ── Check for [TOOL: ...] tag ────────────────────
            parsed = self._parse_tool_tag(content)
            if parsed:
                fn_name, fn_args = parsed

                tool_output = self._execute_tool(fn_name, fn_args)

                # Record the assistant's tool-tag turn
                messages.append({"role": "assistant", "content": content})

                # Feed results back as system context
                messages.append({
                    "role": "system",
                    "content": (
                        f"[DATABASE RESULTS]\n{tool_output}\n\n"
                        f"The user asked: \"{user_input}\"\n"
                        "Now write a helpful response to the user using ONLY "
                        "the data above. Use plain friendly language. "
                        "Do NOT include any [TOOL:] tags, JSON, or code."
                    ),
                })
                continue  # loop for the model's final answer

            # ── No tool tag — candidate final answer ─────────
            clean = self._clean_output(content)
            return self._sanitize(clean, messages, user_input)

        # ── Exhausted rounds — force a plain reply ───────────
        messages.append({
            "role": "system",
            "content": (
                "You must respond to the user now. Do not use any [TOOL:] tags. "
                "Answer using whatever information you have, or tell the user "
                "you need more details."
            ),
        })
        response = self.client.chat_completion(
            messages=messages,
            max_tokens=2048,
        )
        return self._clean_output(response.choices[0].message.content or "")

    # ── Output cleaning ───────────────────────────────────────

    @staticmethod
    def _clean_output(text):
        """Basic cleanup: strip leftover tags, whitespace."""
        if not text:
            return ""
        text = re.sub(r"^\s*<[RT]>\s*", "", text, count=1)
        return text.strip()

    def _sanitize(self, text, messages, user_input):
        """
        If final response still contains tool artifacts,
        re-prompt the model to rewrite cleanly.
        Falls back to stripping artifacts mechanically.
        """
        for _ in range(MAX_CLEAN_RETRIES):
            if not self._contains_artifacts(text):
                return text

            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "system",
                "content": (
                    "[REWRITE NEEDED] Your response contained [TOOL:] tags or "
                    "raw data the user cannot see. Rewrite as a plain friendly "
                    "message with no tags, no JSON, no code.\n"
                    f"The user asked: \"{user_input}\""
                ),
            })

            retry = self.client.chat_completion(
                messages=messages,
                max_tokens=2048,
            )
            text = self._clean_output(retry.choices[0].message.content or "")

        # Last resort: mechanically strip any remaining artifacts
        if self._contains_artifacts(text):
            text = self._strip_tool_tags(text)
            text = re.sub(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', '', text)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()

        return text if text else (
            "I'm sorry, I ran into a technical issue. Please try again, "
            "or contact a BPS Welcome Center at 617-635-9010 for help."
        )