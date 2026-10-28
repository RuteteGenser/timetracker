import time

import pytest

from timetracker.clock import (ACK_REF, LAST_CHANGE, LAST_SEEN, MIN_PLAUSIBLE, OffsetClock, SystemClock,
                               check_clock, clock_reference, make_clock)
from timetracker.db import Database


def test_set_time_moves_the_clock_and_shifts_the_running_timer(db, clock):
    p = db.add_project("A", "#1")
    db.start(p)
    clock.advance(600)                         # 10 minutes elapsed
    before = clock() - db.running().start_ts
    delta = clock.set_time(db, clock() + 5 * 3600)   # clock set 5 hours forward
    assert delta == 5 * 3600
    assert clock() - db.running().start_ts == before   # elapsed time did not jump


def test_set_time_backwards_also_keeps_elapsed(db, clock):
    p = db.add_project("A", "#1")
    db.start(p)
    clock.advance(90)
    clock.set_time(db, clock() - 3 * 86400)
    assert clock() - db.running().start_ts == 90


def test_set_time_records_the_change_and_resets_the_heartbeat(db, clock):
    old = clock()
    clock.set_time(db, old - 7200)
    assert db.get_meta(LAST_SEEN) == str(old - 7200)
    assert db.get_meta(LAST_CHANGE) == f"{old},{old - 7200}"


def test_finished_entries_are_not_touched_by_a_clock_change(db, clock):
    p = db.add_project("A", "#1")
    e = db.start(p)
    clock.advance(60)
    db.stop()
    clock.set_time(db, clock() + 1000)
    kept = db.get_entry(e.id)
    assert (kept.start_ts, kept.end_ts) == (e.start_ts, e.start_ts + 60)


def test_shift_running_is_one_transaction(db, clock):
    p = db.add_project("A", "#1")
    db.start(p)
    start = db.running().start_ts
    with pytest.raises(Exception):
        db.shift_running(100, {"k": None})     # a NULL value violates NOT NULL, so the insert fails
    assert db.running().start_ts == start        # ...and the shift was rolled back with it


def test_offset_clock_persists_across_restarts(tmp_path):
    path = tmp_path / "t.db"
    clock = OffsetClock()
    db = Database(path, clock=clock)
    clock.bind(db)
    target = int(time.time()) + 86400
    clock.set_time(db, target)
    assert abs(clock() - target) < 2
    db.close()
    clock2 = OffsetClock()
    db2 = Database(path, clock=clock2)
    clock2.bind(db2)
    assert abs(clock2() - target) < 2
    db2.close()


def test_offset_clock_shifts_running_timer_atomically(tmp_path):
    clock = OffsetClock()
    db = Database(tmp_path / "t.db", clock=clock)
    clock.bind(db)
    p = db.add_project("A", "#1")
    db.start(p)
    elapsed = clock() - db.running().start_ts
    clock.set_time(db, int(clock()) + 7200)
    assert abs((clock() - db.running().start_ts) - elapsed) < 2
    db.close()


def test_make_clock():
    assert isinstance(make_clock("offset"), OffsetClock)
    assert isinstance(make_clock("system"), SystemClock)
    with pytest.raises(ValueError):
        make_clock("nope")


# -- sanity check ----------------------------------------------------------------------------

def test_a_fresh_database_with_a_sane_clock_is_fine(db, clock):
    assert check_clock(db, clock()) == ""


def test_a_date_before_the_software_existed_is_flagged(db):
    assert "too early" in check_clock(db, MIN_PLAUSIBLE - 86400)


def test_clock_behind_the_last_seen_time_is_flagged(db, clock):
    db.set_meta(LAST_SEEN, str(clock()))
    problem = check_clock(db, clock() - 3 * 3600)
    assert "3 h 00 min behind" in problem


def test_small_differences_are_tolerated(db, clock):
    db.set_meta(LAST_SEEN, str(clock()))
    assert check_clock(db, clock() - 60) == ""


def test_clock_behind_the_newest_entry_is_flagged_even_without_heartbeat(db, clock):
    p = db.add_project("A", "#1")
    db.start(p)
    clock.advance(1000)
    db.stop()
    assert "behind" in check_clock(db, clock() - 86400)


def test_dismissing_a_warning_silences_it_until_the_reference_moves_on(db, clock):
    db.set_meta(LAST_SEEN, str(clock()))
    now = clock() - 5 * 3600
    assert check_clock(db, now) != ""
    db.set_meta(ACK_REF, str(clock_reference(db)))
    assert check_clock(db, now) == ""
    db.set_meta(LAST_SEEN, str(clock() + 100))          # a later time is recorded: warn again
    assert check_clock(db, now) != ""


def test_latest_timestamp(db, clock):
    assert db.latest_timestamp() == 0
    p = db.add_project("A", "#1")
    e = db.start(p)
    assert db.latest_timestamp() == e.start_ts
    clock.advance(50)
    db.stop()
    assert db.latest_timestamp() == e.start_ts + 50
