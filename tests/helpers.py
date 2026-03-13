"""
Shared assertion helpers for BPS chatbot evaluation tests.

All helpers accept a response string and return a bool or numeric value.
Use them inside test functions with plain `assert` statements so pytest
gives a clean failure message.
"""

import re
from typing import List


def contains_any(response: str, keywords: List[str]) -> bool:
    """Return True if response contains at least one keyword (case-insensitive)."""
    lower = response.lower()
    return any(kw.lower() in lower for kw in keywords)


def contains_all(response: str, keywords: List[str]) -> bool:
    """Return True if response contains every keyword (case-insensitive)."""
    lower = response.lower()
    return all(kw.lower() in lower for kw in keywords)


def contains_question(response: str) -> bool:
    """Return True if the response contains at least one question mark."""
    return "?" in response


def count_school_names(response: str, known_schools: List[str]) -> int:
    """
    Count how many school names from known_schools appear in response.
    Matching is case-insensitive.
    """
    lower = response.lower()
    return sum(1 for school in known_schools if school.lower() in lower)


def has_numbered_list(response: str) -> bool:
    """
    Return True if response contains a numbered list item like:
    '1.' or '1)' at the start of a line (ignoring leading whitespace).
    """
    return bool(re.search(r'^\s*\d+[.)]\s+\S', response, re.MULTILINE))


def has_bulleted_list(response: str) -> bool:
    """Return True if response contains a bullet point (-, *, •) list item."""
    return bool(re.search(r'^\s*[-*•]\s+\S', response, re.MULTILINE))


def has_list(response: str) -> bool:
    """Return True if response has either a numbered or bulleted list."""
    return has_numbered_list(response) or has_bulleted_list(response)


def schools_overlap(response: str, db_results: list, min_overlap: int = 1) -> bool:
    """
    Return True if at least min_overlap schools from db_results appear in response.

    db_results should be the list returned by BPSDatabase methods; each item
    is a dict with a 'school' key.
    """
    lower = response.lower()
    matched = sum(
        1 for r in db_results
        if isinstance(r, dict) and r.get("school", "").lower() in lower
    )
    return matched >= min_overlap


def not_gatekeeping(response: str) -> bool:
    """
    Return True if response does NOT refuse to help without an address.
    Catches patterns like "I can't help without your address" or
    "need your address to" etc.
    """
    gatekeep_patterns = [
        r"can'?t help without.{0,20}address",
        r"need.{0,20}address.{0,20}(first|before|to)",
        r"(without|unless).{0,30}address",
        r"provide.{0,20}address.{0,20}(first|before)",
    ]
    lower = response.lower()
    return not any(re.search(p, lower) for p in gatekeep_patterns)


def no_specific_school_recommendation(response: str, known_schools: List[str]) -> bool:
    """
    Return True if response does NOT mention specific school names.
    Used for Partition 1: the bot should NOT recommend schools when
    eligibility is unknown.
    """
    lower = response.lower()
    return not any(school.lower() in lower for school in known_schools)


def asks_about_grade_or_age(response: str) -> bool:
    """Return True if response asks about grade level or child's age."""
    patterns = [
        r'grade',
        r'\bage\b',
        r'year.{0,5}old',
        r'how old',
        r'kindergarten|k-\d|grade \d',
    ]
    lower = response.lower()
    return any(re.search(p, lower) for p in patterns)


def count_recommended_schools(response: str, known_schools: List[str]) -> int:
    """Count how many known school names appear in the response."""
    return count_school_names(response, known_schools)


def references_specific_attributes(response: str) -> bool:
    """
    Return True if the response references concrete school attributes
    like language programs, after-school care, uniforms, AP, IB, etc.
    """
    attribute_keywords = [
        "language", "spanish", "bilingual", "immersion",
        "after.?school", "surround care",
        "uniform", "no uniform",
        "advanced placement", r"\bap\b",
        "international baccalaureate", r"\bib\b",
        "arts", "stem", "math", "science",
        "special education", "ada",
    ]
    lower = response.lower()
    return any(re.search(kw, lower) for kw in attribute_keywords)
