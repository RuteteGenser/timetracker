"""Simulated knob and button for PC development.

Left/Right arrow = turn the knob, Space (or Enter) = press the button.
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QWindow

from .base import InputSource


class SimInput(InputSource):
    def __init__(self, app):
        super().__init__(app)
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.KeyPress or not isinstance(obj, QWindow):
            return False
        key = event.key()
        if key == Qt.Key.Key_Right:
            self.turned.emit(1)
            return True
        if key == Qt.Key.Key_Left:
            self.turned.emit(-1)
            return True
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.isAutoRepeat():
                self.pressed.emit()
            return True
        return False
