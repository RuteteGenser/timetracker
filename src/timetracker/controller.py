"""Glue between the database, the knob/button and the QML screens."""

import time
from typing import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .db import Database
from .model import ProjectModel
from .nav import FIRST_PROJECT, SETTINGS, STYLE, StripNav
from .timeutil import day_bounds


class Controller(QObject):
    selectedChanged = Signal()
    viewOffsetChanged = Signal()
    screenChanged = Signal()
    projectCountChanged = Signal()

    def __init__(self, db: Database, clock: Callable[[], float] = time.time, parent=None):
        super().__init__(parent)
        self._db = db
        self._clock = clock
        self._nav = StripNav()
        self._screen = "main"
        self._last_second = -1
        self.projects = ProjectModel(self)
        self.reload_projects()

        self._ticker = QTimer(self)
        self._ticker.setInterval(100)  # cheap check; the DB is only read when the second changes
        self._ticker.timeout.connect(self._on_tick)
        self._ticker.start()

    # -- properties for QML -------------------------------------------------

    @Property(int, notify=selectedChanged)
    def selected(self):
        return self._nav.selected

    @Property(int, notify=viewOffsetChanged)
    def viewOffset(self):
        return self._nav.offset

    @Property(str, notify=screenChanged)
    def screen(self):
        return self._screen

    @Property(int, notify=projectCountChanged)
    def projectCount(self):
        return self._nav.project_count

    # -- data -----------------------------------------------------------------

    def reload_projects(self) -> None:
        projects = self._db.list_projects()
        self.projects.set_projects([{"id": p.id, "name": p.name, "color": p.color} for p in projects])
        before = (self._nav.selected, self._nav.offset)
        self._nav.set_project_count(len(projects))
        self._emit_nav_changes(before)
        self.projectCountChanged.emit()
        self._refresh_times()

    def _refresh_times(self) -> None:
        now = int(self._clock())
        self._last_second = now
        start, end = day_bounds(now)
        running = self._db.running()
        elapsed = max(0, now - running.start_ts) if running else 0
        self.projects.set_times(
            self._db.totals(start, end), running.project_id if running else None, elapsed
        )

    def _on_tick(self) -> None:
        if int(self._clock()) != self._last_second:
            self._refresh_times()

    # -- navigation -------------------------------------------------------------

    def _emit_nav_changes(self, before: tuple[int, int]) -> None:
        if self._nav.selected != before[0]:
            self.selectedChanged.emit()
        if self._nav.offset != before[1]:
            self.viewOffsetChanged.emit()

    @Slot(int)
    def turn(self, steps: int) -> None:
        """Knob turned: positive = clockwise = selection moves right."""
        if self._screen != "main":
            return
        before = (self._nav.selected, self._nav.offset)
        self._nav.move(steps)
        self._emit_nav_changes(before)

    @Slot()
    def press(self) -> None:
        """Knob button pressed."""
        if self._screen != "main":
            self.back()
        else:
            self._activate(self._nav.selected)

    @Slot(int)
    def tap(self, index: int) -> None:
        """Touchscreen tap on an item (same linear index as the knob uses)."""
        if self._screen != "main":
            return
        before = (self._nav.selected, self._nav.offset)
        self._nav.select(index)
        self._emit_nav_changes(before)
        self._activate(index)

    @Slot()
    def back(self) -> None:
        """Return to the main screen in its default view."""
        before = (self._nav.selected, self._nav.offset)
        self._nav.reset()
        self._emit_nav_changes(before)
        if self._screen != "main":
            self._screen = "main"
            self.screenChanged.emit()

    def _open(self, screen: str) -> None:
        self._screen = screen
        self.screenChanged.emit()

    def _activate(self, index: int) -> None:
        if index == SETTINGS:
            self._open("settings")
        elif index == STYLE:
            self._open("style")
        elif index >= FIRST_PROJECT:
            self._toggle(self.projects.project_id(index - FIRST_PROJECT))

    def _toggle(self, project_id: int) -> None:
        running = self._db.running()
        if running and running.project_id == project_id:
            self._db.stop()
        else:
            self._db.start(project_id)
        self._refresh_times()
