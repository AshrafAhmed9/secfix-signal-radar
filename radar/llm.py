"""One place that talks to an LLM: JSON out, validated, with a cost estimate.

Two providers: the Claude API, or any OpenAI-compatible endpoint (free tiers, local Ollama).
"""
import json
import re
import time

import anthropic

from radar import config, http


class LLMRefused(Exception):
    pass


class LLMBudgetReached(Exception):
    """This run used up LLM_MAX_CALLS. Handled like a provider quota: stop cleanly, retry tomorrow."""

    status = 429


class LLMBadOutput(ValueError):
    """The model answered, but not with JSON that matches the schema."""


class CompatClient:
    """Settings for an OpenAI-compatible endpoint. Calls go through radar.http like everything else."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key


def missing_settings() -> list[str]:
    if config.LLM_PROVIDER == "anthropic":
        return [] if config.ANTHROPIC_API_KEY else ["ANTHROPIC_API_KEY"]
    missing = []
    if not config.LLM_MODEL:
        missing.append("LLM_MODEL")
    local = "localhost" in config.LLM_BASE_URL or "127.0.0.1" in config.LLM_BASE_URL
    if not config.LLM_API_KEY and not local:
        missing.append("LLM_API_KEY")
    return missing


def get_client():
    if config.LLM_PROVIDER == "anthropic":
        # The SDK retries 408/409/429/5xx itself; that is the retry policy for Claude calls.
        return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=4, timeout=60.0)
    return CompatClient(config.LLM_BASE_URL, config.LLM_API_KEY)


def cost_usd(model: str, usage) -> float:
    """Rough cost from token counts. Ignores cache discounts, so it is an upper-ish estimate."""
    price_in, price_out = config.PRICES.get(model, (0.0, 0.0))
    return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000


def conforms(value, schema: dict) -> bool:
    """Small JSON-schema check: type, required keys, enums, array items. Enough to trust the output.

    Free providers don't all enforce schemas, so we check ourselves before anything is stored.
    """
    types = schema.get("type")
    types = types if isinstance(types, list) else [types]
    checks = {
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    if not any(checks.get(t, lambda v: True)(value) for t in types):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, dict) and "object" in types:
        if any(key not in value for key in schema.get("required", [])):
            return False
        return all(conforms(value[k], sub) for k, sub in schema.get("properties", {}).items() if k in value)
    if isinstance(value, list) and "array" in types and "items" in schema:
        return all(conforms(item, schema["items"]) for item in value)
    return True


_last_call = 0.0
_calls = 0


def reset_budget() -> None:
    global _calls
    _calls = 0


def _throttle() -> None:
    global _last_call
    wait = config.LLM_MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _ask_anthropic(client, model, system, prompt, schema, max_tokens, effort):
    response = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise LLMRefused("the model declined this request")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return text, cost_usd(model, response.usage)


def _ask_compat(client, model, system, prompt, schema):
    headers = {"Authorization": f"Bearer {client.api_key}"} if client.api_key else {}
    response = http.request("POST", f"{client.base_url}/chat/completions", headers=headers, timeout=90.0,
                            max_attempts=6, json={
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system + "\nReply with one JSON object only, matching this JSON "
                                                  "Schema exactly:\n" + json.dumps(schema)},
            {"role": "user", "content": prompt},
        ],
    })
    return response.json()["choices"][0]["message"]["content"], 0.0  # free tier: no cost to track


def ask_json(client, model: str, system: str, prompt: str, schema: dict, *,
             max_tokens: int = 4000, effort: str = "low") -> tuple[dict, float]:
    """Ask for JSON that matches schema. Returns (data, estimated_cost_usd). Raises if it doesn't conform."""
    global _calls
    if config.LLM_MAX_CALLS and _calls >= config.LLM_MAX_CALLS:
        raise LLMBudgetReached(f"reached LLM_MAX_CALLS={config.LLM_MAX_CALLS} for this run")
    _calls += 1
    _throttle()
    if isinstance(client, CompatClient):
        text, cost = _ask_compat(client, model, system, prompt, schema)
    else:
        text, cost = _ask_anthropic(client, model, system, prompt, schema, max_tokens, effort)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())  # some models wrap JSON in a code fence
    data = json.loads(text)
    if not conforms(data, schema):
        raise LLMBadOutput("model output does not match the schema")
    return data, cost
