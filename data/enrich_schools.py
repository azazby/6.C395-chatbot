#!/usr/bin/env python3
"""
BPS School Data Enricher
=========================
Scrapes additional school details from BPS website and Mass DESE profiles.
Run this to populate the school_descriptions.json with richer data.

Usage:
    python enrich_schools.py                # Enrich all schools
    python enrich_schools.py --school 1010  # Enrich specific school by ID

This script fetches:
- School descriptions and mission statements
- Program offerings (language, SPED, CTE, arts)
- Contact info (phone, email, principal)
- Hours and transportation info

After running, rebuild the vector store:
    python build_database.py --vector-only
"""

import json
import re
import time
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser

RAW_DIR = Path(__file__).parent / "raw_data"
ENRICHED_JSON = RAW_DIR / "school_descriptions.json"


class SimpleHTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML."""
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_tags = {'script', 'style', 'noscript'}
        self._skip = False
    
    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self._skip = True
    
    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self._skip = False
    
    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.result.append(text)
    
    def get_text(self):
        return ' '.join(self.result)


def fetch_page(url: str, timeout: int = 10) -> str:
    """Fetch a web page and return its text content."""
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0 BPS-Chatbot-Research'})
        with urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='replace')
            parser = SimpleHTMLTextExtractor()
            parser.feed(html)
            return parser.get_text()
    except (HTTPError, URLError, Exception) as e:
        print(f"  Error fetching {url}: {e}")
        return ""


def extract_school_info(text: str, school_name: str) -> dict:
    """Extract structured information from school page text."""
    info = {}
    text_lower = text.lower()
    
    # Look for phone numbers
    phone_match = re.search(r'\(617\)\s*\d{3}[-.]?\d{4}|617[-.]?\d{3}[-.]?\d{4}', text)
    if phone_match:
        info['phone'] = phone_match.group()
    
    # Look for language programs
    languages = []
    lang_keywords = {
        'spanish': 'Spanish', 'french': 'French', 'mandarin': 'Mandarin Chinese',
        'cantonese': 'Cantonese', 'latin': 'Latin', 'portuguese': 'Portuguese',
        'haitian creole': 'Haitian Creole', 'cape verdean': 'Cape Verdean Creole',
        'arabic': 'Arabic', 'vietnamese': 'Vietnamese', 'chinese': 'Chinese',
        'italian': 'Italian', 'somali': 'Somali',
    }
    for kw, name in lang_keywords.items():
        if kw in text_lower:
            languages.append(name)
    if languages:
        info['languages'] = list(set(languages))
    
    # Look for special programs
    programs = []
    program_keywords = {
        'montessori': 'Montessori', 'dual language': 'Dual Language',
        'bilingual': 'Bilingual Education', 'stem': 'STEM',
        'arts integration': 'Arts Integration', 'pilot school': 'Pilot School',
        'inclusion': 'Inclusive Education', 'ib ': 'International Baccalaureate',
        'advanced placement': 'Advanced Placement', 'ap courses': 'Advanced Placement',
        'career and technical': 'Career and Technical Education',
        'early college': 'Early College', 'vocational': 'Vocational/Technical',
        'project-based': 'Project-Based Learning',
    }
    for kw, name in program_keywords.items():
        if kw in text_lower:
            programs.append(name)
    if programs:
        info['programs'] = list(set(programs))
    
    return info


def enrich_from_dese(sch_id: int) -> dict:
    """
    Fetch school profile from Mass DESE (Dept of Elementary & Secondary Ed).
    Example URL: https://profiles.doe.mass.edu/profiles/student.aspx?orgcode=00350000&orgtypecode=6&leftNavId=300&
    """
    # DESE org codes for BPS schools follow a pattern
    # This is a placeholder - you'd need to map SCH_ID to DESE org codes
    return {}


def load_existing() -> dict:
    """Load existing enriched descriptions."""
    if ENRICHED_JSON.exists():
        with open(ENRICHED_JSON) as f:
            return json.load(f)
    return {}


def save_enriched(data: dict):
    """Save enriched descriptions."""
    with open(ENRICHED_JSON, 'w') as f:
        json.dump(data, f, indent=2)


def enrich_school(sch_id: str, sch_name: str, existing: dict) -> dict:
    """Enrich a single school's data."""
    info = existing.get(sch_id, {})
    
    # Try BPS school website 
    # BPS school pages follow pattern: https://www.bostonpublicschools.org/school/SCHOOLNAME
    # but URLs vary — you may need to manually map some
    
    # Try the Discover BPS page
    discover_url = f"https://discover.bostonpublicschools.org/school/{sch_id}"
    print(f"  Fetching Discover BPS page for {sch_name} (ID: {sch_id})...")
    text = fetch_page(discover_url)
    
    if text:
        scraped = extract_school_info(text, sch_name)
        # Merge without overwriting existing curated data
        for key, value in scraped.items():
            if key not in info:
                info[key] = value
    
    return info


def main():
    import sqlite3
    
    db_path = Path(__file__).parent / "bps_schools.db"
    if not db_path.exists():
        print("Database not found. Run build_database.py first.")
        sys.exit(1)
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    existing = load_existing()
    
    # Get target school(s)
    if len(sys.argv) > 2 and sys.argv[1] == '--school':
        target_id = sys.argv[2]
        cur = conn.execute("SELECT sch_id, sch_name FROM schools WHERE sch_id = ?", (target_id,))
    else:
        cur = conn.execute("SELECT sch_id, sch_name FROM schools ORDER BY sch_id")
    
    schools = cur.fetchall()
    print(f"Enriching {len(schools)} schools...")
    
    for school in schools:
        sch_id = str(school['sch_id'])
        sch_name = school['sch_name']
        
        print(f"\n[{sch_id}] {sch_name}")
        info = enrich_school(sch_id, sch_name, existing)
        
        if info:
            existing[sch_id] = info
            print(f"  -> {len(info)} fields")
        
        time.sleep(0.5)  # Be polite to servers
    
    save_enriched(existing)
    print(f"\nSaved enriched data for {len(existing)} schools to {ENRICHED_JSON}")
    print("Now rebuild vector store: python build_database.py --vector-only")
    
    conn.close()


if __name__ == "__main__":
    main()
