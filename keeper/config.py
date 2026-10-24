"""Runtime configuration. Everything is overridable by environment variable."""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("PP_CACHE_DIR", ROOT / "cache"))

# Fixed "today" so deadlines in the demo and the evaluation are reproducible.
AS_OF = date.fromisoformat(os.environ.get("PP_AS_OF", "2026-10-24"))

# LLM providers. "anthropic" uses the Anthropic SDK; every other provider is an OpenAI-compatible
# chat-completions endpoint. Keys come from the environment only. rpm = client-side request pacing
# (free tiers rate-limit hard); max_tokens = cap on the completion budget (Groq's free tier counts it
# against an 8K tokens-per-minute limit). Free-tier limits change often: check each provider's console.
PROVIDERS = {
    "anthropic": {"key_env": "ANTHROPIC_API_KEY"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY", "rpm": 30, "max_tokens": 4000},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key_env": "GEMINI_API_KEY", "rpm": 10},
    "cerebras": {"base_url": "https://api.cerebras.ai/v1", "key_env": "CEREBRAS_API_KEY", "rpm": 5},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY", "rpm": 20},
    # Any other OpenAI-compatible endpoint (GitHub Models, Mistral, NVIDIA NIM, ...).
    "custom": {"base_url": os.environ.get("PP_CUSTOM_BASE_URL", ""), "key_env": "PP_CUSTOM_API_KEY", "rpm": 10},
}
for _name, _p in PROVIDERS.items():
    _rpm = os.environ.get(f"PP_RPM_{_name.upper()}")
    if _rpm:
        _p["rpm"] = float(_rpm)
    _mt = os.environ.get(f"PP_MAX_TOKENS_{_name.upper()}")
    if _mt:
        _p["max_tokens"] = int(_mt)

# Model per stage, as "provider:model" (a bare "claude-..." id means Anthropic). Fast model for
# classification, stronger models for interpretation, drafting and verification.
#   anthropic : the original Claude setup (paid API)
#   free      : free API tiers, spread over three providers so no single daily quota runs out; the
#               verifier and the eval judge use different model families from the drafter.
PRESETS = {
    "anthropic": {
        "intake": "claude-haiku-5-5",
        "extract": "claude-sonnet-5-5",
        "interpret": "claude-opus-5-5",
        "draft": "claude-sonnet-5-5",
        "translate": "claude-sonnet-5-5",
        "verify": "claude-sonnet-5-5",
        "judge": "claude-opus-5-5",
        "ocr": "claude-sonnet-5-5",
    },
    "free": {
        "intake": "groq:openai/gpt-oss-20b",
        "extract": "gemini:gemini-3.8-flash",
        "interpret": "groq:openai/gpt-oss-120b",
        "draft": "cerebras:gpt-oss-120b",
        "translate": "gemini:gemini-3.8-flash",
        "verify": "gemini:gemini-3.8-flash",
        "judge": "cerebras:qwen-3.8-27b",
        "ocr": "gemini:gemini-3.8-flash",
    },
}
PRESET = os.environ.get("PP_MODELS") or ("anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "free")
MODELS = {stage: os.environ.get(f"PP_MODEL_{stage.upper()}", spec) for stage, spec in PRESETS[PRESET].items()}


def split_model(spec):
    """'groq:openai/gpt-oss-20b' -> ('groq', 'openai/gpt-oss-20b'); 'claude-sonnet-5-5' -> ('anthropic', ...)."""
    head, sep, rest = spec.partition(":")
    if sep and head in PROVIDERS:
        return head, rest
    return "anthropic", spec


def provider_key(provider):
    return os.environ.get(PROVIDERS[provider]["key_env"])


def keys_present():
    """Providers used by the configured models that have an API key set."""
    return sorted({p for p in (split_model(s)[0] for s in MODELS.values()) if provider_key(p)})


# live    : call the configured LLM APIs, cache every response on disk
# replay  : use cached responses only; on a cache miss fall back to the deterministic engine
# offline : never call an API; deterministic engine for every stage
MODE = os.environ.get("PP_MODE", "auto")
if MODE == "auto":
    MODE = "live" if keys_present() else "replay"

# USD per million tokens (input, output), Anthropic first-party list prices. Models not listed
# (free tiers) are metered at $0.
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
