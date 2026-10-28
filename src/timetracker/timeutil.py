"""Local-time helpers. All stored timestamps are UTC epoch seconds."""

from datetime import datetime, timedelta


def day_bounds(ts: float) -> tuple[int, int]:
    """Start (inclusive) and end (exclusive) of the local day containing ts."""
    start = datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def span_text(seconds: float) -> str:
    """A duration for the screen: minutes and seconds under an hour, hours and minutes from an hour up."""
    s = max(0, int(seconds))
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {s % 3600 // 60:02d}m"
