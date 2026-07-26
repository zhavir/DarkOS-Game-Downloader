"""Installed game discovery, deletion, and transactional replacement."""

import logging
import os
import re
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from ph.models import DownloadResult, InstalledGame, Platform
from ph.organizer import OrganizeError, unique_destination

LOGGER = logging.getLogger(__name__)

IGNORED_SUFFIXES = {
    ".cfg",
    ".db",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".mp4",
    ".png",
    ".sav",
    ".srm",
    ".state",
    ".txt",
    ".xml",
}
IGNORED_DIRECTORIES = {"images", "manuals", "screenshots", "videos"}
PLAYLIST_SUFFIXES = {".cue", ".m3u"}


class LibraryError(RuntimeError):
    """An installed game could not be managed safely."""


def scan_library(
    roms_directories: Iterable[Path], platforms: Sequence[Platform]
) -> list[InstalledGame]:
    """Scan known platform folders on every mounted ROM partition."""

    roots = tuple(roms_directories)
    LOGGER.debug("Scanning ROM library roots=%s platforms=%d", roots, len(platforms))
    games: list[InstalledGame] = []
    for root in roots:
        root = root.resolve()
        for platform in platforms:
            for folder_name in platform.rom_folders:
                folder = root / folder_name
                if not folder.is_dir():
                    continue
                candidates = list(_iter_game_candidates(folder))
                referenced: set[Path] = set()
                grouped: dict[Path, tuple[Path, ...]] = {}
                for path in candidates:
                    if path.suffix.casefold() in PLAYLIST_SUFFIXES:
                        members = _referenced_files(path)
                        grouped[path] = tuple(dict.fromkeys((path, *members)))
                        referenced.update(members)
                for path in candidates:
                    if path in referenced:
                        continue
                    members = grouped.get(path, (path,))
                    games.append(
                        InstalledGame(
                            title=search_title(path),
                            platform=platform,
                            roms_directory=root,
                            primary_file=path,
                            files=members,
                        )
                    )
    result = sorted(games, key=lambda game: (game.platform.name.casefold(), game.title.casefold()))
    LOGGER.info("ROM library scan completed games=%d roots=%d", len(result), len(roots))
    return result


def platforms_with_installed_games(
    roms_directory: Path,
    platforms: Sequence[Platform],
) -> tuple[Platform, ...]:
    """Quickly find navigable platforms without fully indexing every installed game."""

    available: list[Platform] = []
    for platform in platforms:
        if any(
            next(_iter_game_candidates(roms_directory / folder), None) is not None
            for folder in platform.rom_folders
            if (roms_directory / folder).is_dir()
        ):
            available.append(platform)
    return tuple(available)


def search_title(path: Path) -> str:
    """Turn a ROM filename into a useful remote search phrase."""

    title = path.stem.replace("_", " ").replace(".", " ")
    title = re.sub(r"\s*[\[(].*?[\])]", " ", title)
    title = re.sub(r"\s+-\s+(?:disc|disk|side)\s*\w+$", " ", title, flags=re.IGNORECASE)
    return " ".join(title.split()) or path.stem


def delete_game(game: InstalledGame) -> None:
    """Permanently remove all files grouped under an installed title."""

    errors: list[str] = []
    for path in game.files:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as error:
            errors.append(f"{path.name}: {error}")
    if errors:
        LOGGER.error("Could not completely delete game title=%r errors=%s", game.title, errors)
        raise LibraryError("Some game files could not be deleted: {}".format("; ".join(errors)))
    LOGGER.info("Deleted installed game title=%r files=%d", game.title, len(game.files))


def replace_game(game: InstalledGame, download: DownloadResult) -> DownloadResult:
    """Move a complete replacement beside the old game, then remove the old files."""

    source = download.path
    if not source.is_file():
        raise LibraryError(f"The completed replacement file was not found: {source}")
    requested = game.primary_file.parent / source.name
    existing_files = set(game.files)
    destination = requested if requested in existing_files else unique_destination(requested)
    try:
        source.replace(destination)
    except OSError:
        try:
            import shutil

            shutil.move(str(source), str(destination))
        except OSError as error:
            raise OrganizeError(f"Could not install the replacement: {error}") from error

    delete_errors: list[str] = []
    for old_file in game.files:
        if old_file == destination:
            continue
        try:
            old_file.unlink()
        except FileNotFoundError:
            continue
        except OSError as error:
            delete_errors.append(f"{old_file.name}: {error}")
    if delete_errors:
        LOGGER.warning(
            "Replacement installed but old files remain title=%r errors=%s",
            game.title,
            delete_errors,
        )
        raise LibraryError(
            "The new game was installed at {}, but old files remain: {}".format(
                destination, "; ".join(delete_errors)
            )
        )
    LOGGER.info("Replaced installed game title=%r path=%s", game.title, destination)
    return DownloadResult(url=download.url, path=destination)


def _is_game_candidate(path: Path) -> bool:
    if not path.is_file() or path.name.startswith("."):
        return False
    if any(part.casefold() in IGNORED_DIRECTORIES for part in path.parts):
        return False
    return path.suffix.casefold() not in IGNORED_SUFFIXES


def _iter_game_candidates(folder: Path) -> Iterator[Path]:
    """Yield game-like files while avoiding expensive media and metadata subtrees."""

    for directory, child_directories, filenames in os.walk(folder, followlinks=False):
        child_directories[:] = [
            name
            for name in child_directories
            if not name.startswith(".") and name.casefold() not in IGNORED_DIRECTORIES
        ]
        parent = Path(directory)
        for filename in filenames:
            path = parent / filename
            if _is_game_candidate(path):
                yield path.resolve()


def _referenced_files(playlist: Path) -> tuple[Path, ...]:
    try:
        text = playlist.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    names: list[str] = []
    if playlist.suffix.casefold() == ".cue":
        names.extend(re.findall(r'^\s*FILE\s+"([^"]+)"', text, flags=re.IGNORECASE | re.MULTILINE))
    else:
        names.extend(
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    members: list[Path] = []
    for name in names:
        candidate = (playlist.parent / name).resolve()
        try:
            candidate.relative_to(playlist.parent.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            members.append(candidate)
            if candidate.suffix.casefold() in PLAYLIST_SUFFIXES:
                members.extend(_referenced_files(candidate))
    return tuple(dict.fromkeys(members))
