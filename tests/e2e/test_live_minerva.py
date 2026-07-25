"""Live end-to-end checks for Minerva's real RetroAchievements catalogue."""

import os
from pathlib import Path
from urllib.request import Request, urlopen

import pytest
from pytest_mock import MockerFixture

from dw_cli.bittorrent import parse_torrent
from dw_cli.config import DEFAULT_MINERVA_BASE_URL, DEFAULT_MINERVA_TORRENT_BASE_URL
from dw_cli.minerva_store import MinervaStore
from dw_cli.models import MediaDownload

GBA_DIRECTORY = "RA - Nintendo Game Boy Advance"
ARDUBOY_DIRECTORY = "RA - Arduboy"
LIVE_DOWNLOAD_PREFIX = "Ardu-EZ Button"


@pytest.fixture(scope="module")
def live_minerva() -> MinervaStore:
    """Share live catalogue responses so the E2E suite does not hammer Minerva."""

    base_url = os.environ.get("DW_LIVE_MINERVA_BASE_URL", DEFAULT_MINERVA_BASE_URL)
    torrent_base_url = os.environ.get(
        "DW_LIVE_MINERVA_TORRENT_BASE_URL",
        DEFAULT_MINERVA_TORRENT_BASE_URL,
    )
    return MinervaStore(base_url, torrent_base_url, timeout_seconds=90)


def _torrent_request(client: MinervaStore, url: str) -> Request:
    return Request(
        url,
        headers={**client.headers, "Referer": client.download_referrer},
    )


@pytest.mark.e2e
@pytest.mark.live
def test_real_minerva_search_catalogue_all_platform_and_resolution(
    live_minerva: MinervaStore,
    mocker: MockerFixture,
) -> None:
    """Exercise Minerva's official browse pages and torrent endpoint without ROM data."""

    prefix_results = live_minerva.search(GBA_DIRECTORY, "aDvAnCe WaRs")
    assert prefix_results
    assert all(result.title.casefold().startswith("advance wars") for result in prefix_results)

    catalogue = live_minerva.search(GBA_DIRECTORY, "")
    assert len(catalogue) > 100
    assert any(result.title.startswith("Advance Wars") for result in catalogue)

    # The production all-platform search covers every directory. Two real directories are enough
    # to verify aggregation and filtering here without downloading tens of megabytes from Minerva
    # on every CI run and provoking its shared-IP connection protection.
    mocker.patch(
        "dw_cli.minerva_store.RA_DIRECTORIES",
        (GBA_DIRECTORY, ARDUBOY_DIRECTORY),
    )
    all_platform_results = live_minerva.search("", "aDvAnCe WaRs")
    assert all_platform_results
    assert all(
        result.title.casefold().startswith("advance wars") for result in all_platform_results
    )
    assert any(result.system == "GBA" for result in all_platform_results)

    selected = next(result for result in prefix_results if result.title.startswith("Advance Wars"))
    download = live_minerva.download_request(selected.link)
    assert isinstance(download, MediaDownload)
    assert download.torrent_file_index is not None
    assert download.torrent_file_index > 0
    assert download.expected_filename is not None
    assert download.expected_filename.startswith("Advance Wars")

    request = _torrent_request(live_minerva, download.url)
    with urlopen(request, timeout=60) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "application/x-bittorrent"
        torrent = parse_torrent(response.read())
    selected_file = torrent.files[download.torrent_file_index - 1]
    assert selected_file.path[-1] == download.expected_filename


@pytest.mark.e2e
@pytest.mark.live
def test_real_minerva_downloads_and_validates_torrent_metadata(
    tmp_path: Path,
    live_minerva: MinervaStore,
) -> None:
    """Download real Minerva torrent metadata and validate its selected file."""

    result = next(
        item
        for item in live_minerva.search(ARDUBOY_DIRECTORY, LIVE_DOWNLOAD_PREFIX)
        if item.title.startswith(LIVE_DOWNLOAD_PREFIX)
    )
    request = live_minerva.download_request(result.link)

    torrent_path = tmp_path / "minerva.torrent"
    with urlopen(_torrent_request(live_minerva, request.url), timeout=90) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "application/x-bittorrent"
        torrent_path.write_bytes(response.read())

    torrent = parse_torrent(torrent_path.read_bytes())
    assert request.torrent_file_index is not None
    assert request.expected_filename is not None
    selected_file = torrent.files[request.torrent_file_index - 1]
    assert selected_file.path[-1] == request.expected_filename
    assert selected_file.length > 10_000
