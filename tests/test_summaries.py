from datetime import datetime

import pytest

from timetracker.summaries import (period_bounds, period_label, shift_period, step_limits, summary)


def ts(*args):
    return datetime(*args).timestamp()


# -- period bounds ----------------------------------------------------------------------------------

def test_day_bounds_span_a_local_day():
    start, end = period_bounds(ts(2026, 3, 14, 15, 9), "day")
    assert datetime.fromtimestamp(start) == datetime(2026, 3, 14)
    assert datetime.fromtimestamp(end) == datetime(2026, 3, 15)


def test_week_starts_on_monday_and_lasts_seven_days():
    # 2026-10-28 is a Wednesday
    start, end = period_bounds(ts(2026, 10, 28, 12), "week")
    assert datetime.fromtimestamp(start) == datetime(2026, 10, 26)
    assert datetime.fromtimestamp(end) == datetime(2026, 11, 2)
    # Sunday still belongs to the week that started on the Monday before
    start, _ = period_bounds(ts(2026, 11, 1, 23, 59), "week")
    assert datetime.fromtimestamp(start) == datetime(2026, 10, 26)
    # Monday at midnight starts a new week
    start, _ = period_bounds(ts(2026, 11, 2, 0, 0), "week")
    assert datetime.fromtimestamp(start) == datetime(2026, 11, 2)


def test_month_bounds_including_december_and_february():
    start, end = period_bounds(ts(2026, 12, 31, 23), "month")
    assert (datetime.fromtimestamp(start), datetime.fromtimestamp(end)) == (datetime(2026, 12, 1), datetime(2027, 1, 1))
    start, end = period_bounds(ts(2028, 2, 10), "month")      # a leap year
    assert (datetime.fromtimestamp(start), datetime.fromtimestamp(end)) == (datetime(2028, 2, 1), datetime(2028, 3, 1))


def test_unknown_kind():
    with pytest.raises(ValueError):
        period_bounds(0, "year")


def test_bounds_are_contiguous_and_cover_every_moment():
    for kind in ("day", "week", "month"):
        t = ts(2026, 1, 1)
        start, end = period_bounds(t, kind)
        for _ in range(30):
            nxt_start, _ = period_bounds(end, kind)
            assert nxt_start == end                      # the next period starts exactly where this one ends
            start, end = period_bounds(end, kind)


# -- shifting ---------------------------------------------------------------------------------------

def test_shift_period_steps_by_whole_periods():
    t = ts(2026, 10, 28, 15)
    assert datetime.fromtimestamp(shift_period(t, "day", -1)) == datetime(2026, 10, 27)
    assert datetime.fromtimestamp(shift_period(t, "week", -1)) == datetime(2026, 10, 19)
    assert datetime.fromtimestamp(shift_period(t, "month", -1)) == datetime(2026, 9, 1)
    assert datetime.fromtimestamp(shift_period(t, "month", 3)) == datetime(2027, 1, 1)
    assert datetime.fromtimestamp(shift_period(ts(2026, 1, 15), "month", -1)) == datetime(2025, 12, 1)


# -- labels -----------------------------------------------------------------------------------------

def test_labels():
    now = ts(2026, 10, 28, 12)
    assert period_label(now, "day", now) == "Today"
    assert period_label(ts(2026, 10, 27), "day", now) == "Yesterday"
    assert period_label(ts(2026, 10, 20), "day", now) == "Tue 20 Oct"
    assert period_label(ts(2025, 12, 24), "day", now) == "Wed 24 Dec 2025"
    assert period_label(now, "week", now) == "This week · 26 Oct – 1 Nov"
    assert period_label(ts(2026, 10, 14), "week", now) == "12 Oct – 18 Oct"
    assert period_label(ts(2026, 12, 30), "week", ts(2026, 12, 30)).endswith("3 Jan 2027")
    assert period_label(now, "month", now) == "October 2026"


# -- summaries: they must equal the raw entries ------------------------------------------------------

