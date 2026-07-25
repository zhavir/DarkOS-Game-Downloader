"""Offline RetroBIOS requirements, verification, and explicit firmware retrieval."""

import hashlib
import json
import logging
import os
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from time import time
from typing import Any
from urllib.parse import quote

import yaml

from dw_cli.cache_policy import DEFAULT_CATALOGUE_TTL_DAYS, catalogue_ttl_seconds
from dw_cli.models import Platform
from dw_cli.organizer import ROM_AND_SHARED_BIOS, ROM_LOCAL_BIOS

LOGGER = logging.getLogger(__name__)

RETROBIOS_REPOSITORY = "https://github.com/Abdess/retrobios"
RETROBIOS_RAW_BASE = "https://raw.githubusercontent.com/Abdess/retrobios"
MAX_FIRMWARE_BYTES = 64 * 1024 * 1024
MAX_CATALOGUE_BYTES = 16 * 1024 * 1024
RETROBIOS_CACHE_FILENAME = "catalogue.json"
RETROBIOS_API_URL = "https://api.github.com/repos/Abdess/retrobios/commits/main"

type BiosProgress = Callable[[str, int, int | None], None]
type CancellationCheck = Callable[[], bool]


class BiosError(RuntimeError):
    """A BIOS catalogue, verification, or installation operation failed."""


class BiosDownloadCancelled(BiosError):
    """The user cancelled a RetroBIOS download."""


class BiosState(StrEnum):
    """Verification state of a BIOS requirement on one ROM card."""

    VALID = "valid"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class BiosRequirement:
    """One firmware file described by the pinned RetroBIOS catalogue."""

    name: str
    destination: str
    required: bool
    size: int | None
    sha256: str | None
    sha1: str | None
    md5: str | None
    source_path: str | None
    description: str | None = None
    note: str | None = None
    region: str | None = None
    hle_fallback: bool = False


@dataclass(frozen=True, slots=True)
class BiosSystem:
    """RetroBIOS metadata relevant to one emulated system."""

    system_id: str
    name: str
    core: str | None
    docs: str | None
    requirements: tuple[BiosRequirement, ...]


@dataclass(frozen=True, slots=True)
class BiosCheck:
    """Verification result for one BIOS requirement."""

    requirement: BiosRequirement
    state: BiosState
    paths: tuple[Path, ...]


# dArkOS folder/platform identifiers differ from RetroBIOS system identifiers.
# Keep the mapping explicit so a similarly named but incompatible system is never
# selected by fuzzy matching.
RETROBIOS_SYSTEM_BY_PLATFORM: Mapping[str, str] = {
    "3do": "3do",
    "amiga": "commodore-amiga",
    "amiga-cd32": "commodore-amiga",
    "amstrad-cpc": "amstrad-cpc",
    "arcade": "arcade",
    "atari-800": "atari-400-800",
    "atari-5200": "atari-5200",
    "atari-7800": "atari-7800",
    "atari-lynx": "atari-lynx",
    "atari-st": "atari-st",
    "atomiswave": "sega-dreamcast-arcade",
    "colecovision": "coleco-colecovision",
    "commodore-128": "commodore-c128",
    "cps-1": "arcade",
    "cps-2": "arcade",
    "cps-3": "arcade",
    "dos": "dos",
    "doom": "doom",
    "dreamcast": "sega-dreamcast",
    "enterprise": "enterprise-64-128",
    "fairchild-channel-f": "fairchild-channel-f",
    "famicom-disk-system": "nintendo-fds",
    "game-boy": "nintendo-gb",
    "game-boy-advance": "nintendo-gba",
    "game-boy-color": "nintendo-gbc",
    "game-gear": "sega-game-gear",
    "genesis": "sega-mega-drive",
    "intellivision": "mattel-intellivision",
    "mame-2003": "arcade",
    "mame-2010": "arcade",
    "master-system": "sega-master-system",
    "msx": "microsoft-msx",
    "msx2": "microsoft-msx",
    "naomi": "sega-dreamcast-arcade",
    "neo-geo": "arcade",
    "neo-geo-cd": "snk-neogeo-cd",
    "nintendo-64dd": "nintendo-64dd",
    "nintendo-ds": "nintendo-ds",
    "nintendo": "nintendo-nes",
    "odyssey-2": "magnavox-odyssey2",
    "pc-98": "nec-pc-98",
    "pc-engine": "nec-pc-engine",
    "pc-engine-cd": "nec-pc-engine",
    "pc-fx": "nec-pc-fx",
    "playstation": "sony-playstation",
    "pokemon-mini": "nintendo-pokemon-mini",
    "ps-portable": "sony-psp",
    "psp-minis": "sony-psp",
    "satellaview": "nintendo-satellaview",
    "scummvm": "scummvm",
    "sega-cd": "sega-mega-cd",
    "saturn": "sega-saturn",
    "sharp-x1": "sharp-x1",
    "sharp-x68000": "sharp-x68000",
    "sufami-turbo": "nintendo-sufami-turbo",
    "super-cassette-vision": "epoch-scv",
    "super-game-boy": "nintendo-sgb",
    "super-nintendo": "nintendo-snes",
    "ti-99": "ti-83",
    "videopac": "philips-videopac",
    "videoton-tvc": "videoton-tvc",
    "vircon32": "vircon32",
    "wolfenstein": "wolfenstein-3d",
    "zx-spectrum": "sinclair-zx-spectrum",
}


