// Selection and scrolling logic of the strip. Mirrors src/timetracker/nav.py; keep the two in sync.
//
// Main screen items, left to right: Settings, Style, Reports, project 1, project 2, ...
// The screen is split into equal slots: slot 0 is the column, slot k is project k.
// Five slots are visible; `offset` is the first visible slot.
//
// The Style screen uses the same strip with other items: one column item (Back) and
// four items per card (colour, name, time, More) and a trailing "+" item after the last card.
// See `new StripNav(count, 2, 4, 1)`. A trailing item takes a slot of its own; its "card" index is
// projectCount + k, part 0.

export const SETTINGS = 0;
export const STYLE = 1;
export const REPORTS = 2;
export const FIRST_PROJECT = 3;
export const VISIBLE_SLOTS = 5;
export const SCROLL_AT = 3; // selecting the 4th visible slot starts scrolling

export class StripNav {
  constructor(projectCount = 0, columnItems = FIRST_PROJECT, parts = 1, trailing = 0) {
    this.projectCount = projectCount;
    this.columnItems = columnItems;
    this.parts = parts;
    this.trailing = trailing;
    this.selected = this.#default();
    this.offset = 0; // first visible slot; 0 shows the column
  }

  /** Index of the first card item. */
  get first() {
    return this.columnItems;
  }

  #default() {
    return this.projectCount || this.trailing ? this.first : 0;
  }

  get last() {
    if (this.projectCount || this.trailing) return this.first + this.projectCount * this.parts + this.trailing - 1;
    return this.columnItems - 1;
  }

  /** [card, part] of the selection, or [-1, -1] while a column item is selected. */
  cardAndPart() {
    if (this.selected < this.first) return [-1, -1];
    const i = this.selected - this.first;
    if (i >= this.projectCount * this.parts) return [this.projectCount + (i - this.projectCount * this.parts), 0]; // trailing
    return [Math.floor(i / this.parts), i % this.parts];
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
    this.selected = Math.max(0, Math.min(this.last, index));
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
    this.selected = Math.max(0, Math.min(this.last, this.selected));
    this.#follow();
  }

  #follow() {
    const slot = this.cardAndPart()[0] + 1; // slot 0 is the column
    let offset = this.offset;
    if (slot < offset) offset = slot;
    else if (slot - offset >= SCROLL_AT) offset = slot - SCROLL_AT + 1;
    const lastOffset = Math.max(0, this.projectCount + this.trailing + 1 - VISIBLE_SLOTS);
    this.offset = Math.max(0, Math.min(offset, lastOffset));
  }
}

/**
 * Selection in a vertical list of rows (Settings, ...): a window of `visible` rows follows the
 * selection. Row 0 is normally Back, so turning left from the first real row reaches it.
 */
export class ListNav {
  constructor(count = 0, visible = 6, defaultRow = null) {
    this.count = count;
    this.visible = visible;
    this.defaultRow = defaultRow;
    this.selected = this.#default();
    this.offset = 0; // first visible row
  }

  #default() {
    if (this.defaultRow !== null) return Math.min(this.defaultRow, Math.max(0, this.count - 1));
    return this.count > 1 ? 1 : 0; // the first real row, not Back
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
    this.selected = this.count ? Math.max(0, Math.min(this.count - 1, index)) : 0;
    this.#follow();
    return this.selected !== before[0] || this.offset !== before[1];
  }

  setCount(count) {
    this.count = count;
    this.select(this.selected);
  }

  #follow() {
    if (this.selected < this.offset) this.offset = this.selected;
    else if (this.selected >= this.offset + this.visible) this.offset = this.selected - this.visible + 1;
    this.offset = Math.max(0, Math.min(this.offset, Math.max(0, this.count - this.visible)));
  }
}
