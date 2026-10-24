"""Runtime configuration. Everything is overridable by environment variable."""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("PP_CACHE_DIR", ROOT / "cache"))

# live    : call the Anthropic API, cache every response on disk
# replay  : use cached responses only; on a cache miss fall back to the deterministic engine
# offline : never call the API; deterministic engine for every stage
MODE = os.environ.get("PP_MODE", "auto")
if MODE == "auto":
    MODE = "live" if os.environ.get("ANTHROPIC_API_KEY") else "replay"

# Fixed "today" so deadlines in the demo and the evaluation are reproducible.
AS_OF = date.fromisoformat(os.environ.get("PP_AS_OF", "2026-10-24"))

# Model per stage: fast model for classification, stronger models for interpretation,
# drafting and verification.
MODELS = {
    "intake": os.environ.get("PP_MODEL_INTAKE", "claude-haiku-5-5"),
    "extract": os.environ.get("PP_MODEL_EXTRACT", "claude-sonnet-5-5"),
    "interpret": os.environ.get("PP_MODEL_INTERPRET", "claude-opus-5-5"),
    "draft": os.environ.get("PP_MODEL_DRAFT", "claude-sonnet-5-5"),
    "translate": os.environ.get("PP_MODEL_TRANSLATE", "claude-sonnet-5-5"),
    "verify": os.environ.get("PP_MODEL_VERIFY", "claude-sonnet-5-5"),
    "judge": os.environ.get("PP_MODEL_JUDGE", "claude-opus-5-5"),
}

# USD per million tokens (input, output), Anthropic first-party list prices.
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese (Brazilian)",
    "ht": "Haitian Creole",
    "vi": "Vietnamese",
    "zh": "Chinese (Simplified)",
}
