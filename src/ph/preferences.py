"""Persistent user preferences for the controller-driven TUI."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ph.bittorrent import BitTorrentSettings
from ph.cache_policy import DEFAULT_CATALOGUE_TTL_DAYS
from ph.download_queue import (
    DEFAULT_CONCURRENT_DOWNLOADS,
    RateLimitRetrySettings,
)
from ph.i18n import DEFAULT_LANGUAGE, LanguageCode, normalize_language

PREFERENCES_FILENAME = ".pocket-harbor.json"


class PreferencesError(RuntimeError):
    """Preferences could not be saved."""


@dataclass(frozen=True, slots=True)
class Preferences:
    """Settings selected from the TUI options screen."""

    store_id: str | None = None
    minerva_bittorrent: BitTorrentSettings = field(default_factory=BitTorrentSettings)
    catalogue_ttl_days: int = DEFAULT_CATALOGUE_TTL_DAYS
    log_level: str | None = None
    log_to_file: bool | None = None
    language: LanguageCode = DEFAULT_LANGUAGE
    max_concurrent_downloads: int = DEFAULT_CONCURRENT_DOWNLOADS
    rate_limit_retry: RateLimitRetrySettings = field(default_factory=RateLimitRetrySettings)
    default_roms_directory: str | None = None
    network_timeout_seconds: float | None = None
    store_rom_mappings: dict[str, dict[str, str]] = field(default_factory=dict)
    bios_directory: str = "bios"


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
    ttl_days = _integer_setting(payload, "catalogue_ttl_days", DEFAULT_CATALOGUE_TTL_DAYS)
    if ttl_days <= 0:
        ttl_days = DEFAULT_CATALOGUE_TTL_DAYS
    raw_log_level = payload.get("log_level")
    log_level = (
        raw_log_level.upper()
        if isinstance(raw_log_level, str)
        and raw_log_level.upper() in {"DEBUG", "INFO", "WARNING", "ERROR"}
        else None
    )
    raw_log_to_file = payload.get("log_to_file")
    log_to_file = raw_log_to_file if isinstance(raw_log_to_file, bool) else None
    raw_default_roms_directory = payload.get("default_roms_directory")
    default_roms_directory = (
        raw_default_roms_directory.strip()
        if isinstance(raw_default_roms_directory, str) and raw_default_roms_directory.strip()
        else None
    )
    network_timeout_seconds = _optional_float_setting(payload, "network_timeout_seconds")
    if network_timeout_seconds is not None and not 1 <= network_timeout_seconds <= 3600:
        network_timeout_seconds = None
    store_rom_mappings = _store_rom_mappings(payload.get("store_rom_mappings"))
    bios_directory = _relative_directory(payload.get("bios_directory")) or "bios"
    language = normalize_language(payload.get("language"))
    max_concurrent_downloads = _integer_setting(
        payload,
        "max_concurrent_downloads",
        DEFAULT_CONCURRENT_DOWNLOADS,
    )
    if not 1 <= max_concurrent_downloads <= 8:
        max_concurrent_downloads = DEFAULT_CONCURRENT_DOWNLOADS
    retry_defaults = RateLimitRetrySettings()
    retry_payload = payload.get("rate_limit_retry")
    if isinstance(retry_payload, dict):
        try:
            rate_limit_retry = RateLimitRetrySettings(
                base_seconds=_float_setting(
                    retry_payload,
                    "base_seconds",
                    retry_defaults.base_seconds,
                ),
                max_seconds=_float_setting(
                    retry_payload,
                    "max_seconds",
                    retry_defaults.max_seconds,
                ),
                jitter_ratio=_float_setting(
                    retry_payload,
                    "jitter_ratio",
                    retry_defaults.jitter_ratio,
                ),
            )
        except ValueError:
            rate_limit_retry = retry_defaults
    else:
        rate_limit_retry = retry_defaults
    minerva_payload = payload.get("minerva_bittorrent")
    defaults = BitTorrentSettings()
    if not isinstance(minerva_payload, dict):
        return Preferences(
            store_id=normalized_store_id,
            minerva_bittorrent=defaults,
            catalogue_ttl_days=ttl_days,
            log_level=log_level,
            log_to_file=log_to_file,
            language=language,
            max_concurrent_downloads=max_concurrent_downloads,
            rate_limit_retry=rate_limit_retry,
            default_roms_directory=default_roms_directory,
            network_timeout_seconds=network_timeout_seconds,
            store_rom_mappings=store_rom_mappings,
            bios_directory=bios_directory,
        )
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
    return Preferences(
        store_id=normalized_store_id,
        minerva_bittorrent=settings,
        catalogue_ttl_days=ttl_days,
        log_level=log_level,
        log_to_file=log_to_file,
        language=language,
        max_concurrent_downloads=max_concurrent_downloads,
        rate_limit_retry=rate_limit_retry,
        default_roms_directory=default_roms_directory,
        network_timeout_seconds=network_timeout_seconds,
        store_rom_mappings=store_rom_mappings,
        bios_directory=bios_directory,
    )


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
                    "catalogue_ttl_days": preferences.catalogue_ttl_days,
                    "log_level": preferences.log_level,
                    "log_to_file": preferences.log_to_file,
                    "language": preferences.language,
                    "max_concurrent_downloads": preferences.max_concurrent_downloads,
                    "default_roms_directory": preferences.default_roms_directory,
                    "network_timeout_seconds": preferences.network_timeout_seconds,
                    "store_rom_mappings": preferences.store_rom_mappings,
                    "bios_directory": preferences.bios_directory,
                    "rate_limit_retry": {
                        "base_seconds": preferences.rate_limit_retry.base_seconds,
                        "max_seconds": preferences.rate_limit_retry.max_seconds,
                        "jitter_ratio": preferences.rate_limit_retry.jitter_ratio,
                    },
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


def _optional_float_setting(payload: dict[object, object], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _relative_directory(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _store_rom_mappings(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    mappings: dict[str, dict[str, str]] = {}
    for raw_store_id, raw_platforms in value.items():
        if not isinstance(raw_store_id, str) or not isinstance(raw_platforms, dict):
            continue
        store_id = raw_store_id.strip().casefold()
        if not store_id:
            continue
        platforms: dict[str, str] = {}
        for raw_slug, raw_directory in raw_platforms.items():
            if not isinstance(raw_slug, str):
                continue
            slug = raw_slug.strip().casefold()
            directory = _relative_directory(raw_directory)
            if slug and directory is not None:
                platforms[slug] = directory
        if platforms:
            mappings[store_id] = platforms
    return mappings
