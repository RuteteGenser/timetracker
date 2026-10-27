"""Real GPIO input for the Raspberry Pi (milestone 5)."""

from .base import InputSource


class GpioInput(InputSource):
    def __init__(self, encoder_a: int, encoder_b: int, button: int):
        raise NotImplementedError("GPIO input is added in milestone 5; use driver = \"sim\" for now")
