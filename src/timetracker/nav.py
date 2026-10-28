"""Selection and scrolling logic of the main strip (no Qt, easy to test).

Linear item order, left to right: Settings, Style, Reports, project 1, project 2, ...
Settings, Style and Reports are stacked in one column on screen; the knob steps
through them as three separate items. The Style screen uses the same strip with different
items (see StripNav).

The screen is split into equal slots: slot 0 is the Settings/Style column,
slot k is project k. Five slots are visible; `offset` is the first visible slot.
"""

SETTINGS = 0
STYLE = 1
REPORTS = 2
FIRST_PROJECT = 3
VISIBLE_SLOTS = 5
SCROLL_AT = 3  # selecting the 4th visible slot starts scrolling (a card is always visible ahead)


class StripNav:
    """Selection over [column items..., then `parts` items per project card].

    Main screen: three column items (Settings, Style, Reports), one item per card.
    Style screen: two column items (Back, Archived), four items per card (colour, name, time,
    More) and one trailing item after the last card (the "+" card that adds a project).
    A trailing item takes a slot of its own; its "card" index is project_count + k, part 0.
    """

    def __init__(self, project_count: int = 0, column_items: int = FIRST_PROJECT, parts: int = 1, trailing: int = 0):
        self.project_count = project_count
        self.column_items = column_items
        self.parts = parts
        self.trailing = trailing
        self.selected = self._default()
        self.offset = 0  # first visible slot; 0 shows the column

    @property
    def first(self) -> int:
        """Index of the first card item."""
        return self.column_items

    def _default(self) -> int:
        return self.first if (self.project_count or self.trailing) else 0

    @property
    def last(self) -> int:
        if self.project_count or self.trailing:
            return self.first + self.project_count * self.parts + self.trailing - 1
        return self.column_items - 1

    def card_and_part(self) -> tuple[int, int]:
        """(card index, part) of the selection, or (-1, -1) while a column item is selected."""
        if self.selected < self.first:
            return -1, -1
        i = self.selected - self.first
        if i >= self.project_count * self.parts:  # a trailing item
            return self.project_count + (i - self.project_count * self.parts), 0
        return divmod(i, self.parts)

    def reset(self) -> None:
        """Default view: first card selected, column visible."""
        self.selected = self._default()
        self.offset = 0

    def move(self, steps: int) -> bool:
        return self.select(self.selected + steps)

    def select(self, index: int) -> bool:
        """Select an item, clamped to the ends. Returns True if anything changed."""
        before = (self.selected, self.offset)
        self.selected = max(0, min(self.last, index))
        self._follow()
        return (self.selected, self.offset) != before

    def set_project_count(self, count: int) -> None:
        had_projects = self.project_count > 0
        self.project_count = count
        if count and not had_projects:
            self.reset()  # first projects appeared: start on the first one
            return
        self.selected = max(0, min(self.last, self.selected))
        self._follow()

    def _follow(self) -> None:
        """Scroll when the selection reaches the 4th visible slot, or leaves on the left."""
        card, _ = self.card_and_part()
        slot = card + 1  # slot 0 is the column
        offset = self.offset
        if slot < offset:
            offset = slot
        elif slot - offset >= SCROLL_AT:
            offset = slot - SCROLL_AT + 1
        last_offset = max(0, self.project_count + self.trailing + 1 - VISIBLE_SLOTS)
        self.offset = max(0, min(offset, last_offset))


class ListNav:
    """Selection in a vertical list of rows (Settings, Reports, ...): a window of `visible`
    rows follows the selection. Row 0 is normally Back, so turning counter-clockwise from the
    first real row reaches it."""

    def __init__(self, count: int = 0, visible: int = 6, default: int | None = None):
        self.count = count
        self.visible = visible
        self._default_row = default
        self.selected = self._default()
        self.offset = 0  # first visible row

    def _default(self) -> int:
        if self._default_row is not None:
            return min(self._default_row, max(0, self.count - 1))
        return 1 if self.count > 1 else 0  # the first real row, not Back

    def reset(self) -> None:
        self.selected = self._default()
        self.offset = 0

    def move(self, steps: int) -> bool:
        return self.select(self.selected + steps)

    def select(self, index: int) -> bool:
        """Select a row, clamped to the ends. Returns True if anything changed."""
        before = (self.selected, self.offset)
        self.selected = max(0, min(self.count - 1, index)) if self.count else 0
        self._follow()
        return (self.selected, self.offset) != before

    def set_count(self, count: int) -> None:
        self.count = count
        self.select(self.selected)

    def _follow(self) -> None:
        if self.selected < self.offset:
            self.offset = self.selected
        elif self.selected >= self.offset + self.visible:
            self.offset = self.selected - self.visible + 1
        self.offset = max(0, min(self.offset, max(0, self.count - self.visible)))
