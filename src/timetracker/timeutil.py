"""Local-time helpers. All stored timestamps are UTC epoch seconds."""

from datetime import datetime, timedelta


def day_bounds(ts: float) -> tuple[int, int]:
    """Start (inclusive) and end (exclusive) of the local day containing ts."""
    start = datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())
