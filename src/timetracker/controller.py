"""Glue between the database, the knob/button and the QML screens."""

import calendar
import shutil
import time
from datetime import datetime
from typing import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from . import __version__
from .clock import ACK_REF, LAST_CHANGE, LAST_SEEN, ClockBackend, ClockError, check_clock, clock_reference
from .colors import COLOR_CYCLE, next_color
from .db import Database, Entry, EntryError
from .hardware import rtc_info
from .model import ProjectModel
from .nav import FIRST_PROJECT, REPORTS, SETTINGS, STYLE, ListNav, StripNav
from .summaries import KINDS, grouped_entries, period_bounds, shift_period, step_limits, summary
from .timeutil import day_bounds, span_text

# Text prompt buttons, left to right; the knob button presses the focused one.
# The note prompt has all three, the rename prompt only Cancel (= NOTE_SKIP) and Save.
NOTE_DELETE = 0
NOTE_SKIP = 1
NOTE_SAVE = 2
NOTE_MAX_LENGTH = 200

# Style screen: column items Back and Archived, then four parts per card in the order the knob
# visits them, then a trailing "+" card that adds a project.
STYLE_COLUMN = 2
STYLE_PARTS = 4
PART_COLOR = 0
PART_NAME = 1
PART_TIME = 2
PART_MORE = 3


# Screens: "main", "style", list screens (vertical rows, knob scrolls) and detail screens.
SCREEN_PARENT = {  # where Back goes
    "style": "main", "settings": "main", "reports": "main", "clockwarn": "main",
    "datetime": "settings", "status": "settings",
    "projectmenu": "style", "archived": "style", "archivedmenu": "archived",
    "entries": "reports", "entryedit": "entries",
}
LIST_SCREENS = {"settings", "clockwarn", "projectmenu", "archived", "archivedmenu", "entries", "entryedit", "status"}
LIST_TITLES = {"settings": "Settings", "clockwarn": "Clock check", "archived": "Archived projects", "status": "Status"}
NOTE_LISTS = {"clockwarn", "entryedit"}  # list screens with an explanation under the title

# Date & time screen: five fields, then Cancel and Save. The knob moves the outline over them;
# pressing a field edits it (turn changes the value, press again to finish).
DT_RANGES = [(2020, 2099), (1, 12), (1, 31), (0, 23), (0, 59)]  # year month day hour minute
DT_CANCEL = 5
DT_SAVE = 6
HEARTBEAT_SECONDS = 60

# Reports screen. The period is "live" when the screen opens: turning the knob goes to the previous or
# next period. Pressing the period leaves live mode ("move"): turning then walks the focus over the
# controls and down the entry list; pressing the period again, or a Day / Week / Month button, is live
# again. Focusable items left to right: Back, the three period kinds, Entries (the entries
# of the period shown) and the period itself: pressing the period starts "stepping", where the knob
# moves to older / newer periods.
REP_BACK = 0
REP_ENTRIES = 4
REP_PERIOD = 5
REP_ITEMS = 6  # the top controls; focus REP_ITEMS + k is the k-th entry of the list below them


