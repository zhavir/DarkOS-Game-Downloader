from pathlib import Path

import pytest

from dw_cli.frontend import REFRESH_FILE_ENV, request_emulationstation_refresh


def test_refresh_request_is_disabled_outside_device_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(REFRESH_FILE_ENV, raising=False)
    assert not request_emulationstation_refresh()


def test_refresh_request_creates_launcher_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refresh_file = tmp_path / "app" / ".refresh-emulationstation"
    monkeypatch.setenv(REFRESH_FILE_ENV, str(refresh_file))

    assert request_emulationstation_refresh()
    assert refresh_file.is_file()
