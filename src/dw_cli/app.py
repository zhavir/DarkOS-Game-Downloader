"""Application entry point and backwards-compatible automation commands."""

import argparse
import curses
import locale
import sys
from collections.abc import Sequence
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from dw_cli.compatibility import filter_supported_results
from dw_cli.config import Config
from dw_cli.downloader import DownloadError, download_files
from dw_cli.frontend import request_emulationstation_refresh
from dw_cli.models import SearchResult
from dw_cli.organizer import OrganizeError, detect_roms_directory, move_to_arkos
from dw_cli.platforms import resolve_platform
from dw_cli.store import GameStore, StoreError
from dw_cli.store_catalog import StoreCatalog
from dw_cli.tui import TerminalTooSmall, run_tui


def build_parser() -> argparse.ArgumentParser:
    try:
        app_version = version("darkos-downloader")
    except PackageNotFoundError:
        app_version = "development"
    parser = argparse.ArgumentParser(
        prog="dw",
        description="dArkOS-friendly library downloader. Run without a command to open the TUI.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {app_version}")
    parser.add_argument("--base-url", help="override DW_BASE_URL for this run")
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
        help="move completed files to this platform's dArkOS ROM folder",
    )
    download_parser.add_argument(
        "--directory",
        type=Path,
        help="temporary download directory (defaults to DW_DOWNLOAD_DIR)",
    )
    download_parser.add_argument(
        "--roms-directory",
        type=Path,
        help="dArkOS ROM root (auto-detects /roms2 or /roms)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    config = Config.from_environment()
    if arguments.base_url:
        config = replace(config, base_url=arguments.base_url.rstrip("/"))
    store_catalog = StoreCatalog.from_config(config)
    store = store_catalog.find(arguments.store)
    if store is None:
        available = ", ".join(item.store_id for item in store_catalog.stores)
        parser.error(f"unknown store {arguments.store!r}; available stores: {available}")

    if arguments.command in (None, "tui"):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            parser.error("the TUI needs an interactive terminal; use a subcommand for automation")
        try:
            run_tui(config)
        except (TerminalTooSmall, StoreError, curses.error, locale.Error, ValueError) as error:
            print(f"dw: {error}", file=sys.stderr)
            return 2
        return 0
    if arguments.command == "search":
        return _run_search(store, arguments.console, " ".join(arguments.query))
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


def _run_search(store: GameStore, console: str, query: str) -> int:
    platform = resolve_platform(console)
    if platform is None:
        print(f"Unknown platform {console!r}.", file=sys.stderr)
        return 2
    try:
        results = filter_supported_results(store.search(store.platform_code(platform), query))
    except (StoreError, ValueError) as error:
        print(f"Search failed: {error}", file=sys.stderr)
        return 1
    if not results:
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
        media_urls = [store.retrieve_download_url(url) for url in detail_urls]
        downloads = download_files(
            media_urls,
            directory,
            store.download_referrer,
            config.timeout_seconds,
            _print_progress,
        )
        if platform_name:
            platform = resolve_platform(platform_name)
            if platform is None:
                raise OrganizeError(f"Unknown platform {platform_name!r}.")
            configured_roots = (roms_directory,) if roms_directory else config.roms_directories
            root = detect_roms_directory(configured_roots or None)
            if root is None:
                raise OrganizeError("No dArkOS ROM root found; pass --roms-directory.")
            downloads = move_to_arkos(downloads, platform, root, installed_bios.append)
    except (StoreError, DownloadError, OrganizeError, ValueError) as error:
        print(f"Download failed: {error}", file=sys.stderr)
        return 1
    for result in downloads:
        print(f"Completed: {result.path}")
    for bios_path in installed_bios:
        print(f"BIOS installed: {bios_path}")
    if not platform_name:
        print("Tip: use --platform to move completed files into the matching dArkOS ROM folder.")
    else:
        request_emulationstation_refresh()
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
