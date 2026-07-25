import curses
import locale
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest
from pytest_mock import MockerFixture

from dw_cli import tui as tui_module
from dw_cli.bittorrent import BitTorrentSettings, TorrentFileChoice, TorrentSelectionRequired
from dw_cli.compatibility import CompatibilityError, CompatibilityInfo, R36SCompatibilityClient
from dw_cli.config import Config
from dw_cli.downloader import DownloadCancelled, DownloadError, DownloadSelectionRequired
from dw_cli.gamepad import InputAction, LinuxJoystick
from dw_cli.hardware import DeviceTreeInput, DeviceTreeKey, HardwareProfile
from dw_cli.library import LibraryError
from dw_cli.models import DownloadResult, InstalledGame, MediaDownload, Platform, SearchResult
from dw_cli.organizer import OrganizeError
from dw_cli.platforms import resolve_platform
from dw_cli.preferences import Preferences, PreferencesError, load_preferences
from dw_cli.retrobios import (
    BiosCheck,
    BiosDownloadCancelled,
    BiosError,
    BiosRequirement,
    BiosState,
    BiosSystem,
    RetroBiosCatalog,
    RetroBiosRepository,
)
from dw_cli.store import CatalogProgress, GameStore, StoreError
from dw_cli.store_catalog import StoreCatalog
from dw_cli.tui import (
    GAMEPAD_SEARCH_KEY,
    DownloaderTui,
    TerminalTooSmall,
    _keyboard_rows,
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
    instance.config = Config("https://example.test", Path("downloads"), ())
    instance.store_catalog = StoreCatalog(())
    instance.selected_store = None
    instance.roms_directories = ()
    instance.platforms = ()
    instance.retrobios_catalog = None
    return instance


def bios_catalog_fixture() -> RetroBiosCatalog:
    firmware = BiosRequirement(
        name="gba_bios.bin",
        destination="gba_bios.bin",
        required=True,
        size=4,
        sha256="37be46f4b26de340ff5ea1f9f652b3167b6d3dfc087c3ac2aebc51e423e66912",
        sha1=None,
        md5=None,
        source_path="bios/Nintendo/Game Boy Advance/GBA_bios.rom",
        description="Official GBA BIOS",
    )
    return RetroBiosCatalog(
        "a" * 40,
        {
            "nintendo-gba": BiosSystem(
                "nintendo-gba",
                "Nintendo - Game Boy Advance",
                "gpsp",
                None,
                (firmware,),
            )
        },
        "today",
        "v1",
        9_999_999_999,
    )


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
        lambda _config, _ttl: StoreCatalog((store,)),
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
    choices = iter((0, 1, 2, 3, 4, 5, 6, 0, 6, 1))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    actions: list[str] = []
    mocker.patch.object(instance, "_search_flow", new=lambda: actions.append("search"))
    mocker.patch.object(instance, "_direct_download_flow", new=lambda: actions.append("direct"))
    mocker.patch.object(instance, "_manage_library_flow", new=lambda: actions.append("manage"))
    mocker.patch.object(instance, "_bios_search_flow", new=lambda: actions.append("bios"))
    mocker.patch.object(instance, "_settings_screen", new=lambda: actions.append("settings"))
    mocker.patch.object(instance, "_status_screen", new=lambda: actions.append("status"))
    refreshed: list[bool] = []
    mocker.patch.object(
        tui_module, "request_emulationstation_refresh", lambda: refreshed.append(True) or True
    )
    instance.refresh_on_exit = True

    instance.run()

    assert actions == ["search", "direct", "manage", "bios", "settings", "status"]
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
    downloads: list[tuple[Any, ...]] = []
    mocker.patch.object(
        instance,
        "_download_detail",
        new=lambda *args, **kwargs: downloads.append((*args, kwargs)),
    )
    store = FakeStore()

    instance._results_flow([result], all_platform, [info], store)

    assert downloads[0][1] == gba
    assert downloads[0][-1] == {"region": "USA"}


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
    mocker.patch.object(instance, "_bios_followup", new=lambda *_args: 0)
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
    mocker.patch.object(
        instance,
        "_update_retrobios_catalogue",
        new=lambda: actions.append("retrobios"),
    )
    mocker.patch.object(
        instance,
        "_update_compatibility_catalogue",
        new=lambda: actions.append("compatibility"),
    )
    mocker.patch.object(
        instance,
        "_refresh_store_catalogue",
        new=lambda: actions.append("store_catalogue"),
    )
    mocker.patch.object(
        instance,
        "_configure_catalogue_ttl",
        new=lambda: actions.append("ttl"),
    )
    mocker.patch.object(
        instance,
        "_configure_log_level",
        new=lambda: actions.append("log_level"),
    )
    mocker.patch.object(
        instance,
        "_configure_file_logging",
        new=lambda: actions.append("log_file"),
    )
    for choice in (None, *range(10)):
        mocker.patch.object(instance, "_menu", new=lambda *_args, value=choice: value)
        instance._settings_screen()
    assert actions == [
        "store",
        "store_catalogue",
        "retrobios",
        "compatibility",
        "ttl",
        "log_level",
        "log_file",
        "minerva",
        "update",
    ]

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


def test_runtime_cache_and_logging_settings_apply_immediately_and_persist(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.config = Config("https://example.test", tmp_path, ())
    instance.preferences_path = tmp_path / "settings.json"
    instance.retrobios_repository = mocker.Mock(ttl_seconds=1)
    instance.compatibility_client = mocker.Mock(ttl_seconds=1)
    instance.retrobios_catalog = bios_catalog_fixture()
    store = FakeStore()
    instance.store_catalog = StoreCatalog((store,))
    set_store_ttl = mocker.patch.object(store, "set_catalogue_ttl")
    configure_logging = mocker.patch.object(tui_module, "configure_logging")

    mocker.patch.object(instance, "_on_screen_keyboard", return_value="14")
    instance._configure_catalogue_ttl()

    expected_seconds = 14 * 24 * 60 * 60
    assert instance.preferences.catalogue_ttl_days == 14
    assert instance.retrobios_repository.ttl_seconds == expected_seconds
    assert instance.retrobios_catalog.ttl_seconds == expected_seconds
    assert instance.compatibility_client.ttl_seconds == expected_seconds
    set_store_ttl.assert_called_with(expected_seconds)
    assert load_preferences(instance.preferences_path).catalogue_ttl_days == 14

    mocker.patch.object(instance, "_menu", return_value=0)
    instance._configure_log_level()
    assert instance.preferences.log_level == "DEBUG"
    configure_logging.assert_called_with(None, "DEBUG")

    mocker.patch.object(instance, "_menu", return_value=1)
    instance._configure_file_logging()
    assert instance.preferences.log_to_file is True
    configure_logging.assert_called_with(tmp_path / "darkos-downloader.log", "DEBUG")
    assert load_preferences(instance.preferences_path).log_to_file is True

    mocker.patch.object(instance, "_menu", return_value=0)
    instance._configure_file_logging()
    assert instance.preferences.log_to_file is False
    configure_logging.assert_called_with(None, "DEBUG")

    mocker.patch.object(instance, "_menu", return_value=None)
    instance._configure_log_level()
    instance._configure_file_logging()


def test_runtime_settings_reject_invalid_cache_days_and_handle_save_errors(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.preferences_path = tmp_path / "settings.json"
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    keyboard = mocker.patch.object(instance, "_on_screen_keyboard", return_value="0")

    instance._configure_catalogue_ttl()
    assert errors[-1].startswith("Invalid catalogue lifetime:")

    keyboard.return_value = None
    instance._configure_catalogue_ttl()
    mocker.patch.object(
        tui_module,
        "save_preferences",
        side_effect=PreferencesError("storage is read-only"),
    )
    assert (
        instance._save_runtime_preferences(
            replace(instance.preferences, log_level="ERROR"),
            "SAVED",
            "Saved",
        )
        is False
    )
    assert errors[-1] == "storage is read-only"


def test_settings_can_force_refresh_one_store_platform_catalogue(
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    all_platforms = resolve_platform("ALL")
    assert gba is not None and all_platforms is not None
    instance = bare_tui()
    instance.platforms = (all_platforms, gba, gba)
    store = FakeStore()
    instance.store_catalog = StoreCatalog((store,))
    result = SearchResult("Advance Wars", "https://example.test/game")
    refresh = mocker.patch.object(store, "refresh_catalogue", return_value=[result])
    choices = iter((0, 1))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    messages: list[tuple[str, str]] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda title, message, *_args, **_kwargs: messages.append((title, message)),
    )

    instance._refresh_store_catalogue()

    refresh.assert_called_once_with(gba.code, instance._catalog_progress)
    assert messages[-1] == (
        "GAME CATALOGUE UPDATED",
        "Cached 1 Fake Store result(s) for Game Boy Advance.",
    )
    assert instance._store_cache_status_label(None) == "not downloaded"


def test_store_catalogue_refresh_can_cancel_or_report_failure(
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    instance = bare_tui()
    instance.platforms = (gba,)
    store = FakeStore()
    instance.store_catalog = StoreCatalog((store,))

    mocker.patch.object(instance, "_menu", return_value=None)
    instance._refresh_store_catalogue()

    choices = iter((0, 0))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    mocker.patch.object(store, "refresh_catalogue", side_effect=StoreError("offline"))
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    instance._refresh_store_catalogue()
    assert errors == ["offline"]


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


def test_bios_followup_does_not_prompt_for_bundled_or_second_card_bios(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    instance = bare_tui()
    sd1 = tmp_path / "roms"
    sd2 = tmp_path / "roms2"
    instance.roms_directories = (sd1, sd2)
    catalog = bios_catalog_fixture()
    mocker.patch.object(instance, "_load_retrobios_catalogue", new=lambda **_kwargs: catalog)
    unexpected_menu = mocker.patch.object(instance, "_menu", side_effect=AssertionError("prompted"))
    second_card_bios = sd2 / "bios/gba_bios.bin"
    second_card_bios.parent.mkdir(parents=True)
    second_card_bios.write_bytes(b"bios")

    assert instance._bios_followup(gba, sd1, "USA") == 0
    unexpected_menu.assert_not_called()

    second_card_bios.unlink()
    bundled_bios = sd1 / "bios/gba_bios.bin"
    bundled_bios.parent.mkdir(parents=True, exist_ok=True)
    bundled_bios.write_bytes(b"bios")
    assert instance._bios_followup(gba, sd1, "USA") == 0
    unexpected_menu.assert_not_called()


def test_bios_followup_allows_skip_or_explicit_download(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    instance = bare_tui()
    instance.roms_directories = (tmp_path,)
    catalog = bios_catalog_fixture()
    mocker.patch.object(instance, "_load_retrobios_catalogue", new=lambda **_kwargs: catalog)
    menus = mocker.patch.object(instance, "_menu", return_value=1)

    assert instance._bios_followup(gba, tmp_path, None) == 0
    assert menus.call_args.args[0] == "DOWNLOAD REQUIRED BIOS?"

    choices = iter((0, 1))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    installed: list[tuple[BiosCheck, ...]] = []
    mocker.patch.object(
        instance,
        "_install_bios_checks",
        new=lambda _catalog, checks, _platform, _root: installed.append(tuple(checks)) or 1,
    )
    assert instance._bios_followup(gba, tmp_path, None) == 1
    assert installed[0][0].state is BiosState.MISSING


def test_bios_followup_reports_catalogue_failure_without_download_prompt(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    instance = bare_tui()
    messages: list[tuple[str, str]] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda title, message, *_args, **_kwargs: messages.append((title, message)),
    )
    mocker.patch.object(
        instance,
        "_load_retrobios_catalogue",
        side_effect=BiosError("offline"),
    )
    assert instance._bios_followup(gba, tmp_path, None) == 0
    assert messages[-1][0] == "BIOS CHECK UNAVAILABLE"

    mocker.patch.object(
        instance,
        "_load_retrobios_catalogue",
        side_effect=BiosDownloadCancelled("cancelled"),
    )
    assert instance._bios_followup(gba, tmp_path, None) == 0


def test_manual_bios_search_lists_and_downloads_optional_or_required_files(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    instance = bare_tui()
    instance.roms_directories = (tmp_path,)
    instance.platforms = (gba,)
    catalog = bios_catalog_fixture()
    mocker.patch.object(instance, "_load_retrobios_catalogue", new=lambda **_kwargs: catalog)
    mocker.patch.object(instance, "_on_screen_keyboard", return_value="gba")
    choices = iter((0, None))
    menus: list[tuple[str, tuple[str, ...]]] = []

    def choose(title: str, options: Sequence[str], _footer: str) -> int | None:
        menus.append((title, tuple(options)))
        return next(choices)

    mocker.patch.object(instance, "_menu", new=choose)
    mocker.patch.object(instance, "_confirm_retrobios_download", return_value=True)
    installed: list[str] = []
    mocker.patch.object(
        instance,
        "_install_bios_checks",
        new=lambda *_args: installed.append("gba_bios.bin") or 1,
    )

    instance._bios_search_flow()

    assert menus[0][0] == "BIOS RESULTS (1)"
    assert "GBA" in menus[0][1][0]
    assert installed == ["gba_bios.bin"]


def test_manual_bios_search_handles_cancel_empty_and_unavailable_catalogue(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.roms_directories = ()
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    instance._bios_search_flow()
    assert "No dArkOS" in errors[-1]

    instance.roms_directories = (tmp_path,)
    mocker.patch.object(instance, "_load_retrobios_catalogue", side_effect=BiosError("offline"))
    instance._bios_search_flow()
    assert errors[-1] == "offline"

    catalog = bios_catalog_fixture()
    mocker.patch.object(instance, "_load_retrobios_catalogue", return_value=catalog)
    mocker.patch.object(instance, "_on_screen_keyboard", return_value="does-not-exist")
    messages: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda _title, message, *_args, **_kwargs: messages.append(message),
    )
    instance._bios_search_flow()
    assert "Nothing matched" in messages[-1]


def test_retrobios_cache_loading_and_explicit_settings_update(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.config = Config("https://example.test", tmp_path, ())
    repository = mocker.Mock(spec=RetroBiosRepository)
    instance.retrobios_repository = repository
    catalog = bios_catalog_fixture()
    repository.load.return_value = None
    assert instance._retrobios_cache_label() == "not downloaded"
    repository.load.return_value = catalog
    assert instance._retrobios_cache_label() == "aaaaaaaa - fresh"
    repository.load.side_effect = BiosError("bad cache")
    assert instance._retrobios_cache_label() == "cache invalid"
    repository.load.side_effect = None

    repository.ensure.return_value = catalog
    mocker.patch.object(instance, "_progress", new=lambda *_args: None)
    mocker.patch.object(instance, "_poll_input", new=lambda *_args: None)
    assert instance._load_retrobios_catalogue() is catalog
    repository.ensure.assert_called_once()
    repository.update.return_value = catalog
    assert instance._load_retrobios_catalogue(update=True) is catalog
    repository.update.assert_called_once()

    mocker.patch.object(instance, "_menu", return_value=0)
    mocker.patch.object(instance, "_load_retrobios_catalogue", return_value=catalog)
    messages: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda title, _message, *_args, **_kwargs: messages.append(title),
    )
    instance._update_retrobios_catalogue()
    assert messages[-1] == "RETROBIOS UPDATED"


def test_compatibility_cache_status_and_explicit_update(
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    assert instance._compatibility_cache_label() == "not downloaded"
    client = mocker.Mock(spec=R36SCompatibilityClient)
    instance.compatibility_client = client
    client.cache_age_seconds.return_value = None
    assert instance._compatibility_cache_label() == "not downloaded"
    client.cache_age_seconds.return_value = 1
    client.cache_is_stale.return_value = False
    assert instance._compatibility_cache_label() == "fresh"
    client.cache_is_stale.return_value = True
    assert instance._compatibility_cache_label() == "stale (>7 days)"

    mocker.patch.object(instance, "_menu", return_value=1)
    instance._update_compatibility_catalogue()
    client.refresh.assert_not_called()

    mocker.patch.object(instance, "_menu", return_value=0)
    client.refresh.return_value = 1234
    messages: list[tuple[str, str]] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda title, message, *_args, **_kwargs: messages.append((title, message)),
    )
    instance._update_compatibility_catalogue()
    assert messages[-1][0] == "R36S GAME LIST UPDATED"
    assert "1234" in messages[-1][1]

    client.refresh.side_effect = CompatibilityError("refresh failed")
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    instance._update_compatibility_catalogue()
    assert errors[-1] == "refresh failed"


def test_install_bios_checks_reports_success_cancel_and_error(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    instance = bare_tui()
    instance.config = Config("https://example.test", tmp_path, ())
    catalog = bios_catalog_fixture()
    requirement = catalog.requirements_for(gba)[0]
    check = BiosCheck(requirement, BiosState.MISSING, (tmp_path / "bios/gba_bios.bin",))
    mocker.patch.object(instance, "_progress", new=lambda *_args: None)
    mocker.patch.object(instance, "_poll_input", new=lambda *_args: None)
    installed = mocker.patch.object(tui_module, "install_bios", return_value=check.paths)
    assert instance._install_bios_checks(catalog, (check,), gba, tmp_path) == 1
    installed.assert_called_once()

    installed.side_effect = BiosDownloadCancelled("cancel")
    assert instance._install_bios_checks(catalog, (check,), gba, tmp_path) == 0
    installed.side_effect = BiosError("failed")
    errors: list[str] = []
    mocker.patch.object(instance, "_error", new=errors.append)
    assert instance._install_bios_checks(catalog, (check,), gba, tmp_path) == 0
    assert errors[-1] == "failed"


def test_retrobios_settings_update_handles_keep_cancel_and_failure(
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    messages: list[str] = []
    errors: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda title, *_args, **_kwargs: messages.append(title),
    )
    mocker.patch.object(instance, "_error", new=errors.append)

    mocker.patch.object(instance, "_menu", return_value=1)
    loader = mocker.patch.object(instance, "_load_retrobios_catalogue")
    instance._update_retrobios_catalogue()
    loader.assert_not_called()

    mocker.patch.object(instance, "_menu", return_value=0)
    loader.side_effect = BiosDownloadCancelled("cancelled")
    instance._update_retrobios_catalogue()
    assert messages[-1] == "RETROBIOS UPDATE CANCELLED"

    loader.side_effect = BiosError("metadata unavailable")
    instance._update_retrobios_catalogue()
    assert errors[-1] == "metadata unavailable"


def test_retrobios_cache_shortcut_and_uninitialized_label(mocker: MockerFixture) -> None:
    instance = bare_tui()
    catalog = bios_catalog_fixture()
    instance.retrobios_catalog = catalog
    assert instance._load_retrobios_catalogue() is catalog

    assert instance._retrobios_cache_label() == "not downloaded"


def test_manual_bios_search_handles_cancelled_loading_and_keyboard(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.roms_directories = (tmp_path,)
    mocker.patch.object(
        instance,
        "_load_retrobios_catalogue",
        side_effect=BiosDownloadCancelled("cancelled"),
    )
    instance._bios_search_flow()

    mocker.patch.object(instance, "_load_retrobios_catalogue", return_value=bios_catalog_fixture())
    keyboard = mocker.patch.object(instance, "_on_screen_keyboard", return_value=None)
    instance._bios_search_flow()
    keyboard.assert_called_once()


def test_manual_bios_search_shows_valid_and_unavailable_details(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    base_catalog = bios_catalog_fixture()
    base = base_catalog.requirements_for(gba)[0]
    unavailable = replace(
        base,
        name="optional.bin",
        destination="optional.bin",
        required=False,
        source_path=None,
        note="Only used by one optional core",
    )
    duplicate = replace(base)
    catalog = RetroBiosCatalog(
        base_catalog.revision,
        {
            "nintendo-gba": BiosSystem(
                "nintendo-gba",
                "Nintendo - Game Boy Advance",
                "gpsp",
                None,
                (base, duplicate, unavailable),
            )
        },
        "today",
        "v1",
    )
    bios = tmp_path / "bios/gba_bios.bin"
    bios.parent.mkdir(parents=True)
    bios.write_bytes(b"bios")
    instance = bare_tui()
    instance.roms_directories = (tmp_path,)
    instance.platforms = (
        Platform("No Folder", "no-folder", "NONE", "NONE"),
        Platform("No Metadata", "no-metadata", "NONE", "NONE", "none"),
        gba,
    )
    mocker.patch.object(instance, "_load_retrobios_catalogue", return_value=catalog)
    mocker.patch.object(instance, "_on_screen_keyboard", return_value="")
    choices = iter((0, 1, None))
    mocker.patch.object(instance, "_menu", new=lambda *_args: next(choices))
    messages: list[tuple[str, str]] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda title, message, *_args, **_kwargs: messages.append((title, message)),
    )

    instance._bios_search_flow()

    assert len(messages) == 2
    assert "Status: VALID" in messages[0][1]
    assert "Only used by one optional core" in messages[1][1]
    assert "no downloadable file" in messages[1][1]


def test_bios_followup_handles_no_requirements_and_long_missing_list(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    base_catalog = bios_catalog_fixture()
    base = base_catalog.requirements_for(gba)[0]
    requirements = tuple(
        replace(base, name=f"bios-{index}.bin", destination=f"bios-{index}.bin")
        for index in range(9)
    )
    catalog = RetroBiosCatalog(
        base_catalog.revision,
        {
            "nintendo-gba": BiosSystem(
                "nintendo-gba",
                "Nintendo - Game Boy Advance",
                "gpsp",
                None,
                requirements,
            )
        },
        "today",
        "v1",
    )
    instance = bare_tui()
    instance.roms_directories = (tmp_path,)
    mocker.patch.object(instance, "_load_retrobios_catalogue", return_value=catalog)
    messages: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda _title, message, *_args, **_kwargs: messages.append(message),
    )
    mocker.patch.object(instance, "_menu", return_value=1)
    assert instance._bios_followup(gba, tmp_path, None) == 0
    assert "...and 1 more" in messages[0]

    empty = RetroBiosCatalog("a" * 40, {}, "today", "v1")
    mocker.patch.object(instance, "_load_retrobios_catalogue", return_value=empty)
    assert instance._bios_followup(gba, tmp_path, None) == 0


def test_bios_download_helpers_reject_entries_without_sources(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    catalog = bios_catalog_fixture()
    requirement = replace(catalog.requirements_for(gba)[0], source_path=None)
    check = BiosCheck(requirement, BiosState.MISSING, (tmp_path / "bios/missing.bin",))
    instance = bare_tui()
    messages: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda title, *_args, **_kwargs: messages.append(title),
    )
    assert instance._confirm_retrobios_download((check,)) is False
    assert messages[-1] == "BIOS NOT DOWNLOADABLE"
    assert instance._install_bios_checks(catalog, (check,), gba, tmp_path) == 0


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


def test_changed_minerva_torrent_prompts_and_retries_selected_file(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.config = Config("url", tmp_path, (), timeout_seconds=1.0)
    instance.preferences = Preferences("minerva")
    mocker.patch.object(instance, "_poll_input", return_value=None)
    mocker.patch.object(instance, "_progress")
    choice = TorrentFileChoice(8, ("renamed", "Game Rev 2.zip"), 2048, 0.88)
    selection = DownloadSelectionRequired(
        TorrentSelectionRequired("torrent", "Game.zip", 3, (choice,), 100)
    )
    result = DownloadResult("torrent", tmp_path / choice.filename)
    attempts: list[tuple[str | MediaDownload, ...]] = []

    def downloaded(
        downloads: tuple[str | MediaDownload, ...],
        *_args: object,
        **_kwargs: object,
    ) -> list[DownloadResult]:
        attempts.append(downloads)
        if len(attempts) == 1:
            raise selection
        return [result]

    mocker.patch.object(tui_module, "download_files", downloaded)
    mocker.patch.object(instance, "_choose_torrent_file", return_value=choice)
    request = MediaDownload("torrent", 3, "Game.zip")

    assert instance._download_media([request], FakeStore()) == [result]
    retried = attempts[1][0]
    assert isinstance(retried, MediaDownload)
    assert retried.torrent_file_index == 8
    assert retried.expected_filename == "Game Rev 2.zip"
    assert retried.torrent_file_path == ("renamed", "Game Rev 2.zip")


def test_torrent_file_choice_shows_context_and_requires_confirmation(
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    candidate = TorrentFileChoice(4, ("folder", "Game Rev 2.zip"), 2 * 1024**2, 0.91)
    error = DownloadSelectionRequired(
        TorrentSelectionRequired("torrent", "Game.zip", 2, (candidate,), 50)
    )
    messages: list[str] = []
    mocker.patch.object(
        instance,
        "_draw_message",
        new=lambda _title, message, *_args, **_kwargs: messages.append(message),
    )
    choices = iter((0, 1))
    mocker.patch.object(instance, "_menu", side_effect=lambda *_args: next(choices))

    assert instance._choose_torrent_file(error) == candidate
    context = "\n".join(messages)
    assert "Game.zip" in context
    assert "folder/Game Rev 2.zip" in context
    assert "#2" in context and "#4" in context
    assert "2.0 MiB" in context and "91%" in context

    mocker.patch.object(instance, "_menu", return_value=None)
    assert instance._choose_torrent_file(error) is None
    assert instance._format_file_size(500) == "500 B"
    assert instance._format_file_size(2 * 1024) == "2.0 KiB"
    assert instance._format_file_size(2 * 1024**3) == "2.0 GiB"


def test_changed_minerva_torrent_can_be_cancelled(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    instance.config = Config("url", tmp_path, ())
    instance.preferences = Preferences("minerva")
    choice = TorrentFileChoice(2, ("candidate.zip",), 10, 0.5)
    error = DownloadSelectionRequired(
        TorrentSelectionRequired("torrent", "expected.zip", 1, (choice,), 3)
    )
    mocker.patch.object(tui_module, "download_files", side_effect=error)
    mocker.patch.object(instance, "_poll_input", return_value=None)
    mocker.patch.object(instance, "_progress")
    mocker.patch.object(instance, "_choose_torrent_file", return_value=None)

    with pytest.raises(DownloadCancelled):
        instance._download_media([MediaDownload("torrent", 1, "expected.zip")], FakeStore())


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


def test_keyboard_uses_fixed_darkos_grid_and_exposes_symbols_and_accents(
    mocker: MockerFixture,
) -> None:
    letters = _keyboard_rows("letters", True)
    symbols = _keyboard_rows("symbols", True)
    accents = _keyboard_rows("accents", False)
    assert all(sum(key.span for key in row) == 12 for row in letters)
    assert all(key.span == 1 for row in letters[:4] for key in row)
    assert all(key.span == 2 for key in letters[-1])
    assert {"@", "?", "€", chr(0xD7)} <= {key.value for row in symbols[:4] for key in row}
    assert {"à", "é", "ñ", "ø"} <= {key.value for row in accents[:4] for key in row}

    screen = RecordingScreen()
    instance = bare_tui(screen)
    mocker.patch.object(instance, "_get_input", return_value=GAMEPAD_SEARCH_KEY)
    assert instance._on_screen_keyboard("SEARCH") == ""
    first_row = sorted((x, text) for y, x, text, _attribute in screen.writes if y == 6)
    assert len(first_row) == 12
    assert len({len(text) for _x, text in first_row}) == 1
    assert len({right[0] - left[0] for left, right in pairwise(first_row)}) == 1

    instance = bare_tui()
    inputs = iter((curses.KEY_UP, curses.KEY_RIGHT, 10, curses.KEY_UP, 10, GAMEPAD_SEARCH_KEY))
    mocker.patch.object(instance, "_get_input", new=lambda *_args: next(inputs))
    assert instance._on_screen_keyboard("SEARCH") == "¥"


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ((27,), None),
        (
            (ord("a"), curses.KEY_UP, *(curses.KEY_RIGHT,) * 3, 10, ord("b"), GAMEPAD_SEARCH_KEY),
            "a b",
        ),
        ((ord("a"), curses.KEY_UP, *(curses.KEY_RIGHT,) * 4, 10, GAMEPAD_SEARCH_KEY), ""),
        ((ord("a"), curses.KEY_UP, *(curses.KEY_RIGHT,) * 5, 10), "a"),
        ((curses.KEY_UP, 10, curses.KEY_DOWN, curses.KEY_DOWN, 10, GAMEPAD_SEARCH_KEY), "q"),
        ((curses.KEY_UP, *(curses.KEY_RIGHT,) * 2, 10, curses.KEY_UP, 10, GAMEPAD_SEARCH_KEY), "Ś"),
    ],
)
def test_keyboard_action_keys_and_pages(
    keys: tuple[int, ...],
    expected: str | None,
    mocker: MockerFixture,
) -> None:
    instance = bare_tui()
    inputs = iter(keys)
    mocker.patch.object(instance, "_get_input", new=lambda *_args: next(inputs))
    assert instance._on_screen_keyboard("SEARCH", empty_hint="Type a title") == expected


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
