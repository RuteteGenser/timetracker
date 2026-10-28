"""Read-only facts about the machine, for the Status page.

Everything here is best effort: on a PC, or when a file is missing, the answer is a plain
"not found" or "unknown" instead of an error.
"""

from pathlib import Path

SYSFS_RTC = Path("/sys/class/rtc")


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def rtc_info(root: Path = SYSFS_RTC) -> str:
    """Is there a hardware clock (RTC), and what does it say about its battery?

    The Raspberry Pi 5's RTC shows up as rtc0. The battery voltage file name below is the one used
    by the Pi 5 kernel driver as far as known and has NOT been checked on a real board yet; when it
    is missing the answer is just "found".
    """
    rtc = root / "rtc0"
    if not rtc.exists():
        return "not found"
    microvolts = _read(rtc / "device" / "battery_voltage")
    if microvolts and microvolts.isdigit():
        return f"found, battery {int(microvolts) / 1_000_000:.2f} V"
    return "found, battery unknown"
