"""Controller-friendly full-screen terminal interface."""

import contextlib
import curses
import locale
import logging
import textwrap
import time
from collections.abc import Callable, Mapping, Sequence
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
from ph.download_queue import (
    DownloadJob,
    DownloadQueue,
    DownloadState,
)
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
    scan_library,
)
from ph.logging_config import active_log_file, configure_logging_with_fallback
from ph.models import DownloadResult, InstalledGame, MediaDownload, Platform, SearchResult
from ph.organizer import detect_roms_directories
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
from ph.translation_keys import TranslationKey
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
GAMEPAD_FILTER_KEY = 0x110003
GAMEPAD_RESET_KEY = 0x110004

SEARCH_FILTER_CHOICE = -1
SEARCH_RESET_CHOICE = -2
MENU_REDRAW_SECONDS = 0.25

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

SEARCH_RESULTS_GAMEPAD_KEYS: dict[InputAction, int] = {
    **GAMEPAD_KEYS,
    InputAction.SUBMIT_SEARCH: GAMEPAD_FILTER_KEY,
    InputAction.BACKSPACE: GAMEPAD_RESET_KEY,
}
SEARCH_RESULTS_SHORTCUTS: dict[int, int] = {
    GAMEPAD_FILTER_KEY: SEARCH_FILTER_CHOICE,
    GAMEPAD_RESET_KEY: SEARCH_RESET_CHOICE,
    ord("x"): SEARCH_FILTER_CHOICE,
    ord("X"): SEARCH_FILTER_CHOICE,
    ord("y"): SEARCH_RESET_CHOICE,
    ord("Y"): SEARCH_RESET_CHOICE,
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


def _fit_column(value: str, width: int) -> str:
    """Fit a metadata value without disturbing the following menu columns."""

    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: width - 1] + "…"


def _marquee_text(value: str, width: int, offset: int) -> str:
    """Return one frame of a looping horizontal marquee."""

    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    loop = value + "   "
    start = offset % len(loop)
    repeated = loop + loop[:width]
    return repeated[start : start + width]


def _visible_menu_label(value: str, width: int, offset: int) -> str:
    """Scroll long titles while retaining structured metadata when it fits."""

    if len(value) <= width:
        return value
    prefix, separator, title = value.rpartition(" | ")
    if separator and len(prefix) + len(separator) < width:
        title_width = width - len(prefix) - len(separator)
        return prefix + separator + _marquee_text(title, title_width, offset)
    return _marquee_text(value, width, offset)


def _platform_matches_filter(platform: Platform, query: str) -> bool:
    """Match a platform by any user-visible name or stable identifier."""

    normalized = query.strip().casefold()
    return not normalized or any(
        normalized in value.casefold()
        for value in (platform.name, platform.alias, platform.code, platform.slug)
    )


class TerminalTooSmall(RuntimeError):
    """The active terminal cannot display the interface."""


