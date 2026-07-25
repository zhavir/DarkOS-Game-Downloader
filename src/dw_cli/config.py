"""Application configuration loaded from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from dw_cli.updater import DEFAULT_UPDATE_API_URL

DEFAULT_BASE_URL = "https://vimm.net"
DEFAULT_MINERVA_BASE_URL = "https://minerva-archive.org"
DEFAULT_MINERVA_TORRENT_BASE_URL = "https://cdn.minerva-archive.org/torrents"


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime settings shared by the dArkOS CLI and TUI."""

    base_url: str
    download_directory: Path
    roms_directories: tuple[Path, ...]
    timeout_seconds: float = 30.0
    minerva_base_url: str = DEFAULT_MINERVA_BASE_URL
    minerva_torrent_base_url: str = DEFAULT_MINERVA_TORRENT_BASE_URL
    enabled_stores: tuple[str, ...] = ("vimm", "minerva")
    install_directory: Path | None = None
    update_api_url: str = DEFAULT_UPDATE_API_URL
    log_file: Path | None = None
    log_level: str = "INFO"

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> Self:
        """Build settings while retaining the legacy current-directory default."""

        values = os.environ if environment is None else environment
        base_url = values.get("DW_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        directory = Path(values.get("DW_DOWNLOAD_DIR", ".")).expanduser()
        roms_values = values.get("DW_ROMS_DIRS")
        if roms_values is not None:
            roms_directories = tuple(
                dict.fromkeys(
                    Path(value).expanduser()
                    for value in roms_values.split(os.pathsep)
                    if value.strip()
                )
            )
        else:
            roms_value = values.get("DW_ROMS_DIR")
            roms_directories = (Path(roms_value).expanduser(),) if roms_value else ()
        timeout = float(values.get("DW_TIMEOUT", "30"))
        minerva_base_url = values.get("DW_MINERVA_BASE_URL", DEFAULT_MINERVA_BASE_URL).rstrip("/")
        minerva_torrent_base_url = values.get(
            "DW_MINERVA_TORRENT_BASE_URL", DEFAULT_MINERVA_TORRENT_BASE_URL
        ).rstrip("/")
        enabled_stores = tuple(
            dict.fromkeys(
                store.strip().casefold()
                for store in values.get("DW_STORES", "vimm,minerva").split(",")
                if store.strip()
            )
        )
        install_value = values.get("DW_INSTALL_DIR")
        install_directory = Path(install_value).expanduser() if install_value else None
        update_api_url = values.get("DW_UPDATE_API_URL", DEFAULT_UPDATE_API_URL)
        log_value = values.get("DW_LOG_FILE")
        log_file = Path(log_value).expanduser() if log_value else None
        log_level = values.get("DW_LOG_LEVEL", "INFO")
        return cls(
            base_url=base_url,
            download_directory=directory,
            roms_directories=roms_directories,
            timeout_seconds=timeout,
            minerva_base_url=minerva_base_url,
            minerva_torrent_base_url=minerva_torrent_base_url,
            enabled_stores=enabled_stores,
            install_directory=install_directory,
            update_api_url=update_api_url,
            log_file=log_file,
            log_level=log_level,
        )
