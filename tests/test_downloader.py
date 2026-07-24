from pathlib import Path

import pytest

from dw_cli.downloader import DownloadCancelled, download_files
from dw_cli.models import MediaDownload


def test_torrent_download_uses_native_python_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []

    def native_download(*args: object) -> None:
        calls.append(args)
        destination = args[3]
        assert isinstance(destination, Path)
        destination.write_bytes(b"game")

    monkeypatch.setattr("dw_cli.downloader.download_torrent_file", native_download)

    result = download_files(
        [MediaDownload("https://example.test/games.torrent", 7, "Game.zip")],
        tmp_path,
        "https://example.test/",
    )

    assert result[0].path == tmp_path / "Game.zip"
    assert result[0].path.read_bytes() == b"game"
    assert calls[0][:3] == ("https://example.test/games.torrent", 7, "Game.zip")


def test_cancelled_download_stops_before_network_or_partial_file(tmp_path: Path) -> None:
    with pytest.raises(DownloadCancelled, match="cancelled"):
        download_files(
            [MediaDownload("https://example.test/games.torrent", 7, "Game.zip")],
            tmp_path,
            "https://example.test/",
            cancelled=lambda: True,
        )

    assert not tuple(tmp_path.iterdir())
