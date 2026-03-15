"""
Boston School Finder — Chatbot core
====================================
Designed for Llama 3.1 8B Instruct.

Instead of native tool calling (which 8B models handle unreliably),
the model outputs a simple tag like:
    [TOOL: find_eligible_schools | grade_level=K2 | street_address=123 Main St | zip_code=02118]

Our code detects the tag, parses it, executes the query, and feeds
the results back for the model to summarize.

Two tools:
  1. find_eligible_schools — calls Avela API for eligible school IDs
  2. filter_based_on_preferences — filters/ranks eligible schools by user preferences
"""

import json
import re
from huggingface_hub import InferenceClient
from config import BASE_MODEL, MY_MODEL, HF_TOKEN
from data.database import BPSDatabase
from data.check_eligibility_tool import find_eligible_schools

# ────────────────────────────────────────────────────────────────
# CONSTANTS
# ────────────────────────────────────────────────────────────────
AGENT_NAME = "Boston School Finder"
MAX_TOOL_ROUNDS = 4          # max tool-call loops per user message
MAX_TOOL_RESULT_ITEMS = 15   # truncate large result lists
MAX_CLEAN_RETRIES = 2        # re-prompt attempts if output still has tags

MAX_ELIGIBLE_SCHOOLS_RETURNED = 5

# ────────────────────────────────────────────────────────────────
# SYSTEM PROMPT  — kept concise for 8B model
# ────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""\
You are {AGENT_NAME}, a friendly guide that helps parents in Boston \
find and register for schools.

Your core responsibilities are helping families
1. Find the right school for their child by \
    finding eligible schools and narrowing down school options based on preferences.
2. Understand the Boston Public Schools registration process.
3. Provide official resources when needed.

---

CORE RULES

- Never invent school information or eligibility rules.
- You know nothing about schools until a tool returns results.
- Never show raw JSON, tool output, or function names to the user.
- Do not call tools unless required information is available.
- If results are empty, explain why and suggest ways to adjust preferences.
- If the tool response includes a "notes" field, follow its instructions.
- If unsure about something, say so and provide official contact resources.
- Always end informational responses with a Source: line and link when possible.

---

**1. FINDING THE RIGHT SCHOOL**

Help families understand their options and narrow choices without choosing for them.

**Process:**
1. Collect eligibility information: child’s grade or age, home address, zip code, home language (if relevant).

2. Call `find_eligible_schools`. 
Respond ONLY with 
[TOOL: find_eligible_schools | grade_level=<grade> | street_address=<address> | zip_code=<zip>]

3. After eligibility results are returned:
   - state the number of eligible schools
   - summarize the option overview by explaining the main ways eligible schools may differ
   - suggest common factors families may care about, such as language programs, arts, sports, commute, care, accessibility, school type, and BPS vs non-BPS.
   
4. Ask about preferences:
   - must-have programs or services
   - interests (sports, arts, STEM, languages)
   - practical needs (care, accessibility, commute)

5. Call `filter_based_on_preferences` using structured filters when possible and query text for broader preferences.
Respond ONLY with 
[TOOL: filter_based_on_preferences | **args]

Result display guidelines:
- If more than 10 schools match: summarize patterns instead of listing them all.
- If 4–10 schools match: group them into categories.
- If 2–3 schools remain: show a side-by-side comparison.

7. If no schools satisfy all preferences:
   - explain which preferences conflict
   - suggest ways to relax or re-prioritize preferences.

6. Present results in helpful groups rather than a long list. Highlight key differences and trade-offs.

**Available Tools:**
Call a tool using format: [TOOL: function_name | arg1=value1 | arg2=value2]

1. `find_eligible_schools`
   Finds schools a student is eligible to attend based on grade, address, and language.\
   Results may include both Boston Public Schools and non-BPS schools.
   REQUIRED args: grade_level, street_address, zip_code
   OPTIONAL args: home_language (default English), city (default Boston), state (default MA)
   grade_level values: K0, K1, K2, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
   Returns:
    - eligible_count: number of eligible schools
    - sample_eligible_schools: sample list of at most {MAX_ELIGIBLE_SCHOOLS_RETURNED} eligible school records from catalog
    - eligible_provider_type_counts: counts by provider type

2. `filter_based_on_preferences`
   Filters and ranks the eligible schools by user preferences.
   The system automatically uses the school IDs from the most recent find_eligible_schools call.
   You do NOT need to pass school_ids — they are stored for you.
   OPTIONAL args:
     query=text              (natural language preference, e.g. "strong arts and music")
     top_k=int               (max results per category, default 10)
     ADA=1                   (ADA accessible)
     UPK=1                   (has Universal Pre-K)
     has_language_program=1   (has language/bilingual program)
     has_advanced_placement=1 (has AP courses)
     has_international_baccalaureate=1 (has IB program)
     special_admission=1     (exam/audition school)
     surround_care=1         (has before/after school care)
     accepts_ccfa=1          (accepts childcare financial assistance)
     headstart=1             (Head Start program)
     build_care=1            (has BuildCare)
     uniform=1               (requires uniform)
     tuition=1               (charges tuition)
     provider_type=text      (e.g. "Boston Public School", "Family Child Care")
     lat=float               (latitude for proximity search)
     lon=float               (longitude for proximity search)
     radius_miles=float      (search radius, default 1.0)
   Returns: bps_schools (list), non_bps_schools (list), bps_count, non_bps_count, notes

