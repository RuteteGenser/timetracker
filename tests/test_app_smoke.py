"""Loads the real QML in an offscreen window and drives it with simulated key presses."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from pathlib import Path

import timetracker

import pytest

pytest.importorskip("PySide6.QtQml")

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

import timetracker.app as app_module
from timetracker.config import Config
from timetracker.controller import Controller
from timetracker.inputs import make_input


@pytest.fixture
def ui(db, clock):
    app = QGuiApplication.instance() or QGuiApplication([])
    app_module.seed_starter_projects(db)
    ctl = Controller(db, clock=clock)
    knob = make_input(Config(), app)
    knob.turned.connect(ctl.turn)
    knob.pressed.connect(ctl.press)
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("ctl", ctl)
    ctx.setContextProperty("projects", ctl.projects)
    ctx.setContextProperty("cfgWidth", 1280)
    ctx.setContextProperty("cfgHeight", 720)
    ctx.setContextProperty("cfgFullscreen", False)
    engine.load(QUrl.fromLocalFile(str(Path(app_module.__file__).parent / "qml" / "Main.qml")))
    window = engine.rootObjects()[0]
    yield ctl, window, db
    del window, engine  # destroy QML first so no binding reads a dead controller
    app.processEvents()


def key(window, k):
    QTest.keyClick(window, k)


def test_boot_state_selects_first_project(ui):
    ctl, _, db = ui
    assert ctl.selected == 3                # Settings, Style, Reports, then the first card
    assert ctl.viewOffset == 0
    assert db.running() is None


def test_arrows_and_space_start_and_stop(ui):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    first = db.running()
    assert first is not None
    for _ in range(4):
        key(window, Qt.Key.Key_Right)
    assert ctl.selected == 7 and ctl.viewOffset == 2
    key(window, Qt.Key.Key_Space)  # starting another project stops the first
    assert db.running().project_id != first.project_id
    assert db.get_entry(first.id).end_ts is not None
    assert ctl.notePromptOpen      # ...and asks what was done in the first one
    key(window, Qt.Key.Key_Space)  # Skip is outlined by default: one press dismisses
    assert not ctl.notePromptOpen
    key(window, Qt.Key.Key_Space)  # press again: stop
    assert db.running() is None
    assert ctl.notePromptOpen
    key(window, Qt.Key.Key_Space)
    assert not ctl.notePromptOpen


def test_stopping_asks_for_a_note_and_saves_it(ui):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)          # start project 1
    key(window, Qt.Key.Key_Space)          # stop it
    entry = db.entries_between(0, 2**40)[0]
    assert ctl.notePromptOpen and ctl.noteFocus == 1 and ctl.noteProject == "Work"  # 1 = Skip
    ctl.noteType("Fixed ")
    ctl.noteType("bug")
    key(window, Qt.Key.Key_Right)          # knob: move to Save
    assert ctl.noteFocus == 2
    key(window, Qt.Key.Key_Space)
    assert not ctl.notePromptOpen
    assert db.get_entry(entry.id).note == "Fixed bug"


def test_skipping_leaves_note_empty_and_backspace_works(ui):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Space)
    ctl.noteType("ab")
    ctl.noteBackspace()
    assert ctl.noteText == "a"
    key(window, Qt.Key.Key_Space)          # Skip
    assert db.entries_between(0, 2**40)[0].note == ""


def test_note_prompt_blocks_the_strip(ui):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Space)
    selected = ctl.selected
    ctl.tap(6)                             # tapping a tile behind the prompt does nothing
    assert db.running() is None and ctl.selected == selected


def test_todays_total_grows_after_stop(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    clock.advance(42)
    key(window, Qt.Key.Key_Space)
    ctl._refresh_times()
    assert ctl.projects.data(ctl.projects.index(0), ctl.projects.TodayRole) == 42


def test_left_reaches_reports_style_settings_then_settings_list_and_back(ui):
    ctl, window, _ = ui
    key(window, Qt.Key.Key_Left)
    assert ctl.selected == 2               # Reports
    key(window, Qt.Key.Key_Left)
    assert ctl.selected == 1               # Style
    key(window, Qt.Key.Key_Left)
    assert ctl.selected == 0               # Settings
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "settings" and ctl.screenIsList
    assert [r["id"] for r in ctl.listRows] == ["back", "datetime", "status"]
    assert ctl.listSelected == 1           # the first real row, Back is one step left
    key(window, Qt.Key.Key_Left)
    assert ctl.listSelected == 0
    key(window, Qt.Key.Key_Space)          # Back
    assert ctl.screen == "main" and ctl.selected == 3 and ctl.viewOffset == 0


def test_settings_rows_open_screens_and_back_goes_up_one_level(ui):
    ctl, window, _ = ui
    for _ in range(3):
        key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)          # Settings list
    key(window, Qt.Key.Key_Space)          # Date & time
    assert ctl.screen == "datetime" and not ctl.screenIsList
    ctl.back()
    assert ctl.screen == "settings" and ctl.listSelected == 1
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Right)          # clamps at the last row
    assert ctl.listSelected == 2
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "status" and ctl.screenIsList
    key(window, Qt.Key.Key_Left)           # Back is the first row
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "settings"


def test_reports_button_opens_reports_and_back_item_leaves(ui):
    ctl, window, _ = ui
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "reports"
    for _ in range(5):
        key(window, Qt.Key.Key_Left)       # Period -> Entries -> Month -> Week -> Day -> Back
    assert ctl.repFocus == 0
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "main" and ctl.selected == 3


def test_tapping_list_rows(ui):
    ctl, _, _ = ui
    ctl.tap(0)                             # Settings
    assert ctl.screen == "settings"
    ctl.tap(1)                             # Date & time row
    assert ctl.screen == "datetime"
    ctl.back()
    assert ctl.screen == "settings"
    ctl.tap(0)                             # Back row
    assert ctl.screen == "main"


def test_tap_starts_project(ui):
    ctl, _, db = ui
    ctl.tap(5)
    assert db.running().project_id == ctl.projects.project_id(2)
    assert ctl.selected == 5


def test_delete_needs_two_presses(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)          # start
    clock.advance(300)
    key(window, Qt.Key.Key_Space)          # stop -> prompt
    key(window, Qt.Key.Key_Left)           # knob: move to Delete
    assert ctl.noteFocus == 0 and not ctl.noteDeleteArmed
    key(window, Qt.Key.Key_Left)           # clamps at Delete, nothing else changes
    assert ctl.noteFocus == 0
    key(window, Qt.Key.Key_Space)          # first press: only arms it
    assert ctl.notePromptOpen and ctl.noteDeleteArmed
    assert len(db.entries_between(0, 2**40)) == 1
    key(window, Qt.Key.Key_Space)          # second press: deletes
    assert not ctl.notePromptOpen
    assert db.entries_between(0, 2**40) == []
    assert ctl.projects.data(ctl.projects.index(0), ctl.projects.TodayRole) == 0


def test_turning_away_cancels_a_pending_delete(ui):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)          # armed
    assert ctl.noteDeleteArmed
    key(window, Qt.Key.Key_Right)          # to Skip
    assert not ctl.noteDeleteArmed
    key(window, Qt.Key.Key_Left)           # back to Delete: needs two presses again
    key(window, Qt.Key.Key_Space)
    assert ctl.notePromptOpen and len(db.entries_between(0, 2**40)) == 1


def test_typing_cancels_a_pending_delete(ui):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)
    assert ctl.noteDeleteArmed
    ctl.noteType("x")
    assert not ctl.noteDeleteArmed


def test_delete_from_switch_prompt_keeps_the_new_timer(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)          # start Work
    clock.advance(10)
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)          # start Admin; prompt is for Work
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)          # arm
    key(window, Qt.Key.Key_Space)          # delete Work's entry
    running = db.running()
    assert running is not None and running.project_id == ctl.projects.project_id(1)
    assert len(db.entries_between(0, 2**40)) == 1


# -- Style screen ----------------------------------------------------------------------------

def enter_style(window):
    key(window, Qt.Key.Key_Left)       # Reports
    key(window, Qt.Key.Key_Left)       # Style
    key(window, Qt.Key.Key_Space)


def color_of(ctl, row):
    return ctl.projects.data(ctl.projects.index(row), ctl.projects.ColorRole)


def test_style_opens_on_first_cards_color_part(ui):
    ctl, window, _ = ui
    enter_style(window)
    assert ctl.screen == "style"
    assert (ctl.selectedCard, ctl.selectedPart) == (0, 0)


def test_style_knob_visits_the_four_parts_of_each_card(ui):
    ctl, window, _ = ui
    enter_style(window)
    seen = []
    for _ in range(6):
        seen.append((ctl.selectedCard, ctl.selectedPart))
        key(window, Qt.Key.Key_Right)
    assert seen == [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1)]


def test_style_color_part_cycles_through_eight_colors(ui):
    from timetracker.colors import COLOR_CYCLE, next_color
    ctl, window, db = ui
    enter_style(window)
    start = color_of(ctl, 0)
    seen = [start]
    for _ in range(8):
        key(window, Qt.Key.Key_Space)
        seen.append(color_of(ctl, 0))
    assert seen[1] == next_color(start)
    assert seen[8] == start                      # all eight in the cycle, then back to the start
    assert db.list_projects()[0].color == seen[-1]
    assert set(seen) <= set(COLOR_CYCLE)


def test_style_rename_saves_and_cancel_does_not(ui):
    ctl, window, db = ui
    enter_style(window)
    key(window, Qt.Key.Key_Right)                # name part
    key(window, Qt.Key.Key_Space)
    assert ctl.notePromptOpen and ctl.noteKind == "rename"
    assert ctl.noteText == "Work" and ctl.noteFocus == 1      # Cancel is outlined
    ctl.noteType("!")
    key(window, Qt.Key.Key_Space)                # Cancel
    assert not ctl.notePromptOpen and db.list_projects()[0].name == "Work"
    key(window, Qt.Key.Key_Space)                # open again
    ctl.noteBackspace(); ctl.noteBackspace(); ctl.noteBackspace(); ctl.noteBackspace()
    ctl.noteType("Deep work")
    key(window, Qt.Key.Key_Right)                # Save
    assert ctl.noteFocus == 2
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Left)                 # clamps at Cancel: there is no Delete here
    assert ctl.noteFocus == 1
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)
    assert db.list_projects()[0].name == "Deep work"
    assert ctl.projects.data(ctl.projects.index(0), ctl.projects.NameRole) == "Deep work"


def test_style_empty_name_is_not_saved(ui):
    ctl, window, db = ui
    enter_style(window)
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)
    for _ in range(4):
        ctl.noteBackspace()
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)
    assert db.list_projects()[0].name == "Work"


def test_style_time_reset_needs_two_presses(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)                # start Work
    clock.advance(120)
    key(window, Qt.Key.Key_Space)                # stop
    key(window, Qt.Key.Key_Space)                # skip note
    today = lambda: ctl.projects.data(ctl.projects.index(0), ctl.projects.TodayRole)
    assert today() == 120
    enter_style(window)
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Right)                # time part
    key(window, Qt.Key.Key_Space)                # first press: arms
    assert ctl.resetArmed and today() == 120
    key(window, Qt.Key.Key_Space)                # second press: resets
    assert not ctl.resetArmed and today() == 0
    assert db.entries_between(0, 2**40) == []


def test_style_moving_away_cancels_a_pending_reset(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space); clock.advance(60); key(window, Qt.Key.Key_Space); key(window, Qt.Key.Key_Space)
    enter_style(window)
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)
    assert ctl.resetArmed
    key(window, Qt.Key.Key_Right)                # next card
    assert not ctl.resetArmed
    key(window, Qt.Key.Key_Left)                 # back on the time part: must be armed again first
    key(window, Qt.Key.Key_Space)
    assert ctl.resetArmed and len(db.entries_between(0, 2**40)) == 1


def test_style_back_button_returns_to_the_default_main_view(ui):
    ctl, window, _ = ui
    enter_style(window)
    key(window, Qt.Key.Key_Left)                 # first part -> Archived
    assert ctl.selected == 1 and ctl.selectedCard == -1
    key(window, Qt.Key.Key_Left)                 # -> Back
    assert ctl.selected == 0 and ctl.selectedCard == -1
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "main" and ctl.selected == 3 and ctl.viewOffset == 0


def test_style_tapping_parts(ui):
    ctl, _, db = ui
    ctl.tap(1)                                   # Style column item
    assert ctl.screen == "style"
    before = color_of(ctl, 1)
    ctl.tap(ctl.styleBase + ctl.styleParts * 1 + 0)   # card 2, colour part
    assert color_of(ctl, 1) != before and ctl.selectedCard == 1 and ctl.selectedPart == 0
    ctl.tap(ctl.styleBase + ctl.styleParts * 1 + 1)   # card 2, name part
    assert ctl.noteKind == "rename" and ctl.noteText == "Admin"


# -- Date & time and the clock check ----------------------------------------------------------

from datetime import datetime as _dt


def open_datetime(window):
    for _ in range(3):
        key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)          # Settings
    key(window, Qt.Key.Key_Space)          # Date & time


def local(ts):
    d = _dt.fromtimestamp(ts)
    return [d.year, d.month, d.day, d.hour, d.minute]


def test_datetime_shows_the_current_time_and_nothing_is_changed_by_cancel(ui, clock):
    ctl, window, _ = ui
    open_datetime(window)
    assert list(ctl.dtFields) == local(clock())
    assert ctl.dtFocus == 0 and not ctl.dtEditing
    before = clock()
    for _ in range(5):
        key(window, Qt.Key.Key_Right)      # to Cancel
    assert ctl.dtFocus == 5
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "settings" and clock() == before


def test_datetime_knob_edits_a_field_and_save_sets_the_clock(ui, clock):
    ctl, window, db = ui
    open_datetime(window)
    for _ in range(3):
        key(window, Qt.Key.Key_Right)      # Hour
    assert ctl.dtFocus == 3
    key(window, Qt.Key.Key_Space)          # start editing
    assert ctl.dtEditing
    before = list(ctl.dtFields)
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Right)
    assert ctl.dtFields[3] == (before[3] + 2) % 24
    key(window, Qt.Key.Key_Space)          # stop editing
    assert not ctl.dtEditing
    for _ in range(3):
        key(window, Qt.Key.Key_Right)      # Minute, Cancel, Save
    assert ctl.dtFocus == 6
    edited = list(ctl.dtFields)
    key(window, Qt.Key.Key_Space)          # Save
    assert ctl.screen == "settings"
    assert clock() == int(_dt(*edited).timestamp())      # the clock now shows exactly what was chosen


def test_saving_the_time_keeps_a_running_timer_elapsed_time(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)          # start Work
    clock.advance(300)
    elapsed = clock() - db.running().start_ts
    open_datetime(window)
    ctl.dtAdjust(2, 1)                     # a day later
    ctl.dtSave()
    assert clock() - db.running().start_ts == elapsed
    assert ctl.screen == "settings"


def test_datetime_day_is_clamped_when_the_month_changes(ui):
    ctl, window, _ = ui
    open_datetime(window)
    ctl._dt_fields = [2026, 1, 31, 10, 0]
    ctl.dtAdjust(1, 1)                     # month -> February
    assert ctl.dtFields[1] == 2 and ctl.dtFields[2] == 28
    ctl._dt_fields = [2027, 12, 15, 23, 59]
    ctl.dtAdjust(4, 1)
    assert ctl.dtFields[4] == 0            # minute wraps
    ctl.dtAdjust(3, 1)
    assert ctl.dtFields[3] == 0            # hour wraps
    ctl._dt_fields = [2099, 1, 1, 0, 0]
    ctl.dtAdjust(0, 5)
    assert ctl.dtFields[0] == 2099         # year stops at the end of its range


def test_saving_without_changes_does_not_touch_the_clock(ui, clock):
    ctl, window, db = ui
    open_datetime(window)
    old_meta = db.get_meta("last_clock_change")
    ctl.dtSave()
    assert ctl.screen == "settings" and db.get_meta("last_clock_change") == old_meta


def test_a_clock_that_cannot_be_set_shows_an_error_and_stays(ui, clock, monkeypatch):
    from timetracker.clock import ClockError
    ctl, window, db = ui

    def boom(db_, ts):
        raise ClockError("no helper installed")
    monkeypatch.setattr(clock, "set_time", boom)
    open_datetime(window)
    ctl.dtAdjust(2, 1)
    ctl.dtSave()
    assert ctl.screen == "datetime" and ctl.dtError == "no helper installed"


def test_touch_tap_on_a_field_starts_editing(ui):
    ctl, window, _ = ui
    open_datetime(window)
    ctl.dtTap(3)
    assert ctl.dtFocus == 3 and ctl.dtEditing
    ctl.dtTap(3)
    assert not ctl.dtEditing


def test_boot_check_warns_when_the_clock_is_behind_and_ignore_dismisses(ui, clock, db):
    ctl, window, _ = ui
    db.set_meta("last_seen", str(clock() + 5 * 3600))
    ctl.run_clock_check()
    assert ctl.screen == "clockwarn" and ctl.screenIsList
    assert "behind" in ctl.listNote
    assert [r["id"] for r in ctl.listRows] == ["datetime", "ignore"]
    assert ctl.listSelected == 0           # Set date and time is outlined first
    key(window, Qt.Key.Key_Right)          # Ignore
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "main" and ctl.selected == 3
    ctl.run_clock_check()                  # dismissed: it does not come back
    assert ctl.screen == "main"


def test_boot_check_set_time_returns_to_the_main_screen_afterwards(ui, clock, db):
    ctl, window, _ = ui
    db.set_meta("last_seen", str(clock() + 5 * 3600))
    ctl.run_clock_check()
    key(window, Qt.Key.Key_Space)          # Set date and time
    assert ctl.screen == "datetime"
    ctl.dtAdjust(3, 5)
    ctl.dtSave()
    assert ctl.screen == "main"
    ctl.run_clock_check()
    assert ctl.screen == "main"            # the heartbeat was reset to the new time


def test_boot_check_is_silent_with_a_sane_clock(ui):
    ctl, _, _ = ui
    ctl.run_clock_check()
    assert ctl.screen == "main"


def test_heartbeat_moves_forward_only_and_a_jump_back_while_running_warns(ui, clock, db):
    ctl, _, _ = ui
    ctl._heartbeat(clock())
    assert db.get_meta("last_seen") == str(clock())
    clock.advance(120)
    ctl._heartbeat(clock())
    assert db.get_meta("last_seen") == str(clock())
    seen = clock()
    clock.advance(-3600)                   # the clock jumps back an hour
    ctl._heartbeat(clock())
    assert db.get_meta("last_seen") == str(seen)   # the reference was not dragged back
    assert ctl.screen == "clockwarn" and "behind" in ctl.listNote


# -- project management on the Style screen -------------------------------------------------------

def to_more(window, card=0):
    """From the Style screen's first item to the More part of a card."""
    for _ in range(card * 4 + 3):
        key(window, Qt.Key.Key_Right)


