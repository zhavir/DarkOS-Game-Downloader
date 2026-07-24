"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

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

    @classmethod
    def from_environment(cls) -> Self:
        """Build settings while retaining the legacy current-directory default."""

        base_url = os.environ.get("DW_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        directory = Path(os.environ.get("DW_DOWNLOAD_DIR", ".")).expanduser()
        roms_values = os.environ.get("DW_ROMS_DIRS")
        if roms_values is not None:
            roms_directories = tuple(
                dict.fromkeys(
                    Path(value).expanduser()
                    for value in roms_values.split(os.pathsep)
                    if value.strip()
                )
            )
        else:
            roms_value = os.environ.get("DW_ROMS_DIR")
            roms_directories = (Path(roms_value).expanduser(),) if roms_value else ()
        timeout = float(os.environ.get("DW_TIMEOUT", "30"))
        minerva_base_url = os.environ.get("DW_MINERVA_BASE_URL", DEFAULT_MINERVA_BASE_URL).rstrip(
            "/"
        )
        minerva_torrent_base_url = os.environ.get(
            "DW_MINERVA_TORRENT_BASE_URL", DEFAULT_MINERVA_TORRENT_BASE_URL
        ).rstrip("/")
        enabled_stores = tuple(
            dict.fromkeys(
                store.strip().casefold()
                for store in os.environ.get("DW_STORES", "vimm,minerva").split(",")
                if store.strip()
            )
        )
        return cls(
            base_url=base_url,
            download_directory=directory,
            roms_directories=roms_directories,
            timeout_seconds=timeout,
            minerva_base_url=minerva_base_url,
            minerva_torrent_base_url=minerva_torrent_base_url,
            enabled_stores=enabled_stores,
        )
