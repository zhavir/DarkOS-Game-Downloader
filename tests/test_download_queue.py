import json
import time
from collections.abc import Callable
from pathlib import Path
from threading import Barrier, Event

import pytest

from ph.bittorrent import TorrentFileChoice, TorrentSelectionRequired
from ph.download_queue import (
    DownloadQueue,
    DownloadState,
    RateLimitRetrySettings,
    _rate_limit_retry_delay,
)
from ph.downloader import (
    DownloadCancelled,
    DownloadError,
    DownloadRateLimited,
    DownloadSelectionRequired,
)
from ph.models import DownloadResult, InstalledGame, MediaDownload
from ph.platforms import resolve_platform


def _wait_for_state(
    queue: DownloadQueue,
    job_id: str,
    state: DownloadState,
    timeout: float = 2,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = queue.find(job_id)
        if job is not None and job.state is state:
            return
        time.sleep(0.01)
    current = queue.find(job_id)
    raise AssertionError(f"Job did not reach {state}; current={current}")


def _enqueue(queue: DownloadQueue, root: Path, title: str, url: str) -> str:
    platform = resolve_platform("GBA")
    assert platform is not None
    return queue.enqueue(
        title=title,
        store_id="captured-store",
        store_name="Captured Store",
        referrer="https://captured.test/",
        media=(MediaDownload(url),),
        platform=platform,
        roms_directory=root / "roms",
        timeout_seconds=5,
        region="USA",
    ).job_id


def test_rate_limit_retry_policy_defaults_validation_and_cap() -> None:
    defaults = RateLimitRetrySettings()
    assert defaults.max_seconds == 60 * 60
    without_jitter = RateLimitRetrySettings(15, 3600, 0)
    assert _rate_limit_retry_delay(1, None, without_jitter) == 15
    assert _rate_limit_retry_delay(20, None, without_jitter) == 3600
    assert _rate_limit_retry_delay(1, 7200, without_jitter) == 7200

    with pytest.raises(ValueError, match="positive"):
        RateLimitRetrySettings(0, 3600, 0.2)
    with pytest.raises(ValueError, match="shorter"):
        RateLimitRetrySettings(60, 30, 0.2)
    with pytest.raises(ValueError, match="between"):
        RateLimitRetrySettings(15, 3600, 2)


def test_queue_runs_multiple_downloads_concurrently_and_captures_store(
    tmp_path: Path,
) -> None:
    simultaneous = Barrier(3)

    def runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        _referrer: str,
        _timeout: float,
        progress: Callable[[str, int, int | None], None],
        _cancelled: Callable[[], bool],
        **_kwargs: object,
    ) -> list[DownloadResult]:
        simultaneous.wait(timeout=2)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{Path(media[0].url).name}.zip"
        path.write_bytes(b"game")
        return [DownloadResult(media[0].url, path)]

    queue = DownloadQueue(tmp_path, max_concurrent=2, runner=runner)
    first = _enqueue(queue, tmp_path, "First", "https://example.test/first")
    second = _enqueue(queue, tmp_path, "Second", "https://example.test/second")
    simultaneous.wait(timeout=2)

    _wait_for_state(queue, first, DownloadState.COMPLETED)
    _wait_for_state(queue, second, DownloadState.COMPLETED)
    snapshot = queue.find(first)
    assert snapshot is not None
    assert snapshot.store_id == "captured-store"
    assert snapshot.store_name == "Captured Store"
    assert snapshot.completed_path == tmp_path / "roms" / "gba" / "first.zip"
    assert queue.refresh_required is True
    queue.shutdown()


