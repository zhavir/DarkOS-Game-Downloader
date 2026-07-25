from pathlib import Path

from dw_cli.bittorrent import BitTorrentSettings
from dw_cli.preferences import Preferences, load_preferences, preference_path, save_preferences


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
