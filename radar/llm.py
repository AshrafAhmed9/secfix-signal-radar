"""One place that talks to Claude: structured JSON out, cost estimate, SDK retries configured."""
import json

import anthropic

from radar import config


class LLMRefused(Exception):
    pass


def get_client() -> anthropic.Anthropic:
    # The SDK retries 408/409/429/5xx itself; that is the retry policy for Claude calls.
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=4, timeout=60.0)


def cost_usd(model: str, usage) -> float:
    """Rough cost from token counts. Ignores cache discounts, so it is an upper-ish estimate."""
    price_in, price_out = config.PRICES.get(model, (0.0, 0.0))
    return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000


def ask_json(client, model: str, system: str, prompt: str, schema: dict, *,
             max_tokens: int = 4000, effort: str = "low") -> tuple[dict, float]:
    """Ask for JSON that matches schema. Returns (data, estimated_cost_usd).

    output_config.format makes the API return valid JSON for the schema. max_tokens leaves
    room for the model's own reasoning, which is billed inside it.
    """
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise LLMRefused("the model declined this request")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text), cost_usd(model, response.usage)
