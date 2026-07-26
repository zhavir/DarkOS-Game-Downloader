"""Controller-friendly full-screen terminal interface."""

import contextlib
import curses
import locale
import logging
import textwrap
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock
from typing import Any

from ph.bittorrent import BitTorrentSettings, TorrentFileChoice
from ph.cache_policy import catalogue_ttl_seconds
from ph.compatibility import (
    CompatibilityError,
    CompatibilityInfo,
    GameCompatibilityClient,
    filter_supported_results,
)
from ph.config import Config
from ph.downloader import (
    DownloadCancelled,
    DownloadError,
    DownloadSelectionRequired,
    download_files,
)
from ph.frontend import request_game_frontend_refresh
from ph.gamepad import InputAction, LinuxJoystick
from ph.hardware import detect_hardware_profile
from ph.i18n import LANGUAGES, language_name, normalize_language, translate
from ph.library import (
    LibraryError,
    delete_game,
    platforms_with_installed_games,
    replace_game,
    scan_library,
)
from ph.logging_config import configure_logging
from ph.models import DownloadResult, InstalledGame, MediaDownload, Platform, SearchResult
from ph.organizer import (
    OrganizeError,
    detect_roms_directories,
    install_bundled_bios,
    install_downloads,
)
from ph.platforms import discover_platforms, platform_catalogue, resolve_platform
from ph.preferences import (
    Preferences,
    PreferencesError,
    load_preferences,
    preference_path,
    save_preferences,
)
from ph.retrobios import (
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
from ph.store import GameStore, StoreError
from ph.store_cache import CatalogueCacheError, StoreCacheStatus
from ph.store_catalog import StoreCatalog
from ph.updater import (
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
    # Some handheld images map horizontal stick directions as menu buttons.
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
    """One key in the fixed twelve-column handheld keyboard grid."""

    label: str
    value: str = ""
    action: str | None = None
    span: int = 1


class SettingInputKind(StrEnum):
    """Input controls selected from the semantic type of a setting."""

    MIXED = "mixed"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"


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

_INTEGER_KEYBOARD_ROWS: tuple[tuple[KeyboardKey, ...], ...] = (
    tuple(KeyboardKey(value, value, span=4) for value in "123"),
    tuple(KeyboardKey(value, value, span=4) for value in "456"),
    tuple(KeyboardKey(value, value, span=4) for value in "789"),
    (
        KeyboardKey("0", "0", span=4),
        KeyboardKey("BACK", action="back", span=4),
        KeyboardKey("DONE", action="done", span=4),
    ),
)

_FLOAT_KEYBOARD_ROWS: tuple[tuple[KeyboardKey, ...], ...] = (
    *_INTEGER_KEYBOARD_ROWS[:3],
    (
        KeyboardKey("0", "0", span=3),
        KeyboardKey(".", ".", span=3),
        KeyboardKey("BACK", action="back", span=3),
        KeyboardKey("DONE", action="done", span=3),
    ),
)


def _keyboard_rows(
    page: str,
    uppercase: bool,
    input_kind: SettingInputKind = SettingInputKind.MIXED,
) -> tuple[tuple[KeyboardKey, ...], ...]:
    if input_kind is SettingInputKind.INTEGER:
        return _INTEGER_KEYBOARD_ROWS
    if input_kind is SettingInputKind.FLOAT:
        return _FLOAT_KEYBOARD_ROWS
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
    """A compact curses UI for Linux handheld terminals."""

    def __init__(self, screen: Window, config: Config) -> None:
        self.screen = screen
        self.config = config
        self.preferences_path = preference_path(config.download_directory)
        preferences = load_preferences(self.preferences_path)
        self.preferences = preferences
        self.language = preferences.language
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
        self.compatibility_client = GameCompatibilityClient(
            config.download_directory / ".game-compatibility-cache.json",
            timeout_seconds=config.timeout_seconds,
            ttl_seconds=ttl_seconds,
        )
        self.roms_directories = detect_roms_directories(
            config.roms_directories or None,
            config.target.rom_roots,
        )
        self.platforms = discover_platforms(
            self.roms_directories,
            platform_catalogue(config.target),
        )
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

    def _t(self, key: str, **values: object) -> str:
        """Translate one interface message using the persisted language."""

        language = normalize_language(getattr(self, "language", "en"))
        return translate(language, key, **values)

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
                self._error(self._t("no_download_stores"))
                return
            while self.selected_store is None:
                if self._configure_store(first_run=True):
                    break
                if self._confirm_exit():
                    return
            while True:
                options = (
                    self._t("search_library"),
                    self._t("direct_download"),
                    self._t("manage_games"),
                    self._t("search_bios"),
                    self._t("settings"),
                    self._t("status_controls"),
                    self._t("exit"),
                )
                choice = self._menu(
                    self._t("app_title"),
                    options,
                    self._t("main_footer"),
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
                request_game_frontend_refresh(target=self.config.target)
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
            choice = self._menu(self._t("choose_platform"), labels, self._t("back_footer"))
            if choice is None:
                return
            self._search_platform_flow(store, platforms[choice])

    def _search_platform_flow(self, store: GameStore, platform: Platform) -> None:
        """Keep search navigation within one platform until the user goes back one level."""

        while True:
            query = self._on_screen_keyboard(
                self._t("search_title", platform=platform.alias),
                empty_hint=self._t("search_empty_hint"),
            )
            if query is None:
                return
            description = (
                self._t("looking_for", query=query)
                if query
                else self._t("loading_all", platform=platform.name)
            )
            self._draw_message(self._t("searching"), description, 1)
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
                self._operation_error(error)
                continue
            results = filter_supported_results(results)
            if not results:
                message = (
                    self._t("nothing_matched", query=query) if query else self._t("catalogue_empty")
                )
                self._draw_message(self._t("no_results"), message, 3, wait=True)
                continue
            self._draw_message(
                self._t("checking_compatibility"),
                self._t("matching_compatibility"),
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
            self._t("loading_catalogue"),
            self._t(
                "loading_catalogue_progress",
                current=current,
                total=total,
                percent=percent,
            ),
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
            badge = self._t(
                "compatibility_badge",
                value=self._compatibility_label(info),
            )
            labels.append(f"{prefix}{result.title}{detail}  [{badge}]")
        while True:
            choice = self._menu(
                self._t(
                    "results_title",
                    store=store.display_name.upper(),
                    count=len(results),
                ),
                labels,
                self._t("results_footer"),
            )
            if choice is None:
                return
            result = results[choice]
            info = compatibility[choice]
            effective_platform = platform
            if not platform.code and result.system:
                resolved = resolve_platform(result.system, self.platforms)
                if resolved is not None:
                    effective_platform = resolved
            details = [
                result.title,
                self._t("system_field", value=result.system or effective_platform.name),
                self._t("region_field", value=result.region or "-"),
                self._t("version_field", value=result.version or "-"),
                self._t("languages_field", value=result.languages),
                self._t("rating_field", value=result.rating),
                self._t("compatibility_field", value=self._compatibility_label(info, detail=True)),
            ]
            action = self._menu(
                self._t("title_details"),
                [*details, self._t("download"), self._t("back")],
                self._t("select_download"),
            )
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
            if platform.rom_folder is not None and store.supports_platform(platform)
        )
        choice = self._menu(
            self._t("destination_platform"),
            [f"{item.name} -> {item.rom_folder}" for item in platforms],
            self._t("destination_platform_footer"),
        )
        if choice is None:
            return
        url = self._on_screen_keyboard(self._t("detail_url"), allow_lowercase=True)
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
        if platform.rom_folder is None:
            self._error(self._t("platform_has_no_rom_folder"))
            return
        roms_directory = self._choose_roms_directory()
        if roms_directory is None:
            self._error(self._t("no_rom_partition_environment"))
            return
        self._draw_message(
            self._t("preparing"),
            self._t("retrieving_download_link"),
            1,
        )
        installed_bios: list[Path] = []
        try:
            media_url = store.download_request(detail_url)
            downloads = self._download_media(
                [media_url],
                store,
            )
            completed = install_downloads(
                downloads,
                platform,
                roms_directory,
                installed_bios.append,
            )
        except DownloadCancelled:
            LOGGER.info("Game download cancelled")
            self._draw_message(
                self._t("download_cancelled"),
                self._t("no_game_installed"),
                3,
            )
            return
        except (StoreError, DownloadError, OrganizeError) as error:
            LOGGER.error("Game download failed: %s", error)
            self._operation_error(error)
            return
        final_path = completed[0].path
        retrobios_installed = self._bios_followup(platform, roms_directory, region)
        self.refresh_on_exit = True
        LOGGER.info("Game installed path=%s bios_files=%d", final_path, len(installed_bios))
        bios_message = (
            "\n" + self._t("installed_bundled_bios", count=len(installed_bios))
            if installed_bios
            else ""
        )
        if retrobios_installed:
            bios_message += "\n" + self._t(
                "installed_required_bios",
                count=retrobios_installed,
            )
        self._draw_message(
            self._t("download_complete"),
            self._t(
                "download_complete_message",
                filename=final_path.name,
                destination=final_path.parent,
                bios=bios_message,
            ),
            4,
            wait=True,
        )

    def _manage_library_flow(self) -> None:
        if not self.roms_directories:
            self._error(self._t("no_rom_partitions"))
            return
        while True:
            root = self._choose_from_roots(
                self.roms_directories,
                self._t("choose_memory_card"),
            )
            if root is None:
                return
            self._draw_message(
                self._t("checking_folders"),
                self._t("finding_installed_platforms", root=root),
                1,
            )
            platforms = platforms_with_installed_games(root, self.platforms)
            if not platforms:
                self._draw_message(
                    self._t("no_games_on_card"),
                    self._t("no_supported_games_on_card", root=root),
                    3,
                    wait=True,
                )
                continue
            platform_choice = self._menu(
                self._t("choose_installed_platform"),
                [platform.name for platform in platforms],
                self._t("installed_platform_footer"),
            )
            if platform_choice is None:
                continue
            self._manage_platform_library(root, platforms[platform_choice])

    def _manage_platform_library(self, root: Path, platform: Platform) -> None:
        self._draw_message(
            self._t("scanning_platform"),
            self._t("reading_platform", platform=platform.name, root=root),
            1,
        )
        games = scan_library((root,), (platform,))
        if not games:
            self._draw_message(
                self._t("no_games"),
                self._t("no_platform_games", platform=platform.name),
                3,
                wait=True,
            )
            return
        while games:
            game_choice = self._menu(
                self._t("platform_on_card", platform=platform.alias, root=root),
                [game.title for game in games],
                self._t("manage_games_footer"),
            )
            if game_choice is None:
                return
            if self._manage_game(games[game_choice]):
                self._draw_message(
                    self._t("refreshing"),
                    self._t("refreshing_platform", platform=platform.name),
                    1,
                )
                games = scan_library((root,), (platform,))

    def _manage_game(self, game: InstalledGame) -> bool:
        description = (
            game.title,
            self._t("card_field", value=game.roms_directory),
            self._t("file_field", value=game.primary_file.name),
            self._t("files_in_group", count=len(game.files)),
            self._t("update_from_remote"),
            self._t("delete_from_device"),
            self._t("back"),
        )
        choice = self._menu(
            self._t("manage_game"),
            description,
            self._t("manage_game_footer"),
        )
        if choice == 4:
            return self._update_game(game)
        if choice == 5:
            return self._confirm_delete(game)
        return False

    def _confirm_delete(self, game: InstalledGame) -> bool:
        choice = self._menu(
            self._t("confirm_permanent_delete"),
            (
                self._t("keep_game", title=game.title),
                self._t("delete_files", count=len(game.files)),
            ),
            self._t("delete_warning"),
        )
        if choice != 1:
            return False
        try:
            delete_game(game)
        except LibraryError as error:
            LOGGER.error("Could not delete game title=%r: %s", game.title, error)
            self._operation_error(error)
            return False
        self.refresh_on_exit = True
        LOGGER.info("Deleted game title=%r files=%d", game.title, len(game.files))
        self._draw_message(
            self._t("game_deleted"),
            self._t("game_deleted_message", title=game.title),
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
                self._t(
                    "store_platform_unsupported",
                    store=store.display_name,
                    platform=game.platform.name,
                )
            )
            return False
        self._draw_message(self._t("searching_for_update"), game.title, 1)
        try:
            results = store.search(store.platform_code(game.platform), game.title)
        except StoreError as error:
            self._operation_error(error)
            return False
        if not results:
            self._draw_message(self._t("no_remote_match"), game.title, 3, wait=True)
            return False
        choice = self._menu(
            self._t("choose_replacement"),
            [
                "{} - {} - {}".format(result.title, result.region or "-", result.version or "-")
                for result in results
            ],
            self._t("replacement_footer"),
        )
        if choice is None:
            return False
        selected = results[choice]
        confirmation = self._menu(
            self._t("confirm_update"),
            (
                self._t("keep_file", filename=game.primary_file.name),
                self._t("replace_with", title=selected.title),
            ),
            self._t("confirm_choice_footer"),
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
            self._draw_message(
                self._t("update_cancelled"),
                self._t("installed_game_unchanged"),
                3,
            )
            return False
        except (StoreError, DownloadError, LibraryError, OrganizeError) as error:
            LOGGER.error("Game update failed title=%r: %s", game.title, error)
            self._operation_error(error)
            return False
        self.refresh_on_exit = True
        retrobios_installed = self._bios_followup(
            game.platform,
            game.roms_directory,
            selected.region,
        )
        LOGGER.info("Game updated title=%r path=%s", game.title, completed.path)
        self._draw_message(
            self._t("game_updated"),
            self._t(
                "game_updated_message",
                filename=completed.path.name,
                destination=game.roms_directory,
                bundled=(
                    "\n" + self._t("installed_bundled_bios", count=len(installed_bios))
                    if installed_bios
                    else ""
                ),
                required=(
                    "\n" + self._t("installed_required_bios", count=retrobios_installed)
                    if retrobios_installed
                    else ""
                ),
            ),
            4,
            wait=True,
        )
        return True

    def _choose_roms_directory(self) -> Path | None:
        return self._choose_from_roots(
            self.roms_directories,
            self._t("choose_destination_card"),
        )

    def _choose_store(self, title: str, platform: Platform | None = None) -> GameStore | None:
        stores = tuple(
            store
            for store in self.store_catalog.stores
            if platform is None or store.supports_platform(platform)
        )
        choice = self._menu(
            title,
            [f"{store.display_name} - {self._store_description(store)}" for store in stores],
            self._t("choose_store_footer"),
        )
        return stores[choice] if choice is not None else None

    def _configure_store(self, *, first_run: bool = False) -> bool:
        title = self._t("first_run_store" if first_run else "choose_default_store")
        store = self._choose_store(title)
        if store is None:
            return False
        preferences = load_preferences(self.preferences_path)
        updated_preferences = replace(preferences, store_id=store.store_id)
        try:
            save_preferences(self.preferences_path, updated_preferences)
        except PreferencesError as error:
            self._operation_error(error)
            return False
        self.preferences = updated_preferences
        self.selected_store = store
        LOGGER.info("Default store changed to %s", store.store_id)
        if not first_run:
            self._draw_message(
                self._t("settings_saved"),
                self._t("store_saved_message", store=store.display_name),
                4,
                wait=True,
            )
        return True

    def _settings_screen(self) -> None:
        while True:
            current = (
                self.selected_store.display_name
                if self.selected_store is not None
                else self._t("not_set")
            )
            retrobios_status = self._retrobios_cache_label()
            compatibility_status = self._compatibility_cache_label()
            game_catalogue_count = sum(
                store.catalogue_cache_file_count() for store in self.store_catalog.stores
            )
            options = [
                self._t("change_store", value=current),
                f"{self._t('language')}  [{language_name(self.preferences.language)}]",
                self._t("refresh_store_cache", count=game_catalogue_count),
                self._t("update_bios_catalogue", status=retrobios_status),
                self._t("update_compatibility", status=compatibility_status),
                self._t("cache_lifetime", days=self.preferences.catalogue_ttl_days),
                self._t(
                    "log_level",
                    value=self.preferences.log_level or self.config.log_level,
                ),
                self._t(
                    "file_logging",
                    value=self._t("on") if self._file_logging_enabled() else self._t("off"),
                ),
            ]
            actions = [
                "store",
                "language",
                "store_catalogue",
                "retrobios_update",
                "compatibility_update",
                "catalogue_ttl",
                "log_level",
                "log_file",
            ]
            if self.selected_store is not None and self.selected_store.store_id == "minerva":
                options.append(self._t("minerva_settings"))
                actions.append("minerva")
            options.extend(
                (
                    self._t("check_update", version=installed_version()),
                    self._t("back"),
                )
            )
            actions.extend(("update", "back"))
            choice = self._menu(
                self._t("settings_title"),
                options,
                self._t("settings_footer"),
            )
            if choice is None or actions[choice] == "back":
                return
            action = actions[choice]
            if action == "store":
                self._configure_store()
            elif action == "language":
                self._configure_language()
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

    def _configure_language(self) -> None:
        choice = self._menu(
            self._t("choose_language"),
            [language.name for language in LANGUAGES],
            self._t("language_footer"),
        )
        if choice is None:
            return
        language = LANGUAGES[choice]
        self._save_runtime_preferences(
            replace(self.preferences, language=language.code),
            translate(language.code, "language_saved"),
            translate(
                language.code,
                "language_saved_message",
                language=language.name,
            ),
        )

    def _edit_setting(
        self,
        title: str,
        current: str,
        input_kind: SettingInputKind,
    ) -> str | bool | None:
        if input_kind is SettingInputKind.BOOLEAN:
            choice = self._menu(
                title,
                (self._t("false"), self._t("true")),
                self._t("file_logging_footer"),
            )
            return None if choice is None else choice == 1
        hint_key = (
            "integer_keyboard"
            if input_kind is SettingInputKind.INTEGER
            else "float_keyboard"
            if input_kind is SettingInputKind.FLOAT
            else "mixed_keyboard"
        )
        return self._on_screen_keyboard(
            title,
            allow_lowercase=input_kind is SettingInputKind.MIXED,
            empty_hint=f"{self._t(hint_key)}; {current}",
            input_kind=input_kind,
        )

    def _configure_catalogue_ttl(self) -> None:
        raw_value = self._edit_setting(
            self._t("cache_days_title"),
            self._t(
                "cache_days_hint",
                current=self.preferences.catalogue_ttl_days,
                default=7,
            ),
            SettingInputKind.INTEGER,
        )
        if raw_value is None:
            return
        assert isinstance(raw_value, str)
        try:
            days = int(raw_value)
            if not 1 <= days <= 3650:
                self._error(self._t("cache_lifetime_range"))
                return
        except ValueError:
            self._error(self._t("invalid_cache_lifetime"))
            return
        self._save_runtime_preferences(
            replace(self.preferences, catalogue_ttl_days=days),
            self._t("cache_lifetime_saved"),
            self._t("cache_lifetime_saved_message", days=days),
        )

    def _configure_log_level(self) -> None:
        levels = ("DEBUG", "INFO", "WARNING", "ERROR")
        choice = self._menu(
            self._t("log_level_title"),
            levels,
            self._t("log_level_footer"),
        )
        if choice is None:
            return
        level = levels[choice]
        self._save_runtime_preferences(
            replace(self.preferences, log_level=level),
            self._t("log_level_saved"),
            self._t("log_level_saved_message", level=level),
        )

    def _configure_file_logging(self) -> None:
        enabled = self._edit_setting(
            self._t("file_logging_title"),
            self._t("on") if self._file_logging_enabled() else self._t("off"),
            SettingInputKind.BOOLEAN,
        )
        if enabled is None:
            return
        assert isinstance(enabled, bool)
        self._save_runtime_preferences(
            replace(self.preferences, log_to_file=enabled),
            self._t("file_logging_saved"),
            self._t("file_logging_enabled" if enabled else "file_logging_disabled"),
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
            self._operation_error(error)
            return False
        self.preferences = preferences
        self._apply_runtime_preferences()
        self._draw_message(title, message, 4, wait=True)
        return True

    def _apply_runtime_preferences(self) -> None:
        self.language = normalize_language(self.preferences.language)
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
            log_file = self.config.log_file or self.config.download_directory / "pocket-harbor.log"
        configure_logging(log_file, self.preferences.log_level or self.config.log_level)

    def _refresh_store_catalogue(self) -> None:
        stores = self.store_catalog.stores
        while True:
            store_choice = self._menu(
                self._t("choose_store_catalogue"),
                [
                    self._t(
                        "store_cached_count",
                        store=store.display_name,
                        count=store.catalogue_cache_file_count(),
                    )
                    for store in stores
                ],
                self._t("choose_store_footer"),
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
                self._t("refresh_store_title", store=store.display_name.upper()),
                [
                    f"{platform.name}  [{self._store_cache_status_label(status)}]"
                    for platform, _system_code, status in choices
                ],
                self._t("refresh_store_footer"),
            )
            if platform_choice is None:
                continue
            platform, system_code, _status = choices[platform_choice]
            self._draw_message(
                self._t("refreshing_catalogue"),
                self._t(
                    "refreshing_catalogue_message",
                    store=store.display_name,
                    platform=platform.name,
                ),
                1,
            )
            try:
                results = store.refresh_catalogue(system_code, self._catalog_progress)
            except (CatalogueCacheError, StoreError) as error:
                self._operation_error(error)
                return
            self._draw_message(
                self._t("catalogue_updated"),
                self._t(
                    "catalogue_updated_message",
                    count=len(results),
                    store=store.display_name,
                    platform=platform.name,
                ),
                4,
                wait=True,
            )
            return

    def _store_cache_status_label(self, status: StoreCacheStatus | None) -> str:
        if status is None:
            return self._t("not_downloaded")
        return self._t(
            "stale_games" if status.stale else "fresh_games",
            count=status.result_count,
        )

    def _store_description(self, store: GameStore) -> str:
        key = {
            "vimm": "store_description_vimm",
            "minerva": "store_description_minerva",
        }.get(store.store_id)
        return self._t(key) if key is not None else store.description

    def _compatibility_label(
        self,
        info: CompatibilityInfo,
        *,
        detail: bool = False,
    ) -> str:
        level_key = {
            "not listed": "compatibility_level_not_listed",
            "perfect": "compatibility_level_perfect",
            "playable": "compatibility_level_playable",
            "limited": "compatibility_level_limited",
            "unsupported": "compatibility_level_unsupported",
        }.get(info.level.casefold())
        level = self._t(level_key) if level_key is not None else info.level
        if info.level == "Not listed":
            return self._t("compatibility_not_listed_source") if detail else level
        if detail:
            qualifier = (
                self._t(
                    "compatibility_title_match",
                    score=round(info.match_score * 100),
                )
                if info.title_listed and info.match_score is not None
                else self._t("compatibility_title_listed")
                if info.title_listed
                else self._t("compatibility_platform_rating")
            )
            return self._t("compatibility_detail", level=level, qualifier=qualifier)
        if info.title_listed and info.match_score is not None:
            return self._t(
                "compatibility_match",
                level=level,
                score=round(info.match_score * 100),
            )
        return self._t("compatibility_listed", level=level) if info.title_listed else level

    def _bios_state_label(self, state: BiosState) -> str:
        return self._t(f"bios_state_{state.value}")

    def _progress_label(self, label: str) -> str:
        key = {
            "Finding the latest RetroBIOS revision": "finding_retrobios_revision",
            "Downloading RetroBIOS core profiles": "downloading_retrobios_profiles",
        }.get(label)
        return self._t(key) if key is not None else label

    def _retrobios_cache_label(self) -> str:
        if not hasattr(self, "retrobios_repository"):
            return self._t("not_downloaded")
        try:
            catalogue = self.retrobios_repository.load()
        except BiosError:
            return self._t("cache_invalid")
        if catalogue is None:
            return self._t("not_downloaded")
        freshness = (
            self._t("stale_over_days", days=self.preferences.catalogue_ttl_days)
            if catalogue.cache_is_stale()
            else self._t("fresh")
        )
        return f"{catalogue.revision[:8]} - {freshness}"

    def _compatibility_cache_label(self) -> str:
        if not hasattr(self, "compatibility_client"):
            return self._t("not_downloaded")
        age = self.compatibility_client.cache_age_seconds()
        if age is None:
            return self._t("not_downloaded")
        return (
            self._t("stale_over_days", days=self.preferences.catalogue_ttl_days)
            if self.compatibility_client.cache_is_stale()
            else self._t("fresh")
        )

    def _update_compatibility_catalogue(self) -> None:
        choice = self._menu(
            self._t("compatibility_update_title"),
            (
                self._t("compatibility_update_download"),
                self._t("keep_catalogue"),
            ),
            self._t("keep_cache_footer"),
        )
        if choice != 0:
            return
        self._draw_message(
            self._t("compatibility_updating"),
            self._t("compatibility_updating_message"),
            1,
        )
        try:
            count = self.compatibility_client.refresh()
        except CompatibilityError as error:
            self._operation_error(error)
            return
        self._draw_message(
            self._t("compatibility_updated"),
            self._t(
                "compatibility_updated_message",
                count=count,
                days=self.preferences.catalogue_ttl_days,
            ),
            4,
            wait=True,
        )

    def _load_retrobios_catalogue(self, *, update: bool = False) -> RetroBiosCatalog:
        if not update and self.retrobios_catalog is not None:
            return self.retrobios_catalog
        cancelled = Event()
        state_lock = Lock()
        progress_state: list[str | int | None] = [
            self._t("connecting_retrobios"),
            0,
            None,
        ]

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
                self._progress(self._progress_label(label), current, total)
                pressed = self._poll_input()
                if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                    cancelled.set()
            catalogue = future.result()
        self.retrobios_catalog = catalogue
        return catalogue

    def _update_retrobios_catalogue(self) -> None:
        choice = self._menu(
            self._t("retrobios_update_title"),
            (
                self._t("download_latest_metadata"),
                self._t("keep_catalogue"),
            ),
            self._t("keep_cache_footer"),
        )
        if choice != 0:
            return
        try:
            catalogue = self._load_retrobios_catalogue(update=True)
        except BiosDownloadCancelled:
            self._draw_message(
                self._t("retrobios_update_cancelled"),
                self._t("catalogue_unchanged"),
                3,
                wait=True,
            )
            return
        except BiosError as error:
            self._operation_error(error)
            return
        self._draw_message(
            self._t("retrobios_updated"),
            self._t(
                "retrobios_summary",
                revision=catalogue.revision[:12],
                systems=len(catalogue.systems),
                profile=catalogue.retroarch_version or self._t("unknown"),
            ),
            4,
            wait=True,
        )

    def _bios_search_flow(self) -> None:
        root = self._choose_from_roots(
            self.roms_directories,
            self._t("choose_bios_memory_card"),
        )
        if root is None:
            self._error(self._t("no_rom_partition"))
            return
        try:
            catalogue = self._load_retrobios_catalogue()
        except BiosDownloadCancelled:
            return
        except BiosError as error:
            self._operation_error(error)
            return
        query = self._on_screen_keyboard(
            self._t("search_bios_title"),
            empty_hint=self._t("search_bios_empty_hint"),
        )
        if query is None:
            return
        normalized = query.casefold().strip()
        entries: list[tuple[Platform, BiosCheck]] = []
        seen: set[tuple[str, str, str]] = set()
        for platform in self.platforms:
            if platform.rom_folder is None:
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
                self._t("no_bios_results"),
                (
                    self._t("nothing_matched", query=query)
                    if query
                    else self._t("bios_catalogue_empty")
                ),
                3,
                wait=True,
            )
            return
        while True:
            choice = self._menu(
                self._t("bios_results", count=len(entries)),
                [
                    f"{platform.alias} | {self._bios_check_label(check)}"
                    for platform, check in entries
                ],
                self._t("bios_results_footer"),
            )
            if choice is None:
                return
            platform, old_check = entries[choice]
            check = audit_bios((old_check.requirement,), platform, root)[0]
            entries[choice] = (platform, check)
            requirement = check.requirement
            detail = [
                requirement.description or requirement.name,
                self._t("platform_field", value=platform.name),
                self._t("status_field", value=self._bios_state_label(check.state).upper()),
                self._t("required" if requirement.required else "optional"),
                self._t("region_field", value=requirement.region or self._t("all_regions")),
                self._t("destination_field", value=check.paths[0]),
            ]
            if requirement.note:
                detail.append(requirement.note)
            if check.state is BiosState.VALID:
                self._draw_message(self._t("bios_details"), "\n".join(detail), 4, wait=True)
                continue
            if catalogue.source_url(requirement) is None:
                detail.append(self._t("bios_entry_not_downloadable"))
                self._draw_message(self._t("bios_details"), "\n".join(detail), 3, wait=True)
                continue
            self._draw_message(self._t("bios_details"), "\n".join(detail), 3, wait=True)
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
                self._t("bios_check_unavailable"),
                self._t("bios_check_unavailable_message", error=error),
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
            self._t("required_bios_missing_message"),
            "",
            *(
                f"{check.requirement.name} [{self._bios_state_label(check.state)}]"
                for check in missing[:8]
            ),
        ]
        if len(missing) > 8:
            lines.append(self._t("and_more", count=len(missing) - 8))
        self._draw_message(
            self._t("required_bios_not_found"),
            "\n".join(lines),
            3,
            wait=True,
        )
        choice = self._menu(
            self._t("download_required_bios"),
            (
                self._t("download_from_retrobios"),
                self._t("keep_without_bios"),
            ),
            self._t("firmware_warning"),
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
                self._t("bios_not_downloadable"),
                self._t("bios_not_downloadable_message"),
                3,
                wait=True,
            )
            return False
        choice = self._menu(
            self._t("confirm_retrobios_download"),
            (
                self._t("cancel"),
                self._t("download_verified_bios", count=len(downloadable)),
            ),
            self._t("bios_legal_footer"),
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
        progress_state: list[str | int | None] = [
            self._t("connecting_retrobios"),
            0,
            None,
        ]

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
                    self._progress(self._progress_label(label), current, total)
                    pressed = self._poll_input()
                    if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                        cancelled.set()
                installed = future.result()
        except BiosDownloadCancelled:
            self._draw_message(
                self._t("bios_download_cancelled"),
                self._t("no_incomplete_bios_installed"),
                3,
                wait=True,
            )
            return 0
        except BiosError as error:
            self._operation_error(error)
            return 0
        self._draw_message(
            self._t("bios_installed"),
            self._t(
                "bios_installed_message",
                count=installed,
                destination=root / "bios",
            ),
            4,
            wait=True,
        )
        return installed

    def _bios_check_label(self, check: BiosCheck) -> str:
        kind = self._t("required_short" if check.requirement.required else "optional_short")
        region = f" {check.requirement.region}" if check.requirement.region else ""
        state = self._bios_state_label(check.state).upper()
        return f"[{state}] [{kind}]{region} {check.requirement.name}"

    def _minerva_bittorrent_settings_screen(self) -> None:
        fields = (
            ("minerva_udp_protocol_id", "udp_protocol_id"),
            ("minerva_block_size", "block_size"),
            ("minerva_max_torrent_bytes", "max_torrent_bytes"),
            ("minerva_max_tracker_bytes", "max_tracker_bytes"),
            ("minerva_max_peer_attempts", "max_peer_attempts"),
            ("minerva_peer_race_workers", "peer_race_workers"),
            ("minerva_max_peer_timeout", "max_peer_timeout_seconds"),
            ("minerva_max_tracker_queries", "max_tracker_queries"),
            ("minerva_max_discovered_peers", "max_discovered_peers"),
        )
        while True:
            settings = self.preferences.minerva_bittorrent
            values = [
                f"{self._t(label_key)}  [{self._format_bittorrent_setting(field_name, settings)}]"
                for label_key, field_name in fields
            ]
            choice = self._menu(
                self._t("minerva_settings_title"),
                (*values, self._t("reset_all_defaults"), self._t("back")),
                self._t("minerva_settings_footer"),
            )
            if choice is None or choice == len(fields) + 1:
                return
            if choice == len(fields):
                confirmation = self._menu(
                    self._t("reset_minerva_settings"),
                    (
                        self._t("keep_current_values"),
                        self._t("restore_defaults"),
                    ),
                    self._t("reset_minerva_footer"),
                )
                if confirmation == 1:
                    self._save_minerva_bittorrent_settings(BitTorrentSettings())
                continue
            label_key, field_name = fields[choice]
            label = self._t(label_key)
            current = self._format_bittorrent_setting(field_name, settings)
            input_kind = (
                SettingInputKind.FLOAT
                if field_name == "max_peer_timeout_seconds"
                else SettingInputKind.INTEGER
            )
            raw_value = self._edit_setting(
                label.upper(),
                self._t("current_value", value=current),
                input_kind,
            )
            if raw_value is None:
                continue
            assert isinstance(raw_value, str)
            try:
                value: int | float
                if field_name == "max_peer_timeout_seconds":
                    value = float(raw_value)
                else:
                    value = int(raw_value)
                updated = replace(settings, **{field_name: value})
            except (TypeError, ValueError) as error:
                self._error(self._t("invalid_setting", setting=label, error=error))
                continue
            self._save_minerva_bittorrent_settings(updated)

    def _save_minerva_bittorrent_settings(self, settings: BitTorrentSettings) -> bool:
        updated = replace(self.preferences, minerva_bittorrent=settings)
        try:
            save_preferences(self.preferences_path, updated)
        except PreferencesError as error:
            self._operation_error(error)
            return False
        self.preferences = updated
        LOGGER.info("Minerva BitTorrent settings saved")
        self._draw_message(
            self._t("minerva_settings_saved"),
            self._t("minerva_settings_saved_message"),
            4,
            wait=True,
        )
        return True

    @staticmethod
    def _format_bittorrent_setting(field_name: str, settings: BitTorrentSettings) -> str:
        value = getattr(settings, field_name)
        return str(value)

    def _application_update_flow(self) -> None:
        install_directory = self.config.install_directory
        if install_directory is None:
            self._error(self._t("automatic_update_package"))
            return
        current = installed_version()
        self._draw_message(
            self._t("checking_for_update"),
            self._t("checking_for_update_message", version=current),
            1,
        )
        try:
            release = find_update(
                current,
                self.config.update_api_url,
                self.config.timeout_seconds,
                self.config.target,
            )
        except UpdateError as error:
            self._operation_error(error)
            return
        if release is None:
            self._draw_message(
                self._t("already_up_to_date"),
                self._t(
                    "latest_release_message",
                    version=current,
                    target=self.config.target.display_name,
                ),
                4,
                wait=True,
            )
            return
        choice = self._menu(
            self._t("application_update_available"),
            (
                self._t("download_install_version", version=release.version),
                self._t("later"),
            ),
            self._t("installed_published", installed=current, published=release.tag),
        )
        if choice != 0:
            return
        try:
            self._stage_application_update(release, install_directory)
        except UpdateCancelled:
            LOGGER.info("Application update cancelled")
            self._draw_message(
                self._t("update_cancelled"),
                self._t("installed_application_unchanged"),
                3,
                wait=True,
            )
            return
        except UpdateError as error:
            LOGGER.error("Application update failed: %s", error)
            self._operation_error(error)
            return
        self._draw_message(
            self._t("update_ready"),
            self._t("update_ready_message", version=release.version),
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
        progress_state: list[str | int | None] = [
            self._t("connecting_github"),
            0,
            release.asset_size,
        ]

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
                self.config.target,
            )
            while not future.done():
                with state_lock:
                    label, current, total = progress_state
                if cancelled.is_set():
                    self._draw_message(
                        self._t("cancelling_update"),
                        self._t("cancelling_update_message"),
                        3,
                    )
                else:
                    assert isinstance(label, str)
                    assert isinstance(current, int)
                    assert total is None or isinstance(total, int)
                    self._progress(self._progress_label(label), current, total)
                pressed = self._poll_input()
                if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                    cancelled.set()
            return future.result()

    def _confirm_exit(self) -> bool:
        choice = self._menu(
            self._t("exit_pocket_harbor"),
            (
                self._t("return_to_pocket_harbor"),
                self._t("confirm_exit"),
            ),
            self._t("exit_footer"),
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
                card = self._t("card_number", index=index)
            labels.append(f"{root}  ({card})")
        choice = self._menu(
            title,
            labels,
            self._t("choose_library_location"),
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
            message = self._t(
                "downloaded_kib",
                label=label,
                kib=current // 1024,
            )
        self._draw_message(self._t("downloading"), message, 1)
        self._footer(self._t("cancel_download_footer"))
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
                self._t("connecting_download_service"),
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
                            self._t("cancelling_download"),
                            self._t("cancelling_download_message"),
                            3,
                        )
                    else:
                        assert isinstance(label, str)
                        assert isinstance(current, int)
                        assert total is None or isinstance(total, int)
                        self._progress(self._progress_label(label), current, total)
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
            self._t("minerva_torrent_changed"),
            self._t(
                "minerva_torrent_changed_message",
                filename=error.expected_filename,
                index=error.catalogue_index,
                count=error.total_files,
            ),
            3,
            wait=True,
        )
        labels = [
            self._t(
                "minerva_candidate",
                index=candidate.index,
                filename=candidate.filename,
                size=self._format_file_size(candidate.length),
                score=round(candidate.match_score * 100),
                path="/".join(candidate.path),
            )
            for candidate in error.candidates
        ]
        selected_index = self._menu(
            self._t("choose_minerva_torrent_file"),
            labels,
            self._t("minerva_candidates_footer"),
        )
        if selected_index is None:
            return None
        selected = error.candidates[selected_index]
        self._draw_message(
            self._t("review_minerva_file"),
            self._t(
                "review_minerva_file_message",
                expected=error.expected_filename,
                selected="/".join(selected.path),
                index=selected.index,
                size=self._format_file_size(selected.length),
                score=round(selected.match_score * 100),
            ),
            3,
            wait=True,
        )
        confirmation = self._menu(
            self._t("confirm_minerva_file"),
            (
                self._t("cancel_download"),
                self._t("download_filename", filename=selected.filename),
            ),
            self._t("confirm_minerva_file_footer"),
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
        not_detected = self._t("not_detected")
        roms = ", ".join(str(path) for path in self.roms_directories) or not_detected
        controller = str(self.gamepad.path) if self.gamepad is not None else not_detected
        selected_store = (
            self.selected_store.display_name
            if self.selected_store is not None
            else self._t("not_configured")
        )
        terminal_height, terminal_width = self.screen.getmaxyx()
        compatible = ", ".join(self.hardware.compatible[:2]) or not_detected
        dt_inputs = ", ".join(item.node for item in self.hardware.input_nodes) or not_detected
        key_count = len(self.hardware.keys)
        stores = ", ".join(
            f"{store.display_name} ({store.base_url})" for store in self.store_catalog.stores
        )
        message = self._t(
            "status_message",
            store=selected_store,
            stores=stores,
            staging=self.config.download_directory,
            roms=roms,
            platforms=len(self.platforms) - 1,
            hardware=self.hardware.model,
            compatible=compatible,
            resolution=self.hardware.display_resolution,
            width=terminal_width,
            height=terminal_height,
            inputs=dt_inputs,
            keys=key_count,
            controller=controller,
        )
        self._draw_message(self._t("status_title"), message, 1, wait=True)

    def _on_screen_keyboard(
        self,
        title: str,
        allow_lowercase: bool = False,
        empty_hint: str = "",
        input_kind: SettingInputKind = SettingInputKind.MIXED,
    ) -> str | None:
        value = ""
        page = "letters"
        uppercase = not allow_lowercase
        row = 0
        column = 0
        while True:
            rows = _keyboard_rows(page, uppercase, input_kind)
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
                    translated_label = (
                        self._t("space")
                        if key.action == "space"
                        else self._t("key_back")
                        if key.action == "back"
                        else self._t("done")
                        if key.action == "done"
                        else key.label
                    )
                    visible_label = translated_label[:button_width]
                    label = f"{visible_label:^{button_width}}"
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
            page_label = (
                self._t("integer_keyboard")
                if input_kind is SettingInputKind.INTEGER
                else self._t("float_keyboard")
                if input_kind is SettingInputKind.FLOAT
                else self._t(f"keyboard_{page}")
            )
            footer = self._t("keyboard_footer", page=page_label)
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
                elif key.action == "symbols" and input_kind is SettingInputKind.MIXED:
                    page = "letters" if page == "symbols" else "symbols"
                elif key.action == "accents" and input_kind is SettingInputKind.MIXED:
                    page = "letters" if page == "accents" else "accents"
                else:
                    value += key.value
            elif 32 <= pressed <= 126:
                character = chr(pressed)
                if input_kind is SettingInputKind.INTEGER:
                    if character.isdigit():
                        value += character
                elif input_kind is SettingInputKind.FLOAT:
                    if character.isdigit() or (character == "." and "." not in value):
                        value += character
                else:
                    value += character

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
            self._footer(self._t("continue_footer"))
        self.screen.refresh()
        if wait:
            self._get_input()

    def _get_input(self, gamepad_keys: Mapping[InputAction, int] = GAMEPAD_KEYS) -> int:
        """Wait for a keyboard key or a directly connected controller action."""

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

    def _operation_error(self, error: Exception) -> None:
        self._error(self._t("operation_failed", error=error))

    def _error(self, message: str) -> None:
        self._draw_message(self._t("error"), message, 5, wait=True)

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

    def _require_size(self, height: int, width: int) -> None:
        if height < 15 or width < 40:
            raise TerminalTooSmall(self._t("terminal_too_small"))


def run_tui(config: Config) -> None:
    """Initialize curses and run the interactive application."""

    curses.wrapper(lambda screen: DownloaderTui(screen, config).run())