def test_rate_limited_download_retries_automatically_with_persisted_status(
    tmp_path: Path,
) -> None:
    attempts = 0
    first_rate_limit = Event()

    def runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        _referrer: str,
        _timeout: float,
        _progress: Callable[[str, int, int | None], None],
        _cancelled: Callable[[], bool],
        **_kwargs: object,
    ) -> list[DownloadResult]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            first_rate_limit.set()
            raise DownloadRateLimited()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "game.zip"
        path.write_bytes(b"game")
        return [DownloadResult(media[0].url, path)]

    queue = DownloadQueue(tmp_path, runner=runner, retry_delay=lambda *_args: 0.1)
    job_id = _enqueue(queue, tmp_path, "Rate limited", "https://example.test/game")
    assert first_rate_limit.wait(timeout=1)
    _wait_for_state(queue, job_id, DownloadState.RATE_LIMITED)
    waiting = queue.find(job_id)
    assert waiting is not None
    assert waiting.retry_attempt == 1
    assert waiting.retry_at is not None
    assert "HTTP 429 Too Many Requests" in (waiting.error or "")

    _wait_for_state(queue, job_id, DownloadState.COMPLETED)
    assert attempts == 3
    queue.shutdown()


def test_rate_limit_wait_survives_restart_and_resumes_when_due(tmp_path: Path) -> None:
    def limited_runner(*_args: object, **_kwargs: object) -> list[DownloadResult]:
        raise DownloadRateLimited(60)

    first_queue = DownloadQueue(tmp_path, runner=limited_runner)
    job_id = _enqueue(first_queue, tmp_path, "Persistent limit", "https://example.test/game")
    _wait_for_state(first_queue, job_id, DownloadState.RATE_LIMITED)
    first_queue.shutdown()

    payload = json.loads(first_queue.queue_path.read_text(encoding="utf-8"))
    assert payload["jobs"][0]["state"] == "rate_limited"
    payload["jobs"][0]["retry_at"] = 0
    first_queue.queue_path.write_text(json.dumps(payload), encoding="utf-8")

    def successful_runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        *_args: object,
        **_kwargs: object,
    ) -> list[DownloadResult]:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "resumed.zip"
        path.write_bytes(b"game")
        return [DownloadResult(media[0].url, path)]

    second_queue = DownloadQueue(tmp_path, runner=successful_runner)
    _wait_for_state(second_queue, job_id, DownloadState.COMPLETED)
    second_queue.shutdown()


def test_legacy_http_429_failure_is_migrated_to_automatic_retry(tmp_path: Path) -> None:
    def failed_runner(*_args: object, **_kwargs: object) -> list[DownloadResult]:
        raise DownloadError("temporary failure")

    first_queue = DownloadQueue(tmp_path, runner=failed_runner)
    job_id = _enqueue(first_queue, tmp_path, "Legacy limit", "https://example.test/game")
    _wait_for_state(first_queue, job_id, DownloadState.FAILED)
    first_queue.shutdown()
    payload = json.loads(first_queue.queue_path.read_text(encoding="utf-8"))
    payload["jobs"][0]["error"] = "Download returned HTTP 429."
    first_queue.queue_path.write_text(json.dumps(payload), encoding="utf-8")

    def successful_runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        *_args: object,
        **_kwargs: object,
    ) -> list[DownloadResult]:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "migrated.zip"
        path.write_bytes(b"game")
        return [DownloadResult(media[0].url, path)]

    second_queue = DownloadQueue(tmp_path, runner=successful_runner)
    _wait_for_state(second_queue, job_id, DownloadState.COMPLETED)
    second_queue.shutdown()


def test_rate_limited_jobs_can_be_paused_resumed_and_cancelled(tmp_path: Path) -> None:
    allowed: set[str] = set()

    def runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        *_args: object,
        **_kwargs: object,
    ) -> list[DownloadResult]:
        url = media[0].url
        if url not in allowed:
            raise DownloadRateLimited()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "game.zip"
        path.write_bytes(b"game")
        return [DownloadResult(url, path)]

    queue = DownloadQueue(tmp_path, runner=runner, retry_delay=lambda *_args: 60)
    paused_id = _enqueue(queue, tmp_path, "Pause", "https://example.test/pause")
    _wait_for_state(queue, paused_id, DownloadState.RATE_LIMITED)
    assert queue.pause(paused_id) is True
    paused = queue.find(paused_id)
    assert paused is not None and paused.state is DownloadState.PAUSED
    allowed.add("https://example.test/pause")
    assert queue.resume(paused_id) is True
    _wait_for_state(queue, paused_id, DownloadState.COMPLETED)

    cancelled_id = _enqueue(queue, tmp_path, "Cancel", "https://example.test/cancel")
    _wait_for_state(queue, cancelled_id, DownloadState.RATE_LIMITED)
    assert queue.cancel(cancelled_id) is True
    cancelled = queue.find(cancelled_id)
    assert cancelled is not None and cancelled.state is DownloadState.CANCELLED
    assert not (queue.staging_root / cancelled_id).exists()
    queue.shutdown()


