import curses
import locale
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from pytest_mock import MockerFixture

from dw_cli import tui as tui_module
from dw_cli.bittorrent import BitTorrentSettings
from dw_cli.compatibility import CompatibilityInfo
from dw_cli.config import Config
from dw_cli.downloader import DownloadCancelled, DownloadError
from dw_cli.gamepad import InputAction, LinuxJoystick
from dw_cli.hardware import DeviceTreeInput, DeviceTreeKey, HardwareProfile
from dw_cli.library import LibraryError
from dw_cli.models import DownloadResult, InstalledGame, MediaDownload, Platform, SearchResult
from dw_cli.organizer import OrganizeError
from dw_cli.platforms import resolve_platform
from dw_cli.preferences import Preferences, PreferencesError
from dw_cli.store import CatalogProgress, GameStore, StoreError
from dw_cli.store_catalog import StoreCatalog
from dw_cli.tui import (
    GAMEPAD_SEARCH_KEY,
    DownloaderTui,
    TerminalTooSmall,
)
from dw_cli.updater import ReleaseUpdate, UpdateCancelled, UpdateError


class RecordingScreen:
    def __init__(self, keys: tuple[int, ...] = (), size: tuple[int, int] = (20, 80)) -> None:
        self.keys: Iterator[int] = iter(keys)
        self.size = size
        self.writes: list[tuple[int, int, str, int]] = []
        self.keypad_value: bool | None = None
        self.timeout_value: int | None = None
        self.erases = 0
        self.refreshes = 0

    def getmaxyx(self) -> tuple[int, int]:
        return self.size

    def erase(self) -> None:
        self.erases += 1

    def refresh(self) -> None:
        self.refreshes += 1

    def keypad(self, value: bool) -> None:
        self.keypad_value = value

    def timeout(self, value: int) -> None:
        self.timeout_value = value

    def getch(self) -> int:
        return next(self.keys, -1)

    def addstr(self, y: int, x: int, text: str, attribute: int = 0) -> None:
        self.writes.append((y, x, text, attribute))


class SilentDownloaderTui(DownloaderTui):
    """TUI test harness that suppresses modal output by default."""

    def _draw_message(self, *_args: object, **_kwargs: object) -> None:
        pass

    def _error(self, message: str) -> None:
        pass


class FakeStore(GameStore):
    store_id = "fake"
    display_name = "Fake Store"
    description = "Test catalogue"

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.supported = True

    @property
    def base_url(self) -> str:
        return "https://example.test"

    @property
    def download_referrer(self) -> str:
        return "https://example.test/"

    def supports_platform(self, platform: Platform) -> bool:
        del platform
        return self.supported

    def platform_code(self, platform: Platform) -> str:
        return platform.code

    def search(
        self,
        system_code: str,
        query: str,
        catalog_progress: CatalogProgress | None = None,
    ) -> list[SearchResult]:
        del system_code, query, catalog_progress
        return self.results

    def download_request(self, detail_url: str) -> MediaDownload:
        return MediaDownload(detail_url + "/download")

    def validate_detail_url(self, url: str) -> bool:
        return url.startswith(self.base_url)

    def retrieve_download_url(self, detail_url: str) -> str:
        return detail_url + "/download"


def bare_tui(screen: RecordingScreen | None = None) -> DownloaderTui:
    instance = object.__new__(SilentDownloaderTui)
    instance.screen = screen or RecordingScreen()
    instance.gamepad = None
    instance.refresh_on_exit = False
    instance.exit_after_update = False
    instance.preferences = Preferences()
    instance.selected_store = None
    instance.roms_directories = ()
    instance.platforms = ()
    return instance


@pytest.fixture(autouse=True)
def harmless_curses(mocker: MockerFixture) -> None:
    mocker.patch.object(curses, "color_pair", lambda number: number)


