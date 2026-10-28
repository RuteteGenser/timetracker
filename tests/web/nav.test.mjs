import test from "node:test";
import assert from "node:assert/strict";
import { StripNav, ListNav, FIRST_PROJECT, SETTINGS, STYLE, REPORTS } from "../../docs/nav.js";
import { Store, dayBounds } from "../../docs/store.js";

const memory = () => {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
};

test("default view selects the first project", () => {
  const n = new StripNav(7);
  assert.deepEqual([n.selected, n.offset], [FIRST_PROJECT, 0]);
});

test("scrolling starts when the 4th item (Learning) is selected", () => {
  const n = new StripNav(7);
  n.move(1); // Admin, 3rd item
  assert.deepEqual([n.selected - FIRST_PROJECT, n.offset], [1, 0]);
  n.move(1); // Learning, 4th item
  assert.deepEqual([n.selected - FIRST_PROJECT, n.offset], [2, 1]);
});

test("clockwise keeps scrolling one card per step until the end", () => {
  const n = new StripNav(7);
  const seen = [];
  for (let i = 0; i < 6; i++) { n.move(1); seen.push([n.selected - FIRST_PROJECT, n.offset]); }
  assert.deepEqual(seen, [[1, 0], [2, 1], [3, 2], [4, 3], [5, 3], [6, 3]]);
});

test("counter-clockwise reaches Reports, Style then Settings, no wrap", () => {
  const n = new StripNav(7);
  n.move(-1); assert.equal(n.selected, REPORTS);
  n.move(-1); assert.equal(n.selected, STYLE);
  n.move(-1); assert.equal(n.selected, SETTINGS);
  n.move(-1); assert.equal(n.selected, SETTINGS);
});

test("scrolling back brings the column back", () => {
  const n = new StripNav(7);
  for (let i = 0; i < 6; i++) n.move(1);
  while (n.selected > SETTINGS) n.move(-1);
  assert.equal(n.offset, 0);
});

test("the selection is always visible", () => {
  for (let count = 0; count < 12; count++) {
    const n = new StripNav(count);
    const steps = [...Array(count + 3).fill(1), ...Array(count + 4).fill(-1)];
    for (const step of steps) {
      n.move(step);
      const slot = n.selected < FIRST_PROJECT ? 0 : n.selected - FIRST_PROJECT + 1;
      assert.ok(n.offset <= slot && slot < n.offset + 5);
    }
  }
});

test("four projects fit without scrolling", () => {
  const n = new StripNav(4);
  for (let i = 0; i < 5; i++) n.move(1);
  assert.deepEqual([n.selected, n.offset], [FIRST_PROJECT + 3, 0]);
});

test("store: start, switch, stop, persist", () => {
  let t = 1_700_000_000;
  const storage = memory();
  const s = new Store(storage, () => t);
  const [a, b] = s.projects();
  s.start(a.id);
  t += 60;
  s.start(b.id);                       // stops a
  assert.equal(s.running().projectId, b.id);
  assert.equal(s.data.entries[0].end, s.data.entries[0].start + 60);
  t += 30;
  const reopened = new Store(storage, () => t);   // like reloading the page
  assert.equal(reopened.running().projectId, b.id);
  assert.equal(t - reopened.running().start, 30);
  s.stop();
  assert.equal(s.running(), null);
});

test("store: totals clip to the window and include the running entry", () => {
  let t = 1_700_000_000;
  const s = new Store(memory(), () => t);
  const [a] = s.projects();
  const t0 = t;
  s.start(a.id);
  t += 1000;
  s.stop();
  assert.deepEqual(s.totals(t0 + 300, t0 + 700), { [a.id]: 400 });
  s.start(a.id);
  t += 250;
  assert.equal(s.totals(t0, t0 + 10_000)[a.id], 1250);
});

test("store: clock set back never makes a negative entry", () => {
  let t = 1_700_000_000;
  const s = new Store(memory(), () => t);
  s.start(s.projects()[0].id);
  t -= 3600;
  s.stop();
  const e = s.data.entries[0];
  assert.equal(e.end, e.start);
});