def row_ids(ctl):
    return [r["id"] for r in ctl.listRows]


def project_names(db):
    return [p.name for p in db.list_projects()]


def test_more_opens_a_menu_without_move_left_for_the_first_card(ui):
    ctl, window, _ = ui
    enter_style(window)
    to_more(window)
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "projectmenu" and ctl.screenIsList and ctl.listTitle == "Work"
    assert row_ids(ctl) == ["back", "archive", "moveright", "delete"]
    assert ctl.listSelected == 1
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)                 # Cancel
    assert ctl.screen == "style" and (ctl.selectedCard, ctl.selectedPart) == (0, 3)


def test_last_card_has_no_move_right_and_middle_cards_have_both(ui):
    ctl, window, db = ui
    enter_style(window)
    to_more(window, 2)
    key(window, Qt.Key.Key_Space)
    assert row_ids(ctl) == ["back", "archive", "moveleft", "moveright", "delete"]
    ctl.back()
    to_more_last = ctl.projectCount - 1
    ctl._select_style(to_more_last, 3)
    key(window, Qt.Key.Key_Space)
    assert row_ids(ctl) == ["back", "archive", "moveleft", "delete"]


def test_archive_hides_the_project_and_stops_its_timer(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)                 # start Work
    clock.advance(30)
    key(window, Qt.Key.Key_Space); key(window, Qt.Key.Key_Space)   # (stop + skip note) ...
    key(window, Qt.Key.Key_Space)                 # ... and start it again
    assert db.running() is not None
    enter_style(window)
    to_more(window)
    key(window, Qt.Key.Key_Space)                 # menu
    key(window, Qt.Key.Key_Space)                 # Archive (outlined first)
    assert "Work" not in project_names(db) and ctl.projectCount == 5
    assert db.running() is None
    assert ctl.screen == "style" and (ctl.selectedCard, ctl.selectedPart) == (0, 0)
    assert ctl.projects.data(ctl.projects.index(0), ctl.projects.NameRole) == "Admin"


