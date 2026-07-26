import io
import socket
import struct
from email.message import Message
from pathlib import Path
from threading import Event
from types import TracebackType
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from pytest_mock import MockerFixture

from ph import bittorrent
from ph.bittorrent import (
    BitTorrentCancelled,
    BitTorrentError,
    BitTorrentSettings,
    TorrentFile,
    TorrentMetadata,
    _announce_http,
    _announce_udp,
    _as_bytes,
    _as_dictionary,
    _as_list,
    _as_nonnegative_integer,
    _as_positive_integer,
    _decode_path_part,
    _download_piece,
    _download_piece_from_peers,
    _is_usable_peer,
    _parse_compact_peers,
    _parse_tracker_peers,
    _read_exact,
    _read_peer_message,
    _read_url,
    _send_piece_request,
    bdecode,
    bencode,
    compact_peers,
    discover_peers,
    download_torrent_file,
    parse_torrent,
)
from tests.test_bittorrent import build_torrent


class BytesResponse(io.BytesIO):
    def __enter__(self) -> BytesResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


class FakeConnection:
    def __init__(self, chunks: tuple[bytes, ...] = ()) -> None:
        self.chunks = iter(chunks)
        self.sent: list[bytes] = []
        self.timeout: float | None = None

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def sendall(self, value: bytes) -> None:
        self.sent.append(value)

    def recv(self, _length: int) -> bytes:
        return next(self.chunks, b"")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"udp_protocol_id": 0}, "64-bit"),
        ({"udp_protocol_id": 2**64}, "64-bit"),
        ({"block_size": 0}, "Block size"),
        ({"max_peer_timeout_seconds": 0.0}, "timeout"),
        ({"max_peer_timeout_seconds": float("inf")}, "timeout"),
    ],
)
def test_bittorrent_settings_validate_user_values(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        BitTorrentSettings(**cast(Any, kwargs))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "Unexpected end"),
        (b"x", "Invalid bencode marker"),
        (b"i12", "Unterminated"),
        (b"ixye", "Invalid bencode integer"),
        (b"3abc", "byte string"),
        (b"x:abc", "marker"),
        (b"4:abc", "Truncated"),
        (b"l1:a", "Unterminated bencode list"),
        (b"d1:ai1e", "Unterminated bencode dictionary"),
        (b"1:ax", "Trailing data"),
    ],
)
def test_bdecode_rejects_malformed_values(payload: bytes, message: str) -> None:
    with pytest.raises(BitTorrentError, match=message):
        bdecode(payload)


def test_bencode_rejects_unknown_runtime_value() -> None:
    with pytest.raises(BitTorrentError, match="Unsupported"):
        bencode(cast(Any, None))


def torrent_with_info(info: dict[bytes, object], **root_values: object) -> bytes:
    root: dict[bytes, object] = {b"info": info, b"announce": b"https://tracker.test"}
    root.update({key.encode(): value for key, value in root_values.items()})
    return bencode(cast(Any, root))


def test_parse_single_file_and_announce_list() -> None:
    payload = b"data"
    info = {
        b"name": b"game.zip",
        b"length": len(payload),
        b"piece length": 4,
        b"pieces": __import__("hashlib").sha1(payload, usedforsecurity=False).digest(),
    }
    root = {
        b"info": info,
        b"announce-list": [
            [b"udp://tracker.test:80", b"https://tracker.test"],
            b"ftp://ignored.test",
        ],
        b"announce": b"https://tracker.test",
    }
    metadata = parse_torrent(bencode(cast(Any, root)))
    assert metadata.files == (TorrentFile(("game.zip",), 4, 0),)
    assert metadata.trackers == ("udp://tracker.test:80", "https://tracker.test")


@pytest.mark.parametrize(
    ("info", "root_announce", "message"),
    [
        ({b"piece length": 4, b"pieces": b"", b"name": b"x", b"length": 1}, True, "hashes"),
        (
            {b"piece length": 4, b"pieces": b"x" * 20, b"files": [{b"length": 1, b"path": []}]},
            True,
            "unsafe",
        ),
        ({b"piece length": 4, b"pieces": b"x" * 20, b"files": []}, True, "downloadable"),
        (
            {b"piece length": 1, b"pieces": b"x" * 20, b"name": b"x", b"length": 2},
            True,
            "piece count",
        ),
        (
            {b"piece length": 4, b"pieces": b"x" * 20, b"name": b"x", b"length": 1},
            False,
            "supported tracker",
        ),
    ],
)
def test_parse_torrent_rejects_invalid_metadata(
    info: dict[bytes, object],
    root_announce: bool,
    message: str,
) -> None:
    root: dict[bytes, object] = {b"info": info}
    if root_announce:
        root[b"announce"] = b"https://tracker.test"
    with pytest.raises(BitTorrentError, match=message):
        parse_torrent(bencode(cast(Any, root)))