class RetroBiosCatalog:
    """Read the release-pinned RetroBIOS manifest shipped with the application."""

    def __init__(
        self,
        revision: str,
        systems: Mapping[str, BiosSystem],
        generated_at: str | None = None,
        retroarch_version: str | None = None,
        fetched_at: float | None = None,
        ttl_seconds: int = catalogue_ttl_seconds(DEFAULT_CATALOGUE_TTL_DAYS),
    ) -> None:
        self.revision = revision
        self.systems = systems
        self.generated_at = generated_at
        self.retroarch_version = retroarch_version
        self.fetched_at = fetched_at
        self.ttl_seconds = ttl_seconds

    @classmethod
    def from_json(
        cls,
        content: str,
        ttl_seconds: int = catalogue_ttl_seconds(DEFAULT_CATALOGUE_TTL_DAYS),
    ) -> RetroBiosCatalog:
        """Parse a generated manifest while rejecting unsafe or malformed entries."""

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise BiosError(f"The bundled RetroBIOS catalogue is invalid: {error}") from error
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise BiosError("The bundled RetroBIOS catalogue has an unsupported format.")
        revision = payload.get("source_commit")
        raw_systems = payload.get("systems")
        if (
            not isinstance(revision, str)
            or len(revision) != 40
            or not isinstance(raw_systems, dict)
        ):
            raise BiosError("The bundled RetroBIOS catalogue is incomplete.")
        systems: dict[str, BiosSystem] = {}
        for system_id, raw_system in raw_systems.items():
            if not isinstance(system_id, str) or not isinstance(raw_system, dict):
                continue
            raw_requirements = raw_system.get("files", ())
            if not isinstance(raw_requirements, list):
                continue
            requirements = tuple(
                requirement
                for item in raw_requirements
                if (requirement := _parse_requirement(item)) is not None
            )
            systems[system_id] = BiosSystem(
                system_id=system_id,
                name=_optional_string(raw_system.get("name")) or system_id,
                core=_optional_string(raw_system.get("core")),
                docs=_optional_string(raw_system.get("docs")),
                requirements=requirements,
            )
        return cls(
            revision,
            systems,
            _optional_string(payload.get("source_generated_at")),
            _optional_string(payload.get("retroarch_version")),
            _optional_float(payload.get("fetched_at")),
            ttl_seconds,
        )

    def cache_age_seconds(self) -> float | None:
        """Return the local catalogue age when its download time is known."""

        return None if self.fetched_at is None else max(0.0, time() - self.fetched_at)

    def cache_is_stale(self) -> bool:
        """Return whether this catalogue is missing a timestamp or exceeds its lifetime."""

        age = self.cache_age_seconds()
        return age is None or age > self.ttl_seconds

    def system_for(self, platform: Platform) -> BiosSystem | None:
        """Return the exact RetroBIOS system mapped to a dArkOS platform."""

        system_id = RETROBIOS_SYSTEM_BY_PLATFORM.get(platform.slug)
        return self.systems.get(system_id) if system_id is not None else None

    def requirements_for(
        self,
        platform: Platform,
        region: str | None = None,
        *,
        required_only: bool = False,
    ) -> tuple[BiosRequirement, ...]:
        """Return requirements, narrowing region-specific mandatory alternatives."""

        system = self.system_for(platform)
        if system is None:
            return ()
        requirements = system.requirements
        if required_only:
            requirements = tuple(item for item in requirements if item.required)
        normalized_region = _normalize_region(region)
        if normalized_region is None:
            return requirements
        regional = tuple(item for item in requirements if item.required and item.region)
        matching = tuple(
            item for item in regional if _normalize_region(item.region) == normalized_region
        )
        if not matching:
            return requirements
        nonregional = tuple(item for item in requirements if not item.required or not item.region)
        return nonregional + matching

    def source_url(self, requirement: BiosRequirement) -> str | None:
        """Build the immutable raw GitHub URL for a downloadable requirement."""

        if requirement.source_path is None:
            return None
        return f"{RETROBIOS_RAW_BASE}/{self.revision}/{quote(requirement.source_path, safe='/')}"