def test_move_right_reorders_and_the_outline_follows_the_project(ui):
    ctl, window, db = ui
    enter_style(window)
    to_more(window)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Right)                 # Move right
    key(window, Qt.Key.Key_Space)
    assert project_names(db)[:2] == ["Admin", "Work"]
    assert ctl.projects.data(ctl.projects.index(1), ctl.projects.NameRole) == "Work"
    assert ctl.screen == "style" and (ctl.selectedCard, ctl.selectedPart) == (1, 3)
    key(window, Qt.Key.Key_Space)                 # menu again, now with Move left
    assert "moveleft" in row_ids(ctl)


def test_delete_needs_two_presses_and_removes_the_entries(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space); clock.advance(60); key(window, Qt.Key.Key_Space); key(window, Qt.Key.Key_Space)
    assert len(db.entries_between(0, 2**40)) == 1
    enter_style(window)
    to_more(window)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Right)   # to Delete
    assert ctl.listRows[ctl.listSelected]["id"] == "delete" and ctl.listRows[ctl.listSelected]["kind"] == "danger"
    key(window, Qt.Key.Key_Space)                 # first press: arms
    row = ctl.listRows[ctl.listSelected]
    assert row["label"] == "Confirm delete" and row["kind"] == "armed" and ctl.screen == "projectmenu"
    assert "Work" in project_names(db)
    key(window, Qt.Key.Key_Space)                 # second press: deletes
    assert "Work" not in project_names(db) and db.entries_between(0, 2**40) == []
    assert ctl.screen == "style"


