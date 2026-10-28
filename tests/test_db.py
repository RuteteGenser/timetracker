import sqlite3

import pytest

from timetracker.db import Database


def test_projects_crud_and_order(db):
    a = db.add_project("A", "#111111")
    b = db.add_project("B", "#222222")
    assert [p.name for p in db.list_projects()] == ["A", "B"]
    db.rename_project(a, "Alpha")
    db.set_project_color(b, "#333333")
    assert db.get_project(a).name == "Alpha"
    assert db.get_project(b).color == "#333333"
    db.archive_project(a)
    assert [p.name for p in db.list_projects()] == ["B"]
    assert [p.name for p in db.list_projects(include_archived=True)] == ["Alpha", "B"]
    db.delete_project(b)
    assert db.list_projects(include_archived=True)[0].id == a


def test_empty_name_rejected(db):
    with pytest.raises(ValueError):
        db.add_project("  ", "#000000")


def test_start_stop(db, clock):
    p = db.add_project("A", "#111111")
    e = db.start(p)
    assert db.running().id == e.id
    clock.advance(90)
    done = db.stop()
    assert (done.start_ts, done.end_ts) == (e.start_ts, e.start_ts + 90)
    assert db.running() is None
    assert db.stop() is None


def test_start_same_project_is_noop(db, clock):
    p = db.add_project("A", "#111111")
    first = db.start(p)
    clock.advance(10)
    assert db.start(p).id == first.id
    assert db.running().start_ts == first.start_ts


def test_starting_other_project_stops_the_first(db, clock):
    a, b = db.add_project("A", "#1"), db.add_project("B", "#2")
    ea = db.start(a)
    clock.advance(60)
    eb = db.start(b)
    assert db.running().id == eb.id
    stopped = db.get_entry(ea.id)
    assert stopped.end_ts == eb.start_ts == ea.start_ts + 60


def test_only_one_running_entry_allowed_by_schema(db):
    p = db.add_project("A", "#1")
    db.start(p)
    with pytest.raises(sqlite3.IntegrityError):
        db._conn.execute("INSERT INTO entries(project_id, start_ts) VALUES (?, 1)", (p,))


def test_start_unknown_project(db):
    with pytest.raises(ValueError):
        db.start(999)


def test_archiving_running_project_stops_it(db, clock):
    p = db.add_project("A", "#1")
    db.start(p)
    clock.advance(30)
    db.archive_project(p)
    assert db.running() is None


def test_clock_set_back_never_makes_negative_entry(db, clock):
    p = db.add_project("A", "#1")
    e = db.start(p)
    clock.advance(-3600)  # clock jumped backwards
    done = db.stop()
    assert done.end_ts == e.start_ts


def test_note(db, clock):
    p = db.add_project("A", "#1")
    e = db.start(p)
    clock.advance(5)
    db.stop()
    db.set_note(e.id, "  fixed bug  ")
    assert db.get_entry(e.id).note == "fixed bug"


def test_running_timer_survives_unclean_shutdown(tmp_path, clock):
    """Simulate pulling the plug: reopen the file without closing the first connection."""
    path = tmp_path / "t.db"
    first = Database(path, clock=clock)
    p = first.add_project("A", "#1")
    started = first.start(p)
    clock.advance(1234)

    second = Database(path, clock=clock)  # what the app sees after reboot
    running = second.running()
    assert running is not None
    assert running.project_id == p
    assert running.start_ts == started.start_ts
    assert clock() - running.start_ts == 1234
    second.close()
    first.close()


def test_totals_clip_to_window(db, clock):
    p = db.add_project("A", "#1")
    t0 = clock()
    db.start(p)
    clock.advance(1000)
    db.stop()
    # window covers only the middle 400 s of the entry
    assert db.totals(t0 + 300, t0 + 700) == {p: 400}
    # window entirely outside
    assert db.totals(t0 + 2000, t0 + 3000) == {}
    # window containing everything
    assert db.totals(t0 - 5, t0 + 5000) == {p: 1000}


def test_totals_include_running_entry_up_to_now(db, clock):
    p = db.add_project("A", "#1")
    t0 = clock()
    db.start(p)
    clock.advance(250)
    assert db.totals(t0 - 10, t0 + 10_000) == {p: 250}


def test_totals_sum_per_project(db, clock):
    a, b = db.add_project("A", "#1"), db.add_project("B", "#2")
    t0 = clock()
    db.start(a); clock.advance(100)
    db.start(b); clock.advance(50)
    db.start(a); clock.advance(25)
    db.stop()
    assert db.totals(t0, t0 + 1000) == {a: 125, b: 50}


