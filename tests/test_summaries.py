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


# -- grouped_entries: the list on the Reports page -------------------------------------------------------

from timetracker.summaries import grouped_entries


def test_groups_are_alphabetical_ignoring_case_and_only_for_projects_with_time(db, clock):
    zed, apple, mango, unused = (db.add_project(n, "#1") for n in ("zed", "Apple", "mango", "Unused"))
    clock.t = int(ts(2026, 10, 28, 9))
    for pid in (zed, apple, mango):
        db.start(pid); clock.advance(600); db.stop(); clock.advance(60)
    groups = grouped_entries(db, "day", clock(), clock())
    assert [g["name"] for g in groups] == ["Apple", "mango", "zed"]       # not Apple, Unused, mango, zed (ASCII order)


def test_equal_names_fall_back_to_the_project_id(db, clock):
    a, b = db.add_project("Same", "#1"), db.add_project("same", "#2")
    clock.t = int(ts(2026, 10, 28, 9))
    for pid in (b, a):
        db.start(pid); clock.advance(60); db.stop(); clock.advance(60)
    assert [g["project_id"] for g in grouped_entries(db, "day", clock(), clock())] == [a, b]


def test_entries_inside_a_group_run_from_earliest_to_latest(db, clock):
    a = db.add_project("A", "#1")
    b = db.add_project("B", "#1")
    clock.t = int(ts(2026, 10, 28, 15))
    first = db.start(a); clock.advance(600); db.stop()           # 15:00, made first
    clock.t = int(ts(2026, 10, 28, 9))
    second = db.start(a); clock.advance(600); db.stop()          # 09:00, made later but earlier in the day
    clock.t = int(ts(2026, 10, 28, 12))
    third = db.start(a); clock.advance(600); db.stop()
    db.start(b); clock.advance(30); db.stop()
    [group_a, group_b] = grouped_entries(db, "day", clock(), clock())
    assert [e["id"] for e in group_a["entries"]] == [second.id, third.id, first.id]
    starts = [e["start"] for e in group_a["entries"]]
    assert starts == sorted(starts)
    assert group_b["name"] == "B"


def test_notes_are_carried_along(db, clock):
    a = db.add_project("A", "#1")
    clock.t = int(ts(2026, 10, 28, 9))
    e = db.start(a); clock.advance(600); db.stop()
    db.set_note(e.id, "Quarterly report")
    clock.advance(100)
    db.start(a); clock.advance(60); db.stop()
    [group] = grouped_entries(db, "day", clock(), clock())
    assert [x["note"] for x in group["entries"]] == ["Quarterly report", ""]


def test_group_totals_equal_the_summary_and_the_entries_add_up(db, clock):
    a, b = make_entries(db, clock)
    for kind, anchor in (("day", ts(2026, 10, 28)), ("week", ts(2026, 10, 28)), ("month", ts(2026, 10, 15)),
                         ("month", ts(2026, 11, 15)), ("week", ts(2026, 11, 3))):
        groups = grouped_entries(db, kind, anchor, clock())
        by_project = {g["project_id"]: g["seconds"] for g in groups}
        s = summary(db, kind, anchor, clock())
        for row in s["rows"]:
            assert by_project.get(row["project_id"], 0) == row["seconds"], (kind, anchor)
        for g in groups:
            assert g["seconds"] == sum(e["seconds"] for e in g["entries"])
        assert sum(g["seconds"] for g in groups) == s["total"]


def test_an_entry_crossing_midnight_shows_only_its_part_in_each_period(db, clock):
    a, b = make_entries(db, clock)                              # a: 31 Oct 23:30 for one hour
    sat = grouped_entries(db, "day", ts(2026, 10, 31, 12), clock())[0]
    sun = grouped_entries(db, "day", ts(2026, 11, 1, 12), clock())[0]
    assert [e["seconds"] for e in sat["entries"]] == [1800]
    assert [e["seconds"] for e in sun["entries"]] == [1800]
    assert sat["entries"][0]["id"] == sun["entries"][0]["id"]   # the same entry, listed in both days
    assert sat["entries"][0]["end"] - sat["entries"][0]["start"] == 3600    # its real times are kept


def test_an_archived_project_with_time_is_listed(db, clock):
    a, b = make_entries(db, clock)
    db.archive_project(b)
    names = [(g["name"], g["archived"]) for g in grouped_entries(db, "week", ts(2026, 10, 28), clock())]
    assert names == [("A", False), ("B", True)]


def test_a_running_entry_counts_up_to_now_and_has_no_end(db, clock):
    a = db.add_project("A", "#1")
    clock.t = int(ts(2026, 10, 28, 9))
    db.start(a)
    clock.advance(777)
    [group] = grouped_entries(db, "day", clock(), clock())
    assert group["entries"][0]["end"] is None and group["entries"][0]["seconds"] == 777


def test_an_empty_period_has_no_groups(db, clock):
    db.add_project("A", "#1")
    assert grouped_entries(db, "day", ts(2026, 10, 28), ts(2026, 10, 28)) == []
