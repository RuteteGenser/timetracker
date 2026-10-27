from timetracker.nav import FIRST_PROJECT, SETTINGS, STYLE, StripNav


def nav(n=7):
    return StripNav(n)


def test_default_view():
    n = nav()
    assert n.selected == FIRST_PROJECT
    assert n.offset == 0


def test_clockwise_moves_right_and_slides_after_fourth_tile():
    n = nav()
    seen = []
    for _ in range(6):
        n.move(1)
        seen.append((n.selected - FIRST_PROJECT, n.offset))
    # selecting projects 2,3,4 (index 1,2,3) does not scroll; 5 (index 4) does
    assert seen[:3] == [(1, 0), (2, 0), (3, 0)]
    assert seen[3] == (4, 1)
    assert seen[4] == (5, 2)
    assert seen[5] == (6, 3)


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
    for _ in range(3):
        n.move(-1)
        assert n.offset == 3 or n.offset == n.selected - FIRST_PROJECT
    # selection at project index 3 (still inside window 3..6), keep going left
    while n.selected > STYLE:
        n.move(-1)
    assert n.offset == 0


def test_view_stays_still_while_selection_moves_inside_window():
    n = nav()
    for _ in range(4):
        n.move(1)          # now at index 4, offset 1
    assert n.offset == 1
    n.move(-1)
    n.move(-1)             # index 2, still inside tiles 1..4
    assert n.offset == 1


def test_select_returns_whether_state_changed():
    n = nav()
    assert n.select(FIRST_PROJECT) is False
    assert n.select(FIRST_PROJECT + 1) is True


def test_few_projects_never_scroll():
    n = nav(3)
    for _ in range(5):
        n.move(1)
    assert n.offset == 0 and n.selected == FIRST_PROJECT + 2


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
