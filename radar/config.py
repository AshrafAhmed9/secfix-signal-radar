"""All settings in one place: env vars, queries, limits and the scoring weights."""
import os

from dotenv import load_dotenv

load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


ADZUNA_APP_ID = env("ADZUNA_APP_ID")
ADZUNA_APP_KEY = env("ADZUNA_APP_KEY")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
HUBSPOT_TOKEN = env("HUBSPOT_TOKEN")
SLACK_DIGEST_WEBHOOK = env("SLACK_DIGEST_WEBHOOK")
SLACK_ERROR_WEBHOOK = env("SLACK_ERROR_WEBHOOK")
DB_PATH = env("RADAR_DB_PATH", "radar.db")

COUNTRIES = ["de", "at", "ch"]
QUERIES = [
    "ISO 27001",
    "Informationssicherheit",
    "ISMS",
    "TISAX",
    "NIS2",
    "Information Security Officer",
    "Informationssicherheitsbeauftragter",
]
MAX_PAGES = 3
TOP_N_ALERT = 5
TOP_N_BRIEF = 5

# Cheap model for extraction, stronger one only for briefs (cost control).
MODEL_EXTRACT = "claude-haiku-5-5"  # only used when LLM_PROVIDER=anthropic
MODEL_BRIEF = "claude-sonnet-5-5"

# One dict so the rules are easy to tune. Every point must come with a reason string.
WEIGHTS = {
    "hiring_infosec_role": 30,
    "two_or_more_postings": 10,
    "found_on_both_sources": 5,
    "automotive_supplier": 25,
    "nis2_sector_50_plus": 20,
    "sells_b2b": 15,
    "size_20_to_999": 15,
    "already_certified": -50,
    "uses_competitor": -30,
}

# Employee bands the enrichment step may return.
BANDS_IN_ICP = ("20-49", "50-249", "250-999")
BANDS_50_PLUS = ("50-249", "250-999", "1000+")
SEGMENT_BY_BAND = {"20-49": "SMB", "50-249": "SMB", "250-999": "Mid-Market"}

COMPETITORS = ["vanta", "drata", "secureframe", "sprinto", "dataguard", "kertos", "safebase"]

# Sources to pull from. "arbeitsagentur" is opt-in: its API answers 403 from my laptop and from GitHub Actions.
SOURCES = [x.strip() for x in env("RADAR_SOURCES", "adzuna").split(",") if x.strip()]

# Words that must appear in a posting title for it to count as a security signal.
# The search also matches the job description, so without this a software job that merely
# mentions ISO 27001 would count as a buying signal.
SECURITY_TITLE_WORDS = (
    "sicherheit", "security", "isms", "iso 27001", "iso27001", "tisax", "nis2", "ciso",
    "grc", "compliance", "datenschutz", "cyber", "risk", "risiko",
)

HUBSPOT_PORTAL_ID = env("HUBSPOT_PORTAL_ID")


def owner_ids(name: str) -> list[str]:
    return [x.strip() for x in env(name).split(",") if x.strip()]


OWNERS = {"SMB": owner_ids("OWNERS_SMB"), "Mid-Market": owner_ids("OWNERS_MID_MARKET")}
OWNER_DEFAULT = env("OWNER_DEFAULT")

# Generic client name, no personal contact details.
USER_AGENT = "secfix-signal-radar/0.1 (+https://github.com/AshrafAhmed9/secfix-signal-radar)"

# USD per 1M tokens (input, output), only for the cost estimate in the run log.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}

# --- LLM provider ---------------------------------------------------------------------
# "openai_compat" works with any OpenAI-style /chat/completions endpoint: Gemini's free tier,
# Groq, OpenRouter, or a local Ollama. "anthropic" uses the Claude API. If unset, Claude is
# used when ANTHROPIC_API_KEY exists, otherwise openai_compat.
LLM_PROVIDER = env("LLM_PROVIDER") or ("anthropic" if ANTHROPIC_API_KEY else "openai_compat")
LLM_BASE_URL = env("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
LLM_API_KEY = env("LLM_API_KEY")
LLM_MODEL = env("LLM_MODEL")
LLM_MODEL_BRIEF = env("LLM_MODEL_BRIEF")  # optional stronger model for briefs
# Free tiers allow only a few requests per minute. Seconds to wait between LLM calls.
LLM_MIN_INTERVAL = float(env("LLM_MIN_INTERVAL", "0"))
# Hard cap on LLM calls per run (0 = no cap). Protects free-tier daily quotas.
LLM_MAX_CALLS = int(env("LLM_MAX_CALLS", "0"))


def model_for(role: str) -> str:
    """role is "extract" or "brief"."""
    if LLM_PROVIDER == "anthropic":
        return MODEL_BRIEF if role == "brief" else MODEL_EXTRACT
    return (LLM_MODEL_BRIEF or LLM_MODEL) if role == "brief" else LLM_MODEL