def test_interrupted_job_resumes_automatically_after_restart(tmp_path: Path) -> None:
    started = Event()

    def interrupted_runner(
        _media: object,
        directory: Path,
        _referrer: str,
        _timeout: float,
        progress: Callable[[str, int, int | None], None],
        cancelled: Callable[[], bool],
        **kwargs: object,
    ) -> list[DownloadResult]:
        assert kwargs["resume"] is True
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "game.zip.part").write_bytes(b"partial")
        progress("game.zip", 7, 14)
        started.set()
        while not cancelled():
            time.sleep(0.01)
        raise DownloadCancelled("stopping")

    first_queue = DownloadQueue(tmp_path, runner=interrupted_runner)
    job_id = _enqueue(first_queue, tmp_path, "Persistent", "https://example.test/game")
    assert started.wait(timeout=2)
    first_queue.shutdown()

    resumed: list[bool] = []

    def resumed_runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        _referrer: str,
        _timeout: float,
        _progress: Callable[[str, int, int | None], None],
        _cancelled: Callable[[], bool],
        **kwargs: object,
    ) -> list[DownloadResult]:
        resumed.append(kwargs["resume"] is True)
        assert (directory / "game.zip.part").read_bytes() == b"partial"
        path = directory / "game.zip"
        path.write_bytes(b"complete")
        return [DownloadResult(media[0].url, path)]

    second_queue = DownloadQueue(tmp_path, runner=resumed_runner)
    _wait_for_state(second_queue, job_id, DownloadState.COMPLETED)
    assert resumed == [True]
    second_queue.shutdown()

    third_queue = DownloadQueue(tmp_path, runner=resumed_runner)
    assert third_queue.jobs() == ()
    assert third_queue.refresh_required is True
    third_queue.mark_refreshed()
    third_queue.shutdown()
    payload = json.loads(third_queue.queue_path.read_text(encoding="utf-8"))
    assert payload["jobs"] == []
    assert payload["refresh_required"] is False


def test_pause_resume_cancel_and_retry_controls(tmp_path: Path) -> None:
    attempt = 0
    started = Event()

    def runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        _referrer: str,
        _timeout: float,
        _progress: Callable[[str, int, int | None], None],
        cancelled: Callable[[], bool],
        **_kwargs: object,
    ) -> list[DownloadResult]:
        nonlocal attempt
        attempt += 1
        started.set()
        if attempt == 1:
            while not cancelled():
                time.sleep(0.01)
            raise DownloadCancelled("paused")
        if attempt == 2:
            raise DownloadError("temporary failure")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "game.zip"
        path.write_bytes(b"game")
        return [DownloadResult(media[0].url, path)]

    queue = DownloadQueue(tmp_path, runner=runner)
    job_id = _enqueue(queue, tmp_path, "Controlled", "https://example.test/game")
    assert started.wait(timeout=2)
    assert queue.pause(job_id) is True
    _wait_for_state(queue, job_id, DownloadState.PAUSED)
    assert queue.resume(job_id) is True
    _wait_for_state(queue, job_id, DownloadState.FAILED)
    assert queue.retry(job_id) is True
    _wait_for_state(queue, job_id, DownloadState.COMPLETED)
    assert queue.cancel(job_id) is False
    queue.shutdown()


