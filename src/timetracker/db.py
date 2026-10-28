"""SQLite data layer.

Power can be pulled at any moment, so every change is its own committed
transaction (WAL journal, synchronous=FULL). A running timer is simply an
entry whose end_ts is NULL; its start timestamp survives a power cut, so the
elapsed time is still correct after reboot.
"""

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    color      TEXT    NOT NULL,
    archived   INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    start_ts   INTEGER NOT NULL,
    end_ts     INTEGER,
    note       TEXT    NOT NULL DEFAULT '',
    CHECK (end_ts IS NULL OR end_ts >= start_ts)
);
CREATE INDEX IF NOT EXISTS entries_start ON entries(start_ts);
-- At most one running entry: every row with end_ts NULL maps to the same key.
CREATE UNIQUE INDEX IF NOT EXISTS one_running
    ON entries((end_ts IS NULL)) WHERE end_ts IS NULL;
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class EntryError(ValueError):
    """An entry change was refused; the message says why and is shown to the user."""


FUTURE_TOLERANCE = 60  # seconds an entry time may be ahead of the clock
INFINITY = 2**62  # a running entry has no end yet: for overlap checks it lasts "forever"


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    color: str
    archived: bool
    sort_order: int


@dataclass(frozen=True)
class Entry:
    id: int
    project_id: int
    start_ts: int
    end_ts: int | None
    note: str


