"""Day / week / month summaries. Mirrors docs/summaries.js; keep the two in sync.

A period is a calendar day, a week (Monday to Sunday) or a month, in local time. The numbers come
straight from Database.totals, so a summary always equals the raw entries clipped to its period.
"""

from datetime import datetime, timedelta

KINDS = ("day", "week", "month")


def _midnight(ts: float) -> datetime:
    return datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0)


def _add_months(d: datetime, months: int) -> datetime:
    index = d.year * 12 + (d.month - 1) + months
    return d.replace(year=index // 12, month=index % 12 + 1, day=1)


def period_start(ts: float, kind: str) -> datetime:
    d = _midnight(ts)
    if kind == "day":
        return d
    if kind == "week":
        return d - timedelta(days=d.weekday())  # Monday
    if kind == "month":
        return d.replace(day=1)
    raise ValueError(f"unknown period kind: {kind!r}")


def period_bounds(ts: float, kind: str) -> tuple[int, int]:
    """Start (inclusive) and end (exclusive) of the period containing ts, as epoch seconds."""
    start = period_start(ts, kind)
    if kind == "day":
        end = start + timedelta(days=1)
    elif kind == "week":
        end = start + timedelta(days=7)
    else:
        end = _add_months(start, 1)
    return int(start.timestamp()), int(end.timestamp())


def shift_period(ts: float, kind: str, steps: int) -> int:
    """The start of the period `steps` periods after (or before, if negative) the one containing ts."""
    start = period_start(ts, kind)
    if kind == "day":
        moved = start + timedelta(days=steps)
    elif kind == "week":
        moved = start + timedelta(days=7 * steps)
    else:
        moved = _add_months(start, steps)
    return int(moved.timestamp())


def period_label(ts: float, kind: str, now: float) -> str:
    start = period_start(ts, kind)
    current = period_start(now, kind)
    if kind == "day":
        if start == current:
            return "Today"
        if start == current - timedelta(days=1):
            return "Yesterday"
        year = f" {start.year}" if start.year != current.year else ""
        return f"{start:%a} {start.day} {start:%b}{year}"
    if kind == "week":
        last = start + timedelta(days=6)
        span = f"{start.day} {start:%b} – {last.day} {last:%b}"
        if start.year != last.year or start.year != current.year:
            span += f" {last.year}"
        return f"This week · {span}" if start == current else span
    return f"{start:%B %Y}"


def summary(db, kind: str, anchor: float, now: float) -> dict:
    """Totals per project for the period containing `anchor`.

    Archived projects only appear when they have time in the period. total is the sum of the rows.
    """
    start, end = period_bounds(anchor, kind)
    totals = db.totals(start, end)
    rows = [
        {"project_id": p.id, "name": p.name, "color": p.color, "seconds": totals.get(p.id, 0), "archived": p.archived}
        for p in db.list_projects(include_archived=True)
        if not p.archived or totals.get(p.id, 0) > 0
    ]
    return {
        "kind": kind,
        "start": start,
        "end": end,
        "label": period_label(anchor, kind, now),
        "total": sum(r["seconds"] for r in rows),
        "rows": rows,
    }


def step_limits(db, kind: str, now: float) -> tuple[int, int]:
    """Start of the oldest period worth showing (the one with the first entry) and of the current one."""
    current = period_bounds(now, kind)[0]
    first = db.earliest_timestamp()
    oldest = period_bounds(first, kind)[0] if first is not None else current
    return min(oldest, current), current
