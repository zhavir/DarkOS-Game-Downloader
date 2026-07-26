import io
from email.message import Message
from pathlib import Path
from types import TracebackType
from urllib.error import HTTPError, URLError

import pytest
from pytest_mock import MockerFixture

from ph.bittorrent import (
    BitTorrentCancelled,
    BitTorrentError,
    BitTorrentSettings,
    TorrentFileChoice,
    TorrentSelectionRequired,
)
from ph.downloader import (
    DownloadCancelled,
    DownloadError,
    DownloadSelectionRequired,
    _download_with_urllib,
    _filename_from_headers,
    _safe_filename,
    _unique_download_path,
    download_files,
)
from ph.models import MediaDownload


class Response(io.BytesIO):
    def __init__(
        self,
        payload: bytes,
        *,
        headers: dict[str, str] | None = None,
        url: str = "https://example.test/file.zip",
    ) -> None:
        super().__init__(payload)
        self.headers = headers or {}
        self.url = url

    def __enter__(self) -> Response:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def geturl(self) -> str:
        return self.url


def test_torrent_download_uses_native_python_client(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    calls: list[tuple[object, ...]] = []

    def native_download(*args: object) -> None:
        calls.append(args)
        destination = args[3]
        assert isinstance(destination, Path)
        destination.write_bytes(b"game")

    mocker.patch("ph.downloader.download_torrent_file", native_download)
    settings = BitTorrentSettings(block_size=32 * 1024, peer_race_workers=4)

    result = download_files(
        [MediaDownload("https://example.test/games.torrent", 7, "Game.zip")],
        tmp_path,
        "https://example.test/",
        bittorrent_settings=settings,
    )

    assert result[0].path == tmp_path / "Game.zip"
    assert result[0].path.read_bytes() == b"game"
    assert calls[0][:3] == ("https://example.test/games.torrent", 7, "Game.zip")
    assert calls[0][-2] == settings
    assert calls[0][-1] is None


def test_cancelled_download_stops_before_network_or_partial_file(tmp_path: Path) -> None:
    with pytest.raises(DownloadCancelled, match="cancelled"):
        download_files(
            [MediaDownload("https://example.test/games.torrent", 7, "Game.zip")],
            tmp_path,
            "https://example.test/",
            cancelled=lambda: True,
        )

    assert not tuple(tmp_path.iterdir())


def test_direct_download_uses_headers_progress_and_unique_names(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    responses = iter(
        (
            Response(
                b"first",
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''Game%20One.zip",
                    "Content-Length": "5",
                },
            ),
            Response(b"second", url="https://example.test/Game%20One.zip"),
        )
    )
    opened = mocker.patch(
        "ph.downloader.urlopen", side_effect=lambda *_args, **_kwargs: next(responses)
    )
    progress: list[tuple[str, int, int | None]] = []

    results = download_files(
        ["https://example.test/one", "https://example.test/two"],
        tmp_path,
        "https://example.test/",
        progress=lambda *args: progress.append(args),
    )

    assert [result.path.name for result in results] == ["Game One.zip", "Game One (2).zip"]
    assert results[0].path.read_bytes() == b"first"
    assert progress == [("Game One.zip", 5, 5), ("Game One.zip", 6, None)]
    assert opened.call_count == 2


def test_download_validates_empty_and_torrent_requests(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    with pytest.raises(DownloadError, match="empty"):
        download_files([], tmp_path, "")
    with pytest.raises(DownloadError, match="expected filename"):
        download_files([MediaDownload("torrent", 1, None)], tmp_path, "")

    native = mocker.patch(
        "ph.downloader.download_torrent_file", side_effect=BitTorrentCancelled("stop")
    )
    with pytest.raises(DownloadCancelled):
        download_files([MediaDownload("torrent", 1, "game.zip")], tmp_path, "")
    native.side_effect = BitTorrentError("bad metadata")
    with pytest.raises(DownloadError, match="bad metadata"):
        download_files([MediaDownload("torrent", 1, "game.zip")], tmp_path, "")

    selection = TorrentSelectionRequired(
        "torrent",
        "game.zip",
        1,
        (TorrentFileChoice(2, ("renamed.zip",), 1024, 0.8),),
        10,
    )
    native.side_effect = selection
    with pytest.raises(DownloadSelectionRequired) as raised:
        download_files([MediaDownload("torrent", 1, "game.zip")], tmp_path, "")
    assert raised.value.candidates == selection.candidates


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (HTTPError("url", 404, "missing", Message(), None), "HTTP 404"),
        (URLError("offline"), "offline"),
    ],
)
def test_direct_download_translates_network_errors(
    tmp_path: Path,
    mocker: MockerFixture,
    error: Exception,
    message: str,
) -> None:
    mocker.patch("ph.downloader.urlopen", side_effect=error)
    with pytest.raises(DownloadError, match=message):
        _download_with_urllib(["https://example.test/file"], tmp_path, "", 1, None, None)


def test_cancelled_direct_download_removes_partial_file(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "ph.downloader.urlopen",
        return_value=Response(b"data", headers={"Content-Length": "4"}),
    )
    checks = iter((False, False, True))
    with pytest.raises(DownloadCancelled):
        _download_with_urllib(
            ["https://example.test/file.zip"],
            tmp_path,
            "",
            1,
            None,
            lambda: next(checks),
        )
    assert not (tmp_path / "file.zip.part").exists()


def test_filename_safety_and_unique_path_variants(tmp_path: Path) -> None:
    assert _safe_filename("../bad:name?.zip") == "bad_name_.zip"
    assert _safe_filename("...") == "download.bin"
    assert _filename_from_headers({}, "https://example.test/") == "download.bin"
    destination = tmp_path / "archive.tar.gz"
    destination.write_bytes(b"one")
    (tmp_path / "archive (2).tar.gz.part").write_bytes(b"partial")
    assert _unique_download_path(destination).name == "archive (3).tar.gz"
    plain = tmp_path / "README"
    plain.write_text("one")
    assert _unique_download_path(plain).name == "README (2)"
