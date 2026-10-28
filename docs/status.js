// Facts for the Status page (Settings > Status). Mirrors Controller._status_rows in
// src/timetracker/controller.py. The browser has no hardware clock or disk to report, so it shows
// its clock offset and how much data is stored instead.

export const APP_VERSION = "0.1.0"; // keep in step with pyproject.toml

const pad = (n) => String(n).padStart(2, "0");
const month = (d) => d.toLocaleString("en", { month: "short" });
const stamp = (ts, withYear = false) => {
  const d = new Date(ts * 1000);
  return `${pad(d.getDate())} ${month(d)}${withYear ? ` ${d.getFullYear()}` : ""}${withYear ? "  " : " "}${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

function offsetText(seconds) {
  if (!seconds) return "none";
  const s = Math.abs(Math.round(seconds));
  const body = s < 3600 ? `${Math.floor(s / 60)} min` : s < 2 * 86400 ? `${Math.floor(s / 3600)} h ${pad(Math.floor((s % 3600) / 60))} min` : `${Math.floor(s / 86400)} days`;
  return `${seconds < 0 ? "-" : "+"}${body}`;
}

/** [{ label, value }, ...] */
export function statusRows(store) {
  const projects = store.data.projects;
  const archived = projects.filter((p) => p.archived).length;
  const change = store.data.lastClockChange;
  const kb = store.dataSize() / 1024;
  return [
    { label: "Clock check", value: store.clockProblem() || "OK" },
    { label: "Time now", value: stamp(store.now(), true) },
    { label: "Last time change", value: change ? `${stamp(change[0])} → ${stamp(change[1])}` : "never" },
    { label: "Clock offset", value: offsetText(store.data.clockOffset ?? 0) },
    { label: "Projects", value: `${projects.length - archived}${archived ? ` (${archived} archived)` : ""}` },
    { label: "Entries", value: String(store.data.entries.length) },
    { label: "Stored in this browser", value: `${kb.toFixed(1)} KB` },
    { label: "Version", value: APP_VERSION },
  ];
}
