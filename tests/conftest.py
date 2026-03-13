"""
Pytest fixtures shared across all test modules.

Session-scoped to avoid reloading the embedding model and DB on every test.
"""

import os
import sys
import pytest
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root before anything else
load_dotenv(Path(__file__).parent.parent / ".env")

# Make project root and tests/ importable
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from data.database import BPSDatabase


# ── Database ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db():
    """BPSDatabase instance shared across the whole test session."""
    database = BPSDatabase()
    yield database
    database.close()


# ── Embedding model ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def embedding_model():
    """Sentence-Transformers model (all-MiniLM-L6-v2) — used for similarity."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture(scope="session")
def similarity_checker(embedding_model):
    """
    Returns a callable: similarity_checker(text_a, text_b) -> float in [-1, 1].

    Uses cosine similarity on normalized embeddings, so the range is [0, 1]
    for typical sentence pairs.
    """
    def _check(text_a: str, text_b: str) -> float:
        vecs = embedding_model.encode(
            [text_a, text_b], normalize_embeddings=True
        )
        return float(np.dot(vecs[0], vecs[1]))

    return _check


# ── Chatbot ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def chatbot():
    """
    Live Chatbot instance.

    Skipped automatically if HF_TOKEN is not set so that the data-layer
    tests (which don't need the model) can still run in CI / offline.
    """
    if not os.getenv("HF_TOKEN"):
        pytest.skip("HF_TOKEN not set — chatbot tests require model access")

    from src.chat import Chatbot
    return Chatbot()


# ── LLM-as-judge (OpenAI) ─────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "llm_judge: tests that call OpenAI GPT-4o as a judge (requires OPENAI_API_KEY)",
    )
    config.addinivalue_line(
        "markers",
        "chatbot: tests that require a live HuggingFace chatbot (requires HF_TOKEN)",
    )


@pytest.fixture(scope="session")
def openai_judge():
    """
    LLM-as-judge client. Tries Google Gemini first (free tier), then OpenAI.

    Set one of these in .env:
      GOOGLE_API_KEY=...   → uses gemini-2.0-flash-lite (free)
      OPENAI_API_KEY=...   → uses gpt-4o
    """
    from openai import OpenAI

    google_key = os.getenv("GOOGLE_API_KEY")
    if google_key:
        client = OpenAI(
            api_key=google_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        client._judge_model = "gemini-2.0-flash-lite"
        return client

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        client = OpenAI(api_key=openai_key)
        client._judge_model = "gpt-4o"
        return client

    pytest.skip("No GOOGLE_API_KEY or OPENAI_API_KEY set — skipping LLM-as-judge tests")
