// Browser version of the time tracker: same behaviour as the Pi app, with the
// knob and button simulated by the keyboard (or mouse wheel) and data kept in
// this browser's localStorage. Nothing ever leaves the browser.
// The rules mirror src/timetracker/controller.py.

import { StripNav, ListNav, SETTINGS, STYLE, REPORTS, FIRST_PROJECT } from "./nav.js";
import { Store, EntryError, COLOR_CYCLE, dayBounds, nextColor } from "./store.js";
import { KINDS, periodBounds, shiftPeriod, stepLimits, summary } from "./summaries.js";
import { statusRows } from "./status.js";

const SLOT_W = 250; // five equal slots across the 1250 px inside the 15 px margin
// Style screen: column items Back and Archived, then four parts per card in the order the knob
// visits them, then a trailing "+" card that adds a project.
const STYLE_COLUMN = 2;
const STYLE_PARTS = 4;
const PART_COLOR = 0;
const PART_NAME = 1;
const PART_TIME = 2;
const PART_MORE = 3;

const store = new Store();
const projectCount = store.projects().length;
let nav = new StripNav(projectCount);
let screen = "main"; // a key of SCREEN_PARENT, or "main"
// Screens: "main", "style", list screens (vertical rows, knob scrolls) and detail screens.
const SCREEN_PARENT = { // where Back goes
  style: "main", settings: "main", reports: "main", clockwarn: "main", datetime: "settings", status: "settings",
  projectmenu: "style", archived: "style", archivedmenu: "archived", entries: "reports", entryedit: "entries",
};
const LIST_SCREENS = new Set(["settings", "clockwarn", "projectmenu", "archived", "archivedmenu", "entries", "entryedit", "status"]);
const NOTE_LISTS = new Set(["clockwarn", "entryedit"]); // list screens with an explanation under the title (one row less fits)
const LIST_TITLES = { settings: "Settings", clockwarn: "Clock check", archived: "Archived projects", status: "Status" };
let clockProblem = ""; // message of the clock warning being shown
let returnTo = null; // where Back from Date & time goes, if not Settings
let list = new ListNav(0);
let listRows = []; // rows of the current list screen: { id, label, value }
let resetArmed = null; // Style item whose time reset waits for its confirming second press
let menuPid = null; // project the open menu (More / Archived) is about
let menuArmed = false; // Delete in that menu was pressed once and waits for confirmation
let entryId = null; // entry open in the editor
let entryError = ""; // why the last change to it was refused
let dtEntryField = null; // "start" or "end" while Date & time edits an entry
const listMemory = {}; // selected row of list screens we left, restored on Back

const stage = document.getElementById("stage");
const strip = document.getElementById("strip");
const btnSettings = document.getElementById("btn-settings");
const btnStyle = document.getElementById("btn-style");
const btnReports = document.getElementById("btn-reports");
const btnBack = document.getElementById("btn-back");
const btnArchived = document.getElementById("btn-archived");
const addTile = document.getElementById("addtile");

// -- build tiles --------------------------------------------------------------

// Each tile holds both looks: the main one and `.parts` (colour, name, time, More) for the Style screen.
// The tiles are rebuilt whenever projects are added, archived, deleted or moved.
let tiles = []; // { project, el, timer, today, parts, pname, pval, hint }

