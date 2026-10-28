"""Glue between the database, the knob/button and the QML screens."""

import calendar
import time
from datetime import datetime
from typing import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .clock import ACK_REF, LAST_SEEN, ClockBackend, ClockError, check_clock, clock_reference
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
    "style": "main", "settings": "main", "reports": "main", "clockwarn": "main",
    "datetime": "settings", "status": "settings",
}
LIST_SCREENS = {"settings", "clockwarn"}
LIST_TITLES = {"settings": "Settings", "clockwarn": "Clock check"}

# Date & time screen: five fields, then Cancel and Save. The knob moves the outline over them;
# pressing a field edits it (turn changes the value, press again to finish).
DT_RANGES = [(2020, 2099), (1, 12), (1, 31), (0, 23), (0, 59)]  # year month day hour minute
DT_CANCEL = 5
DT_SAVE = 6
HEARTBEAT_SECONDS = 60


class Controller(QObject):
    selectedChanged = Signal()
    listChanged = Signal()
    dtChanged = Signal()
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
        self._backend = clock if isinstance(clock, ClockBackend) else None  # None: the clock cannot be set
        self._clock_problem = ""  # message of the clock warning being shown
        self._return_to: str | None = None  # where Back from Date & time goes, if not Settings
        self._dt_initial = [2026, 1, 1, 0, 0]
        self._dt_fields = list(self._dt_initial)
        self._dt_focus = 0
        self._dt_editing = False
        self._dt_error = ""
        self._last_seen = int(db.get_meta(LAST_SEEN) or 0)
        self._last_beat = 0
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

    @Property(str, notify=screenChanged)
    def listNote(self):
        return self._clock_problem if self._screen == "clockwarn" else ""

    @Property("QVariantList", notify=dtChanged)
    def dtFields(self):
        return self._dt_fields

    @Property(int, notify=dtChanged)
    def dtFocus(self):
        return self._dt_focus

    @Property(bool, notify=dtChanged)
    def dtEditing(self):
        return self._dt_editing

    @Property(str, notify=dtChanged)
    def dtError(self):
        return self._dt_error

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
        now = int(self._clock())
        if now != self._last_second:
            self._refresh_times()
            self._heartbeat(now)

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
            self._list = ListNav(len(self._list_rows), default=0 if screen == "clockwarn" else None)
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
        if screen == "clockwarn":
            return [row("datetime", "Set date and time"), row("ignore", "Ignore")]
        return []

    def _activate_list(self, index: int) -> None:
        if not 0 <= index < len(self._list_rows):
            return
        row_id = self._list_rows[index]["id"]
        if row_id == "back":
            self.back()
        elif row_id == "ignore":
            self._ignore_clock_problem()
        elif row_id == "datetime":
            self._open_datetime(return_to="main" if self._screen == "clockwarn" else None)
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
        if self._screen == "datetime":
            if self._dt_editing:
                self._dt_adjust(self._dt_focus, steps)
            else:
                self._dt_focus = max(0, min(DT_SAVE, self._dt_focus + steps))
            self.dtChanged.emit()
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
        elif self._screen == "datetime":
            self._dt_press()
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
        parent = self._return_to or SCREEN_PARENT.get(self._screen, "main")
        self._return_to = None
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

    # -- clock: sanity check and the Date & time screen -------------------------------------

    def _heartbeat(self, now: int) -> None:
        """Remember the latest time the clock showed, so a later jump backwards can be noticed.

        It only moves forward (setting the clock by hand resets it itself); a clock that has
        gone back must not drag the reference back with it. A big step back while running
        opens the warning straight away.
        """
        if now + 120 < self._last_seen:
            if self._screen not in ("clockwarn", "datetime") and not self._prompt_open():
                self.run_clock_check()
            return
        if self._screen != "clockwarn" and now > self._last_seen and now - self._last_beat >= HEARTBEAT_SECONDS:
            self._last_beat = now
            self._last_seen = now
            self._db.set_meta(LAST_SEEN, str(now))

    @Slot()
    def run_clock_check(self) -> None:
        """Warn when the clock looks wrong (called once at start, and when it jumps back)."""
        problem = check_clock(self._db, int(self._clock()))
        if problem:
            self._clock_problem = problem
            self._open_screen("clockwarn")

    def _ignore_clock_problem(self) -> None:
        """Dismiss the warning: it will not come back until the clock reference moves on."""
        self._db.set_meta(ACK_REF, str(clock_reference(self._db)))
        self._last_seen = int(self._clock())
        self._db.set_meta(LAST_SEEN, str(self._last_seen))
        self._clock_problem = ""
        self.back()

    def _open_datetime(self, return_to: str | None = None) -> None:
        now = datetime.fromtimestamp(self._clock())
        self._dt_initial = [now.year, now.month, now.day, now.hour, now.minute]
        self._dt_fields = list(self._dt_initial)
        self._dt_focus = 0
        self._dt_editing = False
        self._dt_error = ""
        self._return_to = return_to
        self.dtChanged.emit()
        self._set_screen("datetime")

    def _dt_adjust(self, field: int, delta: int) -> None:
        year, month, day, hour, minute = self._dt_fields
        if field == 0:
            year = max(DT_RANGES[0][0], min(DT_RANGES[0][1], year + delta))
        elif field == 1:
            month = (month - 1 + delta) % 12 + 1
        elif field == 2:
            days = calendar.monthrange(year, month)[1]
            day = (day - 1 + delta) % days + 1
        elif field == 3:
            hour = (hour + delta) % 24
        else:
            minute = (minute + delta) % 60
        day = min(day, calendar.monthrange(year, month)[1])  # 31 Jan -> Feb becomes 28/29
        self._dt_fields = [year, month, day, hour, minute]
        self._dt_error = ""

    def _dt_press(self) -> None:
        if self._dt_focus < DT_CANCEL:
            self._dt_editing = not self._dt_editing
            self.dtChanged.emit()
        elif self._dt_focus == DT_CANCEL:
            self.back()
        else:
            self.dtSave()

    @Slot(int)
    def dtTap(self, field: int) -> None:
        """Touch: tap a field to select it (and start or stop editing it)."""
        if self._screen == "datetime" and 0 <= field < DT_CANCEL:
            self._dt_editing = not self._dt_editing if self._dt_focus == field else True
            self._dt_focus = field
            self.dtChanged.emit()

    @Slot(int, int)
    def dtAdjust(self, field: int, delta: int) -> None:
        """Touch: the + and - buttons above and below a field."""
        if self._screen == "datetime" and 0 <= field < DT_CANCEL:
            self._dt_adjust(field, delta)
            self._dt_focus = field
            self.dtChanged.emit()

    @Slot()
    def dtSave(self) -> None:
        """Set the clock to the chosen date and time. A running timer keeps its elapsed time."""
        if self._dt_fields == self._dt_initial:
            self.back()
            return
        year, month, day, hour, minute = self._dt_fields
        if self._backend is None:
            self._dt_error = "This clock cannot be set."
            self.dtChanged.emit()
            return
        try:
            self._backend.set_time(self._db, int(datetime(year, month, day, hour, minute).timestamp()))
        except ClockError as exc:
            self._dt_error = str(exc)
            self.dtChanged.emit()
            return
        self._last_seen = int(self._clock())
        self._clock_problem = ""
        self._refresh_times()
        self.back()
