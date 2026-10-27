// Selection and scrolling logic of the main strip.
// Mirrors src/timetracker/nav.py; keep the two in sync.
//
// Linear item order, left to right: Settings, Style, project 1, project 2, ...
// The screen is split into equal slots: slot 0 is the Settings/Style column, slot k is
// project k. Five slots are visible; `offset` is the first visible slot.

export const SETTINGS = 0;
export const STYLE = 1;
export const FIRST_PROJECT = 2;
export const VISIBLE_SLOTS = 5;
export const SCROLL_AT = 3; // selecting the 4th visible slot starts scrolling

export class StripNav {
  constructor(projectCount = 0) {
    this.projectCount = projectCount;
    this.selected = this.#default();
    this.offset = 0; // first visible slot; 0 shows the Settings/Style column
  }

  #default() {
    return this.projectCount ? FIRST_PROJECT : SETTINGS;
  }

  get last() {
    return this.projectCount ? FIRST_PROJECT + this.projectCount - 1 : STYLE;
  }

  reset() {
    this.selected = this.#default();
    this.offset = 0;
  }

  move(steps) {
    return this.select(this.selected + steps);
  }

  select(index) {
    const before = [this.selected, this.offset];
    this.selected = Math.max(SETTINGS, Math.min(this.last, index));
    this.#follow();
    return this.selected !== before[0] || this.offset !== before[1];
  }

  setProjectCount(count) {
    const hadProjects = this.projectCount > 0;
    this.projectCount = count;
    if (count && !hadProjects) {
      this.reset();
      return;
    }
    this.selected = Math.max(SETTINGS, Math.min(this.last, this.selected));
    this.#follow();
  }

  #follow() {
    const slot = this.selected < FIRST_PROJECT ? 0 : this.selected - FIRST_PROJECT + 1;
    let offset = this.offset;
    if (slot < offset) offset = slot;
    else if (slot - offset >= SCROLL_AT) offset = slot - SCROLL_AT + 1;
    const lastOffset = Math.max(0, this.projectCount + 1 - VISIBLE_SLOTS);
    this.offset = Math.max(0, Math.min(offset, lastOffset));
  }
}