function buildTiles() {
  for (const t of tiles) t.el.remove();
  tiles = [];
  for (const p of store.projects()) {
    const el = document.createElement("div");
    el.className = "tile";
    el.innerHTML =
      '<div class="band"></div><div class="name"></div><div class="badge">\u25cf RUNNING</div>' +
      '<div class="timer"></div><div class="today"></div>' +
      '<div class="parts">' +
      '<div class="part p-color"><span>Color</span></div>' +
      '<div class="part p-name"><b class="pname"></b><span>Rename</span></div>' +
      '<div class="part p-time"><span class="cap">Today</span><b class="pval"></b><span class="hint"></span></div>' +
      '<div class="part p-more">More\u2026</div>' +
      "</div>";
    const index = tiles.length;
    el.addEventListener("click", () => { if (screen === "main") tap(FIRST_PROJECT + index); });
    const parts = [...el.querySelectorAll(".part")];
    parts.forEach((part, i) => part.addEventListener("click", () => { if (screen === "style") tap(STYLE_COLUMN + STYLE_PARTS * index + i); }));
    strip.insertBefore(el, addTile);
    tiles.push({
      project: p, el, parts,
      timer: el.querySelector(".timer"), today: el.querySelector(".today"),
      pname: el.querySelector(".pname"), pval: el.querySelector(".pval"), hint: el.querySelector(".hint"),
    });
  }
  strip.style.width = `${(tiles.length + 2) * SLOT_W}px`; // the column, the cards and the "+" card
}

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
  btnArchived.classList.toggle("selected", screen === "style" && nav.selected === 1);
  addTile.classList.toggle("selected", screen === "style" && card === tiles.length);
  tiles.forEach((t, i) => {
    t.el.classList.toggle("selected", screen === "main" && card === i);
    t.parts.forEach((el, p) => el.classList.toggle("selected", screen === "style" && card === i && part === p));
    const armed = screen === "style" && resetArmed === STYLE_COLUMN + STYLE_PARTS * i + PART_TIME && nav.selected === resetArmed;
    t.parts[PART_TIME].classList.toggle("armed", armed);
    t.hint.textContent = armed ? "Confirm reset" : "Reset time";
  });
  strip.style.transform = `translateX(${-nav.offset * SLOT_W}px)`;
  const isList = LIST_SCREENS.has(screen);
  document.getElementById("list").classList.toggle("on", isList);
  document.getElementById("rep").classList.toggle("on", screen === "reports");
  if (screen === "reports") renderRep();
  document.getElementById("dt").classList.toggle("on", screen === "datetime");
  if (screen === "datetime") renderDt();
  if (isList) renderList();
}

function renderList() {
  document.getElementById("list-title").textContent = listTitle();
  const noteText = listNote();
  document.getElementById("list-note").textContent = noteText;
  document.getElementById("list").classList.toggle("has-note", noteText !== "");
  const box = document.getElementById("list-rows");
  box.replaceChildren();
  listRows.slice(list.offset, list.offset + list.visible).forEach((r, i) => {
    const index = list.offset + i;
    const el = document.createElement("div");
    el.className = `lrow ${r.id === "back" ? "back" : ""} ${r.kind ?? ""} ${index === list.selected ? "selected" : ""}`;
    el.innerHTML = '<span class="label"></span><span class="value"></span>';
    el.querySelector(".label").textContent = r.label;
    el.querySelector(".value").textContent = r.value;
    el.addEventListener("click", () => tap(index));
    box.appendChild(el);
  });
}

// -- actions ------------------------------------------------------------------

function listTitle() {
  if (screen === "projectmenu" || screen === "archivedmenu") {
    return store.data.projects.find((p) => p.id === menuPid)?.name ?? "";
  }
  if (screen === "entries") return `Entries \u00b7 ${rep.data.label}`;
  if (screen === "entryedit") return "Edit entry";
  return LIST_TITLES[screen];
}

function listNote() {
  if (screen === "entryedit") return entryError || "Changes are saved as you make them.";
  return screen === "clockwarn" ? clockProblem : "";
}

