import curses
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pytest_mock import MockerFixture

from dw_cli.bittorrent import BitTorrentSettings
from dw_cli.compatibility import CompatibilityInfo
from dw_cli.downloader import DownloadCancelled
from dw_cli.gamepad import InputAction
from dw_cli.models import DownloadResult, InstalledGame, MediaDownload, SearchResult
from dw_cli.platforms import resolve_platform
from dw_cli.preferences import Preferences, load_preferences
from dw_cli.store_catalog import StoreCatalog
from dw_cli.tui import (
    GAMEPAD_KEYS,
    GAMEPAD_NOOP_KEY,
    GAMEPAD_SEARCH_KEY,
    KEYBOARD_GAMEPAD_KEYS,
    DownloaderTui,
)
from dw_cli.updater import ReleaseUpdate
from dw_cli.vimm_store import VimmStore


class FakeScreen:
    def getmaxyx(self) -> tuple[int, int]:
        return (20, 80)

    def erase(self) -> None:
        pass

    def refresh(self) -> None:
        pass


def keyboard_with_inputs(
    mocker: MockerFixture,
    inputs: tuple[int, ...],
) -> DownloaderTui:
    tui = object.__new__(DownloaderTui)
    tui.screen = FakeScreen()
    tui.gamepad = None
    mocker.patch.object(tui, "_header", new=lambda _title: None)
    mocker.patch.object(tui, "_footer", new=lambda _text: None)
    mocker.patch.object(tui, "_safe_add", new=lambda *_args, **_kwargs: None)
    pending: Iterator[int] = iter(inputs)
    mocker.patch.object(tui, "_get_input", new=lambda *_args: next(pending))
    mocker.patch.object(curses, "color_pair", lambda _number: 0)
    return tui


def test_x_submits_empty_search(mocker: MockerFixture) -> None:
    tui = keyboard_with_inputs(mocker, (GAMEPAD_SEARCH_KEY,))

    assert tui._on_screen_keyboard("SEARCH") == ""


def test_x_submits_current_search_and_start_is_ignored(mocker: MockerFixture) -> None:
    tui = keyboard_with_inputs(
        mocker,
        (ord("a"), GAMEPAD_NOOP_KEY, ord("D"), ord("v"), GAMEPAD_SEARCH_KEY),
    )

    assert tui._on_screen_keyboard("SEARCH") == "aDv"


def test_gamepad_mapping_is_context_aware_for_keyboard_navigation() -> None:
    assert GAMEPAD_KEYS[InputAction.LEFT] == 27
    assert GAMEPAD_KEYS[InputAction.RIGHT] == 10
    assert KEYBOARD_GAMEPAD_KEYS[InputAction.LEFT] == curses.KEY_LEFT
    assert KEYBOARD_GAMEPAD_KEYS[InputAction.RIGHT] == curses.KEY_RIGHT
    assert KEYBOARD_GAMEPAD_KEYS[InputAction.SUBMIT_SEARCH] == GAMEPAD_SEARCH_KEY
    assert KEYBOARD_GAMEPAD_KEYS[InputAction.START] == GAMEPAD_NOOP_KEY


def test_keyboard_dpad_right_moves_to_next_key(mocker: MockerFixture) -> None:
    tui = keyboard_with_inputs(
        mocker,
        (curses.KEY_RIGHT, 10, GAMEPAD_SEARCH_KEY),
    )

    assert tui._on_screen_keyboard("SEARCH") == "2"


def test_store_picker_returns_registered_store(mocker: MockerFixture) -> None:
    tui = object.__new__(DownloaderTui)
    store = VimmStore("https://example.test")
    tui.store_catalog = StoreCatalog((store,))
    mocker.patch.object(tui, "_menu", new=lambda _title, _options, _footer: 0)

    assert tui._choose_store("CHOOSE A STORE") is store