def test_download_torrent_covers_selection_empty_truncation_and_cleanup(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(bittorrent, "_read_url", lambda *_args: build_torrent())
    with pytest.raises(BitTorrentError, match="unambiguous"):
        download_torrent_file("torrent", 99, "file", tmp_path / "file", "", 1)

    empty_info = {
        b"piece length": 1,
        b"pieces": __import__("hashlib").sha1(b"x", usedforsecurity=False).digest(),
        b"files": [{b"length": 0, b"path": [b"empty"]}, {b"length": 1, b"path": [b"x"]}],
    }
    empty_torrent = bencode(cast(Any, {b"announce": b"https://tracker", b"info": empty_info}))
    mocker.patch.object(bittorrent, "_read_url", lambda *_args: empty_torrent)
    empty = tmp_path / "empty"
    download_torrent_file("torrent", 1, "empty", empty, "", 1)
    assert empty.read_bytes() == b""

    mocker.patch.object(bittorrent, "_read_url", lambda *_args: build_torrent())
    mocker.patch.object(bittorrent, "discover_peers", lambda *_args: (("8.8.8.8", 1),))
    mocker.patch.object(bittorrent, "_download_piece_from_peers", lambda *_args: b"")
    destination = tmp_path / "Game.zip"
    with pytest.raises(BitTorrentError, match="truncated"):
        download_torrent_file("torrent", 2, "Game.zip", destination, "", 1)
    assert not destination.with_name("Game.zip.part").exists()


def test_discover_peers_uses_udp_filters_limits_and_reports_empty(
    mocker: MockerFixture,
) -> None:
    original = parse_torrent(build_torrent())
    metadata = TorrentMetadata(
        original.info_hash,
        original.piece_length,
        original.piece_hashes,
        original.files,
        ("udp://tracker.test:80", "https://broken.test", "https://unused.test"),
        original.total_length,
    )
    mocker.patch.object(
        bittorrent,
        "_announce_udp",
        lambda *_args: (("8.8.8.8", 6881), ("127.0.0.1", 1)),
    )
    mocker.patch.object(
        bittorrent,
        "_announce_http",
        lambda *_args: (_ for _ in ()).throw(BitTorrentError("bad tracker")),
    )
    settings = BitTorrentSettings(max_tracker_queries=2, max_discovered_peers=1)
    peers = discover_peers(metadata, b"-DW1000-abcdefghijkl", 30, settings=settings)
    assert peers == (("8.8.8.8", 6881),)

    mocker.patch.object(bittorrent, "_announce_udp", lambda *_args: ())
    with pytest.raises(BitTorrentError, match="No peers"):
        discover_peers(metadata, b"-DW1000-abcdefghijkl", 30, settings=settings)
    with pytest.raises(BitTorrentCancelled):
        discover_peers(metadata, b"-DW1000-abcdefghijkl", 30, cancelled=lambda: True)


def test_http_announce_parses_peers_and_failure(mocker: MockerFixture) -> None:
    metadata = parse_torrent(build_torrent())
    seen: list[str] = []
    mocker.patch.object(
        bittorrent,
        "_read_url",
        lambda url, *_args: (
            seen.append(url) or bencode({b"peers": compact_peers((("8.8.8.8", 80),))})
        ),
    )
    assert _announce_http(
        "https://tracker.test?a=1", metadata, b"x" * 20, 1, BitTorrentSettings()
    ) == (("8.8.8.8", 80),)
    assert "&" in seen[0]
    mocker.patch.object(
        bittorrent, "_read_url", lambda *_args: bencode({b"failure reason": b"closed"})
    )
    with pytest.raises(BitTorrentError, match="closed"):
        _announce_http("https://tracker.test", metadata, b"x" * 20, 1, BitTorrentSettings())


class FakeUdpSocket(FakeConnection):
    def connect(self, _address: object) -> None:
        return None

    def send(self, value: bytes) -> None:
        self.sent.append(value)


def test_udp_announce_protocol_and_validation(mocker: MockerFixture) -> None:
    metadata = parse_torrent(build_torrent())
    transactions = iter((10, 20, 30))
    mocker.patch.object(bittorrent.secrets, "randbits", lambda _bits: next(transactions))
    connect = struct.pack(">IIQ", 0, 10, 99)
    announce = struct.pack(">IIIII", 1, 20, 0, 0, 0) + compact_peers((("8.8.8.8", 80),))
    client = FakeUdpSocket((connect, announce))
    mocker.patch.object(
        socket, "getaddrinfo", lambda *_args: [(None, None, None, None, ("8.8.8.8", 80))]
    )
    mocker.patch.object(socket, "socket", lambda *_args: client)
    assert _announce_udp("udp://tracker.test:80", metadata, b"x" * 20, 1, BitTorrentSettings()) == (
        ("8.8.8.8", 80),
    )
    assert len(client.sent) == 2

    with pytest.raises(BitTorrentError, match="incomplete"):
        _announce_udp("udp://tracker.test", metadata, b"x" * 20, 1, BitTorrentSettings())


@pytest.mark.parametrize(
    ("responses", "message"),
    [
        ((b"short",), "short connect"),
        ((struct.pack(">IIQ", 1, 10, 99),), "connect response"),
        ((struct.pack(">IIQ", 0, 10, 99), b"short"), "short announce"),
        (
            (struct.pack(">IIQ", 0, 10, 99), struct.pack(">IIIII", 0, 20, 0, 0, 0)),
            "announce response",
        ),
    ],
)
def test_udp_announce_rejects_bad_responses(
    responses: tuple[bytes, ...],
    message: str,
    mocker: MockerFixture,
) -> None:
    metadata = parse_torrent(build_torrent())
    transactions = iter((10, 20, 30))
    mocker.patch.object(bittorrent.secrets, "randbits", lambda _bits: next(transactions))
    mocker.patch.object(
        socket, "getaddrinfo", lambda *_args: [(None, None, None, None, ("8.8.8.8", 80))]
    )
    mocker.patch.object(socket, "socket", lambda *_args: FakeUdpSocket(responses))
    with pytest.raises(BitTorrentError, match=message):
        _announce_udp("udp://tracker.test:80", metadata, b"x" * 20, 1, BitTorrentSettings())


def test_peer_parsers_and_validation_helpers() -> None:
    encoded = compact_peers((("8.8.8.8", 80),))
    assert _parse_tracker_peers(encoded) == (("8.8.8.8", 80),)
    assert _parse_compact_peers(encoded + b"x") == ()
    assert _parse_tracker_peers(None) == ()
    assert _parse_tracker_peers(
        [b"bad", {b"ip": b"host", b"port": 0}, {b"ip": b"host", b"port": 80}]
    ) == (("host", 80),)
    assert _is_usable_peer(("8.8.8.8", 80)) is True
    assert _is_usable_peer(("127.0.0.1", 80)) is False
    assert _is_usable_peer(("hostname", 80)) is True
    assert _is_usable_peer(("", 80)) is False

    validators = (
        (_as_dictionary, b"x"),
        (_as_list, b"x"),
        (_as_bytes, 1),
        (_as_positive_integer, 0),
        (_as_nonnegative_integer, -1),
    )
    for validator, value in validators:
        with pytest.raises(BitTorrentError, match="Invalid"):
            validator(value, "value")  # type: ignore[arg-type]
    with pytest.raises(BitTorrentError, match="unsafe"):
        _decode_path_part(b"../bad")


def test_piece_race_reports_failures_hash_mismatch_and_cancellation(
    mocker: MockerFixture,
) -> None:
    metadata = parse_torrent(build_torrent())
    peers = (("8.8.8.8", 1),)
    mocker.patch.object(
        bittorrent, "_download_piece", lambda *_args: (_ for _ in ()).throw(OSError("down"))
    )
    with pytest.raises(BitTorrentError, match="Could not retrieve"):
        _download_piece_from_peers(metadata, b"x" * 20, peers, 0, 4, 1)
    mocker.patch.object(bittorrent, "_download_piece", lambda *_args: b"wrong")
    with pytest.raises(BitTorrentError, match="Could not retrieve"):
        _download_piece_from_peers(metadata, b"x" * 20, peers, 0, 4, 1)
    with pytest.raises(BitTorrentCancelled):
        _download_piece_from_peers(metadata, b"x" * 20, peers, 0, 4, 1, cancelled=lambda: True)


def handshake(info_hash: bytes) -> bytes:
    return bytes((19,)) + b"BitTorrent protocol" + b"\0" * 8 + info_hash + b"p" * 20


def test_download_piece_exchanges_handshake_and_blocks(mocker: MockerFixture) -> None:
    info_hash = b"i" * 20
    connection = FakeConnection()
    mocker.patch.object(socket, "create_connection", lambda *_args, **_kwargs: connection)
    exact = iter((handshake(info_hash),))
    mocker.patch.object(bittorrent, "_read_exact", lambda *_args: next(exact))
    messages = iter(
        (
            (5, b"\x80"),
            (4, struct.pack(">I", 0)),
            (1, b""),
            (None, b""),
            (7, struct.pack(">II", 99, 0) + b"xxxx"),
            (7, struct.pack(">II", 0, 0) + b"abcd"),
            (7, struct.pack(">II", 0, 4) + b"ef"),
        )
    )
    mocker.patch.object(bittorrent, "_read_peer_message", lambda *_args: next(messages))
    result = _download_piece(
        ("8.8.8.8", 80),
        info_hash,
        b"p" * 20,
        0,
        6,
        1,
        settings=BitTorrentSettings(block_size=4),
    )
    assert result == b"abcdef"
    assert connection.timeout == 1
    assert len(connection.sent) >= 4


@pytest.mark.parametrize(
    ("handshake_value", "messages", "completed", "message"),
    [
        (b"x" * 68, (), False, "invalid handshake"),
        (None, (), True, "Another peer"),
        (None, ((5, b"\x00"), (1, b"")), False, "does not have"),
        (None, ((1, b""), (0, b"")), False, "choked"),
        (None, ((1, b""), (7, struct.pack(">II", 0, 0) + b"x")), False, "invalid piece block"),
    ],
)
def test_download_piece_rejects_peer_protocol_errors(
    mocker: MockerFixture,
    handshake_value: bytes | None,
    messages: tuple[tuple[int | None, bytes], ...],
    completed: bool,
    message: str,
) -> None:
    info_hash = b"i" * 20
    connection = FakeConnection()
    mocker.patch.object(socket, "create_connection", lambda *_args, **_kwargs: connection)
    mocker.patch.object(
        bittorrent, "_read_exact", lambda *_args: handshake_value or handshake(info_hash)
    )
    message_values = iter(messages)
    mocker.patch.object(bittorrent, "_read_peer_message", lambda *_args: next(message_values))
    complete_event = Event()
    if completed:
        complete_event.set()
    with pytest.raises(BitTorrentError, match=message):
        _download_piece(("8.8.8.8", 80), info_hash, b"p" * 20, 0, 4, 1, complete_event)


def test_peer_wire_helpers() -> None:
    connection = FakeConnection((b"ab", b"cd"))
    assert _read_exact(cast(socket.socket, connection), 4) == b"abcd"
    with pytest.raises(BitTorrentError, match="closed"):
        _read_exact(cast(socket.socket, FakeConnection(())), 1)
    keepalive = FakeConnection((struct.pack(">I", 0),))
    assert _read_peer_message(cast(socket.socket, keepalive)) == (None, b"")
    huge = FakeConnection((struct.pack(">I", 1000),))
    with pytest.raises(BitTorrentError, match="large"):
        _read_peer_message(cast(socket.socket, huge), 4)
    message = FakeConnection((struct.pack(">I", 3), b"\x07ok"))
    assert _read_peer_message(cast(socket.socket, message)) == (7, b"ok")
    sent = FakeConnection()
    _send_piece_request(cast(socket.socket, sent), 1, 2, 3)
    assert sent.sent == [struct.pack(">IBIII", 13, 6, 1, 2, 3)]


def test_read_url_headers_limits_and_errors(mocker: MockerFixture) -> None:
    requests: list[Request] = []

    def opened(request: Request, **_kwargs: object) -> BytesResponse:
        requests.append(request)
        return BytesResponse(b"data")

    mocker.patch.object(bittorrent, "urlopen", opened)
    assert _read_url("https://example.test", "https://referrer.test", 1, 4) == b"data"
    assert requests[0].get_header("Referer") == "https://referrer.test"
    mocker.patch.object(bittorrent, "urlopen", lambda *_args, **_kwargs: BytesResponse(b"large"))
    with pytest.raises(BitTorrentError, match="safe size"):
        _read_url("https://example.test", "", 1, 4)
    error = HTTPError("url", 403, "forbidden", Message(), None)
    mocker.patch.object(
        bittorrent, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error)
    )
    with pytest.raises(BitTorrentError, match="403"):
        _read_url("https://example.test", "", 1, 4)
    mocker.patch.object(
        bittorrent, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline"))
    )
    with pytest.raises(BitTorrentError, match="offline"):
        _read_url("https://example.test", "", 1, 4)


def test_explicit_cancellation_helper() -> None:
    bittorrent._raise_if_cancelled(None)
    bittorrent._raise_if_cancelled(lambda: False)
    with pytest.raises(BitTorrentCancelled):
        bittorrent._raise_if_cancelled(lambda: True)
