"""Selection and scrolling logic of the main strip (no Qt, easy to test).

Linear item order, left to right: Settings, Style, project 1, project 2, ...
Settings and Style are stacked in one column on screen; the knob steps through
them as two separate items.

The screen is split into equal slots: slot 0 is the Settings/Style column,
slot k is project k. Five slots are visible; `offset` is the first visible slot.
"""

SETTINGS = 0
STYLE = 1
FIRST_PROJECT = 2
VISIBLE_SLOTS = 5
SCROLL_AT = 3  # selecting the 4th visible slot starts scrolling (a card is always visible ahead)


class StripNav:
    def __init__(self, project_count: int = 0):
        self.project_count = project_count
        self.selected = self._default()
        self.offset = 0  # first visible slot; 0 shows the Settings/Style column

    def _default(self) -> int:
        return FIRST_PROJECT if self.project_count else SETTINGS

    @property
    def last(self) -> int:
        return FIRST_PROJECT + self.project_count - 1 if self.project_count else STYLE

    def reset(self) -> None:
        """Default view: first project selected, column visible."""
        self.selected = self._default()
        self.offset = 0

    def move(self, steps: int) -> bool:
        return self.select(self.selected + steps)

    def select(self, index: int) -> bool:
        """Select an item, clamped to the ends. Returns True if anything changed."""
        before = (self.selected, self.offset)
        self.selected = max(SETTINGS, min(self.last, index))
        self._follow()
        return (self.selected, self.offset) != before

    def set_project_count(self, count: int) -> None:
        had_projects = self.project_count > 0
        self.project_count = count
        if count and not had_projects:
            self.reset()  # first projects appeared: start on the first one
            return
        self.selected = max(SETTINGS, min(self.last, self.selected))
        self._follow()

    def _follow(self) -> None:
        """Scroll when the selection reaches the 4th visible slot, or leaves on the left."""
        slot = 0 if self.selected < FIRST_PROJECT else self.selected - FIRST_PROJECT + 1
        offset = self.offset
        if slot < offset:
            offset = slot
        elif slot - offset >= SCROLL_AT:
            offset = slot - SCROLL_AT + 1
        last_offset = max(0, self.project_count + 1 - VISIBLE_SLOTS)
        self.offset = max(0, min(offset, last_offset))
