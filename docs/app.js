// Browser version of the time tracker: same behaviour as the Pi app, with the
// knob and button simulated by the keyboard (or mouse wheel) and data kept in
// this browser's localStorage. Nothing ever leaves the browser.

import { StripNav, SETTINGS, STYLE, FIRST_PROJECT } from "./nav.js";
import { Store, dayBounds } from "./store.js";

const COL_W = 200;
const TILE_W = 270;

const store = new Store();
const nav = new StripNav(store.projects().length);
let screen = "main";

const stage = document.getElementById("stage");
const strip = document.getElementById("strip");
const overlay = document.getElementById("overlay");
const btnSettings = document.getElementById("btn-settings");
const btnStyle = document.getElementById("btn-style");

// -- build tiles --------------------------------------------------------------

const tiles = []; // { project, el, timer, today }
for (const p of store.projects()) {
  const el = document.createElement("div");
  el.className = "tile";
  el.style.setProperty("--c", p.color);
  el.innerHTML = '<div class="band"></div><div class="name"></div><div class="badge">\u25cf RUNNING</div><div class="timer"></div><div class="today"></div>';
  el.querySelector(".name").textContent = p.name;
  const index = FIRST_PROJECT + tiles.length;
  el.addEventListener("click", () => tap(index));
  strip.appendChild(el);
  tiles.push({ project: p, el, timer: el.querySelector(".timer"), today: el.querySelector(".today") });
}
strip.style.width = `${COL_W + tiles.length * TILE_W}px`;

// -- rendering ----------------------------------------------------------------

