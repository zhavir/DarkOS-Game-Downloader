import zipfile
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from ph.models import DownloadResult, Platform
from ph.organizer import (
    OrganizeError,
    _bios_destinations,
    _bundled_bios_members,
    available_roms_directories,
    detect_roms_directories,
    detect_roms_directory,
    install_bundled_bios,
    install_downloads,
    unique_destination,
)
from ph.platforms import DARKOS_PLATFORMS, discover_platforms, resolve_platform


def test_install_downloads_uses_platform_folder_and_preserves_duplicates(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    roms = tmp_path / "roms"
    staging.mkdir()
    existing_directory = roms / "gba"
    existing_directory.mkdir(parents=True)
    existing = existing_directory / "Game.zip"
    existing.write_bytes(b"existing")
    downloaded = staging / "Game.zip"
    downloaded.write_bytes(b"new")
    platform = resolve_platform("GBA")
    assert platform is not None

    results = install_downloads(
        [DownloadResult("https://example.net/file", downloaded)], platform, roms
    )

    assert results[0].path == existing_directory / "Game (2).zip"
    assert existing.read_bytes() == b"existing"
    assert results[0].path.read_bytes() == b"new"


def test_both_memory_cards_are_detected(tmp_path: Path) -> None:
    card_one = tmp_path / "roms"
    card_two = tmp_path / "roms2"
    (card_one / "ports").mkdir(parents=True)
    (card_two / "gba").mkdir(parents=True)

    assert available_roms_directories((card_two, card_one)) == (card_two, card_one)


def test_darkos_profile_has_complete_rom_folder_set() -> None:
    folders = {folder for platform in DARKOS_PLATFORMS for folder in platform.rom_folders}

    assert len(folders) >= 90
    assert {"amiga", "arcade", "dreamcast", "nds", "pcenginecd", "psx", "zxspectrum"} <= folders


def test_existing_alternate_folder_is_used_as_destination(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    roms = tmp_path / "roms"
    staging.mkdir()
    (roms / "famicom").mkdir(parents=True)
    downloaded = staging / "Game.nes"
    downloaded.write_bytes(b"new")
    platform = resolve_platform("NES")
    assert platform is not None

    result = install_downloads(
        [DownloadResult("https://example.net/file", downloaded)], platform, roms
    )

    assert result[0].path.parent == roms / "famicom"


def test_image_specific_folder_is_discovered(tmp_path: Path) -> None:
    (tmp_path / "futureconsole").mkdir()
    (tmp_path / "bios").mkdir()

    platforms = discover_platforms([tmp_path])

    assert any(platform.rom_folder == "futureconsole" for platform in platforms)
    assert not any(
        platform.rom_folder == "bios" and platform.name.startswith("Detected")
        for platform in platforms
    )


def test_unsupported_modern_console_folders_are_not_discovered(tmp_path: Path) -> None:
    for folder in ("ps2", "PS3", "xbox", "xbox360", "switch", "wii"):
        (tmp_path / folder).mkdir()
    (tmp_path / "futureconsole").mkdir()

    platforms = discover_platforms([tmp_path])
    detected = {
        platform.rom_folder for platform in platforms if platform.name.startswith("Detected")
    }

    assert detected == {"futureconsole"}


def test_game_zip_installs_explicit_bios_tree_and_keeps_game_archive(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    roms = tmp_path / "roms"
    staging.mkdir()
    (roms / "gba").mkdir(parents=True)
    archive = staging / "Game.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("Game.gba", b"game")
        package.writestr("bundle/BIOS/gba_bios.bin", b"bios")
    platform = resolve_platform("GBA")
    assert platform is not None
    bios_files: list[Path] = []

    result = install_downloads(
        [DownloadResult("https://example.net/game", archive)],
        platform,
        roms,
        bios_files.append,
    )

    assert result[0].path == roms / "gba" / "Game.zip"
    assert result[0].path.is_file()
    assert bios_files == [roms / "bios" / "gba_bios.bin"]
    assert bios_files[0].read_bytes() == b"bios"


def test_neogeo_bios_is_installed_shared_and_beside_roms(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    roms = tmp_path / "roms"
    staging.mkdir()
    archive = staging / "Metal Slug.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("game.bin", b"game")
        package.writestr("bios/neogeo.zip", b"bios archive")
    platform = resolve_platform("NEOGEO")
    assert platform is not None

    install_downloads([DownloadResult("https://example.net/game", archive)], platform, roms)

    assert (roms / "bios" / "neogeo.zip").read_bytes() == b"bios archive"
    assert (roms / "neogeo" / "neogeo.zip").read_bytes() == b"bios archive"


def test_existing_bios_is_never_overwritten(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    roms = tmp_path / "roms"
    staging.mkdir()
    (roms / "bios").mkdir(parents=True)
    existing = roms / "bios" / "gba_bios.bin"
    existing.write_bytes(b"keep-me")
    archive = staging / "Game.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("bios/gba_bios.bin", b"replacement")
    platform = resolve_platform("GBA")
    assert platform is not None

    install_downloads([DownloadResult("https://example.net/game", archive)], platform, roms)

    assert existing.read_bytes() == b"keep-me"


def test_unsafe_bios_archive_path_is_rejected_before_game_move(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    roms = tmp_path / "roms"
    staging.mkdir()
    archive = staging / "Game.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("bios/../../escape.bin", b"unsafe")
    platform = resolve_platform("GBA")
    assert platform is not None

    with pytest.raises(OrganizeError, match="Unsafe bundled BIOS path"):
        install_downloads([DownloadResult("https://example.net/game", archive)], platform, roms)

    assert archive.is_file()
    assert not (tmp_path / "escape.bin").exists()


def test_configured_rom_roots_and_preferred_root_are_preserved(tmp_path: Path) -> None:
    roots = (tmp_path / "sd2", tmp_path / "sd1")

    assert detect_roms_directories(roots) == roots
    assert detect_roms_directories(roots[0]) == (roots[0],)
    assert detect_roms_directory(roots) == roots[0]
    assert detect_roms_directory(()) is None


def test_move_reports_unsupported_platform_missing_file_and_invalid_root(tmp_path: Path) -> None:
    unsupported = Platform("Unsupported", "unsupported", "", "NONE", None)
    with pytest.raises(OrganizeError, match="does not have"):
        install_downloads([], unsupported, tmp_path)

    gba = resolve_platform("GBA")
    assert gba is not None
    with pytest.raises(OrganizeError, match="not found"):
        install_downloads([DownloadResult("url", tmp_path / "missing.zip")], gba, tmp_path)

    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory", encoding="utf-8")
    with pytest.raises(OrganizeError, match="Cannot create"):
        install_downloads([], gba, occupied)


def test_non_zip_has_no_bundled_bios_and_advision_bios_is_rom_local(tmp_path: Path) -> None:
    advision = resolve_platform("advision")
    assert advision is not None
    assert install_bundled_bios(tmp_path / "game.bin", advision, tmp_path) == ()
    destinations = _bios_destinations(PurePosixPath("advision.zip"), advision, tmp_path)
    assert destinations == (tmp_path / "advision" / "advision.zip",)
    mapped_advision = replace(advision, rom_folder="custom-advision", alternate_folders=())
    assert _bios_destinations(PurePosixPath("advision.zip"), mapped_advision, tmp_path) == (
        tmp_path / "custom-advision" / "advision.zip",
    )
    gba = resolve_platform("GBA")
    assert gba is not None
    assert _bios_destinations(PurePosixPath("gba_bios.bin"), gba, tmp_path, "firmware") == (
        tmp_path / "firmware" / "gba_bios.bin",
    )


def test_bios_member_validation_rejects_links_and_oversized_payload(tmp_path: Path) -> None:
    archive_path = tmp_path / "bios.zip"
    link = zipfile.ZipInfo("bios/link.bin")
    link.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, b"target")
    with (
        zipfile.ZipFile(archive_path) as archive,
        pytest.raises(OrganizeError, match="symbolic link"),
    ):
        _bundled_bios_members(archive)


def test_unique_destination_handles_multiple_suffixes_and_no_suffix(tmp_path: Path) -> None:
    archive = tmp_path / "game.tar.gz"
    archive.write_bytes(b"one")
    (tmp_path / "game (2).tar.gz").write_bytes(b"two")
    assert unique_destination(archive).name == "game (3).tar.gz"
    plain = tmp_path / "README"
    plain.write_text("one")
    assert unique_destination(plain).name == "README (2)"