def test_constructor_detects_runtime_and_sets_up_screen(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    screen = RecordingScreen()
    store = FakeStore()
    profile = HardwareProfile()
    joystick = mocker.Mock(spec=LinuxJoystick)
    config = Config("https://example.test", tmp_path, (tmp_path / "roms",))
    mocker.patch.object(
        tui_module.StoreCatalog,
        "from_config",
        lambda _config: StoreCatalog((store,)),
    )
    mocker.patch.object(tui_module, "load_preferences", lambda _path: Preferences("fake"))
    mocker.patch.object(tui_module, "detect_roms_directories", lambda _roots: (tmp_path / "roms",))
    mocker.patch.object(tui_module, "discover_platforms", lambda _roots: (resolve_platform("GBA"),))
    mocker.patch.object(tui_module, "detect_hardware_profile", lambda: profile)
    mocker.patch.object(tui_module.LinuxJoystick, "open_first", lambda: joystick)
    mocker.patch.object(curses, "has_colors", lambda: False)
    mocker.patch.object(curses, "curs_set", lambda _value: None)

    instance = DownloaderTui(screen, config)

    assert instance.selected_store is store
    assert instance.hardware is profile
    assert screen.keypad_value is True and screen.timeout_value == 50


def test_setup_screen_falls_back_locale_and_initializes_colors(
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    locale_calls: list[str] = []

    def setlocale(_category: int, value: str) -> str:
        locale_calls.append(value)
        if value == "":
            raise locale.Error("missing")
        return value

    pairs: list[tuple[int, int, int]] = []
    mocker.patch.object(locale, "setlocale", setlocale)
    mocker.patch.object(curses, "curs_set", lambda _value: (_ for _ in ()).throw(curses.error()))
    mocker.patch.object(curses, "has_colors", lambda: True)
    mocker.patch.object(curses, "start_color", lambda: None)
    mocker.patch.object(curses, "use_default_colors", lambda: None)
    mocker.patch.object(curses, "init_pair", lambda *args: pairs.append(args))

    instance._setup_screen()

    assert locale_calls == ["", "C"]
    assert len(pairs) == 5


def test_run_dispatches_main_actions_and_closes_controller(mocker: MockerFixture) -> None:
    instance = bare_tui()
    instance.store_catalog = StoreCatalog((FakeStore(),))
    instance.selected_store = FakeStore()
    closed: list[bool] = []
    instance.gamepad = mocker.Mock(spec=LinuxJoystick)
    instance.gamepad.close.side_effect = lambda: closed.append(True)
    choices = iter((0, 1, 2, 3, 4, 5, 0, 5, 1))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    actions: list[str] = []
    mocker.patch.object(instance, "_search_flow", new=lambda: actions.append("search"))
    mocker.patch.object(instance, "_direct_download_flow", new=lambda: actions.append("direct"))
    mocker.patch.object(instance, "_manage_library_flow", new=lambda: actions.append("manage"))
    mocker.patch.object(instance, "_settings_screen", new=lambda: actions.append("settings"))
    mocker.patch.object(instance, "_status_screen", new=lambda: actions.append("status"))
    refreshed: list[bool] = []
    mocker.patch.object(
        tui_module, "request_emulationstation_refresh", lambda: refreshed.append(True) or True
    )
    instance.refresh_on_exit = True

    instance.run()

    assert actions == ["search", "direct", "manage", "settings", "status"]
    assert closed == [True] and refreshed == [True]


def test_run_handles_missing_and_first_run_stores(mocker: MockerFixture) -> None:
    instance = bare_tui()
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    instance.store_catalog = StoreCatalog(())
    instance.run()
    assert "No download stores" in errors[0]

    instance = bare_tui()
    instance.store_catalog = StoreCatalog((FakeStore(),))
    configuration = iter((False, True))
    mocker.patch.object(instance, "_configure_store", new=lambda **_kwargs: next(configuration))
    confirmations = iter((False, True))
    mocker.patch.object(instance, "_confirm_exit", new=lambda: next(confirmations))
    mocker.patch.object(instance, "_menu", new=lambda *_args: None)
    instance.run()


def test_search_flow_handles_cancel_errors_empty_and_supported_results(
    mocker: MockerFixture,
) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    instance = bare_tui()
    instance.platforms = (platform,)
    mocker.patch.object(instance, "_menu", new=lambda *_args: None)
    instance._search_flow()
    store = FakeStore()
    instance.selected_store = store
    instance._search_flow()

    mocker.patch.object(instance, "_menu", new=lambda *_args: 0)
    mocker.patch.object(instance, "_on_screen_keyboard", new=lambda *_args, **_kwargs: None)
    instance._search_flow()
    messages: list[tuple[Any, ...]] = []
    mocker.patch.object(
        instance, "_draw_message", new=lambda *args, **_kwargs: messages.append(args)
    )
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    mocker.patch.object(instance, "_on_screen_keyboard", new=lambda *_args, **_kwargs: "game")
    mocker.patch.object(
        store, "search", new=lambda *_args: (_ for _ in ()).throw(StoreError("offline"))
    )
    instance._search_flow()
    assert errors == ["offline"]

    mocker.patch.object(store, "search", new=lambda *_args: [])
    instance._search_flow()
    mocker.patch.object(instance, "_on_screen_keyboard", new=lambda *_args, **_kwargs: "")
    instance._search_flow()
    assert any("Nothing matched" in args[1] for args in messages)
    assert any("catalogue is empty" in args[1] for args in messages)

    results = [
        SearchResult("Good", "good"),
        SearchResult("Bad", "bad", system="PS2"),
    ]
    mocker.patch.object(store, "search", new=lambda *_args: results)
    instance.compatibility_client = mocker.Mock()
    instance.compatibility_client.lookup_many.return_value = [
        CompatibilityInfo("Perfect", True),
    ]
    received: list[tuple[Any, ...]] = []
    mocker.patch.object(instance, "_results_flow", new=lambda *args: received.append(args))
    instance._search_flow()
    assert [item.title for item in received[0][0]] == ["Good"]


def test_catalog_progress_and_results_flow_resolve_all_platform(
    mocker: MockerFixture,
) -> None:
    all_platform = resolve_platform("ALL")
    gba = resolve_platform("GBA")
    assert all_platform is not None and gba is not None
    instance = bare_tui()
    messages: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda _title, message, *_args, **_kwargs: messages.append(message),
    )
    instance._catalog_progress(3, 4)
    assert "75%" in messages[-1]

    result = SearchResult(
        "Advance Wars",
        "detail",
        system="GBA",
        region="USA",
        version="1.0",
        languages="English",
        rating="E",
    )
    info = CompatibilityInfo("Perfect", True, 0.95)
    choices = iter((0, 7, 0, 8, None))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    downloads: list[tuple[str, Platform, object]] = []
    mocker.patch.object(instance, "_download_detail", new=lambda *args: downloads.append(args))
    store = FakeStore()

    instance._results_flow([result], all_platform, [info], store)

    assert downloads[0][1] == gba


def test_direct_download_flow_handles_store_platform_and_url_choices(
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    all_platform = resolve_platform("ALL")
    assert gba is not None and all_platform is not None
    instance = bare_tui()
    instance.platforms = (all_platform, gba)
    mocker.patch.object(instance, "_menu", new=lambda *_args: 0)
    instance._direct_download_flow()
    store = FakeStore()
    instance.selected_store = store
    mocker.patch.object(instance, "_menu", new=lambda *_args: None)
    instance._direct_download_flow()
    mocker.patch.object(instance, "_menu", new=lambda *_args: 0)
    mocker.patch.object(instance, "_on_screen_keyboard", new=lambda *_args, **_kwargs: "")
    instance._direct_download_flow()
    calls: list[tuple[Any, ...]] = []
    mocker.patch.object(instance, "_on_screen_keyboard", new=lambda *_args, **_kwargs: "detail")
    mocker.patch.object(instance, "_download_detail", new=lambda *args: calls.append(args))
    instance._direct_download_flow()
    assert calls[0][:2] == ("detail", gba)


@pytest.mark.parametrize(
    ("platform", "root", "exception", "expected"),
    [
        (Platform("All", "ALL", "", ""), Path("roms"), None, "no dArkOS ROM folder"),
        (resolve_platform("GBA"), None, None, "No dArkOS ROM partition"),
        (resolve_platform("GBA"), Path("roms"), DownloadCancelled("cancel"), "DOWNLOAD CANCELLED"),
        (resolve_platform("GBA"), Path("roms"), DownloadError("broken"), "broken"),
        (resolve_platform("GBA"), Path("roms"), StoreError("store"), "store"),
        (resolve_platform("GBA"), Path("roms"), OrganizeError("move"), "move"),
    ],
)
def test_download_detail_reports_failures(
    platform: Platform | None,
    root: Path | None,
    exception: Exception | None,
    expected: str,
    mocker: MockerFixture,
) -> None:
    assert platform is not None
    instance = bare_tui()
    errors: list[str] = []
    messages: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    mocker.patch.object(
        instance, "_draw_message", new=lambda title, *_args, **_kwargs: messages.append(title)
    )
    mocker.patch.object(instance, "_choose_roms_directory", new=lambda: root)
    store = FakeStore()
    if isinstance(exception, StoreError):
        mocker.patch.object(
            store, "download_request", new=lambda _url: (_ for _ in ()).throw(exception)
        )
    elif exception is not None:
        mocker.patch.object(
            instance, "_download_media", new=lambda *_args: (_ for _ in ()).throw(exception)
        )
    else:
        mocker.patch.object(instance, "_download_media", new=lambda *_args: [])

    instance._download_detail("detail", platform, store)

    assert expected in " ".join(errors + messages)


def test_library_management_flows(tmp_path: Path, mocker: MockerFixture) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    instance = bare_tui()
    errors: list[str] = []
    messages: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    mocker.patch.object(
        instance, "_draw_message", new=lambda title, *_args, **_kwargs: messages.append(title)
    )
    instance._manage_library_flow()
    assert errors

    instance.roms_directories = (tmp_path,)
    choices = iter((tmp_path, tmp_path, None))
    mocker.patch.object(instance, "_choose_from_roots", new=lambda *_args: next(choices))
    mocker.patch.object(tui_module, "platforms_with_installed_games", lambda *_args: ())
    instance._manage_library_flow()
    assert "NO GAMES ON CARD" in messages

    choices = iter((tmp_path, None))
    mocker.patch.object(instance, "_choose_from_roots", new=lambda *_args: next(choices))
    mocker.patch.object(tui_module, "platforms_with_installed_games", lambda *_args: (gba,))
    mocker.patch.object(instance, "_menu", new=lambda *_args: 0)
    managed: list[tuple[Path, Platform]] = []
    mocker.patch.object(
        instance, "_manage_platform_library", new=lambda *args: managed.append(args)
    )
    instance._manage_library_flow()
    assert managed == [(tmp_path, gba)]


def test_platform_and_game_management_refreshes_after_change(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    path = tmp_path / "gba" / "game.zip"
    game = InstalledGame("Game", gba, tmp_path, path, (path,))
    instance = bare_tui()
    messages: list[str] = []
    mocker.patch.object(
        instance, "_draw_message", new=lambda title, *_args, **_kwargs: messages.append(title)
    )
    scans = iter(([], [game], [game]))
    mocker.patch.object(tui_module, "scan_library", lambda *_args: next(scans))
    instance._manage_platform_library(tmp_path, gba)
    choices = iter((0, None))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    mocker.patch.object(instance, "_manage_game", new=lambda _game: True)
    instance._manage_platform_library(tmp_path, gba)
    assert "NO GAMES" in messages and "REFRESHING" in messages

    actions = iter((4, 5, None))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(actions))
    mocker.patch.object(instance, "_update_game", new=lambda _game: True)
    mocker.patch.object(instance, "_confirm_delete", new=lambda _game: True)
    assert DownloaderTui._manage_game(instance, game) is True
    assert DownloaderTui._manage_game(instance, game) is True
    assert DownloaderTui._manage_game(instance, game) is False


def test_delete_handles_cancel_library_error_and_success(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    path = tmp_path / "gba" / "game.zip"
    game = InstalledGame("Game", gba, tmp_path, path, (path,))
    instance = bare_tui()
    mocker.patch.object(instance, "_menu", new=lambda *_args: 0)
    assert instance._confirm_delete(game) is False
    mocker.patch.object(instance, "_menu", new=lambda *_args: 1)
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    mocker.patch.object(
        tui_module, "delete_game", lambda _game: (_ for _ in ()).throw(LibraryError("locked"))
    )
    assert instance._confirm_delete(game) is False
    assert errors == ["locked"]
    mocker.patch.object(tui_module, "delete_game", lambda _game: None)
    assert instance._confirm_delete(game) is True
    assert instance.refresh_on_exit is True


def test_update_game_covers_selection_cancel_errors_and_success(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    old_path = tmp_path / "gba" / "old.zip"
    game = InstalledGame("Game", gba, tmp_path, old_path, (old_path,))
    result = SearchResult("Game Rev 2", "detail", region="USA", version="2")
    store = FakeStore([result])
    instance = bare_tui()
    instance.selected_store = None
    assert instance._update_game(game) is False
    instance.selected_store = store
    store.supported = False
    assert instance._update_game(game) is False
    store.supported = True
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    mocker.patch.object(
        store, "search", new=lambda *_args: (_ for _ in ()).throw(StoreError("offline"))
    )
    assert instance._update_game(game) is False
    mocker.patch.object(store, "search", new=lambda *_args: [])
    assert instance._update_game(game) is False
    mocker.patch.object(store, "search", new=lambda *_args: [result])
    mocker.patch.object(instance, "_menu", new=lambda *_args: None)
    assert instance._update_game(game) is False
    choices = iter((0, 0))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    assert instance._update_game(game) is False

    choices = iter((0, 1))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    mocker.patch.object(
        instance,
        "_download_media",
        new=lambda *_args: (_ for _ in ()).throw(DownloadCancelled("cancel")),
    )
    assert instance._update_game(game) is False
    choices = iter((0, 1))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    mocker.patch.object(
        instance,
        "_download_media",
        new=lambda *_args: (_ for _ in ()).throw(DownloadError("broken")),
    )
    assert instance._update_game(game) is False

    downloaded = DownloadResult("file", tmp_path / "new.zip")
    completed = DownloadResult("file", tmp_path / "gba" / "new.zip")
    choices = iter((0, 1))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    mocker.patch.object(instance, "_download_media", new=lambda *_args: [downloaded])
    mocker.patch.object(tui_module, "install_bundled_bios", lambda *_args: (tmp_path / "bios.bin",))
    mocker.patch.object(tui_module, "replace_game", lambda *_args: completed)
    assert instance._update_game(game) is True
    assert instance.refresh_on_exit is True


def test_store_and_root_choices_and_configuration(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    supported = FakeStore()
    unsupported = FakeStore()
    unsupported.display_name = "Other"
    unsupported.supported = False
    instance = bare_tui()
    instance.store_catalog = StoreCatalog((unsupported, supported))
    mocker.patch.object(instance, "_menu", new=lambda *_args: 0)
    assert instance._choose_store("STORE", gba) is supported
    mocker.patch.object(instance, "_menu", new=lambda *_args: None)
    assert instance._choose_store("STORE") is None

    assert instance._choose_from_roots((), "ROOT") is None
    assert instance._choose_from_roots((Path("/roms"),), "ROOT") == Path("/roms")
    roots = (Path("/roms2"), Path("/roms"), tmp_path)
    mocker.patch.object(instance, "_menu", new=lambda *_args: 2)
    assert instance._choose_from_roots(roots, "ROOT") == tmp_path
    mocker.patch.object(instance, "_menu", new=lambda *_args: None)
    assert instance._choose_from_roots(roots, "ROOT") is None

    instance.preferences_path = tmp_path / "settings.json"
    mocker.patch.object(instance, "_choose_store", new=lambda *_args: None)
    assert instance._configure_store() is False
    mocker.patch.object(instance, "_choose_store", new=lambda *_args: supported)
    mocker.patch.object(tui_module, "load_preferences", lambda _path: Preferences())
    mocker.patch.object(
        tui_module,
        "save_preferences",
        lambda *_args: (_ for _ in ()).throw(PreferencesError("read only")),
    )
    assert instance._configure_store() is False
    mocker.patch.object(tui_module, "save_preferences", lambda *_args: None)
    assert instance._configure_store() is True
    assert instance.selected_store is supported


def test_settings_and_minerva_settings_actions(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.selected_store = FakeStore()
    instance.selected_store.store_id = "minerva"
    instance.selected_store.display_name = "Minerva"
    actions: list[str] = []
    mocker.patch.object(instance, "_configure_store", new=lambda: actions.append("store") or True)
    mocker.patch.object(
        instance, "_minerva_bittorrent_settings_screen", new=lambda: actions.append("minerva")
    )
    mocker.patch.object(instance, "_application_update_flow", new=lambda: actions.append("update"))
    for choice in (None, 0, 1, 2, 3):
        mocker.patch.object(instance, "_menu", new=lambda *_args, value=choice: value)
        instance._settings_screen()
    assert actions == ["store", "minerva", "update"]

    instance.preferences_path = tmp_path / "settings.json"
    instance.preferences = Preferences("minerva", BitTorrentSettings(block_size=32768))
    saved: list[BitTorrentSettings] = []
    mocker.patch.object(
        instance,
        "_save_minerva_bittorrent_settings",
        new=lambda settings: saved.append(settings) or True,
    )
    choices = iter((9, 1, 0, 6, 10))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    values = iter(("invalid", "2.5"))
    mocker.patch.object(instance, "_on_screen_keyboard", new=lambda *_args, **_kwargs: next(values))
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    DownloaderTui._minerva_bittorrent_settings_screen(instance)
    assert errors and saved[-1].max_peer_timeout_seconds == 2.5


def test_save_minerva_settings_handles_error_and_formats_values(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.preferences_path = tmp_path / "settings.json"
    instance.preferences = Preferences("minerva")
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    mocker.patch.object(
        tui_module,
        "save_preferences",
        lambda *_args: (_ for _ in ()).throw(PreferencesError("full")),
    )
    assert instance._save_minerva_bittorrent_settings(BitTorrentSettings()) is False
    assert errors == ["full"]
    mocker.patch.object(tui_module, "save_preferences", lambda *_args: None)
    assert instance._save_minerva_bittorrent_settings(BitTorrentSettings()) is True
    assert instance._format_bittorrent_setting("udp_protocol_id", BitTorrentSettings()).startswith(
        "0x"
    )
    assert instance._format_bittorrent_setting("block_size", BitTorrentSettings()) == "16384"


def test_application_update_flow_covers_all_outcomes(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    release = ReleaseUpdate("2.0.0", "v2.0.0", "bundle.zip", "https://example.test/bundle", 50)
    instance = bare_tui()
    errors: list[str] = []
    messages: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    mocker.patch.object(
        instance, "_draw_message", new=lambda title, *_args, **_kwargs: messages.append(title)
    )
    instance.config = Config(
        "url",
        tmp_path / "downloads",
        (),
        timeout_seconds=1.0,
        install_directory=None,
        update_api_url="api",
    )
    instance._application_update_flow()
    assert errors
    instance.config = Config(
        "url",
        tmp_path / "downloads",
        (),
        timeout_seconds=1.0,
        install_directory=tmp_path,
        update_api_url="api",
    )
    mocker.patch.object(tui_module, "installed_version", lambda: "1.0.0")
    mocker.patch.object(
        tui_module, "find_update", lambda *_args: (_ for _ in ()).throw(UpdateError("api error"))
    )
    instance._application_update_flow()
    mocker.patch.object(tui_module, "find_update", lambda *_args: None)
    instance._application_update_flow()
    mocker.patch.object(tui_module, "find_update", lambda *_args: release)
    mocker.patch.object(instance, "_menu", new=lambda *_args: 1)
    instance._application_update_flow()
    mocker.patch.object(instance, "_menu", new=lambda *_args: 0)
    mocker.patch.object(
        instance,
        "_stage_application_update",
        new=lambda *_args: (_ for _ in ()).throw(UpdateCancelled("cancel")),
    )
    instance._application_update_flow()
    mocker.patch.object(
        instance,
        "_stage_application_update",
        new=lambda *_args: (_ for _ in ()).throw(UpdateError("bad bundle")),
    )
    instance._application_update_flow()
    assert "ALREADY UP TO DATE" in messages and "UPDATE CANCELLED" in messages
    assert "api error" in errors and "bad bundle" in errors


def test_stage_update_and_download_background_workers(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.config = Config("url", tmp_path, (), timeout_seconds=1.0)
    release = ReleaseUpdate("2.0.0", "v2.0.0", "bundle.zip", "url", 10)
    mocker.patch.object(instance, "_poll_input", new=lambda *_args: None)
    mocker.patch.object(instance, "_progress", new=lambda *_args: None)

    def staged(
        _release: object, _install: object, _timeout: object, progress: object, _cancel: object
    ) -> Path:
        cast(Callable[[str, int, int | None], None], progress)("bundle", 10, 10)
        return tmp_path / "pending"

    mocker.patch.object(tui_module, "stage_update", staged)
    assert instance._stage_application_update(release, tmp_path) == tmp_path / "pending"

    result = DownloadResult("url", tmp_path / "game.zip")

    def downloaded(*args: object, **_kwargs: object) -> list[DownloadResult]:
        cast(Callable[[str, int, int | None], None], args[4])("game", 10, 10)
        return [result]

    mocker.patch.object(tui_module, "download_files", downloaded)
    store = FakeStore()
    assert instance._download_media(["url"], store) == [result]


def test_progress_status_rendering_and_input_helpers(mocker: MockerFixture) -> None:
    screen = RecordingScreen(keys=(ord("q"),))
    instance = bare_tui(screen)
    drawn: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda _title, message, *_args, **_kwargs: drawn.append(message),
    )
    mocker.patch.object(instance, "_footer", new=lambda _text: None)
    instance._progress("game", 50, 100)
    instance._progress("game", 2048, None)
    assert "50%" in drawn[0] and "2 KiB" in drawn[1]

    instance.roms_directories = (Path("/roms"), Path("/roms2"))
    instance.selected_store = FakeStore()
    instance.store_catalog = StoreCatalog((FakeStore(),))
    all_platform = resolve_platform("ALL")
    gba = resolve_platform("GBA")
    assert all_platform is not None and gba is not None
    instance.platforms = (all_platform, gba)
    instance.hardware = HardwareProfile(
        compatible=("rockchip,rk3326",),
        input_nodes=(DeviceTreeInput("/keys", ("gpio-keys",)),),
        keys=(DeviceTreeKey("A", 1, "/keys/a"),),
        model="R36S",
        display_width=640,
        display_height=480,
    )
    instance.gamepad = mocker.Mock(spec=LinuxJoystick)
    instance.gamepad.path = Path("/dev/input/js0")
    instance.gamepad.poll.return_value = InputAction.UP
    instance.config = Config("url", Path("downloads"), ())
    instance._status_screen()
    assert "R36S" in drawn[-1]
    assert instance._poll_input() == curses.KEY_UP
    instance.gamepad = None
    assert instance._poll_input() == ord("q")


def test_keyboard_menu_and_drawing_primitives(mocker: MockerFixture) -> None:
    instance = bare_tui(RecordingScreen())
    inputs = iter(
        (
            curses.KEY_DOWN,
            curses.KEY_UP,
            curses.KEY_LEFT,
            curses.KEY_RIGHT,
            10,
            curses.KEY_BACKSPACE,
            GAMEPAD_SEARCH_KEY,
        )
    )
    mocker.patch.object(instance, "_get_input", new=lambda *_args: next(inputs))
    assert instance._on_screen_keyboard("SEARCH") == ""

    instance = bare_tui(RecordingScreen(size=(15, 40)))
    inputs = iter((curses.KEY_DOWN, curses.KEY_UP, curses.KEY_NPAGE, curses.KEY_PPAGE, 10))
    mocker.patch.object(instance, "_get_input", new=lambda *_args: next(inputs))
    assert instance._menu("MENU", tuple(str(index) for index in range(20)), "footer") == 0
    mocker.patch.object(instance, "_get_input", new=lambda *_args: 27)
    assert instance._menu("MENU", ("one",), "footer") is None
    assert instance._menu("MENU", (), "footer") is None

    screen = RecordingScreen(size=(20, 50))
    instance = bare_tui(screen)
    mocker.patch.object(instance, "_get_input", new=lambda *_args: 10)
    instance._draw_message("TITLE", "a long message\nsecond", 1, wait=True)
    instance._header("HEADER")
    instance._footer("FOOTER")
    instance._safe_add(-1, 0, "ignored")
    instance._safe_add(2, 100, "ignored")
    instance._safe_add(2, -2, "clipped")
    assert screen.writes
    instance._error("problem")
    with pytest.raises(TerminalTooSmall):
        instance._require_size(14, 80)
    with pytest.raises(TerminalTooSmall):
        instance._require_size(20, 39)
    instance._require_size(15, 40)


def test_get_input_waits_and_run_tui_uses_curses_wrapper(mocker: MockerFixture) -> None:
    instance = bare_tui()
    values = iter((None, None, 10))
    mocker.patch.object(instance, "_poll_input", new=lambda *_args: next(values))
    assert instance._get_input() == 10
    called: list[object] = []
    mocker.patch.object(curses, "wrapper", lambda callback: callback(RecordingScreen()))
    mocker.patch.object(
        DownloaderTui, "__init__", lambda self, screen, config: called.extend((screen, config))
    )
    mocker.patch.object(DownloaderTui, "run", lambda self: called.append("run"))
    config = Config("url", Path("downloads"), ())
    tui_module.run_tui(config)
    assert called[-1] == "run"
