from timetracker.nav import FIRST_PROJECT, REPORTS, SETTINGS, STYLE, ListNav, StripNav


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


def test_counter_clockwise_reaches_reports_then_style_then_settings():
    n = nav()
    n.move(-1)
    assert n.selected == REPORTS
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
    while n.selected > SETTINGS:
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
    assert n.selected == REPORTS


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


# -- Style screen: one Back item, three parts per card -----------------------------------

def style_nav(n=7):
    return StripNav(n, column_items=1, parts=3)


def test_style_default_is_first_cards_color():
    n = style_nav()
    assert n.selected == 1
    assert n.card_and_part() == (0, 0)


def test_style_knob_visits_color_name_time_then_next_card():
    n = style_nav()
    seen = []
    for _ in range(5):
        seen.append(n.card_and_part())
        n.move(1)
    assert seen == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]


def test_style_counter_clockwise_from_first_part_reaches_back():
    n = style_nav()
    n.move(-1)
    assert n.selected == 0 and n.card_and_part() == (-1, -1)
    n.move(-1)
    assert n.selected == 0


def test_style_scrolls_when_the_fourth_card_is_reached():
    n = style_nav()
    for _ in range(3 * 2 + 2):          # card 2 (Admin), last part
        n.move(1)
    assert n.card_and_part() == (2, 2) and n.offset == 1   # Learning is the 4th slot: scrolled
    n = style_nav()
    for _ in range(3 * 1 + 2):
        n.move(1)
    assert n.card_and_part() == (1, 2) and n.offset == 0


def test_style_every_part_is_visible():
    for count in range(0, 10):
        n = style_nav(count)
        for step in [1] * (3 * count + 3) + [-1] * (3 * count + 4):
            n.move(step)
            card, _ = n.card_and_part()
            slot = card + 1
            assert n.offset <= slot < n.offset + 5


def test_main_nav_card_and_part():
    n = nav()
    assert n.card_and_part() == (0, 0)
    n.move(-1)
    assert n.card_and_part() == (-1, -1)


# -- list screens ---------------------------------------------------------------------------

def test_list_default_is_the_first_real_row_not_back():
    n = ListNav(4)
    assert n.selected == 1
    assert ListNav(1).selected == 0 and ListNav(0).selected == 0


def test_list_turn_left_reaches_back_and_stops():
    n = ListNav(4)
    n.move(-1)
    assert n.selected == 0
    n.move(-1)
    assert n.selected == 0


def test_list_stops_at_the_last_row():
    n = ListNav(4)
    for _ in range(10):
        n.move(1)
    assert n.selected == 3


def test_list_window_follows_the_selection():
    n = ListNav(12, visible=5)
    for _ in range(11):
        n.move(1)
    assert n.selected == 11 and n.offset == 7
    for _ in range(11):
        n.move(-1)
    assert n.selected == 0 and n.offset == 0


def test_list_selection_is_always_visible():
    for count in range(0, 15):
        n = ListNav(count, visible=4)
        for step in [1] * (count + 2) + [-1] * (count + 2):
            n.move(step)
            assert n.offset <= n.selected < n.offset + 4 or count == 0


def test_list_set_count_clamps():
    n = ListNav(10, visible=4)
    for _ in range(9):
        n.move(1)
    n.set_count(3)
    assert n.selected == 2 and n.offset == 0


# -- Style screen with a trailing "+" item ---------------------------------------------------

def style4(n=5):
    return StripNav(n, column_items=2, parts=4, trailing=1)


def test_style4_default_is_the_first_cards_colour():
    n = style4()
    assert n.selected == 2 and n.card_and_part() == (0, 0)


def test_style4_knob_visits_four_parts_then_the_plus_card():
    n = style4(2)
    seen = []
    for _ in range(10):
        seen.append(n.card_and_part())
        n.move(1)
    assert seen[:8] == [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3)]
    assert seen[8] == (2, 0)                  # the "+" card: card index == project_count
    assert seen[9] == (2, 0)                  # and the end: no wrap
    assert n.selected == n.last


def test_style4_left_from_the_first_part_reaches_archived_then_back():
    n = style4()
    n.move(-1)
    assert n.selected == 1 and n.card_and_part() == (-1, -1)
    n.move(-1)
    assert n.selected == 0
    n.move(-1)
    assert n.selected == 0


def test_style4_with_no_projects_only_the_plus_card_remains():
    n = style4(0)
    assert n.selected == 2 and n.card_and_part() == (0, 0)
    n.move(5)
    assert n.selected == 2
    n.move(-1)
    assert n.selected == 1


def test_style4_every_item_is_visible_and_the_plus_card_is_reachable():
    for count in range(0, 10):
        n = style4(count)
        for step in [1] * (4 * count + 4) + [-1] * (4 * count + 5):
            n.move(step)
            card, _ = n.card_and_part()
            assert n.offset <= card + 1 < n.offset + 5
        for _ in range(4 * count + 4):
            n.move(1)
        assert n.card_and_part() == (count, 0)


def test_style4_scrolling_counts_the_plus_card_as_a_slot():
    n = style4(3)                              # slots: col, 3 cards, "+"
    for _ in range(4 * 3):
        n.move(1)                              # now on the "+" card, slot 4
    assert n.card_and_part() == (3, 0) and n.offset == 0   # five slots fit exactly
    n = style4(4)
    for _ in range(4 * 4):
        n.move(1)
    assert n.card_and_part() == (4, 0) and n.offset == 1