const pad = (n) => String(n).padStart(2, "0");
const clock = (s) => `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
// Under an hour show minutes and seconds, so even a short timer visibly adds up.
const span = (s) => s < 3600
  ? `${Math.floor(s / 60)}m ${pad(s % 60)}s`
  : `${Math.floor(s / 3600)}h ${pad(Math.floor(s / 60) % 60)}m`;
const spanShort = (s) => (s < 60 ? `${s}s` : span(s));

function renderTimes() {
  const now = store.now();
  const [start, end] = dayBounds(now);
  const totals = store.totals(start, end);
  const run = store.running();
  for (const t of tiles) {
    const running = run?.projectId === t.project.id;
    t.el.classList.toggle("running", running);
    t.timer.textContent = running ? clock(Math.max(0, now - run.start)) : "";
    t.today.textContent = `Today  ${span(totals[t.project.id] ?? 0)}`;
  }
}

function renderNav() {
  btnSettings.classList.toggle("selected", nav.selected === SETTINGS);
  btnStyle.classList.toggle("selected", nav.selected === STYLE);
  tiles.forEach((t, i) => t.el.classList.toggle("selected", nav.selected === FIRST_PROJECT + i));
  const x = nav.offset === 0 ? 0 : COL_W + nav.offset * TILE_W;
  strip.style.transform = `translateX(${-x}px)`;
  overlay.classList.toggle("on", screen !== "main");
  document.getElementById("overlay-title").textContent = screen === "style" ? "Style" : "Settings";
}

// -- actions (same rules as src/timetracker/controller.py) ----------------------

function turn(steps) {
  if (note) {                       // in the note prompt the knob moves between Skip and Save
    note.focus = steps > 0 ? 1 : 0;
    renderNote();
    return;
  }
  if (screen !== "main") return;
  nav.move(steps);
  renderNav();
}

function activate(index) {
  if (index === SETTINGS) screen = "settings";
  else if (index === STYLE) screen = "style";
  else {
    const p = tiles[index - FIRST_PROJECT]?.project;
    if (p) {
      const run = store.running();
      let finished = null;
      if (run?.projectId === p.id) {
        finished = store.stop();
      } else {
        store.start(p.id);          // also ends the previously running entry
        finished = run;
      }
      if (finished) openNote(finished, tiles.find((t) => t.project.id === finished.projectId).project);
    }
  }
  renderTimes();
  renderNav();
}

function back() {
  screen = "main";
  nav.reset();
  renderNav();
}

function press() {
  if (note) note.focus === 1 ? noteSave() : noteSkip();
  else if (screen !== "main") back();
  else activate(nav.selected);
}

function tap(index) {
  if (screen !== "main" || note) return;
  nav.select(index);
  activate(index);
}

// -- note prompt ----------------------------------------------------------------

let note = null; // { entryId, name, seconds, text, focus: 0 = Skip, 1 = Save, shift }
const noteEl = document.getElementById("note");
const noteText = document.getElementById("note-text");
const KEY_ROWS = ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.-"];

function openNote(entry, project) {
  note = { entryId: entry.id, name: project.name, seconds: entry.end - entry.start, text: "", focus: 0, shift: true };
  document.getElementById("note-sub").textContent = `${project.name}  \u00b7  ${spanShort(note.seconds)}`;
  renderNote();
}

function noteClose() {
  note = null;
  renderNote();
}

function noteSave() {
  if (note.text.trim()) store.setNote(note.entryId, note.text);
  noteClose();
}

function noteSkip() {
  noteClose();
}

function noteType(ch) {
  if (note.text.length < 200) note.text += ch;
  note.shift = false;
  renderNote();
}

function noteBackspace() {
  note.text = note.text.slice(0, -1);
  renderNote();
}

function renderNote() {
  noteEl.classList.toggle("on", note !== null);
  if (!note) return;
  noteText.classList.toggle("empty", note.text === "");
  noteText.textContent = note.text === "" ? "Optional note\u2026" : note.text + "\u258f";
  const keys = document.getElementById("note-keys");
  keys.replaceChildren();
  const key = (label, cls, onClick) => {
    const k = document.createElement("div");
    k.className = `key ${cls}`;
    k.textContent = label;
    k.addEventListener("click", onClick);
    return k;
  };
  KEY_ROWS.forEach((chars, r) => {
    const row = document.createElement("div");
    row.className = "krow";
    for (const c of chars) {
      const ch = note.shift ? c.toUpperCase() : c;
      row.appendChild(key(ch, "", () => noteType(ch)));
    }
    if (r === 0) row.appendChild(key("\u232b", "", noteBackspace));
    else row.appendChild(key("", "", () => {})).style.visibility = "hidden";
    keys.appendChild(row);
  });
  const last = document.createElement("div");
  last.className = "krow";
  last.appendChild(key("Shift", `wide-s ${note.shift ? "shift-on" : ""}`, () => { note.shift = !note.shift; renderNote(); }));
  last.appendChild(key("space", "grow", () => noteType(" ")));
  last.appendChild(key("Skip", `wide-b ${note.focus === 0 ? "focus" : ""}`, noteSkip));
  last.appendChild(key("Save", `wide-b accent ${note.focus === 1 ? "focus" : ""}`, noteSave));
  keys.appendChild(last);
}

// -- input --------------------------------------------------------------------

btnSettings.addEventListener("click", () => tap(SETTINGS));
btnStyle.addEventListener("click", () => tap(STYLE));
document.getElementById("overlay-back").addEventListener("click", back);

window.addEventListener("keydown", (e) => {
  if (note && e.key === "Backspace") noteBackspace();
  else if (note && e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey) noteType(e.key);
  else if (e.key === "ArrowRight") turn(1);
  else if (e.key === "ArrowLeft") turn(-1);
  else if ((e.key === " " || e.key === "Enter") && !e.repeat) press();
  else return;
  e.preventDefault();
});

let wheelAcc = 0;
window.addEventListener("wheel", (e) => {
  wheelAcc += e.deltaY || e.deltaX;
  if (Math.abs(wheelAcc) >= 60) {
    turn(wheelAcc > 0 ? 1 : -1);
    wheelAcc = 0;
  }
}, { passive: true });

// -- scale the 1280x720 stage to the window ---------------------------------------

function fit() {
  const s = Math.min(window.innerWidth / 1280, (window.innerHeight - 20) / 720);
  stage.style.transform = `translate(${-640 * s}px, ${-360 * s - 10}px) scale(${s})`;
}
window.addEventListener("resize", fit);

fit();
renderTimes();
renderNav();
let lastSecond = store.now();
setInterval(() => {
  const s = store.now();
  if (s !== lastSecond) { lastSecond = s; renderTimes(); }
}, 200);
