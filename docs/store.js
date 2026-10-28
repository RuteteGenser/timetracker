// Browser-side storage. Every change is written to localStorage immediately,
// and a running timer is just an entry with a start time and no end time.

const KEY = "timetracker.v1";

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
    return Math.floor(this.clock());
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
