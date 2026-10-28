// Browser version of the time tracker: same behaviour as the Pi app, with the
// knob and button simulated by the keyboard (or mouse wheel) and data kept in
// this browser's localStorage. Nothing ever leaves the browser.
// The rules mirror src/timetracker/controller.py.

import { StripNav, ListNav, SETTINGS, STYLE, REPORTS, FIRST_PROJECT } from "./nav.js";
import { Store, dayBounds, nextColor } from "./store.js";

const SLOT_W = 250; // five equal slots across the 1250 px inside the 15 px margin
const STYLE_PARTS = 3; // colour, name, time: the order the knob visits them
const PART_COLOR = 0;
const PART_NAME = 1;
const PART_TIME = 2;

const store = new Store();
const projectCount = store.projects().length;
let nav = new StripNav(projectCount);
let screen = "main"; // a key of SCREEN_PARENT, or "main"
// Screens: "main", "style", list screens (vertical rows, knob scrolls) and detail screens.
const SCREEN_PARENT = { // where Back goes
  style: "main", settings: "main", reports: "main", datetime: "settings", status: "settings",
};
const LIST_SCREENS = new Set(["settings"]);
const LIST_TITLES = { settings: "Settings" };
const PLACEHOLDER_TITLES = { reports: "Reports", datetime: "Date & time", status: "Status" };
let list = new ListNav(0);
let listRows = []; // rows of the current list screen: { id, label, value }
let resetArmed = null; // Style item whose time reset waits for its confirming second press

const stage = document.getElementById("stage");
const strip = document.getElementById("strip");
const overlay = document.getElementById("overlay");
const btnSettings = document.getElementById("btn-settings");
const btnStyle = document.getElementById("btn-style");
const btnReports = document.getElementById("btn-reports");
const btnBack = document.getElementById("btn-back");

// -- build tiles --------------------------------------------------------------

// Each tile holds both looks: the main one and `.parts` (colour, name, time) for the Style screen.
const tiles = []; // { project, el, timer, today, parts: [colour, name, time], pname, pval }
for (const p of store.projects()) {
  const el = document.createElement("div");
  el.className = "tile";
  el.innerHTML =
    '<div class="band"></div><div class="name"></div><div class="badge">● RUNNING</div>' +
    '<div class="timer"></div><div class="today"></div>' +
    '<div class="parts">' +
    '<div class="part p-color"><span>Color</span></div>' +
    '<div class="part p-name"><b class="pname"></b><span>Rename</span></div>' +
    '<div class="part p-time"><span class="cap">Today</span><b class="pval"></b><span class="hint"></span></div>' +
    "</div>";
  const index = tiles.length;
  el.addEventListener("click", () => { if (screen === "main") tap(FIRST_PROJECT + index); });
  const parts = [...el.querySelectorAll(".part")];
  parts.forEach((part, i) => part.addEventListener("click", () => { if (screen === "style") tap(1 + STYLE_PARTS * index + i); }));
  strip.appendChild(el);
  tiles.push({
    project: p, el, parts,
    timer: el.querySelector(".timer"), today: el.querySelector(".today"),
    pname: el.querySelector(".pname"), pval: el.querySelector(".pval"), hint: el.querySelector(".hint"),
  });
}
strip.style.width = `${(tiles.length + 1) * SLOT_W}px`;

// -- rendering ----------------------------------------------------------------

