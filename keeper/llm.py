"""Thin Anthropic wrapper: structured JSON output, on-disk response cache, usage/cost accounting.

Privacy: document text is sent only to the Anthropic API call itself. Nothing is sent to any
other third-party service, and document contents are never written to logs (the on-disk cache
lives in ./cache, which is git-ignored and local to the laptop). Cache files are encrypted at rest
with keeper/crypto.py because responses can quote document text.
"""
import hashlib
import json
import threading
import time

from . import config, crypto


class LLMUnavailable(Exception):
    """Raised when a stage must fall back to its deterministic engine."""


_client = None
_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(max_retries=2, timeout=120)
    return _client


def _cache_path(key):
    d = config.CACHE_DIR / "llm"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def cost_usd(model, usage):
    pin, pout = config.PRICING.get(model, (0.0, 0.0))
    return (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1e6


def call_json(stage, system, user, schema, max_tokens=16000, effort="low", meter=None):
    """Return (parsed_json, info). info has model, cached, usage, cost, ms.

    Raises LLMUnavailable if the mode/cache/network does not allow a result.
    """
    model = config.MODELS[stage]
    payload = {"model": model, "system": system, "user": user, "schema": schema, "effort": effort}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:32]
    path = _cache_path(key)

    if path.exists():
        rec = crypto.read_json(path)
        info = {"model": model, "cached": True, "usage": rec["usage"], "cost": cost_usd(model, rec["usage"]),
                "ms": rec.get("ms", 0)}
        if meter is not None:
            meter.append(info)
        return rec["data"], info

    if config.MODE != "live":
        raise LLMUnavailable(f"{config.MODE} mode and no cached response")

    t0 = time.time()
    try:
        resp = _get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
    except Exception as e:  # network, auth, rate limit: the pipeline degrades to deterministic
        raise LLMUnavailable(f"API error: {type(e).__name__}: {e}")
    ms = int((time.time() - t0) * 1000)

    if resp.stop_reason in ("refusal", "max_tokens"):
        raise LLMUnavailable(f"stop_reason={resp.stop_reason}")
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), None)
    if text is None:
        raise LLMUnavailable("no text block in response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"invalid JSON: {e}")

    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    with _lock:
        crypto.write_json(path, {"data": data, "usage": usage, "ms": ms, "model": model})
    info = {"model": model, "cached": False, "usage": usage, "cost": cost_usd(model, usage), "ms": ms}
    if meter is not None:
        meter.append(info)
    return data, info
