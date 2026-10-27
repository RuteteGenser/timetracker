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
  el.innerHTML = '<div class="band"></div><div class="name"></div><div class="timer"></div><div class="today"></div>';
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
const hm = (s) => `${Math.floor(s / 3600)}h ${pad(Math.floor(s / 60) % 60)}m`;

function renderTimes() {
  const now = store.now();
  const [start, end] = dayBounds(now);
  const totals = store.totals(start, end);
  const run = store.running();
  for (const t of tiles) {
    const running = run?.projectId === t.project.id;
    t.el.classList.toggle("running", running);
    t.timer.textContent = running ? clock(Math.max(0, now - run.start)) : "";
    t.today.textContent = `Today  ${hm(totals[t.project.id] ?? 0)}`;
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
  if (screen !== "main") return;
  nav.move(steps);
  renderNav();
}

function activate(index) {
  if (index === SETTINGS) screen = "settings";
  else if (index === STYLE) screen = "style";
  else {
    const p = tiles[index - FIRST_PROJECT]?.project;
    if (p) store.running()?.projectId === p.id ? store.stop() : store.start(p.id);
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
  if (screen !== "main") back();
  else activate(nav.selected);
}

function tap(index) {
  if (screen !== "main") return;
  nav.select(index);
  activate(index);
}

// -- input --------------------------------------------------------------------

btnSettings.addEventListener("click", () => tap(SETTINGS));
btnStyle.addEventListener("click", () => tap(STYLE));
document.getElementById("overlay-back").addEventListener("click", back);

window.addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") turn(1);
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
