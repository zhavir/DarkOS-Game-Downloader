"""Persistent concurrent game-download queue."""

import json
import logging
import os
import random
import shutil
import time
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from threading import Event, RLock, Timer
from typing import Any, cast

from ph.bittorrent import BitTorrentSettings, TorrentFileChoice
from ph.downloader import (
    DownloadCancelled,
    DownloadError,
    DownloadRateLimited,
    DownloadSelectionRequired,
    download_files,
)
from ph.library import replace_game
from ph.models import DownloadResult, InstalledGame, MediaDownload, Platform
from ph.organizer import OrganizeError, install_bundled_bios, install_downloads

LOGGER = logging.getLogger(__name__)

QUEUE_FILENAME = ".pocket-harbor-downloads.json"
QUEUE_DIRECTORY = ".pocket-harbor-downloads"
QUEUE_FORMAT_VERSION = 1
DEFAULT_CONCURRENT_DOWNLOADS = 3
RATE_LIMIT_RETRY_BASE_SECONDS = 15.0
RATE_LIMIT_RETRY_MAX_SECONDS = 60.0 * 60.0
RATE_LIMIT_RETRY_JITTER = 0.2

type DownloadRunner = Callable[..., list[DownloadResult]]
type DownloadInstaller = Callable[..., list[DownloadResult]]
type GameReplacer = Callable[[InstalledGame, DownloadResult], DownloadResult]
type BundledBiosInstaller = Callable[..., tuple[Path, ...]]
type RetryDelay = Callable[[int, float | None], float]


@dataclass(frozen=True, slots=True)
class RateLimitRetrySettings:
    """User-configurable exponential backoff policy for HTTP 429 responses."""

    base_seconds: float = RATE_LIMIT_RETRY_BASE_SECONDS
    max_seconds: float = RATE_LIMIT_RETRY_MAX_SECONDS
    jitter_ratio: float = RATE_LIMIT_RETRY_JITTER

    def __post_init__(self) -> None:
        if self.base_seconds <= 0:
            raise ValueError("Initial retry delay must be positive.")
        if self.max_seconds < self.base_seconds:
            raise ValueError("Maximum retry delay must not be shorter than the initial delay.")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("Retry jitter ratio must be between 0 and 1.")


