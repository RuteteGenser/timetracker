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
