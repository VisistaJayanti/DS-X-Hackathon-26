"""LLM wrapper: structured JSON output, on-disk response cache, usage/cost accounting.

Each stage's model is "provider:model" (config.MODELS): Anthropic through its SDK, or any OpenAI-compatible
endpoint (Groq, Gemini, Cerebras, OpenRouter, custom). Free providers don't all enforce JSON schemas, so
every response is checked against the stage's schema here; one that doesn't fit raises LLMUnavailable and
the stage falls back to its deterministic engine.

Privacy: document text is sent only to the configured provider's API call itself. Free tiers may retain
prompts or use them for training, so use them with synthetic data only. Document contents are never
written to logs (the on-disk cache lives in ./cache, which is git-ignored and local to the laptop).
"""
import base64
import hashlib
import json
import re
import threading
import time

from . import config


class LLMUnavailable(Exception):
    """Raised when a stage must fall back to its deterministic engine."""


_clients = {}
_lock = threading.Lock()
_pace = {}
_no_schema = set()  # (provider, model) that rejected JSON-schema mode; skip straight to JSON-object mode

# Providers/models that accept reasoning_effort; sending it elsewhere is a 400.
REASONING = {"groq": lambda m: "gpt-oss" in m, "gemini": lambda m: True}


def _get_client(provider="anthropic"):
    with _lock:
        if provider not in _clients:
            if provider == "anthropic":
                import anthropic

                _clients[provider] = anthropic.Anthropic(max_retries=2, timeout=120)
            else:
                from openai import OpenAI

                p = config.PROVIDERS[provider]
                if not p.get("base_url"):
                    raise LLMUnavailable(f"no base URL configured for provider {provider!r}")
                _clients[provider] = OpenAI(base_url=p["base_url"], api_key=config.provider_key(provider), max_retries=4,
                                            timeout=120)
        return _clients[provider]


def _wait_turn(provider):
    """Space requests to stay under the provider's requests-per-minute limit."""
    rpm = config.PROVIDERS[provider].get("rpm")
    if not rpm:
        return
    with _lock:
        lk, slot = _pace.setdefault(provider, (threading.Lock(), [0.0]))
    with lk:
        now = time.time()
        if slot[0] > now:
            time.sleep(slot[0] - now)
        slot[0] = max(now, slot[0]) + 60.0 / rpm


def _cache_path(key):
    d = config.CACHE_DIR / "llm"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def cost_usd(model, usage):
    pin, pout = config.PRICING.get(model, (0.0, 0.0))
    return (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1e6


# ------------------------------------------------------------------ schema handling
def _portable(schema):
    """Copy of the schema that OpenAI-style strict validators accept: an enum allowing null becomes anyOf."""
    if isinstance(schema, list):
        return [_portable(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    s = {k: _portable(v) for k, v in schema.items()}
    if isinstance(s.get("enum"), list) and None in s["enum"]:
        types = s.get("type") if isinstance(s.get("type"), list) else [s.get("type")]
        types = [t for t in types if t not in (None, "null")] or ["string"]
        rest = {k: v for k, v in s.items() if k not in ("type", "enum")}
        return dict(rest, anyOf=[{"type": types[0] if len(types) == 1 else types, "enum": [e for e in s["enum"] if e is not None]},
                                 {"type": "null"}])
    return s


def _types(schema):
    t = schema.get("type")
    return t if isinstance(t, list) else [t] if t else []


def _nullable(schema):
    return ("null" in _types(schema) or any(_nullable(a) for a in schema.get("anyOf", []))
            or None in (schema.get("enum") or []))


def _conform(value, schema, path="$"):
    """Check value against the JSON Schema subset the stages use and return a normalised copy.

    Smaller models often omit nullable fields or add extra keys: a missing required field whose schema
    allows null is filled with None, and keys an object doesn't declare are dropped. Anything else that
    doesn't fit raises LLMUnavailable."""
    if "anyOf" in schema:
        for alt in schema["anyOf"]:
            try:
                return _conform(value, alt, path)
            except LLMUnavailable:
                pass
        raise LLMUnavailable(f"schema mismatch at {path}")
    types = _types(schema)
    if value is None:
        if _nullable(schema):
            return None
        raise LLMUnavailable(f"schema mismatch at {path}: null")
    if "enum" in schema and value not in schema["enum"]:
        raise LLMUnavailable(f"schema mismatch at {path}: {value!r} not allowed")
    if "object" in types and isinstance(value, dict):
        props, out = schema.get("properties", {}), {}
        for k, sub in props.items():
            if k in value:
                out[k] = _conform(value[k], sub, f"{path}.{k}")
            elif k in schema.get("required", []):
                if not _nullable(sub):
                    raise LLMUnavailable(f"schema mismatch at {path}: missing {k!r}")
                out[k] = None
        if schema.get("additionalProperties", True) is not False:
            out.update({k: v for k, v in value.items() if k not in props})
        return out
    if "array" in types and isinstance(value, list):
        return [_conform(v, schema.get("items", {}), f"{path}[{i}]") for i, v in enumerate(value)]
    if "string" in types and isinstance(value, str):
        return value
    if "boolean" in types and isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "integer" in types and float(value).is_integer():
            return int(value)
        if "number" in types:
            return value
    if not types:
        return value
    raise LLMUnavailable(f"schema mismatch at {path}: expected {'/'.join(types)}")


def _parse(text):
    t = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S)
    if m:
        t = m.group(1)
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"invalid JSON: {e}")


# ------------------------------------------------------------------ providers
def _anthropic(model, system, user, schema, max_tokens, effort):
    resp = _get_client("anthropic").messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise LLMUnavailable(f"stop_reason={resp.stop_reason}")
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), None)
    if text is None:
        raise LLMUnavailable("no text block in response")
    return text, {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}