def make_entries(db, clock):
    a, b = db.add_project("A", "#1"), db.add_project("B", "#2")
    # Monday 26 Oct .. Sunday 1 Nov 2026
    plan = [
        (a, ts(2026, 10, 26, 9), 3600),
        (b, ts(2026, 10, 27, 10), 1800),
        (a, ts(2026, 10, 28, 9), 5400),
        (a, ts(2026, 10, 31, 23, 30), 3600),     # crosses midnight into Sunday 1 Nov
        (b, ts(2026, 11, 2, 8), 600),            # the following Monday
        (a, ts(2026, 9, 30, 8), 900),            # last month
    ]
    for pid, start, seconds in plan:
        clock.t = int(start)
        db.start(pid)
        clock.t += seconds
        db.stop()
    clock.t = int(ts(2026, 11, 2, 12))
    return a, b


def seconds_by_project(result):
    return {r["project_id"]: r["seconds"] for r in result["rows"]}


def test_day_summary_matches_the_entries(db, clock):
    a, b = make_entries(db, clock)
    r = summary(db, "day", ts(2026, 10, 28, 12), clock())
    assert seconds_by_project(r) == {a: 5400, b: 0}
    assert r["total"] == 5400


def test_week_summary_matches_the_entries_including_the_midnight_split(db, clock):
    a, b = make_entries(db, clock)
    r = summary(db, "week", ts(2026, 10, 28), clock())
    # A: 3600 + 5400 + 30 min before midnight on Saturday + 30 min on Sunday; B: 1800
    assert seconds_by_project(r) == {a: 3600 + 5400 + 3600, b: 1800}
    assert r["total"] == 3600 + 5400 + 3600 + 1800


def test_the_next_week_gets_the_other_half_of_the_split_entry(db, clock):
    a, b = make_entries(db, clock)
    r = summary(db, "week", ts(2026, 11, 3), clock())
    assert seconds_by_project(r) == {a: 0, b: 600}


def test_month_summary_matches_the_entries(db, clock):
    a, b = make_entries(db, clock)
    r = summary(db, "month", ts(2026, 10, 15), clock())
    # October: all of the week-one entries up to midnight on 31 Oct (the split entry: 30 min in Oct, 30 in Nov)
    assert seconds_by_project(r) == {a: 3600 + 5400 + 1800, b: 1800}
    nov = summary(db, "month", ts(2026, 11, 15), clock())
    assert seconds_by_project(nov) == {a: 1800, b: 600}
    sep = summary(db, "month", ts(2026, 9, 15), clock())
    assert seconds_by_project(sep) == {a: 900, b: 0}


def test_total_is_the_sum_of_the_rows_and_of_all_raw_entries(db, clock):
    a, b = make_entries(db, clock)
    entries = db.entries_between(0, 2**40)
    raw_total = sum(e.end_ts - e.start_ts for e in entries)
    parts = [summary(db, "month", ts(2026, m, 15), clock())["total"] for m in (9, 10, 11)]
    assert sum(parts) == raw_total
    for kind in ("day", "week", "month"):
        r = summary(db, kind, ts(2026, 10, 28), clock())
        assert r["total"] == sum(row["seconds"] for row in r["rows"])


def test_a_running_timer_counts_up_to_now(db, clock):
    a = db.add_project("A", "#1")
    clock.t = int(ts(2026, 10, 28, 9))
    db.start(a)
    clock.t += 1234
    r = summary(db, "day", clock(), clock())
    assert seconds_by_project(r) == {a: 1234}


def test_archived_projects_only_show_when_they_have_time_in_the_period(db, clock):
    a, b = make_entries(db, clock)
    db.archive_project(b)
    wk = summary(db, "week", ts(2026, 10, 28), clock())
    assert [r["name"] for r in wk["rows"]] == ["A", "B"] and wk["rows"][1]["archived"] is True
    day = summary(db, "day", ts(2026, 10, 28), clock())
    assert [r["name"] for r in day["rows"]] == ["A"]          # B has nothing that day


def test_step_limits(db, clock):
    assert step_limits(db, "day", ts(2026, 10, 28, 12)) == (period_bounds(ts(2026, 10, 28), "day")[0],) * 2
    make_entries(db, clock)
    oldest, current = step_limits(db, "month", clock())
    assert datetime.fromtimestamp(oldest) == datetime(2026, 9, 1)
    assert datetime.fromtimestamp(current) == datetime(2026, 11, 1)