class DownloadState(StrEnum):
    """Stable states exposed to the TUI and persisted between launches."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    RATE_LIMITED = "rate_limited"
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class DownloadJob:
    """Read-only snapshot of one queued game download."""

    job_id: str
    title: str
    store_id: str
    store_name: str
    state: DownloadState
    filename: str
    downloaded_bytes: int
    total_bytes: int | None
    error: str | None
    created_at: float
    completed_path: Path | None
    torrent_candidates: tuple[TorrentFileChoice, ...]
    platform: Platform
    roms_directory: Path
    region: str | None
    bundled_bios_count: int
    is_update: bool
    retry_attempt: int = 0
    retry_at: float | None = None
    bios_directory: str = "bios"


@dataclass(slots=True)
class _QueuedDownload:
    job_id: str
    title: str
    store_id: str
    store_name: str
    referrer: str
    media: tuple[MediaDownload, ...]
    platform: Platform
    roms_directory: Path
    bios_directory: str
    timeout_seconds: float
    bittorrent_settings: BitTorrentSettings | None
    region: str | None
    replacement_game: InstalledGame | None = None
    state: DownloadState = DownloadState.QUEUED
    filename: str = ""
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_path: Path | None = None
    bundled_bios_count: int = 0
    torrent_candidates: tuple[TorrentFileChoice, ...] = ()
    stop_reason: str | None = None
    stop_event: Event = field(default_factory=Event, repr=False)
    last_persisted_at: float = field(default=0.0, repr=False)
    retry_attempt: int = 0
    retry_at: float | None = None

    def snapshot(self) -> DownloadJob:
        return DownloadJob(
            job_id=self.job_id,
            title=self.title,
            store_id=self.store_id,
            store_name=self.store_name,
            state=self.state,
            filename=self.filename,
            downloaded_bytes=self.downloaded_bytes,
            total_bytes=self.total_bytes,
            error=self.error,
            created_at=self.created_at,
            completed_path=self.completed_path,
            torrent_candidates=self.torrent_candidates,
            platform=self.platform,
            roms_directory=self.roms_directory,
            region=self.region,
            bundled_bios_count=self.bundled_bios_count,
            is_update=self.replacement_game is not None,
            retry_attempt=self.retry_attempt,
            retry_at=self.retry_at,
            bios_directory=self.bios_directory,
        )


class DownloadQueue:
    """Run several downloads concurrently and preserve unfinished jobs on disk."""

    def __init__(
        self,
        download_directory: Path,
        *,
        max_concurrent: int = DEFAULT_CONCURRENT_DOWNLOADS,
        runner: DownloadRunner = download_files,
        installer: DownloadInstaller = install_downloads,
        replacer: GameReplacer = replace_game,
        bios_installer: BundledBiosInstaller = install_bundled_bios,
        retry_delay: RetryDelay | None = None,
        retry_settings: RateLimitRetrySettings | None = None,
    ) -> None:
        if max_concurrent <= 0:
            raise ValueError("The concurrent download count must be positive.")
        self.download_directory = download_directory
        self.queue_path = download_directory / QUEUE_FILENAME
        self.staging_root = download_directory / QUEUE_DIRECTORY
        self._runner = runner
        self._installer = installer
        self._replacer = replacer
        self._bios_installer = bios_installer
        self._retry_delay = retry_delay
        self._retry_settings = retry_settings or RateLimitRetrySettings()
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrent,
            thread_name_prefix="pocket-harbor-download",
        )
        self._jobs: dict[str, _QueuedDownload] = {}
        self._futures: dict[str, Future[None]] = {}
        self._retry_timers: dict[str, Timer] = {}
        self._closing = False
        self._refresh_required = False
        self._load()
        with self._lock:
            for job in self._jobs.values():
                if job.state in {DownloadState.QUEUED, DownloadState.DOWNLOADING}:
                    job.state = DownloadState.QUEUED
                    self._submit_locked(job)
                elif job.state is DownloadState.RATE_LIMITED:
                    self._schedule_rate_limit_retry_locked(job)
            self._save_locked()

    def enqueue(
        self,
        *,
        title: str,
        store_id: str,
        store_name: str,
        referrer: str,
        media: Sequence[MediaDownload],
        platform: Platform,
        roms_directory: Path,
        timeout_seconds: float,
        bios_directory: str = "bios",
        bittorrent_settings: BitTorrentSettings | None = None,
        region: str | None = None,
        replacement_game: InstalledGame | None = None,
    ) -> DownloadJob:
        """Persist and start one game download using a snapshot of its store settings."""

        if not media:
            raise DownloadError("The download list is empty.")
        job = _QueuedDownload(
            job_id=uuid.uuid4().hex[:12],
            title=title.strip() or media[0].expected_filename or "Download",
            store_id=store_id,
            store_name=store_name,
            referrer=referrer,
            media=tuple(media),
            platform=platform,
            roms_directory=roms_directory,
            bios_directory=bios_directory,
            timeout_seconds=timeout_seconds,
            bittorrent_settings=bittorrent_settings,
            region=region,
            replacement_game=replacement_game,
        )
        with self._lock:
            if self._closing:
                raise DownloadError("The download queue is closing.")
            self._jobs[job.job_id] = job
            self._save_locked()
            self._submit_locked(job)
        LOGGER.info(
            "Queued game download id=%s title=%r store=%s platform=%s",
            job.job_id,
            job.title,
            job.store_id,
            job.platform.alias,
        )
        return job.snapshot()

    def jobs(self) -> tuple[DownloadJob, ...]:
        """Return stable snapshots ordered with the newest job first."""

        with self._lock:
            return tuple(
                job.snapshot()
                for job in sorted(
                    self._jobs.values(),
                    key=lambda item: item.created_at,
                    reverse=True,
                )
            )

    def find(self, job_id: str) -> DownloadJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job is not None else None

    def dismiss_completed(self, job_id: str) -> bool:
        """Remove a completed job after the interface has acknowledged it."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not DownloadState.COMPLETED:
                return False
            del self._jobs[job_id]
            self._futures.pop(job_id, None)
            self._save_locked()
        LOGGER.debug("Removed acknowledged completed download id=%s", job_id)
        return True

    def pause(self, job_id: str) -> bool:
        """Pause a queued or active job while keeping its verified partial data."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state not in {
                DownloadState.QUEUED,
                DownloadState.DOWNLOADING,
                DownloadState.RATE_LIMITED,
            }:
                return False
            if job.state is DownloadState.RATE_LIMITED:
                self._cancel_retry_timer_locked(job_id)
                job.state = DownloadState.PAUSED
                self._save_locked()
                return True
            job.stop_reason = "pause"
            job.stop_event.set()
            future = self._futures.get(job_id)
            if future is not None and future.cancel():
                job.state = DownloadState.PAUSED
                job.stop_event.clear()
            self._save_locked()
            return True

    def resume(self, job_id: str) -> bool:
        """Resume an explicitly paused job."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not DownloadState.PAUSED or self._closing:
                return False
            self._reset_for_run(job, keep_progress=True)
            self._save_locked()
            self._submit_locked(job)
            return True

    def retry(self, job_id: str) -> bool:
        """Retry a failed or cancelled job, reusing any safe partial data."""

        with self._lock:
            job = self._jobs.get(job_id)
            if (
                job is None
                or job.state
                not in {
                    DownloadState.FAILED,
                    DownloadState.CANCELLED,
                }
                or self._closing
            ):
                return False
            self._reset_for_run(job, keep_progress=job.state is DownloadState.FAILED)
            self._save_locked()
            self._submit_locked(job)
            return True

    def cancel(self, job_id: str) -> bool:
        """Cancel a job and remove its incomplete transfer data."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state in {
                DownloadState.CANCELLED,
                DownloadState.COMPLETED,
            }:
                return False
            if job.state is DownloadState.RATE_LIMITED:
                self._cancel_retry_timer_locked(job_id)
                job.state = DownloadState.CANCELLED
                self._remove_staging(job.job_id)
                self._save_locked()
                return True
            job.stop_reason = "cancel"
            job.stop_event.set()
            future = self._futures.get(job_id)
            if (future is not None and future.cancel()) or job.state in {
                DownloadState.PAUSED,
                DownloadState.FAILED,
            }:
                job.state = DownloadState.CANCELLED
                self._remove_staging(job.job_id)
            self._save_locked()
            return True

    def choose_torrent_file(self, job_id: str, choice: TorrentFileChoice) -> bool:
        """Apply an explicit Minerva file choice before retrying a failed job."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not DownloadState.FAILED:
                return False
            changed = False
            updated: list[MediaDownload] = []
            for media in job.media:
                if not changed and media.torrent_file_index is not None:
                    updated.append(
                        replace(
                            media,
                            torrent_file_index=choice.index,
                            expected_filename=choice.filename,
                            torrent_file_path=choice.path,
                        )
                    )
                    changed = True
                else:
                    updated.append(media)
            if not changed:
                return False
            job.media = tuple(updated)
            job.torrent_candidates = ()
            job.error = None
            self._save_locked()
            return True

    @property
    def refresh_required(self) -> bool:
        with self._lock:
            return self._refresh_required

    def update_retry_settings(self, settings: RateLimitRetrySettings) -> None:
        """Apply a changed backoff policy to retry delays scheduled from now on."""

        with self._lock:
            self._retry_settings = settings

    def mark_refreshed(self) -> None:
        """Persist that the frontend has observed all completed installations."""

        with self._lock:
            self._refresh_required = False
            self._save_locked(include_terminal=not self._closing)

    def shutdown(self) -> None:
        """Stop workers safely; interrupted jobs resume automatically next launch."""

        with self._lock:
            if self._closing:
                return
            self._closing = True
            for job in self._jobs.values():
                if job.state not in {DownloadState.QUEUED, DownloadState.DOWNLOADING}:
                    continue
                job.stop_reason = "shutdown"
                job.stop_event.set()
                future = self._futures.get(job.job_id)
                if future is not None and future.cancel():
                    job.state = DownloadState.QUEUED
            for timer in self._retry_timers.values():
                timer.cancel()
            self._retry_timers.clear()
            self._save_locked(include_terminal=False)
        self._executor.shutdown(wait=True, cancel_futures=True)
        with self._lock:
            self._save_locked(include_terminal=False)
        LOGGER.info("Download queue stopped with %d persistent job(s)", len(self._jobs))

    def _submit_locked(self, job: _QueuedDownload) -> None:
        job.stop_reason = None
        job.stop_event.clear()
        self._futures[job.job_id] = self._executor.submit(self._run, job.job_id)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not DownloadState.QUEUED or self._closing:
                return
            job.state = DownloadState.DOWNLOADING
            self._save_locked()
            job_directory = self.staging_root / job.job_id

        installed_bios: list[Path] = []
        try:
            downloads = self._runner(
                job.media,
                job_directory,
                job.referrer,
                job.timeout_seconds,
                lambda label, current, total: self._progress(job_id, label, current, total),
                job.stop_event.is_set,
                bittorrent_settings=job.bittorrent_settings,
                resume=True,
            )
            if job.stop_event.is_set():
                raise DownloadCancelled("Download interrupted.")
            if job.replacement_game is not None:
                if len(downloads) != 1:
                    raise OrganizeError("A game update must contain exactly one download.")
                installed_bios.extend(
                    self._bios_installer(
                        downloads[0].path,
                        job.platform,
                        job.roms_directory,
                        job.bios_directory,
                    )
                )
                completed = [self._replacer(job.replacement_game, downloads[0])]
            else:
                completed = self._installer(
                    downloads,
                    job.platform,
                    job.roms_directory,
                    installed_bios.append,
                    job.bios_directory,
                )
            if not completed:
                raise OrganizeError("The completed download was not installed.")
        except DownloadSelectionRequired as error:
            self._finish_failed(job_id, str(error), error.candidates)
            return
        except DownloadRateLimited as error:
            self._finish_rate_limited(job_id, error)
            return
        except DownloadCancelled:
            self._finish_interrupted(job_id)
            return
        except (DownloadError, OrganizeError, OSError) as error:
            self._finish_failed(job_id, str(error))
            return
        except Exception as error:  # pragma: no cover - final worker boundary
            LOGGER.exception("Unexpected background download failure id=%s", job_id)
            self._finish_failed(job_id, str(error))
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.state = DownloadState.COMPLETED
            job.completed_path = completed[0].path
            job.bundled_bios_count = len(installed_bios)
            job.downloaded_bytes = job.total_bytes or job.downloaded_bytes
            job.error = None
            self._refresh_required = True
            self._save_locked()
        self._remove_staging(job_id)
        LOGGER.info("Background download installed id=%s path=%s", job_id, completed[0].path)

    def _progress(self, job_id: str, label: str, current: int, total: int | None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.filename = label
            job.downloaded_bytes = current
            job.total_bytes = total
            now = time.monotonic()
            if now - job.last_persisted_at >= 5:
                job.last_persisted_at = now
                self._save_locked()

    def _finish_interrupted(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            reason = job.stop_reason
            if reason == "cancel":
                job.state = DownloadState.CANCELLED
                self._remove_staging(job_id)
            elif reason == "pause":
                job.state = DownloadState.PAUSED
            else:
                job.state = DownloadState.QUEUED
            job.stop_event.clear()
            self._save_locked(include_terminal=not self._closing)
        LOGGER.info("Background download interrupted id=%s reason=%s", job_id, reason)

    def _finish_failed(
        self,
        job_id: str,
        message: str,
        candidates: tuple[TorrentFileChoice, ...] = (),
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.state = DownloadState.FAILED
            job.error = message
            job.torrent_candidates = candidates
            job.stop_event.clear()
            self._save_locked()
        LOGGER.error("Background download failed id=%s: %s", job_id, message)

    def _finish_rate_limited(self, job_id: str, error: DownloadRateLimited) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.retry_attempt += 1
            delay = max(
                0.0,
                self._retry_delay(job.retry_attempt, error.retry_after_seconds)
                if self._retry_delay is not None
                else _rate_limit_retry_delay(
                    job.retry_attempt,
                    error.retry_after_seconds,
                    self._retry_settings,
                ),
            )
            job.state = DownloadState.RATE_LIMITED
            job.error = str(error)
            job.retry_at = time.time() + delay
            job.stop_event.clear()
            self._save_locked()
            if not self._closing:
                self._schedule_rate_limit_retry_locked(job)
        LOGGER.warning(
            "Background download rate limited id=%s store=%s attempt=%d retry_in=%.1fs",
            job_id,
            job.store_id,
            job.retry_attempt,
            delay,
        )

    def _schedule_rate_limit_retry_locked(self, job: _QueuedDownload) -> None:
        self._cancel_retry_timer_locked(job.job_id)
        delay = max(0.0, (job.retry_at or time.time()) - time.time())
        timer = Timer(delay, self._retry_rate_limited, args=(job.job_id,))
        timer.daemon = True
        self._retry_timers[job.job_id] = timer
        timer.start()

    def _retry_rate_limited(self, job_id: str) -> None:
        with self._lock:
            self._retry_timers.pop(job_id, None)
            job = self._jobs.get(job_id)
            if job is None or job.state is not DownloadState.RATE_LIMITED or self._closing:
                return
            job.state = DownloadState.QUEUED
            job.retry_at = None
            self._save_locked()
            self._submit_locked(job)

    def _cancel_retry_timer_locked(self, job_id: str) -> None:
        timer = self._retry_timers.pop(job_id, None)
        if timer is not None:
            timer.cancel()

    def _reset_for_run(self, job: _QueuedDownload, *, keep_progress: bool) -> None:
        job.state = DownloadState.QUEUED
        job.error = None
        job.stop_reason = None
        job.stop_event.clear()
        job.retry_attempt = 0
        job.retry_at = None
        if not keep_progress:
            self._remove_staging(job.job_id)
            job.filename = ""
            job.downloaded_bytes = 0
            job.total_bytes = None

    def _remove_staging(self, job_id: str) -> None:
        if not job_id or "/" in job_id or "\\" in job_id:
            return
        shutil.rmtree(self.staging_root / job_id, ignore_errors=True)

    def _load(self) -> None:
        try:
            payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            LOGGER.warning("Could not read persistent download queue: %s", error)
            return
        if not isinstance(payload, dict) or payload.get("version") != QUEUE_FORMAT_VERSION:
            LOGGER.warning("Ignoring an unsupported persistent download queue")
            return
        self._refresh_required = payload.get("refresh_required") is True
        raw_jobs = payload.get("jobs")
        if not isinstance(raw_jobs, list):
            return
        for raw_job in raw_jobs:
            try:
                job = _job_from_json(raw_job)
            except KeyError, TypeError, ValueError:
                LOGGER.warning("Ignoring a malformed persistent download job")
                continue
            if (
                job.state is DownloadState.FAILED
                and job.error is not None
                and "HTTP 429" in job.error
            ):
                job.state = DownloadState.RATE_LIMITED
                job.retry_attempt = max(1, job.retry_attempt)
                job.retry_at = time.time()
                LOGGER.info("Migrated rate-limited download for automatic retry id=%s", job.job_id)
            if job.state not in {DownloadState.COMPLETED, DownloadState.CANCELLED}:
                self._jobs[job.job_id] = job

    def _save_locked(self, *, include_terminal: bool = True) -> None:
        jobs = [
            _job_to_json(job)
            for job in self._jobs.values()
            if include_terminal
            or job.state not in {DownloadState.COMPLETED, DownloadState.CANCELLED}
        ]
        payload = {
            "version": QUEUE_FORMAT_VERSION,
            "refresh_required": self._refresh_required,
            "jobs": jobs,
        }
        temporary = self.queue_path.with_name(self.queue_path.name + ".tmp")
        try:
            self.download_directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.queue_path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            LOGGER.error("Could not persist download queue: %s", error)


def _job_to_json(job: _QueuedDownload) -> dict[str, object]:
    return {
        "id": job.job_id,
        "title": job.title,
        "store_id": job.store_id,
        "store_name": job.store_name,
        "referrer": job.referrer,
        "media": [
            {
                "url": media.url,
                "torrent_file_index": media.torrent_file_index,
                "expected_filename": media.expected_filename,
                "torrent_file_path": list(media.torrent_file_path)
                if media.torrent_file_path is not None
                else None,
            }
            for media in job.media
        ],
        "platform": {
            "name": job.platform.name,
            "slug": job.platform.slug,
            "code": job.platform.code,
            "alias": job.platform.alias,
            "rom_folder": job.platform.rom_folder,
            "alternate_folders": list(job.platform.alternate_folders),
        },
        "roms_directory": str(job.roms_directory),
        "bios_directory": job.bios_directory,
        "timeout_seconds": job.timeout_seconds,
        "bittorrent_settings": asdict(job.bittorrent_settings)
        if job.bittorrent_settings is not None
        else None,
        "region": job.region,
        "replacement_game": _installed_game_to_json(job.replacement_game),
        "state": job.state.value,
        "filename": job.filename,
        "downloaded_bytes": job.downloaded_bytes,
        "total_bytes": job.total_bytes,
        "error": job.error,
        "created_at": job.created_at,
        "completed_path": str(job.completed_path) if job.completed_path is not None else None,
        "bundled_bios_count": job.bundled_bios_count,
        "torrent_candidates": [
            {
                "index": choice.index,
                "path": list(choice.path),
                "length": choice.length,
                "match_score": choice.match_score,
            }
            for choice in job.torrent_candidates
        ],
        "retry_attempt": job.retry_attempt,
        "retry_at": job.retry_at,
    }


def _job_from_json(value: object) -> _QueuedDownload:
    payload = _dictionary(value)
    platform_payload = _dictionary(payload["platform"])
    media_payload = _list(payload["media"])
    settings_payload = payload.get("bittorrent_settings")
    candidates_payload = _list(payload.get("torrent_candidates", []))
    platform = Platform(
        _string(platform_payload["name"]),
        _string(platform_payload["slug"]),
        _string(platform_payload["code"]),
        _string(platform_payload["alias"]),
        _optional_string(platform_payload.get("rom_folder")),
        tuple(_string(item) for item in _list(platform_payload.get("alternate_folders", []))),
    )
    return _QueuedDownload(
        job_id=_string(payload["id"]),
        title=_string(payload["title"]),
        store_id=_string(payload["store_id"]),
        store_name=_string(payload["store_name"]),
        referrer=_string(payload["referrer"]),
        media=tuple(_media_from_json(item) for item in media_payload),
        platform=platform,
        roms_directory=Path(_string(payload["roms_directory"])),
        bios_directory=_string(payload.get("bios_directory", "bios")),
        timeout_seconds=_number(payload["timeout_seconds"]),
        bittorrent_settings=(
            BitTorrentSettings(**_dictionary(settings_payload))
            if settings_payload is not None
            else None
        ),
        region=_optional_string(payload.get("region")),
        replacement_game=_installed_game_from_json(payload.get("replacement_game"), platform),
        state=DownloadState(_string(payload["state"])),
        filename=_string(payload.get("filename", "")),
        downloaded_bytes=_integer(payload.get("downloaded_bytes", 0)),
        total_bytes=_optional_integer(payload.get("total_bytes")),
        error=_optional_string(payload.get("error")),
        created_at=_number(payload.get("created_at", time.time())),
        completed_path=(
            Path(path) if (path := _optional_string(payload.get("completed_path"))) else None
        ),
        bundled_bios_count=_integer(payload.get("bundled_bios_count", 0)),
        torrent_candidates=tuple(_choice_from_json(item) for item in candidates_payload),
        retry_attempt=_integer(payload.get("retry_attempt", 0)),
        retry_at=(_number(payload["retry_at"]) if payload.get("retry_at") is not None else None),
    )


def _rate_limit_retry_delay(
    attempt: int,
    retry_after_seconds: float | None,
    settings: RateLimitRetrySettings | None = None,
) -> float:
    """Return a capped exponential delay with jitter for an HTTP 429 response."""

    effective_settings = settings or RateLimitRetrySettings()
    if retry_after_seconds is not None:
        base = max(retry_after_seconds, 1.0)
        return base * random.uniform(1.0, 1.0 + effective_settings.jitter_ratio)
    else:
        exponent = min(max(attempt - 1, 0), 30)
        base = min(
            effective_settings.base_seconds * (2**exponent),
            effective_settings.max_seconds,
        )
    return base * random.uniform(
        1.0 - effective_settings.jitter_ratio,
        1.0 + effective_settings.jitter_ratio,
    )


def _media_from_json(value: object) -> MediaDownload:
    payload = _dictionary(value)
    raw_path = payload.get("torrent_file_path")
    return MediaDownload(
        _string(payload["url"]),
        _optional_integer(payload.get("torrent_file_index")),
        _optional_string(payload.get("expected_filename")),
        tuple(_string(item) for item in _list(raw_path)) if raw_path is not None else None,
    )


def _choice_from_json(value: object) -> TorrentFileChoice:
    payload = _dictionary(value)
    return TorrentFileChoice(
        _integer(payload["index"]),
        tuple(_string(item) for item in _list(payload["path"])),
        _integer(payload["length"]),
        _number(payload["match_score"]),
    )


def _installed_game_to_json(game: InstalledGame | None) -> dict[str, object] | None:
    if game is None:
        return None
    return {
        "title": game.title,
        "roms_directory": str(game.roms_directory),
        "primary_file": str(game.primary_file),
        "files": [str(path) for path in game.files],
    }


def _installed_game_from_json(value: object, platform: Platform) -> InstalledGame | None:
    if value is None:
        return None
    payload = _dictionary(value)
    return InstalledGame(
        _string(payload["title"]),
        platform,
        Path(_string(payload["roms_directory"])),
        Path(_string(payload["primary_file"])),
        tuple(Path(_string(item)) for item in _list(payload["files"])),
    )


def _dictionary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError
    return cast("dict[str, Any]", value)


def _list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _integer(value)


def _number(value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError
    return float(value)
