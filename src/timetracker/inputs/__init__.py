"""Input drivers. The app only sees InputSource; the config picks the driver."""

from .base import InputSource


def make_input(config, app) -> InputSource:
    if config.input_driver == "sim":
        from .sim import SimInput

        return SimInput(app)
    if config.input_driver == "gpio":
        from .gpio import GpioInput

        return GpioInput(config.encoder_a, config.encoder_b, config.button)
    raise ValueError(f"unknown input driver: {config.input_driver!r} (use 'sim' or 'gpio')")
