"""Discover and safely stage self-contained Pocket Harbor release updates."""

import json
import logging
import os
import re
import shutil
import ssl
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ph.store import USER_AGENT
from ph.targets import DARKOS, LinuxTarget

LOGGER = logging.getLogger(__name__)

DEFAULT_UPDATE_API_URL = "https://api.github.com/repos/zhavir/PoketHarbor/releases/latest"
PENDING_UPDATE_DIRECTORY = DARKOS.update_staging_directory
READY_MARKER = ".ready"
MAX_RELEASE_METADATA_BYTES = 2 * 1024 * 1024
MAX_UPDATE_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_UPDATE_FILES = 25_000
_VERSION_PATTERN = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

type ProgressCallback = Callable[[str, int, int | None], None]
type CancelCallback = Callable[[], bool]


class UpdateError(RuntimeError):
    """An application update could not be checked or staged."""


class UpdateCancelled(UpdateError):
    """The user cancelled an application update."""


@dataclass(frozen=True, slots=True)
class ReleaseUpdate:
    """The exact device bundle attached to a newer GitHub release."""

    version: str
    tag: str
    asset_name: str
    asset_url: str
    asset_size: int | None


def installed_version() -> str:
    """Return the packaged application version used for update comparisons."""

    try:
        return version("pocket-harbor")
    except PackageNotFoundError:
        return "development"