class RetroBiosRepository:
    """Persist an atomic local catalogue downloaded only on first use or request."""

    def __init__(
        self,
        cache_directory: Path,
        timeout_seconds: float,
        ttl_seconds: int = catalogue_ttl_seconds(DEFAULT_CATALOGUE_TTL_DAYS),
    ) -> None:
        self.cache_path = cache_directory / "retrobios" / RETROBIOS_CACHE_FILENAME
        self.timeout_seconds = timeout_seconds
        self.ttl_seconds = ttl_seconds

    def load(self) -> RetroBiosCatalog | None:
        """Load the existing cache without contacting GitHub."""

        try:
            content = self.cache_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as error:
            raise BiosError(f"Could not read the RetroBIOS catalogue: {error}") from error
        return RetroBiosCatalog.from_json(content, self.ttl_seconds)

    def ensure(
        self,
        progress: BiosProgress | None = None,
        cancelled: CancellationCheck | None = None,
    ) -> RetroBiosCatalog:
        """Use the cache when present, downloading it once when missing."""

        cached = self.load()
        return cached if cached is not None else self.update(progress, cancelled)

    def update(
        self,
        progress: BiosProgress | None = None,
        cancelled: CancellationCheck | None = None,
    ) -> RetroBiosCatalog:
        """Download, validate, and atomically replace the cached catalogue."""

        if progress is not None:
            progress("Finding the latest RetroBIOS revision", 0, 1)
        api_payload = _download_json(
            RETROBIOS_API_URL,
            self.timeout_seconds,
            cancelled,
            max_bytes=1024 * 1024,
        )
        revision = api_payload.get("sha") if isinstance(api_payload, dict) else None
        if (
            not isinstance(revision, str)
            or len(revision) != 40
            or any(character not in "0123456789abcdef" for character in revision.casefold())
        ):
            raise BiosError("GitHub returned an invalid RetroBIOS revision.")

        platform_url = f"{RETROBIOS_RAW_BASE}/{revision}/platforms/retroarch.yml"
        platform = _download_yaml(platform_url, self.timeout_seconds, cancelled)
        systems = platform.get("systems")
        if not isinstance(systems, dict):
            raise BiosError("RetroBIOS returned an invalid RetroArch platform catalogue.")
        cores = sorted(
            {
                core
                for system in systems.values()
                if isinstance(system, dict)
                and isinstance((core := system.get("core")), str)
                and core
            }
        )
        total_steps = len(cores) + 2
        if progress is not None:
            progress("Downloading RetroBIOS core profiles", 1, total_steps)
        profiles: dict[str, dict[str, Any]] = {}

        def download_profile(core: str) -> tuple[str, dict[str, Any]]:
            profile_url = f"{RETROBIOS_RAW_BASE}/{revision}/emulators/{quote(core)}.yml"
            return core, _download_yaml(profile_url, self.timeout_seconds, cancelled)

        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="retrobios-metadata") as executor:
            futures = {executor.submit(download_profile, core): core for core in cores}
            for completed, future in enumerate(as_completed(futures), start=2):
                if cancelled is not None and cancelled():
                    for pending in futures:
                        pending.cancel()
                    raise BiosDownloadCancelled("RetroBIOS catalogue update cancelled.")
                core, profile = future.result()
                profiles[core] = profile
                if progress is not None:
                    progress("Downloading RetroBIOS core profiles", completed, total_steps)

        database_url = f"{RETROBIOS_RAW_BASE}/{revision}/database.json"
        database = _download_json(
            database_url,
            self.timeout_seconds,
            cancelled,
            max_bytes=MAX_CATALOGUE_BYTES,
        )
        manifest = _build_manifest(revision, platform, profiles, database)
        serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        catalogue = RetroBiosCatalog.from_json(serialized, self.ttl_seconds)
        temporary = self.cache_path.with_name(self.cache_path.name + ".tmp")
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(serialized, encoding="utf-8")
            os.replace(temporary, self.cache_path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise BiosError(f"Could not save the RetroBIOS catalogue: {error}") from error
        LOGGER.info(
            "RetroBIOS catalogue cached revision=%s systems=%d path=%s",
            revision,
            len(catalogue.systems),
            self.cache_path,
        )
        return catalogue


def _download_yaml(
    url: str,
    timeout_seconds: float,
    cancelled: CancellationCheck | None,
) -> dict[str, Any]:
    content = _download_bytes(
        url,
        timeout_seconds,
        cancelled,
        max_bytes=2 * 1024 * 1024,
    )
    try:
        payload = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise BiosError(f"RetroBIOS returned invalid YAML metadata: {error}") from error
    if not isinstance(payload, dict):
        raise BiosError("RetroBIOS returned incomplete YAML metadata.")
    return payload


def _download_json(
    url: str,
    timeout_seconds: float,
    cancelled: CancellationCheck | None,
    *,
    max_bytes: int,
) -> dict[str, Any]:
    content = _download_bytes(url, timeout_seconds, cancelled, max_bytes=max_bytes)
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BiosError(f"RetroBIOS returned invalid JSON metadata: {error}") from error
    if not isinstance(payload, dict):
        raise BiosError("RetroBIOS returned incomplete JSON metadata.")
    return payload


def _download_bytes(
    url: str,
    timeout_seconds: float,
    cancelled: CancellationCheck | None,
    *,
    max_bytes: int,
) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "darkos-downloader/retrobios",
        },
    )
    content = bytearray()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            while chunk := response.read(1024 * 128):
                if cancelled is not None and cancelled():
                    raise BiosDownloadCancelled("RetroBIOS catalogue update cancelled.")
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise BiosError("RetroBIOS metadata exceeded the safety limit.")
    except BiosError:
        raise
    except (OSError, urllib.error.URLError) as error:
        raise BiosError(f"Could not reach RetroBIOS: {error}") from error
    return bytes(content)


