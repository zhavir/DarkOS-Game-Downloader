"""Shared lifetime policy for downloaded application catalogues."""

DEFAULT_CATALOGUE_TTL_DAYS = 7
SECONDS_PER_DAY = 24 * 60 * 60


def catalogue_ttl_seconds(days: int) -> int:
    """Convert the persisted whole-day setting to the runtime cache lifetime."""

    return days * SECONDS_PER_DAY