function rowsFor(name) {
  const row = (id, label, value = "", kind = "") => ({ id, label, value, kind });
  const del = row("delete", menuArmed ? "Confirm delete" : "Delete", "", menuArmed ? "armed" : "danger");
  if (name === "settings") {
    const d = new Date(store.now() * 1000);
    const p2 = (n) => String(n).padStart(2, "0");
    const when = `${p2(d.getDate())} ${d.toLocaleString("en", { month: "short" })} ${d.getFullYear()}  ${p2(d.getHours())}:${p2(d.getMinutes())}`;
    return [row("back", "Back"), row("datetime", "Date & time", when), row("status", "Status")];
  }
  if (name === "clockwarn") return [row("datetime", "Set date and time"), row("ignore", "Ignore")];
  if (name === "projectmenu") {
    const ids = store.projects().map((p) => p.id);
    const card = Math.max(0, ids.indexOf(menuPid));
    const rows = [row("back", "Cancel"), row("archive", "Archive")];
    if (card > 0) rows.push(row("moveleft", "Move left"));
    if (card < ids.length - 1) rows.push(row("moveright", "Move right"));
    return [...rows, del];
  }
  if (name === "archived") {
    const archived = store.archivedProjects();
    if (!archived.length) return [row("back", "Back"), row("none", "No archived projects")];
    return [row("back", "Back"), ...archived.map((p) => row(`project:${p.id}`, p.name, "Restore or delete"))];
  }
  if (name === "archivedmenu") return [row("back", "Cancel"), row("restore", "Restore"), del];
  if (name === "status") return [row("back", "Back"), ...statusRows(store).map((r) => row("info", r.label, r.value))];
  if (name === "entries") return entryRows(row);
  if (name === "entryedit") {
    const e = store.entry(entryId);
    if (!e) return [row("back", "Back")];
    const project = store.data.projects.find((p) => p.id === e.projectId);
    return [
      row("back", "Done"),
      row("project", "Project", project?.name ?? "?"),
      row("start", "Start", fmtFull(e.start)),
      row("end", "End", e.end === null ? "running" : fmtFull(e.end)),
      row("note", "Note", e.note || "none"),
      del,
    ];
  }
  return [];
}

