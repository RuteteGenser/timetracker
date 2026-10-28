from timetracker.colors import COLOR_CYCLE, next_color


def test_cycle_has_eight_distinct_colors():
    assert len(COLOR_CYCLE) == 8
    assert len(set(COLOR_CYCLE)) == 8


def test_next_color_steps_through_all_eight_and_wraps():
    color = COLOR_CYCLE[0]
    seen = [color]
    for _ in range(8):
        color = next_color(color)
        seen.append(color)
    assert seen[:8] == COLOR_CYCLE
    assert seen[8] == COLOR_CYCLE[0]


def test_unknown_color_starts_the_cycle():
    assert next_color("#123456") == COLOR_CYCLE[0]


def test_case_is_ignored():
    assert next_color(COLOR_CYCLE[1].upper()) == COLOR_CYCLE[2]
