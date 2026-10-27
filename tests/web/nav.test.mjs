import test from "node:test";
import assert from "node:assert/strict";
import { StripNav, FIRST_PROJECT, SETTINGS, STYLE } from "../../docs/nav.js";
import { Store, dayBounds } from "../../docs/store.js";

const memory = () => {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
};

test("default view selects the first project", () => {
  const n = new StripNav(7);
  assert.deepEqual([n.selected, n.offset], [FIRST_PROJECT, 0]);
});

test("clockwise slides only after the fourth tile", () => {
  const n = new StripNav(7);
  const seen = [];
  for (let i = 0; i < 6; i++) { n.move(1); seen.push([n.selected - FIRST_PROJECT, n.offset]); }
  assert.deepEqual(seen, [[1, 0], [2, 0], [3, 0], [4, 1], [5, 2], [6, 3]]);
});

test("counter-clockwise reaches Style then Settings, no wrap", () => {
  const n = new StripNav(7);
  n.move(-1); assert.equal(n.selected, STYLE);
  n.move(-1); assert.equal(n.selected, SETTINGS);
  n.move(-1); assert.equal(n.selected, SETTINGS);
});

test("scrolling back brings the column back", () => {
  const n = new StripNav(7);
  for (let i = 0; i < 6; i++) n.move(1);
  while (n.selected > STYLE) n.move(-1);
  assert.equal(n.offset, 0);
});

test("few projects never scroll", () => {
  const n = new StripNav(3);
  for (let i = 0; i < 5; i++) n.move(1);
  assert.deepEqual([n.selected, n.offset], [FIRST_PROJECT + 2, 0]);
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