def _build_manifest(
    revision: str,
    platform: dict[str, Any],
    profiles: Mapping[str, dict[str, Any]],
    database: dict[str, Any],
) -> dict[str, Any]:
    systems = platform.get("systems")
    if not isinstance(systems, dict):
        raise BiosError("RetroBIOS platform metadata does not contain systems.")
    generated_systems: dict[str, Any] = {}
    for system_id, system_data in systems.items():
        if not isinstance(system_id, str) or not isinstance(system_data, dict):
            continue
        core = _optional_string(system_data.get("core"))
        profile = profiles.get(core) if core is not None else None
        profile_files = _profile_files(profile)
        generated_files: list[dict[str, Any]] = []
        raw_files = system_data.get("files", ())
        for file_data in raw_files if isinstance(raw_files, list) else ():
            if not isinstance(file_data, dict) or not isinstance(file_data.get("name"), str):
                continue
            profile_file = profile_files.get(str(file_data["name"]).casefold(), {})
            stored_file = _database_file(database, file_data) or {}
            generated_files.append(
                {
                    "name": file_data["name"],
                    "destination": file_data.get("destination", file_data["name"]),
                    "required": (
                        profile_file.get("required", False)
                        if profile is not None
                        else file_data.get("required", False)
                    ),
                    "size": file_data.get("size", stored_file.get("size")),
                    "sha256": stored_file.get("sha256"),
                    "sha1": file_data.get("sha1", stored_file.get("sha1")),
                    "md5": file_data.get("md5", stored_file.get("md5")),
                    "source_path": stored_file.get("path"),
                    "description": profile_file.get("description"),
                    "note": profile_file.get("note"),
                    "region": profile_file.get("region"),
                    "hle_fallback": profile_file.get("hle_fallback", False),
                }
            )
        generated_systems[system_id] = {
            "name": system_data.get("native_id", system_id),
            "core": core,
            "docs": system_data.get("docs"),
            "files": generated_files,
        }
    return {
        "schema_version": 1,
        "fetched_at": time(),
        "source_repository": RETROBIOS_REPOSITORY,
        "source_commit": revision,
        "source_generated_at": database.get("generated_at"),
        "retroarch_version": platform.get("version"),
        "systems": generated_systems,
    }