def test_cancelled_job_removes_partial_data_and_can_be_retried(tmp_path: Path) -> None:
    started = Event()
    attempt = 0

    def runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        _referrer: str,
        _timeout: float,
        _progress: Callable[[str, int, int | None], None],
        cancelled: Callable[[], bool],
        **_kwargs: object,
    ) -> list[DownloadResult]:
        nonlocal attempt
        attempt += 1
        directory.mkdir(parents=True, exist_ok=True)
        if attempt > 1:
            completed = directory / "game.zip"
            completed.write_bytes(b"complete")
            return [DownloadResult(media[0].url, completed)]
        partial = directory / "game.zip.part"
        partial.write_bytes(b"partial")
        started.set()
        while not cancelled():
            time.sleep(0.01)
        raise DownloadCancelled("cancelled")

    queue = DownloadQueue(tmp_path, runner=runner)
    job_id = _enqueue(queue, tmp_path, "Cancel", "https://example.test/game")
    assert started.wait(timeout=2)
    assert queue.cancel(job_id) is True
    _wait_for_state(queue, job_id, DownloadState.CANCELLED)
    assert not (queue.staging_root / job_id).exists()
    assert queue.retry(job_id) is True
    _wait_for_state(queue, job_id, DownloadState.COMPLETED)
    queue.shutdown()


def test_background_update_keeps_old_game_until_replacement_is_ready(tmp_path: Path) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    roms_directory = tmp_path / "roms" / "gba"
    roms_directory.mkdir(parents=True)
    old_file = roms_directory / "Game (v1).zip"
    old_file.write_bytes(b"old")
    installed = InstalledGame("Game", platform, tmp_path / "roms", old_file, (old_file,))
    release_download = Event()

    def runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        _referrer: str,
        _timeout: float,
        _progress: Callable[[str, int, int | None], None],
        _cancelled: Callable[[], bool],
        **_kwargs: object,
    ) -> list[DownloadResult]:
        assert old_file.read_bytes() == b"old"
        assert release_download.wait(timeout=2)
        directory.mkdir(parents=True, exist_ok=True)
        replacement = directory / "Game (v2).zip"
        replacement.write_bytes(b"new")
        return [DownloadResult(media[0].url, replacement)]

    queue = DownloadQueue(tmp_path, runner=runner)
    job = queue.enqueue(
        title="Game v2",
        store_id="vimm",
        store_name="Vimm",
        referrer="https://example.test/",
        media=(MediaDownload("https://example.test/game-v2"),),
        platform=platform,
        roms_directory=tmp_path / "roms",
        timeout_seconds=5,
        replacement_game=installed,
    )
    assert old_file.is_file()
    release_download.set()
    _wait_for_state(queue, job.job_id, DownloadState.COMPLETED)

    completed = queue.find(job.job_id)
    assert completed is not None and completed.is_update is True
    assert not old_file.exists()
    assert completed.completed_path is not None
    assert completed.completed_path.read_bytes() == b"new"
    queue.shutdown()


def test_queue_rejects_invalid_operations_and_new_work_after_shutdown(tmp_path: Path) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    with pytest.raises(ValueError, match="positive"):
        DownloadQueue(tmp_path, max_concurrent=0)

    queue = DownloadQueue(tmp_path)
    with pytest.raises(DownloadError, match="empty"):
        queue.enqueue(
            title="Empty",
            store_id="vimm",
            store_name="Vimm",
            referrer="",
            media=(),
            platform=platform,
            roms_directory=tmp_path,
            timeout_seconds=1,
        )
    assert queue.find("missing") is None
    assert queue.pause("missing") is False
    assert queue.resume("missing") is False
    assert queue.retry("missing") is False
    assert queue.cancel("missing") is False
    assert (
        queue.choose_torrent_file(
            "missing",
            TorrentFileChoice(1, ("game.zip",), 1, 1.0),
        )
        is False
    )
    queue.shutdown()
    queue.shutdown()
    with pytest.raises(DownloadError, match="closing"):
        queue.enqueue(
            title="Late",
            store_id="vimm",
            store_name="Vimm",
            referrer="",
            media=(MediaDownload("url"),),
            platform=platform,
            roms_directory=tmp_path,
            timeout_seconds=1,
        )