class DownloaderTui:
    """A compact curses UI for Linux handheld terminals."""

    def __init__(self, screen: Window, config: Config) -> None:
        self.screen = screen
        self.preferences_path = preference_path(config.download_directory)
        preferences = load_preferences(self.preferences_path)
        self.preferences = preferences
        self.config = replace(
            config,
            timeout_seconds=preferences.network_timeout_seconds or config.timeout_seconds,
        )
        self.language = preferences.language
        ttl_seconds = catalogue_ttl_seconds(preferences.catalogue_ttl_days)
        self.store_catalog = StoreCatalog.from_config(self.config, ttl_seconds)
        self.retrobios_repository = RetroBiosRepository(
            self.config.download_directory,
            self.config.timeout_seconds,
            ttl_seconds,
        )
        self.retrobios_catalog: RetroBiosCatalog | None = None
        self.selected_store = (
            self.store_catalog.find(preferences.store_id)
            if preferences.store_id and not preferences.ask_store_each_time
            else None
        )
        self.download_queue = DownloadQueue(
            self.config.download_directory,
            max_concurrent=preferences.max_concurrent_downloads,
            retry_settings=preferences.rate_limit_retry,
        )
        self._handled_completed_jobs: set[str] = set()
        self.refresh_on_exit = False
        self.exit_after_update = False
        self.compatibility_client = GameCompatibilityClient(
            self.config.download_directory / ".game-compatibility-cache.json",
            timeout_seconds=self.config.timeout_seconds,
            ttl_seconds=ttl_seconds,
        )
        self.roms_directories = detect_roms_directories(
            self.config.roms_directories or None,
            self.config.target.rom_roots,
        )
        self.platforms = discover_platforms(
            self.roms_directories,
            platform_catalogue(self.config.target),
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

    def _t(self, key: TranslationKey, **values: object) -> str:
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
                self._error(self._t(TranslationKey.NO_DOWNLOAD_STORES))
                return
            while self.selected_store is None and not self.preferences.ask_store_each_time:
                if self._configure_store(first_run=True):
                    break
                if self._confirm_exit():
                    return
            while True:
                self._handle_download_completions()
                options = (
                    self._t(TranslationKey.SEARCH_LIBRARY),
                    self._t(TranslationKey.DIRECT_DOWNLOAD),
                    self._download_queue_menu_label(),
                    self._t(TranslationKey.MANAGE_GAMES),
                    self._t(TranslationKey.SEARCH_BIOS),
                    self._t(TranslationKey.SETTINGS),
                    self._t(TranslationKey.STATUS_CONTROLS),
                    self._t(TranslationKey.EXIT),
                )
                choice = self._menu(
                    self._t(TranslationKey.APP_TITLE),
                    options,
                    self._t(TranslationKey.MAIN_FOOTER),
                )
                if choice is None or choice == 7:
                    if self._confirm_exit():
                        return
                    continue
                if choice == 0:
                    self._search_flow()
                elif choice == 1:
                    self._direct_download_flow()
                elif choice == 2:
                    self._download_queue_screen()
                elif choice == 3:
                    self._manage_library_flow()
                elif choice == 4:
                    self._bios_search_flow()
                elif choice == 5:
                    self._settings_screen()
                elif choice == 6:
                    self._status_screen()
                if self.exit_after_update:
                    return
        finally:
            self.download_queue.shutdown()
            self.refresh_on_exit = self.refresh_on_exit or self.download_queue.refresh_required
            if self.refresh_on_exit:
                LOGGER.info("Requesting EmulationStation refresh on TUI exit")
                if request_game_frontend_refresh(target=self.config.target):
                    self.download_queue.mark_refreshed()
            if self.gamepad is not None:
                self.gamepad.close()
            LOGGER.info("TUI session finished")

    def _download_queue_menu_label(self) -> str:
        """Keep the Downloads entry visible with the current persisted job count."""

        return f"{self._t(TranslationKey.DOWNLOAD_QUEUE)}  [{len(self.download_queue.jobs())}]"

    def _search_flow(self) -> None:
        store = self._store_for_operation(self._t(TranslationKey.CHOOSE_STORE))
        if store is None:
            return
        platforms = tuple(
            platform for platform in self.platforms if store.supports_platform(platform)
        )
        platform_filter = ""
        while True:
            visible_platforms = tuple(
                platform
                for platform in platforms
                if _platform_matches_filter(platform, platform_filter)
            )
            labels = [f"{item.name}  [{item.alias}]" for item in visible_platforms]
            choice = self._menu(
                self._t(TranslationKey.CHOOSE_PLATFORM),
                labels,
                self._t(TranslationKey.PLATFORM_FILTER_FOOTER),
                gamepad_keys=SEARCH_RESULTS_GAMEPAD_KEYS,
                shortcuts=SEARCH_RESULTS_SHORTCUTS,
            )
            if choice is None:
                return
            if choice == SEARCH_FILTER_CHOICE:
                query = self._on_screen_keyboard(
                    self._t(TranslationKey.PLATFORM_FILTER_TITLE),
                    allow_lowercase=True,
                    empty_hint=self._t(TranslationKey.PLATFORM_FILTER_HINT),
                )
                if query is None:
                    continue
                if query and not any(
                    _platform_matches_filter(platform, query) for platform in platforms
                ):
                    self._draw_message(
                        self._t(TranslationKey.NO_RESULTS),
                        self._t(TranslationKey.NO_MATCHING_PLATFORMS, query=query),
                        3,
                        wait=True,
                    )
                    continue
                platform_filter = query
                continue
            if choice == SEARCH_RESET_CHOICE:
                platform_filter = ""
                continue
            self._search_platform_flow(store, visible_platforms[choice])

    def _search_platform_flow(self, store: GameStore, platform: Platform) -> None:
        """Keep search navigation within one platform until the user goes back one level."""

        while True:
            query = self._on_screen_keyboard(
                self._t(TranslationKey.SEARCH_TITLE, platform=platform.alias),
                empty_hint=self._t(TranslationKey.SEARCH_EMPTY_HINT),
            )
            if query is None:
                return
            description = (
                self._t(TranslationKey.LOOKING_FOR, query=query)
                if query
                else self._t(TranslationKey.LOADING_ALL, platform=platform.name)
            )
            self._draw_message(self._t(TranslationKey.SEARCHING), description, 1)
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
                    self._t(TranslationKey.NOTHING_MATCHED, query=query)
                    if query
                    else self._t(TranslationKey.CATALOGUE_EMPTY)
                )
                self._draw_message(self._t(TranslationKey.NO_RESULTS), message, 3, wait=True)
                continue
            self._results_flow(results, platform, store)
            LOGGER.info("Search produced %d result(s)", len(results))

    def _catalog_progress(self, current: int, total: int) -> None:
        percent = int(current * 100 / total)
        self._draw_message(
            self._t(TranslationKey.LOADING_CATALOGUE),
            self._t(
                TranslationKey.LOADING_CATALOGUE_PROGRESS,
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
        store: GameStore,
    ) -> None:
        system_filter: str | None = None
        while True:
            visible_results = [
                result
                for result in results
                if system_filter is None
                or (result.system and result.system.casefold() == system_filter.casefold())
            ]
            labels = []
            for result in visible_results:
                prefix = f"{result.system} | " if result.system else ""
                detail = f" - {result.region}" if result.region else ""
                labels.append(f"{prefix}{result.title}{detail}")
            choice = self._menu(
                self._t(
                    TranslationKey.RESULTS_TITLE,
                    store=store.display_name.upper(),
                    count=len(visible_results),
                ),
                labels,
                self._t(TranslationKey.RESULTS_FOOTER),
                gamepad_keys=SEARCH_RESULTS_GAMEPAD_KEYS,
                shortcuts=SEARCH_RESULTS_SHORTCUTS,
            )
            if choice is None:
                return
            if choice == SEARCH_FILTER_CHOICE:
                systems = sorted(
                    {result.system for result in results if result.system},
                    key=str.casefold,
                )
                filter_choice = self._menu(
                    self._t(TranslationKey.FILTER_CONSOLE),
                    [self._t(TranslationKey.ALL_CONSOLES), *systems],
                    self._t(TranslationKey.FILTER_CONSOLE_FOOTER),
                )
                if filter_choice is not None:
                    system_filter = None if filter_choice == 0 else systems[filter_choice - 1]
                continue
            if choice == SEARCH_RESET_CHOICE:
                system_filter = None
                continue
            result = visible_results[choice]
            effective_platform = platform
            if not platform.code and result.system:
                resolved = resolve_platform(result.system, self.platforms)
                if resolved is not None:
                    effective_platform = resolved
            self._draw_message(
                self._t(TranslationKey.CHECKING_COMPATIBILITY),
                self._t(TranslationKey.MATCHING_COMPATIBILITY),
                1,
            )
            info = self.compatibility_client.lookup_many((result,), effective_platform)[0]
            details = [
                result.title,
                self._t(
                    TranslationKey.SYSTEM_FIELD, value=result.system or effective_platform.name
                ),
                self._t(TranslationKey.REGION_FIELD, value=result.region or "-"),
                self._t(TranslationKey.VERSION_FIELD, value=result.version or "-"),
                self._t(TranslationKey.LANGUAGES_FIELD, value=result.languages),
                self._t(TranslationKey.RATING_FIELD, value=result.rating),
                self._t(
                    TranslationKey.COMPATIBILITY_FIELD,
                    value=self._compatibility_label(info, detail=True),
                ),
            ]
            action = self._menu(
                self._t(TranslationKey.TITLE_DETAILS),
                [*details, self._t(TranslationKey.DOWNLOAD), self._t(TranslationKey.BACK)],
                self._t(TranslationKey.SELECT_DOWNLOAD),
            )
            if action == len(details):
                self._download_detail(
                    result.link,
                    effective_platform,
                    store,
                    title=result.title,
                    region=result.region,
                )
            elif action is None or action == len(details) + 1:
                continue

    def _direct_download_flow(self) -> None:
        store = self._store_for_operation(self._t(TranslationKey.CHOOSE_STORE))
        if store is None:
            return
        platforms = tuple(
            platform
            for platform in self.platforms
            if platform.rom_folder is not None and store.supports_platform(platform)
        )
        choice = self._menu(
            self._t(TranslationKey.DESTINATION_PLATFORM),
            [
                f"{item.name} -> {self._platform_for_store(store, item).rom_folder}"
                for item in platforms
            ],
            self._t(TranslationKey.DESTINATION_PLATFORM_FOOTER),
        )
        if choice is None:
            return
        url = self._on_screen_keyboard(self._t(TranslationKey.DETAIL_URL), allow_lowercase=True)
        if not url:
            return
        self._download_detail(url, platforms[choice], store, title=url)

    def _download_detail(
        self,
        detail_url: str,
        platform: Platform,
        store: GameStore,
        *,
        title: str | None = None,
        region: str | None = None,
    ) -> None:
        install_platform = self._platform_for_store(store, platform)
        if install_platform.rom_folder is None:
            self._error(self._t(TranslationKey.PLATFORM_HAS_NO_ROM_FOLDER))
            return
        roms_directory = self._choose_roms_directory()
        if roms_directory is None:
            self._error(self._t(TranslationKey.NO_ROM_PARTITION_ENVIRONMENT))
            return
        self._draw_message(
            self._t(TranslationKey.PREPARING),
            self._t(TranslationKey.RETRIEVING_DOWNLOAD_LINK),
            1,
        )
        try:
            media = store.download_request(detail_url)
            job = self.download_queue.enqueue(
                title=title or media.expected_filename or detail_url,
                store_id=store.store_id,
                store_name=store.display_name,
                referrer=store.download_referrer,
                media=(media,),
                platform=install_platform,
                roms_directory=roms_directory,
                timeout_seconds=self.config.timeout_seconds,
                bios_directory=self.preferences.bios_directory,
                bittorrent_settings=(
                    self.preferences.minerva_bittorrent if store.store_id == "minerva" else None
                ),
                region=region,
            )
        except (StoreError, DownloadError) as error:
            LOGGER.error("Could not queue game download: %s", error)
            self._operation_error(error)
            return
        LOGGER.info("Game download queued id=%s store=%s", job.job_id, store.store_id)
        self._draw_message(
            self._t(TranslationKey.DOWNLOAD_QUEUED),
            self._t(
                TranslationKey.DOWNLOAD_QUEUED_MESSAGE,
                title=job.title,
                store=job.store_name,
            ),
            4,
            wait=True,
        )

    def _handle_download_completions(self) -> None:
        for job in self.download_queue.jobs():
            if (
                job.state is not DownloadState.COMPLETED
                or job.job_id in self._handled_completed_jobs
            ):
                continue
            self._handled_completed_jobs.add(job.job_id)
            required_bios = self._bios_followup(
                job.platform,
                job.roms_directory,
                job.region,
                job.bios_directory,
            )
            bundled_message = (
                "\n" + self._t(TranslationKey.INSTALLED_BUNDLED_BIOS, count=job.bundled_bios_count)
                if job.bundled_bios_count
                else ""
            )
            required_message = (
                "\n" + self._t(TranslationKey.INSTALLED_REQUIRED_BIOS, count=required_bios)
                if required_bios
                else ""
            )
            destination = job.completed_path.parent if job.completed_path is not None else "-"
            filename = job.completed_path.name if job.completed_path is not None else job.title
            message = (
                self._t(
                    TranslationKey.GAME_UPDATED_MESSAGE,
                    filename=filename,
                    destination=destination,
                    bundled=bundled_message,
                    required=required_message,
                )
                if job.is_update
                else self._t(
                    TranslationKey.DOWNLOAD_COMPLETE_MESSAGE,
                    filename=filename,
                    destination=destination,
                    bios=bundled_message + required_message,
                )
            )
            self._draw_message(
                self._t(
                    TranslationKey.GAME_UPDATED
                    if job.is_update
                    else TranslationKey.DOWNLOAD_COMPLETE
                ),
                message,
                4,
                wait=True,
            )
            self.download_queue.dismiss_completed(job.job_id)

    def _download_queue_screen(self) -> None:
        while True:
            jobs: tuple[DownloadJob, ...] = ()

            def menu_options() -> Sequence[str]:
                nonlocal jobs
                jobs = tuple(
                    job
                    for job in self.download_queue.jobs()
                    if job.state is not DownloadState.COMPLETED
                )
                if not jobs:
                    return ()
                _height, width = self.screen.getmaxyx()
                return [
                    *self._download_job_labels(jobs, max(1, width - 6)),
                    self._t(TranslationKey.REFRESH_DOWNLOAD_STATUS),
                ]

            initial_options = menu_options()
            if not jobs:
                self._draw_message(
                    self._t(TranslationKey.DOWNLOAD_QUEUE_EMPTY),
                    self._t(TranslationKey.DOWNLOAD_QUEUE_EMPTY_MESSAGE),
                    1,
                    wait=True,
                )
                return
            choice = self._menu(
                self._t(TranslationKey.DOWNLOAD_QUEUE_TITLE),
                initial_options,
                self._t(TranslationKey.DOWNLOAD_QUEUE_FOOTER),
                refresh_options=menu_options,
                refresh_seconds=MENU_REDRAW_SECONDS,
            )
            if choice is None:
                return
            if choice >= len(jobs):
                continue
            self._download_job_controls(jobs[choice])

    def _download_job_fields(self, job: DownloadJob) -> tuple[str, str, str]:
        state = self._t(TranslationKey(f"download_state_{job.state.value}"))
        if job.total_bytes:
            percent = min(100, int(job.downloaded_bytes * 100 / job.total_bytes))
            progress = self._t(TranslationKey.DOWNLOAD_PROGRESS_PERCENT, percent=percent)
        elif job.downloaded_bytes:
            progress = self._t(
                TranslationKey.DOWNLOAD_PROGRESS_SIZE,
                size=self._format_file_size(job.downloaded_bytes),
            )
        else:
            progress = self._t(TranslationKey.DOWNLOAD_PROGRESS_WAITING)
        return progress, state, job.store_name

    def _download_job_label(
        self,
        job: DownloadJob,
        widths: tuple[int, int, int] | None = None,
    ) -> str:
        progress, state, store = self._download_job_fields(job)
        progress_width, state_width, store_width = widths or (
            len(progress),
            len(state),
            len(store),
        )
        progress = _fit_column(progress, progress_width)
        state = _fit_column(state, state_width)
        store = _fit_column(store, store_width)
        return (
            f"{progress:>{progress_width}} | "
            f"{state:<{state_width}} | "
            f"{store:<{store_width}} | {job.title}"
        )

    def _download_job_labels(
        self,
        jobs: Sequence[DownloadJob],
        available_width: int,
    ) -> list[str]:
        fields = [self._download_job_fields(job) for job in jobs]
        desired = [
            min(10, max(len(progress) for progress, _state, _store in fields)),
            min(16, max(len(state) for _progress, state, _store in fields)),
            min(12, max(len(store) for _progress, _state, store in fields)),
        ]
        minimums = (5, 7, 5)
        column_budget = max(sum(minimums), available_width - 17)
        while sum(desired) > column_budget:
            shrinkable = [
                (width - minimum, index)
                for index, (width, minimum) in enumerate(zip(desired, minimums, strict=True))
                if width > minimum
            ]
            if not shrinkable:
                break
            _room, index = max(shrinkable)
            desired[index] -= 1
        widths = (desired[0], desired[1], desired[2])
        return [self._download_job_label(job, widths) for job in jobs]

    def _download_job_controls(self, job: DownloadJob) -> None:
        current = self.download_queue.find(job.job_id)
        if current is None:
            return
        details = [
            current.title,
            self._t(TranslationKey.DOWNLOAD_STORE_FIELD, value=current.store_name),
            self._t(
                TranslationKey.DOWNLOAD_STATUS_FIELD,
                value=self._t(TranslationKey(f"download_state_{current.state.value}")),
            ),
            self._t(
                TranslationKey.DOWNLOAD_PROGRESS_FIELD,
                value=self._download_progress_detail(current),
            ),
        ]
        if current.error:
            details.append(self._t(TranslationKey.DOWNLOAD_ERROR_FIELD, value=current.error))
        if current.state is DownloadState.RATE_LIMITED and current.retry_at is not None:
            seconds = max(0, int(current.retry_at - time.time() + 0.999))
            details.append(
                self._t(
                    TranslationKey.DOWNLOAD_RETRY_FIELD,
                    attempt=current.retry_attempt,
                    seconds=seconds,
                )
            )
        actions: list[str] = []
        options = list(details)
        if current.state in {
            DownloadState.QUEUED,
            DownloadState.DOWNLOADING,
            DownloadState.RATE_LIMITED,
        }:
            options.extend(
                (self._t(TranslationKey.PAUSE_DOWNLOAD), self._t(TranslationKey.CANCEL_DOWNLOAD))
            )
            actions.extend(("pause", "cancel"))
        elif current.state is DownloadState.PAUSED:
            options.extend(
                (self._t(TranslationKey.RESUME_DOWNLOAD), self._t(TranslationKey.CANCEL_DOWNLOAD))
            )
            actions.extend(("resume", "cancel"))
        elif current.state in {DownloadState.FAILED, DownloadState.CANCELLED}:
            if current.torrent_candidates:
                options.append(self._t(TranslationKey.CHOOSE_MINERVA_TORRENT_FILE))
                actions.append("choose_file")
            options.extend(
                (self._t(TranslationKey.RETRY_DOWNLOAD), self._t(TranslationKey.CANCEL_DOWNLOAD))
            )
            actions.extend(("retry", "cancel"))
        options.append(self._t(TranslationKey.BACK))
        actions.append("back")
        choice = self._menu(
            self._t(TranslationKey.DOWNLOAD_DETAILS_TITLE),
            options,
            self._t(TranslationKey.DOWNLOAD_CONTROLS_FOOTER),
        )
        if choice is None or choice < len(details):
            return
        action = actions[choice - len(details)]
        if action == "pause":
            self.download_queue.pause(current.job_id)
        elif action == "resume":
            self.download_queue.resume(current.job_id)
        elif action == "retry":
            self.download_queue.retry(current.job_id)
        elif action == "cancel":
            if self._confirm_download_cancel(current):
                self.download_queue.cancel(current.job_id)
        elif action == "choose_file":
            choice = self._choose_queued_torrent_file(current)
            if choice is not None and self.download_queue.choose_torrent_file(
                current.job_id,
                choice,
            ):
                self.download_queue.retry(current.job_id)

    def _download_progress_detail(self, job: DownloadJob) -> str:
        if job.total_bytes:
            return self._t(
                TranslationKey.DOWNLOAD_PROGRESS_BYTES,
                current=self._format_file_size(job.downloaded_bytes),
                total=self._format_file_size(job.total_bytes),
            )
        if job.downloaded_bytes:
            return self._format_file_size(job.downloaded_bytes)
        return self._t(TranslationKey.DOWNLOAD_PROGRESS_WAITING)

    def _confirm_download_cancel(self, job: DownloadJob) -> bool:
        choice = self._menu(
            self._t(TranslationKey.CONFIRM_DOWNLOAD_CANCEL),
            (
                self._t(TranslationKey.KEEP_DOWNLOADING, title=job.title),
                self._t(TranslationKey.CANCEL_AND_REMOVE_PARTIAL),
            ),
            self._t(TranslationKey.CANCEL_DOWNLOAD_WARNING),
        )
        return choice == 1

    def _choose_queued_torrent_file(self, job: DownloadJob) -> TorrentFileChoice | None:
        choice = self._menu(
            self._t(TranslationKey.CHOOSE_MINERVA_TORRENT_FILE),
            [
                self._t(
                    TranslationKey.MINERVA_CANDIDATE,
                    index=candidate.index,
                    filename=candidate.filename,
                    size=self._format_file_size(candidate.length),
                    score=round(candidate.match_score * 100),
                    path="/".join(candidate.path),
                )
                for candidate in job.torrent_candidates
            ],
            self._t(TranslationKey.MINERVA_CANDIDATES_FOOTER),
        )
        return job.torrent_candidates[choice] if choice is not None else None

    def _manage_library_flow(self) -> None:
        if not self.roms_directories:
            self._error(self._t(TranslationKey.NO_ROM_PARTITIONS))
            return
        while True:
            root = self._choose_from_roots(
                self.roms_directories,
                self._t(TranslationKey.CHOOSE_MEMORY_CARD),
            )
            if root is None:
                return
            self._draw_message(
                self._t(TranslationKey.CHECKING_FOLDERS),
                self._t(TranslationKey.FINDING_INSTALLED_PLATFORMS, root=root),
                1,
            )
            platforms = platforms_with_installed_games(root, self.platforms)
            if not platforms:
                self._draw_message(
                    self._t(TranslationKey.NO_GAMES_ON_CARD),
                    self._t(TranslationKey.NO_SUPPORTED_GAMES_ON_CARD, root=root),
                    3,
                    wait=True,
                )
                continue
            platform_choice = self._menu(
                self._t(TranslationKey.CHOOSE_INSTALLED_PLATFORM),
                [platform.name for platform in platforms],
                self._t(TranslationKey.INSTALLED_PLATFORM_FOOTER),
            )
            if platform_choice is None:
                continue
            self._manage_platform_library(root, platforms[platform_choice])

    def _manage_platform_library(self, root: Path, platform: Platform) -> None:
        self._draw_message(
            self._t(TranslationKey.SCANNING_PLATFORM),
            self._t(TranslationKey.READING_PLATFORM, platform=platform.name, root=root),
            1,
        )
        games = scan_library((root,), (platform,))
        if not games:
            self._draw_message(
                self._t(TranslationKey.NO_GAMES),
                self._t(TranslationKey.NO_PLATFORM_GAMES, platform=platform.name),
                3,
                wait=True,
            )
            return
        while games:
            game_choice = self._menu(
                self._t(TranslationKey.PLATFORM_ON_CARD, platform=platform.alias, root=root),
                [game.title for game in games],
                self._t(TranslationKey.MANAGE_GAMES_FOOTER),
            )
            if game_choice is None:
                return
            if self._manage_game(games[game_choice]):
                self._draw_message(
                    self._t(TranslationKey.REFRESHING),
                    self._t(TranslationKey.REFRESHING_PLATFORM, platform=platform.name),
                    1,
                )
                games = scan_library((root,), (platform,))

    def _manage_game(self, game: InstalledGame) -> bool:
        description = (
            game.title,
            self._t(TranslationKey.CARD_FIELD, value=game.roms_directory),
            self._t(TranslationKey.FILE_FIELD, value=game.primary_file.name),
            self._t(TranslationKey.FILES_IN_GROUP, count=len(game.files)),
            self._t(TranslationKey.UPDATE_FROM_REMOTE),
            self._t(TranslationKey.DELETE_FROM_DEVICE),
            self._t(TranslationKey.BACK),
        )
        choice = self._menu(
            self._t(TranslationKey.MANAGE_GAME),
            description,
            self._t(TranslationKey.MANAGE_GAME_FOOTER),
        )
        if choice == 4:
            return self._update_game(game)
        if choice == 5:
            return self._confirm_delete(game)
        return False

    def _confirm_delete(self, game: InstalledGame) -> bool:
        choice = self._menu(
            self._t(TranslationKey.CONFIRM_PERMANENT_DELETE),
            (
                self._t(TranslationKey.KEEP_GAME, title=game.title),
                self._t(TranslationKey.DELETE_FILES, count=len(game.files)),
            ),
            self._t(TranslationKey.DELETE_WARNING),
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
            self._t(TranslationKey.GAME_DELETED),
            self._t(TranslationKey.GAME_DELETED_MESSAGE, title=game.title),
            4,
            wait=True,
        )
        return True

    def _update_game(self, game: InstalledGame) -> bool:
        store = self._store_for_operation(
            self._t(TranslationKey.CHOOSE_STORE),
            game.platform,
        )
        if store is None:
            return False
        if not store.supports_platform(game.platform):
            self._error(
                self._t(
                    TranslationKey.STORE_PLATFORM_UNSUPPORTED,
                    store=store.display_name,
                    platform=game.platform.name,
                )
            )
            return False
        self._draw_message(self._t(TranslationKey.SEARCHING_FOR_UPDATE), game.title, 1)
        try:
            results = store.search(store.platform_code(game.platform), game.title)
        except StoreError as error:
            self._operation_error(error)
            return False
        if not results:
            self._draw_message(self._t(TranslationKey.NO_REMOTE_MATCH), game.title, 3, wait=True)
            return False
        choice = self._menu(
            self._t(TranslationKey.CHOOSE_REPLACEMENT),
            [
                "{} - {} - {}".format(result.title, result.region or "-", result.version or "-")
                for result in results
            ],
            self._t(TranslationKey.REPLACEMENT_FOOTER),
        )
        if choice is None:
            return False
        selected = results[choice]
        confirmation = self._menu(
            self._t(TranslationKey.CONFIRM_UPDATE),
            (
                self._t(TranslationKey.KEEP_FILE, filename=game.primary_file.name),
                self._t(TranslationKey.REPLACE_WITH, title=selected.title),
            ),
            self._t(TranslationKey.CONFIRM_CHOICE_FOOTER),
        )
        if confirmation != 1:
            return False
        try:
            media = store.download_request(selected.link)
            job = self.download_queue.enqueue(
                title=selected.title,
                store_id=store.store_id,
                store_name=store.display_name,
                referrer=store.download_referrer,
                media=(media,),
                platform=game.platform,
                roms_directory=game.roms_directory,
                timeout_seconds=self.config.timeout_seconds,
                bios_directory=self.preferences.bios_directory,
                bittorrent_settings=(
                    self.preferences.minerva_bittorrent if store.store_id == "minerva" else None
                ),
                region=selected.region,
                replacement_game=game,
            )
        except (StoreError, DownloadError) as error:
            LOGGER.error("Could not queue game update title=%r: %s", game.title, error)
            self._operation_error(error)
            return False
        LOGGER.info("Game update queued id=%s title=%r", job.job_id, game.title)
        self._draw_message(
            self._t(TranslationKey.UPDATE_QUEUED),
            self._t(
                TranslationKey.UPDATE_QUEUED_MESSAGE,
                title=selected.title,
                store=store.display_name,
            ),
            4,
            wait=True,
        )
        return False

    def _choose_roms_directory(self) -> Path | None:
        preferred = self._preferred_roms_directory()
        if preferred is not None:
            return preferred
        return self._choose_from_roots(
            self.roms_directories,
            self._t(TranslationKey.CHOOSE_DESTINATION_CARD),
        )

    def _preferred_roms_directory(self) -> Path | None:
        configured = self.preferences.default_roms_directory
        if configured is None:
            return None
        preferred = Path(configured).expanduser()
        return next((root for root in self.roms_directories if root == preferred), None)

    def _choose_store(self, title: str, platform: Platform | None = None) -> GameStore | None:
        stores = tuple(
            store
            for store in self.store_catalog.stores
            if platform is None or store.supports_platform(platform)
        )
        choice = self._menu(
            title,
            [f"{store.display_name} - {self._store_description(store)}" for store in stores],
            self._t(TranslationKey.CHOOSE_STORE_FOOTER),
        )
        return stores[choice] if choice is not None else None

    def _store_for_operation(
        self,
        title: str,
        platform: Platform | None = None,
    ) -> GameStore | None:
        """Use the default store or prompt when manual selection is configured."""

        if self.preferences.ask_store_each_time:
            return self._choose_store(title, platform)
        return self.selected_store

    def _configure_store(self, *, first_run: bool = False) -> bool:
        title = self._t(
            TranslationKey.FIRST_RUN_STORE if first_run else TranslationKey.CHOOSE_DEFAULT_STORE
        )
        stores = self.store_catalog.stores
        choice = self._menu(
            title,
            [
                *(f"{store.display_name} - {self._store_description(store)}" for store in stores),
                self._t(TranslationKey.MANUAL_EVERY_TIME),
            ],
            self._t(TranslationKey.CHOOSE_STORE_FOOTER),
        )
        if choice is None:
            return False
        manual = choice == len(stores)
        store = None if manual else stores[choice]
        preferences = load_preferences(self.preferences_path)
        updated_preferences = replace(
            preferences,
            store_id=store.store_id if store is not None else None,
            ask_store_each_time=manual,
        )
        try:
            save_preferences(self.preferences_path, updated_preferences)
        except PreferencesError as error:
            self._operation_error(error)
            return False
        self.preferences = updated_preferences
        self.selected_store = store
        store_label = (
            store.display_name if store is not None else self._t(TranslationKey.MANUAL_EVERY_TIME)
        )
        LOGGER.info(
            "Default store changed to %s",
            store.store_id if store is not None else "manual",
        )
        if not first_run:
            self._draw_message(
                self._t(TranslationKey.SETTINGS_SAVED),
                self._t(TranslationKey.STORE_SAVED_MESSAGE, store=store_label),
                4,
                wait=True,
            )
        return True

    def _settings_screen(self) -> None:
        while True:
            current = (
                self._t(TranslationKey.MANUAL_EVERY_TIME)
                if self.preferences.ask_store_each_time
                else self.selected_store.display_name
                if self.selected_store is not None
                else self._t(TranslationKey.NOT_SET)
            )
            retrobios_status = self._retrobios_cache_label()
            compatibility_status = self._compatibility_cache_label()
            game_catalogue_count = sum(
                store.catalogue_cache_file_count() for store in self.store_catalog.stores
            )
            options = [
                self._t(TranslationKey.CHANGE_STORE, value=current),
                self._t(
                    TranslationKey.DEFAULT_ROM_DESTINATION,
                    value=(
                        str(self._preferred_roms_directory())
                        if self._preferred_roms_directory() is not None
                        else self._t(TranslationKey.MANUAL_EVERY_TIME)
                    ),
                ),
                self._t(TranslationKey.CONSOLE_FOLDER_MAPPINGS),
                self._t(TranslationKey.BIOS_DIRECTORY, value=self.preferences.bios_directory),
                f"{self._t(TranslationKey.LANGUAGE)}  [{language_name(self.preferences.language)}]",
                self._t(TranslationKey.REFRESH_STORE_CACHE, count=game_catalogue_count),
                self._t(TranslationKey.UPDATE_BIOS_CATALOGUE, status=retrobios_status),
                self._t(TranslationKey.UPDATE_COMPATIBILITY, status=compatibility_status),
                self._t(TranslationKey.CACHE_LIFETIME, days=self.preferences.catalogue_ttl_days),
                self._t(
                    TranslationKey.MAX_CONCURRENT_DOWNLOADS,
                    count=self.preferences.max_concurrent_downloads,
                ),
                self._t(TranslationKey.RATE_LIMIT_RETRY_SETTINGS),
                self._t(
                    TranslationKey.NETWORK_TIMEOUT,
                    value=self.config.timeout_seconds,
                ),
                self._t(
                    TranslationKey.LOG_LEVEL,
                    value=self.preferences.log_level or self.config.log_level,
                ),
                self._t(
                    TranslationKey.FILE_LOGGING,
                    value=self._t(TranslationKey.ON)
                    if self._file_logging_enabled()
                    else self._t(TranslationKey.OFF),
                ),
            ]
            actions = [
                "store",
                "rom_destination",
                "console_mappings",
                "bios_directory",
                "language",
                "store_catalogue",
                "retrobios_update",
                "compatibility_update",
                "catalogue_ttl",
                "max_concurrent_downloads",
                "rate_limit_retry",
                "network_timeout",
                "log_level",
                "log_file",
            ]
            if (
                self.selected_store is not None and self.selected_store.store_id == "minerva"
            ) or self.store_catalog.find("minerva") is not None:
                options.append(self._t(TranslationKey.MINERVA_SETTINGS))
                actions.append("minerva")
            options.extend(
                (
                    self._t(TranslationKey.CHECK_UPDATE, version=installed_version()),
                    self._t(TranslationKey.BACK),
                )
            )
            actions.extend(("update", "back"))
            choice = self._menu(
                self._t(TranslationKey.SETTINGS_TITLE),
                options,
                self._t(TranslationKey.SETTINGS_FOOTER),
            )
            if choice is None or actions[choice] == "back":
                return
            action = actions[choice]
            if action == "store":
                self._configure_store()
            elif action == "rom_destination":
                self._configure_default_roms_directory()
            elif action == "console_mappings":
                self._console_folder_mappings_screen()
            elif action == "bios_directory":
                self._configure_bios_directory()
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
            elif action == "max_concurrent_downloads":
                self._configure_max_concurrent_downloads()
            elif action == "rate_limit_retry":
                self._rate_limit_retry_settings_screen()
            elif action == "network_timeout":
                self._configure_network_timeout()
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

    def _configure_default_roms_directory(self) -> None:
        choice = self._menu(
            self._t(TranslationKey.DEFAULT_ROM_DESTINATION_TITLE),
            [
                self._t(TranslationKey.MANUAL_EVERY_TIME),
                *(str(root) for root in self.roms_directories),
            ],
            self._t(TranslationKey.DEFAULT_ROM_DESTINATION_FOOTER),
        )
        if choice is None:
            return
        destination = None if choice == 0 else str(self.roms_directories[choice - 1])
        display = destination or self._t(TranslationKey.MANUAL_EVERY_TIME)
        self._save_runtime_preferences(
            replace(self.preferences, default_roms_directory=destination),
            self._t(TranslationKey.DEFAULT_ROM_DESTINATION_SAVED),
            self._t(TranslationKey.DEFAULT_ROM_DESTINATION_SAVED_MESSAGE, destination=display),
        )

    def _platform_for_store(self, store: GameStore, platform: Platform) -> Platform:
        directory = self.preferences.store_rom_mappings.get(store.store_id, {}).get(platform.slug)
        if directory is None:
            return platform
        return replace(platform, rom_folder=directory, alternate_folders=())

    def _rom_folder_choices(self) -> tuple[str, ...]:
        folders = {
            folder for platform in self.platforms for folder in platform.rom_folders if folder
        }
        for root in self.roms_directories:
            with contextlib.suppress(OSError):
                folders.update(
                    entry.name
                    for entry in root.iterdir()
                    if entry.is_dir() and not entry.name.startswith(".")
                )
        return tuple(sorted(folders, key=str.casefold))

    def _console_folder_mappings_screen(self) -> None:
        store = self._choose_store(self._t(TranslationKey.CHOOSE_MAPPING_STORE))
        if store is None:
            return
        platforms = tuple(
            platform
            for platform in self.platforms
            if platform.slug != "all"
            and platform.rom_folder is not None
            and store.supports_platform(platform)
        )
        while True:
            choice = self._menu(
                self._t(TranslationKey.CONSOLE_FOLDER_MAPPINGS_TITLE, store=store.display_name),
                [
                    self._t(
                        TranslationKey.CONSOLE_FOLDER_MAPPING,
                        console=platform.name,
                        folder=self._platform_for_store(store, platform).rom_folder,
                    )
                    for platform in platforms
                ]
                + [self._t(TranslationKey.BACK)],
                self._t(TranslationKey.CONSOLE_FOLDER_MAPPINGS_FOOTER),
            )
            if choice is None or choice == len(platforms):
                return
            platform = platforms[choice]
            folders = self._rom_folder_choices()
            folder_choice = self._menu(
                self._t(TranslationKey.CHOOSE_CONSOLE_FOLDER, console=platform.name),
                [
                    self._t(TranslationKey.AUTOMATIC_FOLDER, folder=platform.rom_folder),
                    *folders,
                ],
                self._t(TranslationKey.CHOOSE_CONSOLE_FOLDER_FOOTER),
            )
            if folder_choice is None:
                continue
            mappings = {
                store_id: dict(platform_mappings)
                for store_id, platform_mappings in self.preferences.store_rom_mappings.items()
            }
            store_mappings = mappings.setdefault(store.store_id, {})
            if folder_choice == 0:
                store_mappings.pop(platform.slug, None)
            else:
                store_mappings[platform.slug] = folders[folder_choice - 1]
            if not store_mappings:
                mappings.pop(store.store_id, None)
            destination = platform.rom_folder if folder_choice == 0 else folders[folder_choice - 1]
            self._save_runtime_preferences(
                replace(self.preferences, store_rom_mappings=mappings),
                self._t(TranslationKey.CONSOLE_FOLDER_MAPPING_SAVED),
                self._t(
                    TranslationKey.CONSOLE_FOLDER_MAPPING_SAVED_MESSAGE,
                    store=store.display_name,
                    console=platform.name,
                    folder=destination,
                ),
            )

    def _configure_bios_directory(self) -> None:
        folders = self._rom_folder_choices()
        choices = tuple(folder for folder in folders if folder != "bios")
        choice = self._menu(
            self._t(TranslationKey.BIOS_DIRECTORY_TITLE),
            [self._t(TranslationKey.AUTOMATIC_FOLDER, folder="bios"), *choices],
            self._t(TranslationKey.BIOS_DIRECTORY_FOOTER),
        )
        if choice is None:
            return
        directory = "bios" if choice == 0 else choices[choice - 1]
        self._save_runtime_preferences(
            replace(self.preferences, bios_directory=directory),
            self._t(TranslationKey.BIOS_DIRECTORY_SAVED),
            self._t(TranslationKey.BIOS_DIRECTORY_SAVED_MESSAGE, directory=directory),
        )

    def _configure_language(self) -> None:
        choice = self._menu(
            self._t(TranslationKey.CHOOSE_LANGUAGE),
            [language.name for language in LANGUAGES],
            self._t(TranslationKey.LANGUAGE_FOOTER),
        )
        if choice is None:
            return
        language = LANGUAGES[choice]
        self._save_runtime_preferences(
            replace(self.preferences, language=language.code),
            translate(language.code, TranslationKey.LANGUAGE_SAVED),
            translate(
                language.code,
                TranslationKey.LANGUAGE_SAVED_MESSAGE,
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
                (self._t(TranslationKey.FALSE), self._t(TranslationKey.TRUE)),
                self._t(TranslationKey.FILE_LOGGING_FOOTER),
            )
            return None if choice is None else choice == 1
        hint_key = (
            TranslationKey.INTEGER_KEYBOARD
            if input_kind is SettingInputKind.INTEGER
            else TranslationKey.FLOAT_KEYBOARD
            if input_kind is SettingInputKind.FLOAT
            else TranslationKey.MIXED_KEYBOARD
        )
        return self._on_screen_keyboard(
            title,
            allow_lowercase=input_kind is SettingInputKind.MIXED,
            empty_hint=f"{self._t(hint_key)}; {current}",
            input_kind=input_kind,
        )

    def _configure_catalogue_ttl(self) -> None:
        raw_value = self._edit_setting(
            self._t(TranslationKey.CACHE_DAYS_TITLE),
            self._t(
                TranslationKey.CACHE_DAYS_HINT,
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
                self._error(self._t(TranslationKey.CACHE_LIFETIME_RANGE))
                return
        except ValueError:
            self._error(self._t(TranslationKey.INVALID_CACHE_LIFETIME))
            return
        self._save_runtime_preferences(
            replace(self.preferences, catalogue_ttl_days=days),
            self._t(TranslationKey.CACHE_LIFETIME_SAVED),
            self._t(TranslationKey.CACHE_LIFETIME_SAVED_MESSAGE, days=days),
        )

    def _configure_max_concurrent_downloads(self) -> None:
        raw_value = self._edit_setting(
            self._t(TranslationKey.MAX_CONCURRENT_DOWNLOADS_TITLE),
            self._t(
                TranslationKey.MAX_CONCURRENT_DOWNLOADS_HINT,
                current=self.preferences.max_concurrent_downloads,
            ),
            SettingInputKind.INTEGER,
        )
        if raw_value is None:
            return
        assert isinstance(raw_value, str)
        try:
            count = int(raw_value)
        except ValueError:
            self._error(self._t(TranslationKey.MAX_CONCURRENT_DOWNLOADS_RANGE))
            return
        if not 1 <= count <= 8:
            self._error(self._t(TranslationKey.MAX_CONCURRENT_DOWNLOADS_RANGE))
            return
        self._save_runtime_preferences(
            replace(self.preferences, max_concurrent_downloads=count),
            self._t(TranslationKey.MAX_CONCURRENT_DOWNLOADS_SAVED),
            self._t(TranslationKey.MAX_CONCURRENT_DOWNLOADS_SAVED_MESSAGE, count=count),
        )

    def _configure_network_timeout(self) -> None:
        raw_value = self._edit_setting(
            self._t(TranslationKey.NETWORK_TIMEOUT_TITLE),
            self._t(TranslationKey.NETWORK_TIMEOUT_HINT, current=self.config.timeout_seconds),
            SettingInputKind.FLOAT,
        )
        if raw_value is None:
            return
        assert isinstance(raw_value, str)
        try:
            timeout_seconds = float(raw_value)
        except ValueError:
            self._error(self._t(TranslationKey.NETWORK_TIMEOUT_RANGE))
            return
        if not 1 <= timeout_seconds <= 3600:
            self._error(self._t(TranslationKey.NETWORK_TIMEOUT_RANGE))
            return
        self._save_runtime_preferences(
            replace(self.preferences, network_timeout_seconds=timeout_seconds),
            self._t(TranslationKey.NETWORK_TIMEOUT_SAVED),
            self._t(TranslationKey.NETWORK_TIMEOUT_SAVED_MESSAGE, value=timeout_seconds),
        )

    def _rate_limit_retry_settings_screen(self) -> None:
        while True:
            settings = self.preferences.rate_limit_retry
            options = (
                self._t(TranslationKey.RATE_LIMIT_RETRY_BASE, value=settings.base_seconds),
                self._t(TranslationKey.RATE_LIMIT_RETRY_MAX, value=settings.max_seconds),
                self._t(TranslationKey.RATE_LIMIT_RETRY_JITTER, value=settings.jitter_ratio * 100),
                self._t(TranslationKey.BACK),
            )
            choice = self._menu(
                self._t(TranslationKey.RATE_LIMIT_RETRY_TITLE),
                options,
                self._t(TranslationKey.RATE_LIMIT_RETRY_FOOTER),
            )
            if choice is None or choice == 3:
                return
            title_key = (
                TranslationKey.RATE_LIMIT_RETRY_BASE_SECONDS_TITLE,
                TranslationKey.RATE_LIMIT_RETRY_MAX_SECONDS_TITLE,
                TranslationKey.RATE_LIMIT_RETRY_JITTER_RATIO_TITLE,
            )[choice]
            current = (
                settings.base_seconds,
                settings.max_seconds,
                settings.jitter_ratio * 100,
            )[choice]
            raw_value = self._edit_setting(
                self._t(title_key),
                str(current),
                SettingInputKind.FLOAT,
            )
            if raw_value is None:
                continue
            assert isinstance(raw_value, str)
            try:
                value = float(raw_value)
            except ValueError:
                self._error(self._t(TranslationKey.RATE_LIMIT_RETRY_INVALID))
                continue
            try:
                if choice == 0:
                    updated_settings = replace(settings, base_seconds=value)
                elif choice == 1:
                    updated_settings = replace(settings, max_seconds=value)
                else:
                    updated_settings = replace(settings, jitter_ratio=value / 100)
                if updated_settings.base_seconds > 3600:
                    raise ValueError
                if updated_settings.max_seconds > 24 * 60 * 60:
                    raise ValueError
            except ValueError:
                self._error(self._t(TranslationKey.RATE_LIMIT_RETRY_INVALID))
                continue
            if self._save_runtime_preferences(
                replace(self.preferences, rate_limit_retry=updated_settings),
                self._t(TranslationKey.RATE_LIMIT_RETRY_SAVED),
                self._t(TranslationKey.RATE_LIMIT_RETRY_SAVED_MESSAGE),
            ):
                self.download_queue.update_retry_settings(updated_settings)

    def _configure_log_level(self) -> None:
        levels = ("DEBUG", "INFO", "WARNING", "ERROR")
        choice = self._menu(
            self._t(TranslationKey.LOG_LEVEL_TITLE),
            levels,
            self._t(TranslationKey.LOG_LEVEL_FOOTER),
        )
        if choice is None:
            return
        level = levels[choice]
        self._save_runtime_preferences(
            replace(self.preferences, log_level=level),
            self._t(TranslationKey.LOG_LEVEL_SAVED),
            self._t(TranslationKey.LOG_LEVEL_SAVED_MESSAGE, level=level),
        )

    def _configure_file_logging(self) -> None:
        enabled = self._edit_setting(
            self._t(TranslationKey.FILE_LOGGING_TITLE),
            self._t(TranslationKey.ON)
            if self._file_logging_enabled()
            else self._t(TranslationKey.OFF),
            SettingInputKind.BOOLEAN,
        )
        if enabled is None:
            return
        assert isinstance(enabled, bool)
        self._save_runtime_preferences(
            replace(self.preferences, log_to_file=enabled),
            self._t(TranslationKey.FILE_LOGGING_SAVED),
            self._file_logging_message
            if enabled
            else self._t(TranslationKey.FILE_LOGGING_DISABLED),
        )

    def _save_runtime_preferences(
        self,
        preferences: Preferences,
        title: str,
        message: str | Callable[[], str],
    ) -> bool:
        try:
            save_preferences(self.preferences_path, preferences)
        except PreferencesError as error:
            self._operation_error(error)
            return False
        self.preferences = preferences
        self._apply_runtime_preferences()
        rendered_message = message if isinstance(message, str) else message()
        self._draw_message(title, rendered_message, 4, wait=True)
        return True

    def _apply_runtime_preferences(self) -> None:
        self.language = normalize_language(self.preferences.language)
        if self.preferences.network_timeout_seconds is not None:
            self.config = replace(
                self.config,
                timeout_seconds=self.preferences.network_timeout_seconds,
            )
        ttl_seconds = catalogue_ttl_seconds(self.preferences.catalogue_ttl_days)
        for store in self.store_catalog.stores:
            store.set_catalogue_ttl(ttl_seconds)
            store.set_network_timeout(self.config.timeout_seconds)
        self.retrobios_repository.ttl_seconds = ttl_seconds
        self.retrobios_repository.timeout_seconds = self.config.timeout_seconds
        if self.retrobios_catalog is not None:
            self.retrobios_catalog.ttl_seconds = ttl_seconds
        self.compatibility_client.ttl_seconds = ttl_seconds
        self.compatibility_client.timeout_seconds = self.config.timeout_seconds
        self._apply_logging_preferences()

    def _file_logging_enabled(self) -> bool:
        if self.preferences.log_to_file is not None:
            return self.preferences.log_to_file
        return self.config.log_file is not None

    def _apply_logging_preferences(self) -> None:
        log_file = None
        if self._file_logging_enabled():
            log_file = self.config.log_file or self.config.download_directory / "pocket-harbor.log"
        configure_logging_with_fallback(
            log_file,
            self.preferences.log_level or self.config.log_level,
            self.config.download_directory / "pocket-harbor.log" if log_file is not None else None,
        )

    def _file_logging_message(self) -> str:
        path = active_log_file()
        if path is None:
            return self._t(TranslationKey.FILE_LOGGING_FAILED)
        return self._t(TranslationKey.FILE_LOGGING_ENABLED, path=path)

    def _refresh_store_catalogue(self) -> None:
        stores = self.store_catalog.stores
        while True:
            store_choice = self._menu(
                self._t(TranslationKey.CHOOSE_STORE_CATALOGUE),
                [
                    self._t(
                        TranslationKey.STORE_CACHED_COUNT,
                        store=store.display_name,
                        count=store.catalogue_cache_file_count(),
                    )
                    for store in stores
                ],
                self._t(TranslationKey.CHOOSE_STORE_FOOTER),
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
                self._t(TranslationKey.REFRESH_STORE_TITLE, store=store.display_name.upper()),
                [
                    f"{platform.name}  [{self._store_cache_status_label(status)}]"
                    for platform, _system_code, status in choices
                ],
                self._t(TranslationKey.REFRESH_STORE_FOOTER),
            )
            if platform_choice is None:
                continue
            platform, system_code, _status = choices[platform_choice]
            self._draw_message(
                self._t(TranslationKey.REFRESHING_CATALOGUE),
                self._t(
                    TranslationKey.REFRESHING_CATALOGUE_MESSAGE,
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
                self._t(TranslationKey.CATALOGUE_UPDATED),
                self._t(
                    TranslationKey.CATALOGUE_UPDATED_MESSAGE,
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
            return self._t(TranslationKey.NOT_DOWNLOADED)
        return self._t(
            TranslationKey.STALE_GAMES if status.stale else TranslationKey.FRESH_GAMES,
            count=status.result_count,
        )

    def _store_description(self, store: GameStore) -> str:
        key = {
            "vimm": TranslationKey.STORE_DESCRIPTION_VIMM,
            "minerva": TranslationKey.STORE_DESCRIPTION_MINERVA,
        }.get(store.store_id)
        return self._t(key) if key is not None else store.description

    def _compatibility_label(
        self,
        info: CompatibilityInfo,
        *,
        detail: bool = False,
    ) -> str:
        level_key = {
            "not listed": TranslationKey.COMPATIBILITY_LEVEL_NOT_LISTED,
            "perfect": TranslationKey.COMPATIBILITY_LEVEL_PERFECT,
            "playable": TranslationKey.COMPATIBILITY_LEVEL_PLAYABLE,
            "limited": TranslationKey.COMPATIBILITY_LEVEL_LIMITED,
            "unsupported": TranslationKey.COMPATIBILITY_LEVEL_UNSUPPORTED,
        }.get(info.level.casefold())
        level = self._t(level_key) if level_key is not None else info.level
        if info.level == "Not listed":
            return self._t(TranslationKey.COMPATIBILITY_NOT_LISTED_SOURCE) if detail else level
        if detail:
            qualifier = (
                self._t(
                    TranslationKey.COMPATIBILITY_TITLE_MATCH,
                    score=round(info.match_score * 100),
                )
                if info.title_listed and info.match_score is not None
                else self._t(TranslationKey.COMPATIBILITY_TITLE_LISTED)
                if info.title_listed
                else self._t(TranslationKey.COMPATIBILITY_PLATFORM_RATING)
            )
            return self._t(TranslationKey.COMPATIBILITY_DETAIL, level=level, qualifier=qualifier)
        if info.title_listed and info.match_score is not None:
            return self._t(
                TranslationKey.COMPATIBILITY_MATCH,
                level=level,
                score=round(info.match_score * 100),
            )
        return (
            self._t(TranslationKey.COMPATIBILITY_LISTED, level=level)
            if info.title_listed
            else level
        )

    def _bios_state_label(self, state: BiosState) -> str:
        return self._t(TranslationKey(f"bios_state_{state.value}"))

    def _progress_label(self, label: str) -> str:
        key = {
            "Finding the latest RetroBIOS revision": TranslationKey.FINDING_RETROBIOS_REVISION,
            "Downloading RetroBIOS core profiles": TranslationKey.DOWNLOADING_RETROBIOS_PROFILES,
        }.get(label)
        return self._t(key) if key is not None else label

    def _retrobios_cache_label(self) -> str:
        if not hasattr(self, "retrobios_repository"):
            return self._t(TranslationKey.NOT_DOWNLOADED)
        try:
            catalogue = self.retrobios_repository.load()
        except BiosError:
            return self._t(TranslationKey.CACHE_INVALID)
        if catalogue is None:
            return self._t(TranslationKey.NOT_DOWNLOADED)
        freshness = (
            self._t(TranslationKey.STALE_OVER_DAYS, days=self.preferences.catalogue_ttl_days)
            if catalogue.cache_is_stale()
            else self._t(TranslationKey.FRESH)
        )
        return f"{catalogue.revision[:8]} - {freshness}"

    def _compatibility_cache_label(self) -> str:
        if not hasattr(self, "compatibility_client"):
            return self._t(TranslationKey.NOT_DOWNLOADED)
        age = self.compatibility_client.cache_age_seconds()
        if age is None:
            return self._t(TranslationKey.NOT_DOWNLOADED)
        return (
            self._t(TranslationKey.STALE_OVER_DAYS, days=self.preferences.catalogue_ttl_days)
            if self.compatibility_client.cache_is_stale()
            else self._t(TranslationKey.FRESH)
        )

    def _update_compatibility_catalogue(self) -> None:
        choice = self._menu(
            self._t(TranslationKey.COMPATIBILITY_UPDATE_TITLE),
            (
                self._t(TranslationKey.COMPATIBILITY_UPDATE_DOWNLOAD),
                self._t(TranslationKey.KEEP_CATALOGUE),
            ),
            self._t(TranslationKey.KEEP_CACHE_FOOTER),
        )
        if choice != 0:
            return
        self._draw_message(
            self._t(TranslationKey.COMPATIBILITY_UPDATING),
            self._t(TranslationKey.COMPATIBILITY_UPDATING_MESSAGE),
            1,
        )
        try:
            count = self.compatibility_client.refresh()
        except CompatibilityError as error:
            self._operation_error(error)
            return
        self._draw_message(
            self._t(TranslationKey.COMPATIBILITY_UPDATED),
            self._t(
                TranslationKey.COMPATIBILITY_UPDATED_MESSAGE,
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
            self._t(TranslationKey.CONNECTING_RETROBIOS),
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
            self._t(TranslationKey.RETROBIOS_UPDATE_TITLE),
            (
                self._t(TranslationKey.DOWNLOAD_LATEST_METADATA),
                self._t(TranslationKey.KEEP_CATALOGUE),
            ),
            self._t(TranslationKey.KEEP_CACHE_FOOTER),
        )
        if choice != 0:
            return
        try:
            catalogue = self._load_retrobios_catalogue(update=True)
        except BiosDownloadCancelled:
            self._draw_message(
                self._t(TranslationKey.RETROBIOS_UPDATE_CANCELLED),
                self._t(TranslationKey.CATALOGUE_UNCHANGED),
                3,
                wait=True,
            )
            return
        except BiosError as error:
            self._operation_error(error)
            return
        self._draw_message(
            self._t(TranslationKey.RETROBIOS_UPDATED),
            self._t(
                TranslationKey.RETROBIOS_SUMMARY,
                revision=catalogue.revision[:12],
                systems=len(catalogue.systems),
                profile=catalogue.retroarch_version or self._t(TranslationKey.UNKNOWN),
            ),
            4,
            wait=True,
        )

    def _bios_search_flow(self) -> None:
        root = self._choose_from_roots(
            self.roms_directories,
            self._t(TranslationKey.CHOOSE_BIOS_MEMORY_CARD),
        )
        if root is None:
            self._error(self._t(TranslationKey.NO_ROM_PARTITION))
            return
        try:
            catalogue = self._load_retrobios_catalogue()
        except BiosDownloadCancelled:
            return
        except BiosError as error:
            self._operation_error(error)
            return
        query = self._on_screen_keyboard(
            self._t(TranslationKey.SEARCH_BIOS_TITLE),
            empty_hint=self._t(TranslationKey.SEARCH_BIOS_EMPTY_HINT),
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
            for check in audit_bios(
                system.requirements,
                platform,
                root,
                self.preferences.bios_directory,
            ):
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
                self._t(TranslationKey.NO_BIOS_RESULTS),
                (
                    self._t(TranslationKey.NOTHING_MATCHED, query=query)
                    if query
                    else self._t(TranslationKey.BIOS_CATALOGUE_EMPTY)
                ),
                3,
                wait=True,
            )
            return
        while True:
            choice = self._menu(
                self._t(TranslationKey.BIOS_RESULTS, count=len(entries)),
                [
                    f"{platform.alias} | {self._bios_check_label(check)}"
                    for platform, check in entries
                ],
                self._t(TranslationKey.BIOS_RESULTS_FOOTER),
            )
            if choice is None:
                return
            platform, old_check = entries[choice]
            check = audit_bios(
                (old_check.requirement,),
                platform,
                root,
                self.preferences.bios_directory,
            )[0]
            entries[choice] = (platform, check)
            requirement = check.requirement
            detail = [
                requirement.description or requirement.name,
                self._t(TranslationKey.PLATFORM_FIELD, value=platform.name),
                self._t(
                    TranslationKey.STATUS_FIELD, value=self._bios_state_label(check.state).upper()
                ),
                self._t(
                    TranslationKey.REQUIRED if requirement.required else TranslationKey.OPTIONAL
                ),
                self._t(
                    TranslationKey.REGION_FIELD,
                    value=requirement.region or self._t(TranslationKey.ALL_REGIONS),
                ),
                self._t(TranslationKey.DESTINATION_FIELD, value=check.paths[0]),
            ]
            if requirement.note:
                detail.append(requirement.note)
            if check.state is BiosState.VALID:
                self._draw_message(
                    self._t(TranslationKey.BIOS_DETAILS), "\n".join(detail), 4, wait=True
                )
                continue
            if catalogue.source_url(requirement) is None:
                detail.append(self._t(TranslationKey.BIOS_ENTRY_NOT_DOWNLOADABLE))
                self._draw_message(
                    self._t(TranslationKey.BIOS_DETAILS), "\n".join(detail), 3, wait=True
                )
                continue
            self._draw_message(
                self._t(TranslationKey.BIOS_DETAILS), "\n".join(detail), 3, wait=True
            )
            confirmation = self._confirm_retrobios_download((check,))
            if confirmation:
                self._install_bios_checks(catalogue, (check,), platform, root)

    def _bios_followup(
        self,
        platform: Platform,
        roms_directory: Path,
        region: str | None,
        bios_directory: str = "bios",
    ) -> int:
        """Offer BIOS only after bundled and existing files have been checked."""

        try:
            catalogue = self._load_retrobios_catalogue()
        except BiosDownloadCancelled:
            return 0
        except BiosError as error:
            self._draw_message(
                self._t(TranslationKey.BIOS_CHECK_UNAVAILABLE),
                self._t(TranslationKey.BIOS_CHECK_UNAVAILABLE_MESSAGE, error=error),
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
            bios_directory,
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
            self._t(TranslationKey.REQUIRED_BIOS_MISSING_MESSAGE),
            "",
            *(
                f"{check.requirement.name} [{self._bios_state_label(check.state)}]"
                for check in missing[:8]
            ),
        ]
        if len(missing) > 8:
            lines.append(self._t(TranslationKey.AND_MORE, count=len(missing) - 8))
        self._draw_message(
            self._t(TranslationKey.REQUIRED_BIOS_NOT_FOUND),
            "\n".join(lines),
            3,
            wait=True,
        )
        choice = self._menu(
            self._t(TranslationKey.DOWNLOAD_REQUIRED_BIOS),
            (
                self._t(TranslationKey.DOWNLOAD_FROM_RETROBIOS),
                self._t(TranslationKey.KEEP_WITHOUT_BIOS),
            ),
            self._t(TranslationKey.FIRMWARE_WARNING),
        )
        if choice != 0 or not self._confirm_retrobios_download(missing):
            LOGGER.warning(
                "User kept game without %d required BIOS file(s) platform=%s",
                len(missing),
                platform.alias,
            )
            return 0
        return self._install_bios_checks(
            catalogue,
            missing,
            platform,
            roms_directory,
            bios_directory,
        )

    def _confirm_retrobios_download(self, checks: Sequence[BiosCheck]) -> bool:
        downloadable = tuple(check for check in checks if check.requirement.source_path is not None)
        if not downloadable:
            self._draw_message(
                self._t(TranslationKey.BIOS_NOT_DOWNLOADABLE),
                self._t(TranslationKey.BIOS_NOT_DOWNLOADABLE_MESSAGE),
                3,
                wait=True,
            )
            return False
        choice = self._menu(
            self._t(TranslationKey.CONFIRM_RETROBIOS_DOWNLOAD),
            (
                self._t(TranslationKey.CANCEL),
                self._t(TranslationKey.DOWNLOAD_VERIFIED_BIOS, count=len(downloadable)),
            ),
            self._t(TranslationKey.BIOS_LEGAL_FOOTER),
        )
        return choice == 1

    def _install_bios_checks(
        self,
        catalogue: RetroBiosCatalog,
        checks: Sequence[BiosCheck],
        platform: Platform,
        root: Path,
        bios_directory: str | None = None,
    ) -> int:
        effective_bios_directory = bios_directory or self.preferences.bios_directory
        selected = tuple(
            check for check in checks if catalogue.source_url(check.requirement) is not None
        )
        if not selected:
            return 0
        cancelled = Event()
        state_lock = Lock()
        progress_state: list[str | int | None] = [
            self._t(TranslationKey.CONNECTING_RETROBIOS),
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
                    effective_bios_directory,
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
                self._t(TranslationKey.BIOS_DOWNLOAD_CANCELLED),
                self._t(TranslationKey.NO_INCOMPLETE_BIOS_INSTALLED),
                3,
                wait=True,
            )
            return 0
        except BiosError as error:
            self._operation_error(error)
            return 0
        self._draw_message(
            self._t(TranslationKey.BIOS_INSTALLED),
            self._t(
                TranslationKey.BIOS_INSTALLED_MESSAGE,
                count=installed,
                destination=root / effective_bios_directory,
            ),
            4,
            wait=True,
        )
        return installed

    def _bios_check_label(self, check: BiosCheck) -> str:
        kind = self._t(
            TranslationKey.REQUIRED_SHORT
            if check.requirement.required
            else TranslationKey.OPTIONAL_SHORT
        )
        region = f" {check.requirement.region}" if check.requirement.region else ""
        state = self._bios_state_label(check.state).upper()
        return f"[{state}] [{kind}]{region} {check.requirement.name}"

    def _minerva_bittorrent_settings_screen(self) -> None:
        fields = (
            (TranslationKey.MINERVA_UDP_PROTOCOL_ID, "udp_protocol_id"),
            (TranslationKey.MINERVA_BLOCK_SIZE, "block_size"),
            (TranslationKey.MINERVA_MAX_TORRENT_BYTES, "max_torrent_bytes"),
            (TranslationKey.MINERVA_MAX_TRACKER_BYTES, "max_tracker_bytes"),
            (TranslationKey.MINERVA_MAX_PEER_ATTEMPTS, "max_peer_attempts"),
            (TranslationKey.MINERVA_PEER_RACE_WORKERS, "peer_race_workers"),
            (TranslationKey.MINERVA_MAX_PEER_TIMEOUT, "max_peer_timeout_seconds"),
            (TranslationKey.MINERVA_MAX_TRACKER_QUERIES, "max_tracker_queries"),
            (TranslationKey.MINERVA_MAX_DISCOVERED_PEERS, "max_discovered_peers"),
        )
        while True:
            settings = self.preferences.minerva_bittorrent
            values = [
                f"{self._t(label_key)}  [{self._format_bittorrent_setting(field_name, settings)}]"
                for label_key, field_name in fields
            ]
            choice = self._menu(
                self._t(TranslationKey.MINERVA_SETTINGS_TITLE),
                (*values, self._t(TranslationKey.RESET_ALL_DEFAULTS), self._t(TranslationKey.BACK)),
                self._t(TranslationKey.MINERVA_SETTINGS_FOOTER),
            )
            if choice is None or choice == len(fields) + 1:
                return
            if choice == len(fields):
                confirmation = self._menu(
                    self._t(TranslationKey.RESET_MINERVA_SETTINGS),
                    (
                        self._t(TranslationKey.KEEP_CURRENT_VALUES),
                        self._t(TranslationKey.RESTORE_DEFAULTS),
                    ),
                    self._t(TranslationKey.RESET_MINERVA_FOOTER),
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
                self._t(TranslationKey.CURRENT_VALUE, value=current),
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
                self._error(self._t(TranslationKey.INVALID_SETTING, setting=label, error=error))
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
            self._t(TranslationKey.MINERVA_SETTINGS_SAVED),
            self._t(TranslationKey.MINERVA_SETTINGS_SAVED_MESSAGE),
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
            self._error(self._t(TranslationKey.AUTOMATIC_UPDATE_PACKAGE))
            return
        current = installed_version()
        self._draw_message(
            self._t(TranslationKey.CHECKING_FOR_UPDATE),
            self._t(TranslationKey.CHECKING_FOR_UPDATE_MESSAGE, version=current),
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
                self._t(TranslationKey.ALREADY_UP_TO_DATE),
                self._t(
                    TranslationKey.LATEST_RELEASE_MESSAGE,
                    version=current,
                    target=self.config.target.display_name,
                ),
                4,
                wait=True,
            )
            return
        choice = self._menu(
            self._t(TranslationKey.APPLICATION_UPDATE_AVAILABLE),
            (
                self._t(TranslationKey.DOWNLOAD_INSTALL_VERSION, version=release.version),
                self._t(TranslationKey.LATER),
            ),
            self._t(TranslationKey.INSTALLED_PUBLISHED, installed=current, published=release.tag),
        )
        if choice != 0:
            return
        try:
            self._stage_application_update(release, install_directory)
        except UpdateCancelled:
            LOGGER.info("Application update cancelled")
            self._draw_message(
                self._t(TranslationKey.UPDATE_CANCELLED),
                self._t(TranslationKey.INSTALLED_APPLICATION_UNCHANGED),
                3,
                wait=True,
            )
            return
        except UpdateError as error:
            LOGGER.error("Application update failed: %s", error)
            self._operation_error(error)
            return
        self._draw_message(
            self._t(TranslationKey.UPDATE_READY),
            self._t(TranslationKey.UPDATE_READY_MESSAGE, version=release.version),
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
            self._t(TranslationKey.CONNECTING_GITHUB),
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
                        self._t(TranslationKey.CANCELLING_UPDATE),
                        self._t(TranslationKey.CANCELLING_UPDATE_MESSAGE),
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
            self._t(TranslationKey.EXIT_POCKET_HARBOR),
            (
                self._t(TranslationKey.RETURN_TO_POCKET_HARBOR),
                self._t(TranslationKey.CONFIRM_EXIT),
            ),
            self._t(TranslationKey.EXIT_FOOTER),
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
                card = self._t(TranslationKey.CARD_NUMBER, index=index)
            labels.append(f"{root}  ({card})")
        choice = self._menu(
            title,
            labels,
            self._t(TranslationKey.CHOOSE_LIBRARY_LOCATION),
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
                TranslationKey.DOWNLOADED_KIB,
                label=label,
                kib=current // 1024,
            )
        self._draw_message(self._t(TranslationKey.DOWNLOADING), message, 1)
        self._footer(self._t(TranslationKey.CANCEL_DOWNLOAD_FOOTER))
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
                self._t(TranslationKey.CONNECTING_DOWNLOAD_SERVICE),
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
                            self._t(TranslationKey.CANCELLING_DOWNLOAD),
                            self._t(TranslationKey.CANCELLING_DOWNLOAD_MESSAGE),
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
            self._t(TranslationKey.MINERVA_TORRENT_CHANGED),
            self._t(
                TranslationKey.MINERVA_TORRENT_CHANGED_MESSAGE,
                filename=error.expected_filename,
                index=error.catalogue_index,
                count=error.total_files,
            ),
            3,
            wait=True,
        )
        labels = [
            self._t(
                TranslationKey.MINERVA_CANDIDATE,
                index=candidate.index,
                filename=candidate.filename,
                size=self._format_file_size(candidate.length),
                score=round(candidate.match_score * 100),
                path="/".join(candidate.path),
            )
            for candidate in error.candidates
        ]
        selected_index = self._menu(
            self._t(TranslationKey.CHOOSE_MINERVA_TORRENT_FILE),
            labels,
            self._t(TranslationKey.MINERVA_CANDIDATES_FOOTER),
        )
        if selected_index is None:
            return None
        selected = error.candidates[selected_index]
        self._draw_message(
            self._t(TranslationKey.REVIEW_MINERVA_FILE),
            self._t(
                TranslationKey.REVIEW_MINERVA_FILE_MESSAGE,
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
            self._t(TranslationKey.CONFIRM_MINERVA_FILE),
            (
                self._t(TranslationKey.CANCEL_DOWNLOAD),
                self._t(TranslationKey.DOWNLOAD_FILENAME, filename=selected.filename),
            ),
            self._t(TranslationKey.CONFIRM_MINERVA_FILE_FOOTER),
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
        not_detected = self._t(TranslationKey.NOT_DETECTED)
        roms = ", ".join(str(path) for path in self.roms_directories) or not_detected
        controller = str(self.gamepad.path) if self.gamepad is not None else not_detected
        selected_store = (
            self._t(TranslationKey.MANUAL_EVERY_TIME)
            if self.preferences.ask_store_each_time
            else self.selected_store.display_name
            if self.selected_store is not None
            else self._t(TranslationKey.NOT_CONFIGURED)
        )
        terminal_height, terminal_width = self.screen.getmaxyx()
        compatible = ", ".join(self.hardware.compatible[:2]) or not_detected
        dt_inputs = ", ".join(item.node for item in self.hardware.input_nodes) or not_detected
        key_count = len(self.hardware.keys)
        stores = ", ".join(
            f"{store.display_name} ({store.base_url})" for store in self.store_catalog.stores
        )
        message = self._t(
            TranslationKey.STATUS_MESSAGE,
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
        self._draw_message(self._t(TranslationKey.STATUS_TITLE), message, 1, wait=True)

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
                        self._t(TranslationKey.SPACE)
                        if key.action == "space"
                        else self._t(TranslationKey.KEY_BACK)
                        if key.action == "back"
                        else self._t(TranslationKey.DONE)
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
                self._t(TranslationKey.INTEGER_KEYBOARD)
                if input_kind is SettingInputKind.INTEGER
                else self._t(TranslationKey.FLOAT_KEYBOARD)
                if input_kind is SettingInputKind.FLOAT
                else self._t(TranslationKey(f"keyboard_{page}"))
            )
            footer = self._t(TranslationKey.KEYBOARD_FOOTER, page=page_label)
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

    def _menu(
        self,
        title: str,
        options: Sequence[str],
        footer: str,
        *,
        gamepad_keys: Mapping[InputAction, int] = GAMEPAD_KEYS,
        shortcuts: Mapping[int, int] | None = None,
        refresh_options: Callable[[], Sequence[str]] | None = None,
        refresh_seconds: float | None = None,
    ) -> int | None:
        options_provider = refresh_options or (lambda: options)
        dynamic = refresh_options is not None
        selected = 0
        offset = 0
        marquee_offset = 0
        while True:
            current_options = tuple(options_provider())
            if not current_options:
                return None
            selected = min(selected, len(current_options) - 1)
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
                range(offset, min(len(current_options), offset + visible))
            ):
                label = current_options[option_index].replace("\n", " ")
                marker = "> " if option_index == selected else "  "
                attribute = (
                    curses.color_pair(2) | curses.A_BOLD
                    if option_index == selected
                    else curses.A_NORMAL
                )
                label_width = max(1, width - 6)
                frame = _visible_menu_label(
                    label,
                    label_width,
                    marquee_offset if option_index == selected else 0,
                )
                self._safe_add(3 + screen_row, 2, marker + frame, attribute)
            if len(current_options) > visible:
                position = "%d/%d" % (selected + 1, len(current_options))
                self._safe_add(
                    height - 3, max(2, width - len(position) - 2), position, curses.color_pair(3)
                )
            self._footer(footer)
            self.screen.refresh()
            selected_label = current_options[selected].replace("\n", " ")
            live_refresh = dynamic or len(selected_label) > max(1, width - 6)
            pressed = (
                self._get_input_until(
                    gamepad_keys,
                    refresh_seconds or MENU_REDRAW_SECONDS,
                )
                if live_refresh or refresh_seconds is not None
                else self._get_input(gamepad_keys)
            )
            if pressed is None:
                marquee_offset += 1
                continue
            if shortcuts is not None and pressed in shortcuts:
                return shortcuts[pressed]
            if pressed in (27, ord("b"), ord("B"), curses.KEY_BACKSPACE, 127):
                return None
            if pressed in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(current_options)
                marquee_offset = 0
            elif pressed in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(current_options)
                marquee_offset = 0
            elif pressed == curses.KEY_PPAGE:
                selected = max(0, selected - visible)
                marquee_offset = 0
            elif pressed == curses.KEY_NPAGE:
                selected = min(len(current_options) - 1, selected + visible)
                marquee_offset = 0
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
            self._footer(self._t(TranslationKey.CONTINUE_FOOTER))
        self.screen.refresh()
        if wait:
            self._get_input()

    def _get_input(self, gamepad_keys: Mapping[InputAction, int] = GAMEPAD_KEYS) -> int:
        """Wait for a keyboard key or a directly connected controller action."""

        while True:
            pressed = self._poll_input(gamepad_keys)
            if pressed is not None:
                return pressed

    def _get_input_until(
        self,
        gamepad_keys: Mapping[InputAction, int],
        timeout_seconds: float,
    ) -> int | None:
        """Wait for input until a live menu needs its next render frame."""

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            pressed = self._poll_input(gamepad_keys)
            if pressed is not None:
                return pressed
        return None

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
        self._error(self._t(TranslationKey.OPERATION_FAILED, error=error))

    def _error(self, message: str) -> None:
        self._draw_message(self._t(TranslationKey.ERROR), message, 5, wait=True)

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
            raise TerminalTooSmall(self._t(TranslationKey.TERMINAL_TOO_SMALL))


def run_tui(config: Config) -> None:
    """Initialize curses and run the interactive application."""

    curses.wrapper(lambda screen: DownloaderTui(screen, config).run())