def test_turning_away_cancels_a_pending_project_delete(ui):
    ctl, window, db = ui
    enter_style(window)
    to_more(window)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)                 # armed
    key(window, Qt.Key.Key_Left)                  # away
    assert all(r["kind"] != "armed" for r in ctl.listRows)
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)                 # back on Delete: needs two presses again
    assert "Work" in project_names(db) and ctl.listRows[ctl.listSelected]["kind"] == "armed"


def test_archived_list_restore_and_delete(ui):
    ctl, window, db = ui
    enter_style(window)
    key(window, Qt.Key.Key_Left)                  # Archived
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "archived" and row_ids(ctl) == ["back", "none"]
    ctl.back()
    assert ctl.screen == "style"
    ctl._select_style(0, 3)
    key(window, Qt.Key.Key_Space); key(window, Qt.Key.Key_Space)   # menu, Archive Work
    ctl.tap(1)                                    # Archived column item
    assert ctl.screen == "archived" and [r["label"] for r in ctl.listRows] == ["Back", "Work"]
    key(window, Qt.Key.Key_Space)                 # open Work
    assert ctl.screen == "archivedmenu" and row_ids(ctl) == ["back", "restore", "delete"]
    key(window, Qt.Key.Key_Space)                 # Restore
    assert ctl.screen == "archived" and project_names(db)[0] == "Work"   # back at its old place
    assert row_ids(ctl) == ["back", "none"]
    # archive again, then delete from the archive
    ctl.back()
    ctl._select_style(0, 3)
    key(window, Qt.Key.Key_Space); key(window, Qt.Key.Key_Space)
    ctl.tap(1)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Right)                 # Delete
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "archivedmenu"           # armed
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "archived" and db.archived_projects() == [] and "Work" not in project_names(db)


