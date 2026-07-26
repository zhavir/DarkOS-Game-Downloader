"""Linux distribution targets supported by the portable application core."""

from dataclasses import dataclass
from pathlib import Path

type TargetId = str
type CpuArchitecture = str


class TargetError(ValueError):
    """A requested operating-system target is not registered."""


@dataclass(frozen=True, slots=True)
class LinuxTarget:
    """OS integration points kept outside store and library workflows."""

    target_id: TargetId
    display_name: str
    tested: bool
    architecture: CpuArchitecture
    elf_class: int
    elf_machine: int
    rom_roots: tuple[Path, ...]
    tools_directory: str
    launcher_name: str
    application_directory: str
    executable_name: str
    update_staging_directory: str
    refresh_marker_environment: str
    platform_profile: str

    def release_asset_name(self, version: str) -> str:
        """Return the exact self-contained bundle name for this target."""

        return f"pocket-harbor-{version}-{self.target_id}-{self.architecture}.zip"


DARKOS = LinuxTarget(
    target_id="darkos",
    display_name="DarkOS",
    tested=True,
    architecture="arm64",
    elf_class=2,
    elf_machine=183,
    rom_roots=(Path("/roms2"), Path("/roms")),
    tools_directory="tools",
    launcher_name="Pocket Harbor.sh",
    application_directory="pocket-harbor",
    executable_name="pocket-harbor",
    update_staging_directory=".pocket-harbor-update",
    refresh_marker_environment="PH_ES_REFRESH_FILE",
    platform_profile="darkos",
)

TARGETS: tuple[LinuxTarget, ...] = (DARKOS,)


def resolve_target(value: str) -> LinuxTarget:
    """Resolve a configured target and fail clearly for unimplemented distributions."""

    normalized = value.strip().casefold()
    target = next((item for item in TARGETS if item.target_id == normalized), None)
    if target is None:
        supported = ", ".join(item.target_id for item in TARGETS)
        raise TargetError(f"Unknown Linux target {value!r}; available targets: {supported}.")
    return target
