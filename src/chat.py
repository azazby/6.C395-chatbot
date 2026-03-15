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
from config import BASE_MODEL, MY_MODEL, HF_TOKEN, SYSTEM_PROMPT, MAX_ELIGIBLE_SCHOOLS_RETURNED, SYSTEM_PROMPT_FIND, SYSTEM_PROMPT_REG, SYSTEM_PROMPT_CONTACT
from data.database import BPSDatabase
from data.check_eligibility_tool import find_eligible_schools

# ────────────────────────────────────────────────────────────────
# CONSTANTS
# ────────────────────────────────────────────────────────────────
MAX_TOOL_ROUNDS = 4          # max tool-call loops per user message
MAX_TOOL_RESULT_ITEMS = 15   # truncate large result lists
MAX_CLEAN_RETRIES = 2        # re-prompt attempts if output still has tags

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

                # find_eligible_school requires arguments to be strings
                # # Try numeric conversion
                # try:
                #     val = int(val)
                # except ValueError:
                #     try:
                #         val = float(val)
                #     except ValueError:
                #         pass  # keep as string

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

    def _build_messages(self, user_input, history=None, mode="Find School"):
        """
        Build messages list from Gradio history + current input.
        Handles both Gradio 3.x (pair lists) and 4.x (dict lists).
        """
        prompt_map = {
            "Find School": SYSTEM_PROMPT_FIND,
            "Registration Guide": SYSTEM_PROMPT_REG,
            "Contact Info": SYSTEM_PROMPT_CONTACT
        }
        
        # Get the right prompt, defaulting to FIND if something goes wrong
        active_system_prompt = prompt_map.get(mode, SYSTEM_PROMPT_FIND)

        messages = [{"role": "system", "content": active_system_prompt}]

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

    def get_response(self, user_input, history=None, mode="Find School"):
        """
        Generate a response to the user's message.

        Loop:
        1. Call model (no native tools — plain text generation).
        2. If output contains [TOOL: ...], parse + execute + inject
           results, then loop.
        3. If output is plain text, sanitize and return.
        """
        messages = self._build_messages(user_input, history, mode)

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
                        "role": "user",
                        "content": (
                            f"System Observation: Data from database: \n{tool_output}\n\n"
                            "Using ONLY the data above, state the number of eligible schools, "
                            "briefly categorize and summarize the sample school options visible,"
                            "and ask for user preferences on how to narrow down the options."
                            "Do NOT include any [TOOL:] tags, JSON, or code."
                        ),
                    })
                elif fn_name == 'filter_based_on_preferences':
                     messages.append({
                        "role": "user",
                        "content": (
                            f"System Observation: Data from database: \n{tool_output}\n\n"
                            "Now respond to my previous message with a helpful response using ONLY "
                            "the data above. Explain the filtered school options, the main trade-offs, "
                            "and I could narrow further if needed."
                            "Do NOT include any [TOOL:] tags, JSON, or code."
                        ),
                    })
                continue  # loop for the model's final answer

            # ── No tool tag — candidate final answer ─────────
            clean = self._clean_output(content)
            print(messages)
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
        
        # Strip the reasoning block (everything between <think> and </think>)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

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