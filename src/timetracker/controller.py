"""Glue between the database, the knob/button and the QML screens."""

import time
from typing import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .db import Database, Entry
from .model import ProjectModel
from .nav import FIRST_PROJECT, SETTINGS, STYLE, StripNav
from .timeutil import day_bounds


NOTE_DELETE = 0  # note prompt buttons, left to right; the knob button presses the focused one
NOTE_SKIP = 1
NOTE_SAVE = 2
NOTE_MAX_LENGTH = 200


class Controller(QObject):
    selectedChanged = Signal()
    viewOffsetChanged = Signal()
    screenChanged = Signal()
    projectCountChanged = Signal()
    noteChanged = Signal()

    def __init__(self, db: Database, clock: Callable[[], float] = time.time, parent=None):
        super().__init__(parent)
        self._db = db
        self._clock = clock
        self._nav = StripNav()
        self._screen = "main"
        self._last_second = -1
        self._note_entry: Entry | None = None  # finished entry waiting for its note
        self._note_text = ""
        self._note_focus = NOTE_SKIP
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

    @Property(bool, notify=noteChanged)
    def notePromptOpen(self):
        return self._note_entry is not None

    @Property(str, notify=noteChanged)
    def noteText(self):
        return self._note_text

    @Property(int, notify=noteChanged)
    def noteFocus(self):
        return self._note_focus

    @Property(str, notify=noteChanged)
    def noteProject(self):
        if self._note_entry is None:
            return ""
        project = self._db.get_project(self._note_entry.project_id)
        return project.name if project else ""

    @Property(int, notify=noteChanged)
    def noteSeconds(self):
        e = self._note_entry
        return 0 if e is None or e.end_ts is None else e.end_ts - e.start_ts

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
        if self._note_entry is not None:
            # In the note prompt the knob moves the focus between Delete, Skip and Save.
            self._note_focus = max(NOTE_DELETE, min(NOTE_SAVE, self._note_focus + steps))
            self.noteChanged.emit()
            return
        if self._screen != "main":
            return
        before = (self._nav.selected, self._nav.offset)
        self._nav.move(steps)
        self._emit_nav_changes(before)

    @Slot()
    def press(self) -> None:
        """Knob button pressed."""
        if self._note_entry is not None:
            {NOTE_DELETE: self.noteDelete, NOTE_SKIP: self.noteSkip, NOTE_SAVE: self.noteSave}[self._note_focus]()
        elif self._screen != "main":
            self.back()
        else:
            self._activate(self._nav.selected)

    @Slot(int)
    def tap(self, index: int) -> None:
        """Touchscreen tap on an item (same linear index as the knob uses)."""
        if self._screen != "main" or self._note_entry is not None:
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
            finished = self._db.stop()
        else:
            self._db.start(project_id)  # also ends the previously running entry
            finished = self._db.get_entry(running.id) if running else None
        self._refresh_times()
        if finished is not None:
            self._open_note(finished)

    # -- note prompt ---------------------------------------------------------------

    def _open_note(self, entry: Entry) -> None:
        self._note_entry = entry
        self._note_text = ""
        self._note_focus = NOTE_SKIP  # one button press skips
        self.noteChanged.emit()

    def _close_note(self) -> None:
        self._note_entry = None
        self._note_text = ""
        self._note_focus = NOTE_SKIP
        self.noteChanged.emit()

    @Slot(str)
    def noteType(self, text: str) -> None:
        if self._note_entry is not None:
            self._note_text = (self._note_text + text)[:NOTE_MAX_LENGTH]
            self.noteChanged.emit()

    @Slot()
    def noteBackspace(self) -> None:
        if self._note_entry is not None and self._note_text:
            self._note_text = self._note_text[:-1]
            self.noteChanged.emit()

    @Slot()
    def noteSave(self) -> None:
        if self._note_entry is not None:
            if self._note_text.strip():
                self._db.set_note(self._note_entry.id, self._note_text)
            self._close_note()

    @Slot()
    def noteSkip(self) -> None:
        if self._note_entry is not None:
            self._close_note()

    @Slot()
    def noteDelete(self) -> None:
        """Discard the entry that was just stopped: its time does not count."""
        if self._note_entry is not None:
            self._db.delete_entry(self._note_entry.id)
            self._close_note()
            self._refresh_times()
