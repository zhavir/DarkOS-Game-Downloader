"""Controller-friendly full-screen terminal interface."""

import contextlib
import curses
import locale
import textwrap
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from typing import Any

from dw_cli.compatibility import (
    CompatibilityInfo,
    R36SCompatibilityClient,
    filter_supported_results,
)
from dw_cli.config import Config
from dw_cli.downloader import DownloadCancelled, DownloadError, download_files
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
from dw_cli.store import GameStore, StoreError
from dw_cli.store_catalog import StoreCatalog

type Window = Any

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


class TerminalTooSmall(RuntimeError):
    """The active terminal cannot display the interface."""


class DownloaderTui:
    """A compact curses UI designed for a 640x480 dArkOS R36S screen."""

    def __init__(self, screen: Window, config: Config) -> None:
        self.screen = screen
        self.config = config
        self.store_catalog = StoreCatalog.from_config(config)
        self.preferences_path = preference_path(config.download_directory)
        preferences = load_preferences(self.preferences_path)
        self.selected_store = (
            self.store_catalog.find(preferences.store_id) if preferences.store_id else None
        )
        self.exit_after_refresh = False
        self.compatibility_client = R36SCompatibilityClient(
            config.download_directory / ".r36s-game-list-cache.json",
            timeout_seconds=config.timeout_seconds,
        )
        self.roms_directories = detect_roms_directories(config.roms_directories or None)
        self.platforms = discover_platforms(self.roms_directories)
        self.hardware = detect_hardware_profile()
        self.gamepad = LinuxJoystick.open_first()
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
                if choice is None or choice == 5:
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
                    self._settings_screen()
                elif choice == 4:
                    self._status_screen()
                if self.exit_after_refresh:
                    return
        finally:
            if self.gamepad is not None:
                self.gamepad.close()

    def _search_flow(self) -> None:
        store = self.selected_store
        if store is None:
            return
        platforms = tuple(
            platform for platform in self.platforms if store.supports_platform(platform)
        )
        labels = [f"{item.name}  [{item.alias}]" for item in platforms]
        choice = self._menu("CHOOSE A PLATFORM", labels, "B/Esc: back")
        if choice is None:
            return
        platform = platforms[choice]
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
            results = store.search(store.platform_code(platform), query, self._catalog_progress)
        except StoreError as error:
            self._error(str(error))
            return
        results = filter_supported_results(results)
        if not results:
            message = f"Nothing matched {query}." if query else "The catalogue is empty."
            self._draw_message("NO RESULTS", message, 3, wait=True)
            return
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
                self._download_detail(result.link, effective_platform, store)
                if self.exit_after_refresh:
                    return
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
            self._draw_message("DOWNLOAD CANCELLED", "No game was installed.", 3)
            return
        except (StoreError, DownloadError, OrganizeError) as error:
            self._error(str(error))
            return
        final_path = completed[0].path
        refresh_requested = request_emulationstation_refresh()
        bios_message = (
            "\nInstalled %d bundled BIOS file(s)." % len(installed_bios) if installed_bios else ""
        )
        refresh_message = (
            "\nThe downloader will now close and refresh the game list."
            if refresh_requested
            else ""
        )
        self._draw_message(
            "DOWNLOAD COMPLETE",
            f"{final_path.name}\nMoved to {final_path.parent}{bios_message}{refresh_message}",
            4,
            wait=True,
        )
        self.exit_after_refresh = refresh_requested

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
            if self.exit_after_refresh:
                return

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
                if self.exit_after_refresh:
                    return
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
            self._error(str(error))
            return False
        refresh_requested = request_emulationstation_refresh()
        refresh_message = (
            "\nThe downloader will now close and refresh the game list."
            if refresh_requested
            else ""
        )
        self._draw_message("GAME DELETED", game.title + refresh_message, 4, wait=True)
        self.exit_after_refresh = refresh_requested
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
            self._draw_message("UPDATE CANCELLED", "The installed game was not changed.", 3)
            return False
        except (StoreError, DownloadError, LibraryError, OrganizeError) as error:
            self._error(str(error))
            return False
        refresh_requested = request_emulationstation_refresh()
        refresh_message = (
            "\nThe downloader will now close and refresh the game list."
            if refresh_requested
            else ""
        )
        self._draw_message(
            "GAME UPDATED",
            "{}\nInstalled on {}{}".format(
                completed.path.name,
                game.roms_directory,
                "\nInstalled %d bundled BIOS file(s)." % len(installed_bios)
                if installed_bios
                else "",
            )
            + refresh_message,
            4,
            wait=True,
        )
        self.exit_after_refresh = refresh_requested
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
        try:
            save_preferences(self.preferences_path, Preferences(store.store_id))
        except PreferencesError as error:
            self._error(str(error))
            return False
        self.selected_store = store
        if not first_run:
            self._draw_message(
                "SETTINGS SAVED",
                f"Searches, downloads, and updates will use {store.display_name}.",
                4,
                wait=True,
            )
        return True

    def _settings_screen(self) -> None:
        current = self.selected_store.display_name if self.selected_store is not None else "not set"
        choice = self._menu(
            "SETTINGS",
            (f"Change download store  [current: {current}]", "Back"),
            "The selected store is remembered for future launches",
        )
        if choice == 0:
            self._configure_store()

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

        cancelled = Event()
        state_lock = Lock()
        progress_state: list[str | int | None] = ["Connecting to the download service...", 0, None]

        def report(label: str, current: int, total: int | None) -> None:
            with state_lock:
                progress_state[:] = [label, current, total]

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="tui-download") as executor:
            future = executor.submit(
                download_files,
                downloads,
                self.config.download_directory,
                store.download_referrer,
                self.config.timeout_seconds,
                report,
                cancelled.is_set,
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
            return future.result()

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
        rows: tuple[tuple[str, ...], ...] = (
            tuple("1234567890"),
            tuple("QWERTYUIOP"),
            tuple("ASDFGHJKL"),
            tuple("ZXCVBNM"),
            tuple("-_.:/?=&"),
            ("SPACE", "BACK", "CLEAR", "DONE", "CANCEL"),
        )
        value = ""
        row = 0
        column = 0
        while True:
            height, width = self.screen.getmaxyx()
            self._require_size(height, width)
            self.screen.erase()
            self._header(title)
            display = value[-max(1, width - 8) :]
            self._safe_add(3, 3, "> " + display, curses.color_pair(3) | curses.A_BOLD)
            start_y = 6
            for row_index, keys in enumerate(rows):
                key_width = max(3, (width - 6) // max(1, len(keys)))
                total_width = key_width * len(keys)
                start_x = max(2, (width - total_width) // 2)
                for column_index, key in enumerate(keys):
                    selected = row_index == row and column_index == column
                    label = f" {key} "
                    attribute = (
                        curses.color_pair(2) | curses.A_BOLD if selected else curses.A_NORMAL
                    )
                    self._safe_add(
                        start_y + row_index * 2,
                        start_x + column_index * key_width,
                        label,
                        attribute,
                    )
            footer = "D-pad/stick: move   A: key   X: search   B: cancel"
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
                row = (row - 1) % len(rows)
                column = min(column, len(rows[row]) - 1)
            elif pressed in (curses.KEY_DOWN, ord("j")):
                row = (row + 1) % len(rows)
                column = min(column, len(rows[row]) - 1)
            elif pressed in (curses.KEY_LEFT, ord("h")):
                column = (column - 1) % len(rows[row])
            elif pressed in (curses.KEY_RIGHT, ord("l")):
                column = (column + 1) % len(rows[row])
            elif pressed in (curses.KEY_BACKSPACE, 8, 127):
                value = value[:-1]
            elif pressed in (10, 13, curses.KEY_ENTER):
                key = rows[row][column]
                if key == "SPACE":
                    value += " "
                elif key == "BACK":
                    value = value[:-1]
                elif key == "CLEAR":
                    value = ""
                elif key == "DONE":
                    return value.strip()
                elif key == "CANCEL":
                    return None
                else:
                    value += key.lower() if allow_lowercase else key
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