def find_update(
    current_version: str,
    api_url: str = DEFAULT_UPDATE_API_URL,
    timeout_seconds: float = 30.0,
    target: LinuxTarget = DARKOS,
) -> ReleaseUpdate | None:
    """Return a newer stable device release, if GitHub publishes one."""

    current = _parse_version(current_version, "installed application version")
    LOGGER.info("Checking for an application update from version=%s", current_version)
    request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(
            request, timeout=timeout_seconds, context=ssl.create_default_context()
        ) as response:
            content_length = response.headers.get("Content-Length")
            if (
                content_length
                and content_length.isdigit()
                and int(content_length) > MAX_RELEASE_METADATA_BYTES
            ):
                raise UpdateError("GitHub returned unexpectedly large release metadata.")
            payload_bytes = response.read(MAX_RELEASE_METADATA_BYTES + 1)
    except HTTPError as error:
        LOGGER.error("GitHub release check returned status=%d", error.code)
        raise UpdateError(f"GitHub release check returned HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        LOGGER.warning("Could not check GitHub for updates: %s", reason)
        raise UpdateError(f"Could not check GitHub for updates: {reason}") from error
    if len(payload_bytes) > MAX_RELEASE_METADATA_BYTES:
        raise UpdateError("GitHub returned unexpectedly large release metadata.")
    try:
        payload = json.loads(payload_bytes)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise UpdateError("GitHub returned invalid release metadata.") from error
    if not isinstance(payload, dict):
        raise UpdateError("GitHub returned invalid release metadata.")
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateError("The latest GitHub release has no semantic version tag.")
    remote = _parse_version(tag, "latest GitHub release tag")
    if remote <= current:
        LOGGER.info("No newer application release is available")
        return None
    version = ".".join(str(part) for part in remote)
    asset_name = target.release_asset_name(version)
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("The latest GitHub release has no downloadable assets.")
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != asset_name:
            continue
        asset_url = asset.get("browser_download_url")
        asset_size = asset.get("size")
        if not isinstance(asset_url, str) or not asset_url:
            break
        if not isinstance(asset_size, int) or isinstance(asset_size, bool) or asset_size < 0:
            asset_size = None
        if asset_size is not None and asset_size > MAX_UPDATE_ARCHIVE_BYTES:
            raise UpdateError("The Pocket Harbor update bundle is unexpectedly large.")
        LOGGER.info("Application update available version=%s size=%s", version, asset_size)
        return ReleaseUpdate(version, tag, asset_name, asset_url, asset_size)
    raise UpdateError(f"The latest release does not contain {asset_name}.")


def stage_update(
    release: ReleaseUpdate,
    install_directory: Path,
    timeout_seconds: float = 30.0,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
    target: LinuxTarget = DARKOS,
) -> Path:
    """Download and validate a bundle for the launcher to install after exit."""

    install_directory = install_directory.expanduser().resolve()
    LOGGER.info("Staging application update version=%s", release.version)
    executable = install_directory / target.executable_name
    if install_directory.name != target.application_directory or not executable.is_file():
        raise UpdateError(
            f"Automatic updates require the self-contained {target.display_name} package."
        )
    tools_directory = install_directory.parent
    pending_name = target.update_staging_directory
    pending = tools_directory / pending_name
    incomplete = tools_directory / f"{pending_name}.incomplete"
    archive = tools_directory / f"{pending_name}.zip.part"
    _remove_staging_path(incomplete)
    archive.unlink(missing_ok=True)
    try:
        _raise_if_cancelled(cancelled)
        _download_release(release, archive, timeout_seconds, progress, cancelled)
        _raise_if_cancelled(cancelled)
        incomplete.mkdir(parents=False)
        _extract_bundle(archive, incomplete, cancelled, target)
        _validate_staged_bundle(incomplete, release.version, target)
        _remove_staging_path(pending)
        os.replace(incomplete, pending)
    except UpdateCancelled, UpdateError:
        _remove_staging_path(incomplete)
        LOGGER.info("Application update staging stopped")
        raise
    except OSError as error:
        _remove_staging_path(incomplete)
        LOGGER.error("Could not stage application update: %s", error)
        raise UpdateError(f"Could not stage the application update: {error}") from error
    except BaseException:
        _remove_staging_path(incomplete)
        raise
    finally:
        archive.unlink(missing_ok=True)
    LOGGER.info("Application update staged successfully version=%s", release.version)
    return pending


def _parse_version(value: str, description: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise UpdateError(f"The {description} {value!r} is not a stable semantic version.")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _download_release(
    release: ReleaseUpdate,
    destination: Path,
    timeout_seconds: float,
    progress: ProgressCallback | None,
    cancelled: CancelCallback | None,
) -> None:
    request = Request(release.asset_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(
            request, timeout=timeout_seconds, context=ssl.create_default_context()
        ) as response:
            length_header = response.headers.get("Content-Length")
            total = int(length_header) if length_header and length_header.isdigit() else None
            if total is None:
                total = release.asset_size
            if total is not None and total > MAX_UPDATE_ARCHIVE_BYTES:
                raise UpdateError("The Pocket Harbor update bundle is unexpectedly large.")
            downloaded = 0
            try:
                with destination.open("wb") as output:
                    while True:
                        _raise_if_cancelled(cancelled)
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > MAX_UPDATE_ARCHIVE_BYTES:
                            raise UpdateError(
                                "The Pocket Harbor update bundle is unexpectedly large."
                            )
                        output.write(chunk)
                        if progress is not None:
                            progress(release.asset_name, downloaded, total)
                _raise_if_cancelled(cancelled)
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
    except HTTPError as error:
        LOGGER.error("Update download returned status=%d", error.code)
        raise UpdateError(f"Update download returned HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        LOGGER.warning("Could not download application update: %s", reason)
        raise UpdateError(f"Could not download the update: {reason}") from error


def _extract_bundle(
    archive: Path,
    destination: Path,
    cancelled: CancelCallback | None,
    target: LinuxTarget = DARKOS,
) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            files = [item for item in bundle.infolist() if not item.is_dir()]
            if len(files) > MAX_UPDATE_FILES:
                raise UpdateError("The update bundle contains too many files.")
            total_size = sum(item.file_size for item in files)
            if total_size > MAX_UPDATE_ARCHIVE_BYTES:
                raise UpdateError("The expanded update bundle is unexpectedly large.")
            for item in files:
                _raise_if_cancelled(cancelled)
                relative = _safe_bundle_path(item, target)
                output_path = destination.joinpath(*relative.parts)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as source, output_path.open("wb") as output:
                    while chunk := source.read(1024 * 256):
                        _raise_if_cancelled(cancelled)
                        output.write(chunk)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as error:
        raise UpdateError(f"The downloaded update bundle is invalid: {error}") from error


def _safe_bundle_path(
    item: zipfile.ZipInfo,
    target: LinuxTarget = DARKOS,
) -> PurePosixPath:
    path = PurePosixPath(item.filename)
    mode = item.external_attr >> 16
    if (
        path.is_absolute()
        or not path.parts
        or path.parts[0] != target.tools_directory
        or len(path.parts) == 1
        or any(part in ("", ".", "..") for part in path.parts)
        or stat.S_ISLNK(mode)
    ):
        raise UpdateError(f"Unsafe path in update bundle: {item.filename!r}.")
    return PurePosixPath(*path.parts[1:])


def _validate_staged_bundle(
    destination: Path,
    version: str,
    target: LinuxTarget = DARKOS,
) -> None:
    launcher = destination / target.launcher_name
    executable = destination / target.application_directory / target.executable_name
    if not launcher.is_file() or launcher.is_symlink():
        raise UpdateError("The update bundle is missing the Pocket Harbor Tools launcher.")
    if not executable.is_file() or executable.is_symlink():
        raise UpdateError("The update bundle is missing the ARM64 application executable.")
    try:
        with executable.open("rb") as stream:
            elf_header = stream.read(20)
    except OSError as error:
        raise UpdateError(f"Could not inspect the staged executable: {error}") from error
    if (
        len(elf_header) < 20
        or elf_header[:4] != b"\x7fELF"
        or elf_header[4] != target.elf_class
        or elf_header[5] != 1
        or int.from_bytes(elf_header[18:20], "little") != target.elf_machine
    ):
        raise UpdateError(
            f"The update bundle executable is not Linux {target.architecture.upper()}."
        )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (destination / READY_MARKER).write_text(version + "\n", encoding="ascii")


def _remove_staging_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _raise_if_cancelled(cancelled: CancelCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise UpdateCancelled("Application update cancelled.")
