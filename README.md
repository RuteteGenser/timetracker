# Time tracker

A fully offline desk time tracker for a Raspberry Pi: a knob and a button for
daily use (pick a project, start/stop), a touchscreen for everything else.

Status: the PC app and the browser version are feature-complete for milestones 1-3
(tracking, notes, reports, project management, entry editing, colours, clock setting).
Not done yet: the power-loss kill test (milestone 4) and everything that needs a real
Pi: GPIO input, kiosk boot and the setup guide (milestones 5-6). See `docs/hardware.md`
for the parts list and wiring.

## What is on each screen

- **Main:** the project cards (press to start or stop; stopping asks for an optional note) and
  the column Settings / Style / Reports.
- **Style:** per card, colour (8 steps), name, a reset for today's time (two presses), and **More**
  (archive, move left / right, delete). A **+** card adds a project; **Archived** lists hidden
  projects (restore or delete).
- **Reports:** every entry of the day / week / month, grouped per project (projects A-Z, entries
  earliest first) with its note, and a total per project and overall. The period is live: turn the
  knob for the previous / next day; press to move around the buttons and down the list; press an
  entry to edit it. **Entries** opens the flat newest-first editor list; entries can be edited
  (project, start, end, note) or deleted. Changes that would overlap another entry, put the end before the start or
  lie in the future are refused with the reason.
- **Settings:** **Date & time** (sets the clock; a running timer keeps its elapsed time) and
  **Status** (clock check, last clock change, hardware clock, storage, counts, version).
- Destructive actions (delete, reset today) always need a second press, shown in dark red or
  orange.

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