def test_plus_card_adds_a_project(ui):
    ctl, window, db = ui
    enter_style(window)
    for _ in range(ctl.projectCount * 4):
        key(window, Qt.Key.Key_Right)             # to the "+" card
    assert ctl.selectedCard == ctl.projectCount and ctl.selected == ctl.styleBase + 4 * ctl.projectCount
    last_color = db.list_projects()[-1].color
    key(window, Qt.Key.Key_Space)
    assert ctl.notePromptOpen and ctl.noteKind == "add" and ctl.noteText == ""
    assert ctl.noteFocus == 1                     # Cancel is outlined
    ctl.noteType("Reading")
    key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)                 # Save
    assert project_names(db)[-1] == "Reading" and ctl.projectCount == 7
    assert db.list_projects()[-1].color != last_color
    assert (ctl.selectedCard, ctl.selectedPart) == (6, 0)


def test_adding_can_be_cancelled_and_an_empty_name_adds_nothing(ui):
    ctl, window, db = ui
    count = ctl.projectCount
    ctl.tap(1)                                    # Style
    ctl.tap(ctl.styleBase + 4 * count)            # the "+" card
    ctl.noteType("Nope")
    key(window, Qt.Key.Key_Space)                 # Cancel
    assert ctl.projectCount == count
    ctl.tap(ctl.styleBase + 4 * count)
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Space)    # Save with no name
    assert ctl.projectCount == count and not ctl.notePromptOpen


def test_with_every_project_archived_the_plus_card_still_works(ui):
    ctl, window, db = ui
    for p in db.list_projects():
        db.archive_project(p.id)
    ctl.reload_projects()
    ctl.tap(1)                                    # Style
    assert ctl.screen == "style" and ctl.projectCount == 0
    assert ctl.selectedCard == 0 and ctl.selected == ctl.styleBase   # the "+" card is the only card
    key(window, Qt.Key.Key_Space)
    assert ctl.noteKind == "add"
    ctl.noteType("First")
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Space)
    assert project_names(db) == ["First"] and db.list_projects()[0].color


def test_new_project_shows_up_on_the_main_screen(ui):
    ctl, window, db = ui
    ctl.tap(1)
    ctl.tap(ctl.styleBase + 4 * ctl.projectCount)
    ctl.noteType("Reading")
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Space)
    ctl.tap(0)                                    # Back
    assert ctl.screen == "main" and ctl.projectCount == 7
    assert ctl.projects.data(ctl.projects.index(6), ctl.projects.NameRole) == "Reading"


# -- Reports --------------------------------------------------------------------------------------------

def open_reports(window, ctl=None):
    if ctl is not None:
        ctl.tap(2)                          # the Reports column item, wherever the selection is
        return
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Space)


def track(window, clock, seconds):
    """Start the first project, let `seconds` pass, stop it and skip the note."""
    key(window, Qt.Key.Key_Space)
    clock.advance(seconds)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Space)