def test_search_flow_uses_persisted_store_without_prompt(mocker: MockerFixture) -> None:
    tui = object.__new__(DownloaderTui)
    store = VimmStore("https://example.test")
    platform = resolve_platform("GBA")
    assert platform is not None
    result = SearchResult("Advance Wars", "https://example.test/vault/1")
    calls: list[tuple[str, str]] = []
    mocker.patch.object(
        store,
        "search",
        lambda system, query, _progress: calls.append((system, query)) or [result],
    )
    tui.store_catalog = StoreCatalog((store,))
    tui.selected_store = store
    tui.platforms = (platform,)
    choices = iter((0,))
    mocker.patch.object(tui, "_menu", new=lambda _title, _options, _footer: next(choices))
    mocker.patch.object(tui, "_on_screen_keyboard", new=lambda *_args, **_kwargs: "ADV")
    mocker.patch.object(tui, "_draw_message", new=lambda *_args, **_kwargs: None)
    tui.compatibility_client = SimpleNamespace(
        lookup_many=lambda _results, _platform: [CompatibilityInfo("Perfect", True)]
    )
    selected: list[object] = []
    mocker.patch.object(tui, "_results_flow", new=lambda *args: selected.extend(args))

    tui._search_flow()

    assert calls == [(platform.code, "ADV")]
    assert selected[-1] is store