const pad = (n) => String(n).padStart(2, "0");
const clock = (s) => `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
// Under an hour show minutes and seconds, so even a short timer visibly adds up.
const span = (s) => s < 3600
  ? `${Math.floor(s / 60)}m ${pad(s % 60)}s`
  : `${Math.floor(s / 3600)}h ${pad(Math.floor(s / 60) % 60)}m`;
const spanShort = (s) => (s < 60 ? `${s}s` : span(s));

// Shrink a name until it fits its box (wrapping at spaces; a single long word just gets smaller).
function fitText(el, minPx = 12) {
  el.style.fontSize = "";
  let size = parseFloat(getComputedStyle(el).fontSize);
  while (size > minPx && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)) {
    size -= 1;
    el.style.fontSize = `${size}px`;
  }
}

function fitNames() { // only visible names can be measured, so this runs again when the screen changes
  for (const t of tiles) {
    for (const el of [t.el.querySelector(".name"), t.pname]) if (el.offsetParent !== null) fitText(el);
  }
}

function renderTiles() { // names and colours
  for (const t of tiles) {
    t.el.style.setProperty("--c", t.project.color);
    t.el.querySelector(".name").textContent = t.project.name;
    t.pname.textContent = t.project.name;
  }
  fitNames();
}

function renderTimes() {
  const now = store.now();
  const [start, end] = dayBounds(now);
  const totals = store.totals(start, end);
  const run = store.running();
  for (const t of tiles) {
    const running = run?.projectId === t.project.id;
    const today = totals[t.project.id] ?? 0;
    t.el.classList.toggle("running", running);
    t.timer.textContent = running ? clock(Math.max(0, now - run.start)) : "";
    t.today.textContent = `Today  ${span(today)}`;
    t.pval.textContent = span(today);
  }
}

let fittedFor = null;

function renderNav() {
  const [card, part] = nav.cardAndPart();
  stage.classList.toggle("style-mode", screen === "style");
  if (fittedFor !== screen) { fittedFor = screen; fitNames(); }
  btnSettings.classList.toggle("selected", screen === "main" && nav.selected === SETTINGS);
  btnStyle.classList.toggle("selected", screen === "main" && nav.selected === STYLE);
  btnReports.classList.toggle("selected", screen === "main" && nav.selected === REPORTS);
  btnBack.classList.toggle("selected", screen === "style" && nav.selected === 0);
  tiles.forEach((t, i) => {
    t.el.classList.toggle("selected", screen === "main" && card === i);
    t.parts.forEach((el, p) => el.classList.toggle("selected", screen === "style" && card === i && part === p));
    const armed = screen === "style" && resetArmed === 1 + STYLE_PARTS * i + PART_TIME && nav.selected === resetArmed;
    t.parts[PART_TIME].classList.toggle("armed", armed);
    t.hint.textContent = armed ? "Confirm reset" : "Reset time";
  });
  strip.style.transform = `translateX(${-nav.offset * SLOT_W}px)`;
  const isList = LIST_SCREENS.has(screen);
  document.getElementById("list").classList.toggle("on", isList);
  overlay.classList.toggle("on", screen !== "main" && screen !== "style" && !isList);
  document.getElementById("overlay-title").textContent = PLACEHOLDER_TITLES[screen] ?? "";
  if (isList) renderList();
}

function renderList() {
  document.getElementById("list-title").textContent = LIST_TITLES[screen];
  const box = document.getElementById("list-rows");
  box.replaceChildren();
  listRows.slice(list.offset, list.offset + list.visible).forEach((r, i) => {
    const index = list.offset + i;
    const el = document.createElement("div");
    el.className = `lrow ${r.id === "back" ? "back" : ""} ${index === list.selected ? "selected" : ""}`;
    el.innerHTML = '<span class="label"></span><span class="value"></span>';
    el.querySelector(".label").textContent = r.label;
    el.querySelector(".value").textContent = r.value;
    el.addEventListener("click", () => tap(index));
    box.appendChild(el);
  });
}

// -- actions ------------------------------------------------------------------

function rowsFor(name) {
  const row = (id, label, value = "") => ({ id, label, value });
  if (name === "settings") {
    const d = new Date(store.now() * 1000);
    const p2 = (n) => String(n).padStart(2, "0");
    const when = `${p2(d.getDate())} ${d.toLocaleString("en", { month: "short" })} ${d.getFullYear()}  ${p2(d.getHours())}:${p2(d.getMinutes())}`;
    return [row("back", "Back"), row("datetime", "Date & time", when), row("status", "Status")];
  }
  return [];
}

/** Show a screen; list screens get fresh rows and selection. */
function openScreen(name) {
  if (LIST_SCREENS.has(name)) {
    listRows = rowsFor(name);
    list = new ListNav(listRows.length);
  }
  screen = name;
}

function activateList(index) {
  const r = listRows[index];
  if (!r) return;
  if (r.id === "back") back();
  else openScreen(r.id);
}

function useNav(newNav) {
  nav = newNav;
  resetArmed = null;
}

function turn(steps) {
  if (note) {                       // in a text prompt the knob moves between its buttons
    const lowest = note.kind === "rename" ? NOTE_SKIP : NOTE_DELETE;
    const focus = Math.max(lowest, Math.min(NOTE_SAVE, note.focus + steps));
    if (focus !== note.focus) note.armed = false; // moving away cancels a pending delete
    note.focus = focus;
    renderNote();
    return;
  }
  if (LIST_SCREENS.has(screen)) {
    list.move(steps);
    renderNav();
    return;
  }
  if (screen !== "main" && screen !== "style") return;
  const before = nav.selected;
  nav.move(steps);
  if (nav.selected !== before) resetArmed = null; // moving away cancels a pending time reset
  renderNav();
}

function toggleProject(p) {
  const run = store.running();
  let finished = null;
  if (run?.projectId === p.id) {
    finished = store.stop();
  } else {
    store.start(p.id);              // also ends the previously running entry
    finished = run;
  }
  if (finished) openNote(finished, tiles.find((t) => t.project.id === finished.projectId).project);
}

function activateStyle(index) {
  if (index === 0) { back(); return; } // the Back button in the column
  const card = Math.floor((index - 1) / STYLE_PARTS);
  const part = (index - 1) % STYLE_PARTS;
  const project = tiles[card].project;
  if (part === PART_COLOR) {
    project.color = nextColor(project.color);
    store.setProjectColor(project.id, project.color);
    renderTiles();
  } else if (part === PART_NAME) {
    openRename(project);
  } else if (resetArmed !== index) {  // time: the first press only arms it
    resetArmed = index;
  } else {                            // the second press resets today's total
    resetArmed = null;
    store.resetToday(project.id);
  }
}

function activate(index) {
  if (screen === "style") activateStyle(index);
  else if (index === SETTINGS) openScreen("settings");
  else if (index === REPORTS) openScreen("reports");
  else if (index === STYLE) {
    useNav(new StripNav(nav.projectCount, 1, STYLE_PARTS));
    screen = "style";
  } else {
    const p = tiles[index - FIRST_PROJECT]?.project;
    if (p) toggleProject(p);
  }
  renderTimes();
  renderNav();
}

function back() { // go up one level; the main screen comes back in its default view
  const parent = SCREEN_PARENT[screen] ?? "main";
  if (parent === "main") {
    useNav(new StripNav(nav.projectCount));
    screen = "main";
  } else {
    openScreen(parent);
  }
  renderNav();
}

function press() {
  if (note) [noteDelete, noteSkip, noteSave][note.focus]();
  else if (LIST_SCREENS.has(screen)) { activateList(list.selected); renderNav(); }
  else if (screen !== "main" && screen !== "style") back(); // placeholder screens: any press goes back
  else activate(nav.selected);
}

function tap(index) {
  if (note) return;
  if (LIST_SCREENS.has(screen)) {
    list.select(index);
    activateList(index);
    renderNav();
    return;
  }
  if (screen !== "main" && screen !== "style") return;
  const before = nav.selected;
  nav.select(index);
  if (nav.selected !== before) resetArmed = null;
  activate(index);
}

// -- text prompt: note after a stop, or renaming a project ---------------------------

const NOTE_DELETE = 0; // prompt buttons, left to right; rename only has Cancel (= NOTE_SKIP) and Save
const NOTE_SKIP = 1;
const NOTE_SAVE = 2;
let note = null; // { kind: "note" | "rename", entryId, project, text, focus, shift, armed }
const noteEl = document.getElementById("note");
const noteText = document.getElementById("note-text");
const KEY_ROWS = ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.-"];

function openNote(entry, project) {
  note = { kind: "note", entryId: entry.id, project, text: "", focus: NOTE_SKIP, shift: true, armed: false };
  document.getElementById("note-title").textContent = "What did you do?";
  document.getElementById("note-sub").textContent = `${project.name}  ·  ${spanShort(entry.end - entry.start)}`;
  renderNote();
}

function openRename(project) {
  note = { kind: "rename", project, text: project.name, focus: NOTE_SKIP, shift: false, armed: false };
  document.getElementById("note-title").textContent = "Rename";
  document.getElementById("note-sub").textContent = project.name;
  renderNote();
}

function noteClose() {
  note = null;
  renderNote();
}

function noteSave() {
  if (note.kind === "rename") {
    const name = note.text.trim();
    if (name) {
      store.renameProject(note.project.id, name);
      note.project.name = name;
      renderTiles();
    }
  } else if (note.text.trim()) {
    store.setNote(note.entryId, note.text);
  }
  noteClose();
}

function noteSkip() { // skips the note, or cancels the rename
  noteClose();
}

// Throw away the timer that was just stopped (its time no longer counts).
// The first press only arms the button (dark red, "Confirm"); the second deletes.
function noteDelete() {
  if (note.kind !== "note") return;
  if (!note.armed) {
    note.armed = true;
    renderNote();
    return;
  }
  store.deleteEntry(note.entryId);
  noteClose();
  renderTimes();
}

function noteType(ch) {
  if (note.text.length < 200) note.text += ch;
  note.shift = false;
  note.armed = false;
  renderNote();
}

function noteBackspace() {
  note.text = note.text.slice(0, -1);
  note.armed = false;
  renderNote();
}

function renderNote() {
  noteEl.classList.toggle("on", note !== null);
  renderNav();
  renderTimes();
  if (!note) return;
  noteText.classList.toggle("empty", note.text === "");
  noteText.textContent = note.text === "" ? (note.kind === "rename" ? "Name…" : "Optional note…") : note.text + "▏";
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
    if (r === 0) row.appendChild(key("⌫", "", noteBackspace));
    else row.appendChild(key("", "", () => {})).style.visibility = "hidden";
    keys.appendChild(row);
  });
  const last = document.createElement("div");
  last.className = "krow";
  last.appendChild(key("Shift", `wide-s ${note.shift ? "shift-on" : ""}`, () => { note.shift = !note.shift; renderNote(); }));
  last.appendChild(key("space", "grow", () => noteType(" ")));
  if (note.kind === "note") {
    last.appendChild(key(note.armed ? "Confirm" : "Delete", `wide-b ${note.armed ? "armed" : "danger"} ${note.focus === NOTE_DELETE ? "focus" : ""}`, noteDelete));
  }
  last.appendChild(key(note.kind === "rename" ? "Cancel" : "Skip", `wide-b ${note.focus === NOTE_SKIP ? "focus" : ""}`, noteSkip));
  last.appendChild(key("Save", `wide-b accent ${note.focus === NOTE_SAVE ? "focus" : ""}`, noteSave));
  keys.appendChild(last);
}

// -- input --------------------------------------------------------------------

btnSettings.addEventListener("click", () => tap(SETTINGS));
btnStyle.addEventListener("click", () => tap(STYLE));
btnReports.addEventListener("click", () => tap(REPORTS));
btnBack.addEventListener("click", () => tap(0));
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
renderTiles();
renderTimes();
renderNav();
let lastSecond = store.now();
setInterval(() => {
  const s = store.now();
  if (s !== lastSecond) { lastSecond = s; renderTimes(); }
}, 200);
