"""Controller-friendly full-screen terminal interface."""

import contextlib
import curses
import locale
import logging
import textwrap
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Lock
from typing import Any

from dw_cli.bittorrent import BitTorrentSettings, TorrentFileChoice
from dw_cli.cache_policy import catalogue_ttl_seconds
from dw_cli.compatibility import (
    CompatibilityError,
    CompatibilityInfo,
    R36SCompatibilityClient,
    filter_supported_results,
)
from dw_cli.config import Config
from dw_cli.downloader import (
    DownloadCancelled,
    DownloadError,
    DownloadSelectionRequired,
    download_files,
)
from dw_cli.frontend import request_emulationstation_refresh
from dw_cli.gamepad import InputAction, LinuxJoystick
from dw_cli.hardware import detect_hardware_profile
from dw_cli.library import (
    LibraryError,
    delete_game,
    platforms_with_installed_games,
    replace_game,
    scan_library,
)
from dw_cli.logging_config import configure_logging
from dw_cli.models import DownloadResult, InstalledGame, MediaDownload, Platform, SearchResult
from dw_cli.organizer import (
    OrganizeError,
    detect_roms_directories,
    install_bundled_bios,
    move_to_arkos,
)
from dw_cli.platforms import discover_platforms, resolve_platform
from dw_cli.preferences import (
    Preferences,
    PreferencesError,
    load_preferences,
    preference_path,
    save_preferences,
)
from dw_cli.retrobios import (
    BiosCheck,
    BiosDownloadCancelled,
    BiosError,
    BiosState,
    RetroBiosCatalog,
    RetroBiosRepository,
    audit_bios,
    audit_bios_roots,
    install_bios,
    unresolved,
)
from dw_cli.store import GameStore, StoreError
from dw_cli.store_cache import CatalogueCacheError, StoreCacheStatus
from dw_cli.store_catalog import StoreCatalog
from dw_cli.updater import (
    ReleaseUpdate,
    UpdateCancelled,
    UpdateError,
    find_update,
    installed_version,
    stage_update,
)

type Window = Any

LOGGER = logging.getLogger(__name__)

GAMEPAD_START_KEY = 0x110000
GAMEPAD_SEARCH_KEY = 0x110001
GAMEPAD_NOOP_KEY = 0x110002

GAMEPAD_KEYS: dict[InputAction, int] = {
    InputAction.UP: curses.KEY_UP,
    InputAction.DOWN: curses.KEY_DOWN,
    # dArkOS maps the R36S horizontal stick directions as menu buttons.
    InputAction.LEFT: 27,
    InputAction.RIGHT: 10,
    InputAction.SELECT: 10,
    InputAction.BACK: 27,
    InputAction.BACKSPACE: curses.KEY_BACKSPACE,
    InputAction.SUBMIT_SEARCH: GAMEPAD_NOOP_KEY,
    InputAction.PAGE_UP: curses.KEY_PPAGE,
    InputAction.PAGE_DOWN: curses.KEY_NPAGE,
    InputAction.START: GAMEPAD_START_KEY,
}

KEYBOARD_GAMEPAD_KEYS: dict[InputAction, int] = {
    **GAMEPAD_KEYS,
    InputAction.LEFT: curses.KEY_LEFT,
    InputAction.RIGHT: curses.KEY_RIGHT,
    InputAction.SUBMIT_SEARCH: GAMEPAD_SEARCH_KEY,
    InputAction.START: GAMEPAD_NOOP_KEY,
}


@dataclass(frozen=True, slots=True)
class KeyboardKey:
    """One key in the fixed twelve-column dArkOS-style keyboard grid."""

    label: str
    value: str = ""
    action: str | None = None
    span: int = 1