class Database:
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self._clock = clock
        if str(path) != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            path = Path(path).expanduser()
        # isolation_level=None: we issue BEGIN/COMMIT ourselves.
        self._conn = sqlite3.connect(str(path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def now(self) -> int:
        return int(self._clock())

    @contextmanager
    def _tx(self):
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    # -- projects ---------------------------------------------------------

    @staticmethod
    def _project(row: sqlite3.Row) -> Project:
        return Project(row["id"], row["name"], row["color"], bool(row["archived"]), row["sort_order"])

    def add_project(self, name: str, color: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("project name must not be empty")
        with self._tx():
            order = self._conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM projects").fetchone()[0]
            cur = self._conn.execute(
                "INSERT INTO projects(name, color, sort_order) VALUES (?, ?, ?)", (name, color, order)
            )
        return cur.lastrowid

    def get_project(self, project_id: int) -> Project | None:
        row = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._project(row) if row else None

    def list_projects(self, include_archived: bool = False) -> list[Project]:
        sql = "SELECT * FROM projects"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY sort_order, id"
        return [self._project(r) for r in self._conn.execute(sql)]

    def archived_projects(self) -> list[Project]:
        return [p for p in self.list_projects(include_archived=True) if p.archived]

    def move_project(self, project_id: int, direction: int) -> bool:
        """Swap a project's place with its neighbour among the visible ones (-1 left, +1 right).
        Returns False when it is already at that end."""
        visible = self.list_projects()
        ids = [p.id for p in visible]
        if project_id not in ids:
            return False
        i = ids.index(project_id)
        j = i + (1 if direction > 0 else -1)
        if not 0 <= j < len(visible):
            return False
        a, b = visible[i], visible[j]
        with self._tx():
            self._conn.execute("UPDATE projects SET sort_order = ? WHERE id = ?", (b.sort_order, a.id))
            self._conn.execute("UPDATE projects SET sort_order = ? WHERE id = ?", (a.sort_order, b.id))
        return True

    def rename_project(self, project_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("project name must not be empty")
        with self._tx():
            self._conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))

    def set_project_color(self, project_id: int, color: str) -> None:
        with self._tx():
            self._conn.execute("UPDATE projects SET color = ? WHERE id = ?", (color, project_id))

    def archive_project(self, project_id: int, archived: bool = True) -> None:
        """Hide a project from the main screen. A running timer on it is stopped."""
        with self._tx():
            if archived:
                self._stop_locked(self.now(), project_id=project_id)
            self._conn.execute("UPDATE projects SET archived = ? WHERE id = ?", (int(archived), project_id))

    def delete_project(self, project_id: int) -> None:
        """Delete a project together with all its entries."""
        with self._tx():
            self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    # -- timer ------------------------------------------------------------

    def running(self) -> Entry | None:
        row = self._conn.execute("SELECT * FROM entries WHERE end_ts IS NULL").fetchone()
        return self._entry(row) if row else None

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(row["id"], row["project_id"], row["start_ts"], row["end_ts"], row["note"])

    def _stop_locked(self, now: int, project_id: int | None = None) -> Entry | None:
        row = self._conn.execute("SELECT * FROM entries WHERE end_ts IS NULL").fetchone()
        if row is None or (project_id is not None and row["project_id"] != project_id):
            return None
        # If the clock was set back while running, never end before the start.
        end = max(now, row["start_ts"])
        self._conn.execute("UPDATE entries SET end_ts = ? WHERE id = ?", (end, row["id"]))
        return Entry(row["id"], row["project_id"], row["start_ts"], end, row["note"])

    def start(self, project_id: int) -> Entry:
        """Start a timer, stopping any other running one in the same transaction."""
        with self._tx():
            project = self._conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
            if project is None:
                raise ValueError(f"no such project: {project_id}")
            current = self._conn.execute("SELECT * FROM entries WHERE end_ts IS NULL").fetchone()
            if current is not None and current["project_id"] == project_id:
                return self._entry(current)
            now = self.now()
            self._stop_locked(now)
            cur = self._conn.execute(
                "INSERT INTO entries(project_id, start_ts) VALUES (?, ?)", (project_id, now)
            )
        return Entry(cur.lastrowid, project_id, now, None, "")

    def stop(self) -> Entry | None:
        """Stop the running timer. Returns the finished entry, or None if nothing ran."""
        with self._tx():
            return self._stop_locked(self.now())

    def reset_day(self, project_id: int, day_start: int, day_end: int) -> None:
        """Zero a project's total for one day.

        Entries inside the day are deleted, ones that run in from the day before are cut at
        midnight, and a running timer restarts from now (its earlier part of the day goes).
        """
        now = self.now()
        with self._tx():
            self._conn.execute(
                "DELETE FROM entries WHERE project_id = ? AND end_ts IS NOT NULL "
                "AND start_ts >= ? AND end_ts <= ?",
                (project_id, day_start, day_end),
            )
            self._conn.execute(
                "UPDATE entries SET end_ts = ? WHERE project_id = ? AND end_ts IS NOT NULL "
                "AND start_ts < ? AND end_ts > ? AND end_ts <= ?",
                (day_start, project_id, day_start, day_start, day_end),
            )
            run = self._conn.execute(
                "SELECT * FROM entries WHERE project_id = ? AND end_ts IS NULL", (project_id,)
            ).fetchone()
            if run is not None and run["start_ts"] >= day_start:
                self._conn.execute("UPDATE entries SET start_ts = ? WHERE id = ?", (now, run["id"]))
            elif run is not None:  # started before today: keep yesterday's part, restart now
                self._conn.execute("UPDATE entries SET end_ts = ? WHERE id = ?", (day_start, run["id"]))
                self._conn.execute(
                    "INSERT INTO entries(project_id, start_ts) VALUES (?, ?)", (project_id, now)
                )

    # -- entries ----------------------------------------------------------

    def get_entry(self, entry_id: int) -> Entry | None:
        row = self._conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return self._entry(row) if row else None

    def delete_entry(self, entry_id: int) -> None:
        """Remove one entry; its time no longer counts anywhere."""
        with self._tx():
            self._conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def update_entry(self, entry_id: int, **changes) -> Entry:
        """Change an entry's project_id, start_ts, end_ts and/or note.

        Time changes are checked: the end must be after the start, nothing may lie in the future,
        the entry must not overlap another one, and a running timer has no end to set. Raises
        EntryError (nothing is changed) when a rule is broken.
        """
        unknown = set(changes) - {"project_id", "start_ts", "end_ts", "note"}
        if unknown:
            raise ValueError(f"cannot change {sorted(unknown)}")
        with self._tx():
            row = self._conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise EntryError("This entry no longer exists.")
            new = {k: row[k] for k in ("project_id", "start_ts", "end_ts", "note")}
            new.update(changes)
            if "project_id" in changes and self._conn.execute(
                "SELECT 1 FROM projects WHERE id = ?", (new["project_id"],)
            ).fetchone() is None:
                raise EntryError("That project no longer exists.")
            if "end_ts" in changes and row["end_ts"] is None:
                raise EntryError("A running timer has no end yet.")
            if "start_ts" in changes or "end_ts" in changes:
                if new["end_ts"] is not None and new["end_ts"] <= new["start_ts"]:
                    raise EntryError("The end must be after the start.")
                limit = self.now() + FUTURE_TOLERANCE
                if new["start_ts"] > limit or (new["end_ts"] or 0) > limit:
                    raise EntryError("That time is in the future.")
                clash = self._conn.execute(
                    "SELECT 1 FROM entries WHERE id != ? AND start_ts < ? AND COALESCE(end_ts, ?) > ? LIMIT 1",
                    (entry_id, new["end_ts"] if new["end_ts"] is not None else INFINITY, INFINITY, new["start_ts"]),
                ).fetchone()
                if clash:
                    raise EntryError("That overlaps another entry.")
            self._conn.execute(
                "UPDATE entries SET project_id = ?, start_ts = ?, end_ts = ?, note = ? WHERE id = ?",
                (new["project_id"], new["start_ts"], new["end_ts"], str(new["note"]).strip(), entry_id),
            )
        return self.get_entry(entry_id)

    def set_note(self, entry_id: int, note: str) -> None:
        with self._tx():
            self._conn.execute("UPDATE entries SET note = ? WHERE id = ?", (note.strip(), entry_id))

    def entries_between(self, start: int, end: int) -> list[Entry]:
        """Entries overlapping [start, end), oldest first. A running entry counts up to now."""
        now = self.now()
        rows = self._conn.execute(
            "SELECT * FROM entries WHERE start_ts < ? AND COALESCE(end_ts, ?) > ? ORDER BY start_ts, id",
            (end, now, start),
        )
        return [self._entry(r) for r in rows]

    def totals(self, start: int, end: int) -> dict[int, int]:
        """Seconds per project within [start, end). Entries crossing the edges are clipped."""
        now = self.now()
        rows = self._conn.execute(
            """
            SELECT project_id,
                   SUM(MAX(0, MIN(COALESCE(end_ts, :now), :end) - MAX(start_ts, :start))) AS secs
            FROM entries
            WHERE start_ts < :end AND COALESCE(end_ts, :now) > :start
            GROUP BY project_id
            """,
            {"now": now, "start": start, "end": end},
        )
        return {r["project_id"]: r["secs"] for r in rows}

    def earliest_timestamp(self) -> int | None:
        """The start of the oldest entry, or None if there are no entries."""
        return self._conn.execute("SELECT MIN(start_ts) FROM entries").fetchone()[0]

    def latest_timestamp(self) -> int:
        """The newest start or end time of any entry, 0 if there are none."""
        row = self._conn.execute("SELECT MAX(start_ts), MAX(end_ts) FROM entries").fetchone()
        return max(row[0] or 0, row[1] or 0)

    def shift_running(self, delta: int, meta: dict[str, str] | None = None) -> None:
        """Move the running timer's start by delta seconds and save meta values, in one
        transaction. Used when the clock is set, so the elapsed time does not jump."""
        with self._tx():
            self._conn.execute("UPDATE entries SET start_ts = start_ts + ? WHERE end_ts IS NULL", (delta,))
            for key, value in (meta or {}).items():
                self._conn.execute(
                    "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    # -- meta -------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._tx():
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