def _profile_files(profile: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw_files = profile.get("files", ()) if profile is not None else ()
    if not isinstance(raw_files, list):
        return {}
    return {
        str(item["name"]).casefold(): item
        for item in raw_files
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _database_file(
    database: dict[str, Any],
    file_data: dict[str, Any],
) -> dict[str, Any] | None:
    raw_files = database.get("files", {})
    if not isinstance(raw_files, dict):
        return None
    sha1 = _optional_string(file_data.get("sha1"))
    if sha1 is not None:
        candidate = raw_files.get(sha1.casefold())
        if isinstance(candidate, dict):
            return candidate
    indexes = database.get("indexes", {})
    by_name = indexes.get("by_name", {}) if isinstance(indexes, dict) else {}
    name = _optional_string(file_data.get("name"))
    keys = by_name.get(name.casefold(), ()) if isinstance(by_name, dict) and name else ()
    for key in keys if isinstance(keys, list) else ():
        candidate = raw_files.get(key)
        if not isinstance(candidate, dict):
            continue
        expected_size = file_data.get("size")
        if expected_size is None or candidate.get("size") == expected_size:
            return candidate
    return None


def audit_bios(
    requirements: Iterable[BiosRequirement],
    platform: Platform,
    roms_directory: Path,
) -> tuple[BiosCheck, ...]:
    """Verify BIOS files on the selected ROM card using pinned checksums."""

    checks: list[BiosCheck] = []
    for requirement in requirements:
        paths = bios_destinations(requirement, platform, roms_directory)
        existing = tuple(path for path in paths if path.is_file())
        validity = tuple(verify_bios_file(path, requirement) for path in existing)
        if len(existing) == len(paths) and all(validity):
            state = BiosState.VALID
        elif any(not valid for valid in validity):
            state = BiosState.INVALID
        else:
            state = BiosState.MISSING
        checks.append(BiosCheck(requirement, state, paths))
    return tuple(checks)


def audit_bios_roots(
    requirements: Iterable[BiosRequirement],
    platform: Platform,
    roms_directories: Sequence[Path],
    preferred_directory: Path,
) -> tuple[BiosCheck, ...]:
    """Treat a valid BIOS on either active memory card as already available."""

    roots = tuple(dict.fromkeys((preferred_directory, *roms_directories)))
    preferred_checks = audit_bios(requirements, platform, preferred_directory)
    checks_by_root = tuple(audit_bios(requirements, platform, root) for root in roots)
    combined: list[BiosCheck] = []
    for index, preferred in enumerate(preferred_checks):
        valid = next(
            (
                checks[index]
                for checks in checks_by_root
                if index < len(checks) and checks[index].state is BiosState.VALID
            ),
            None,
        )
        combined.append(valid or preferred)
    return tuple(combined)


def bios_destinations(
    requirement: BiosRequirement,
    platform: Platform,
    roms_directory: Path,
) -> tuple[Path, ...]:
    """Resolve shared and exceptional ROM-local dArkOS BIOS destinations."""

    relative = PurePosixPath(requirement.destination.replace("\\", "/"))
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise BiosError(f"RetroBIOS contains an unsafe destination: {requirement.destination}")
    folder = platform.arkos_folder or ""
    filename = relative.name.casefold()
    shared = roms_directory / "bios" / Path(*relative.parts)
    local = roms_directory / folder / Path(*relative.parts)
    if filename in ROM_LOCAL_BIOS.get(folder, frozenset()):
        return (local,)
    if filename in ROM_AND_SHARED_BIOS.get(folder, frozenset()):
        return (shared, local)
    return (shared,)


def verify_bios_file(path: Path, requirement: BiosRequirement) -> bool:
    """Validate size and the strongest checksum published by RetroBIOS."""

    try:
        if requirement.size is not None and path.stat().st_size != requirement.size:
            return False
        algorithm, expected = _strongest_checksum(requirement)
        if algorithm is None or expected is None:
            return requirement.size is not None
        digest = hashlib.new(algorithm)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 256):
                digest.update(chunk)
        return digest.hexdigest().casefold() == expected.casefold()
    except OSError:
        return False


def install_bios(
    catalog: RetroBiosCatalog,
    requirement: BiosRequirement,
    platform: Platform,
    roms_directory: Path,
    timeout_seconds: float,
    progress: BiosProgress | None = None,
    cancelled: CancellationCheck | None = None,
) -> tuple[Path, ...]:
    """Download one explicitly approved BIOS and atomically install verified copies."""

    url = catalog.source_url(requirement)
    if url is None:
        raise BiosError(f"RetroBIOS does not provide a downloadable copy of {requirement.name}.")
    if requirement.size is not None and requirement.size > MAX_FIRMWARE_BYTES:
        raise BiosError(f"RetroBIOS firmware is too large to install safely: {requirement.name}")
    destinations = bios_destinations(requirement, platform, roms_directory)
    valid = tuple(path for path in destinations if verify_bios_file(path, requirement))
    if len(valid) == len(destinations):
        return valid

    primary = destinations[0]
    partial = primary.with_name(primary.name + ".part")
    try:
        primary.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "darkos-downloader/retrobios"},
        )
        with (
            urllib.request.urlopen(request, timeout=timeout_seconds) as response,
            partial.open("wb") as output,
        ):
            header = response.headers.get("Content-Length")
            total = int(header) if header and header.isdigit() else requirement.size
            downloaded = 0
            while chunk := response.read(1024 * 128):
                if cancelled is not None and cancelled():
                    raise BiosDownloadCancelled("BIOS download cancelled.")
                downloaded += len(chunk)
                if downloaded > MAX_FIRMWARE_BYTES:
                    raise BiosError("RetroBIOS download exceeded the firmware safety limit.")
                output.write(chunk)
                if progress is not None:
                    progress(requirement.name, downloaded, total)
        if cancelled is not None and cancelled():
            raise BiosDownloadCancelled("BIOS download cancelled.")
        if not verify_bios_file(partial, requirement):
            raise BiosError(f"Downloaded {requirement.name} does not match the RetroBIOS checksum.")
        os.replace(partial, primary)
        installed = [primary]
        for destination in destinations[1:]:
            if verify_bios_file(destination, requirement):
                installed.append(destination)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_partial = destination.with_name(destination.name + ".part")
            try:
                shutil.copyfile(primary, copy_partial)
                os.replace(copy_partial, destination)
            except OSError:
                copy_partial.unlink(missing_ok=True)
                raise
            installed.append(destination)
        LOGGER.info(
            "Installed RetroBIOS firmware platform=%s file=%s destinations=%s",
            platform.alias,
            requirement.name,
            installed,
        )
        return tuple(installed)
    except BiosDownloadCancelled:
        partial.unlink(missing_ok=True)
        LOGGER.info("RetroBIOS download cancelled file=%s", requirement.name)
        raise
    except BiosError:
        partial.unlink(missing_ok=True)
        raise
    except (OSError, ValueError, urllib.error.URLError) as error:
        partial.unlink(missing_ok=True)
        LOGGER.error("RetroBIOS download failed file=%s: %s", requirement.name, error)
        raise BiosError(f"Could not install {requirement.name} from RetroBIOS: {error}") from error


