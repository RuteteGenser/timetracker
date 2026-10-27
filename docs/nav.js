// Selection and scrolling logic of the main strip.
// Mirrors src/timetracker/nav.py; keep the two in sync.
//
// Linear item order, left to right: Settings, Style, project 1, project 2, ...

export const SETTINGS = 0;
export const STYLE = 1;
export const FIRST_PROJECT = 2;
export const VISIBLE_TILES = 4;

export class StripNav {
  constructor(projectCount = 0) {
    this.projectCount = projectCount;
    this.selected = this.#default();
    this.offset = 0; // index of the leftmost visible project; 0 also shows the column
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
    if (this.selected < FIRST_PROJECT) {
      this.offset = 0;
      return;
    }
    const k = this.selected - FIRST_PROJECT;
    if (k < this.offset) this.offset = k;
    else if (k > this.offset + VISIBLE_TILES - 1) this.offset = k - VISIBLE_TILES + 1;
    this.offset = Math.max(0, Math.min(this.offset, this.projectCount - VISIBLE_TILES));
  }
}
