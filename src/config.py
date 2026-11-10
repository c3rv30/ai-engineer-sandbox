"""Process configuration: loads .env once, before anything reads the environment.

Every module that reads the environment at import time imports this first (HYG-05).
Before, each one called load_dotenv() on its own, and router.py and extractor.py did
not: they built their Anthropic client without a key whenever they were imported before
the others, as a script or a worker does, and the first LLM call failed.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# The model of every LLM call in the system (DOC-07). Haiku: low latency and low cost,
# enough for routing, generation, extraction and evaluation.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
