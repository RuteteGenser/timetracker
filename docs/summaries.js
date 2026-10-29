// Day / week / month summaries. Mirrors src/timetracker/summaries.py; keep the two in sync.
//
// A period is a calendar day, a week (Monday to Sunday) or a month, in local time. Timestamps are
// epoch seconds. The numbers come from Store.totals, so a summary always equals the raw entries
// clipped to its period.

export const KINDS = ["day", "week", "month"];

function startDate(ts, kind) {
  const d = new Date(ts * 1000);
  d.setHours(0, 0, 0, 0);
  if (kind === "week") d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); // Monday
  else if (kind === "month") d.setDate(1);
  else if (kind !== "day") throw new Error(`unknown period kind: ${kind}`);
  return d;
}

const secs = (d) => Math.floor(d.getTime() / 1000);

function advance(d, kind, steps) {
  const e = new Date(d);
  if (kind === "day") e.setDate(e.getDate() + steps);
  else if (kind === "week") e.setDate(e.getDate() + 7 * steps);
  else e.setMonth(e.getMonth() + steps); // the 1st of a month, so no day overflow
  return e;
}

/** Start (inclusive) and end (exclusive) of the period containing ts. */
export function periodBounds(ts, kind) {
  const start = startDate(ts, kind);
  return [secs(start), secs(advance(start, kind, 1))];
}

/** The start of the period `steps` periods after (or before, if negative) the one containing ts. */
export function shiftPeriod(ts, kind, steps) {
  return secs(advance(startDate(ts, kind), kind, steps));
}

const month = (d, style = "short") => d.toLocaleString("en", { month: style });

export function periodLabel(ts, kind, now) {
  const start = startDate(ts, kind);
  const current = startDate(now, kind);
  if (kind === "day") {
    if (start.getTime() === current.getTime()) return "Today";
    if (start.getTime() === advance(current, "day", -1).getTime()) return "Yesterday";
    const year = start.getFullYear() !== current.getFullYear() ? ` ${start.getFullYear()}` : "";
    return `${start.toLocaleString("en", { weekday: "short" })} ${start.getDate()} ${month(start)}${year}`;
  }
  if (kind === "week") {
    const last = advance(start, "day", 6);
    let span = `${start.getDate()} ${month(start)} – ${last.getDate()} ${month(last)}`;
    if (start.getFullYear() !== last.getFullYear() || start.getFullYear() !== current.getFullYear()) span += ` ${last.getFullYear()}`;
    return start.getTime() === current.getTime() ? `This week · ${span}` : span;
  }
  return `${month(start, "long")} ${start.getFullYear()}`;
}

/**
 * Totals per project for the period containing `anchor`. Archived projects only appear when they
 * have time in the period. `total` is the sum of the rows.
 */
export function summary(store, kind, anchor, now) {
  const [start, end] = periodBounds(anchor, kind);
  const totals = store.totals(start, end);
  const rows = store.data.projects
    .filter((p) => !p.archived || (totals[p.id] ?? 0) > 0)
    .map((p) => ({ projectId: p.id, name: p.name, color: p.color, seconds: totals[p.id] ?? 0, archived: p.archived }));
  return { kind, start, end, label: periodLabel(anchor, kind, now), total: rows.reduce((t, r) => t + r.seconds, 0), rows };
}

/**
 * Every entry of the period, grouped per project. Groups are sorted alphabetically by project name
 * (ignoring case, then by id) and only exist for projects with time in the period (archived ones
 * included). Inside a group the entries run from the earliest to the latest start. An entry's
 * `seconds` is clipped to the period, so the entries of a group add up to the group's `seconds`.
 */
export function groupedEntries(store, kind, anchor, now) {
  const [start, end] = periodBounds(anchor, kind);
  const projects = new Map(store.data.projects.map((p) => [p.id, p]));
  const groups = new Map();
  for (const e of store.entriesBetween(start, end)) {
    const stop = e.end ?? now;
    const seconds = Math.max(0, Math.min(stop, end) - Math.max(e.start, start));
    const p = projects.get(e.projectId);
    if (!groups.has(p.id)) groups.set(p.id, { projectId: p.id, name: p.name, color: p.color, archived: p.archived, seconds: 0, entries: [] });
    const g = groups.get(p.id);
    g.seconds += seconds;
    g.entries.push({ id: e.id, start: e.start, end: e.end, seconds, note: e.note });
  }
  for (const g of groups.values()) g.entries.sort((a, b) => a.start - b.start || a.id - b.id);
  return [...groups.values()].sort((a, b) => {
    const x = a.name.toLowerCase();
    const y = b.name.toLowerCase();
    return x < y ? -1 : x > y ? 1 : a.projectId - b.projectId;
  });
}

/** Start of the oldest period worth showing (the one with the first entry) and of the current one. */
export function stepLimits(store, kind, now) {
  const current = periodBounds(now, kind)[0];
  const first = store.earliestTimestamp();
  const oldest = first === null ? current : periodBounds(first, kind)[0];
  return [Math.min(oldest, current), current];
}
