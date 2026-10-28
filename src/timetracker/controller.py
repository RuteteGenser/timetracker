"""Glue between the database, the knob/button and the QML screens."""

import time
from datetime import datetime
from typing import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .colors import next_color
from .db import Database, Entry
from .model import ProjectModel
from .nav import FIRST_PROJECT, REPORTS, SETTINGS, STYLE, ListNav, StripNav
from .timeutil import day_bounds

# Text prompt buttons, left to right; the knob button presses the focused one.
# The note prompt has all three, the rename prompt only Cancel (= NOTE_SKIP) and Save.
NOTE_DELETE = 0
NOTE_SKIP = 1
NOTE_SAVE = 2
NOTE_MAX_LENGTH = 200

# Style screen: every card has three parts, in the order the knob visits them.
STYLE_PARTS = 3
PART_COLOR = 0
PART_NAME = 1
PART_TIME = 2


# Screens: "main", "style", list screens (vertical rows, knob scrolls) and detail screens.
SCREEN_PARENT = {  # where Back goes
    "style": "main", "settings": "main", "reports": "main",
    "datetime": "settings", "status": "settings",
}
LIST_SCREENS = {"settings"}
LIST_TITLES = {"settings": "Settings"}


class Controller(QObject):
    selectedChanged = Signal()
    listChanged = Signal()
    viewOffsetChanged = Signal()
    screenChanged = Signal()
    projectCountChanged = Signal()
    noteChanged = Signal()
    resetArmedChanged = Signal()

    def __init__(self, db: Database, clock: Callable[[], float] = time.time, parent=None):
        super().__init__(parent)
        self._db = db
        self._clock = clock
        self._nav = StripNav()
        self._screen = "main"  # a key of SCREEN_PARENT, or "main"
        self._list = ListNav()
        self._list_rows: list[dict] = []  # rows of the current list screen: {id, label, value}
        self._last_second = -1
        self._note_entry: Entry | None = None  # finished entry waiting for its note
        self._rename_id: int | None = None  # project being renamed (same prompt, other mode)
        self._rename_row = -1
        self._note_text = ""
        self._note_focus = NOTE_SKIP
        self._delete_armed = False  # Delete was pressed once and waits for confirmation
        self._reset_armed_index: int | None = None  # Style item whose time reset awaits confirmation
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

    @Property(int, notify=selectedChanged)
    def selectedCard(self):
        """Card of the selection, -1 while a column item (Settings, Style, Back) is selected."""
        return self._nav.card_and_part()[0]

    @Property(int, notify=selectedChanged)
    def selectedPart(self):
        """Style screen: 0 colour, 1 name, 2 time. -1 on the main screen or in the column."""
        return self._nav.card_and_part()[1] if self._screen == "style" else -1

    @Property(int, constant=True)
    def firstItem(self):
        """Selection index of the first project card on the main screen."""
        return FIRST_PROJECT

    @Property(bool, notify=screenChanged)
    def screenIsList(self):
        return self._screen in LIST_SCREENS

    @Property(str, notify=screenChanged)
    def listTitle(self):
        return LIST_TITLES.get(self._screen, "")

    @Property("QVariantList", notify=listChanged)
    def listRows(self):
        return self._list_rows

    @Property(int, notify=listChanged)
    def listSelected(self):
        return self._list.selected

    @Property(int, notify=listChanged)
    def listOffset(self):
        return self._list.offset

    @Property(bool, notify=resetArmedChanged)
    def resetArmed(self):
        return self._reset_armed_index is not None and self._reset_armed_index == self._nav.selected

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
        return self._prompt_open()

    @Property(str, notify=noteChanged)
    def noteKind(self):
        return "rename" if self._rename_id is not None else "note"

    @Property(str, notify=noteChanged)
    def noteText(self):
        return self._note_text

    @Property(int, notify=noteChanged)
    def noteFocus(self):
        return self._note_focus

    @Property(bool, notify=noteChanged)
    def noteDeleteArmed(self):
        return self._delete_armed

    @Property(str, notify=noteChanged)
    def noteProject(self):
        project_id = self._rename_id if self._rename_id is not None else (
            self._note_entry.project_id if self._note_entry is not None else None
        )
        project = self._db.get_project(project_id) if project_id is not None else None
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
            self._disarm_reset()  # moving the selection cancels a pending time reset
        if self._nav.offset != before[1]:
            self.viewOffsetChanged.emit()

    def _use_nav(self, nav: StripNav) -> None:
        self._nav = nav
        self.selectedChanged.emit()
        self.viewOffsetChanged.emit()
        self._disarm_reset()

    def _set_screen(self, screen: str) -> None:
        if screen != self._screen:
            self._screen = screen
            self.screenChanged.emit()

    def _open_screen(self, screen: str) -> None:
        """Show a screen; list screens get fresh rows and selection."""
        if screen in LIST_SCREENS:
            self._list_rows = self._rows_for(screen)
            self._list = ListNav(len(self._list_rows))
            self.listChanged.emit()
        self._set_screen(screen)

    def _rows_for(self, screen: str) -> list[dict]:
        def row(id_: str, label: str, value: str = "") -> dict:
            return {"id": id_, "label": label, "value": value}

        if screen == "settings":
            now = datetime.fromtimestamp(self._clock())
            return [
                row("back", "Back"),
                row("datetime", "Date & time", now.strftime("%d %b %Y  %H:%M")),
                row("status", "Status"),
            ]
        return []

    def _activate_list(self, index: int) -> None:
        if not 0 <= index < len(self._list_rows):
            return
        row_id = self._list_rows[index]["id"]
        if row_id == "back":
            self.back()
        else:
            self._open_screen(row_id)

    @Slot(int)
    def turn(self, steps: int) -> None:
        """Knob turned: positive = clockwise = selection moves right."""
        if self._prompt_open():
            # In a text prompt the knob moves the focus between its buttons.
            lowest = NOTE_SKIP if self._rename_id is not None else NOTE_DELETE
            focus = max(lowest, min(NOTE_SAVE, self._note_focus + steps))
            if focus != self._note_focus:
                self._note_focus = focus
                self._delete_armed = False  # moving away cancels a pending delete
                self.noteChanged.emit()
            return
        if self._screen in LIST_SCREENS:
            self._list.move(steps)
            self.listChanged.emit()
            return
        if self._screen not in ("main", "style"):
            return
        before = (self._nav.selected, self._nav.offset)
        self._nav.move(steps)
        self._emit_nav_changes(before)

    @Slot()
    def press(self) -> None:
        """Knob button pressed."""
        if self._prompt_open():
            {NOTE_DELETE: self.noteDelete, NOTE_SKIP: self.noteSkip, NOTE_SAVE: self.noteSave}[self._note_focus]()
        elif self._screen in LIST_SCREENS:
            self._activate_list(self._list.selected)
        elif self._screen not in ("main", "style"):
            self.back()  # placeholder screens: any press goes back
        else:
            self._activate(self._nav.selected)

    @Slot(int)
    def tap(self, index: int) -> None:
        """Touchscreen tap on an item (same item index as the knob uses)."""
        if self._prompt_open():
            return
        if self._screen in LIST_SCREENS:
            self._list.select(index)
            self.listChanged.emit()
            self._activate_list(index)
            return
        if self._screen not in ("main", "style"):
            return
        before = (self._nav.selected, self._nav.offset)
        self._nav.select(index)
        self._emit_nav_changes(before)
        self._activate(index)

    @Slot()
    def back(self) -> None:
        """Go up one level; the main screen comes back in its default view."""
        parent = SCREEN_PARENT.get(self._screen, "main")
        if parent == "main":
            self._use_nav(StripNav(self._nav.project_count))
            self._set_screen("main")
        else:
            self._open_screen(parent)

    def _activate(self, index: int) -> None:
        if self._screen == "style":
            self._activate_style(index)
        elif index == SETTINGS:
            self._open_screen("settings")
        elif index == REPORTS:
            self._open_screen("reports")
        elif index == STYLE:
            self._use_nav(StripNav(self._nav.project_count, column_items=1, parts=STYLE_PARTS))
            self._set_screen("style")
        elif index >= FIRST_PROJECT:
            self._toggle(self.projects.project_id(index - FIRST_PROJECT))

    # -- main screen: start / stop ----------------------------------------------------

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

    # -- style screen ----------------------------------------------------------------

    def _activate_style(self, index: int) -> None:
        if index == 0:  # the Back button in the column
            self.back()
            return
        card, part = divmod(index - 1, STYLE_PARTS)
        if part == PART_COLOR:
            self._cycle_color(card)
        elif part == PART_NAME:
            self._open_rename(card)
        else:
            self._reset_time(card, index)

    def _cycle_color(self, card: int) -> None:
        project_id = self.projects.project_id(card)
        project = self._db.get_project(project_id)
        color = next_color(project.color)
        self._db.set_project_color(project_id, color)
        self.projects.set_color(card, color)

    def _reset_time(self, card: int, index: int) -> None:
        """Zero today's total of a project. The first press only arms it, the second does it."""
        if self._reset_armed_index != index:
            self._reset_armed_index = index
            self.resetArmedChanged.emit()
            return
        self._disarm_reset()
        start, end = day_bounds(self._clock())
        self._db.reset_day(self.projects.project_id(card), start, end)
        self._refresh_times()

    def _disarm_reset(self) -> None:
        if self._reset_armed_index is not None:
            self._reset_armed_index = None
            self.resetArmedChanged.emit()

    # -- text prompt: note after a stop, or renaming a project ------------------------------

    def _prompt_open(self) -> bool:
        return self._note_entry is not None or self._rename_id is not None

    def _open_note(self, entry: Entry) -> None:
        self._note_entry = entry
        self._note_text = ""
        self._note_focus = NOTE_SKIP  # one button press skips
        self._delete_armed = False
        self.noteChanged.emit()

    def _open_rename(self, card: int) -> None:
        project = self._db.get_project(self.projects.project_id(card))
        self._rename_id = project.id
        self._rename_row = card
        self._note_text = project.name
        self._note_focus = NOTE_SKIP  # Cancel: one button press changes nothing
        self._delete_armed = False
        self.noteChanged.emit()

    def _close_note(self) -> None:
        self._note_entry = None
        self._rename_id = None
        self._note_text = ""
        self._note_focus = NOTE_SKIP
        self._delete_armed = False
        self.noteChanged.emit()

    @Slot(str)
    def noteType(self, text: str) -> None:
        if self._prompt_open():
            self._note_text = (self._note_text + text)[:NOTE_MAX_LENGTH]
            self._delete_armed = False
            self.noteChanged.emit()

    @Slot()
    def noteBackspace(self) -> None:
        if self._prompt_open() and self._note_text:
            self._note_text = self._note_text[:-1]
            self._delete_armed = False
            self.noteChanged.emit()

    @Slot()
    def noteSave(self) -> None:
        if self._rename_id is not None:
            name = self._note_text.strip()
            if name:
                self._db.rename_project(self._rename_id, name)
                self.projects.set_name(self._rename_row, name)
            self._close_note()
        elif self._note_entry is not None:
            if self._note_text.strip():
                self._db.set_note(self._note_entry.id, self._note_text)
            self._close_note()

    @Slot()
    def noteSkip(self) -> None:
        """Skip the note, or cancel the rename."""
        if self._prompt_open():
            self._close_note()

    @Slot()
    def noteDelete(self) -> None:
        """Discard the entry that was just stopped (its time does not count).

        The first call only arms the button; the second one deletes.
        """
        if self._note_entry is None:
            return
        if not self._delete_armed:
            self._delete_armed = True
            self.noteChanged.emit()
            return
        self._db.delete_entry(self._note_entry.id)
        self._close_note()
        self._refresh_times()
