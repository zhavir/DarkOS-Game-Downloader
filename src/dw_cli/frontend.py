"""Request a safe EmulationStation game-list refresh from the device launcher."""

import os
from collections.abc import Mapping
from pathlib import Path

REFRESH_FILE_ENV = "DW_ES_REFRESH_FILE"


def request_emulationstation_refresh(environment: Mapping[str, str] | None = None) -> bool:
    """Ask the dArkOS launcher to restart EmulationStation after this tool exits."""

    values = os.environ if environment is None else environment
    configured_path = values.get(REFRESH_FILE_ENV, "").strip()
    if not configured_path:
        return False
    refresh_file = Path(configured_path)
    try:
        refresh_file.parent.mkdir(parents=True, exist_ok=True)
        refresh_file.touch()
    except OSError:
        return False
    return True
