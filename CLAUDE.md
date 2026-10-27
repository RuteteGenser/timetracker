# Project rules

- **No animations** unless the user explicitly asks for one (this app runs on a
  Raspberry Pi and must stay light). That means no pulsing, fading, easing or
  transitions in QML or in the web version. State is shown statically.
  (The strip slide when scrolling was part of the original spec; see README.)
- Keep `docs/` (browser version) in step with the Python app only when asked.
