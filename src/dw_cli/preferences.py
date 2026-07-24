"""Persistent user preferences for the controller-driven TUI."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

PREFERENCES_FILENAME = ".darkos-downloader.json"


class PreferencesError(RuntimeError):
    """Preferences could not be saved."""


@dataclass(frozen=True, slots=True)
class Preferences:
    """Settings selected from the TUI options screen."""

    store_id: str | None = None


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
        return Preferences()
    return Preferences(store_id.strip().casefold())


def save_preferences(path: Path, preferences: Preferences) -> None:
    """Atomically persist preferences without leaving a partial JSON file."""

    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps({"store": preferences.store_id}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise PreferencesError(f"Could not save TUI settings: {error}") from error
