"""Application entry point."""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from .clock import OffsetClock, make_clock
from .colors import COLOR_CYCLE
from .config import load_config
from .controller import Controller
from .db import Database
from .inputs import make_input

STARTER_PROJECTS = [  # (name, index into COLOR_CYCLE)
    ("Work", 5), ("Admin", 6), ("Learning", 4), ("Meetings", 0), ("Personal", 2), ("Other", 3),
]


def seed_starter_projects(db: Database) -> None:
    """On the very first start, create a few projects so the screen is not empty."""
    if db.get_meta("seeded"):
        return
    for name, color in STARTER_PROJECTS:
        db.add_project(name, COLOR_CYCLE[color])
    db.set_meta("seeded", "1")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline desk time tracker")
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    parser.add_argument("--db", help="database file (overrides config)")
    parser.add_argument("--fullscreen", action="store_true", help="fullscreen (overrides config)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.db:
        cfg.db_path = args.db
    if args.fullscreen:
        cfg.fullscreen = True

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Time Tracker")
    if cfg.hide_cursor:
        app.setOverrideCursor(Qt.CursorShape.BlankCursor)

    clock = make_clock(cfg.clock_driver)
    db = Database(Path(cfg.db_path).expanduser(), clock=clock)
    if isinstance(clock, OffsetClock):
        clock.bind(db)  # picks up the offset saved by an earlier "set date and time"
    seed_starter_projects(db)
    controller = Controller(db, clock=clock)
    controller.run_clock_check()  # opens the warning screen if the clock looks wrong

    knob = make_input(cfg, app)
    knob.turned.connect(controller.turn)
    knob.pressed.connect(controller.press)

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("ctl", controller)
    ctx.setContextProperty("projects", controller.projects)
    ctx.setContextProperty("cfgWidth", cfg.width)
    ctx.setContextProperty("cfgHeight", cfg.height)
    ctx.setContextProperty("cfgFullscreen", cfg.fullscreen)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    code = app.exec()
    del engine  # destroy QML before the controller it is bound to
    return code


if __name__ == "__main__":
    sys.exit(main())
