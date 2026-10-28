import test from "node:test";
import assert from "node:assert/strict";
import { Store } from "../../docs/store.js";
import { periodBounds, shiftPeriod, periodLabel, summary, stepLimits } from "../../docs/summaries.js";

const ts = (...a) => new Date(...a.map((v, i) => (i === 1 ? v - 1 : v))).getTime() / 1000; // month is 1-based here
const at = (t) => new Date(t * 1000);
const memory = () => {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
};

test("day bounds span a local day", () => {
  const [s, e] = periodBounds(ts(2026, 3, 14, 15, 9), "day");
  assert.deepEqual([at(s).getDate(), at(s).getHours(), at(e).getDate(), at(e).getHours()], [14, 0, 15, 0]);
});

test("a week starts on Monday and lasts seven days", () => {
  // 2026-10-28 is a Wednesday
  let [s, e] = periodBounds(ts(2026, 10, 28, 12), "week");
  assert.equal(s, ts(2026, 10, 26));
  assert.equal(e, ts(2026, 11, 2));
  [s] = periodBounds(ts(2026, 11, 1, 23, 59), "week");      // Sunday belongs to the week before
  assert.equal(s, ts(2026, 10, 26));
  [s] = periodBounds(ts(2026, 11, 2, 0, 0), "week");        // Monday at midnight starts a new week
  assert.equal(s, ts(2026, 11, 2));
});

test("month bounds, including December and a leap February", () => {
  assert.deepEqual(periodBounds(ts(2026, 12, 31, 23), "month"), [ts(2026, 12, 1), ts(2027, 1, 1)]);
  assert.deepEqual(periodBounds(ts(2028, 2, 10), "month"), [ts(2028, 2, 1), ts(2028, 3, 1)]);
});

test("an unknown kind throws", () => {
  assert.throws(() => periodBounds(0, "year"));
});

test("periods are contiguous", () => {
  for (const kind of ["day", "week", "month"]) {
    let [, end] = periodBounds(ts(2026, 1, 1), kind);
    for (let i = 0; i < 30; i++) {
      const [nextStart, nextEnd] = periodBounds(end, kind);
      assert.equal(nextStart, end);
      end = nextEnd;
    }
  }
});

test("shiftPeriod steps by whole periods", () => {
  const t = ts(2026, 10, 28, 15);
  assert.equal(shiftPeriod(t, "day", -1), ts(2026, 10, 27));
  assert.equal(shiftPeriod(t, "week", -1), ts(2026, 10, 19));
  assert.equal(shiftPeriod(t, "month", -1), ts(2026, 9, 1));
  assert.equal(shiftPeriod(t, "month", 3), ts(2027, 1, 1));
  assert.equal(shiftPeriod(ts(2026, 1, 15), "month", -1), ts(2025, 12, 1));
});

test("labels", () => {
  const now = ts(2026, 10, 28, 12);
  assert.equal(periodLabel(now, "day", now), "Today");
  assert.equal(periodLabel(ts(2026, 10, 27), "day", now), "Yesterday");
  assert.equal(periodLabel(ts(2026, 10, 20), "day", now), "Tue 20 Oct");
  assert.equal(periodLabel(ts(2025, 12, 24), "day", now), "Wed 24 Dec 2025");
  assert.equal(periodLabel(now, "week", now), "This week · 26 Oct – 1 Nov");
  assert.equal(periodLabel(ts(2026, 10, 14), "week", now), "12 Oct – 18 Oct");
  assert.ok(periodLabel(ts(2026, 12, 30), "week", ts(2026, 12, 30)).endsWith("3 Jan 2027"));
  assert.equal(periodLabel(now, "month", now), "October 2026");
});

// -- summaries equal the raw entries -----------------------------------------------------------

function makeEntries() {
  const state = { t: ts(2026, 10, 1) };
  const s = new Store(memory(), () => state.t);
  const [a, b] = s.projects();
  const plan = [
    [a, ts(2026, 10, 26, 9), 3600],
    [b, ts(2026, 10, 27, 10), 1800],
    [a, ts(2026, 10, 28, 9), 5400],
    [a, ts(2026, 10, 31, 23, 30), 3600],      // crosses midnight into Sunday 1 Nov
    [b, ts(2026, 11, 2, 8), 600],             // the following Monday
    [a, ts(2026, 9, 30, 8), 900],             // last month
  ];
  for (const [p, start, seconds] of plan) {
    state.t = start;
    s.start(p.id);
    state.t += seconds;
    s.stop();
  }
  state.t = ts(2026, 11, 2, 12);
  return { s, a, b, state };
}

