from timetracker.nav import FIRST_PROJECT, SETTINGS, STYLE, StripNav


def nav(n=7):
    return StripNav(n)


def test_default_view():
    n = nav()
    assert n.selected == FIRST_PROJECT
    assert n.offset == 0


def test_scrolling_starts_when_the_fourth_item_is_selected():
    """Items: 1 = Settings/Style column, 2 = project 1 (Work), 3 = project 2 (Admin), 4 = project 3 (Learning)."""
    n = nav()
    n.move(1)                                   # Admin, the 3rd item
    assert (n.selected - FIRST_PROJECT, n.offset) == (1, 0)
    n.move(1)                                   # Learning, the 4th item: the strip starts to move
    assert (n.selected - FIRST_PROJECT, n.offset) == (2, 1)


def test_clockwise_keeps_scrolling_one_card_per_step():
    n = nav(7)
    seen = []
    for _ in range(6):
        n.move(1)
        seen.append((n.selected - FIRST_PROJECT, n.offset))
    # last offset is project_count + 1 - 5 = 3, so the end of the list is reached at offset 3
    assert seen == [(1, 0), (2, 1), (3, 2), (4, 3), (5, 3), (6, 3)]


def test_stops_at_last_project():
    n = nav(5)
    for _ in range(20):
        n.move(1)
    assert n.selected == FIRST_PROJECT + 4


def test_counter_clockwise_reaches_style_then_settings():
    n = nav()
    n.move(-1)
    assert n.selected == STYLE
    n.move(-1)
    assert n.selected == SETTINGS
    n.move(-1)
    assert n.selected == SETTINGS  # no wrap


def test_scrolling_back_brings_the_column_back():
    n = nav()
    for _ in range(6):
        n.move(1)
    assert n.offset == 3
    while n.selected > STYLE:
        n.move(-1)
    assert n.offset == 0


def test_every_selection_is_visible():
    for count in range(0, 12):
        n = nav(count)
        for step in [1] * (count + 3) + [-1] * (count + 4):
            n.move(step)
            slot = 0 if n.selected < FIRST_PROJECT else n.selected - FIRST_PROJECT + 1
            assert n.offset <= slot < n.offset + 5


def test_select_returns_whether_state_changed():
    n = nav()
    assert n.select(FIRST_PROJECT) is False
    assert n.select(FIRST_PROJECT + 1) is True


def test_four_projects_fit_without_scrolling():
    n = nav(4)
    for _ in range(5):
        n.move(1)
    assert n.offset == 0 and n.selected == FIRST_PROJECT + 3


def test_no_projects():
    n = StripNav(0)
    assert n.selected == SETTINGS
    n.move(5)
    assert n.selected == STYLE


def test_project_count_shrinks():
    n = nav(7)
    for _ in range(6):
        n.move(1)
    n.set_project_count(3)
    assert n.selected == FIRST_PROJECT + 2
    assert n.offset == 0


def test_reset():
    n = nav()
    for _ in range(5):
        n.move(1)
    n.reset()
    assert (n.selected, n.offset) == (FIRST_PROJECT, 0)


def test_first_projects_appearing_selects_the_first_project():
    n = StripNav(0)
    n.set_project_count(6)
    assert (n.selected, n.offset) == (FIRST_PROJECT, 0)
