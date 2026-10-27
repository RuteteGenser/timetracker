# Time tracker

A fully offline desk time tracker for a Raspberry Pi: a knob and a button for
daily use (pick a project, start/stop), a touchscreen for everything else.

Status: **milestone 1** (PC app with simulated controls). See `docs/hardware.md`
for the parts list and wiring.

## Run on a PC

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m timetracker
```

| Real hardware      | Keyboard (simulated) |
|--------------------|----------------------|
| Knob clockwise     | Right arrow          |
| Knob counter-clockwise | Left arrow       |
| Knob button        | Space or Enter       |

Everything is also tappable with the mouse or touchscreen. Settings live in
`config.toml`; data is stored in a SQLite file (`~/.local/share/timetracker/` by
default, or `--db PATH`).

## Tests

```bash
pytest
```

The UI smoke tests run headless (`QT_QPA_PLATFORM=offscreen`).

## Design notes

- **Stack:** Python 3, PySide6 (Qt Quick/QML) for the UI, SQLite for storage.
- **Power-loss safety:** every change is its own committed transaction (WAL,
  `synchronous=FULL`). A running timer is an entry with a start time and no end
  time, so after a power cut it is still running and the elapsed time is right.
- **Input:** the app only sees an `InputSource` (turned / pressed signals).
  `driver = "sim"` or `"gpio"` in `config.toml` picks the implementation.
