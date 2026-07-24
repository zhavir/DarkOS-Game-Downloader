from pathlib import Path

import pytest

from dw_cli.library import (
    LibraryError,
    delete_game,
    platforms_with_installed_games,
    replace_game,
    scan_library,
    search_title,
)
from dw_cli.models import DownloadResult
from dw_cli.platforms import PLATFORMS, resolve_platform


def test_scan_library_groups_cue_members(tmp_path: Path) -> None:
    psx = tmp_path / "psx"
    psx.mkdir()
    cue = psx / "Example Game (USA).cue"
    track = psx / "Example Game (Track 1).bin"
    cue.write_text('FILE "Example Game (Track 1).bin" BINARY\n', encoding="utf-8")
    track.write_bytes(b"track")

    games = scan_library([tmp_path], PLATFORMS)

    assert len(games) == 1
    assert games[0].primary_file == cue
    assert set(games[0].files) == {cue, track}
    assert games[0].title == "Example Game"


def test_delete_game_removes_grouped_files(tmp_path: Path) -> None:
    psx = tmp_path / "psx"
    psx.mkdir()
    cue = psx / "Game.cue"
    track = psx / "Game.bin"
    cue.write_text('FILE "Game.bin" BINARY\n', encoding="utf-8")
    track.write_bytes(b"old")
    game = scan_library([tmp_path], PLATFORMS)[0]

    delete_game(game)

    assert not cue.exists()
    assert not track.exists()


def test_replace_game_keeps_old_file_until_replacement_exists(tmp_path: Path) -> None:
    gba = tmp_path / "gba"
    staging = tmp_path / "staging"
    gba.mkdir()
    staging.mkdir()
    old = gba / "Game (USA).zip"
    old.write_bytes(b"old")
    replacement = staging / "Game (Rev 1).zip"
    replacement.write_bytes(b"new")
    game = scan_library([tmp_path], PLATFORMS)[0]

    result = replace_game(game, DownloadResult("https://example.net/file", replacement))

    assert result.path.parent == gba
    assert result.path.read_bytes() == b"new"
    assert not old.exists()


def test_search_title_removes_release_tags() -> None:
    assert search_title(Path("Advance_Wars_(USA)_[!].zip")) == "Advance Wars"


def test_failed_update_keeps_existing_game(tmp_path: Path) -> None:
    gba = tmp_path / "gba"
    gba.mkdir()
    old = gba / "Game.zip"
    old.write_bytes(b"old")
    game = scan_library([tmp_path], PLATFORMS)[0]

    with pytest.raises(LibraryError):
        replace_game(game, DownloadResult("https://example.net/file", tmp_path / "missing.zip"))

    assert old.read_bytes() == b"old"


def test_playstation_aliases_are_not_overwritten() -> None:
    ps1 = resolve_platform("PS1")
    psp = resolve_platform("PSP")
    assert ps1 is not None
    assert psp is not None
    assert ps1.code == "PS1"
    assert psp.code == "PSP"


def test_platform_navigation_hides_empty_folders_and_prunes_media(tmp_path: Path) -> None:
    (tmp_path / "nes").mkdir()
    (tmp_path / "gba" / "images" / "covers").mkdir(parents=True)
    (tmp_path / "gba" / "images" / "covers" / "not-a-rom.zip").write_bytes(b"image")
    (tmp_path / "gba" / "Game.zip").write_bytes(b"game")

    platforms = platforms_with_installed_games(tmp_path, PLATFORMS)
    games = scan_library((tmp_path,), platforms)

    assert [platform.alias for platform in platforms] == ["GBA"]
    assert [game.title for game in games] == ["Game"]