def test_torrent_selection_failure_can_be_corrected_and_retried(tmp_path: Path) -> None:
    candidate = TorrentFileChoice(3, ("renamed.zip",), 4, 0.8)
    attempts = 0

    def runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        _referrer: str,
        _timeout: float,
        _progress: Callable[[str, int, int | None], None],
        _cancelled: Callable[[], bool],
        **_kwargs: object,
    ) -> list[DownloadResult]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise DownloadSelectionRequired(
                TorrentSelectionRequired(
                    media[0].url,
                    "expected.zip",
                    1,
                    (candidate,),
                    5,
                )
            )
        assert media[0].torrent_file_index == 3
        assert media[0].torrent_file_path == ("renamed.zip",)
        directory.mkdir(parents=True, exist_ok=True)
        completed = directory / "renamed.zip"
        completed.write_bytes(b"game")
        return [DownloadResult(media[0].url, completed)]

    platform = resolve_platform("GBA")
    assert platform is not None
    queue = DownloadQueue(tmp_path, runner=runner)
    job = queue.enqueue(
        title="Changed",
        store_id="minerva",
        store_name="Minerva",
        referrer="",
        media=(MediaDownload("torrent", 1, "expected.zip"),),
        platform=platform,
        roms_directory=tmp_path / "roms",
        timeout_seconds=1,
    )
    _wait_for_state(queue, job.job_id, DownloadState.FAILED)
    failed = queue.find(job.job_id)
    assert failed is not None and failed.torrent_candidates == (candidate,)
    queue.shutdown()

    queue = DownloadQueue(tmp_path, runner=runner)
    restored = queue.find(job.job_id)
    assert restored is not None and restored.torrent_candidates == (candidate,)
    assert queue.choose_torrent_file(job.job_id, candidate) is True
    assert queue.retry(job.job_id) is True
    _wait_for_state(queue, job.job_id, DownloadState.COMPLETED)
    queue.shutdown()


def test_queue_reports_install_and_worker_failures(tmp_path: Path) -> None:
    def completed_runner(
        media: tuple[MediaDownload, ...],
        directory: Path,
        *_args: object,
        **_kwargs: object,
    ) -> list[DownloadResult]:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "game.zip"
        path.write_bytes(b"game")
        return [DownloadResult(media[0].url, path)]

    empty_installer = DownloadQueue(
        tmp_path / "empty",
        runner=completed_runner,
        installer=lambda *_args: [],
    )
    empty_id = _enqueue(empty_installer, tmp_path / "empty", "Empty", "url")
    _wait_for_state(empty_installer, empty_id, DownloadState.FAILED)
    empty_failure = empty_installer.find(empty_id)
    assert empty_failure is not None and "not installed" in (empty_failure.error or "")
    assert (
        empty_installer.choose_torrent_file(
            empty_id,
            TorrentFileChoice(1, ("game.zip",), 1, 1.0),
        )
        is False
    )
    empty_installer.shutdown()

    def broken_runner(*_args: object, **_kwargs: object) -> list[DownloadResult]:
        raise OSError("disk error")

    broken = DownloadQueue(tmp_path / "broken", runner=broken_runner)
    broken_id = _enqueue(broken, tmp_path / "broken", "Broken", "url")
    _wait_for_state(broken, broken_id, DownloadState.FAILED)
    broken_failure = broken.find(broken_id)
    assert broken_failure is not None and "disk error" in (broken_failure.error or "")
    broken.shutdown()


@pytest.mark.parametrize(
    "payload",
    (
        "not json",
        '{"version": 99, "jobs": []}',
        '{"version": 1, "jobs": {}}',
        '{"version": 1, "jobs": [{"bad": true}]}',
    ),
)
def test_malformed_persistent_queues_are_ignored(tmp_path: Path, payload: str) -> None:
    directory = tmp_path / str(abs(hash(payload)))
    directory.mkdir()
    (directory / ".pocket-harbor-downloads.json").write_text(payload, encoding="utf-8")

    queue = DownloadQueue(directory)

    assert queue.jobs() == ()
    queue.shutdown()
