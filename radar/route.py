"""Stage 6b: which rep owns which account."""
from radar import config


def segment_for(employee_band: str | None) -> str | None:
    """SMB or Mid-Market from the employee band. Out-of-ICP sizes get no segment."""
    return config.SEGMENT_BY_BAND.get(employee_band or "")


def pick_owner(segment: str | None, counts: dict, owners: dict | None = None,
               default: str | None = None) -> str | None:
    """Round-robin inside a segment. counts is mutated: it remembers how many we assigned."""
    owners = config.OWNERS if owners is None else owners
    default = config.OWNER_DEFAULT if default is None else default
    pool = owners.get(segment or "", [])
    if not pool:
        return default or None
    index = counts.get(segment, 0)
    counts[segment] = index + 1
    return pool[index % len(pool)]
