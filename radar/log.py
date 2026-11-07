"""Structured JSON logs, one line per event, always with the stage name."""
import json
import sys
from datetime import datetime, timezone


def log(stage: str, message: str, **fields) -> None:
    line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage,
            "msg": message, **fields}
    print(json.dumps(line, ensure_ascii=False, default=str), file=sys.stdout, flush=True)
