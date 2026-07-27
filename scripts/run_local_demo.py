"""Run the real TUI against the offline demo catalogue and local fake SD cards."""

import argparse
import os
import threading
from collections.abc import Sequence
from pathlib import Path

from ph.app import main as run_pocket_harbor
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
        "PH_VIMM_BASE_URL": base_url,
        "PH_DOWNLOAD_DIR": str(downloads),
        "PH_ROMS_DIRS": os.pathsep.join((str(card_one), str(card_two))),
        "PH_STORES": "vimm",
        "PH_TIMEOUT": "5",
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
        return run_pocket_harbor([])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
