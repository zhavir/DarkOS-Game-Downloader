from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ph.library import (
    LibraryError,
    _is_game_candidate,
    _referenced_files,
    delete_game,
    platforms_with_installed_games,
    replace_game,
    scan_library,
    search_title,
)
from ph.models import DownloadResult, InstalledGame
from ph.platforms import DARKOS_PLATFORMS, resolve_platform


def test_scan_library_groups_cue_members(tmp_path: Path) -> None:
    psx = tmp_path / "psx"
    psx.mkdir()
    cue = psx / "Example Game (USA).cue"
    track = psx / "Example Game (Track 1).bin"
    cue.write_text('FILE "Example Game (Track 1).bin" BINARY\n', encoding="utf-8")
    track.write_bytes(b"track")

    games = scan_library([tmp_path], DARKOS_PLATFORMS)

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
    game = scan_library([tmp_path], DARKOS_PLATFORMS)[0]

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
    game = scan_library([tmp_path], DARKOS_PLATFORMS)[0]

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
    game = scan_library([tmp_path], DARKOS_PLATFORMS)[0]

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

    platforms = platforms_with_installed_games(tmp_path, DARKOS_PLATFORMS)
    games = scan_library((tmp_path,), platforms)

    assert [platform.alias for platform in platforms] == ["GBA"]
    assert [game.title for game in games] == ["Game"]


def test_m3u_groups_nested_playlists_and_ignores_unsafe_members(tmp_path: Path) -> None:
    psx = tmp_path / "psx"
    psx.mkdir()
    disc = psx / "Disc 1.chd"
    disc.write_bytes(b"disc")
    cue = psx / "Disc 2.cue"
    track = psx / "Disc 2.bin"
    track.write_bytes(b"track")
    cue.write_text('FILE "Disc 2.bin" BINARY\n', encoding="utf-8")
    playlist = psx / "Game.m3u"
    playlist.write_text(
        "# grouped game\nDisc 1.chd\nDisc 2.cue\n../outside.zip\n", encoding="utf-8"
    )
    (tmp_path / "outside.zip").write_bytes(b"outside")

    game = scan_library((tmp_path,), DARKOS_PLATFORMS)[0]

    assert game.primary_file == playlist.resolve()
    assert set(game.files) == {playlist.resolve(), disc.resolve(), cue.resolve(), track.resolve()}


def test_playlist_read_failure_and_candidate_filters(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    playlist = tmp_path / "game.m3u"
    playlist.write_text("game.zip", encoding="utf-8")
    mocker.patch.object(Path, "read_text", side_effect=OSError("unreadable"))
    assert _referenced_files(playlist) == ()

    hidden = tmp_path / ".hidden.zip"
    hidden.write_bytes(b"game")
    image = tmp_path / "images" / "game.zip"
    image.parent.mkdir()
    image.write_bytes(b"image")
    metadata = tmp_path / "game.json"
    metadata.write_text("{}")
    assert not _is_game_candidate(hidden)
    assert not _is_game_candidate(image)
    assert not _is_game_candidate(metadata)
    assert not _is_game_candidate(tmp_path / "missing.zip")


def test_delete_game_ignores_missing_files_and_reports_other_failures(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    missing = tmp_path / "missing.zip"
    locked = tmp_path / "locked.zip"
    locked.write_bytes(b"game")
    installed = InstalledGame("Game", gba, tmp_path, locked, (missing, locked))
    original_unlink = Path.unlink

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if path == locked:
            raise OSError("read only")
        original_unlink(path, missing_ok=missing_ok)

    mocker.patch.object(Path, "unlink", unlink)
    with pytest.raises(LibraryError, match="read only"):
        delete_game(installed)


def test_replace_game_falls_back_to_move_and_reports_cleanup_failure(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    folder = tmp_path / "gba"
    folder.mkdir()
    old = folder / "old.zip"
    old.write_bytes(b"old")
    source = tmp_path / "new.zip"
    source.write_bytes(b"new")
    game = scan_library((tmp_path,), (gba,))[0]
    mocker.patch.object(Path, "replace", side_effect=OSError("cross-device"))
    moved = mocker.patch("shutil.move", return_value=str(folder / "new.zip"))

    result = replace_game(game, DownloadResult("url", source))

    assert result.path == folder / "new.zip"
    moved.assert_called_once()

    source.write_bytes(b"new")
    moved.side_effect = OSError("disk full")
    with pytest.raises(Exception, match="disk full"):
        replace_game(game, DownloadResult("url", source))


def test_replace_game_reports_old_files_that_cannot_be_removed(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    folder = tmp_path / "gba"
    folder.mkdir()
    old = folder / "old.zip"
    old.write_bytes(b"old")
    source = tmp_path / "new.zip"
    source.write_bytes(b"new")
    game = scan_library((tmp_path,), (gba,))[0]
    original_unlink = Path.unlink

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if path == old:
            raise OSError("locked")
        original_unlink(path, missing_ok=missing_ok)

    mocker.patch.object(Path, "unlink", unlink)
    with pytest.raises(LibraryError, match="old files remain"):
        replace_game(game, DownloadResult("url", source))