const bySeconds = (r) => Object.fromEntries(r.rows.map((x) => [x.projectId, x.seconds]));

test("day summary matches the entries", () => {
  const { s, a, b, state } = makeEntries();
  const r = summary(s, "day", ts(2026, 10, 28, 12), state.t);
  assert.deepEqual([bySeconds(r)[a.id], bySeconds(r)[b.id], r.total], [5400, 0, 5400]);
});

test("week summary matches the entries, including the midnight split", () => {
  const { s, a, b, state } = makeEntries();
  const r = summary(s, "week", ts(2026, 10, 28), state.t);
  assert.deepEqual([bySeconds(r)[a.id], bySeconds(r)[b.id]], [3600 + 5400 + 3600, 1800]);
  assert.equal(r.total, 3600 + 5400 + 3600 + 1800);
});

test("the next week gets nothing of the split entry (it ended on Sunday)", () => {
  const { s, a, b, state } = makeEntries();
  const r = summary(s, "week", ts(2026, 11, 3), state.t);
  assert.deepEqual([bySeconds(r)[a.id], bySeconds(r)[b.id]], [0, 600]);
});

test("month summaries split the midnight entry between October and November", () => {
  const { s, a, b, state } = makeEntries();
  const oct = summary(s, "month", ts(2026, 10, 15), state.t);
  assert.deepEqual([bySeconds(oct)[a.id], bySeconds(oct)[b.id]], [3600 + 5400 + 1800, 1800]);
  const nov = summary(s, "month", ts(2026, 11, 15), state.t);
  assert.deepEqual([bySeconds(nov)[a.id], bySeconds(nov)[b.id]], [1800, 600]);
  const sep = summary(s, "month", ts(2026, 9, 15), state.t);
  assert.deepEqual([bySeconds(sep)[a.id], bySeconds(sep)[b.id]], [900, 0]);
});

test("the totals add up to the raw entries", () => {
  const { s, state } = makeEntries();
  const raw = s.data.entries.reduce((t, e) => t + (e.end - e.start), 0);
  const parts = [9, 10, 11].map((m) => summary(s, "month", ts(2026, m, 15), state.t).total);
  assert.equal(parts.reduce((x, y) => x + y, 0), raw);
  for (const kind of ["day", "week", "month"]) {
    const r = summary(s, kind, ts(2026, 10, 28), state.t);
    assert.equal(r.total, r.rows.reduce((t, x) => t + x.seconds, 0));
  }
});

test("a running timer counts up to now", () => {
  const state = { t: ts(2026, 10, 28, 9) };
  const s = new Store(memory(), () => state.t);
  const a = s.projects()[0];
  s.start(a.id);
  state.t += 1234;
  assert.equal(bySeconds(summary(s, "day", state.t, state.t))[a.id], 1234);
});

test("archived projects only show when they have time in the period", () => {
  const { s, b, state } = makeEntries();
  s.archiveProject(b.id);
  const wk = summary(s, "week", ts(2026, 10, 28), state.t);
  assert.deepEqual(wk.rows.slice(0, 2).map((r) => r.name), [s.data.projects[0].name, b.name]);
  assert.equal(wk.rows.find((r) => r.projectId === b.id).archived, true);
  const day = summary(s, "day", ts(2026, 10, 28), state.t);
  assert.ok(!day.rows.some((r) => r.projectId === b.id));
});

test("stepLimits: the oldest period with an entry and the current one", () => {
  const state = { t: ts(2026, 10, 28, 12) };
  const empty = new Store(memory(), () => state.t);
  const dayStart = periodBounds(state.t, "day")[0];
  assert.deepEqual(stepLimits(empty, "day", state.t), [dayStart, dayStart]);
  const { s, state: st } = makeEntries();
  const [oldest, current] = stepLimits(s, "month", st.t);
  assert.equal(oldest, ts(2026, 9, 1));
  assert.equal(current, ts(2026, 11, 1));
});

test("earliestTimestamp", () => {
  const state = { t: ts(2026, 10, 28, 12) };
  const s = new Store(memory(), () => state.t);
  assert.equal(s.earliestTimestamp(), null);
  const e = s.start(s.projects()[0].id);
  assert.equal(s.earliestTimestamp(), e.start);
});
