from pathlib import Path

from dw_cli.frontend import REFRESH_FILE_ENV, request_emulationstation_refresh


def test_refresh_request_is_disabled_outside_device_launcher() -> None:
    assert not request_emulationstation_refresh({})


def test_refresh_request_creates_launcher_signal(
    tmp_path: Path,
) -> None:
    refresh_file = tmp_path / "app" / ".refresh-emulationstation"

    assert request_emulationstation_refresh({REFRESH_FILE_ENV: str(refresh_file)})
    assert refresh_file.is_file()


def test_refresh_request_reports_unwritable_signal_path(tmp_path: Path) -> None:
    occupied = tmp_path / "file"
    occupied.write_text("not a directory", encoding="utf-8")

    assert not request_emulationstation_refresh(
        {REFRESH_FILE_ENV: str(occupied / ".refresh-emulationstation")}
    )
