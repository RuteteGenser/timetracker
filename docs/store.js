// Browser-side storage. Every change is written to localStorage immediately,
// and a running timer is just an entry with a start time and no end time.

const KEY = "timetracker.v1";

/** An entry change was refused; the message says why and is shown to the user. */
export class EntryError extends Error {}
const FUTURE_TOLERANCE = 60; // seconds an entry time may be ahead of the clock

// Mirrors src/timetracker/clock.py. The browser's own clock cannot be set, so "set date and time"
// keeps an offset (`clockOffset`) that is added to it.
export const MIN_PLAUSIBLE = new Date(2026, 0, 1).getTime() / 1000; // the software was made in 2026
export const CLOCK_TOLERANCE = 120; // seconds the clock may look behind before we warn

// The Style screen steps through these on every press (dark enough for white text).
export const COLOR_CYCLE = ["#c8424e", "#d9722f", "#b8861b", "#2f9a58", "#1a948f", "#3274d1", "#9250b4", "#cc4a93"];

/** The colour after `current` in COLOR_CYCLE; an unknown colour starts the cycle. */
export function nextColor(current) {
  const i = COLOR_CYCLE.indexOf(String(current).toLowerCase());
  return i < 0 ? COLOR_CYCLE[0] : COLOR_CYCLE[(i + 1) % COLOR_CYCLE.length];
}

const STARTERS = [
  ["Work", "#3274d1"], ["Admin", "#9250b4"], ["Learning", "#1a948f"],
  ["Meetings", "#c8424e"], ["Personal", "#b8861b"], ["Other", "#2f9a58"],
];

