from dataclasses import replace
from pathlib import Path

from ph.frontend import REFRESH_FILE_ENV, request_game_frontend_refresh
from ph.targets import DARKOS


def test_refresh_request_is_disabled_outside_device_launcher() -> None:
    assert not request_game_frontend_refresh({})


def test_refresh_request_creates_launcher_signal(
    tmp_path: Path,
) -> None:
    refresh_file = tmp_path / "app" / ".refresh-emulationstation"

    assert request_game_frontend_refresh({REFRESH_FILE_ENV: str(refresh_file)})
    assert refresh_file.is_file()


def test_refresh_request_reports_unwritable_signal_path(tmp_path: Path) -> None:
    occupied = tmp_path / "file"
    occupied.write_text("not a directory", encoding="utf-8")

    assert not request_game_frontend_refresh(
        {REFRESH_FILE_ENV: str(occupied / ".refresh-emulationstation")}
    )


def test_refresh_request_uses_the_selected_target_marker(tmp_path: Path) -> None:
    target = replace(DARKOS, target_id="future", refresh_marker_environment="FUTURE_REFRESH")
    refresh_file = tmp_path / ".refresh"

    assert request_game_frontend_refresh({"FUTURE_REFRESH": str(refresh_file)}, target)
    assert refresh_file.is_file()
