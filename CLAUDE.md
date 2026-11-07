# secfix-signal-radar

Daily pipeline that finds DACH companies showing compliance-buying signals (hiring for ISO 27001 / TISAX / NIS2 / infosec roles), scores them with explainable rules, upserts them into HubSpot and posts a Slack digest.

## Working rules (for Claude Code)

- Simplest code that works. Short functions, plain names, no frameworks unless needed.
- Plain Python 3.11: `requests`, `sqlite3`, `python-dotenv`, `pytest`; `anthropic` only for the optional Claude provider.
- Comment only the *why* of non-obvious lines.
- No fabricated data: no invented companies, people or numbers.
- Every external HTTP call goes through `radar/http.py`.
- Cost control: cache LLM calls, cap calls per run (`LLM_MAX_CALLS`, `--limit`), cheap model for extraction.
- The LLM researches, reps write. No AI-drafted outreach copy anywhere.
- Out of scope: dashboard UI, ML scoring, Docker/Kubernetes, multi-CRM, async (sequential is fine at this volume).
- Never put a number in the README that a run or `eval/precision.py` did not produce.
