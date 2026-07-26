"""Request a safe game-frontend refresh from the active target launcher."""

import os
from collections.abc import Mapping
from pathlib import Path

from ph.targets import DARKOS, LinuxTarget

REFRESH_FILE_ENV = DARKOS.refresh_marker_environment


def request_game_frontend_refresh(
    environment: Mapping[str, str] | None = None,
    target: LinuxTarget = DARKOS,
) -> bool:
    """Ask the active target launcher to refresh its game frontend after exit."""

    values = os.environ if environment is None else environment
    configured_path = values.get(target.refresh_marker_environment, "").strip()
    if not configured_path:
        return False
    refresh_file = Path(configured_path)
    try:
        refresh_file.parent.mkdir(parents=True, exist_ok=True)
        refresh_file.touch()
    except OSError:
        return False
    return True
