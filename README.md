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

## Run in a browser (GitHub Pages)

`docs/` holds a plain HTML/JS version of the same screen. It needs no build step
and no server: open `docs/index.html` through any static web server
(`python3 -m http.server -d docs`) or publish the `docs/` folder with GitHub Pages.

- Keys, mouse wheel and taps work like the knob and button.
- Data is stored in that browser only (localStorage), written on every change; a
  running timer survives a page reload. It is separate from the Pi's database.
- Its strip logic mirrors `src/timetracker/nav.py`; the real device app is the
  Python one.

## Clock

There is no internet on the device, so the app guards its own clock: Settings > Date & time sets it (a
running timer keeps its elapsed time), and at start, or if the time jumps back, a "Clock check" screen
warns when the clock is behind the last recorded time or before 2026. See `docs/hardware.md` for the
Pi's RTC battery and the helper script that lets the app set the real clock.

## Tests

```bash
pytest
```

The UI smoke tests run headless (`QT_QPA_PLATFORM=offscreen`). The browser
version has its own tests: `node --test tests/web/nav.test.mjs`.

## Design notes

- **Stack:** Python 3, PySide6 (Qt Quick/QML) for the UI, SQLite for storage.
- **Power-loss safety:** every change is its own committed transaction (WAL,
  `synchronous=FULL`). A running timer is an entry with a start time and no end
  time, so after a power cut it is still running and the elapsed time is right.
- **Input:** the app only sees an `InputSource` (turned / pressed signals).
  `driver = "sim"` or `"gpio"` in `config.toml` picks the implementation.
