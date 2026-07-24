"""Download engine with an aria2 fast path and a standard-library fallback."""

import os
import re
import shutil
import ssl
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from dw_cli.models import DownloadResult
from dw_cli.store import USER_AGENT

type ProgressCallback = Callable[[str, int, int | None], None]


class DownloadError(RuntimeError):
    """A download could not be completed."""


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
    urls: Sequence[str],
    directory: Path,
    referer: str,
    timeout_seconds: float = 30.0,
    progress: ProgressCallback | None = None,
) -> list[DownloadResult]:
    """Download URLs serially, preferring aria2 when it is installed."""

    if not urls:
        raise DownloadError("The download list is empty.")
    directory.mkdir(parents=True, exist_ok=True)
    disable_aria2 = os.environ.get("DW_DISABLE_ARIA2", "").casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    aria2 = None if disable_aria2 else shutil.which("aria2c")
    if aria2:
        return _download_with_aria2(aria2, urls, directory, referer, progress)
    return _download_with_urllib(urls, directory, referer, timeout_seconds, progress)


def _download_with_aria2(
    executable: str,
    urls: Sequence[str],
    directory: Path,
    referer: str,
    progress: ProgressCallback | None,
) -> list[DownloadResult]:
    base_command = [
        executable,
        f"--dir={directory}",
        "--max-concurrent-downloads=1",
        "--continue=true",
        "--auto-file-renaming=false",
        "--content-disposition=true",
        "--summary-interval=1",
        f"--referer={referer}",
        f"--user-agent={USER_AGENT}",
    ]
    results: list[DownloadResult] = []
    for index, url in enumerate(urls, start=1):
        if progress:
            progress("Starting aria2 download %d" % index, index - 1, len(urls))
        before = _directory_snapshot(directory)
        try:
            completed = subprocess.run([*base_command, url], check=False)
        except OSError as error:
            raise DownloadError(f"Could not start aria2: {error}") from error
        if completed.returncode != 0:
            raise DownloadError("aria2 exited with status %d." % completed.returncode)
        changed = [
            path
            for path, signature in _directory_snapshot(directory).items()
            if not path.name.endswith(".aria2") and before.get(path) != signature
        ]
        if len(changed) != 1:
            raise DownloadError("Could not identify the file completed by aria2.")
        results.append(DownloadResult(url=url, path=changed[0]))
        if progress:
            progress(changed[0].name, index, len(urls))
    return results


def _directory_snapshot(directory: Path) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in directory.iterdir():
        if path.is_file():
            stat = path.stat()
            snapshot[path] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _download_with_urllib(
    urls: Sequence[str],
    directory: Path,
    referer: str,
    timeout_seconds: float,
    progress: ProgressCallback | None,
) -> list[DownloadResult]:
    results: list[DownloadResult] = []
    ssl_context = ssl.create_default_context()
    for url in urls:
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
                            chunk = response.read(1024 * 256)
                            if not chunk:
                                break
                            output.write(chunk)
                            downloaded += len(chunk)
                            if progress:
                                progress(filename, downloaded, total)
                    os.replace(str(partial), str(destination))
                except BaseException:
                    partial.unlink(missing_ok=True)
                    raise
                results.append(DownloadResult(url=url, path=destination))
        except HTTPError as error:
            raise DownloadError("Download returned HTTP %d." % error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise DownloadError(f"Download failed: {reason}") from error
    return results


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