class Controller(QObject):
    selectedChanged = Signal()
    listChanged = Signal()
    dtChanged = Signal()
    repChanged = Signal()
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
        self._rep_kind = "day"
        self._rep_anchor = 0  # any moment inside the period being shown
        self._rep_focus = REP_PERIOD
        self._rep_stepping = True  # "live" mode: the knob changes the period
        self._rep_data: dict = {"label": "", "total": 0, "rows": []}
        self._rep_items: list[dict] = []  # the grouped list shown under the controls (headers and entries)
        self._rep_entries: list[int] = []  # entry ids in the order they appear in that list
        self._rep_limits = (0, 0)
        self._entry_id: int | None = None  # entry open in the editor
        self._entry_error = ""  # why the last change to it was refused
        self._entry_origin = "entries"  # where Back from the entry editor goes: "entries" or "reports"
        self._entry_note = False  # the text prompt is editing that entry's note
        self._dt_entry_field: str | None = None  # "start" or "end" while Date & time edits an entry
        self._list_memory: dict[str, int] = {}  # selected row of list screens we left, restored on Back
        self._last_second = -1
        self._note_entry: Entry | None = None  # finished entry waiting for its note
        self._rename_id: int | None = None  # project being renamed (same prompt, other mode)
        self._rename_row = -1
        self._adding = False  # the text prompt is naming a new project
        self._menu_pid: int | None = None  # project the open menu (More / Archived) is about
        self._menu_armed = False  # Delete in that menu was pressed once and waits for confirmation
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

    @Property(int, constant=True)
    def styleBase(self):
        """Style screen: item index of the first card's colour part (after the column items)."""
        return STYLE_COLUMN

    @Property(int, constant=True)
    def styleParts(self):
        return STYLE_PARTS

    @Property(str, notify=screenChanged)
    def listTitle(self):
        if self._screen in ("projectmenu", "archivedmenu"):
            project = self._db.get_project(self._menu_pid) if self._menu_pid is not None else None
            return project.name if project else ""
        if self._screen == "entries":
            return f"Entries \u00b7 {self._rep_data['label']}"
        if self._screen == "entryedit":
            return "Edit entry"
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

    @Property(int, notify=listChanged)
    def listVisible(self):
        """How many rows fit on screen; the rows after that wait for the knob to scroll."""
        return self._list.visible

    @Property(str, notify=screenChanged)
    def listNote(self):
        if self._screen == "entryedit":
            return self._entry_error or "Changes are saved as you make them."
        return self._clock_problem if self._screen == "clockwarn" else ""

    @Property(str, notify=dtChanged)
    def dtTitle(self):
        return {"start": "Entry start", "end": "Entry end"}.get(self._dt_entry_field, "Date & time")

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

    @Property(str, notify=repChanged)
    def repKind(self):
        return self._rep_kind

    @Property(str, notify=repChanged)
    def repLabel(self):
        return self._rep_data["label"]

    @Property(int, notify=repChanged)
    def repTotal(self):
        return self._rep_data["total"]

    @Property("QVariantList", notify=repChanged)
    def repRows(self):
        return [{"name": r["name"], "color": r["color"], "seconds": r["seconds"], "archived": r["archived"]}
                for r in self._rep_data["rows"]]

    @Property("QVariantList", notify=repChanged)
    def repItems(self):
        """Headers and entries of the period, grouped per project (see _rep_refresh)."""
        return self._rep_items

    @Property(int, notify=repChanged)
    def repFocus(self):
        return self._rep_focus

    @Property(bool, notify=repChanged)
    def repStepping(self):
        return self._rep_stepping

    @Property(bool, notify=repChanged)
    def repCanOlder(self):
        return self._rep_data.get("start", 0) > self._rep_limits[0]

    @Property(bool, notify=repChanged)
    def repCanNewer(self):
        return self._rep_data.get("start", 0) < self._rep_limits[1]

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
        if self._adding:
            return "add"
        if self._entry_note:
            return "entrynote"
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
        entry = self._db.get_entry(self._entry_id) if self._entry_note and self._entry_id is not None else None
        project_id = self._rename_id if self._rename_id is not None else (
            self._note_entry.project_id if self._note_entry is not None else (entry.project_id if entry else None)
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
            if self._screen == "reports":
                self._rep_refresh()  # a running timer keeps today's numbers moving

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

    def _open_screen(self, screen: str, restore: bool = False) -> None:
        """Show a screen. List screens get fresh rows; with restore (coming Back) the outline returns
        to the row that was open, otherwise it starts on the first real row."""
        if screen == "reports":
            self._rep_refresh()  # the entries may have been edited meanwhile
        if screen in LIST_SCREENS:
            self._entry_error = ""
            self._list_rows = self._rows_for(screen)
            # a note under the title leaves room for one row less
            visible = 5 if screen in NOTE_LISTS else 6
            self._list = ListNav(len(self._list_rows), visible=visible, default=0 if screen == "clockwarn" else None)
            if restore and screen in self._list_memory:
                self._list.select(self._list_memory[screen])
            self.listChanged.emit()
        self._set_screen(screen)

    def _rows_for(self, screen: str) -> list[dict]:
        def row(id_: str, label: str, value: str = "", kind: str = "") -> dict:
            return {"id": id_, "label": label, "value": value, "kind": kind}

        if screen == "settings":
            now = datetime.fromtimestamp(self._clock())
            return [
                row("back", "Back"),
                row("datetime", "Date & time", now.strftime("%d %b %Y  %H:%M")),
                row("status", "Status"),
            ]
        if screen == "clockwarn":
            return [row("datetime", "Set date and time"), row("ignore", "Ignore")]
        delete = row("delete", "Confirm delete" if self._menu_armed else "Delete", kind="armed" if self._menu_armed else "danger")
        if screen == "projectmenu":
            ids = [p.id for p in self._db.list_projects()]
            card = ids.index(self._menu_pid) if self._menu_pid in ids else 0
            rows = [row("back", "Cancel"), row("archive", "Archive")]
            if card > 0:
                rows.append(row("moveleft", "Move left"))
            if card < len(ids) - 1:
                rows.append(row("moveright", "Move right"))
            return rows + [delete]
        if screen == "archived":
            archived = self._db.archived_projects()
            if not archived:
                return [row("back", "Back"), row("none", "No archived projects")]
            return [row("back", "Back")] + [row(f"project:{p.id}", p.name, "Restore or delete") for p in archived]
        if screen == "archivedmenu":
            return [row("back", "Cancel"), row("restore", "Restore"), delete]
        if screen == "status":
            return self._status_rows(row)
        if screen == "entries":
            return self._entry_rows(row)
        if screen == "entryedit":
            entry = self._db.get_entry(self._entry_id) if self._entry_id is not None else None
            if entry is None:
                return [row("back", "Back")]
            project = self._db.get_project(entry.project_id)
            return [
                row("back", "Done"),
                row("project", "Project", project.name if project else "?"),
                row("start", "Start", f"{datetime.fromtimestamp(entry.start_ts):%d %b %Y  %H:%M}"),
                row("end", "End", "running" if entry.end_ts is None else f"{datetime.fromtimestamp(entry.end_ts):%d %b %Y  %H:%M}"),
                row("note", "Note", entry.note or "none"),
                delete,
            ]
        return []

    def _entry_rows(self, row) -> list[dict]:
        """The entries of the period shown in Reports, newest first."""
        names = {p.id: p.name for p in self._db.list_projects(include_archived=True)}
        rows = [row("back", "Back")]
        for e in reversed(self._db.entries_between(self._rep_data["start"], self._rep_data["end"])):
            start = datetime.fromtimestamp(e.start_ts)
            if e.end_ts is None:
                end, duration = "now", "running"
            else:
                stop = datetime.fromtimestamp(e.end_ts)
                end = f"{stop:%H:%M}" if stop.date() == start.date() else f"{stop:%d %b %H:%M}"
                duration = span_text(e.end_ts - e.start_ts)
            label = f"{start:%d %b}  {start:%H:%M}\u2013{end}  {names.get(e.project_id, '?')}" + ("  \u270e" if e.note else "")
            rows.append(row(f"entry:{e.id}", label, duration))
        if len(rows) == 1:
            rows.append(row("none", "No entries in this period"))
        return rows

    def _activate_list(self, index: int) -> None:
        if not 0 <= index < len(self._list_rows):
            return
        row_id = self._list_rows[index]["id"]
        self._list_memory[self._screen] = index
        if row_id == "back":
            self.back()
        elif row_id == "ignore":
            self._ignore_clock_problem()
        elif row_id == "datetime":
            self._open_datetime(return_to="main" if self._screen == "clockwarn" else None)
        elif row_id == "archive":
            self._menu_archive()
        elif row_id in ("moveleft", "moveright"):
            self._menu_move(-1 if row_id == "moveleft" else 1)
        elif row_id == "delete":
            self._menu_delete()
        elif row_id == "restore":
            self._menu_restore()
        elif row_id.startswith("entry:"):
            self._entry_id = int(row_id.split(":", 1)[1])
            self._entry_origin = "entries"
            self._menu_armed = False
            self._open_screen("entryedit")
        elif row_id == "project":
            self._entry_cycle_project()
        elif row_id in ("start", "end"):
            self._open_datetime(return_to="entryedit", entry_field=row_id)
        elif row_id == "note":
            self._open_entry_note()
        elif row_id.startswith("project:"):
            self._menu_pid = int(row_id.split(":", 1)[1])
            self._menu_armed = False
            self._open_screen("archivedmenu")
        elif row_id in ("none", "info"):
            return  # nothing to open
        else:
            self._open_screen(row_id)

    @Slot(int)
    def turn(self, steps: int) -> None:
        """Knob turned: positive = clockwise = selection moves right."""
        if self._prompt_open():
            # In a text prompt the knob moves the focus between its buttons.
            lowest = NOTE_DELETE if self._note_entry is not None else NOTE_SKIP  # only notes have Delete
            focus = max(lowest, min(NOTE_SAVE, self._note_focus + steps))
            if focus != self._note_focus:
                self._note_focus = focus
                self._delete_armed = False  # moving away cancels a pending delete
                self.noteChanged.emit()
            return
        if self._screen in LIST_SCREENS:
            if self._list.move(steps) and self._menu_armed:
                self._menu_armed = False  # moving away cancels a pending delete
                self._list_rows = self._rows_for(self._screen)
            self.listChanged.emit()
            return
        if self._screen == "datetime":
            if self._dt_editing:
                self._dt_adjust(self._dt_focus, steps)
            else:
                self._dt_focus = max(0, min(DT_SAVE, self._dt_focus + steps))
            self.dtChanged.emit()
            return
        if self._screen == "reports":
            if self._rep_stepping:
                self._rep_step(steps)
            else:
                self._rep_focus = max(0, min(REP_ITEMS - 1 + len(self._rep_entries), self._rep_focus + steps))
                self.repChanged.emit()
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
        elif self._screen == "reports":
            self._rep_press()
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
        parent = self._return_to or (self._entry_origin if self._screen == "entryedit" else SCREEN_PARENT.get(self._screen, "main"))
        self._return_to = None
        if parent == "main":
            self._use_nav(StripNav(self._nav.project_count))
            self._set_screen("main")
        else:
            self._open_screen(parent, restore=True)

    def _activate(self, index: int) -> None:
        if self._screen == "style":
            self._activate_style(index)
        elif index == SETTINGS:
            self._open_screen("settings")
        elif index == REPORTS:
            self._open_reports()
        elif index == STYLE:
            self._use_nav(self._new_style_nav())
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

    def _new_style_nav(self) -> StripNav:
        return StripNav(self._nav.project_count, column_items=STYLE_COLUMN, parts=STYLE_PARTS, trailing=1)

    def _select_style(self, card: int, part: int) -> None:
        before = (self._nav.selected, self._nav.offset)
        self._nav.select(STYLE_COLUMN + card * STYLE_PARTS + part)
        self._emit_nav_changes(before)

    def _activate_style(self, index: int) -> None:
        if index == 0:  # Back
            self.back()
            return
        if index == 1:  # Archived
            self._open_screen("archived")
            return
        count = self._nav.project_count
        if index == STYLE_COLUMN + count * STYLE_PARTS:  # the "+" card
            self._open_add()
            return
        card, part = divmod(index - STYLE_COLUMN, STYLE_PARTS)
        if part == PART_COLOR:
            self._cycle_color(card)
        elif part == PART_NAME:
            self._open_rename(card)
        elif part == PART_TIME:
            self._reset_time(card, index)
        else:
            self._menu_pid = self.projects.project_id(card)
            self._menu_armed = False
            self._open_screen("projectmenu")

    # -- project menus: More (on a card) and the Archived list ------------------------------------

    def _menu_card(self) -> int:
        ids = [p.id for p in self._db.list_projects()]
        return ids.index(self._menu_pid) if self._menu_pid in ids else 0

    def _leave_menu(self, parent: str) -> None:
        self._menu_armed = False
        self._open_screen(parent)

    def _menu_archive(self) -> None:
        card = self._menu_card()
        self._db.archive_project(self._menu_pid)  # also stops its timer, if it was running
        self.reload_projects()
        self._leave_menu("style")
        self._select_style(min(card, max(0, self._nav.project_count - 1)), PART_COLOR)

    def _menu_move(self, direction: int) -> None:
        card = self._menu_card()
        if self._db.move_project(self._menu_pid, direction):
            self.reload_projects()
            card += direction
        self._leave_menu("style")
        self._select_style(card, PART_MORE)  # the outline follows the project, ready to move it again

    def _menu_restore(self) -> None:
        self._db.archive_project(self._menu_pid, False)
        self.reload_projects()
        self._leave_menu("archived")

    def _menu_delete(self) -> None:
        """Delete a project and all its entries. The first press only arms it, the second does it."""
        if not self._menu_armed:
            self._menu_armed = True
            self._list_rows = self._rows_for(self._screen)
            self.listChanged.emit()
            return
        if self._screen == "entryedit":
            self._db.delete_entry(self._entry_id)
            self._refresh_times()
            self._menu_armed = False
            self._open_screen(self._entry_origin, restore=True)
            return
        card = self._menu_card()
        from_archive = self._screen == "archivedmenu"
        self._db.delete_project(self._menu_pid)
        self.reload_projects()
        self._leave_menu("archived" if from_archive else "style")
        if not from_archive:
            self._select_style(min(card, max(0, self._nav.project_count - 1)), PART_COLOR)

    # -- adding a project -------------------------------------------------------------------------

    def _open_add(self) -> None:
        self._adding = True
        self._note_text = ""
        self._note_focus = NOTE_SKIP
        self._delete_armed = False
        self.noteChanged.emit()

    def _new_project_color(self) -> str:
        """The next colour in the cycle after the last project's, so neighbours differ."""
        projects = self._db.list_projects()
        return next_color(projects[-1].color) if projects else COLOR_CYCLE[0]

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
        return self._note_entry is not None or self._rename_id is not None or self._adding or self._entry_note

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
        self._adding = False
        self._entry_note = False
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
        if self._entry_note:
            text = self._note_text
            self._close_note()
            try:
                self._db.update_entry(self._entry_id, note=text)
            except EntryError as exc:
                self._entry_error = str(exc)
            self._list_rows = self._rows_for("entryedit")
            self.listChanged.emit()
        elif self._adding:
            name = self._note_text.strip()
            self._close_note()
            if name:
                self._db.add_project(name, self._new_project_color())
                self.reload_projects()
                self._select_style(self._nav.project_count - 1, PART_COLOR)  # the new card
        elif self._rename_id is not None:
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

    def _open_datetime(self, return_to: str | None = None, entry_field: str | None = None) -> None:
        self._dt_entry_field = entry_field
        shown = self._clock()
        if entry_field:
            entry = self._db.get_entry(self._entry_id)
            shown = entry.start_ts if entry_field == "start" else (entry.end_ts or entry.start_ts)
        now = datetime.fromtimestamp(shown)
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
        if self._dt_entry_field:  # editing an entry's start or end, not the clock
            try:
                self._db.update_entry(
                    self._entry_id, **{f"{self._dt_entry_field}_ts": int(datetime(year, month, day, hour, minute).timestamp())}
                )
            except EntryError as exc:
                self._dt_error = str(exc)
                self.dtChanged.emit()
                return
            self.back()
            return
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

    # -- reports ----------------------------------------------------------------------------------

    def _open_reports(self) -> None:
        self._rep_kind = "day"
        self._rep_anchor = int(self._clock())
        self._rep_focus = REP_PERIOD
        self._rep_stepping = True
        self._rep_refresh()
        self._set_screen("reports")

    def _rep_refresh(self) -> None:
        now = int(self._clock())
        self._rep_data = summary(self._db, self._rep_kind, self._rep_anchor, now)
        self._rep_limits = step_limits(self._db, self._rep_kind, now)
        self._rep_build_items(now)
        # entries may have gone (deleted, or a period change by touch): keep the focus on something that exists
        self._rep_focus = min(self._rep_focus, REP_ITEMS - 1 + len(self._rep_entries))
        self.repChanged.emit()

    def _rep_build_items(self, now: int) -> None:
        """The list under the controls: per project (alphabetical) a header, then its entries."""
        kind = self._rep_kind
        items: list[dict] = []
        entries: list[int] = []
        for group in grouped_entries(self._db, kind, self._rep_anchor, now):
            items.append({
                "kind": "header", "name": group["name"] + (" (archived)" if group["archived"] else ""),
                "color": group["color"], "total": span_text(group["seconds"]),
            })
            for e in group["entries"]:
                start = datetime.fromtimestamp(e["start"])
                if e["end"] is None:
                    end = "now"
                else:
                    stop = datetime.fromtimestamp(e["end"])
                    end = f"{stop:%H:%M}" if stop.date() == start.date() else f"{stop:%d %b %H:%M}"
                day = "" if kind == "day" else f"{start:%a} {start.day} {start:%b}  "
                items.append({
                    "kind": "entry", "k": len(entries), "color": group["color"],
                    "time": f"{day}{start:%H:%M}\u2013{end}", "duration": span_text(e["seconds"]), "note": e["note"],
                })
                entries.append(e["id"])
        self._rep_items = items
        self._rep_entries = entries

    def _rep_step(self, steps: int) -> None:
        """Move to an older (negative) or newer (positive) period, never past the first entry or today."""
        oldest, current = self._rep_limits
        start = shift_period(self._rep_anchor, self._rep_kind, steps)
        self._rep_anchor = max(oldest, min(current, start))
        self._rep_refresh()

    def _rep_set_kind(self, kind: str) -> None:
        """Change Day / Week / Month. The moment being looked at stays, unless the new kind's
        limits (a month reaches back fewer steps than days) force it inside them."""
        self._rep_kind = kind
        self._rep_limits = step_limits(self._db, kind, int(self._clock()))
        oldest, current = self._rep_limits
        start = period_bounds(self._rep_anchor, kind)[0]
        if start < oldest:
            self._rep_anchor = oldest
        elif start > current:
            self._rep_anchor = current
        self._rep_stepping = True  # choosing a kind is followed by choosing the period
        self._rep_focus = REP_PERIOD
        self._rep_refresh()

    def _rep_press(self) -> None:
        if self._rep_focus == REP_BACK:
            self.back()
        elif self._rep_focus < REP_ENTRIES:
            self._rep_set_kind(KINDS[self._rep_focus - 1])
        elif self._rep_focus == REP_ENTRIES:
            self._open_entries()
        elif self._rep_focus == REP_PERIOD:
            self._rep_stepping = not self._rep_stepping
            self.repChanged.emit()
        else:
            self._open_report_entry(self._rep_focus - REP_ITEMS)

    def _open_report_entry(self, k: int) -> None:
        """Open an entry of the list in the editor; Back returns to the same place in the report."""
        if 0 <= k < len(self._rep_entries):
            self._entry_id = self._rep_entries[k]
            self._entry_origin = "reports"
            self._menu_armed = False
            self._open_screen("entryedit")

    @Slot(int)
    def repTap(self, item: int) -> None:
        """Touch: tap Back, Day, Week, Month, Entries or the period label (which starts or ends live mode)."""
        if self._screen != "reports" or not 0 <= item < REP_ITEMS:
            return
        if item == REP_PERIOD:
            self._rep_stepping = (not self._rep_stepping) if self._rep_focus == item else True
        else:
            self._rep_stepping = False
        self._rep_focus = item
        self._rep_press_item(item)

    @Slot(int)
    def repTapEntry(self, k: int) -> None:
        """Touch: tap an entry of the list."""
        if self._screen == "reports" and 0 <= k < len(self._rep_entries):
            self._rep_stepping = False
            self._rep_focus = REP_ITEMS + k
            self._open_report_entry(k)

    def _rep_press_item(self, item: int) -> None:
        if item == REP_BACK:
            self.back()
        elif item < REP_ENTRIES:
            self._rep_set_kind(KINDS[item - 1])
        elif item == REP_ENTRIES:
            self._open_entries()
        else:
            self.repChanged.emit()

    @Slot(int)
    def repStep(self, steps: int) -> None:
        """Touch: the arrows beside the period label."""
        if self._screen == "reports":
            self._rep_step(steps)

    # -- entries: browse and edit ---------------------------------------------------------------------

    def _open_entries(self) -> None:
        self._open_screen("entries")

    def _open_entry_note(self) -> None:
        entry = self._db.get_entry(self._entry_id)
        self._entry_note = True
        self._note_text = entry.note
        self._note_focus = NOTE_SKIP
        self._delete_armed = False
        self.noteChanged.emit()

    def _entry_cycle_project(self) -> None:
        """Give the entry to the next project (archived ones only if it already belongs to one)."""
        entry = self._db.get_entry(self._entry_id)
        ids = [p.id for p in self._db.list_projects(include_archived=True) if not p.archived or p.id == entry.project_id]
        target = ids[(ids.index(entry.project_id) + 1) % len(ids)]
        try:
            self._db.update_entry(self._entry_id, project_id=target)
            self._entry_error = ""
        except EntryError as exc:
            self._entry_error = str(exc)
        self._list_rows = self._rows_for("entryedit")
        self.listChanged.emit()
        self.screenChanged.emit()  # the note under the title may have changed

    # -- status ------------------------------------------------------------------------------------

    def _status_rows(self, row) -> list[dict]:
        """Facts for troubleshooting: is the clock trustworthy, how full is the disk, what is stored."""
        now = int(self._clock())
        problem = check_clock(self._db, now)
        change = self._db.get_meta(LAST_CHANGE)
        if change:
            old, new = (int(x) for x in change.split(","))
            changed = f"{datetime.fromtimestamp(old):%d %b %H:%M} \u2192 {datetime.fromtimestamp(new):%d %b %H:%M}"
        else:
            changed = "never"
        projects = self._db.list_projects(include_archived=True)
        archived = sum(1 for p in projects if p.archived)
        free = "unknown"
        if self._db.path is not None:
            try:
                free = f"{shutil.disk_usage(self._db.path.parent).free / 1e9:.1f} GB free"
            except OSError:
                pass
        info = lambda label, value: row("info", label, value)  # noqa: E731
        return [
            row("back", "Back"),
            info("Clock check", problem or "OK"),
            info("Time now", f"{datetime.fromtimestamp(now):%d %b %Y  %H:%M}"),
            info("Last time change", changed),
            info("Hardware clock", rtc_info()),
            info("Projects", f"{len(projects) - archived}" + (f" ({archived} archived)" if archived else "")),
            info("Entries", str(self._db.count_entries())),
            info("Storage", free),
            info("Version", __version__),
        ]
