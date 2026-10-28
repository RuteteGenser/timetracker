import pytest

from timetracker.clock import ClockBackend
from timetracker.db import Database


class FakeClock(ClockBackend):
    """A clock the test controls; it can also be 'set' like the real ones (after 2026, so it looks sane)."""

    def __init__(self, t=1_800_000_000):
        self.t = t

    def now(self):
        return self.t

    def _set(self, new_ts):
        self.t = new_ts

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def db(tmp_path, clock):
    d = Database(tmp_path / "t.db", clock=clock)
    yield d
    d.close()
