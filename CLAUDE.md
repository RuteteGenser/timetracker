# Project rules

- **No animations** unless the user explicitly asks for one (this app runs on a
  Raspberry Pi and must stay light). That means no pulsing, fading, easing or
  transitions in QML or in the web version. State is shown statically.
  (The strip slide when scrolling was part of the original spec; see README.)
- **Always keep the GitHub Pages site up to date.** The site is `docs/` served from
  `main`, so every change to the app's behaviour or look must also be made in
  `docs/` (the browser version mirrors `src/timetracker/`: `nav.js` = `nav.py`,
  `store.js` = `db.py`, `app.js` + `style.css` = controller + QML), tested, and
  pushed to `main` in the same commit. Bump the `?v=N` on the script and
  stylesheet links in `docs/index.html` each time `docs/` changes, so browsers
  do not keep an old copy. Features that only make sense on the Pi (GPIO,
  kiosk boot, systemd) are the only exception.
