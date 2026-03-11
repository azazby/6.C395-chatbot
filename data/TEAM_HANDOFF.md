# Team Handoff: Data Layer is Done — Here's How to Use It

## What's Built

Two data stores that work together for the chatbot:

1. **SQLite database** (`bps_schools.db`) — 131 BPS schools with structured fields: name, address, lat/lon, grade range, school type, neighborhood. This powers **hard filtering** (e.g., "what schools can my 3rd grader attend within 1 mile of my house?").

2. **FAISS vector store** (`vector_store/school_index.faiss`) — Every school has a text description embedded as a 384-dim vector. This powers **soft filtering / RAG** (e.g., "I want a school with strong arts programs" or "bilingual Spanish immersion").

The two layers combine: hard filter narrows to eligible schools, then semantic search ranks them by the user's preferences.

## How to Use in the Chatbot

Everything goes through one class. Import it:

```python
from build_database import BPSDatabase

db = BPSDatabase()
```

### Three main methods:

**1. Hard filter only** — when the user gives concrete constraints:
```python
# "What schools serve 3rd grade in Dorchester?"
results = db.hard_filter(grade=3, neighborhood="Dorchester")

# "Schools within 1 mile of my home"
results = db.hard_filter(grade=1, lat=42.35, lon=-71.06, radius_miles=1.0)
```

**2. Semantic search only** — when the user asks something fuzzy:
```python
# "What schools have bilingual Spanish programs?"
results = db.semantic_search("bilingual Spanish dual language", top_k=5)
```

**3. Combined search** — hard filter first, then rank by semantic match (this is the main one to use):
```python
# "My kid is entering 6th grade near Jamaica Plain and loves art"
results = db.search(
    query="arts programs visual arts music",
    grade=6,
    neighborhood="Jamaica Plain",
    top_k=5
)
```

Each result is a dict with: `sch_id`, `sch_name`, `score`, `description`, `distance_miles` (if location was provided), and `metadata`.

### Getting full school details:
```python
school = db.get_school_detail(1010)  # Returns full row for Boston Latin School
```

### Helper methods:
```python
db.get_all_neighborhoods()   # List of all neighborhoods
db.get_all_school_types()    # List of (type_code, type_description) tuples
```

## Grade Encoding

When the user says a grade, convert it to an integer:

| User says | Pass as |
|-----------|---------|
| K0 / Pre-K | `-2` |
| K1 / Kindergarten | `-1` |
| K2 | `0` |
| 1st grade | `1` |
| ... | ... |
| 12th grade | `12` |

## What the Chatbot Needs to Do

The LLM (via the Anthropic API or whatever model you're using) should:

1. **Parse the user's message** to extract:
   - Grade level (hard filter)
   - Location / neighborhood / address (hard filter — you'll need geocoding for addresses)
   - School type preference (hard filter)
   - Soft preferences like "arts", "STEM", "bilingual", "small school" (soft filter)

2. **Call `db.search()`** with the extracted parameters

3. **Format the results** into a natural language response with school names, addresses, why they match, etc.

4. **Use the `description` field** from results as RAG context — feed it into the LLM prompt so it can give specific, accurate answers about each school.

## Example Chatbot Flow

```
User: "I'm looking for a school for my daughter entering kindergarten. 
       We live in East Boston and she speaks Spanish at home."

Bot extracts:
  - grade = -1  (K1)
  - neighborhood = "East Boston"
  - query = "Spanish bilingual language"

Bot calls:
  db.search(query="Spanish bilingual language", grade=-1, 
            neighborhood="East Boston", top_k=5)

Bot gets back schools like:
  - Alighieri Montessori (bilingual programs)
  - East Boston EEC
  - Guild Elementary
  - etc.

Bot responds with a friendly summary of the options.
```

## File Structure

```
chatbot/
├── build_database.py          # BPSDatabase class — import this
├── enrich_schools.py          # (Optional) scraper to add more school data
├── bps_schools.db             # SQLite database (don't edit directly)
├── raw_data/
│   ├── public_schools.csv     # Source data (131 schools)
│   └── school_descriptions.json  # Enriched descriptions (programs, languages, etc.)
├── vector_store/
│   ├── school_index.faiss     # FAISS vector index
│   ├── documents.json         # Text descriptions
│   └── metadata.json          # Structured metadata
└── app.py                     # ← YOUR GRADIO CHATBOT GOES HERE
```

## Setup for New Team Members

```bash
cd chatbot
uv venv bps_env
source bps_env/bin/activate
uv pip install faiss-cpu sentence-transformers pandas numpy gradio
```

The database and vector store are already built (committed to the repo), so teammates don't need to run `build_database.py` unless they change the source data.

## For HuggingFace Spaces Deployment

Your `requirements.txt` should include:
```
faiss-cpu
sentence-transformers
pandas
numpy
gradio
```

Bundle `bps_schools.db`, `vector_store/`, `raw_data/`, and `build_database.py` in the Space repo alongside your `app.py`.

## Geocoding (Nice to Have)

If you want to let users type an address instead of a neighborhood, you'll need geocoding to get lat/lon. Options:
- **geopy** (`pip install geopy`) — uses free Nominatim/OpenStreetMap
- **Google Maps Geocoding API** — more accurate but needs API key
- Or just ask users for their neighborhood/zip code to keep it simple

## What's NOT in the Data Yet

- Exact walk zone boundaries (we approximate with 1-mile radius)
- Transportation eligibility rules (complex, depends on grade + distance)
- School capacity / available seats
- MCAS scores / accountability ratings
- Detailed school hours
- Before/after school program details (we have some, not all)

These could be added to `school_descriptions.json` and the vector store rebuilt.