def rep_seconds(ctl):
    return {r["name"]: r["seconds"] for r in ctl.repRows}


def test_reports_opens_on_today_with_the_period_focused(ui):
    ctl, window, _ = ui
    open_reports(window)
    assert (ctl.repKind, ctl.repLabel, ctl.repFocus, ctl.repStepping) == ("day", "Today", 5, False)
    assert ctl.repTotal == 0 and [r["name"] for r in ctl.repRows][:2] == ["Work", "Admin"]
    assert not ctl.repCanOlder and not ctl.repCanNewer


def test_reports_show_the_tracked_time_per_project_and_the_total(ui, clock):
    ctl, window, _ = ui
    track(window, clock, 600)                           # Work, 10 min
    key(window, Qt.Key.Key_Right)                       # Admin
    key(window, Qt.Key.Key_Space)
    clock.advance(300)                                  # Admin, 5 min
    key(window, Qt.Key.Key_Space); key(window, Qt.Key.Key_Space)
    open_reports(window, ctl)
    assert rep_seconds(ctl)["Work"] == 600 and rep_seconds(ctl)["Admin"] == 300
    assert ctl.repTotal == 900 == sum(r["seconds"] for r in ctl.repRows)


def test_stepping_to_older_periods_stops_at_the_first_entry_and_at_today(ui, clock):
    ctl, window, db = ui
    track(window, clock, 600)                           # today
    clock.advance(2 * 86400)                            # two days later
    track(window, clock, 120)
    open_reports(window, ctl)
    assert ctl.repLabel == "Today" and ctl.repCanOlder and not ctl.repCanNewer
    key(window, Qt.Key.Key_Space)                       # start stepping
    assert ctl.repStepping
    key(window, Qt.Key.Key_Left)
    assert ctl.repLabel == "Yesterday" and ctl.repTotal == 0
    key(window, Qt.Key.Key_Left)                        # the day with the first entry
    assert rep_seconds(ctl)["Work"] == 600 and not ctl.repCanOlder
    key(window, Qt.Key.Key_Left)                        # nothing older: stays
    assert rep_seconds(ctl)["Work"] == 600
    for _ in range(5):
        key(window, Qt.Key.Key_Right)                   # clamps at today
    assert ctl.repLabel == "Today" and not ctl.repCanNewer
    key(window, Qt.Key.Key_Space)                       # stop stepping
    assert not ctl.repStepping


def test_week_and_month_kinds_sum_several_days(ui, clock):
    ctl, window, _ = ui
    track(window, clock, 600)
    clock.advance(86400)
    track(window, clock, 300)
    open_reports(window, ctl)
    ctl.repTap(1)
    assert ctl.repTotal == 300                          # the day view only has today's entry
    ctl.repTap(2)
    assert ctl.repKind == "week" and ctl.repLabel.startswith("This week") and ctl.repTotal == 900
    ctl.repTap(3)
    assert ctl.repKind == "month" and ctl.repTotal == 900


def test_the_period_label_for_a_week_covers_monday_to_sunday(ui):
    ctl, window, _ = ui
    open_reports(window, ctl)
    key(window, Qt.Key.Key_Left); key(window, Qt.Key.Key_Left); key(window, Qt.Key.Key_Left)   # Entries, Month, Week
    key(window, Qt.Key.Key_Space)
    assert ctl.repKind == "week" and "\u2013" in ctl.repLabel


def test_a_running_timer_keeps_todays_numbers_moving(ui, clock):
    ctl, window, _ = ui
    key(window, Qt.Key.Key_Space)                       # start Work
    open_reports(window, ctl)
    clock.advance(90)
    ctl._on_tick()
    assert rep_seconds(ctl)["Work"] == 90 and ctl.repTotal == 90


def test_reports_touch_controls(ui, clock):
    ctl, window, _ = ui
    track(window, clock, 600)
    clock.advance(86400)
    track(window, clock, 60)
    open_reports(window, ctl)
    ctl.repTap(2)                                       # Week
    assert ctl.repKind == "week"
    ctl.repTap(1)                                       # Day
    assert ctl.repKind == "day" and ctl.repLabel == "Today"
    ctl.repStep(-1)
    assert ctl.repLabel == "Yesterday" and rep_seconds(ctl)["Work"] == 600
    ctl.repStep(+1)
    assert ctl.repLabel == "Today"
    ctl.repTap(0)                                       # Back
    assert ctl.screen == "main"


def test_changing_kind_keeps_the_period_inside_the_limits(ui, clock):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_reports(window, ctl)
    ctl.repStep(-5)                                     # no older day exists
    assert ctl.repLabel == "Today"
    ctl.repTap(3)                                       # Month
    assert ctl.repKind == "month" and not ctl.repCanOlder and not ctl.repCanNewer


# -- Entries: browse and edit -------------------------------------------------------------------------

from datetime import datetime as _dt2


def open_entries(window, ctl):
    open_reports(window, ctl)
    key(window, Qt.Key.Key_Left)                         # Period -> Entries
    key(window, Qt.Key.Key_Space)


def row_by_id(ctl, id_):
    return next(r for r in ctl.listRows if r["id"] == id_)


def entry_ids(ctl):
    return [int(r["id"].split(":")[1]) for r in ctl.listRows if r["id"].startswith("entry:")]


def open_first_entry(window, ctl):
    open_entries(window, ctl)
    key(window, Qt.Key.Key_Space)                        # the first (newest) entry row is outlined
    assert ctl.screen == "entryedit"


