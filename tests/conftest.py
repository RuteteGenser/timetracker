import pytest

from timetracker.db import Database


class FakeClock:
    def __init__(self, t=1_700_000_000):
        self.t = t

    def __call__(self):
        return self.t

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
