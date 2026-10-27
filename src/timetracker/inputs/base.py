from PySide6.QtCore import QObject, Signal


class InputSource(QObject):
    """A knob and a button.

    turned(steps): +1 per detent clockwise, -1 per detent counter-clockwise.
    pressed(): the button went down.
    """

    turned = Signal(int)
    pressed = Signal()
