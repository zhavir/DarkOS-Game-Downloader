import io
import json
import stat
import zipfile
from email.message import Message
from pathlib import Path
from types import TracebackType
from urllib.error import HTTPError, URLError

import pytest
from pytest_mock import MockerFixture

from dw_cli import updater
from dw_cli.updater import (
    READY_MARKER,
    ReleaseUpdate,
    UpdateCancelled,
    UpdateError,
    _download_release,
    _extract_bundle,
    _parse_version,
    _remove_staging_path,
    _safe_bundle_path,
    _validate_staged_bundle,
    find_update,
    installed_version,
    stage_update,
)


class Response(io.BytesIO):
    def __init__(self, payload: bytes, content_length: str | None = None) -> None:
        super().__init__(payload)
        self.headers = {} if content_length is None else {"Content-Length": content_length}

    def __enter__(self) -> Response:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def test_installed_version_falls_back_for_source_checkout(mocker: MockerFixture) -> None:
    mocker.patch.object(
        updater, "version", lambda _name: (_ for _ in ()).throw(updater.PackageNotFoundError())
    )
    assert installed_version() == "development"


@pytest.mark.parametrize("value", ("development", "1.2", "v01.2.3", "1.2.3.4"))
def test_parse_version_requires_stable_semver(value: str) -> None:
    with pytest.raises(UpdateError, match="stable semantic version"):
        _parse_version(value, "version")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"not json", "invalid release metadata"),
        (b"[]", "invalid release metadata"),
        (b"{}", "no semantic version tag"),
        (json.dumps({"tag_name": "v2.0.0", "assets": {}}).encode(), "no downloadable assets"),
        (json.dumps({"tag_name": "v2.0.0", "assets": ["bad"]}).encode(), "does not contain"),
        (
            json.dumps(
                {
                    "tag_name": "v2.0.0",
                    "assets": [
                        {
                            "name": "darkos-downloader-2.0.0-r36s-arm64.zip",
                            "browser_download_url": "",
                            "size": 1,
                        }
                    ],
                }
            ).encode(),
            "does not contain",
        ),
    ],
)
def test_find_update_validates_github_payload(
    payload: bytes,
    message: str,
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(updater, "urlopen", lambda *_args, **_kwargs: Response(payload))
    with pytest.raises(UpdateError, match=message):
        find_update("1.0.0", "https://api.test")


def test_find_update_normalizes_unknown_size_and_rejects_large_metadata(
    mocker: MockerFixture,
) -> None:
    asset = {
        "tag_name": "v2.0.0",
        "assets": [
            {
                "name": "darkos-downloader-2.0.0-r36s-arm64.zip",
                "browser_download_url": "https://example.test/bundle",
                "size": True,
            }
        ],
    }
    mocker.patch.object(
        updater, "urlopen", lambda *_args, **_kwargs: Response(json.dumps(asset).encode())
    )
    release = find_update("1.0.0")
    assert release is not None
    assert release.asset_size is None

    mocker.patch.object(updater, "MAX_RELEASE_METADATA_BYTES", 2)
    mocker.patch.object(updater, "urlopen", lambda *_args, **_kwargs: Response(b"{}", "3"))
    with pytest.raises(UpdateError, match="large release metadata"):
        find_update("1.0.0")
    mocker.patch.object(updater, "urlopen", lambda *_args, **_kwargs: Response(b"abc"))
    with pytest.raises(UpdateError, match="large release metadata"):
        find_update("1.0.0")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (HTTPError("url", 403, "forbidden", Message(), None), "HTTP 403"),
        (URLError("offline"), "offline"),
    ],
)
def test_find_update_translates_network_errors(
    error: Exception,
    message: str,
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(updater, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(UpdateError, match=message):
        find_update("1.0.0")


def test_find_update_rejects_large_release_asset(mocker: MockerFixture) -> None:
    payload = {
        "tag_name": "v2.0.0",
        "assets": [
            {
                "name": "darkos-downloader-2.0.0-r36s-arm64.zip",
                "browser_download_url": "https://example.test/bundle",
                "size": 11,
            }
        ],
    }
    mocker.patch.object(updater, "MAX_UPDATE_ARCHIVE_BYTES", 10)
    mocker.patch.object(
        updater, "urlopen", lambda *_args, **_kwargs: Response(json.dumps(payload).encode())
    )
    with pytest.raises(UpdateError, match="unexpectedly large"):
        find_update("1.0.0")


def test_stage_update_requires_packaged_layout_and_translates_os_errors(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    release = ReleaseUpdate("2.0.0", "v2.0.0", "bundle.zip", "url", None)
    with pytest.raises(UpdateError, match="self-contained"):
        stage_update(release, tmp_path / "wrong")
    install = tmp_path / "darkos-downloader"
    install.mkdir()
    (install / "darkos-downloader").write_bytes(b"current")
    mocker.patch.object(updater, "_download_release", lambda *_args: None)
    mocker.patch.object(
        Path, "mkdir", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read only"))
    )
    with pytest.raises(UpdateError, match="read only"):
        stage_update(release, install)


def test_stage_update_cleans_up_unexpected_exceptions(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    install = tmp_path / "tools" / "darkos-downloader"
    install.mkdir(parents=True)
    (install / "darkos-downloader").write_bytes(b"current")
    release = ReleaseUpdate("2.0.0", "v2.0.0", "bundle.zip", "url", None)
    mocker.patch.object(updater, "_download_release", lambda *_args: None)
    mocker.patch.object(
        updater, "_extract_bundle", lambda *_args: (_ for _ in ()).throw(RuntimeError("bug"))
    )
    with pytest.raises(RuntimeError, match="bug"):
        stage_update(release, install)
    assert not (tmp_path / "tools" / ".darkos-downloader-update.incomplete").exists()


def test_download_release_reports_progress_cancellation_size_and_network_errors(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    release = ReleaseUpdate("2.0.0", "v2.0.0", "bundle.zip", "https://example.test/bundle", 4)
    destination = tmp_path / "bundle.part"
    progress: list[tuple[str, int, int | None]] = []
    mocker.patch.object(updater, "urlopen", lambda *_args, **_kwargs: Response(b"data"))
    _download_release(release, destination, 1, lambda *args: progress.append(args), None)
    assert destination.read_bytes() == b"data" and progress[-1] == ("bundle.zip", 4, 4)

    mocker.patch.object(updater, "MAX_UPDATE_ARCHIVE_BYTES", 3)
    mocker.patch.object(updater, "urlopen", lambda *_args, **_kwargs: Response(b"data", "4"))
    with pytest.raises(UpdateError, match="large"):
        _download_release(release, destination, 1, None, None)
    mocker.patch.object(updater, "urlopen", lambda *_args, **_kwargs: Response(b"data"))
    with pytest.raises(UpdateError, match="large"):
        _download_release(
            ReleaseUpdate("2", "v2", "b", "https://example.test/bundle", None),
            destination,
            1,
            None,
            None,
        )

    mocker.patch.object(
        updater,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPError("url", 404, "", Message(), None)),
    )
    with pytest.raises(UpdateError, match="HTTP 404"):
        _download_release(release, destination, 1, None, None)
    mocker.patch.object(
        updater, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline"))
    )
    with pytest.raises(UpdateError, match="offline"):
        _download_release(release, destination, 1, None, None)


def test_extract_bundle_validates_file_limits_and_bad_archives(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    archive = tmp_path / "bundle.zip"
    destination = tmp_path / "expanded"
    destination.mkdir()
    archive.write_bytes(b"not zip")
    with pytest.raises(UpdateError, match="invalid"):
        _extract_bundle(archive, destination, None)

    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("tools/file", b"data")
    mocker.patch.object(updater, "MAX_UPDATE_FILES", 0)
    with pytest.raises(UpdateError, match="too many files"):
        _extract_bundle(archive, destination, None)
    mocker.patch.object(updater, "MAX_UPDATE_FILES", 10)
    mocker.patch.object(updater, "MAX_UPDATE_ARCHIVE_BYTES", 3)
    with pytest.raises(UpdateError, match="expanded"):
        _extract_bundle(archive, destination, None)


def test_safe_bundle_path_rejects_links_and_validate_bundle_errors(tmp_path: Path) -> None:
    item = zipfile.ZipInfo("tools/link")
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(UpdateError, match="Unsafe path"):
        _safe_bundle_path(item)

    destination = tmp_path / "expanded"
    destination.mkdir()
    with pytest.raises(UpdateError, match="launcher"):
        _validate_staged_bundle(destination, "2.0.0")
    (destination / "dArkOS Downloader.sh").write_text("launcher")
    with pytest.raises(UpdateError, match="executable"):
        _validate_staged_bundle(destination, "2.0.0")
    executable = destination / "darkos-downloader" / "darkos-downloader"
    executable.parent.mkdir()
    executable.write_bytes(b"not arm64")
    with pytest.raises(UpdateError, match="not Linux ARM64"):
        _validate_staged_bundle(destination, "2.0.0")


def test_validate_bundle_sets_permissions_and_remove_staging_path(tmp_path: Path) -> None:
    destination = tmp_path / "expanded"
    destination.mkdir()
    launcher = destination / "dArkOS Downloader.sh"
    launcher.write_text("launcher")
    executable = destination / "darkos-downloader" / "darkos-downloader"
    executable.parent.mkdir()
    executable.write_bytes(b"\x7fELF" + bytes((2, 1)) + b"\0" * 12 + (183).to_bytes(2, "little"))
    _validate_staged_bundle(destination, "2.0.0")
    assert (destination / READY_MARKER).read_text() == "2.0.0\n"
    assert executable.stat().st_mode & stat.S_IXUSR

    _remove_staging_path(destination)
    assert not destination.exists()
    file_path = tmp_path / "file"
    file_path.write_text("x")
    _remove_staging_path(file_path)
    assert not file_path.exists()


def test_update_cancel_callback() -> None:
    updater._raise_if_cancelled(None)
    updater._raise_if_cancelled(lambda: False)
    with pytest.raises(UpdateCancelled):
        updater._raise_if_cancelled(lambda: True)
