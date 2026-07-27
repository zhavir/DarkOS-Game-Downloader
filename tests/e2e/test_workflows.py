"""Offline end-to-end coverage for the user-visible library workflows."""

import json
import os
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ph.app import main
from ph.config import Config
from ph.downloader import download_files
from ph.library import delete_game, replace_game, scan_library
from ph.models import DownloadResult
from ph.organizer import detect_roms_directories, install_downloads
from ph.platforms import DARKOS_PLATFORMS, resolve_platform
from ph.vimm_store import VimmStore
from scripts.local_vault_server import build_server
from scripts.run_local_demo import prepare_demo_environment


@pytest.fixture
def local_vault() -> Iterator[str]:
    server = build_server(
        port=0,
        exact_search_only=True,
        missing_sections_return_404=True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_demo_environment_creates_two_safe_local_cards(tmp_path: Path) -> None:
    environment = prepare_demo_environment(tmp_path / "demo", "http://127.0.0.1:9999")
    roots = tuple(Path(value) for value in environment["PH_ROMS_DIRS"].split(os.pathsep))

    assert (roots[0] / "gba").is_dir()
    assert (roots[1] / "gba").is_dir()
    assert environment["PH_STORES"] == "vimm"


@pytest.mark.e2e
@pytest.mark.integration
def test_search_caches_full_catalogue_for_prefix_empty_and_offline_replay(
    local_vault: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
) -> None:
    staging = tmp_path / "downloads"
    card = tmp_path / "sd1"
    (card / "gba").mkdir(parents=True)
    config = Config.from_environment(
        {
            "PH_VIMM_BASE_URL": local_vault,
            "PH_DOWNLOAD_DIR": str(staging),
            "PH_ROMS_DIR": str(card),
        }
    )

    assert main(["search", "GBA", "aDv"], runtime_config=config) == 0
    search_output = capsys.readouterr().out
    assert "Advance Wars" in search_output
    assert "Golden Sun" not in search_output

    assert main(["search", "GBA"], runtime_config=config) == 0
    catalogue_output = capsys.readouterr().out
    assert "Advance Wars" in catalogue_output
    assert "Golden Sun" in catalogue_output
    assert "007 - Everything or Nothing" in catalogue_output

    assert main(["search", "ALL"], runtime_config=config) == 0
    all_catalogue_output = capsys.readouterr().out
    assert "Advance Wars" in all_catalogue_output
    assert "Golden Sun" in all_catalogue_output

    cache_path = staging / "game-catalogues" / "vimm" / "GBA.json"
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache_payload["store_id"] == "vimm"
    assert cache_payload["system_code"] == "GBA"
    assert {item["title"] for item in cache_payload["results"]} >= {
        "Advance Wars",
        "Golden Sun",
    }

    cached_store = VimmStore(local_vault, config.timeout_seconds, staging)
    network_fetch = mocker.patch.object(
        cached_store,
        "_fetch_catalogue",
        side_effect=AssertionError("a fresh catalogue must not contact the store"),
    )
    assert [result.title for result in cached_store.search("GBA", "gOlD")] == ["Golden Sun"]
    assert len(cached_store.search("GBA", "")) >= 3
    network_fetch.assert_not_called()

    assert (
        main(
            ["download", "--platform", "GBA", f"{local_vault}/vault/2001"],
            runtime_config=config,
        )
        == 0
    )
    download_output = capsys.readouterr().out
    installed = card / "gba" / "Golden Sun (USA).zip"
    assert str(installed) in download_output
    with zipfile.ZipFile(installed) as game_archive:
        assert game_archive.read("Golden Sun.gba") == b"golden-sun"
    assert (card / "bios" / "gba_bios.bin").read_bytes() == b"demo-bios"
    assert "BIOS installed:" in download_output
    assert not tuple(staging.glob("*.part"))


@pytest.mark.e2e
@pytest.mark.integration
def test_dual_card_install_update_and_delete_workflow(
    local_vault: str,
    tmp_path: Path,
) -> None:
    card_one = tmp_path / "sd1"
    card_two = tmp_path / "sd2"
    staging = tmp_path / "downloads"
    (card_one / "gba").mkdir(parents=True)
    (card_two / "gba").mkdir(parents=True)
    config = Config.from_environment(
        {
            "PH_VIMM_BASE_URL": local_vault,
            "PH_DOWNLOAD_DIR": str(staging),
            "PH_ROMS_DIRS": os.pathsep.join((str(card_one), str(card_two))),
        }
    )
    assert config.roms_directories == (card_one, card_two)
    assert detect_roms_directories(config.roms_directories) == (card_one, card_two)
    platform = resolve_platform("GBA")
    assert platform is not None
    client = VimmStore(config.vimm_base_url, config.timeout_seconds)

    matches = client.search(platform.code, "advance wars")
    original = next(result for result in matches if result.version == "1.0")
    original_download = _download(client, original.link, staging, local_vault)
    installed = install_downloads([original_download], platform, card_two)[0]
    assert installed.path == card_two / "gba" / "Advance Wars (USA).zip"
    assert installed.path.read_bytes() == b"demo-v1"

    installed_games = scan_library(config.roms_directories, DARKOS_PLATFORMS)
    game = next(item for item in installed_games if item.primary_file == installed.path)
    replacement = next(result for result in matches if result.version == "Rev 2")
    replacement_download = _download(client, replacement.link, staging, local_vault)
    updated = replace_game(game, replacement_download)
    assert updated.path.parent == card_two / "gba"
    assert updated.path.read_bytes() == b"demo-v2"
    assert not installed.path.exists()

    updated_game = next(
        item
        for item in scan_library(config.roms_directories, DARKOS_PLATFORMS)
        if item.primary_file == updated.path
    )
    delete_game(updated_game)
    assert not updated.path.exists()
    assert not scan_library(config.roms_directories, DARKOS_PLATFORMS)


def _download(
    client: VimmStore,
    detail_url: str,
    staging: Path,
    base_url: str,
) -> DownloadResult:
    media_url = client.retrieve_download_url(detail_url)
    return download_files([media_url], staging, f"{base_url}/vault/")[0]