def unresolved(checks: Sequence[BiosCheck]) -> tuple[BiosCheck, ...]:
    """Return missing or invalid BIOS checks."""

    return tuple(check for check in checks if check.state is not BiosState.VALID)


def _parse_requirement(payload: object) -> BiosRequirement | None:
    if not isinstance(payload, dict):
        return None
    name = _optional_string(payload.get("name"))
    destination = _optional_string(payload.get("destination"))
    if name is None or destination is None:
        return None
    raw_size = payload.get("size")
    size = raw_size if isinstance(raw_size, int) and not isinstance(raw_size, bool) else None
    return BiosRequirement(
        name=name,
        destination=destination,
        required=payload.get("required") is True,
        size=size,
        sha256=_optional_string(payload.get("sha256")),
        sha1=_optional_string(payload.get("sha1")),
        md5=_optional_string(payload.get("md5")),
        source_path=_optional_string(payload.get("source_path")),
        description=_optional_string(payload.get("description")),
        note=_optional_string(payload.get("note")),
        region=_optional_string(payload.get("region")),
        hle_fallback=payload.get("hle_fallback") is True,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _strongest_checksum(requirement: BiosRequirement) -> tuple[str | None, str | None]:
    if requirement.sha256:
        return "sha256", requirement.sha256
    if requirement.sha1:
        return "sha1", requirement.sha1
    if requirement.md5:
        return "md5", requirement.md5
    return None, None


def _normalize_region(region: str | None) -> str | None:
    if not region:
        return None
    normalized = region.casefold()
    if any(value in normalized for value in ("usa", "north america", "ntsc-u", "canada")):
        return "ntsc-u"
    if any(value in normalized for value in ("europe", "australia", "pal")):
        return "pal"
    if any(value in normalized for value in ("japan", "ntsc-j")):
        return "ntsc-j"
    return None
