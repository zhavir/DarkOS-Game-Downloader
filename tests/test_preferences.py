from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from dw_cli.bittorrent import BitTorrentSettings
from dw_cli.preferences import (
    Preferences,
    PreferencesError,
    load_preferences,
    preference_path,
    save_preferences,
)


def test_store_preference_round_trip(tmp_path: Path) -> None:
    path = preference_path(tmp_path / ".downloads")

    save_preferences(path, Preferences("minerva"))

    assert load_preferences(path) == Preferences("minerva")
    assert not path.with_name(path.name + ".tmp").exists()


def test_invalid_preferences_return_first_run_state(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")

    assert load_preferences(path) == Preferences()


def test_minerva_bittorrent_preferences_round_trip(tmp_path: Path) -> None:
    path = preference_path(tmp_path)
    settings = BitTorrentSettings(
        udp_protocol_id=0x123456789,
        block_size=32 * 1024,
        max_torrent_bytes=20 * 1024 * 1024,
        max_tracker_bytes=3 * 1024 * 1024,
        max_peer_attempts=120,
        peer_race_workers=4,
        max_peer_timeout_seconds=12.5,
        max_tracker_queries=12,
        max_discovered_peers=180,
    )

    save_preferences(path, Preferences("minerva", settings))

    assert load_preferences(path) == Preferences("minerva", settings)


@pytest.mark.parametrize(
    ("payload", "expected_store"),
    [
        ("[]", None),
        ('{"store": 3}', None),
        ('{"store": "   "}', None),
        ('{"store": "  VIMM  "}', "vimm"),
        ('{"store": "VIMM", "minerva_bittorrent": []}', "vimm"),
    ],
)
def test_preferences_normalize_partial_payloads(
    tmp_path: Path,
    payload: str,
    expected_store: str | None,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(payload, encoding="utf-8")

    assert load_preferences(path).store_id == expected_store


def test_preferences_use_defaults_for_invalid_setting_types(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        """{
          "store": "minerva",
          "minerva_bittorrent": {
            "block_size": true,
            "max_peer_attempts": "many",
            "max_peer_timeout_seconds": false,
            "peer_race_workers": 0
          }
        }""",
        encoding="utf-8",
    )

    preferences = load_preferences(path)

    assert preferences.store_id == "minerva"
    assert preferences.minerva_bittorrent == BitTorrentSettings()


def test_preferences_accept_integer_timeout(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"minerva_bittorrent": {"max_peer_timeout_seconds": 12}}',
        encoding="utf-8",
    )

    assert load_preferences(path).minerva_bittorrent.max_peer_timeout_seconds == 12.0


def test_save_preferences_removes_temporary_file_after_failure(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    path = tmp_path / "settings.json"
    mocker.patch.object(Path, "write_text", side_effect=OSError("disk full"))

    with pytest.raises(PreferencesError, match="disk full"):
        save_preferences(path, Preferences("vimm"))

    assert not path.with_name("settings.json.tmp").exists()
