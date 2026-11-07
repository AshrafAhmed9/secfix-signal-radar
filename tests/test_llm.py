import json

import pytest

from radar import config, http, llm
from tests.fakes import FakeResponse

SCHEMA = {"type": "object", "required": ["a", "tags"], "additionalProperties": False,
          "properties": {"a": {"type": "string", "enum": ["x", "y"]},
                         "tags": {"type": "array", "items": {"type": "string", "enum": ["p", "q"]}},
                         "n": {"type": ["string", "null"]}}}


@pytest.mark.parametrize("value,ok", [
    ({"a": "x", "tags": ["p"]}, True),
    ({"a": "x", "tags": [], "n": None}, True),
    ({"a": "z", "tags": []}, False),            # not in enum
    ({"a": "x"}, False),                         # missing required key
    ({"a": "x", "tags": ["nope"]}, False),       # bad array item
    ({"a": "x", "tags": [], "n": 5}, False),     # wrong type
    ("not an object", False),
])
def test_conforms(value, ok):
    assert llm.conforms(value, SCHEMA) is ok


def compat_reply(text):
    return FakeResponse(200, {"choices": [{"message": {"content": text}}]})


def test_compat_provider_posts_chat_completion_and_parses_fenced_json(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "LLM_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(http, "request", lambda *a, **k: calls.append((a, k)) or
                        compat_reply('```json\n{"a": "x", "tags": ["p"]}\n```'))
    data, cost = llm.ask_json(llm.CompatClient("https://api.test/v1", "KEY"), "m1", "sys", "prompt", SCHEMA)
    assert data == {"a": "x", "tags": ["p"]} and cost == 0.0
    (method, url), kwargs = calls[0]
    assert (method, url) == ("POST", "https://api.test/v1/chat/completions")
    assert kwargs["headers"] == {"Authorization": "Bearer KEY"}
    assert kwargs["json"]["model"] == "m1" and kwargs["json"]["response_format"] == {"type": "json_object"}
    assert '"required"' in kwargs["json"]["messages"][0]["content"]  # schema is in the prompt


def test_output_that_does_not_match_the_schema_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(http, "request", lambda *a, **k: compat_reply('{"a": "nope", "tags": []}'))
    with pytest.raises(llm.LLMBadOutput):
        llm.ask_json(llm.CompatClient("https://api.test/v1", ""), "m", "s", "p", SCHEMA)


def test_non_json_output_raises_a_json_error(monkeypatch):
    monkeypatch.setattr(config, "LLM_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(http, "request", lambda *a, **k: compat_reply("Sure! Here you go"))
    with pytest.raises(json.JSONDecodeError):
        llm.ask_json(llm.CompatClient("https://api.test/v1", ""), "m", "s", "p", SCHEMA)


def test_missing_settings_per_provider(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://api.test/v1")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert llm.missing_settings() == ["LLM_MODEL", "LLM_API_KEY"]
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://localhost:11434/v1")  # local Ollama needs no key
    monkeypatch.setattr(config, "LLM_MODEL", "llama")
    assert llm.missing_settings() == []
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    assert llm.missing_settings() == ["ANTHROPIC_API_KEY"]


def test_model_for_roles(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(config, "LLM_MODEL", "fast")
    monkeypatch.setattr(config, "LLM_MODEL_BRIEF", "")
    assert config.model_for("extract") == "fast" and config.model_for("brief") == "fast"
    monkeypatch.setattr(config, "LLM_MODEL_BRIEF", "smart")
    assert config.model_for("brief") == "smart"
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    assert config.model_for("brief") == config.MODEL_BRIEF