test("dayBounds spans the local day", () => {
  const ts = new Date(2026, 2, 14, 15, 9, 26).getTime() / 1000;
  const [start, end] = dayBounds(ts);
  assert.ok(start <= ts && ts < end);
  assert.equal(new Date(start * 1000).getHours(), 0);
});

test("store: stop returns the finished entry and notes can be saved", () => {
  let t = 1_700_000_000;
  const s = new Store(memory(), () => t);
  s.start(s.projects()[0].id);
  t += 90;
  const done = s.stop();
  assert.equal(done.end - done.start, 90);
  assert.equal(s.stop(), null);
  s.setNote(done.id, "  wrote tests  ");
  assert.equal(s.data.entries[0].note, "wrote tests");
});

test("store: deleting an entry removes its time", () => {
  let t = 1_700_000_000;
  const s = new Store(memory(), () => t);
  const [a] = s.projects();
  const t0 = t;
  s.start(a.id);
  t += 60;
  const done = s.stop();
  assert.deepEqual(s.totals(t0 - 1, t0 + 1000), { [a.id]: 60 });
  s.deleteEntry(done.id);
  assert.deepEqual(s.totals(t0 - 1, t0 + 1000), {});
  assert.equal(s.data.entries.length, 0);
});

// -- Style screen ---------------------------------------------------------------------------

import { COLOR_CYCLE, nextColor } from "../../docs/store.js";

const styleNav = (n = 7) => new StripNav(n, 1, 3);

test("style: default is the first card's colour part", () => {
  const n = styleNav();
  assert.equal(n.selected, 1);
  assert.deepEqual(n.cardAndPart(), [0, 0]);
});

test("style: the knob visits colour, name, time, then the next card", () => {
  const n = styleNav();
  const seen = [];
  for (let i = 0; i < 5; i++) { seen.push(n.cardAndPart()); n.move(1); }
  assert.deepEqual(seen, [[0, 0], [0, 1], [0, 2], [1, 0], [1, 1]]);
});

test("style: counter-clockwise from the first part reaches Back", () => {
  const n = styleNav();
  n.move(-1);
  assert.deepEqual([n.selected, ...n.cardAndPart()], [0, -1, -1]);
  n.move(-1);
  assert.equal(n.selected, 0);
});

test("style: scrolling starts when the fourth card is reached", () => {
  let n = styleNav();
  for (let i = 0; i < 3 * 2 + 2; i++) n.move(1);
  assert.deepEqual([n.cardAndPart(), n.offset], [[2, 2], 1]);
  n = styleNav();
  for (let i = 0; i < 3 * 1 + 2; i++) n.move(1);
  assert.deepEqual([n.cardAndPart(), n.offset], [[1, 2], 0]);
});

test("style: every part stays visible", () => {
  for (let count = 0; count < 10; count++) {
    const n = styleNav(count);
    const steps = [...Array(3 * count + 3).fill(1), ...Array(3 * count + 4).fill(-1)];
    for (const step of steps) {
      n.move(step);
      const slot = n.cardAndPart()[0] + 1;
      assert.ok(n.offset <= slot && slot < n.offset + 5);
    }
  }
});

test("colour cycle has eight colours, steps through all of them and wraps", () => {
  assert.equal(COLOR_CYCLE.length, 8);
  assert.equal(new Set(COLOR_CYCLE).size, 8);
  let c = COLOR_CYCLE[0];
  const seen = [c];
  for (let i = 0; i < 8; i++) { c = nextColor(c); seen.push(c); }
  assert.deepEqual(seen.slice(0, 8), COLOR_CYCLE);
  assert.equal(seen[8], COLOR_CYCLE[0]);
  assert.equal(nextColor("#123456"), COLOR_CYCLE[0]);
  assert.equal(nextColor(COLOR_CYCLE[1].toUpperCase()), COLOR_CYCLE[2]);
});

test("store: rename and colour persist", () => {
  const storage = memory();
  const s = new Store(storage, () => 1_700_000_000);
  const [a] = s.projects();
  s.renameProject(a.id, "  Deep work ");
  s.setProjectColor(a.id, "#cc4a93");
  const again = new Store(storage, () => 1_700_000_000);
  assert.equal(again.projects()[0].name, "Deep work");
  assert.equal(again.projects()[0].color, "#cc4a93");
  s.renameProject(a.id, "   ");                      // an empty name is ignored
  assert.equal(s.projects()[0].name, "Deep work");
});

