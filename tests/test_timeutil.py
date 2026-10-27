from datetime import datetime

from timetracker.timeutil import day_bounds


def test_day_bounds_contain_timestamp_and_span_a_day():
    ts = datetime(2026, 3, 14, 15, 9, 26).timestamp()
    start, end = day_bounds(ts)
    assert start <= ts < end
    assert datetime.fromtimestamp(start) == datetime(2026, 3, 14, 0, 0, 0)
    assert datetime.fromtimestamp(end) == datetime(2026, 3, 15, 0, 0, 0)


def test_day_bounds_at_exact_midnight():
    ts = datetime(2026, 1, 1, 0, 0, 0).timestamp()
    start, end = day_bounds(ts)
    assert start == ts