def _openai_compat(provider, model, system, user, schema, max_tokens, effort):
    """Try strict JSON-schema mode; if the provider/model rejects it (HTTP 400), retry in JSON-object mode
    with the schema in the prompt. _conform() checks the result either way."""
    from openai import BadRequestError

    client = _get_client(provider)
    cap = config.PROVIDERS[provider].get("max_tokens")
    base = {"model": model, "max_tokens": min(max_tokens, cap) if cap else max_tokens}
    schema_mode = dict(base, response_format={"type": "json_schema",
                                              "json_schema": {"name": "output", "strict": True, "schema": _portable(schema)}})
    if REASONING.get(provider, lambda m: False)(model):
        schema_mode["reasoning_effort"] = effort
    attempts = [
        (schema_mode, system),
        (dict(base, response_format={"type": "json_object"}),
         system + "\n\nRespond with a single JSON object that matches this JSON Schema exactly:\n" + json.dumps(schema)),
    ]
    if (provider, model) in _no_schema:
        attempts = attempts[1:]
    last = None
    for req, sys_text in attempts:
        _wait_turn(provider)
        try:
            resp = client.chat.completions.create(
                messages=[{"role": "system", "content": sys_text}, {"role": "user", "content": user}], **req)
        except BadRequestError as e:
            last = e
            if req is schema_mode:
                _no_schema.add((provider, model))
            continue
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise LLMUnavailable("finish_reason=length")
        u = resp.usage
        return choice.message.content, {"input_tokens": getattr(u, "prompt_tokens", 0) or 0,
                                        "output_tokens": getattr(u, "completion_tokens", 0) or 0}
    raise LLMUnavailable(f"API error: {type(last).__name__}: {last}")


def _ready(spec):
    provider, model = config.split_model(spec)
    if not config.provider_key(provider):
        raise LLMUnavailable(f"{config.PROVIDERS[provider]['key_env']} not set")
    return provider, model


def call_json(stage, system, user, schema, max_tokens=16000, effort="low", meter=None):
    """Return (parsed_json, info). info has model, cached, usage, cost, ms.

    Raises LLMUnavailable if the mode/cache/network/response does not allow a result.
    """
    model = config.MODELS[stage]
    payload = {"model": model, "system": system, "user": user, "schema": schema, "effort": effort}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:32]
    path = _cache_path(key)

    if path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        info = {"model": model, "cached": True, "usage": rec["usage"], "cost": cost_usd(model, rec["usage"]),
                "ms": rec.get("ms", 0)}
        if meter is not None:
            meter.append(info)
        return rec["data"], info

    if config.MODE != "live":
        raise LLMUnavailable(f"{config.MODE} mode and no cached response")
    provider, model_id = _ready(model)

    t0 = time.time()
    try:
        if provider == "anthropic":
            text, usage = _anthropic(model_id, system, user, schema, max_tokens, effort)
        else:
            text, usage = _openai_compat(provider, model_id, system, user, schema, max_tokens, effort)
    except LLMUnavailable:
        raise
    except Exception as e:  # network, auth, rate limit, missing SDK: the pipeline degrades to deterministic
        raise LLMUnavailable(f"API error: {type(e).__name__}: {e}")
    ms = int((time.time() - t0) * 1000)
    data = _conform(_parse(text), schema)

    with _lock:
        path.write_text(json.dumps({"data": data, "usage": usage, "ms": ms, "model": model}), encoding="utf-8")
    info = {"model": model, "cached": False, "usage": usage, "cost": cost_usd(model, usage), "ms": ms}
    if meter is not None:
        meter.append(info)
    return data, info


def transcribe_image(data, media_type, prompt):
    """Image document -> text with the 'ocr' stage model (live mode only, not cached)."""
    if config.MODE != "live":
        raise LLMUnavailable("Image documents need live mode (a vision model) for transcription")
    provider, model = _ready(config.MODELS["ocr"])
    b64 = base64.b64encode(data).decode()
    try:
        if provider == "anthropic":
            resp = _get_client("anthropic").messages.create(model=model, max_tokens=8000, messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt}]}])
            return next(b.text for b in resp.content if getattr(b, "type", "") == "text")
        _wait_turn(provider)
        cap = config.PROVIDERS[provider].get("max_tokens") or 8000
        resp = _get_client(provider).chat.completions.create(model=model, max_tokens=min(8000, cap), messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}}]}])
        return resp.choices[0].message.content or ""
    except LLMUnavailable:
        raise
    except Exception as e:
        raise LLMUnavailable(f"API error: {type(e).__name__}: {e}")
