from pathlib import Path

import pytest

from ph.platforms import resolve_platform
from ph.retrobios import RetroBiosRepository, install_bios, verify_bios_file


@pytest.mark.e2e
@pytest.mark.live
def test_real_retrobios_catalogue_and_gba_bios_download(tmp_path: Path) -> None:
    """Exercise the real metadata API, raw catalogue, firmware endpoint, and checksum."""

    repository = RetroBiosRepository(tmp_path / "cache", 30)
    catalog = repository.update()
    gba = resolve_platform("GBA")
    assert gba is not None
    requirement = next(
        item for item in catalog.requirements_for(gba) if item.name.casefold() == "gba_bios.bin"
    )

    installed = install_bios(catalog, requirement, gba, tmp_path / "roms", 30)

    assert installed == (tmp_path / "roms" / "bios" / "gba_bios.bin",)
    assert verify_bios_file(installed[0], requirement)
