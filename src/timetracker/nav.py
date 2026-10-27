"""Selection and scrolling logic of the main strip (no Qt, easy to test).

Linear item order, left to right: Settings, Style, project 1, project 2, ...
Settings and Style are stacked in one column on screen; the knob steps through
them as two separate items.
"""

SETTINGS = 0
STYLE = 1
FIRST_PROJECT = 2
VISIBLE_TILES = 4


class StripNav:
    def __init__(self, project_count: int = 0):
        self.project_count = project_count
        self.selected = self._default()
        self.offset = 0  # index of the leftmost visible project; 0 also shows the column

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
        """Slide the view only when the selection would leave the visible tiles."""
        if self.selected < FIRST_PROJECT:
            self.offset = 0
            return
        k = self.selected - FIRST_PROJECT
        if k < self.offset:
            self.offset = k
        elif k > self.offset + VISIBLE_TILES - 1:
            self.offset = k - VISIBLE_TILES + 1
        self.offset = max(0, min(self.offset, self.project_count - VISIBLE_TILES))
