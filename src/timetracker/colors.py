"""Project colour palette (all dark enough for white text)."""

PALETTE = [
    ("Red", "#c8424e"),
    ("Orange", "#d9722f"),
    ("Amber", "#b8861b"),
    ("Lime", "#6f9420"),
    ("Green", "#2f9a58"),
    ("Teal", "#1a948f"),
    ("Blue", "#3274d1"),
    ("Indigo", "#5656cf"),
    ("Purple", "#9250b4"),
    ("Pink", "#cc4a93"),
    ("Brown", "#85665a"),
    ("Slate", "#586c7e"),
]

# The Style screen steps through these on every press (dark enough for white text).
COLOR_CYCLE = ["#c8424e", "#d9722f", "#b8861b", "#2f9a58", "#1a948f", "#3274d1", "#9250b4", "#cc4a93"]


def next_color(current: str) -> str:
    """The colour after `current` in COLOR_CYCLE; an unknown colour starts the cycle."""
    try:
        i = COLOR_CYCLE.index(current.lower())
    except ValueError:
        return COLOR_CYCLE[0]
    return COLOR_CYCLE[(i + 1) % len(COLOR_CYCLE)]