function spanText(seconds) {
  seconds = Math.abs(Math.floor(seconds));
  if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))} min`;
  if (seconds < 2 * 86400) return `${Math.floor(seconds / 3600)} h ${String(Math.floor((seconds % 3600) / 60)).padStart(2, "0")} min`;
  return `${Math.floor(seconds / 86400)} days`;
}

export function dayBounds(ts) {
  const d = new Date(ts * 1000);
  d.setHours(0, 0, 0, 0);
  const start = d.getTime() / 1000;
  d.setDate(d.getDate() + 1);
  return [start, d.getTime() / 1000];
}

export class Store {
  constructor(storage = globalThis.localStorage, clock = () => Date.now() / 1000) {
    this.storage = storage;
    this.clock = clock;
    this.data = this.#load();
    if (!this.data.seeded) {
      STARTERS.forEach(([name, color]) => this.addProject(name, color, false));
      this.data.seeded = true;
      this.#save();
    }
  }

  now() {
    return Math.floor(this.clock() + (this.data.clockOffset ?? 0));
  }

  #load() {
    try {
      const raw = this.storage.getItem(KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) { /* storage blocked or corrupt: start fresh */ }
    return { projects: [], entries: [], nextId: 1, seeded: false };
  }

  #save() {
    try {
      this.storage.setItem(KEY, JSON.stringify(this.data));
    } catch (e) {
      this.saveFailed = true; // e.g. private mode; the app still works for this session
    }
  }

  addProject(name, color, save = true) {
    const id = this.data.nextId++;
    this.data.projects.push({ id, name, color, archived: false });
    if (save) this.#save();
    return id;
  }

  projects() {
    return this.data.projects.filter((p) => !p.archived);
  }

  archivedProjects() {
    return this.data.projects.filter((p) => p.archived);
  }

  /** Hide a project from the main screen (or bring it back). A running timer on it is stopped. */
  archiveProject(projectId, archived = true) {
    const p = this.data.projects.find((x) => x.id === projectId);
    if (!p) return;
    if (archived && this.running()?.projectId === projectId) this.#stopRunning(this.now());
    p.archived = archived;
    this.#save();
  }

  /** Delete a project together with all its entries. */
  deleteProject(projectId) {
    this.data.projects = this.data.projects.filter((p) => p.id !== projectId);
    this.data.entries = this.data.entries.filter((e) => e.projectId !== projectId);
    this.#save();
  }

  /** Swap a project's place with its visible neighbour (-1 left, +1 right). False at the ends. */
  moveProject(projectId, direction) {
    const visible = this.projects();
    const i = visible.findIndex((p) => p.id === projectId);
    const j = i + (direction > 0 ? 1 : -1);
    if (i < 0 || j < 0 || j >= visible.length) return false;
    const all = this.data.projects;
    const a = all.indexOf(visible[i]);
    const b = all.indexOf(visible[j]);
    [all[a], all[b]] = [all[b], all[a]];
    this.#save();
    return true;
  }

  running() {
    return this.data.entries.find((e) => e.end === null) ?? null;
  }

  #stopRunning(now) {
    const run = this.running();
    if (run) run.end = Math.max(now, run.start); // never end before the start
  }

  start(projectId) {
    const run = this.running();
    if (run && run.projectId === projectId) return run;
    const now = this.now();
    this.#stopRunning(now);
    const entry = { id: this.data.nextId++, projectId, start: now, end: null, note: "" };
    this.data.entries.push(entry);
    this.#save();
    return entry;
  }

  /** Stop the running timer. Returns the finished entry, or null if nothing ran. */
  stop() {
    const run = this.running();
    this.#stopRunning(this.now());
    this.#save();
    return run;
  }

  setProjectColor(projectId, color) {
    const p = this.data.projects.find((x) => x.id === projectId);
    if (p) {
      p.color = color;
      this.#save();
    }
  }

  renameProject(projectId, name) {
    const p = this.data.projects.find((x) => x.id === projectId);
    if (p && name.trim()) {
      p.name = name.trim();
      this.#save();
    }
  }

  /**
   * Zero a project's total for today. Entries inside today are deleted, ones that run in
   * from yesterday are cut at midnight, and a running timer restarts from now.
   */
  resetToday(projectId) {
    const now = this.now();
    const [dayStart, dayEnd] = dayBounds(now);
    const keep = [];
    for (const e of this.data.entries) {
      if (e.projectId !== projectId) {
        keep.push(e);
      } else if (e.end === null) {
        if (e.start >= dayStart) {
          e.start = now;
          keep.push(e);
        } else {                       // started before today: keep that part, restart now
          e.end = dayStart;
          keep.push(e, { id: this.data.nextId++, projectId, start: now, end: null, note: "" });
        }
      } else if (e.start >= dayStart && e.end <= dayEnd) {
        // finished inside today: removed
      } else {
        if (e.start < dayStart && e.end > dayStart && e.end <= dayEnd) e.end = dayStart;
        keep.push(e);
      }
    }
    this.data.entries = keep;
    this.#save();
  }

  // -- clock: setting it, and whether it can be trusted -------------------------------------

  /**
   * Set the clock to newTs. A running timer keeps its elapsed time (its start moves by the same
   * amount). Everything is saved together. Returns how far the clock moved, in seconds.
   */
  setTime(newTs) {
    const old = this.now();
    const delta = newTs - old;
    this.data.clockOffset = (this.data.clockOffset ?? 0) + delta;
    const run = this.running();
    if (run) run.start += delta;
    this.data.lastSeen = newTs;
    this.data.lastClockChange = [old, newTs];
    this.#save();
    return delta;
  }

  lastSeen() {
    return this.data.lastSeen ?? 0;
  }

  /** Remember the latest time the clock showed; it only moves forward (setTime resets it itself). */
  heartbeat(now) {
    if (now > this.lastSeen()) {
      this.data.lastSeen = now;
      this.#save();
    }
  }

  /** How many characters of data are saved in this browser (for the Status page). */
  dataSize() {
    try {
      return (this.storage.getItem(KEY) ?? "").length;
    } catch (e) {
      return 0;
    }
  }

  /** The start of the oldest entry, or null if there are no entries. */
  earliestTimestamp() {
    return this.data.entries.length ? Math.min(...this.data.entries.map((e) => e.start)) : null;
  }

  /** The newest start or end time of any entry, 0 if there are none. */
  latestTimestamp() {
    return this.data.entries.reduce((m, e) => Math.max(m, e.start, e.end ?? 0), 0);
  }

  clockReference() {
    return Math.max(this.lastSeen(), this.latestTimestamp());
  }

  /** A message when the clock looks wrong, otherwise "". */
  clockProblem() {
    const now = this.now();
    if (now < MIN_PLAUSIBLE) {
      return `The date looks too early (${new Date(now * 1000).toLocaleDateString("en", { day: "2-digit", month: "short", year: "numeric" })}). The clock probably lost its time.`;
    }
    const ref = this.clockReference();
    if (ref > (this.data.clockAck ?? 0) && now < ref - CLOCK_TOLERANCE) {
      const when = new Date(ref * 1000).toLocaleString("en", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
      return `The clock is ${spanText(ref - now)} behind the last recorded time (${when}).`;
    }
    return "";
  }

  /** The user dismissed the warning: it does not come back until the reference moves on. */
  ignoreClockProblem() {
    this.data.clockAck = this.clockReference();
    this.data.lastSeen = this.now();
    this.#save();
  }

  entry(id) {
    return this.data.entries.find((e) => e.id === id) ?? null;
  }

  /** Entries overlapping [start, end), oldest first. A running entry counts up to now. */
  entriesBetween(start, end) {
    const now = this.now();
    return this.data.entries.filter((e) => e.start < end && (e.end ?? now) > start).sort((a, b) => a.start - b.start || a.id - b.id);
  }

  /**
   * Change an entry's projectId, start, end and/or note. Time changes are checked: the end must be
   * after the start, nothing may lie in the future, the entry must not overlap another one, and a
   * running timer has no end to set. Throws EntryError (nothing is changed) when a rule is broken.
   */
  updateEntry(id, changes) {
    const e = this.entry(id);
    if (!e) throw new EntryError("This entry no longer exists.");
    const unknown = Object.keys(changes).filter((k) => !["projectId", "start", "end", "note"].includes(k));
    if (unknown.length) throw new Error(`cannot change ${unknown}`);
    const next = { projectId: e.projectId, start: e.start, end: e.end, note: e.note, ...changes };
    if ("projectId" in changes && !this.data.projects.some((p) => p.id === next.projectId)) throw new EntryError("That project no longer exists.");
    if ("end" in changes && e.end === null) throw new EntryError("A running timer has no end yet.");
    if ("start" in changes || "end" in changes) {
      if (next.end !== null && next.end <= next.start) throw new EntryError("The end must be after the start.");
      const limit = this.now() + FUTURE_TOLERANCE;
      if (next.start > limit || (next.end ?? 0) > limit) throw new EntryError("That time is in the future.");
      const clash = this.data.entries.some((o) => o.id !== id && o.start < (next.end ?? Infinity) && (o.end ?? Infinity) > next.start);
      if (clash) throw new EntryError("That overlaps another entry.");
    }
    Object.assign(e, { projectId: next.projectId, start: next.start, end: next.end, note: String(next.note).trim() });
    this.#save();
    return e;
  }

  /** Remove one entry; its time no longer counts anywhere. */
  deleteEntry(entryId) {
    this.data.entries = this.data.entries.filter((e) => e.id !== entryId);
    this.#save();
  }

  setNote(entryId, note) {
    const e = this.data.entries.find((x) => x.id === entryId);
    if (e) {
      e.note = note.trim();
      this.#save();
    }
  }

  /** Seconds per project within [start, end), clipping entries at the edges. */
  totals(start, end) {
    const now = this.now();
    const out = {};
    for (const e of this.data.entries) {
      const e2 = e.end ?? now;
      if (e.start < end && e2 > start) {
        const secs = Math.max(0, Math.min(e2, end) - Math.max(e.start, start));
        out[e.projectId] = (out[e.projectId] ?? 0) + secs;
      }
    }
    return out;
  }
}
