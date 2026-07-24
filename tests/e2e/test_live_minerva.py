"""Live end-to-end checks for Minerva's real RetroAchievements catalogue."""

import os
from urllib.request import Request, urlopen

import pytest

from dw_cli.bittorrent import parse_torrent
from dw_cli.config import DEFAULT_MINERVA_BASE_URL, DEFAULT_MINERVA_TORRENT_BASE_URL
from dw_cli.downloader import download_files
from dw_cli.minerva_store import MinervaStore
from dw_cli.models import MediaDownload

GBA_DIRECTORY = "RA - Nintendo Game Boy Advance"
ARDUBOY_DIRECTORY = "RA - Arduboy"
LIVE_DOWNLOAD_PREFIX = "Ardu-EZ Button"


@pytest.mark.e2e
@pytest.mark.live
def test_real_minerva_search_catalogue_all_platform_and_resolution() -> None:
    """Exercise Minerva's official browse pages and torrent endpoint without ROM data."""

    base_url = os.environ.get("DW_LIVE_MINERVA_BASE_URL", DEFAULT_MINERVA_BASE_URL)
    torrent_base_url = os.environ.get(
        "DW_LIVE_MINERVA_TORRENT_BASE_URL",
        DEFAULT_MINERVA_TORRENT_BASE_URL,
    )
    client = MinervaStore(base_url, torrent_base_url, timeout_seconds=90)

    prefix_results = client.search(GBA_DIRECTORY, "aDvAnCe WaRs")
    assert prefix_results
    assert all(result.title.casefold().startswith("advance wars") for result in prefix_results)

    catalogue = client.search(GBA_DIRECTORY, "")
    assert len(catalogue) > 100
    assert any(result.title.startswith("Advance Wars") for result in catalogue)

    all_platform_results = client.search("", "aDvAnCe WaRs")
    assert all_platform_results
    assert all(
        result.title.casefold().startswith("advance wars") for result in all_platform_results
    )
    assert any(result.system == "GBA" for result in all_platform_results)

    selected = next(result for result in prefix_results if result.title.startswith("Advance Wars"))
    download = client.download_request(selected.link)
    assert isinstance(download, MediaDownload)
    assert download.torrent_file_index is not None
    assert download.torrent_file_index > 0
    assert download.expected_filename is not None
    assert download.expected_filename.startswith("Advance Wars")

    request = Request(download.url)
    with urlopen(request, timeout=60) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "application/x-bittorrent"
        torrent = parse_torrent(response.read())
    selected_file = torrent.files[download.torrent_file_index - 1]
    assert selected_file.path[-1] == download.expected_filename


@pytest.mark.e2e
@pytest.mark.live
def test_real_minerva_downloads_and_verifies_a_complete_file(tmp_path) -> None:
    """Download a tiny Arduboy homebrew archive through real trackers and peers."""

    base_url = os.environ.get("DW_LIVE_MINERVA_BASE_URL", DEFAULT_MINERVA_BASE_URL)
    torrent_base_url = os.environ.get(
        "DW_LIVE_MINERVA_TORRENT_BASE_URL",
        DEFAULT_MINERVA_TORRENT_BASE_URL,
    )
    client = MinervaStore(base_url, torrent_base_url, timeout_seconds=90)
    result = next(
        item
        for item in client.search(ARDUBOY_DIRECTORY, LIVE_DOWNLOAD_PREFIX)
        if item.title.startswith(LIVE_DOWNLOAD_PREFIX)
    )
    request = client.download_request(result.link)

    completed = download_files(
        [request],
        tmp_path,
        client.download_referrer,
        timeout_seconds=90,
    )

    assert len(completed) == 1
    downloaded = completed[0].path
    assert downloaded.name == request.expected_filename
    assert downloaded.stat().st_size > 10_000
    assert downloaded.read_bytes().startswith(b"PK")
    assert not downloaded.with_name(downloaded.name + ".part").exists()
