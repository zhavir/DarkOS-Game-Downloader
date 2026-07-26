"""Move completed downloads into a target's ROM library."""

import logging
import os
import shutil
import stat
import zipfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path, PurePosixPath

from ph.models import DownloadResult, Platform
from ph.targets import DARKOS

LOGGER = logging.getLogger(__name__)


class OrganizeError(RuntimeError):
    """A completed file could not be placed in the ROM library."""


MAX_BIOS_FILES = 128
MAX_BIOS_FILE_SIZE = 64 * 1024 * 1024
MAX_BIOS_TOTAL_SIZE = 256 * 1024 * 1024
ROM_LOCAL_BIOS: dict[str, frozenset[str]] = {
    "advision": frozenset({"advision.zip"}),
    "astrocde": frozenset({"astrocde.zip"}),
    "coco3": frozenset({"coco.zip", "coco2.zip", "coco2b.zip", "coco3.zip", "coco3p.zip"}),
}
ROM_AND_SHARED_BIOS: dict[str, frozenset[str]] = {
    "neogeo": frozenset({"aes.zip", "neogeo.zip"}),
}


def detect_roms_directories(
    configured: Path | Sequence[Path] | None = None,
    candidates: Sequence[Path] = DARKOS.rom_roots,
) -> tuple[Path, ...]:
    """Find all active ROM partitions for the selected Linux target."""

    if configured is not None:
        return (configured,) if isinstance(configured, Path) else tuple(configured)

    return available_roms_directories(candidates)


def available_roms_directories(candidates: Sequence[Path]) -> tuple[Path, ...]:
    """Return every candidate that looks like a mounted, writable ROM partition."""

    # Every official image exposes some combination of system folders. Avoid a
    # short console allow-list so customized distribution images are recognized.
    available = tuple(
        candidate
        for candidate in candidates
        if candidate.is_dir()
        and (
            any(path.is_dir() for path in candidate.iterdir()) or os.access(str(candidate), os.W_OK)
        )
    )
    return available


def detect_roms_directory(
    configured: Path | Sequence[Path] | None = None,
    candidates: Sequence[Path] = DARKOS.rom_roots,
) -> Path | None:
    """Find the preferred target ROM partition for non-interactive use."""

    directories = detect_roms_directories(configured, candidates)
    return directories[0] if directories else None


def install_downloads(
    downloads: Iterable[DownloadResult],
    platform: Platform,
    roms_directory: Path,
    bios_installed: Callable[[Path], None] | None = None,
) -> list[DownloadResult]:
    """Move completed files to a platform folder without overwriting existing ROMs."""

    if platform.rom_folder is None:
        raise OrganizeError(f"{platform.name} does not have a supported ROM folder.")
    existing_folder = next(
        (folder for folder in platform.rom_folders if (roms_directory / folder).is_dir()),
        platform.rom_folder,
    )
    destination_directory = roms_directory / existing_folder
    LOGGER.debug(
        "Installing downloads platform=%s destination=%s",
        platform.alias,
        destination_directory,
    )
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OrganizeError(f"Cannot create {destination_directory}: {error}") from error

    moved: list[DownloadResult] = []
    for download in downloads:
        source = download.path
        if not source.is_file():
            raise OrganizeError(f"Completed file was not found: {source}")
        for bios_path in install_bundled_bios(source, platform, roms_directory):
            if bios_installed is not None:
                bios_installed(bios_path)
        destination = unique_destination(destination_directory / source.name)
        try:
            final_path = Path(shutil.move(str(source), str(destination)))
        except OSError as error:
            raise OrganizeError(f"Could not move {source.name}: {error}") from error
        moved.append(DownloadResult(url=download.url, path=final_path))
        LOGGER.info("Installed ROM platform=%s path=%s", platform.alias, final_path)
    return moved


def install_bundled_bios(
    archive_path: Path,
    platform: Platform,
    roms_directory: Path,
) -> tuple[Path, ...]:
    """Safely install files explicitly stored under a BIOS directory in a game ZIP."""

    if archive_path.suffix.casefold() != ".zip" or not zipfile.is_zipfile(archive_path):
        return ()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _bundled_bios_members(archive)
            installed: list[Path] = []
            for member, relative_path in members:
                for destination in _bios_destinations(relative_path, platform, roms_directory):
                    if destination.exists():
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    partial = destination.with_name(destination.name + ".part")
                    try:
                        with archive.open(member) as source, partial.open("wb") as output:
                            shutil.copyfileobj(source, output, length=1024 * 256)
                        os.replace(partial, destination)
                    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
                        partial.unlink(missing_ok=True)
                        raise OrganizeError(
                            f"Could not install bundled BIOS {relative_path}: {error}"
                        ) from error
                    installed.append(destination)
                    LOGGER.info("Installed bundled BIOS path=%s", destination)
            return tuple(installed)
    except zipfile.BadZipFile as error:
        raise OrganizeError(f"Could not inspect bundled BIOS files: {error}") from error


def _bundled_bios_members(
    archive: zipfile.ZipFile,
) -> tuple[tuple[zipfile.ZipInfo, PurePosixPath], ...]:
    selected: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    total_size = 0
    for member in archive.infolist():
        normalized = member.filename.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        bios_index = next(
            (index for index, part in enumerate(parts) if part.casefold() == "bios"),
            None,
        )
        if bios_index is None or member.is_dir():
            continue
        relative_parts = parts[bios_index + 1 :]
        if not relative_parts or any(part in {"", ".", "..", "/"} for part in relative_parts):
            raise OrganizeError(f"Unsafe bundled BIOS path: {member.filename}")
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise OrganizeError(f"Bundled BIOS cannot be a symbolic link: {member.filename}")
        if member.file_size > MAX_BIOS_FILE_SIZE:
            raise OrganizeError(f"Bundled BIOS is unexpectedly large: {member.filename}")
        total_size += member.file_size
        if len(selected) >= MAX_BIOS_FILES or total_size > MAX_BIOS_TOTAL_SIZE:
            raise OrganizeError("Bundled BIOS payload exceeds the safe extraction limit.")
        selected.append((member, PurePosixPath(*relative_parts)))
    return tuple(selected)


def _bios_destinations(
    relative_path: PurePosixPath,
    platform: Platform,
    roms_directory: Path,
) -> tuple[Path, ...]:
    folder = platform.rom_folder or ""
    filename = relative_path.name.casefold()
    local = roms_directory / folder / Path(*relative_path.parts)
    shared = roms_directory / "bios" / Path(*relative_path.parts)
    if filename in ROM_LOCAL_BIOS.get(folder, frozenset()):
        return (local,)
    if filename in ROM_AND_SHARED_BIOS.get(folder, frozenset()):
        return (shared, local)
    return (shared,)


def unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    suffixes = "".join(destination.suffixes)
    stem = destination.name[: -len(suffixes)] if suffixes else destination.name
    counter = 2
    while True:
        candidate = destination.with_name("%s (%d)%s" % (stem, counter, suffixes))
        if not candidate.exists():
            return candidate
        counter += 1
