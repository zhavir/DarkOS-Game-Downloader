"""Application entry point and non-interactive automation commands."""

import argparse
import curses
import locale
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ph.cache_policy import catalogue_ttl_seconds
from ph.compatibility import filter_supported_results
from ph.config import Config
from ph.downloader import DownloadError, download_files
from ph.frontend import request_game_frontend_refresh
from ph.logging_config import configure_logging
from ph.models import SearchResult
from ph.organizer import OrganizeError, detect_roms_directory, install_downloads
from ph.platforms import platform_catalogue, resolve_platform
from ph.preferences import load_preferences, preference_path
from ph.store import GameStore, StoreError
from ph.store_catalog import StoreCatalog
from ph.targets import DARKOS, LinuxTarget, TargetError
from ph.tui import TerminalTooSmall, run_tui

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    try:
        app_version = version("pocket-harbor")
    except PackageNotFoundError:
        app_version = "development"
    parser = argparse.ArgumentParser(
        prog="ph",
        description="Linux handheld library manager. Run without a command to open the TUI.",
    )
    parser.add_argument("--version", action="version", version=f"ph {app_version}")
    parser.add_argument("--base-url", help="override PH_BASE_URL for this run")
    parser.add_argument(
        "--store",
        default="vimm",
        help="download store identifier for CLI commands (default: vimm)",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("tui", help="open the full-screen controller interface")

    search_parser = subparsers.add_parser("search", help="search without opening the TUI")
    search_parser.add_argument("console", help="platform slug, service code, or short alias")
    search_parser.add_argument(
        "query",
        nargs="*",
        help="optional title prefix; omit it to list the platform catalogue",
    )

    download_parser = subparsers.add_parser("download", help="download detail URLs")
    download_parser.add_argument("urls", nargs="+", help="one or more detail-page URLs")
    download_parser.add_argument(
        "--platform",
        help="move completed files to this platform's ROM folder",
    )
    download_parser.add_argument(
        "--directory",
        type=Path,
        help="temporary download directory (defaults to PH_DOWNLOAD_DIR)",
    )
    download_parser.add_argument(
        "--roms-directory",
        type=Path,
        help="ROM root (uses the selected OS target defaults when omitted)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime_config: Config | None = None,
    runtime_environment: Mapping[str, str] | None = None,
) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        config = runtime_config or Config.from_environment(runtime_environment)
    except TargetError as error:
        print(f"ph: {error}", file=sys.stderr)
        return 2
    if arguments.base_url:
        config = replace(config, base_url=arguments.base_url.rstrip("/"))
    preferences = load_preferences(preference_path(config.download_directory))
    log_to_file = (
        config.log_file is not None if preferences.log_to_file is None else preferences.log_to_file
    )
    log_file = (
        config.log_file or config.download_directory / "pocket-harbor.log" if log_to_file else None
    )
    configure_logging(log_file, preferences.log_level or config.log_level)
    LOGGER.info("Starting Pocket Harbor command=%s", arguments.command or "tui")
    LOGGER.debug(
        "Runtime configuration target=%s stores=%s download_directory=%s "
        "roms_directories=%s timeout=%s",
        config.target.target_id,
        config.enabled_stores,
        config.download_directory,
        config.roms_directories,
        config.timeout_seconds,
    )
    store_catalog = StoreCatalog.from_config(
        config,
        catalogue_ttl_seconds(preferences.catalogue_ttl_days),
    )

    if arguments.command in (None, "tui"):
        if not store_catalog.stores:
            LOGGER.error("No download stores are enabled")
            parser.error("no download stores are enabled; check PH_STORES")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            LOGGER.error("TUI requested without an interactive terminal")
            parser.error("the TUI needs an interactive terminal; use a subcommand for automation")
        try:
            run_tui(config)
        except (TerminalTooSmall, StoreError, curses.error, locale.Error, ValueError) as error:
            LOGGER.error("TUI stopped: %s", error)
            print(f"ph: {error}", file=sys.stderr)
            return 2
        except Exception:
            LOGGER.exception("TUI stopped because of an unexpected error")
            print(
                "ph: An unexpected error stopped the TUI. Check the diagnostic log.",
                file=sys.stderr,
            )
            return 2
        LOGGER.info("TUI closed normally")
        return 0
    store = store_catalog.find(arguments.store)
    if store is None:
        available = ", ".join(item.store_id for item in store_catalog.stores) or "none"
        LOGGER.error("Unknown store requested: %s", arguments.store)
        parser.error(f"unknown store {arguments.store!r}; available stores: {available}")
    if arguments.command == "search":
        return _run_search(
            store,
            arguments.console,
            " ".join(arguments.query),
            config.target,
        )
    if arguments.command == "download":
        directory = arguments.directory or config.download_directory
        return _run_download(
            store,
            config,
            arguments.urls,
            directory,
            arguments.platform,
            arguments.roms_directory,
        )
    parser.print_help()
    return 0


def _run_search(
    store: GameStore,
    console: str,
    query: str,
    target: LinuxTarget = DARKOS,
) -> int:
    platform = resolve_platform(console, platform_catalogue(target))
    if platform is None:
        print(f"Unknown platform {console!r}.", file=sys.stderr)
        return 2
    if not store.supports_platform(platform):
        print(f"{store.display_name} does not provide {platform.name}.", file=sys.stderr)
        return 2
    try:
        LOGGER.info(
            "Searching store=%s platform=%s query=%r", store.store_id, platform.alias, query
        )
        results = filter_supported_results(store.search(store.platform_code(platform), query))
    except (StoreError, ValueError) as error:
        LOGGER.warning(
            "Search failed store=%s platform=%s: %s", store.store_id, platform.alias, error
        )
        print(f"Search failed: {error}", file=sys.stderr)
        return 1
    if not results:
        LOGGER.info(
            "Search returned no results store=%s platform=%s", store.store_id, platform.alias
        )
        if query.strip():
            print(f"No results found for {query!r} on {platform.name}.")
        else:
            print(f"No catalogue entries found for {platform.name}.")
        return 0
    _print_results(results)
    return 0


def _run_download(
    store: GameStore,
    config: Config,
    detail_urls: Sequence[str],
    directory: Path,
    platform_name: str | None,
    roms_directory: Path | None,
) -> int:
    installed_bios: list[Path] = []
    try:
        LOGGER.info(
            "Starting download count=%d platform=%s",
            len(detail_urls),
            platform_name or "staging-only",
        )
        media_urls = [store.download_request(url) for url in detail_urls]
        downloads = download_files(
            media_urls,
            directory,
            store.download_referrer,
            config.timeout_seconds,
            _print_progress,
        )
        if platform_name:
            platform = resolve_platform(platform_name, platform_catalogue(config.target))
            if platform is None:
                raise OrganizeError(f"Unknown platform {platform_name!r}.")
            configured_roots = (roms_directory,) if roms_directory else config.roms_directories
            root = detect_roms_directory(configured_roots or None, config.target.rom_roots)
            if root is None:
                raise OrganizeError("No ROM root found; pass --roms-directory.")
            downloads = install_downloads(downloads, platform, root, installed_bios.append)
    except (StoreError, DownloadError, OrganizeError, ValueError) as error:
        LOGGER.error("Download failed: %s", error)
        print(f"Download failed: {error}", file=sys.stderr)
        return 1
    for result in downloads:
        print(f"Completed: {result.path}")
    for bios_path in installed_bios:
        print(f"BIOS installed: {bios_path}")
    if not platform_name:
        print("Tip: use --platform to move completed files into the matching ROM folder.")
    else:
        request_game_frontend_refresh(target=config.target)
    LOGGER.info("Download completed files=%d bios=%d", len(downloads), len(installed_bios))
    return 0


def _print_progress(label: str, current: int, total: int | None) -> None:
    if total:
        print("\r%s: %d%%" % (label, min(100, int(current * 100 / total))), end="", flush=True)
        if current >= total:
            print()
    else:
        print("\r%s: %d KiB" % (label, current // 1024), end="", flush=True)


def _print_results(results: Sequence[SearchResult]) -> None:
    rows: list[Sequence[str]] = []
    for result in results:
        rows.append(
            (
                result.system or "-",
                result.title,
                result.region or "-",
                result.version or "-",
                result.link,
            )
        )
    _print_table(("SYSTEM", "TITLE", "REGION", "VERSION", "LINK"), rows)


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    all_rows = [tuple(headers)] + [tuple(str(value) for value in row) for row in rows]
    widths = [max(len(row[index]) for row in all_rows) for index in range(len(headers))]
    template = "  ".join("{:<%d}" % width for width in widths)
    print(template.format(*all_rows[0]))
    print(template.format(*("-" * width for width in widths)))
    for row in all_rows[1:]:
        print(template.format(*row))


if __name__ == "__main__":
    raise SystemExit(main())