def test_entries_lists_the_period_newest_first(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    clock.advance(1000)
    track(window, clock, 300)
    open_entries(window, ctl)
    assert ctl.screen == "entries" and ctl.screenIsList and ctl.listTitle == "Entries \u00b7 Today"
    ids = entry_ids(ctl)
    assert len(ids) == 2 and ids[0] > ids[1]             # newest first
    assert ctl.listSelected == 1 and ctl.listRows[1]["value"] == "5m 00s"
    assert ctl.listRows[2]["value"] == "10m 00s" and "Work" in ctl.listRows[2]["label"]


def test_entries_of_a_week_include_earlier_days_and_empty_periods_say_so(ui, clock):
    ctl, window, _ = ui
    open_entries(window, ctl)
    assert [r["id"] for r in ctl.listRows] == ["back", "none"] and ctl.listSelected == 1
    key(window, Qt.Key.Key_Space)                        # the "No entries" row does nothing
    assert ctl.screen == "entries"
    key(window, Qt.Key.Key_Left); key(window, Qt.Key.Key_Space)    # Back
    assert ctl.screen == "reports"
    ctl.repTap(0)                                        # Back to the main screen
    track(window, clock, 600)
    open_reports(window, ctl)
    ctl.repTap(2)                                        # Week
    ctl.repTap(4)                                        # Entries
    assert len(entry_ids(ctl)) == 1 and "Entries" in ctl.listTitle and "\u2013" in ctl.listTitle


def test_back_from_entries_returns_to_reports_with_its_state(ui, clock):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_reports(window, ctl)
    ctl.repTap(2)
    ctl.repTap(4)
    ctl.back()
    assert ctl.screen == "reports" and ctl.repKind == "week"


def test_an_entry_row_opens_the_editor(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_first_entry(window, ctl)
    assert [r["id"] for r in ctl.listRows] == ["back", "project", "start", "end", "note", "delete"]
    assert row_by_id(ctl, "project")["value"] == "Work" and row_by_id(ctl, "note")["value"] == "none"
    assert ctl.listTitle == "Edit entry" and "saved as you make" in ctl.listNote
    key(window, Qt.Key.Key_Left)                         # Done
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "entries" and ctl.listSelected == 1     # the outline returned to the row


def test_the_project_row_cycles_the_projects(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_first_entry(window, ctl)
    key(window, Qt.Key.Key_Space)                        # Project is outlined first: Work -> Admin
    assert row_by_id(ctl, "project")["value"] == "Admin"
    entry = db.entries_between(0, 2**40)[0]
    assert db.get_project(entry.project_id).name == "Admin"
    for _ in range(5):
        key(window, Qt.Key.Key_Space)                    # ... and round the six projects back to Work
    assert row_by_id(ctl, "project")["value"] == "Work"


def test_a_note_can_be_edited_and_cancelled(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_first_entry(window, ctl)
    for _ in range(3):
        key(window, Qt.Key.Key_Right)                    # Note row
    assert ctl.listRows[ctl.listSelected]["id"] == "note"
    key(window, Qt.Key.Key_Space)
    assert ctl.notePromptOpen and ctl.noteKind == "entrynote" and ctl.noteText == "" and ctl.noteProject == "Work"
    ctl.noteType("Quarterly report")
    key(window, Qt.Key.Key_Space)                        # Cancel is outlined by default
    assert db.entries_between(0, 2**40)[0].note == ""
    key(window, Qt.Key.Key_Space)                        # open again
    ctl.noteType("Quarterly report")
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Space)    # Save
    assert db.entries_between(0, 2**40)[0].note == "Quarterly report"
    assert row_by_id(ctl, "note")["value"] == "Quarterly report" and ctl.screen == "entryedit"
    assert ctl.listRows[ctl.listSelected]["id"] == "note"


def test_start_and_end_use_the_date_and_time_screen(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    entry = db.entries_between(0, 2**40)[0]
    open_first_entry(window, ctl)
    key(window, Qt.Key.Key_Right)                        # Start row
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "datetime" and ctl.dtTitle == "Entry start"
    d = _dt2.fromtimestamp(entry.start_ts)
    assert list(ctl.dtFields) == [d.year, d.month, d.day, d.hour, d.minute]
    ctl.dtAdjust(4, +1)                                  # one minute later (a minute field wraps inside its hour)
    ctl.dtSave()
    assert ctl.screen == "entryedit" and ctl.listRows[ctl.listSelected]["id"] == "start"
    assert db.get_entry(entry.id).start_ts == int(_dt2(d.year, d.month, d.day, d.hour, (d.minute + 1) % 60).timestamp())
    key(window, Qt.Key.Key_Right)                        # End row
    key(window, Qt.Key.Key_Space)
    assert ctl.dtTitle == "Entry end"
    ctl.dtAdjust(4, +2)
    ctl.dtSave()
    assert db.get_entry(entry.id).end_ts is not None


def test_an_impossible_time_is_refused_and_explained(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    entry = db.entries_between(0, 2**40)[0]
    open_first_entry(window, ctl)
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Right)   # End row
    key(window, Qt.Key.Key_Space)
    ctl.dtAdjust(3, -2)                                  # two hours earlier: before the start
    ctl.dtSave()
    assert ctl.screen == "datetime" and "after the start" in ctl.dtError
    assert db.get_entry(entry.id) == entry
    ctl.dtAdjust(3, 100)                                 # back to the original hour
    ctl.dtAdjust(3, 100)
    ctl.back()                                           # Back from the editor screen: no change made
    assert ctl.screen == "entryedit" and db.get_entry(entry.id) == entry


def test_an_overlap_is_refused(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)                            # [t, t+600)
    clock.advance(1000)
    track(window, clock, 300)                            # [t+1600, t+1900); now = t+1900
    older, newer = db.entries_between(0, 2**40)
    open_entries(window, ctl)
    key(window, Qt.Key.Key_Right)                        # the older entry (second row)
    key(window, Qt.Key.Key_Space)
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Right)   # End row
    key(window, Qt.Key.Key_Space)
    ctl.dtAdjust(4, 17)                                  # +17 minutes: past the newer entry's start, not in the future
    ctl.dtSave()
    assert ctl.screen == "datetime" and "overlaps" in ctl.dtError
    assert db.get_entry(older.id) == older


def test_the_end_of_a_running_timer_cannot_be_edited(ui, clock, db):
    ctl, window, _ = ui
    key(window, Qt.Key.Key_Space)                        # start Work
    clock.advance(120)
    open_first_entry(window, ctl)
    assert row_by_id(ctl, "end")["value"] == "running"
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)                        # End
    assert ctl.screen == "datetime" and ctl.dtTitle == "Entry end"
    ctl.dtAdjust(4, 1)
    ctl.dtSave()
    assert "no end yet" in ctl.dtError and db.running() is not None


def test_deleting_an_entry_needs_two_presses_and_updates_the_reports(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_first_entry(window, ctl)
    for _ in range(4):
        key(window, Qt.Key.Key_Right)                    # Delete
    row = ctl.listRows[ctl.listSelected]
    assert row["id"] == "delete" and row["kind"] == "danger"
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "entryedit" and ctl.listRows[ctl.listSelected]["kind"] == "armed"
    assert len(db.entries_between(0, 2**40)) == 1
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "entries" and db.entries_between(0, 2**40) == []
    assert [r["id"] for r in ctl.listRows] == ["back", "none"]
    ctl.back()
    assert ctl.screen == "reports" and ctl.repTotal == 0


def test_turning_away_cancels_a_pending_entry_delete(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_first_entry(window, ctl)
    for _ in range(4):
        key(window, Qt.Key.Key_Right)
    key(window, Qt.Key.Key_Space)                        # armed
    key(window, Qt.Key.Key_Left)
    assert all(r["kind"] != "armed" for r in ctl.listRows)
    assert len(db.entries_between(0, 2**40)) == 1


def test_edits_show_up_in_the_reports_and_the_main_screen_totals(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_first_entry(window, ctl)
    key(window, Qt.Key.Key_Right); key(window, Qt.Key.Key_Right)   # End row
    key(window, Qt.Key.Key_Space)
    ctl.dtAdjust(4, -3)                                  # ends three minutes earlier
    ctl.dtSave()
    ctl.back(); ctl.back()                               # editor -> entries -> reports
    assert ctl.screen == "reports" and ctl.repTotal == 600 - 180


def test_a_list_with_a_note_shows_one_row_less_and_still_reaches_every_row(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 600)
    open_first_entry(window, ctl)
    assert ctl.listVisible == 5 and len(ctl.listRows) == 6
    for _ in range(6):
        key(window, Qt.Key.Key_Right)
    assert ctl.listRows[ctl.listSelected]["id"] == "delete"
    assert ctl.listOffset <= ctl.listSelected < ctl.listOffset + ctl.listVisible
    ctl.back(); ctl.back(); ctl.back()
    ctl.tap(0)                                  # Settings: no note, six rows fit
    assert ctl.listVisible == 6


# -- Status -------------------------------------------------------------------------------------------

def open_status(ctl):
    ctl.tap(0)                                  # Settings
    ctl.tap(2)                                  # Status


def status(ctl):
    return {r["label"]: r["value"] for r in ctl.listRows if r["id"] == "info"}


def test_status_lists_the_facts_and_info_rows_do_nothing(ui, clock):
    ctl, window, db = ui
    open_status(ctl)
    assert ctl.screen == "status" and ctl.listTitle == "Status"
    facts = status(ctl)
    assert list(facts) == ["Clock check", "Time now", "Last time change", "Hardware clock", "Projects", "Entries", "Storage", "Version"]
    assert facts["Clock check"] == "OK" and facts["Last time change"] == "never"
    assert facts["Projects"] == "6" and facts["Entries"] == "0"
    assert facts["Storage"].endswith("GB free") and facts["Version"] == timetracker.__version__
    key(window, Qt.Key.Key_Space)                # an info row: nothing happens
    assert ctl.screen == "status"


def test_status_shows_a_clock_problem_a_clock_change_and_counts(ui, clock, db):
    ctl, window, _ = ui
    track(window, clock, 120)
    ctl.tap(0); ctl.tap(1)                       # Settings -> Date & time
    ctl.dtAdjust(3, 2)
    ctl.dtSave()                                 # changes the clock: recorded
    ctl.back()                                   # Settings -> main
    db.archive_project(db.list_projects()[3].id)
    ctl.reload_projects()
    db.set_meta("last_seen", str(clock() + 4 * 3600))
    open_status(ctl)
    facts = status(ctl)
    assert "behind" in facts["Clock check"]
    assert "\u2192" in facts["Last time change"]
    assert facts["Projects"] == "5 (1 archived)" and facts["Entries"] == "1"


def test_status_back_row_returns_to_settings(ui):
    ctl, window, _ = ui
    open_status(ctl)
    ctl.tap(0)
    assert ctl.screen == "settings"