def test_delete_project_removes_entries(db, clock):
    p = db.add_project("A", "#1")
    db.start(p)
    clock.advance(5)
    db.stop()
    t0 = clock() - 5
    db.delete_project(p)
    assert db.entries_between(t0 - 1, t0 + 100) == []


def test_meta(db):
    assert db.get_meta("k") is None
    db.set_meta("k", "v1")
    db.set_meta("k", "v2")
    assert db.get_meta("k") == "v2"


def test_durability_pragmas(db):
    assert db._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db._conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL


def test_delete_entry_removes_its_time(db, clock):
    p = db.add_project("A", "#1")
    t0 = clock()
    e = db.start(p)
    clock.advance(60)
    db.stop()
    assert db.totals(t0 - 1, t0 + 1000) == {p: 60}
    db.delete_entry(e.id)
    assert db.get_entry(e.id) is None
    assert db.totals(t0 - 1, t0 + 1000) == {}


# -- reset_day ------------------------------------------------------------------------------

DAY = 86_400


def day_of(clock):
    start = clock() - clock() % DAY  # any fixed 24 h window will do
    return start, start + DAY


def test_reset_day_removes_todays_entries_only_for_that_project(db, clock):
    a, b = db.add_project("A", "#1"), db.add_project("B", "#2")
    day_start, day_end = day_of(clock)
    clock.t = day_start + 3600
    db.start(a); clock.advance(600)
    db.start(b); clock.advance(300)
    db.stop()
    db.reset_day(a, day_start, day_end)
    assert db.totals(day_start, day_end) == {b: 300}


def test_reset_day_keeps_other_days(db, clock):
    p = db.add_project("A", "#1")
    day_start, day_end = day_of(clock)
    clock.t = day_start - 7200            # yesterday
    db.start(p); clock.advance(1000); db.stop()
    clock.t = day_start + 100             # today
    db.start(p); clock.advance(500); db.stop()
    db.reset_day(p, day_start, day_end)
    assert db.totals(day_start, day_end) == {}
    assert db.totals(day_start - DAY, day_start) == {p: 1000}


def test_reset_day_cuts_an_entry_that_runs_in_from_yesterday(db, clock):
    p = db.add_project("A", "#1")
    day_start, day_end = day_of(clock)
    clock.t = day_start - 600             # 10 minutes before midnight
    db.start(p); clock.advance(1200); db.stop()   # 10 min yesterday, 10 min today
    assert db.totals(day_start, day_end) == {p: 600}
    db.reset_day(p, day_start, day_end)
    assert db.totals(day_start, day_end) == {}
    assert db.totals(day_start - DAY, day_start) == {p: 600}


def test_reset_day_restarts_a_running_timer_from_now(db, clock):
    p = db.add_project("A", "#1")
    day_start, day_end = day_of(clock)
    clock.t = day_start + 1000
    db.start(p)
    clock.advance(500)
    db.reset_day(p, day_start, day_end)
    running = db.running()
    assert running.project_id == p and running.start_ts == clock()
    assert db.totals(day_start, day_end) == {p: 0} or db.totals(day_start, day_end) == {}


def test_reset_day_on_a_timer_that_started_yesterday_keeps_yesterdays_part(db, clock):
    p = db.add_project("A", "#1")
    day_start, day_end = day_of(clock)
    clock.t = day_start - 900
    db.start(p)
    clock.t = day_start + 600
    db.reset_day(p, day_start, day_end)
    assert db.totals(day_start - DAY, day_start) == {p: 900}   # yesterday's part stays
    assert db.running().start_ts == clock()                    # and a new timer runs from now
    assert db.totals(day_start, day_end) in ({p: 0}, {})


# -- project order and archive ------------------------------------------------------------------

def names(db):
    return [p.name for p in db.list_projects()]


def test_move_project_swaps_with_the_neighbour(db):
    a, b, c = (db.add_project(n, "#1") for n in "ABC")
    assert db.move_project(b, -1) is True
    assert names(db) == ["B", "A", "C"]
    assert db.move_project(b, +1) is True
    assert names(db) == ["A", "B", "C"]


def test_move_project_stops_at_the_ends(db):
    a, b = db.add_project("A", "#1"), db.add_project("B", "#1")
    assert db.move_project(a, -1) is False
    assert db.move_project(b, +1) is False
    assert names(db) == ["A", "B"]


