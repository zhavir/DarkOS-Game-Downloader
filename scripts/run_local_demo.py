"""Run the real TUI against the offline demo catalogue and local fake SD cards."""

import argparse
import os
import threading
from collections.abc import Sequence
from pathlib import Path

from dw_cli.app import main as run_downloader
from scripts.local_vault_server import build_server


def prepare_demo_environment(workspace: Path, base_url: str) -> dict[str, str]:
    """Create a persistent local dual-card layout and return its runtime environment."""

    workspace = workspace.expanduser().resolve()
    downloads = workspace / "downloads"
    card_one = workspace / "sd1"
    card_two = workspace / "sd2"
    for directory in (downloads, card_one / "gba", card_two / "gba"):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "DW_BASE_URL": base_url,
        "DW_DOWNLOAD_DIR": str(downloads),
        "DW_ROMS_DIRS": os.pathsep.join((str(card_one), str(card_two))),
        "DW_STORES": "vimm",
        "DW_TIMEOUT": "5",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".local-test"),
        help="persistent demo downloads and SD cards (default: .local-test)",
    )
    parser.add_argument("--verbose-server", action="store_true")
    arguments = parser.parse_args(argv)

    server = build_server(port=0, verbose=arguments.verbose_server)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    environment = prepare_demo_environment(arguments.workspace, f"http://{host}:{port}")
    os.environ.update(environment)
    try:
        return run_downloader([])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
