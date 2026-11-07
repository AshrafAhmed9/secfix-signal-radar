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

COUNTRIES = ["de", "at"]  # add "ch" if Adzuna supports it for this account
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
ALERT_COOLDOWN_DAYS = 14

# Cheap model for extraction, stronger one only for briefs (cost control).
MODEL_EXTRACT = "claude-haiku-5-5"
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
