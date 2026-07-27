"""Live end-to-end checks for Minerva's real RetroAchievements catalogue."""

import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest
from pytest_mock import MockerFixture

from ph.bittorrent import parse_torrent
from ph.config import DEFAULT_MINERVA_BASE_URL, DEFAULT_MINERVA_TORRENT_BASE_URL
from ph.download_queue import DownloadQueue, DownloadState
from ph.minerva_store import MinervaStore
from ph.models import MediaDownload
from ph.platforms import resolve_platform

GBA_DIRECTORY = "RA - Nintendo Game Boy Advance"
ARDUBOY_DIRECTORY = "RA - Arduboy"
LIVE_DOWNLOAD_PREFIX = "Ardu-EZ Button"


@pytest.fixture(scope="module")
def live_minerva() -> MinervaStore:
    """Share live catalogue responses so the E2E suite does not hammer Minerva."""

    base_url = os.environ.get("PH_LIVE_MINERVA_BASE_URL", DEFAULT_MINERVA_BASE_URL)
    torrent_base_url = os.environ.get(
        "PH_LIVE_MINERVA_TORRENT_BASE_URL",
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
        "ph.minerva_store.RA_DIRECTORIES",
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


@pytest.mark.e2e
@pytest.mark.live
def test_real_minerva_runs_two_native_downloads_concurrently(
    tmp_path: Path,
    live_minerva: MinervaStore,
) -> None:
    """Exercise two background workers against Minerva's real Arduboy swarm."""

    catalogue = live_minerva.search(ARDUBOY_DIRECTORY, "")
    torrent_request = live_minerva.download_request(catalogue[0].link)
    with urlopen(_torrent_request(live_minerva, torrent_request.url), timeout=90) as response:
        metadata = parse_torrent(response.read())
    lengths = {item.path[-1]: item.length for item in metadata.files}
    candidates = sorted(
        (
            (result, media, lengths.get(media.expected_filename or "", 0))
            for result in catalogue
            if (media := live_minerva.download_request(result.link)).expected_filename is not None
        ),
        key=lambda item: item[2],
    )
    selected = [item for item in candidates if 10_000 < item[2] < 2 * 1024 * 1024][:2]
    assert len(selected) == 2
    platform = resolve_platform("arduboy")
    assert platform is not None

    roms = tmp_path / "roms"
    queue = DownloadQueue(tmp_path / "downloads", max_concurrent=2)
    jobs = {
        queue.enqueue(
            title=result.title,
            store_id=live_minerva.store_id,
            store_name=live_minerva.display_name,
            referrer=live_minerva.download_referrer,
            media=(media,),
            platform=platform,
            roms_directory=roms,
            timeout_seconds=90,
        ).job_id
        for result, media, _length in selected
    }
    try:
        deadline = time.monotonic() + 10 * 60
        while time.monotonic() < deadline:
            snapshots = {job.job_id: job for job in queue.jobs()}
            failures = {
                job_id: snapshots[job_id].error
                for job_id in jobs
                if snapshots[job_id].state is DownloadState.FAILED
            }
            assert not failures, f"real parallel Minerva downloads failed: {failures}"
            if all(snapshots[job_id].state is DownloadState.COMPLETED for job_id in jobs):
                break
            time.sleep(0.25)
        else:
            pytest.fail("real parallel Minerva downloads did not finish within ten minutes")
    finally:
        queue.shutdown()

    installed = tuple(
        roms / "arduboy" / (media.expected_filename or "") for _result, media, _length in selected
    )
    assert all(path.is_file() for path in installed)
    assert [path.stat().st_size for path in installed] == [item[2] for item in selected]
