import tomllib
from pathlib import Path

import timetracker
from timetracker.hardware import rtc_info


def test_no_rtc_on_a_pc(tmp_path):
    assert rtc_info(tmp_path) == "not found"


def test_rtc_without_battery_information(tmp_path):
    (tmp_path / "rtc0").mkdir()
    assert rtc_info(tmp_path) == "found, battery unknown"


def test_rtc_with_battery_voltage(tmp_path):
    device = tmp_path / "rtc0" / "device"
    device.mkdir(parents=True)
    (device / "battery_voltage").write_text("3012345\n")
    assert rtc_info(tmp_path) == "found, battery 3.01 V"


def test_a_garbled_voltage_file_is_not_trusted(tmp_path):
    device = tmp_path / "rtc0" / "device"
    device.mkdir(parents=True)
    (device / "battery_voltage").write_text("n/a")
    assert rtc_info(tmp_path) == "found, battery unknown"


def test_version_matches_pyproject():
    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == timetracker.__version__
