from dataclasses import replace
from pathlib import Path

import pytest

from ph.config import Config
from ph.platforms import DARKOS_PLATFORMS, platform_catalogue, resolve_platform
from ph.targets import DARKOS, TargetError, resolve_target


def test_darkos_is_the_only_registered_and_hardware_tested_target() -> None:
    assert resolve_target(" DarkOS ") is DARKOS
    assert DARKOS.tested is True
    assert (DARKOS.elf_class, DARKOS.elf_machine) == (2, 183)
    assert DARKOS.rom_roots == (Path("/roms2"), Path("/roms"))
    assert DARKOS.release_asset_name("2.3.4") == "pocket-harbor-2.3.4-darkos-arm64.zip"


def test_unknown_linux_target_fails_with_the_available_profiles() -> None:
    with pytest.raises(TargetError, match="available targets: darkos"):
        resolve_target("future-os")


def test_environment_selects_the_target_and_defaults_to_darkos() -> None:
    assert Config.from_environment({}).target is DARKOS
    assert Config.from_environment({"PH_TARGET_OS": "DARKOS"}).target is DARKOS

    with pytest.raises(TargetError, match="future-os"):
        Config.from_environment({"PH_TARGET_OS": "future-os"})


def test_target_selects_its_platform_catalogue() -> None:
    assert platform_catalogue(DARKOS) is DARKOS_PLATFORMS
    assert resolve_platform("snes", platform_catalogue(DARKOS)) is not None

    unsupported = replace(DARKOS, target_id="future", platform_profile="future")
    with pytest.raises(ValueError, match="No platform catalogue"):
        platform_catalogue(unsupported)
