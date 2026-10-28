import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Store } from "../../docs/store.js";
import { APP_VERSION, statusRows } from "../../docs/status.js";

const T0 = 1_800_000_000;
const memory = () => {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
};
const facts = (s) => Object.fromEntries(statusRows(s).map((r) => [r.label, r.value]));

test("status lists the facts in order", () => {
  const s = new Store(memory(), () => T0);
  assert.deepEqual(statusRows(s).map((r) => r.label), ["Clock check", "Time now", "Last time change", "Clock offset", "Projects", "Entries", "Stored in this browser", "Version"]);
  const f = facts(s);
  assert.deepEqual([f["Clock check"], f["Last time change"], f["Clock offset"], f.Projects, f.Entries], ["OK", "never", "none", "6", "0"]);
  assert.match(f["Stored in this browser"], /^\d+\.\d KB$/);
  assert.equal(f.Version, APP_VERSION);
});

test("the version matches the Python package", () => {
  const pyproject = readFileSync(new URL("../../pyproject.toml", import.meta.url), "utf8");
  assert.equal(pyproject.match(/^version = "(.+)"$/m)[1], APP_VERSION);
});

test("a clock problem, a clock change, an offset and counts show up", () => {
  const state = { t: T0 };
  const s = new Store(memory(), () => state.t);
  s.start(s.projects()[0].id); state.t += 120; s.stop();
  s.setTime(s.now() + 2 * 3600);
  s.archiveProject(s.projects()[3].id);
  s.heartbeat(s.now() + 4 * 3600);
  const f = facts(s);
  assert.match(f["Clock check"], /behind/);
  assert.match(f["Last time change"], /→/);
  assert.equal(f["Clock offset"], "+2 h 00 min");
  assert.equal(f.Projects, "5 (1 archived)");
  assert.equal(f.Entries, "1");
});

test("a clock set back shows a minus offset", () => {
  const s = new Store(memory(), () => T0);
  s.setTime(s.now() - 90 * 60);
  assert.equal(facts(s)["Clock offset"], "-1 h 30 min");
});

test("dataSize grows with the data and is safe without storage", () => {
  const s = new Store(memory(), () => T0);
  const before = s.dataSize();
  s.start(s.projects()[0].id);
  assert.ok(s.dataSize() > before);
  const broken = new Store({ getItem() { throw new Error("blocked"); }, setItem() {} }, () => T0);
  assert.equal(broken.dataSize(), 0);
});
