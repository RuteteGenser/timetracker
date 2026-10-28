"""Where "now" comes from, how the user can set it, and whether it can be trusted.

The Pi has no internet to ask, so the time may be wrong after a power cut (no RTC battery) or
jump backwards. Two backends:
  * OffsetClock: for development on a PC. The system clock is left alone; the app keeps an offset.
  * SystemClock: on the Pi. Sets the real clock (and the RTC) through a small root helper.
"""

import subprocess
import time
from datetime import datetime

LAST_SEEN = "last_seen"  # meta key: the latest time the app has seen the clock show
LAST_CHANGE = "last_clock_change"  # meta key: "old,new" epoch seconds of the last manual change
ACK_REF = "clock_ack_ref"  # meta key: a "behind" warning was dismissed up to this time
CLOCK_OFFSET = "clock_offset"  # meta key: OffsetClock's offset in seconds

# The software was made in 2026: an earlier date means the clock lost its time.
MIN_PLAUSIBLE = int(datetime(2026, 1, 1).timestamp())
TOLERANCE = 120  # seconds the clock may look behind before we warn


class ClockError(Exception):
    """The clock could not be set; the message is shown to the user."""


class ClockBackend:
    def now(self) -> float:
        raise NotImplementedError

    def __call__(self) -> float:  # usable wherever a plain clock function is expected
        return self.now()

    def _set(self, new_ts: int) -> None:
        raise NotImplementedError

    def set_time(self, db, new_ts: int) -> int:
        """Set the clock to new_ts. A running timer keeps its elapsed time (its start moves
        by the same amount). Returns how far the clock moved, in seconds."""
        old = int(self.now())
        delta = new_ts - old
        self._set(new_ts)
        db.shift_running(delta, {LAST_SEEN: str(new_ts), LAST_CHANGE: f"{old},{new_ts}"})
        return delta


class OffsetClock(ClockBackend):
    def __init__(self, offset: float = 0.0):
        self.offset = offset

    def bind(self, db) -> None:
        """Load the saved offset; the database was created with this clock, so call this after."""
        saved = db.get_meta(CLOCK_OFFSET)
        self.offset = float(saved) if saved else 0.0

    def now(self) -> float:
        return time.time() + self.offset

    def set_time(self, db, new_ts: int) -> int:
        old = int(self.now())
        delta = new_ts - old
        offset = self.offset + delta
        # the offset and the running timer's new start are saved together
        db.shift_running(delta, {CLOCK_OFFSET: repr(offset), LAST_SEEN: str(new_ts), LAST_CHANGE: f"{old},{new_ts}"})
        self.offset = offset
        return delta


class SystemClock(ClockBackend):
    HELPER = ["sudo", "-n", "/usr/local/bin/timetracker-set-time"]

    def now(self) -> float:
        return time.time()

    def _set(self, new_ts: int) -> None:
        try:
            subprocess.run([*self.HELPER, str(new_ts)], check=True, capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ClockError(f"Could not set the clock ({exc.__class__.__name__}). Is the helper installed?") from exc


def make_clock(driver: str) -> ClockBackend:
    if driver == "offset":
        return OffsetClock()
    if driver == "system":
        return SystemClock()
    raise ValueError(f"unknown clock driver: {driver!r} (use 'offset' or 'system')")


def clock_reference(db) -> int:
    """The latest time the app knows about: the heartbeat or the newest entry, whichever is later."""
    seen = int(db.get_meta(LAST_SEEN) or 0)
    return max(seen, db.latest_timestamp())


def _span(seconds: int) -> str:
    seconds = abs(int(seconds))
    if seconds < 3600:
        return f"{max(1, seconds // 60)} min"
    if seconds < 2 * 86400:
        return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"
    return f"{seconds // 86400} days"


def check_clock(db, now: int) -> str:
    """A message when the clock looks wrong, otherwise ''."""
    if now < MIN_PLAUSIBLE:
        return f"The date looks too early ({datetime.fromtimestamp(now):%d %b %Y}). The clock probably lost its time."
    ref = clock_reference(db)
    if ref > int(db.get_meta(ACK_REF) or 0) and now < ref - TOLERANCE:
        return f"The clock is {_span(ref - now)} behind the last recorded time ({datetime.fromtimestamp(ref):%d %b %H:%M})."
    return ""