---

2. REGISTRATION PROCESS

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

3. CONTACT INFO 
Share when relevant or when you can't answer a question.

- BPS Welcome Centers: https://www.bostonpublicschools.org/enrollment/welcome-services/welcome-centers-locations
- Phone: 617-635-9010
- Registration info: https://www.bostonpublicschools.org/enrollment/welcome-services/registration
- School info sessions: https://www.bostonpublicschools.org/enrollment/welcome-services/school-information-sessions
- Info session schedule: https://drive.google.com/file/d/1M-fkgEs1gGrhA60-Yrc-rinfng14hnlV/view
- Eligibility map: https://boston.explore.avela.org/

---

SAFETY: Never invent facts. Never fabricate URLs. If unsure, say so and share \
the most relevant contact link above.
"""


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
        "find_eligible_schools", "filter_based_on_preferences",
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
        self._eligible_ids = None  # populated by find_eligible_schools, used by filter_based_on_preferences
        self._eligible_schools = []
        self._eligible_provider_type_counts = dict()

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


    def _clean_eligible_schools(self, eligible_schools):
        cleaned_eligible_schools = []
        for school in eligible_schools:
            cleaned_school = dict()
            for key, value in school.items():
                if value is not None and value != "":
                    cleaned_school[key] = value
            cleaned_eligible_schools.append(cleaned_school)

        return cleaned_eligible_schools
    
    # ── Tool execution ────────────────────────────────────────

    def _execute_tool(self, fn_name, args):
        """Dispatch a tool call. Returns JSON string."""
        try:
            if fn_name == "find_eligible_schools":
                print("[TOOL CALL] find_eligible_schools")
                
                if self._eligible_ids is None:
                    print("Executing find_eligible_schools")
                    result = find_eligible_schools(**args)
                    if result.get("error"):
                        return json.dumps({"error": result["error"]})
                    
                    # Store eligible IDs on the instance for filter_based_on_preferences
                    self._eligible_ids = [
                        str(s["id"]) for s in result.get("eligible_schools", [])
                    ]
                    self._eligible_schools = result.get("eligible_schools", [])
                    self._eligible_provider_type_counts = result.get("eligible_provider_type_counts",{})

                else:
                    print("already stored eligible schools")
                
                # small list of eligible schools for now
                sample_eligible_schools = self._eligible_schools
                if len(sample_eligible_schools) > MAX_ELIGIBLE_SCHOOLS_RETURNED:
                    sample_eligible_schools = sample_eligible_schools[:MAX_ELIGIBLE_SCHOOLS_RETURNED]
                # print(sample_eligible_schools)
                sample_eligible_schools = self._clean_eligible_schools(sample_eligible_schools)

                return json.dumps({
                    "eligible_count": len(self._eligible_ids),
                    "sample_eligible_schools": sample_eligible_schools,
                    "eligible_provider_type_counts": self._eligible_provider_type_counts
                })

            elif fn_name == "filter_based_on_preferences":
                print("[TOOL CALL] filter_based_on_preferences")
                if not self._eligible_ids:
                    return json.dumps({
                        "error": "No eligible schools found yet. Call find_eligible_schools first."
                    })
                result = self.db.filter_based_on_preferences(
                    self._eligible_ids, **args
                )
                return json.dumps(result, default=str)

            else:
                print("[TOOL CALL] unknown tool")
                return json.dumps({"error": f"Unknown tool: {fn_name}"})

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
                if fn_name == 'find_eligible_schools':
                    messages.append({
                        "role": "system",
                        "content": (
                            f"[DATA]\n{tool_output}\n\n"
                            f"The user asked to find eligible schools for their child.\n"
                            "Using ONLY the data above, state the number of eligible schools, "
                            "briefly categorize and summarize the school options visible in the preview,"
                            "and ask for user preferences on how to narrow down the options."
                            "Do NOT include any [TOOL:] tags, JSON, or code."
                        ),
                    })
                    print(messages[:-1])
                elif fn_name == 'filter_based_on_preferences':
                     messages.append({
                        "role": "system",
                        "content": (
                            f"[DATA]\n{tool_output}\n\n"
                            f"The user asked: \"{user_input}\"\n"
                            "Now write a helpful response to the user using ONLY "
                            "the data above. Explain the filtered school options, the main trade-offs, "
                            "and how the family could narrow further if needed."
                            "Do NOT include any [TOOL:] tags, JSON, or code."
                        ),
                    })
                else:
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