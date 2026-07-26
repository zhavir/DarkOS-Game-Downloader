"""Native HTTP and selective BitTorrent download engine."""

import logging
import os
import re
import ssl
from collections.abc import Callable, Mapping, Sequence
from functools import partial
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from ph.bittorrent import (
    BitTorrentCancelled,
    BitTorrentError,
    BitTorrentSettings,
    TorrentFileChoice,
    TorrentSelectionRequired,
    download_torrent_file,
)
from ph.models import DownloadResult, MediaDownload
from ph.store import USER_AGENT

LOGGER = logging.getLogger(__name__)

type ProgressCallback = Callable[[str, int, int | None], None]
type CancelCallback = Callable[[], bool]


class DownloadError(RuntimeError):
    """A download could not be completed."""


class DownloadCancelled(DownloadError):
    """The user cancelled an in-progress download."""


class DownloadSelectionRequired(DownloadError):
    """A changed torrent needs an explicit file choice from the user."""

    def __init__(self, error: TorrentSelectionRequired) -> None:
        super().__init__(str(error))
        self.torrent_url = error.torrent_url
        self.expected_filename = error.expected_filename
        self.catalogue_index = error.catalogue_index
        self.candidates: tuple[TorrentFileChoice, ...] = error.candidates
        self.total_files = error.total_files


def _safe_filename(value: str) -> str:
    name = Path(unquote(value)).name
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip(". ")
    return name or "download.bin"


def _filename_from_headers(headers: Mapping[str, str], url: str) -> str:
    disposition = headers.get("Content-Disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.IGNORECASE)
    if match:
        return _safe_filename(match.group(1).strip())
    return _safe_filename(urlparse(url).path)


def download_files(
    downloads: Sequence[str | MediaDownload],
    directory: Path,
    referer: str,
    timeout_seconds: float = 30.0,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
    bittorrent_settings: BitTorrentSettings | None = None,
) -> list[DownloadResult]:
    """Download direct URLs or selected torrent files without external tools."""

    if not downloads:
        LOGGER.warning("Download requested with an empty media list")
        raise DownloadError("The download list is empty.")
    LOGGER.info("Downloading %d media item(s) into %s", len(downloads), directory)
    directory.mkdir(parents=True, exist_ok=True)
    resolved = [_as_media_download(download) for download in downloads]
    results: list[DownloadResult] = []
    for download in resolved:
        _raise_if_cancelled(cancelled)
        if download.torrent_file_index is None:
            LOGGER.debug("Starting direct media download")
            results.extend(
                _download_with_urllib(
                    [download.url],
                    directory,
                    referer,
                    timeout_seconds,
                    progress,
                    cancelled,
                )
            )
            continue
        if not download.expected_filename:
            raise DownloadError("The torrent download is missing its expected filename.")
        destination = _unique_download_path(directory / download.expected_filename)
        LOGGER.debug(
            "Starting torrent media download file=%r index=%d",
            download.expected_filename,
            download.torrent_file_index,
        )
        try:
            download_torrent_file(
                download.url,
                download.torrent_file_index,
                download.expected_filename,
                destination,
                referer,
                timeout_seconds,
                partial(progress, download.expected_filename) if progress is not None else None,
                cancelled,
                bittorrent_settings,
                download.torrent_file_path,
            )
        except BitTorrentCancelled as error:
            LOGGER.info("Torrent download cancelled")
            raise DownloadCancelled("Download cancelled.") from error
        except TorrentSelectionRequired as error:
            LOGGER.warning("Torrent file selection requires user confirmation: %s", error)
            raise DownloadSelectionRequired(error) from error
        except BitTorrentError as error:
            LOGGER.error("Torrent download failed: %s", error)
            raise DownloadError(str(error)) from error
        results.append(DownloadResult(download.url, destination))
    LOGGER.info("Completed %d media download(s)", len(results))
    return results


def _as_media_download(download: str | MediaDownload) -> MediaDownload:
    return download if isinstance(download, MediaDownload) else MediaDownload(download)


def _download_with_urllib(
    urls: Sequence[str],
    directory: Path,
    referer: str,
    timeout_seconds: float,
    progress: ProgressCallback | None,
    cancelled: CancelCallback | None,
) -> list[DownloadResult]:
    results: list[DownloadResult] = []
    ssl_context = ssl.create_default_context()
    for url in urls:
        _raise_if_cancelled(cancelled)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Referer": referer})
        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
                context=ssl_context,
            ) as response:
                filename = _filename_from_headers(response.headers, response.geturl())
                destination = _unique_download_path(directory / filename)
                partial = destination.with_name(destination.name + ".part")
                total_header = response.headers.get("Content-Length")
                total = int(total_header) if total_header and total_header.isdigit() else None
                downloaded = 0
                try:
                    with partial.open("wb") as output:
                        while True:
                            _raise_if_cancelled(cancelled)
                            chunk = response.read(1024 * 256)
                            if not chunk:
                                break
                            output.write(chunk)
                            downloaded += len(chunk)
                            if progress:
                                progress(filename, downloaded, total)
                        _raise_if_cancelled(cancelled)
                    os.replace(str(partial), str(destination))
                except BaseException:
                    partial.unlink(missing_ok=True)
                    raise
                results.append(DownloadResult(url=url, path=destination))
        except HTTPError as error:
            LOGGER.error("HTTP download returned status=%d", error.code)
            raise DownloadError("Download returned HTTP %d." % error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            LOGGER.error("HTTP download failed: %s", reason)
            raise DownloadError(f"Download failed: {reason}") from error
    return results


def _raise_if_cancelled(cancelled: CancelCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise DownloadCancelled("Download cancelled.")


def _unique_download_path(destination: Path) -> Path:
    partial = destination.with_name(destination.name + ".part")
    if not destination.exists() and not partial.exists():
        return destination
    suffixes = "".join(destination.suffixes)
    stem = destination.name[: -len(suffixes)] if suffixes else destination.name
    counter = 2
    while True:
        candidate = destination.with_name(f"{stem} ({counter}){suffixes}")
        partial = candidate.with_name(candidate.name + ".part")
        if not candidate.exists() and not partial.exists():
            return candidate
        counter += 1