def test_update_uses_persisted_store_without_prompt(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    tui = object.__new__(DownloaderTui)
    store = VimmStore("https://example.test")
    platform = resolve_platform("GBA")
    assert platform is not None
    game_path = tmp_path / "gba" / "Advance Wars.zip"
    game = InstalledGame("Advance Wars", platform, tmp_path, game_path, (game_path,))
    calls: list[tuple[str, str]] = []
    mocker.patch.object(
        store,
        "search",
        lambda system, query: (
            calls.append((system, query))
            or [SearchResult("Advance Wars", "https://example.test/vault/1")]
        ),
    )
    tui.selected_store = store
    mocker.patch.object(tui, "_draw_message", new=lambda *_args, **_kwargs: None)
    mocker.patch.object(tui, "_menu", new=lambda _title, _options, _footer: None)

    assert tui._update_game(game) is False
    assert calls == [(platform.code, game.title)]


def test_configure_store_persists_selection(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    tui = object.__new__(DownloaderTui)
    store = VimmStore("https://example.test")
    tui.store_catalog = StoreCatalog((store,))
    tui.preferences_path = tmp_path / ".downloads" / "settings.json"
    tui.selected_store = None
    mocker.patch.object(tui, "_menu", new=lambda _title, _options, _footer: 0)
    mocker.patch.object(tui, "_draw_message", new=lambda *_args, **_kwargs: None)
    mocker.patch.object(tui, "_error", new=lambda _message: None)

    assert tui._configure_store(first_run=True) is True
    assert tui.selected_store is store
    assert load_preferences(tui.preferences_path) == Preferences("vimm")


def test_minerva_settings_menu_edits_and_persists_value(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    tui = object.__new__(DownloaderTui)
    tui.preferences_path = tmp_path / ".downloads" / "settings.json"
    tui.preferences = Preferences("minerva")
    choices = iter((1, None))
    shown_options: list[tuple[str, ...]] = []

    def menu(_title: str, options: tuple[str, ...], _footer: str) -> int | None:
        shown_options.append(tuple(options))
        return next(choices)

    mocker.patch.object(tui, "_menu", new=menu)
    mocker.patch.object(tui, "_on_screen_keyboard", new=lambda *_args, **_kwargs: "32768")
    mocker.patch.object(tui, "_draw_message", new=lambda *_args, **_kwargs: None)
    mocker.patch.object(tui, "_error", new=lambda message: pytest.fail(message))

    tui._minerva_bittorrent_settings_screen()

    expected = BitTorrentSettings(block_size=32768)
    assert tui.preferences == Preferences("minerva", expected)
    assert load_preferences(tui.preferences_path) == Preferences("minerva", expected)
    labels = " ".join(shown_options[0])
    assert all(
        label in labels
        for label in (
            "UDP protocol ID",
            "Block size",
            "Max torrent metadata",
            "Max tracker response",
            "Max peer attempts",
            "Peer race workers",
            "Max peer timeout",
            "Max tracker queries",
            "Max discovered peers",
        )
    )


def test_minerva_advanced_settings_only_appear_for_minerva(
    mocker: MockerFixture,
) -> None:
    tui = object.__new__(DownloaderTui)
    shown_options: list[tuple[str, ...]] = []
    mocker.patch.object(
        tui,
        "_menu",
        new=lambda _title, options, _footer: shown_options.append(tuple(options)) or None,
    )
    tui.selected_store = VimmStore("https://example.test")

    tui._settings_screen()

    assert not any("Minerva BitTorrent" in option for option in shown_options[-1])
    tui.selected_store = SimpleNamespace(store_id="minerva", display_name="Minerva Archive")

    tui._settings_screen()

    assert any("Minerva BitTorrent" in option for option in shown_options[-1])


def test_exit_requires_explicit_yes(mocker: MockerFixture) -> None:
    tui = object.__new__(DownloaderTui)
    choices = iter((None, 0, 1))
    mocker.patch.object(tui, "_menu", new=lambda _title, _options, _footer: next(choices))

    assert tui._confirm_exit() is False
    assert tui._confirm_exit() is False
    assert tui._confirm_exit() is True


def test_application_update_is_staged_and_closes_tui(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    install_directory = tmp_path / "tools" / "darkos-downloader"
    release = ReleaseUpdate(
        "1.2.0",
        "v1.2.0",
        "darkos-downloader-1.2.0-r36s-arm64.zip",
        "https://example.test/update.zip",
        100,
    )
    tui = object.__new__(DownloaderTui)
    tui.config = SimpleNamespace(
        install_directory=install_directory,
        update_api_url="https://api.example.test/releases/latest",
        timeout_seconds=1.0,
    )
    tui.exit_after_update = False
    mocker.patch.object(tui, "_draw_message", new=lambda *_args, **_kwargs: None)
    mocker.patch.object(tui, "_error", new=lambda message: pytest.fail(message))
    mocker.patch.object(tui, "_menu", new=lambda *_args: 0)
    staged: list[tuple[ReleaseUpdate, Path]] = []
    mocker.patch.object(
        tui,
        "_stage_application_update",
        new=lambda update, directory: staged.append((update, directory)) or directory.parent,
    )
    mocker.patch("dw_cli.tui.installed_version", lambda: "1.0.1")
    mocker.patch("dw_cli.tui.find_update", lambda *_args: release)

    tui._application_update_flow()

    assert staged == [(release, install_directory)]
    assert tui.exit_after_update is True


def test_back_cancels_active_download(mocker: MockerFixture, tmp_path: Path) -> None:
    cancellation_seen = False

    def fake_download_files(*args: object, **_kwargs: object) -> list[object]:
        nonlocal cancellation_seen
        is_cancelled = cast(Callable[[], bool], args[-1])
        while not is_cancelled():
            time.sleep(0.001)
        cancellation_seen = True
        raise DownloadCancelled("Download cancelled.")

    tui = object.__new__(DownloaderTui)
    tui.config = SimpleNamespace(download_directory=tmp_path, timeout_seconds=1.0)
    mocker.patch.object(tui, "_poll_input", new=lambda: 27)
    mocker.patch.object(tui, "_progress", new=lambda *_args: None)
    mocker.patch.object(tui, "_draw_message", new=lambda *_args, **_kwargs: None)
    mocker.patch("dw_cli.tui.download_files", fake_download_files)

    with pytest.raises(DownloadCancelled):
        tui._download_media(["https://example.test/game.zip"], VimmStore("https://example.test"))

    assert cancellation_seen is True


def test_minerva_download_uses_persisted_bittorrent_settings(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    settings = BitTorrentSettings(block_size=32 * 1024, max_peer_attempts=100)
    tui = object.__new__(DownloaderTui)
    tui.config = SimpleNamespace(download_directory=tmp_path, timeout_seconds=1.0)
    tui.preferences = Preferences("minerva", settings)
    mocker.patch.object(tui, "_poll_input", new=lambda: None)
    mocker.patch.object(tui, "_progress", new=lambda *_args: None)
    captured: list[BitTorrentSettings | None] = []

    def fake_download_files(*_args: object, **kwargs: object) -> list[DownloadResult]:
        value = kwargs.get("bittorrent_settings")
        assert value is None or isinstance(value, BitTorrentSettings)
        captured.append(value)
        return []

    mocker.patch("dw_cli.tui.download_files", fake_download_files)
    store = SimpleNamespace(store_id="minerva", download_referrer="https://example.test/")

    assert tui._download_media([], store) == []  # type: ignore[arg-type]
    assert captured == [settings]


def test_completed_download_defers_refresh_until_tui_exit(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    downloaded = tmp_path / "download" / "Advance Wars.zip"
    downloaded.parent.mkdir()
    downloaded.write_bytes(b"game")
    store = VimmStore("https://example.test")
    tui = object.__new__(DownloaderTui)
    tui.refresh_on_exit = False
    mocker.patch.object(tui, "_choose_roms_directory", new=lambda: tmp_path / "roms")
    mocker.patch.object(
        tui,
        "_download_media",
        new=lambda *_args: [DownloadResult("https://example.test/game.zip", downloaded)],
    )
    messages: list[str] = []
    mocker.patch.object(
        tui,
        "_draw_message",
        new=lambda _title, message, *_args, **_kwargs: messages.append(message),
    )
    mocker.patch.object(
        store,
        "download_request",
        lambda _url: MediaDownload("https://example.test/game.zip"),
    )
    refresh_requests: list[bool] = []
    mocker.patch(
        "dw_cli.tui.request_emulationstation_refresh",
        lambda: refresh_requests.append(True) or True,
    )

    tui._download_detail("https://example.test/game", platform, store)

    assert (tmp_path / "roms" / "gba" / "Advance Wars.zip").is_file()
    assert tui.refresh_on_exit is True
    assert refresh_requests == []
    assert "refresh when you exit" in messages[-1]


def test_pending_refresh_is_requested_when_tui_exits(mocker: MockerFixture) -> None:
    tui = object.__new__(DownloaderTui)
    tui.store_catalog = SimpleNamespace(stores=(object(),))
    tui.selected_store = object()
    tui.refresh_on_exit = True
    tui.exit_after_update = False
    tui.gamepad = None
    choices = iter((5, 1))
    mocker.patch.object(tui, "_menu", new=lambda *_args: next(choices))
    refresh_requests: list[bool] = []
    mocker.patch(
        "dw_cli.tui.request_emulationstation_refresh",
        lambda: refresh_requests.append(True) or True,
    )

    tui.run()

    assert refresh_requests == [True]


def test_delete_defers_refresh_until_tui_exit(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    game_path = tmp_path / "gba" / "Advance Wars.zip"
    game = InstalledGame("Advance Wars", platform, tmp_path, game_path, (game_path,))
    tui = object.__new__(DownloaderTui)
    tui.refresh_on_exit = False
    mocker.patch.object(tui, "_menu", new=lambda _title, _options, _footer: 1)
    mocker.patch.object(tui, "_draw_message", new=lambda *_args, **_kwargs: None)
    mocker.patch("dw_cli.tui.delete_game", lambda _game: None)
    refresh_requests: list[bool] = []
    mocker.patch(
        "dw_cli.tui.request_emulationstation_refresh",
        lambda: refresh_requests.append(True) or True,
    )

    assert tui._confirm_delete(game) is True
    assert tui.refresh_on_exit is True
    assert refresh_requests == []