_KEYBOARD_LETTER_ROWS: tuple[tuple[str, ...], ...] = (
    tuple("1234567890-="),
    tuple("QWERTYUIOP[]"),
    tuple("ASDFGHJKL;'#"),
    ("Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "`", "\\"),
)
_KEYBOARD_SYMBOL_ROWS: tuple[tuple[str, ...], ...] = (
    ("!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "_", "+"),
    ("{", "}", "[", "]", "<", ">", "|", "~", ":", ";", '"', "'"),
    ("?", "/", "\\", "=", "-", ".", ",", "&", "%", "$", "@", "#"),
    ("€", "£", "¥", "©", "®", "°", "±", "×", "÷", "§", "¶", "•"),  # noqa: RUF001
)
_KEYBOARD_ACCENT_ROWS: tuple[tuple[str, ...], ...] = (
    tuple("ÀÁÂÃÄÅÆÇÈÉÊË"),
    tuple("ÌÍÎÏÑÒÓÔÕÖØŒ"),
    tuple("ÙÚÛÜÝŸŠŽÐÞŁĆ"),
    tuple("ČĐĞİŚŞŤŹŻÑÕØ"),
)


def _keyboard_rows(page: str, uppercase: bool) -> tuple[tuple[KeyboardKey, ...], ...]:
    if page == "symbols":
        character_rows = _KEYBOARD_SYMBOL_ROWS
    elif page == "accents":
        character_rows = _KEYBOARD_ACCENT_ROWS
    else:
        character_rows = _KEYBOARD_LETTER_ROWS
    if not uppercase and page != "symbols":
        character_rows = tuple(tuple(value.lower() for value in row) for row in character_rows)
    actions = (
        KeyboardKey("aA", action="case", span=2),
        KeyboardKey("#+=", action="symbols", span=2),
        KeyboardKey("ÁÉ", action="accents", span=2),
        KeyboardKey("SPACE", action="space", span=2),
        KeyboardKey("BACK", action="back", span=2),
        KeyboardKey("DONE", action="done", span=2),
    )
    return (
        *tuple(tuple(KeyboardKey(value, value) for value in row) for row in character_rows),
        actions,
    )


def _keyboard_key_center(row: Sequence[KeyboardKey], index: int) -> float:
    start = sum(key.span for key in row[:index])
    return start + row[index].span / 2


def _nearest_keyboard_key(row: Sequence[KeyboardKey], center: float) -> int:
    return min(range(len(row)), key=lambda index: abs(_keyboard_key_center(row, index) - center))


class TerminalTooSmall(RuntimeError):
    """The active terminal cannot display the interface."""


class DownloaderTui:
    """A compact curses UI designed for a 640x480 dArkOS R36S screen."""

    def __init__(self, screen: Window, config: Config) -> None:
        self.screen = screen
        self.config = config
        self.preferences_path = preference_path(config.download_directory)
        preferences = load_preferences(self.preferences_path)
        self.preferences = preferences
        ttl_seconds = catalogue_ttl_seconds(preferences.catalogue_ttl_days)
        self.store_catalog = StoreCatalog.from_config(config, ttl_seconds)
        self.retrobios_repository = RetroBiosRepository(
            config.download_directory,
            config.timeout_seconds,
            ttl_seconds,
        )
        self.retrobios_catalog: RetroBiosCatalog | None = None
        self.selected_store = (
            self.store_catalog.find(preferences.store_id) if preferences.store_id else None
        )
        self.refresh_on_exit = False
        self.exit_after_update = False
        self.compatibility_client = R36SCompatibilityClient(
            config.download_directory / ".r36s-game-list-cache.json",
            timeout_seconds=config.timeout_seconds,
            ttl_seconds=ttl_seconds,
        )
        self.roms_directories = detect_roms_directories(config.roms_directories or None)
        self.platforms = discover_platforms(self.roms_directories)
        self.hardware = detect_hardware_profile()
        self.gamepad = LinuxJoystick.open_first()
        self._apply_logging_preferences()
        LOGGER.debug(
            "Runtime detected model=%r display=%s roms=%s platforms=%d gamepad=%s",
            self.hardware.model,
            self.hardware.display_resolution,
            self.roms_directories,
            len(self.platforms),
            self.gamepad.path if self.gamepad is not None else "not detected",
        )
        self._setup_screen()

    def _setup_screen(self) -> None:
        try:
            locale.setlocale(locale.LC_ALL, "")
        except locale.Error:
            locale.setlocale(locale.LC_ALL, "C")
        with contextlib.suppress(curses.error):
            curses.curs_set(0)
        self.screen.keypad(True)
        self.screen.timeout(50)
        if curses.has_colors():
            with contextlib.suppress(curses.error):
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_CYAN, -1)
                curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
                curses.init_pair(3, curses.COLOR_YELLOW, -1)
                curses.init_pair(4, curses.COLOR_GREEN, -1)
                curses.init_pair(5, curses.COLOR_RED, -1)

    def run(self) -> None:
        LOGGER.info("TUI session started")
        try:
            if not self.store_catalog.stores:
                self._error("No download stores are enabled. Check DW_STORES.")
                return
            while self.selected_store is None:
                if self._configure_store(first_run=True):
                    break
                if self._confirm_exit():
                    return
            options = (
                "Search the library",
                "Download from a detail link",
                "Manage installed games",
                "Search and download BIOS",
                "Settings",
                "dArkOS status and controls",
                "Exit",
            )
            while True:
                choice = self._menu(
                    "DARKOS DOWNLOADER",
                    options,
                    "D-pad/stick: move   A/Enter: select",
                )
                if choice is None or choice == 6:
                    if self._confirm_exit():
                        return
                    continue
                if choice == 0:
                    self._search_flow()
                elif choice == 1:
                    self._direct_download_flow()
                elif choice == 2:
                    self._manage_library_flow()
                elif choice == 3:
                    self._bios_search_flow()
                elif choice == 4:
                    self._settings_screen()
                elif choice == 5:
                    self._status_screen()
                if self.exit_after_update:
                    return
        finally:
            if self.refresh_on_exit:
                LOGGER.info("Requesting EmulationStation refresh on TUI exit")
                request_emulationstation_refresh()
            if self.gamepad is not None:
                self.gamepad.close()
            LOGGER.info("TUI session finished")

    def _search_flow(self) -> None:
        store = self.selected_store
        if store is None:
            return
        platforms = tuple(
            platform for platform in self.platforms if store.supports_platform(platform)
        )
        labels = [f"{item.name}  [{item.alias}]" for item in platforms]
        while True:
            choice = self._menu("CHOOSE A PLATFORM", labels, "B/Esc: back")
            if choice is None:
                return
            self._search_platform_flow(store, platforms[choice])

    def _search_platform_flow(self, store: GameStore, platform: Platform) -> None:
        """Keep search navigation within one platform until the user goes back one level."""

        while True:
            query = self._on_screen_keyboard(
                f"SEARCH {platform.alias}",
                empty_hint="DONE with no text: list all games",
            )
            if query is None:
                return
            description = (
                f"Looking for {query}..." if query else f"Loading all {platform.name} games..."
            )
            self._draw_message("SEARCHING", description, 1)
            try:
                LOGGER.info(
                    "Searching store=%s platform=%s query=%r",
                    store.store_id,
                    platform.alias,
                    query,
                )
                results = store.search(store.platform_code(platform), query, self._catalog_progress)
            except StoreError as error:
                LOGGER.warning("Search failed: %s", error)
                self._error(str(error))
                continue
            results = filter_supported_results(results)
            if not results:
                message = f"Nothing matched {query}." if query else "The catalogue is empty."
                self._draw_message("NO RESULTS", message, 3, wait=True)
                continue
            self._draw_message(
                "CHECKING R36S SUPPORT",
                "Matching results against the cached R36S game list...",
                1,
            )
            compatibility = self.compatibility_client.lookup_many(results, platform)
            supported_pairs = [
                (result, info)
                for result, info in zip(results, compatibility, strict=True)
                if info.level != "Unsupported"
            ]
            self._results_flow(
                [result for result, _info in supported_pairs],
                platform,
                [info for _result, info in supported_pairs],
                store,
            )
            LOGGER.info("Search produced %d supported result(s)", len(supported_pairs))

    def _catalog_progress(self, current: int, total: int) -> None:
        percent = int(current * 100 / total)
        self._draw_message(
            "LOADING CATALOGUE",
            "Reading numeric and A-Z sections...\n%d/%d  (%d%%)" % (current, total, percent),
            1,
        )

    def _results_flow(
        self,
        results: Sequence[SearchResult],
        platform: Platform,
        compatibility: Sequence[CompatibilityInfo],
        store: GameStore,
    ) -> None:
        labels = []
        for result, info in zip(results, compatibility, strict=True):
            prefix = f"{result.system} | " if result.system else ""
            detail = f" - {result.region}" if result.region else ""
            labels.append(f"{prefix}{result.title}{detail}  [R36S: {info.short_label}]")
        while True:
            choice = self._menu(
                "%s RESULTS (%d)" % (store.display_name.upper(), len(results)),
                labels,
                "A/Enter: details   B/Esc: back",
            )
            if choice is None:
                return
            result = results[choice]
            info = compatibility[choice]
            effective_platform = platform
            if not platform.code and result.system:
                resolved = resolve_platform(result.system)
                if resolved is not None:
                    effective_platform = resolved
            details = [
                result.title,
                "System: %s" % (result.system or effective_platform.name),
                "Region: %s" % (result.region or "-"),
                "Version: %s" % (result.version or "-"),
                f"Languages: {result.languages}",
                f"Rating: {result.rating}",
                f"R36S: {info.detail_label}",
            ]
            action = self._menu("TITLE DETAILS", [*details, "Download", "Back"], "Select Download")
            if action == len(details):
                self._download_detail(
                    result.link,
                    effective_platform,
                    store,
                    region=result.region,
                )
            elif action is None or action == len(details) + 1:
                continue

    def _direct_download_flow(self) -> None:
        store = self.selected_store
        if store is None:
            return
        platforms = tuple(
            platform
            for platform in self.platforms
            if platform.arkos_folder is not None and store.supports_platform(platform)
        )
        choice = self._menu(
            "DESTINATION PLATFORM",
            [f"{item.name} -> {item.arkos_folder}" for item in platforms],
            "The completed file is moved into this ROM folder",
        )
        if choice is None:
            return
        url = self._on_screen_keyboard("DETAIL URL", allow_lowercase=True)
        if not url:
            return
        self._download_detail(url, platforms[choice], store)

    def _download_detail(
        self,
        detail_url: str,
        platform: Platform,
        store: GameStore,
        *,
        region: str | None = None,
    ) -> None:
        if platform.arkos_folder is None:
            self._error("This platform has no dArkOS ROM folder on supported handhelds.")
            return
        roms_directory = self._choose_roms_directory()
        if roms_directory is None:
            self._error("No dArkOS ROM partition found. Set DW_ROMS_DIR or DW_ROMS_DIRS.")
            return
        self._draw_message("PREPARING", "Retrieving the download link...", 1)
        installed_bios: list[Path] = []
        try:
            media_url = store.download_request(detail_url)
            downloads = self._download_media(
                [media_url],
                store,
            )
            completed = move_to_arkos(
                downloads,
                platform,
                roms_directory,
                installed_bios.append,
            )
        except DownloadCancelled:
            LOGGER.info("Game download cancelled")
            self._draw_message("DOWNLOAD CANCELLED", "No game was installed.", 3)
            return
        except (StoreError, DownloadError, OrganizeError) as error:
            LOGGER.error("Game download failed: %s", error)
            self._error(str(error))
            return
        final_path = completed[0].path
        retrobios_installed = self._bios_followup(platform, roms_directory, region)
        self.refresh_on_exit = True
        LOGGER.info("Game installed path=%s bios_files=%d", final_path, len(installed_bios))
        bios_message = (
            "\nInstalled %d bundled BIOS file(s)." % len(installed_bios) if installed_bios else ""
        )
        if retrobios_installed:
            bios_message += "\nInstalled %d required BIOS file(s) from RetroBIOS." % (
                retrobios_installed
            )
        self._draw_message(
            "DOWNLOAD COMPLETE",
            f"{final_path.name}\nMoved to {final_path.parent}{bios_message}"
            "\nThe game list will refresh when you exit the downloader.",
            4,
            wait=True,
        )

    def _manage_library_flow(self) -> None:
        if not self.roms_directories:
            self._error("No dArkOS ROM partitions were found.")
            return
        while True:
            root = self._choose_from_roots(self.roms_directories, "CHOOSE MEMORY CARD")
            if root is None:
                return
            self._draw_message("CHECKING FOLDERS", f"Finding installed platforms on {root}...", 1)
            platforms = platforms_with_installed_games(root, self.platforms)
            if not platforms:
                self._draw_message(
                    "NO GAMES ON CARD",
                    f"No supported game files were found on {root}.",
                    3,
                    wait=True,
                )
                continue
            platform_choice = self._menu(
                "CHOOSE INSTALLED PLATFORM",
                [platform.name for platform in platforms],
                "Platforms are detected quickly; games load after selection",
            )
            if platform_choice is None:
                continue
            self._manage_platform_library(root, platforms[platform_choice])

    def _manage_platform_library(self, root: Path, platform: Platform) -> None:
        self._draw_message(
            "SCANNING PLATFORM",
            f"Reading only {platform.name} on {root}...",
            1,
        )
        games = scan_library((root,), (platform,))
        if not games:
            self._draw_message("NO GAMES", f"No {platform.name} games were found.", 3, wait=True)
            return
        while games:
            game_choice = self._menu(
                f"{platform.alias} ON {root}",
                [game.title for game in games],
                "A: manage   B: back   L1/R1: page",
            )
            if game_choice is None:
                return
            if self._manage_game(games[game_choice]):
                self._draw_message(
                    "REFRESHING",
                    f"Refreshing {platform.name} only...",
                    1,
                )
                games = scan_library((root,), (platform,))

    def _manage_game(self, game: InstalledGame) -> bool:
        description = (
            game.title,
            f"Card: {game.roms_directory}",
            f"File: {game.primary_file.name}",
            "Files in group: %d" % len(game.files),
            "Update from remote",
            "Delete from device",
            "Back",
        )
        choice = self._menu("MANAGE GAME", description, "Updates keep the same card and platform")
        if choice == 4:
            return self._update_game(game)
        if choice == 5:
            return self._confirm_delete(game)
        return False

    def _confirm_delete(self, game: InstalledGame) -> bool:
        choice = self._menu(
            "CONFIRM PERMANENT DELETE",
            (
                f"No - keep {game.title}",
                "Yes - delete %d file(s)" % len(game.files),
            ),
            "Deleted files cannot be recovered",
        )
        if choice != 1:
            return False
        try:
            delete_game(game)
        except LibraryError as error:
            LOGGER.error("Could not delete game title=%r: %s", game.title, error)
            self._error(str(error))
            return False
        self.refresh_on_exit = True
        LOGGER.info("Deleted game title=%r files=%d", game.title, len(game.files))
        self._draw_message(
            "GAME DELETED",
            game.title + "\nThe game list will refresh when you exit the downloader.",
            4,
            wait=True,
        )
        return True

    def _update_game(self, game: InstalledGame) -> bool:
        store = self.selected_store
        if store is None:
            return False
        if not store.supports_platform(game.platform):
            self._error(
                f"{store.display_name} does not support {game.platform.name}. "
                "Choose another store in Settings."
            )
            return False
        self._draw_message("SEARCHING FOR UPDATE", game.title, 1)
        try:
            results = store.search(store.platform_code(game.platform), game.title)
        except StoreError as error:
            self._error(str(error))
            return False
        if not results:
            self._draw_message("NO REMOTE MATCH", game.title, 3, wait=True)
            return False
        choice = self._menu(
            "CHOOSE REPLACEMENT",
            [
                "{} - {} - {}".format(result.title, result.region or "-", result.version or "-")
                for result in results
            ],
            "The old game is removed only after download completes",
        )
        if choice is None:
            return False
        selected = results[choice]
        confirmation = self._menu(
            "CONFIRM UPDATE",
            (
                f"Cancel - keep {game.primary_file.name}",
                f"Replace with {selected.title}",
            ),
            "A/Enter: confirm choice",
        )
        if confirmation != 1:
            return False
        try:
            media_url = store.download_request(selected.link)
            downloads = self._download_media(
                [media_url],
                store,
            )
            installed_bios = install_bundled_bios(
                downloads[0].path,
                game.platform,
                game.roms_directory,
            )
            completed = replace_game(game, downloads[0])
        except DownloadCancelled:
            LOGGER.info("Game update cancelled title=%r", game.title)
            self._draw_message("UPDATE CANCELLED", "The installed game was not changed.", 3)
            return False
        except (StoreError, DownloadError, LibraryError, OrganizeError) as error:
            LOGGER.error("Game update failed title=%r: %s", game.title, error)
            self._error(str(error))
            return False
        self.refresh_on_exit = True
        retrobios_installed = self._bios_followup(
            game.platform,
            game.roms_directory,
            selected.region,
        )
        LOGGER.info("Game updated title=%r path=%s", game.title, completed.path)
        self._draw_message(
            "GAME UPDATED",
            "{}\nInstalled on {}{}".format(
                completed.path.name,
                game.roms_directory,
                "\nInstalled %d bundled BIOS file(s)." % len(installed_bios)
                if installed_bios
                else "",
            )
            + (
                "\nInstalled %d required BIOS file(s) from RetroBIOS." % retrobios_installed
                if retrobios_installed
                else ""
            )
            + "\nThe game list will refresh when you exit the downloader.",
            4,
            wait=True,
        )
        return True

    def _choose_roms_directory(self) -> Path | None:
        return self._choose_from_roots(self.roms_directories, "CHOOSE DESTINATION CARD")

    def _choose_store(self, title: str, platform: Platform | None = None) -> GameStore | None:
        stores = tuple(
            store
            for store in self.store_catalog.stores
            if platform is None or store.supports_platform(platform)
        )
        choice = self._menu(
            title,
            [f"{store.display_name} - {store.description}" for store in stores],
            "More download stores can be added without changing the TUI",
        )
        return stores[choice] if choice is not None else None

    def _configure_store(self, *, first_run: bool = False) -> bool:
        title = "FIRST-RUN DOWNLOAD STORE" if first_run else "CHOOSE DEFAULT STORE"
        store = self._choose_store(title)
        if store is None:
            return False
        preferences = load_preferences(self.preferences_path)
        updated_preferences = replace(preferences, store_id=store.store_id)
        try:
            save_preferences(self.preferences_path, updated_preferences)
        except PreferencesError as error:
            self._error(str(error))
            return False
        self.preferences = updated_preferences
        self.selected_store = store
        LOGGER.info("Default store changed to %s", store.store_id)
        if not first_run:
            self._draw_message(
                "SETTINGS SAVED",
                f"Searches, downloads, and updates will use {store.display_name}.",
                4,
                wait=True,
            )
        return True

    def _settings_screen(self) -> None:
        while True:
            current = (
                self.selected_store.display_name if self.selected_store is not None else "not set"
            )
            retrobios_status = self._retrobios_cache_label()
            compatibility_status = self._compatibility_cache_label()
            game_catalogue_count = sum(
                store.catalogue_cache_file_count() for store in self.store_catalog.stores
            )
            options = [
                f"Change download store  [current: {current}]",
                f"Refresh store game catalogue  [{game_catalogue_count} cached]",
                f"Update RetroBIOS catalogue  [{retrobios_status}]",
                f"Update R36S Game List  [{compatibility_status}]",
                f"Catalogue cache lifetime  [{self.preferences.catalogue_ttl_days} days]",
                f"Application log level  [{self.preferences.log_level or self.config.log_level}]",
                f"Write logs to file  [{'on' if self._file_logging_enabled() else 'off'}]",
            ]
            actions = [
                "store",
                "store_catalogue",
                "retrobios_update",
                "compatibility_update",
                "catalogue_ttl",
                "log_level",
                "log_file",
            ]
            if self.selected_store is not None and self.selected_store.store_id == "minerva":
                options.append("Minerva BitTorrent settings")
                actions.append("minerva")
            options.extend(
                (
                    f"Check for application update  [installed: v{installed_version()}]",
                    "Back",
                )
            )
            actions.extend(("update", "back"))
            choice = self._menu(
                "SETTINGS",
                options,
                "Store settings and self-contained R36S updates",
            )
            if choice is None or actions[choice] == "back":
                return
            action = actions[choice]
            if action == "store":
                self._configure_store()
            elif action == "store_catalogue":
                self._refresh_store_catalogue()
            elif action == "retrobios_update":
                self._update_retrobios_catalogue()
            elif action == "compatibility_update":
                self._update_compatibility_catalogue()
            elif action == "catalogue_ttl":
                self._configure_catalogue_ttl()
            elif action == "log_level":
                self._configure_log_level()
            elif action == "log_file":
                self._configure_file_logging()
            elif action == "minerva":
                self._minerva_bittorrent_settings_screen()
            elif action == "update":
                self._application_update_flow()
            if self.exit_after_update:
                return

    def _configure_catalogue_ttl(self) -> None:
        raw_value = self._on_screen_keyboard(
            "CATALOGUE CACHE DAYS",
            empty_hint=f"Current: {self.preferences.catalogue_ttl_days}; default: 7",
        )
        if raw_value is None:
            return
        try:
            days = int(raw_value)
            if not 1 <= days <= 3650:
                raise ValueError("enter a value from 1 to 3650 days")
        except ValueError as error:
            self._error(f"Invalid catalogue lifetime: {error}")
            return
        self._save_runtime_preferences(
            replace(self.preferences, catalogue_ttl_days=days),
            "CACHE LIFETIME SAVED",
            f"Catalogue files now expire after {days} day(s).",
        )

    def _configure_log_level(self) -> None:
        levels = ("DEBUG", "INFO", "WARNING", "ERROR")
        choice = self._menu(
            "APPLICATION LOG LEVEL",
            levels,
            "The selected level applies immediately",
        )
        if choice is None:
            return
        level = levels[choice]
        self._save_runtime_preferences(
            replace(self.preferences, log_level=level),
            "LOG LEVEL SAVED",
            f"Application logging is now set to {level}.",
        )

    def _configure_file_logging(self) -> None:
        choice = self._menu(
            "WRITE LOGS TO FILE?",
            ("Off", "On"),
            "Changes apply immediately and are saved for the next launch",
        )
        if choice is None:
            return
        enabled = choice == 1
        self._save_runtime_preferences(
            replace(self.preferences, log_to_file=enabled),
            "FILE LOGGING SAVED",
            "File logging is enabled." if enabled else "File logging is disabled.",
        )

    def _save_runtime_preferences(
        self,
        preferences: Preferences,
        title: str,
        message: str,
    ) -> bool:
        try:
            save_preferences(self.preferences_path, preferences)
        except PreferencesError as error:
            self._error(str(error))
            return False
        self.preferences = preferences
        self._apply_runtime_preferences()
        self._draw_message(title, message, 4, wait=True)
        return True

    def _apply_runtime_preferences(self) -> None:
        ttl_seconds = catalogue_ttl_seconds(self.preferences.catalogue_ttl_days)
        for store in self.store_catalog.stores:
            store.set_catalogue_ttl(ttl_seconds)
        self.retrobios_repository.ttl_seconds = ttl_seconds
        if self.retrobios_catalog is not None:
            self.retrobios_catalog.ttl_seconds = ttl_seconds
        self.compatibility_client.ttl_seconds = ttl_seconds
        self._apply_logging_preferences()

    def _file_logging_enabled(self) -> bool:
        if self.preferences.log_to_file is not None:
            return self.preferences.log_to_file
        return self.config.log_file is not None

    def _apply_logging_preferences(self) -> None:
        log_file = None
        if self._file_logging_enabled():
            log_file = (
                self.config.log_file or self.config.download_directory / "darkos-downloader.log"
            )
        configure_logging(log_file, self.preferences.log_level or self.config.log_level)

    def _refresh_store_catalogue(self) -> None:
        stores = self.store_catalog.stores
        while True:
            store_choice = self._menu(
                "CHOOSE STORE CATALOGUE",
                [
                    f"{store.display_name}  [{store.catalogue_cache_file_count()} cached]"
                    for store in stores
                ],
                "Select a store; B/Escape returns",
            )
            if store_choice is None:
                return
            store = stores[store_choice]
            choices: list[tuple[Platform, str, StoreCacheStatus | None]] = []
            seen_codes: set[str] = set()
            for platform in self.platforms:
                if not store.supports_platform(platform):
                    continue
                system_code = store.platform_code(platform)
                if system_code in seen_codes:
                    continue
                seen_codes.add(system_code)
                choices.append((platform, system_code, store.catalogue_cache_status(system_code)))
            platform_choice = self._menu(
                f"REFRESH {store.display_name.upper()}",
                [
                    f"{platform.name}  [{self._store_cache_status_label(status)}]"
                    for platform, _system_code, status in choices
                ],
                "This replaces the selected cache even before its configured lifetime expires",
            )
            if platform_choice is None:
                continue
            platform, system_code, _status = choices[platform_choice]
            self._draw_message(
                "REFRESHING GAME CATALOGUE",
                f"Downloading the complete {store.display_name} catalogue for {platform.name}...",
                1,
            )
            try:
                results = store.refresh_catalogue(system_code, self._catalog_progress)
            except (CatalogueCacheError, StoreError) as error:
                self._error(str(error))
                return
            self._draw_message(
                "GAME CATALOGUE UPDATED",
                f"Cached {len(results)} {store.display_name} result(s) for {platform.name}.",
                4,
                wait=True,
            )
            return

    @staticmethod
    def _store_cache_status_label(status: StoreCacheStatus | None) -> str:
        if status is None:
            return "not downloaded"
        freshness = "stale" if status.stale else "fresh"
        return f"{freshness}, {status.result_count} games"

    def _retrobios_cache_label(self) -> str:
        if not hasattr(self, "retrobios_repository"):
            return "not downloaded"
        try:
            catalogue = self.retrobios_repository.load()
        except BiosError:
            return "cache invalid"
        if catalogue is None:
            return "not downloaded"
        freshness = (
            f"stale (>{self.preferences.catalogue_ttl_days} days)"
            if catalogue.cache_is_stale()
            else "fresh"
        )
        return f"{catalogue.revision[:8]} - {freshness}"

    def _compatibility_cache_label(self) -> str:
        if not hasattr(self, "compatibility_client"):
            return "not downloaded"
        age = self.compatibility_client.cache_age_seconds()
        if age is None:
            return "not downloaded"
        return (
            f"stale (>{self.preferences.catalogue_ttl_days} days)"
            if self.compatibility_client.cache_is_stale()
            else "fresh"
        )

    def _update_compatibility_catalogue(self) -> None:
        choice = self._menu(
            "UPDATE R36S GAME LIST?",
            ("Download latest compatibility catalogue", "Keep current catalogue"),
            "The existing offline cache is kept if the update fails",
        )
        if choice != 0:
            return
        self._draw_message(
            "UPDATING R36S GAME LIST",
            "Downloading the current frontend compatibility catalogue...",
            1,
        )
        try:
            count = self.compatibility_client.refresh()
        except CompatibilityError as error:
            self._error(str(error))
            return
        self._draw_message(
            "R36S GAME LIST UPDATED",
            f"Cached {count} game title(s). The catalogue is valid for "
            f"{self.preferences.catalogue_ttl_days} day(s).",
            4,
            wait=True,
        )

    def _load_retrobios_catalogue(self, *, update: bool = False) -> RetroBiosCatalog:
        if not update and self.retrobios_catalog is not None:
            return self.retrobios_catalog
        cancelled = Event()
        state_lock = Lock()
        progress_state: list[str | int | None] = ["Connecting to RetroBIOS...", 0, None]

        def report(label: str, current: int, total: int | None) -> None:
            with state_lock:
                progress_state[:] = [label, current, total]

        operation = self.retrobios_repository.update if update else self.retrobios_repository.ensure
        with ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="retrobios-catalogue",
        ) as executor:
            future = executor.submit(operation, report, cancelled.is_set)
            while not future.done():
                with state_lock:
                    label, current, total = progress_state
                assert isinstance(label, str)
                assert isinstance(current, int)
                assert total is None or isinstance(total, int)
                self._progress(label, current, total)
                pressed = self._poll_input()
                if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                    cancelled.set()
            catalogue = future.result()
        self.retrobios_catalog = catalogue
        return catalogue

    def _update_retrobios_catalogue(self) -> None:
        choice = self._menu(
            "UPDATE RETROBIOS CATALOGUE?",
            ("Download latest metadata", "Keep current catalogue"),
            "The existing offline cache is kept if the update fails",
        )
        if choice != 0:
            return
        try:
            catalogue = self._load_retrobios_catalogue(update=True)
        except BiosDownloadCancelled:
            self._draw_message(
                "RETROBIOS UPDATE CANCELLED",
                "The existing catalogue was not changed.",
                3,
                wait=True,
            )
            return
        except BiosError as error:
            self._error(str(error))
            return
        self._draw_message(
            "RETROBIOS UPDATED",
            "Revision: {}\nSystems: {}\nRetroArch profile: {}".format(
                catalogue.revision[:12],
                len(catalogue.systems),
                catalogue.retroarch_version or "unknown",
            ),
            4,
            wait=True,
        )

    def _bios_search_flow(self) -> None:
        root = self._choose_from_roots(self.roms_directories, "CHOOSE BIOS MEMORY CARD")
        if root is None:
            self._error("No dArkOS ROM partition was found.")
            return
        try:
            catalogue = self._load_retrobios_catalogue()
        except BiosDownloadCancelled:
            return
        except BiosError as error:
            self._error(str(error))
            return
        query = self._on_screen_keyboard(
            "SEARCH BIOS",
            empty_hint="DONE with no text: list the full R36S BIOS catalogue",
        )
        if query is None:
            return
        normalized = query.casefold().strip()
        entries: list[tuple[Platform, BiosCheck]] = []
        seen: set[tuple[str, str, str]] = set()
        for platform in self.platforms:
            if platform.arkos_folder is None:
                continue
            system = catalogue.system_for(platform)
            if system is None:
                continue
            for check in audit_bios(system.requirements, platform, root):
                requirement = check.requirement
                haystack = " ".join(
                    (
                        platform.name,
                        platform.alias,
                        system.name,
                        requirement.name,
                        requirement.description or "",
                        requirement.region or "",
                    )
                ).casefold()
                if normalized and normalized not in haystack:
                    continue
                key = (
                    platform.slug,
                    requirement.destination.casefold(),
                    requirement.sha256 or requirement.sha1 or requirement.md5 or "",
                )
                if key in seen:
                    continue
                seen.add(key)
                entries.append((platform, check))
        if not entries:
            self._draw_message(
                "NO BIOS RESULTS",
                f"Nothing matched {query}." if query else "The R36S BIOS catalogue is empty.",
                3,
                wait=True,
            )
            return
        while True:
            choice = self._menu(
                f"BIOS RESULTS ({len(entries)})",
                [
                    f"{platform.alias} | {self._bios_check_label(check)}"
                    for platform, check in entries
                ],
                "Select a BIOS to inspect or download; B/Escape returns",
            )
            if choice is None:
                return
            platform, old_check = entries[choice]
            check = audit_bios((old_check.requirement,), platform, root)[0]
            entries[choice] = (platform, check)
            requirement = check.requirement
            detail = [
                requirement.description or requirement.name,
                f"Platform: {platform.name}",
                f"Status: {check.state.value.upper()}",
                "Required" if requirement.required else "Optional",
                f"Region: {requirement.region or 'all'}",
                f"Destination: {check.paths[0]}",
            ]
            if requirement.note:
                detail.append(requirement.note)
            if check.state is BiosState.VALID:
                self._draw_message("BIOS DETAILS", "\n".join(detail), 4, wait=True)
                continue
            if catalogue.source_url(requirement) is None:
                detail.append("RetroBIOS has metadata but no downloadable file for this entry.")
                self._draw_message("BIOS DETAILS", "\n".join(detail), 3, wait=True)
                continue
            self._draw_message("BIOS DETAILS", "\n".join(detail), 3, wait=True)
            confirmation = self._confirm_retrobios_download((check,))
            if confirmation:
                self._install_bios_checks(catalogue, (check,), platform, root)

    def _bios_followup(
        self,
        platform: Platform,
        roms_directory: Path,
        region: str | None,
    ) -> int:
        """Offer BIOS only after bundled and existing files have been checked."""

        try:
            catalogue = self._load_retrobios_catalogue()
        except BiosDownloadCancelled:
            return 0
        except BiosError as error:
            self._draw_message(
                "BIOS CHECK UNAVAILABLE",
                f"The game was installed, but RetroBIOS metadata could not be loaded:\n{error}\n"
                "You can retry from Search and download BIOS.",
                3,
                wait=True,
            )
            return 0
        requirements = catalogue.requirements_for(
            platform,
            region,
            required_only=True,
        )
        if not requirements:
            return 0
        checks = audit_bios_roots(
            requirements,
            platform,
            self.roms_directories,
            roms_directory,
        )
        missing = unresolved(checks)
        if not missing:
            LOGGER.info(
                "Required BIOS already available platform=%s roots=%s",
                platform.alias,
                self.roms_directories,
            )
            return 0
        lines = [
            "The game archive did not provide these required BIOS files, and no valid copy "
            "was found on either memory card:",
            "",
            *(f"{check.requirement.name} [{check.state.value}]" for check in missing[:8]),
        ]
        if len(missing) > 8:
            lines.append(f"...and {len(missing) - 8} more")
        self._draw_message("REQUIRED BIOS NOT FOUND", "\n".join(lines), 3, wait=True)
        choice = self._menu(
            "DOWNLOAD REQUIRED BIOS?",
            ("Download from RetroBIOS", "Keep the game without BIOS"),
            "The game may not start without required firmware",
        )
        if choice != 0 or not self._confirm_retrobios_download(missing):
            LOGGER.warning(
                "User kept game without %d required BIOS file(s) platform=%s",
                len(missing),
                platform.alias,
            )
            return 0
        return self._install_bios_checks(catalogue, missing, platform, roms_directory)

    def _confirm_retrobios_download(self, checks: Sequence[BiosCheck]) -> bool:
        downloadable = tuple(check for check in checks if check.requirement.source_path is not None)
        if not downloadable:
            self._draw_message(
                "BIOS NOT DOWNLOADABLE",
                "RetroBIOS has requirement metadata but no downloadable copy for the "
                "selected files.",
                3,
                wait=True,
            )
            return False
        choice = self._menu(
            "CONFIRM RETROBIOS DOWNLOAD",
            ("Cancel", f"Download {len(downloadable)} verified BIOS file(s)"),
            "Only continue if you are permitted to obtain these personal backup files",
        )
        return choice == 1

    def _install_bios_checks(
        self,
        catalogue: RetroBiosCatalog,
        checks: Sequence[BiosCheck],
        platform: Platform,
        root: Path,
    ) -> int:
        selected = tuple(
            check for check in checks if catalogue.source_url(check.requirement) is not None
        )
        if not selected:
            return 0
        cancelled = Event()
        state_lock = Lock()
        progress_state: list[str | int | None] = ["Connecting to RetroBIOS...", 0, None]

        def report(label: str, current: int, total: int | None) -> None:
            with state_lock:
                progress_state[:] = [label, current, total]

        def install_selected() -> int:
            installed = 0
            for check in selected:
                install_bios(
                    catalogue,
                    check.requirement,
                    platform,
                    root,
                    self.config.timeout_seconds,
                    report,
                    cancelled.is_set,
                )
                installed += 1
            return installed

        try:
            with ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="retrobios-download",
            ) as executor:
                future = executor.submit(install_selected)
                while not future.done():
                    with state_lock:
                        label, current, total = progress_state
                    assert isinstance(label, str)
                    assert isinstance(current, int)
                    assert total is None or isinstance(total, int)
                    self._progress(label, current, total)
                    pressed = self._poll_input()
                    if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                        cancelled.set()
                installed = future.result()
        except BiosDownloadCancelled:
            self._draw_message(
                "BIOS DOWNLOAD CANCELLED",
                "No incomplete BIOS file was installed.",
                3,
                wait=True,
            )
            return 0
        except BiosError as error:
            self._error(str(error))
            return 0
        self._draw_message(
            "BIOS INSTALLED",
            f"Installed and verified {installed} BIOS file(s) in {root / 'bios'}.",
            4,
            wait=True,
        )
        return installed

    @staticmethod
    def _bios_check_label(check: BiosCheck) -> str:
        kind = "R" if check.requirement.required else "O"
        region = f" {check.requirement.region}" if check.requirement.region else ""
        return f"[{check.state.value.upper()}] [{kind}]{region} {check.requirement.name}"

    def _minerva_bittorrent_settings_screen(self) -> None:
        fields = (
            ("UDP protocol ID", "udp_protocol_id"),
            ("Block size (bytes)", "block_size"),
            ("Max torrent metadata (bytes)", "max_torrent_bytes"),
            ("Max tracker response (bytes)", "max_tracker_bytes"),
            ("Max peer attempts", "max_peer_attempts"),
            ("Peer race workers", "peer_race_workers"),
            ("Max peer timeout (seconds)", "max_peer_timeout_seconds"),
            ("Max tracker queries", "max_tracker_queries"),
            ("Max discovered peers", "max_discovered_peers"),
        )
        while True:
            settings = self.preferences.minerva_bittorrent
            values = [
                f"{label}  [{self._format_bittorrent_setting(field_name, settings)}]"
                for label, field_name in fields
            ]
            choice = self._menu(
                "MINERVA BITTORRENT SETTINGS",
                (*values, "Reset all to defaults", "Back"),
                "Advanced values are saved locally",
            )
            if choice is None or choice == len(fields) + 1:
                return
            if choice == len(fields):
                confirmation = self._menu(
                    "RESET MINERVA SETTINGS?",
                    ("No - keep current values", "Yes - restore defaults"),
                    "This changes all nine BitTorrent values",
                )
                if confirmation == 1:
                    self._save_minerva_bittorrent_settings(BitTorrentSettings())
                continue
            label, field_name = fields[choice]
            current = self._format_bittorrent_setting(field_name, settings)
            raw_value = self._on_screen_keyboard(
                label.upper(),
                allow_lowercase=True,
                empty_hint=f"Current: {current}",
            )
            if raw_value is None:
                continue
            try:
                value: int | float
                if field_name == "max_peer_timeout_seconds":
                    value = float(raw_value)
                else:
                    value = int(raw_value, 0)
                updated = replace(settings, **{field_name: value})
            except (TypeError, ValueError) as error:
                self._error(f"Invalid {label.lower()}: {error}")
                continue
            self._save_minerva_bittorrent_settings(updated)

    def _save_minerva_bittorrent_settings(self, settings: BitTorrentSettings) -> bool:
        updated = replace(self.preferences, minerva_bittorrent=settings)
        try:
            save_preferences(self.preferences_path, updated)
        except PreferencesError as error:
            self._error(str(error))
            return False
        self.preferences = updated
        LOGGER.info("Minerva BitTorrent settings saved")
        self._draw_message(
            "MINERVA SETTINGS SAVED",
            "The new values will be used by the next Minerva download.",
            4,
            wait=True,
        )
        return True

    @staticmethod
    def _format_bittorrent_setting(field_name: str, settings: BitTorrentSettings) -> str:
        value = getattr(settings, field_name)
        return hex(value) if field_name == "udp_protocol_id" else str(value)

    def _application_update_flow(self) -> None:
        install_directory = self.config.install_directory
        if install_directory is None:
            self._error(
                "Automatic updates are available from the self-contained R36S package. "
                "Local development checkouts should update with git and uv."
            )
            return
        current = installed_version()
        self._draw_message(
            "CHECKING FOR UPDATE",
            f"Installed: v{current}\nReading the latest GitHub release...",
            1,
        )
        try:
            release = find_update(
                current,
                self.config.update_api_url,
                self.config.timeout_seconds,
            )
        except UpdateError as error:
            self._error(str(error))
            return
        if release is None:
            self._draw_message(
                "ALREADY UP TO DATE",
                f"v{current} is the latest published dArkOS release.",
                4,
                wait=True,
            )
            return
        choice = self._menu(
            "APPLICATION UPDATE AVAILABLE",
            (f"Download and install v{release.version}", "Later"),
            f"Installed: v{current}   Published: {release.tag}",
        )
        if choice != 0:
            return
        try:
            self._stage_application_update(release, install_directory)
        except UpdateCancelled:
            LOGGER.info("Application update cancelled")
            self._draw_message(
                "UPDATE CANCELLED",
                "The installed application was not changed.",
                3,
                wait=True,
            )
            return
        except UpdateError as error:
            LOGGER.error("Application update failed: %s", error)
            self._error(str(error))
            return
        self._draw_message(
            "UPDATE READY",
            f"v{release.version} will be installed now.\n"
            "Reopen dArkOS Downloader from Tools after this screen closes.",
            4,
            wait=True,
        )
        self.exit_after_update = True
        LOGGER.info("Application update staged; closing TUI")

    def _stage_application_update(
        self,
        release: ReleaseUpdate,
        install_directory: Path,
    ) -> Path:
        """Stage an update while keeping controller cancellation responsive."""

        cancelled = Event()
        state_lock = Lock()
        progress_state: list[str | int | None] = ["Connecting to GitHub...", 0, release.asset_size]

        def report(label: str, current: int, total: int | None) -> None:
            with state_lock:
                progress_state[:] = [label, current, total]

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="tui-update") as executor:
            future = executor.submit(
                stage_update,
                release,
                install_directory,
                self.config.timeout_seconds,
                report,
                cancelled.is_set,
            )
            while not future.done():
                with state_lock:
                    label, current, total = progress_state
                if cancelled.is_set():
                    self._draw_message(
                        "CANCELLING UPDATE",
                        "Removing the incomplete update; the installed version is unchanged...",
                        3,
                    )
                else:
                    assert isinstance(label, str)
                    assert isinstance(current, int)
                    assert total is None or isinstance(total, int)
                    self._progress(label, current, total)
                pressed = self._poll_input()
                if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                    cancelled.set()
            return future.result()

    def _confirm_exit(self) -> bool:
        choice = self._menu(
            "EXIT DARKOS DOWNLOADER?",
            ("No - return to the downloader", "Yes - exit"),
            "Confirm before returning to EmulationStation",
        )
        return choice == 1

    def _choose_from_roots(self, roots: Sequence[Path], title: str) -> Path | None:
        if not roots:
            return None
        if len(roots) == 1:
            return roots[0]
        labels = []
        for index, root in enumerate(roots, start=1):
            if root == Path("/roms2"):
                card = "SD2"
            elif root == Path("/roms"):
                card = "SD1"
            else:
                card = f"CARD {index}"
            labels.append(f"{root}  ({card})")
        choice = self._menu(
            title,
            labels,
            "Choose where the game library is stored",
        )
        return roots[choice] if choice is not None else None

    def _progress(self, label: str, current: int, total: int | None) -> None:
        if total:
            percent = min(100, int(current * 100 / total))
            message = "%s\n[%s%s] %d%%" % (
                label,
                "#" * (percent // 5),
                "." * (20 - percent // 5),
                percent,
            )
        else:
            message = "%s\n%d KiB downloaded" % (label, current // 1024)
        self._draw_message("DOWNLOADING", message, 1)
        self._footer("B/Escape: cancel download")
        self.screen.refresh()

    def _download_media(
        self,
        downloads: Sequence[str | MediaDownload],
        store: GameStore,
    ) -> list[DownloadResult]:
        """Run network work in the background while the main thread handles cancellation."""

        pending_downloads = tuple(downloads)
        while True:
            cancelled = Event()
            state_lock = Lock()
            progress_state: list[str | int | None] = [
                "Connecting to the download service...",
                0,
                None,
            ]

            def report(
                label: str,
                current: int,
                total: int | None,
                state: list[str | int | None] = progress_state,
                lock: Lock = state_lock,
            ) -> None:
                with lock:
                    state[:] = [label, current, total]

            selection_error: DownloadSelectionRequired | None = None
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="tui-download") as executor:
                bittorrent_settings = (
                    self.preferences.minerva_bittorrent if store.store_id == "minerva" else None
                )
                future = executor.submit(
                    download_files,
                    pending_downloads,
                    self.config.download_directory,
                    store.download_referrer,
                    self.config.timeout_seconds,
                    report,
                    cancelled.is_set,
                    bittorrent_settings=bittorrent_settings,
                )
                while not future.done():
                    with state_lock:
                        label, current, total = progress_state
                    if cancelled.is_set():
                        self._draw_message(
                            "CANCELLING DOWNLOAD",
                            "Closing active network connections and removing partial files...",
                            3,
                        )
                    else:
                        assert isinstance(label, str)
                        assert isinstance(current, int)
                        assert total is None or isinstance(total, int)
                        self._progress(label, current, total)
                    pressed = self._poll_input()
                    if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                        cancelled.set()
                try:
                    return future.result()
                except DownloadSelectionRequired as error:
                    selection_error = error

            assert selection_error is not None
            choice = self._choose_torrent_file(selection_error)
            if choice is None:
                raise DownloadCancelled("Download cancelled.")
            updated: list[str | MediaDownload] = []
            selection_applied = False
            for download in pending_downloads:
                if (
                    isinstance(download, MediaDownload)
                    and download.url == selection_error.torrent_url
                ):
                    updated.append(
                        replace(
                            download,
                            torrent_file_index=choice.index,
                            expected_filename=choice.filename,
                            torrent_file_path=choice.path,
                        )
                    )
                    selection_applied = True
                else:
                    updated.append(download)
            if not selection_applied:
                raise DownloadError("Could not apply the selected Minerva torrent file.")
            pending_downloads = tuple(updated)
            LOGGER.info(
                "User selected changed Minerva torrent file index=%d path=%s",
                choice.index,
                "/".join(choice.path),
            )

    def _choose_torrent_file(
        self,
        error: DownloadSelectionRequired,
    ) -> TorrentFileChoice | None:
        """Explain a changed Minerva torrent and ask the user for a safe choice."""

        self._draw_message(
            "MINERVA TORRENT CHANGED",
            f"Catalogue file:\n{error.expected_filename}\n"
            f"Catalogue position: #{error.catalogue_index}\n\n"
            f"The torrent now contains {error.total_files} files and no longer has one "
            "unambiguous match. Review the closest candidates or cancel; no game has been "
            "installed yet.",
            3,
            wait=True,
        )
        labels = [
            "#{}  {}  | {} | {}% title match | {}".format(
                candidate.index,
                candidate.filename,
                self._format_file_size(candidate.length),
                round(candidate.match_score * 100),
                "/".join(candidate.path),
            )
            for candidate in error.candidates
        ]
        selected_index = self._menu(
            "CHOOSE MINERVA TORRENT FILE",
            labels,
            "These are the closest safe candidates; B/Escape cancels",
        )
        if selected_index is None:
            return None
        selected = error.candidates[selected_index]
        self._draw_message(
            "REVIEW MINERVA FILE",
            f"Catalogue expected:\n{error.expected_filename}\n\n"
            f"Selected torrent file:\n{'/'.join(selected.path)}\n"
            f"Torrent position: #{selected.index}\n"
            f"Size: {self._format_file_size(selected.length)}\n"
            f"Title similarity: {round(selected.match_score * 100)}%",
            3,
            wait=True,
        )
        confirmation = self._menu(
            "CONFIRM MINERVA FILE",
            ("Cancel download", f"Download {selected.filename}"),
            "Only the explicitly selected torrent file will be downloaded",
        )
        return selected if confirmation == 1 else None

    @staticmethod
    def _format_file_size(length: int) -> str:
        size = float(length)
        units = ("B", "KiB", "MiB", "GiB")
        for unit in units[:-1]:
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} {units[-1]}"

    def _status_screen(self) -> None:
        roms = ", ".join(str(path) for path in self.roms_directories) or "not detected"
        controller = str(self.gamepad.path) if self.gamepad is not None else "not detected"
        selected_store = (
            self.selected_store.display_name
            if self.selected_store is not None
            else "not configured"
        )
        terminal_height, terminal_width = self.screen.getmaxyx()
        compatible = ", ".join(self.hardware.compatible[:2]) or "not detected"
        dt_inputs = ", ".join(item.node for item in self.hardware.input_nodes) or "not detected"
        key_count = len(self.hardware.keys)
        stores = ", ".join(
            f"{store.display_name} ({store.base_url})" for store in self.store_catalog.stores
        )
        lines = (
            f"Default store: {selected_store}",
            f"Stores: {stores}",
            f"Staging: {self.config.download_directory}",
            f"ROM root: {roms}",
            f"Platforms: {len(self.platforms) - 1}",
            f"Hardware: {self.hardware.model}",
            f"Compatible: {compatible}",
            f"Display: {self.hardware.display_resolution} pixels; "
            f"{terminal_width}x{terminal_height} terminal cells",
            f"DT inputs: {dt_inputs} ({key_count} GPIO keys)",
            f"Controller: {controller} (native Linux input)",
            "",
            "Controls",
            "D-pad / sticks / arrows   Move selection",
            "A / Enter        Select",
            "B / Escape       Go back",
            "X                Submit search text",
            "",
            "Search text can be entered with the built-in on-screen keyboard.",
        )
        self._draw_message("DARKOS STATUS", "\n".join(lines), 1, wait=True)

    def _on_screen_keyboard(
        self,
        title: str,
        allow_lowercase: bool = False,
        empty_hint: str = "",
    ) -> str | None:
        value = ""
        page = "letters"
        uppercase = not allow_lowercase
        row = 0
        column = 0
        while True:
            rows = _keyboard_rows(page, uppercase)
            height, width = self.screen.getmaxyx()
            self._require_size(height, width)
            self.screen.erase()
            self._header(title)
            display = value[-max(1, width - 8) :]
            self._safe_add(3, 3, "> " + display, curses.color_pair(3) | curses.A_BOLD)
            start_y = 6
            row_step = 2 if height >= 18 else 1
            key_width = max(3, (width - 4) // 12)
            total_width = key_width * 12
            start_x = max(1, (width - total_width) // 2)
            for row_index, keys in enumerate(rows):
                grid_column = 0
                for column_index, key in enumerate(keys):
                    selected = row_index == row and column_index == column
                    button_width = key_width * key.span
                    content_width = max(1, button_width - 2)
                    visible_label = key.label[:content_width]
                    label = f"[{visible_label:^{content_width}}]"
                    attribute = (
                        curses.color_pair(2) | curses.A_BOLD if selected else curses.A_NORMAL
                    )
                    self._safe_add(
                        start_y + row_index * row_step,
                        start_x + grid_column * key_width,
                        label,
                        attribute,
                    )
                    grid_column += key.span
            footer = f"{page.upper()}   D-pad: move   A: key   X: search   Y: back   B: cancel"
            if empty_hint:
                footer = f"{footer}   {empty_hint}"
            self._footer(footer)
            self.screen.refresh()
            pressed = self._get_input(KEYBOARD_GAMEPAD_KEYS)
            if pressed == 27:
                return None
            if pressed == GAMEPAD_SEARCH_KEY:
                return value.strip()
            if pressed in (curses.KEY_UP, ord("k")):
                center = _keyboard_key_center(rows[row], column)
                row = (row - 1) % len(rows)
                column = _nearest_keyboard_key(rows[row], center)
            elif pressed in (curses.KEY_DOWN, ord("j")):
                center = _keyboard_key_center(rows[row], column)
                row = (row + 1) % len(rows)
                column = _nearest_keyboard_key(rows[row], center)
            elif pressed in (curses.KEY_LEFT, ord("h")):
                column = (column - 1) % len(rows[row])
            elif pressed in (curses.KEY_RIGHT, ord("l")):
                column = (column + 1) % len(rows[row])
            elif pressed in (curses.KEY_BACKSPACE, 8, 127):
                value = value[:-1]
            elif pressed in (10, 13, curses.KEY_ENTER):
                key = rows[row][column]
                if key.action == "space":
                    value += " "
                elif key.action == "back":
                    value = value[:-1]
                elif key.action == "done":
                    return value.strip()
                elif key.action == "case":
                    uppercase = not uppercase
                elif key.action == "symbols":
                    page = "letters" if page == "symbols" else "symbols"
                elif key.action == "accents":
                    page = "letters" if page == "accents" else "accents"
                else:
                    value += key.value
            elif 32 <= pressed <= 126:
                value += chr(pressed)

    def _menu(self, title: str, options: Sequence[str], footer: str) -> int | None:
        if not options:
            return None
        selected = 0
        offset = 0
        while True:
            height, width = self.screen.getmaxyx()
            self._require_size(height, width)
            visible = max(1, height - 7)
            if selected < offset:
                offset = selected
            elif selected >= offset + visible:
                offset = selected - visible + 1
            self.screen.erase()
            self._header(title)
            for screen_row, option_index in enumerate(
                range(offset, min(len(options), offset + visible))
            ):
                label = options[option_index].replace("\n", " ")
                marker = "> " if option_index == selected else "  "
                attribute = (
                    curses.color_pair(2) | curses.A_BOLD
                    if option_index == selected
                    else curses.A_NORMAL
                )
                self._safe_add(3 + screen_row, 2, marker + label, attribute)
            if len(options) > visible:
                position = "%d/%d" % (selected + 1, len(options))
                self._safe_add(
                    height - 3, max(2, width - len(position) - 2), position, curses.color_pair(3)
                )
            self._footer(footer)
            self.screen.refresh()
            pressed = self._get_input()
            if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                return None
            if pressed in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(options)
            elif pressed in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(options)
            elif pressed == curses.KEY_PPAGE:
                selected = max(0, selected - visible)
            elif pressed == curses.KEY_NPAGE:
                selected = min(len(options) - 1, selected + visible)
            elif pressed in (
                10,
                13,
                curses.KEY_ENTER,
                GAMEPAD_START_KEY,
                ord("a"),
                ord("A"),
            ):
                return selected

    def _draw_message(
        self,
        title: str,
        message: str,
        color_pair: int,
        wait: bool = False,
    ) -> None:
        height, width = self.screen.getmaxyx()
        self._require_size(height, width)
        self.screen.erase()
        self._header(title)
        y = 4
        for paragraph in message.splitlines() or [""]:
            for line in textwrap.wrap(paragraph, max(10, width - 8)) or [""]:
                self._safe_add(y, 4, line, curses.color_pair(color_pair))
                y += 1
        if wait:
            self._footer("A/Enter/B/Esc: continue")
        self.screen.refresh()
        if wait:
            self._get_input()

    def _get_input(self, gamepad_keys: Mapping[InputAction, int] = GAMEPAD_KEYS) -> int:
        """Wait for a keyboard key or a directly connected dArkOS controller action."""

        while True:
            pressed = self._poll_input(gamepad_keys)
            if pressed is not None:
                return pressed

    def _poll_input(
        self,
        gamepad_keys: Mapping[InputAction, int] = GAMEPAD_KEYS,
    ) -> int | None:
        """Poll one controller or terminal event, respecting the screen timeout."""

        if self.gamepad is not None:
            action = self.gamepad.poll()
            if action is not None:
                return gamepad_keys[action]
        pressed = self.screen.getch()
        return int(pressed) if pressed != -1 else None

    def _error(self, message: str) -> None:
        self._draw_message("ERROR", message, 5, wait=True)

    def _header(self, title: str) -> None:
        _, width = self.screen.getmaxyx()
        line = "=" * max(1, width - 2)
        self._safe_add(0, 1, line, curses.color_pair(1))
        self._safe_add(
            1, max(1, (width - len(title)) // 2), title, curses.color_pair(1) | curses.A_BOLD
        )

    def _footer(self, text: str) -> None:
        height, width = self.screen.getmaxyx()
        self._safe_add(height - 2, 1, "-" * max(1, width - 2), curses.color_pair(1))
        self._safe_add(height - 1, 2, text, curses.A_DIM)

    def _safe_add(self, y: int, x: int, text: str, attribute: int = 0) -> None:
        height, width = self.screen.getmaxyx()
        if y < 0 or y >= height or x >= width:
            return
        clipped = text[: max(0, width - x - 1)]
        with contextlib.suppress(curses.error):
            self.screen.addstr(y, max(0, x), clipped, attribute)

    @staticmethod
    def _require_size(height: int, width: int) -> None:
        if height < 15 or width < 40:
            raise TerminalTooSmall("Terminal must be at least 40 columns by 15 rows.")


def run_tui(config: Config) -> None:
    """Initialize curses and run the interactive application."""

    curses.wrapper(lambda screen: DownloaderTui(screen, config).run())
