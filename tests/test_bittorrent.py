import hashlib
from pathlib import Path
from threading import Lock
from time import sleep

import pytest

from dw_cli.bittorrent import (
    BitTorrentError,
    BValue,
    TorrentMetadata,
    _download_piece_from_peers,
    bdecode,
    bencode,
    discover_peers,
    download_torrent_file,
    parse_torrent,
)


def build_torrent(payload: bytes = b"abcHELLOxyz") -> bytes:
    piece_length = 4
    pieces = b"".join(
        hashlib.sha1(payload[offset : offset + piece_length], usedforsecurity=False).digest()
        for offset in range(0, len(payload), piece_length)
    )
    files: list[BValue] = [
        {b"length": 3, b"path": [b"prefix.bin"]},
        {b"length": 5, b"path": [b"Game.zip"]},
        {b"length": 3, b"path": [b"suffix.bin"]},
    ]
    info: dict[bytes, BValue] = {
        b"name": b"bundle",
        b"piece length": piece_length,
        b"pieces": pieces,
        b"files": files,
    }
    root: dict[bytes, BValue] = {
        b"announce": b"http://tracker.example/announce",
        b"info": info,
    }
    return bencode(root)


def test_bencode_round_trip_and_torrent_file_offsets() -> None:
    encoded = build_torrent()
    assert bencode(bdecode(encoded)) == encoded

    metadata = parse_torrent(encoded)

    assert metadata.piece_length == 4
    assert [file.offset for file in metadata.files] == [0, 3, 8]
    assert metadata.files[1].path == ("Game.zip",)
    assert len(metadata.piece_hashes) == 3


def test_native_selective_download_verifies_pieces_and_extracts_only_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"abcHELLOxyz"
    torrent = build_torrent(payload)
    progress: list[tuple[int, int]] = []
    monkeypatch.setattr("dw_cli.bittorrent._read_url", lambda *_args: torrent)
    monkeypatch.setattr(
        "dw_cli.bittorrent.discover_peers",
        lambda *_args: (("127.0.0.1", 6881),),
    )

    def piece(
        metadata: TorrentMetadata,
        _peer_id: bytes,
        _peers: object,
        piece_index: int,
        piece_length: int,
        _timeout: float,
        _cancelled: object,
    ) -> bytes:
        start = piece_index * metadata.piece_length
        return payload[start : start + piece_length]

    monkeypatch.setattr("dw_cli.bittorrent._download_piece_from_peers", piece)
    destination = tmp_path / "Game.zip"

    download_torrent_file(
        "https://example.test/game.torrent",
        2,
        "Game.zip",
        destination,
        "https://example.test/",
        10,
        lambda current, total: progress.append((current, total)),
    )

    assert destination.read_bytes() == b"HELLO"
    assert progress[0] == (0, 5)
    assert progress[-1] == (5, 5)
    assert not (tmp_path / "prefix.bin").exists()
    assert not (tmp_path / "suffix.bin").exists()
    assert not (tmp_path / "Game.zip.part").exists()


def test_selective_download_rejects_changed_catalogue_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dw_cli.bittorrent._read_url", lambda *_args: build_torrent())

    with pytest.raises(BitTorrentError, match="no longer matches"):
        download_torrent_file(
            "https://example.test/game.torrent",
            2,
            "Different.zip",
            tmp_path / "Different.zip",
            "https://example.test/",
            10,
        )


def test_peer_attempts_are_bounded_and_raced(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = parse_torrent(build_torrent())
    peers = tuple((f"192.0.2.{index}", 6881) for index in range(1, 31))
    attempts: list[tuple[str, int]] = []
    active = 0
    maximum_active = 0
    lock = Lock()

    def peer_download(
        peer: tuple[str, int],
        _info_hash: bytes,
        _peer_id: bytes,
        _piece_index: int,
        _piece_length: int,
        _timeout_seconds: float,
        _completed: object,
        _cancelled: object,
    ) -> bytes:
        nonlocal active, maximum_active
        attempts.append(peer)
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        sleep(0.02)
        with lock:
            active -= 1
        return b"abcH"

    monkeypatch.setattr("dw_cli.bittorrent._download_piece", peer_download)

    data = _download_piece_from_peers(
        metadata,
        b"-DW1000-abcdefghijkl",
        peers,
        0,
        len(b"abcH"),
        30,
    )

    assert data == b"abcH"
    assert 1 < len(attempts) <= 8
    assert maximum_active == 8


def test_peer_discovery_merges_multiple_trackers(monkeypatch: pytest.MonkeyPatch) -> None:
    original = parse_torrent(build_torrent())
    metadata = TorrentMetadata(
        info_hash=original.info_hash,
        piece_length=original.piece_length,
        piece_hashes=original.piece_hashes,
        files=original.files,
        trackers=(
            "http://one.example/announce",
            "http://two.example/announce",
            "http://three.example/announce",
        ),
        total_length=original.total_length,
    )
    responses = {
        "http://one.example/announce": (("1.1.1.1", 6881),),
        "http://two.example/announce": (("8.8.8.8", 6881),),
        "http://three.example/announce": (("1.1.1.1", 6881), ("9.9.9.9", 6881)),
    }
    monkeypatch.setattr(
        "dw_cli.bittorrent._announce_http",
        lambda tracker, *_args: responses[tracker],
    )

    peers = discover_peers(metadata, b"-DW1000-abcdefghijkl", 30)

    assert set(peers) == {
        ("1.1.1.1", 6881),
        ("8.8.8.8", 6881),
        ("9.9.9.9", 6881),
    }
