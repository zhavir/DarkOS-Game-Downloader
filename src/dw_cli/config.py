"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

DEFAULT_BASE_URL = "https://vimm.net"


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime settings shared by the dArkOS CLI and TUI."""

    base_url: str
    download_directory: Path
    roms_directories: tuple[Path, ...]
    timeout_seconds: float = 30.0

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
        return cls(
            base_url=base_url,
            download_directory=directory,
            roms_directories=roms_directories,
            timeout_seconds=timeout,
        )