const monthShort = (d) => d.toLocaleString("en", { month: "short" });
const fmtDate = (d) => `${d.getDate()} ${monthShort(d)}`; // 28 Oct
const fmtTime = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`; // 09:15
const fmtFull = (ts) => { const d = new Date(ts * 1000); return `${pad(d.getDate())} ${monthShort(d)} ${d.getFullYear()}  ${fmtTime(d)}`; };

/** The entries of the period shown in Reports, newest first. */
function entryRows(row) {
  const names = Object.fromEntries(store.data.projects.map((p) => [p.id, p.name]));
  const rows = [row("back", "Back")];
  for (const e of store.entriesBetween(rep.data.start, rep.data.end).reverse()) {
    const start = new Date(e.start * 1000);
    let end, duration;
    if (e.end === null) {
      end = "now";
      duration = "running";
    } else {
      const stop = new Date(e.end * 1000);
      end = stop.toDateString() === start.toDateString() ? fmtTime(stop) : `${fmtDate(stop)} ${fmtTime(stop)}`;
      duration = span(e.end - e.start);
    }
    const label = `${fmtDate(start)}  ${fmtTime(start)}\u2013${end}  ${names[e.projectId] ?? "?"}${e.note ? "  \u270e" : ""}`;
    rows.push(row(`entry:${e.id}`, label, duration));
  }
  if (rows.length === 1) rows.push(row("none", "No entries in this period"));
  return rows;
}

/**
 * Show a screen. List screens get fresh rows; with restore (coming Back) the outline returns to the
 * row that was open, otherwise it starts on the first real row.
 */
function openScreen(name, restore = false) {
  if (name === "reports") repRefresh(); // the entries may have been edited meanwhile
  if (LIST_SCREENS.has(name)) {
    entryError = "";
    listRows = rowsFor(name);
    list = new ListNav(listRows.length, NOTE_LISTS.has(name) ? 5 : 6, name === "clockwarn" ? 0 : null);
    if (restore && name in listMemory) list.select(listMemory[name]);
  }
  screen = name;
}

function activateList(index) {
  const r = listRows[index];
  if (!r) return;
  listMemory[screen] = index;
  if (r.id === "back") back();
  else if (r.id === "ignore") ignoreClockProblem();
  else if (r.id === "datetime") openDatetime(screen === "clockwarn" ? "main" : null);
  else if (r.id === "archive") menuArchive();
  else if (r.id === "moveleft" || r.id === "moveright") menuMove(r.id === "moveleft" ? -1 : 1);
  else if (r.id === "delete") menuDelete();
  else if (r.id === "restore") menuRestore();
  else if (r.id.startsWith("entry:")) { entryId = Number(r.id.slice(6)); menuArmed = false; openScreen("entryedit"); }
  else if (r.id === "project") entryCycleProject();
  else if (r.id === "start" || r.id === "end") openDatetime("entryedit", r.id);
  else if (r.id === "note") openEntryNote();
  else if (r.id.startsWith("project:")) { menuPid = Number(r.id.slice(8)); menuArmed = false; openScreen("archivedmenu"); }
  else if (r.id === "none" || r.id === "info") return; // nothing to open
  else openScreen(r.id);
}

function useNav(newNav) {
  nav = newNav;
  resetArmed = null;
}

function turn(steps) {
  if (note) {                       // in a text prompt the knob moves between its buttons
    const lowest = note.kind === "note" ? NOTE_DELETE : NOTE_SKIP; // only notes have Delete
    const focus = Math.max(lowest, Math.min(NOTE_SAVE, note.focus + steps));
    if (focus !== note.focus) note.armed = false; // moving away cancels a pending delete
    note.focus = focus;
    renderNote();
    return;
  }
  if (LIST_SCREENS.has(screen)) {
    if (list.move(steps) && menuArmed) { // moving away cancels a pending delete
      menuArmed = false;
      listRows = rowsFor(screen);
    }
    renderNav();
    return;
  }
  if (screen === "datetime") {
    if (dt.editing) dtAdjust(dt.focus, steps);
    else dt.focus = Math.max(0, Math.min(DT_SAVE, dt.focus + steps));
    renderNav();
    return;
  }
  if (screen === "reports") {
    if (rep.stepping) repStep(steps);
    else { rep.focus = Math.max(0, Math.min(REP_ITEMS - 1, rep.focus + steps)); renderNav(); }
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

function newStyleNav() {
  return new StripNav(nav.projectCount, STYLE_COLUMN, STYLE_PARTS, 1);
}

function selectStyle(card, part) {
  nav.select(STYLE_COLUMN + card * STYLE_PARTS + part);
}

/** Projects were added, archived, deleted or moved: rebuild the cards. */
function refreshProjects() {
  buildTiles();
  nav.setProjectCount(tiles.length);
  renderTiles();
  renderTimes();
  fittedFor = null;
}

function activateStyle(index) {
  if (index === 0) { back(); return; }               // Back
  if (index === 1) { openScreen("archived"); return; } // Archived
  if (index === STYLE_COLUMN + tiles.length * STYLE_PARTS) { openAdd(); return; } // the "+" card
  const card = Math.floor((index - STYLE_COLUMN) / STYLE_PARTS);
  const part = (index - STYLE_COLUMN) % STYLE_PARTS;
  const project = tiles[card].project;
  if (part === PART_COLOR) {
    project.color = nextColor(project.color);
    store.setProjectColor(project.id, project.color);
    renderTiles();
  } else if (part === PART_NAME) {
    openRename(project);
  } else if (part === PART_TIME) {
    if (resetArmed !== index) {                      // the first press only arms it
      resetArmed = index;
    } else {                                         // the second press resets today's total
      resetArmed = null;
      store.resetToday(project.id);
    }
  } else {
    menuPid = project.id;
    menuArmed = false;
    openScreen("projectmenu");
  }
}

// -- project menus: More (on a card) and the Archived list ----------------------------------

const menuCard = () => Math.max(0, store.projects().findIndex((p) => p.id === menuPid));

function leaveMenu(parent) {
  menuArmed = false;
  openScreen(parent);
}

function menuArchive() {
  const card = menuCard();
  store.archiveProject(menuPid); // also stops its timer, if it was running
  refreshProjects();
  leaveMenu("style");
  selectStyle(Math.min(card, Math.max(0, tiles.length - 1)), PART_COLOR);
}

function menuMove(direction) {
  let card = menuCard();
  if (store.moveProject(menuPid, direction)) {
    refreshProjects();
    card += direction;
  }
  leaveMenu("style");
  selectStyle(card, PART_MORE); // the outline follows the project, ready to move it again
}

function menuRestore() {
  store.archiveProject(menuPid, false);
  refreshProjects();
  leaveMenu("archived");
}

// Delete a project and all its entries. The first press only arms it, the second does it.
function menuDelete() {
  if (!menuArmed) {
    menuArmed = true;
    listRows = rowsFor(screen);
    return;
  }
  if (screen === "entryedit") {
    store.deleteEntry(entryId);
    renderTimes();
    menuArmed = false;
    openScreen("entries", true);
    return;
  }
  const card = menuCard();
  const fromArchive = screen === "archivedmenu";
  store.deleteProject(menuPid);
  refreshProjects();
  leaveMenu(fromArchive ? "archived" : "style");
  if (!fromArchive) selectStyle(Math.min(card, Math.max(0, tiles.length - 1)), PART_COLOR);
}

function activate(index) {
  if (screen === "style") activateStyle(index);
  else if (index === SETTINGS) openScreen("settings");
  else if (index === REPORTS) openReports();
  else if (index === STYLE) {
    useNav(newStyleNav());
    screen = "style";
  } else {
    const p = tiles[index - FIRST_PROJECT]?.project;
    if (p) toggleProject(p);
  }
  renderTimes();
  renderNav();
}

function back() { // go up one level; the main screen comes back in its default view
  const parent = returnTo || SCREEN_PARENT[screen] || "main";
  returnTo = null;
  if (parent === "main") {
    useNav(new StripNav(nav.projectCount));
    screen = "main";
  } else {
    openScreen(parent, true);
  }
  renderNav();
}

function press() {
  if (note) [noteDelete, noteSkip, noteSave][note.focus]();
  else if (LIST_SCREENS.has(screen)) { activateList(list.selected); renderNav(); }
  else if (screen === "datetime") dtPress();
  else if (screen === "reports") repPress();
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

// -- entries: browse and edit ------------------------------------------------------------------

/** Give the entry to the next project (archived ones only if it already belongs to one). */
function entryCycleProject() {
  const e = store.entry(entryId);
  const ids = store.data.projects.filter((p) => !p.archived || p.id === e.projectId).map((p) => p.id);
  try {
    store.updateEntry(entryId, { projectId: ids[(ids.indexOf(e.projectId) + 1) % ids.length] });
    entryError = "";
  } catch (err) {
    if (!(err instanceof EntryError)) throw err;
    entryError = err.message;
  }
  listRows = rowsFor("entryedit");
}

function openEntryNote() {
  const e = store.entry(entryId);
  const project = store.data.projects.find((p) => p.id === e.projectId);
  note = { kind: "entrynote", project, text: e.note, focus: NOTE_SKIP, shift: e.note === "", armed: false };
  document.getElementById("note-title").textContent = "Note";
  document.getElementById("note-sub").textContent = project.name;
  renderNote();
}

// -- reports ----------------------------------------------------------------------------------

// Focusable items left to right: Back, Day, Week, Month, Entries (the entries of the period shown) and
// the period itself. Pressing the period starts "stepping": turn = older / newer period, press again to stop.
const REP_BACK = 0;
const REP_ENTRIES = 4;
const REP_PERIOD = 5;
const REP_ITEMS = 6;
let rep = { kind: "day", anchor: 0, focus: REP_PERIOD, stepping: false, data: null, limits: [0, 0] };

function openReports() {
  rep = { kind: "day", anchor: store.now(), focus: REP_PERIOD, stepping: false, data: null, limits: [0, 0] };
  repRefresh();
  screen = "reports";
}

function repRefresh() {
  const now = store.now();
  rep.data = summary(store, rep.kind, rep.anchor, now);
  rep.limits = stepLimits(store, rep.kind, now);
}

/** Move to an older (negative) or newer (positive) period, never past the first entry or today. */
function repStep(steps) {
  const [oldest, current] = rep.limits;
  rep.anchor = Math.max(oldest, Math.min(current, shiftPeriod(rep.anchor, rep.kind, steps)));
  repRefresh();
  renderNav();
}

/** Change Day / Week / Month. The moment being looked at stays, unless the new kind's limits force it inside. */
function repSetKind(kind) {
  rep.kind = kind;
  rep.limits = stepLimits(store, kind, store.now());
  const start = periodBounds(rep.anchor, kind)[0];
  if (start < rep.limits[0]) rep.anchor = rep.limits[0];
  else if (start > rep.limits[1]) rep.anchor = rep.limits[1];
  repRefresh();
}

function repPressItem(item) {
  if (item === REP_BACK) back();
  else if (item < REP_ENTRIES) repSetKind(KINDS[item - 1]);
  else if (item === REP_ENTRIES) { openScreen("entries"); renderNav(); }
}

function repPress() {
  if (rep.focus < REP_PERIOD) repPressItem(rep.focus);
  else rep.stepping = !rep.stepping;
  if (screen === "reports") renderNav();
}

function repTap(item) {
  rep.stepping = item === REP_PERIOD && rep.focus === item ? !rep.stepping : false;
  rep.focus = item;
  repPressItem(item);
  if (screen === "reports") renderNav();
}

function renderRep() {
  const d = rep.data;
  const key = (label, cls, onClick) => {
    const k = document.createElement("div");
    k.className = `key ${cls}`;
    k.textContent = label;
    k.addEventListener("click", onClick);
    return k;
  };
  const controls = document.getElementById("rep-controls"); // first row: Back, Day, Week, Month, Entries
  controls.replaceChildren();
  controls.appendChild(key("Back", rep.focus === 0 ? "focus" : "", () => repTap(0)));
  ["Day", "Week", "Month"].forEach((label, i) => {
    controls.appendChild(key(label, `${rep.kind === KINDS[i] ? "active" : ""} ${rep.focus === i + 1 ? "focus" : ""}`, () => repTap(i + 1)));
  });
  controls.appendChild(key("Entries", rep.focus === REP_ENTRIES ? "focus" : "", () => repTap(REP_ENTRIES)));

  const period = document.getElementById("rep-period"); // second row: older, the period, newer and the total
  period.replaceChildren();
  period.appendChild(key("\u25c0", d.start > rep.limits[0] ? "" : "dim", () => repStep(-1)));
  const label = document.createElement("div");
  label.className = `rperiod ${rep.stepping ? "stepping" : ""} ${rep.focus === REP_PERIOD ? "focus" : ""}`;
  label.textContent = d.label;
  label.addEventListener("click", () => repTap(REP_PERIOD));
  period.appendChild(label);
  period.appendChild(key("\u25b6", d.start < rep.limits[1] ? "" : "dim", () => repStep(1)));
  const total = document.createElement("div");
  total.className = "total";
  total.innerHTML = '<span class="lbl">Total</span><span class="val"></span>';
  total.querySelector(".val").textContent = repSpan(d.total);
  period.appendChild(total);

  const chart = document.getElementById("rep-chart");
  chart.replaceChildren();
  if (d.total === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Nothing tracked in this period";
    chart.appendChild(empty);
    return;
  }
  const max = Math.max(1, ...d.rows.map((r) => r.seconds));
  const rowH = Math.min(64, chart.clientHeight / Math.max(1, d.rows.length));
  const barW = chart.clientWidth - 250 - 170 - 20;
  for (const r of d.rows) {
    const row = document.createElement("div");
    row.className = "rrow";
    row.style.height = `${rowH}px`;
    row.innerHTML = '<div class="rname"></div><div class="rbar"></div><div class="rval"></div>';
    const name = row.querySelector(".rname");
    name.textContent = r.name + (r.archived ? " (archived)" : "");
    name.classList.toggle("archived", r.archived);
    const bar = row.querySelector(".rbar");
    bar.style.background = r.color;
    bar.style.height = `${Math.min(rowH * 0.62, 40)}px`;
    bar.style.width = `${r.seconds > 0 ? Math.max(6, (barW * r.seconds) / max) : 0}px`;
    const val = row.querySelector(".rval");
    val.textContent = repSpan(r.seconds);
    val.style.left = `${250 + barW + 20}px`;
    val.classList.toggle("zero", r.seconds === 0);
    chart.appendChild(row);
  }
}

// Under an hour show minutes and seconds; from an hour up, hours and minutes.
function repSpan(s) {
  if (s <= 0) return "\u2013";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (s < 3600) return `${m}m ${pad(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${pad(m % 60)}m`;
}

// -- clock: sanity check and the Date & time screen ---------------------------------------

// Five fields, then Cancel and Save. The knob moves the outline over them; pressing a field edits it
// (turn changes the value, press again to finish).
const DT_CANCEL = 5;
const DT_SAVE = 6;
const DT_LABELS = ["Year", "Month", "Day", "Hour", "Minute"];
let dt = { initial: [], fields: [], focus: 0, editing: false, error: "" };
let lastBeat = 0;

const daysIn = (y, m) => new Date(y, m, 0).getDate();

function runClockCheck() { // at start, and when the clock jumps back while running
  const problem = store.clockProblem();
  if (problem) {
    clockProblem = problem;
    openScreen("clockwarn");
    renderNav();
  }
}

function ignoreClockProblem() {
  store.ignoreClockProblem();
  clockProblem = "";
  back();
}

function openDatetime(returnScreen = null, entryField = null) {
  dtEntryField = entryField;
  let shown = store.now();
  if (entryField) {
    const e = store.entry(entryId);
    shown = entryField === "start" ? e.start : (e.end ?? e.start);
  }
  const d = new Date(shown * 1000);
  dt = { initial: [d.getFullYear(), d.getMonth() + 1, d.getDate(), d.getHours(), d.getMinutes()], focus: 0, editing: false, error: "" };
  dt.fields = [...dt.initial];
  returnTo = returnScreen;
  screen = "datetime";
}

function dtAdjust(field, delta) {
  let [year, month, day, hour, minute] = dt.fields;
  if (field === 0) year = Math.max(2020, Math.min(2099, year + delta));
  else if (field === 1) month = ((month - 1 + delta) % 12 + 12) % 12 + 1;
  else if (field === 2) { const n = daysIn(year, month); day = ((day - 1 + delta) % n + n) % n + 1; }
  else if (field === 3) hour = ((hour + delta) % 24 + 24) % 24;
  else minute = ((minute + delta) % 60 + 60) % 60;
  day = Math.min(day, daysIn(year, month)); // 31 Jan -> Feb becomes 28/29
  dt.fields = [year, month, day, hour, minute];
  dt.error = "";
}

function dtPress() {
  if (dt.focus < DT_CANCEL) { dt.editing = !dt.editing; renderNav(); }
  else if (dt.focus === DT_CANCEL) back();
  else dtSave();
}

function dtSave() { // a running timer keeps its elapsed time
  if (dt.fields.every((v, i) => v === dt.initial[i])) { back(); return; }
  const [y, mo, d, h, mi] = dt.fields;
  const newTs = Math.floor(new Date(y, mo - 1, d, h, mi).getTime() / 1000);
  if (dtEntryField) { // editing an entry's start or end, not the clock
    try {
      store.updateEntry(entryId, { [dtEntryField]: newTs });
    } catch (err) {
      if (!(err instanceof EntryError)) throw err;
      dt.error = err.message;
      renderNav();
      return;
    }
    back();
    return;
  }
  store.setTime(newTs);
  clockProblem = "";
  renderTimes();
  back();
}

function renderDt() {
  document.getElementById("dt-title").textContent = { start: "Entry start", end: "Entry end" }[dtEntryField] ?? "Date & time";
  const hint = document.getElementById("dt-hint");
  hint.textContent = dt.error || "Turn to move, press to change a field, then Save.";
  hint.classList.toggle("error", dt.error !== "");
  const cols = document.getElementById("dt-cols");
  cols.replaceChildren();
  const key = (label, onClick) => {
    const k = document.createElement("div");
    k.className = "key";
    k.textContent = label;
    k.addEventListener("click", onClick);
    return k;
  };
  DT_LABELS.forEach((label, i) => {
    const col = document.createElement("div");
    col.className = "dtcol";
    const name = document.createElement("div");
    name.className = "dtlabel";
    name.textContent = label;
    const val = document.createElement("div");
    val.className = `dtval ${dt.focus === i ? "focus" : ""} ${dt.focus === i && dt.editing ? "editing" : ""}`;
    val.textContent = i === 0 ? String(dt.fields[i]) : String(dt.fields[i]).padStart(2, "0");
    val.addEventListener("click", () => { dt.editing = dt.focus === i ? !dt.editing : true; dt.focus = i; renderNav(); });
    col.append(name, key("+", () => { dtAdjust(i, 1); dt.focus = i; renderNav(); }), val,
      key("\u2212", () => { dtAdjust(i, -1); dt.focus = i; renderNav(); }));
    cols.appendChild(col);
  });
  document.getElementById("dt-cancel").classList.toggle("focus", dt.focus === DT_CANCEL);
  document.getElementById("dt-save").classList.toggle("focus", dt.focus === DT_SAVE);
}

/** Remember the latest time the clock showed; a big step back while running opens the warning. */
function heartbeat(now) {
  if (now + 120 < store.lastSeen()) {
    if (screen !== "clockwarn" && screen !== "datetime" && !note) runClockCheck();
    return;
  }
  if (screen !== "clockwarn" && now > store.lastSeen() && now - lastBeat >= 60) {
    lastBeat = now;
    store.heartbeat(now);
  }
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

function openAdd() {
  note = { kind: "add", project: null, text: "", focus: NOTE_SKIP, shift: true, armed: false };
  document.getElementById("note-title").textContent = "New project";
  document.getElementById("note-sub").textContent = "";
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
  if (note.kind === "entrynote") {
    const text = note.text;
    noteClose();
    try {
      store.updateEntry(entryId, { note: text });
    } catch (err) {
      if (!(err instanceof EntryError)) throw err;
      entryError = err.message;
    }
    listRows = rowsFor("entryedit");
    renderNav();
    return;
  }
  if (note.kind === "add") {
    const name = note.text.trim();
    noteClose();
    if (name) {
      const last = store.projects().at(-1);
      store.addProject(name, last ? nextColor(last.color) : COLOR_CYCLE[0]);
      refreshProjects();
      selectStyle(tiles.length - 1, PART_COLOR); // the new card
    }
    renderNav();
    return;
  }
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
  noteText.textContent = note.text === "" ? (note.kind === "entrynote" ? "Note…" : (note.kind !== "note" ? "Name…" : "Optional note…")) : note.text + "▏";
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
  last.appendChild(key(note.kind !== "note" ? "Cancel" : "Skip", `wide-b ${note.focus === NOTE_SKIP ? "focus" : ""}`, noteSkip));
  last.appendChild(key("Save", `wide-b accent ${note.focus === NOTE_SAVE ? "focus" : ""}`, noteSave));
  keys.appendChild(last);
}

// -- input --------------------------------------------------------------------

btnSettings.addEventListener("click", () => tap(SETTINGS));
btnStyle.addEventListener("click", () => tap(STYLE));
btnArchived.addEventListener("click", () => tap(1));
addTile.addEventListener("click", () => { if (screen === "style") tap(STYLE_COLUMN + STYLE_PARTS * tiles.length); });
btnReports.addEventListener("click", () => tap(REPORTS));
btnBack.addEventListener("click", () => tap(0));
document.getElementById("dt-cancel").addEventListener("click", back);
document.getElementById("dt-save").addEventListener("click", dtSave);

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
buildTiles();
renderTiles();
renderTimes();
renderNav();
let lastSecond = store.now();
runClockCheck();
setInterval(() => {
  const s = store.now();
  if (s !== lastSecond) {
    lastSecond = s;
    renderTimes();
    heartbeat(s);
    if (screen === "reports") { repRefresh(); renderNav(); } // a running timer keeps today's numbers moving
  }
}, 200);
