"""Loads the real QML in an offscreen window and drives it with simulated key presses."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from pathlib import Path

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
    assert ctl.selected == 2
    assert ctl.viewOffset == 0
    assert db.running() is None


def test_arrows_and_space_start_and_stop(ui):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    first = db.running()
    assert first is not None
    for _ in range(4):
        key(window, Qt.Key.Key_Right)
    assert ctl.selected == 6 and ctl.viewOffset == 2
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
    ctl.tap(5)                             # tapping a tile behind the prompt does nothing
    assert db.running() is None and ctl.selected == selected


def test_todays_total_grows_after_stop(ui, clock):
    ctl, window, db = ui
    key(window, Qt.Key.Key_Space)
    clock.advance(42)
    key(window, Qt.Key.Key_Space)
    ctl._refresh_times()
    assert ctl.projects.data(ctl.projects.index(0), ctl.projects.TodayRole) == 42


def test_left_reaches_style_then_settings_and_back(ui):
    ctl, window, _ = ui
    key(window, Qt.Key.Key_Left)
    assert ctl.selected == 1
    key(window, Qt.Key.Key_Left)
    assert ctl.selected == 0
    key(window, Qt.Key.Key_Space)
    assert ctl.screen == "settings"
    key(window, Qt.Key.Key_Space)  # button returns to the main screen's default view
    assert ctl.screen == "main" and ctl.selected == 2 and ctl.viewOffset == 0


def test_tap_starts_project(ui):
    ctl, _, db = ui
    ctl.tap(4)
    assert db.running().project_id == ctl.projects.project_id(2)
    assert ctl.selected == 4


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