def test_move_project_skips_archived_neighbours(db):
    a, b, c = (db.add_project(n, "#1") for n in "ABC")
    db.archive_project(b)
    assert db.move_project(c, -1) is True
    assert names(db) == ["C", "A"]
    db.archive_project(b, False)               # B comes back where its order puts it
    assert names(db) == ["C", "B", "A"]         # sort orders were A=1 B=2 C=3, then C and A swapped


def test_archived_projects_lists_only_archived(db):
    a, b = db.add_project("A", "#1"), db.add_project("B", "#1")
    assert db.archived_projects() == []
    db.archive_project(a)
    assert [p.name for p in db.archived_projects()] == ["A"]
    db.archive_project(a, False)
    assert db.archived_projects() == []


# -- update_entry --------------------------------------------------------------------------------------

from timetracker.db import EntryError


def two_entries(db, clock):
    """Two finished entries: [t, t+600) and [t+1000, t+1600)."""
    a, b = db.add_project("A", "#1"), db.add_project("B", "#2")
    t = clock()
    e1 = db.start(a); clock.advance(600); db.stop()
    clock.advance(400)
    e2 = db.start(b); clock.advance(600); db.stop()
    clock.advance(100)
    return a, b, db.get_entry(e1.id), db.get_entry(e2.id), t


def test_update_entry_changes_project_note_and_times(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    updated = db.update_entry(e1.id, project_id=b, note="  fixed  ", start_ts=t - 100, end_ts=t + 500)
    assert (updated.project_id, updated.note, updated.start_ts, updated.end_ts) == (b, "fixed", t - 100, t + 500)
    assert db.get_entry(e1.id) == updated


def test_end_must_be_after_start(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    with pytest.raises(EntryError, match="after the start"):
        db.update_entry(e1.id, end_ts=e1.start_ts)
    with pytest.raises(EntryError, match="after the start"):
        db.update_entry(e1.id, start_ts=e1.end_ts + 5)
    assert db.get_entry(e1.id) == e1          # nothing changed


def test_nothing_may_lie_in_the_future(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    with pytest.raises(EntryError, match="future"):
        db.update_entry(e2.id, end_ts=clock() + 3600)
    db.update_entry(e2.id, end_ts=clock() + 30)           # a few seconds of clock slack are fine


def test_an_entry_may_not_overlap_another(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    with pytest.raises(EntryError, match="overlaps"):
        db.update_entry(e1.id, end_ts=e2.start_ts + 1)     # runs into the next entry
    with pytest.raises(EntryError, match="overlaps"):
        db.update_entry(e2.id, start_ts=e1.end_ts - 1)     # runs back into the previous one
    db.update_entry(e2.id, start_ts=e1.end_ts)             # touching (end == start) is fine
    assert db.get_entry(e2.id).start_ts == e1.end_ts


def test_a_note_or_project_change_ignores_existing_overlaps(db, clock):
    """Old data (e.g. from a clock set back) may already overlap: editing a note must still work."""
    a, b, e1, e2, t = two_entries(db, clock)
    db._conn.execute("UPDATE entries SET start_ts = ? WHERE id = ?", (e1.start_ts + 100, e2.id))   # force an overlap
    db.update_entry(e2.id, note="still editable", project_id=a)
    assert db.get_entry(e2.id).note == "still editable"


def test_a_running_timer_has_no_end_to_set_but_its_start_can_move(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    run = db.start(a)
    with pytest.raises(EntryError, match="no end"):
        db.update_entry(run.id, end_ts=clock() + 10)
    moved = db.update_entry(run.id, start_ts=run.start_ts - 50)
    assert moved.start_ts == run.start_ts - 50 and moved.end_ts is None
    with pytest.raises(EntryError, match="overlaps"):
        db.update_entry(run.id, start_ts=e2.start_ts + 10)  # back into the previous entry


def test_unknown_entry_project_and_fields(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    with pytest.raises(EntryError, match="no longer exists"):
        db.update_entry(9999, note="x")
    with pytest.raises(EntryError, match="project"):
        db.update_entry(e1.id, project_id=9999)
    with pytest.raises(ValueError):
        db.update_entry(e1.id, id=5)


def test_a_failed_update_changes_nothing(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    with pytest.raises(EntryError):
        db.update_entry(e1.id, project_id=b, note="x", end_ts=e1.start_ts)
    assert db.get_entry(e1.id) == e1


def test_totals_follow_an_edited_entry(db, clock):
    a, b, e1, e2, t = two_entries(db, clock)
    before = db.totals(t - 10, t + 5000)
    db.update_entry(e1.id, end_ts=e1.end_ts - 100)
    assert db.totals(t - 10, t + 5000)[a] == before[a] - 100
