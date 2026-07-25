"""Persistent user preferences for the controller-driven TUI."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dw_cli.bittorrent import BitTorrentSettings

PREFERENCES_FILENAME = ".darkos-downloader.json"


class PreferencesError(RuntimeError):
    """Preferences could not be saved."""


@dataclass(frozen=True, slots=True)
class Preferences:
    """Settings selected from the TUI options screen."""

    store_id: str | None = None
    minerva_bittorrent: BitTorrentSettings = field(default_factory=BitTorrentSettings)


def preference_path(download_directory: Path) -> Path:
    """Keep settings beside staged downloads in the tool's writable directory."""

    return download_directory / PREFERENCES_FILENAME


def load_preferences(path: Path) -> Preferences:
    """Read preferences, treating absent or malformed files as first-run state."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        return Preferences()
    if not isinstance(payload, dict):
        return Preferences()
    store_id = payload.get("store")
    if not isinstance(store_id, str) or not store_id.strip():
        normalized_store_id = None
    else:
        normalized_store_id = store_id.strip().casefold()
    minerva_payload = payload.get("minerva_bittorrent")
    defaults = BitTorrentSettings()
    if not isinstance(minerva_payload, dict):
        return Preferences(normalized_store_id, defaults)
    try:
        settings = BitTorrentSettings(
            udp_protocol_id=_integer_setting(
                minerva_payload,
                "udp_protocol_id",
                defaults.udp_protocol_id,
            ),
            block_size=_integer_setting(minerva_payload, "block_size", defaults.block_size),
            max_torrent_bytes=_integer_setting(
                minerva_payload,
                "max_torrent_bytes",
                defaults.max_torrent_bytes,
            ),
            max_tracker_bytes=_integer_setting(
                minerva_payload,
                "max_tracker_bytes",
                defaults.max_tracker_bytes,
            ),
            max_peer_attempts=_integer_setting(
                minerva_payload,
                "max_peer_attempts",
                defaults.max_peer_attempts,
            ),
            peer_race_workers=_integer_setting(
                minerva_payload,
                "peer_race_workers",
                defaults.peer_race_workers,
            ),
            max_peer_timeout_seconds=_float_setting(
                minerva_payload,
                "max_peer_timeout_seconds",
                defaults.max_peer_timeout_seconds,
            ),
            max_tracker_queries=_integer_setting(
                minerva_payload,
                "max_tracker_queries",
                defaults.max_tracker_queries,
            ),
            max_discovered_peers=_integer_setting(
                minerva_payload,
                "max_discovered_peers",
                defaults.max_discovered_peers,
            ),
        )
    except ValueError:
        settings = defaults
    return Preferences(normalized_store_id, settings)


def save_preferences(path: Path, preferences: Preferences) -> None:
    """Atomically persist preferences without leaving a partial JSON file."""

    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        settings = preferences.minerva_bittorrent
        temporary.write_text(
            json.dumps(
                {
                    "store": preferences.store_id,
                    "minerva_bittorrent": {
                        "udp_protocol_id": settings.udp_protocol_id,
                        "block_size": settings.block_size,
                        "max_torrent_bytes": settings.max_torrent_bytes,
                        "max_tracker_bytes": settings.max_tracker_bytes,
                        "max_peer_attempts": settings.max_peer_attempts,
                        "peer_race_workers": settings.peer_race_workers,
                        "max_peer_timeout_seconds": settings.max_peer_timeout_seconds,
                        "max_tracker_queries": settings.max_tracker_queries,
                        "max_discovered_peers": settings.max_discovered_peers,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise PreferencesError(f"Could not save TUI settings: {error}") from error


def _integer_setting(payload: dict[object, object], key: str, default: int) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _float_setting(payload: dict[object, object], key: str, default: float) -> float:
    value = payload.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return default
