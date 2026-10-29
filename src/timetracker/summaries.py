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


def grouped_entries(db, kind: str, anchor: float, now: float) -> list[dict]:
    """Every entry of the period, grouped per project.

    Groups are sorted alphabetically by project name (ignoring case, then by id) and only exist for
    projects with time in the period (archived ones included). Inside a group the entries run from
    the earliest to the latest start. An entry's `seconds` is clipped to the period, so the entries
    of a group add up to the group's `seconds`, which equals summary()'s number for that project.
    """
    start, end = period_bounds(anchor, kind)
    projects = {p.id: p for p in db.list_projects(include_archived=True)}
    groups: dict[int, dict] = {}
    for e in db.entries_between(start, end):
        stop = e.end_ts if e.end_ts is not None else now
        seconds = max(0, min(stop, end) - max(e.start_ts, start))
        project = projects[e.project_id]
        group = groups.setdefault(project.id, {
            "project_id": project.id, "name": project.name, "color": project.color,
            "archived": project.archived, "seconds": 0, "entries": [],
        })
        group["seconds"] += seconds
        group["entries"].append({"id": e.id, "start": e.start_ts, "end": e.end_ts, "seconds": seconds, "note": e.note})
    for group in groups.values():
        group["entries"].sort(key=lambda x: (x["start"], x["id"]))
    return sorted(groups.values(), key=lambda g: (g["name"].casefold(), g["project_id"]))


def step_limits(db, kind: str, now: float) -> tuple[int, int]:
    """Start of the oldest period worth showing (the one with the first entry) and of the current one."""
    current = period_bounds(now, kind)[0]
    first = db.earliest_timestamp()
    oldest = period_bounds(first, kind)[0] if first is not None else current
    return min(oldest, current), current