const DAY = 86_400;

function resetSetup(startOffset = 3600) {
  const t0 = new Date(2026, 5, 10, 0, 0, 0).getTime() / 1000;   // local midnight
  const state = { t: t0 + startOffset };
  const s = new Store(memory(), () => state.t);
  const [a, b] = s.projects();
  const [dayStart, dayEnd] = dayBounds(state.t);
  return { s, a, b, state, dayStart, dayEnd };
}

test("resetToday removes today's entries for that project only", () => {
  const { s, a, b, state, dayStart, dayEnd } = resetSetup();
  s.start(a.id); state.t += 600;
  s.start(b.id); state.t += 300;
  s.stop();
  s.resetToday(a.id);
  assert.deepEqual(s.totals(dayStart, dayEnd), { [b.id]: 300 });
});

test("resetToday keeps other days", () => {
  const { s, a, state, dayStart, dayEnd } = resetSetup(100);
  state.t = dayStart - 7200;
  s.start(a.id); state.t += 1000; s.stop();
  state.t = dayStart + 100;
  s.start(a.id); state.t += 500; s.stop();
  s.resetToday(a.id);
  assert.deepEqual(s.totals(dayStart, dayEnd), {});
  assert.deepEqual(s.totals(dayStart - DAY, dayStart), { [a.id]: 1000 });
});

test("resetToday cuts an entry that runs in from yesterday at midnight", () => {
  const { s, a, state, dayStart, dayEnd } = resetSetup();
  state.t = dayStart - 600;
  s.start(a.id); state.t += 1200; s.stop();
  assert.deepEqual(s.totals(dayStart, dayEnd), { [a.id]: 600 });
  s.resetToday(a.id);
  assert.deepEqual(s.totals(dayStart, dayEnd), {});
  assert.deepEqual(s.totals(dayStart - DAY, dayStart), { [a.id]: 600 });
});

test("resetToday restarts a running timer from now", () => {
  const { s, a, state, dayStart, dayEnd } = resetSetup(1000);
  s.start(a.id); state.t += 500;
  s.resetToday(a.id);
  assert.equal(s.running().start, state.t);
  assert.equal(s.totals(dayStart, dayEnd)[a.id] ?? 0, 0);
});

test("resetToday on a timer started yesterday keeps yesterday's part", () => {
  const { s, a, state, dayStart, dayEnd } = resetSetup();
  state.t = dayStart - 900;
  s.start(a.id);
  state.t = dayStart + 600;
  s.resetToday(a.id);
  assert.deepEqual(s.totals(dayStart - DAY, dayStart), { [a.id]: 900 });
  assert.equal(s.running().start, state.t);
  assert.equal(s.totals(dayStart, dayEnd)[a.id] ?? 0, 0);
});


// -- list screens --------------------------------------------------------------------------

test("list: default is the first real row, not Back", () => {
  assert.equal(new ListNav(4).selected, 1);
  assert.equal(new ListNav(1).selected, 0);
  assert.equal(new ListNav(0).selected, 0);
});

test("list: turning left reaches Back and stops there", () => {
  const n = new ListNav(4);
  n.move(-1); assert.equal(n.selected, 0);
  n.move(-1); assert.equal(n.selected, 0);
});

test("list: stops at the last row", () => {
  const n = new ListNav(4);
  for (let i = 0; i < 10; i++) n.move(1);
  assert.equal(n.selected, 3);
});

test("list: the window follows the selection and the selection stays visible", () => {
  for (let count = 1; count < 15; count++) {
    const n = new ListNav(count, 4);
    for (const step of [...Array(count + 2).fill(1), ...Array(count + 2).fill(-1)]) {
      n.move(step);
      assert.ok(n.offset <= n.selected && n.selected < n.offset + 4);
    }
  }
  const n = new ListNav(12, 5);
  for (let i = 0; i < 11; i++) n.move(1);
  assert.deepEqual([n.selected, n.offset], [11, 7]);
});

test("list: setCount clamps", () => {
  const n = new ListNav(10, 4);
  for (let i = 0; i < 9; i++) n.move(1);
  n.setCount(3);
  assert.deepEqual([n.selected, n.offset], [2, 0]);
});

// -- clock: setting it and the sanity check ----------------------------------------------------

import { MIN_PLAUSIBLE } from "../../docs/store.js";

const T0 = 1_800_000_000; // after 2026, so it looks sane

test("setTime moves the clock, keeps a running timer's elapsed time and resets the heartbeat", () => {
  const state = { t: T0 };
  const s = new Store(memory(), () => state.t);
  s.start(s.projects()[0].id);
  state.t += 300;
  const elapsed = s.now() - s.running().start;
  const delta = s.setTime(s.now() + 5 * 3600);
  assert.equal(delta, 5 * 3600);
  assert.equal(s.now() - s.running().start, elapsed);
  assert.equal(s.lastSeen(), s.now());
});

test("setTime backwards keeps elapsed time too, and finished entries are untouched", () => {
  const state = { t: T0 };
  const s = new Store(memory(), () => state.t);
  const [a, b] = s.projects();
  s.start(a.id); state.t += 60; const done = s.stop();
  const start = done.start, end = done.end;
  s.start(b.id); state.t += 90;
  s.setTime(s.now() - 3 * 86400);
  assert.equal(s.now() - s.running().start, 90);
  assert.deepEqual([done.start, done.end], [start, end]);
});

test("the clock offset persists across a reload", () => {
  const state = { t: T0 };
  const storage = memory();
  const s = new Store(storage, () => state.t);
  s.setTime(s.now() + 86400);
  const again = new Store(storage, () => state.t);
  assert.equal(again.now(), s.now());
});

test("a fresh store with a sane clock has no clock problem", () => {
  assert.equal(new Store(memory(), () => T0).clockProblem(), "");
});

test("a date before the software existed is flagged", () => {
  assert.match(new Store(memory(), () => MIN_PLAUSIBLE - 86400).clockProblem(), /too early/);
});

test("a clock behind the last seen time is flagged, small differences are not", () => {
  const state = { t: T0 };
  const s = new Store(memory(), () => state.t);
  s.heartbeat(T0 + 5 * 3600);
  assert.match(s.clockProblem(), /5 h 00 min behind/);
  state.t = T0 + 5 * 3600 - 60;
  assert.equal(s.clockProblem(), "");
});

test("a clock behind the newest entry is flagged even without a heartbeat", () => {
  const state = { t: T0 };
  const s = new Store(memory(), () => state.t);
  s.start(s.projects()[0].id); state.t += 1000; s.stop();
  state.t -= 86400;
  assert.match(s.clockProblem(), /behind/);
});

test("ignoring a warning silences it until the reference moves on", () => {
  const state = { t: T0 };
  const s = new Store(memory(), () => state.t);
  s.heartbeat(T0 + 3600);
  assert.notEqual(s.clockProblem(), "");
  s.ignoreClockProblem();
  assert.equal(s.clockProblem(), "");
  s.heartbeat(s.now() + 7200);
  assert.notEqual(s.clockProblem(), "");
});

test("the heartbeat only moves forward", () => {
  const s = new Store(memory(), () => T0);
  s.heartbeat(T0 + 100);
  s.heartbeat(T0 + 50);
  assert.equal(s.lastSeen(), T0 + 100);
});

test("latestTimestamp", () => {
  const state = { t: T0 };
  const s = new Store(memory(), () => state.t);
  assert.equal(s.latestTimestamp(), 0);
  const e = s.start(s.projects()[0].id);
  assert.equal(s.latestTimestamp(), e.start);
  state.t += 50; s.stop();
  assert.equal(s.latestTimestamp(), e.start + 50);
});

test("list: a default row can be chosen", () => {
  assert.equal(new ListNav(2, 6, 0).selected, 0);
  assert.equal(new ListNav(5, 6, 3).selected, 3);
  assert.equal(new ListNav(2, 6, 9).selected, 1);
});
