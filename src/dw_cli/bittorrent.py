"""Small standard-library BitTorrent v1 client for selective Minerva downloads."""

import hashlib
import ipaddress
import secrets
import socket
import ssl
import struct
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from dw_cli.store import USER_AGENT

type BValue = bytes | int | list[BValue] | dict[bytes, BValue]
type PeerAddress = tuple[str, int]
type TorrentProgress = Callable[[int, int], None]
type CancelCallback = Callable[[], bool]

_PROTOCOL = b"BitTorrent protocol"
_UDP_PROTOCOL_ID = 0x41727101980
_BLOCK_SIZE = 16 * 1024
_MAX_TORRENT_BYTES = 16 * 1024 * 1024
_MAX_TRACKER_BYTES = 2 * 1024 * 1024
_MAX_PEER_ATTEMPTS = 240
_PEER_RACE_WORKERS = 8
_MAX_PEER_TIMEOUT_SECONDS = 8.0
_MAX_TRACKER_QUERIES = 16
_MAX_DISCOVERED_PEERS = 240


class BitTorrentError(RuntimeError):
    """Torrent metadata, tracker discovery, or peer transfer failed."""


class BitTorrentCancelled(BitTorrentError):
    """The caller requested cancellation of a torrent transfer."""


class _BDecoder:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    def decode(self) -> BValue:
        if self.position >= len(self.data):
            raise BitTorrentError("Unexpected end of bencoded data.")
        marker = self.data[self.position]
        if marker == ord("i"):
            return self._integer()
        if marker == ord("l"):
            return self._list()
        if marker == ord("d"):
            return self._dictionary()
        if ord("0") <= marker <= ord("9"):
            return self._bytes()
        raise BitTorrentError("Invalid bencode marker.")

    def _integer(self) -> int:
        self.position += 1
        end = self.data.find(b"e", self.position)
        if end < 0:
            raise BitTorrentError("Unterminated bencode integer.")
        raw = self.data[self.position : end]
        self.position = end + 1
        try:
            return int(raw)
        except ValueError as error:
            raise BitTorrentError("Invalid bencode integer.") from error

    def _bytes(self) -> bytes:
        separator = self.data.find(b":", self.position)
        if separator < 0:
            raise BitTorrentError("Invalid bencode byte string.")
        try:
            length = int(self.data[self.position : separator])
        except ValueError as error:
            raise BitTorrentError("Invalid bencode byte-string length.") from error
        self.position = separator + 1
        end = self.position + length
        if length < 0 or end > len(self.data):
            raise BitTorrentError("Truncated bencode byte string.")
        value = self.data[self.position : end]
        self.position = end
        return value

    def _list(self) -> list[BValue]:
        self.position += 1
        values: list[BValue] = []
        while self.position < len(self.data) and self.data[self.position] != ord("e"):
            values.append(self.decode())
        if self.position >= len(self.data):
            raise BitTorrentError("Unterminated bencode list.")
        self.position += 1
        return values

    def _dictionary(self) -> dict[bytes, BValue]:
        self.position += 1
        values: dict[bytes, BValue] = {}
        while self.position < len(self.data) and self.data[self.position] != ord("e"):
            key = self._bytes()
            values[key] = self.decode()
        if self.position >= len(self.data):
            raise BitTorrentError("Unterminated bencode dictionary.")
        self.position += 1
        return values


def bdecode(data: bytes) -> BValue:
    """Decode one complete bencoded value."""

    decoder = _BDecoder(data)
    value = decoder.decode()
    if decoder.position != len(data):
        raise BitTorrentError("Trailing data after bencoded value.")
    return value


def bencode(value: BValue) -> bytes:
    """Encode a value canonically so an info dictionary keeps its v1 hash."""

    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        return (
            b"d"
            + b"".join(bencode(key) + bencode(item) for key, item in sorted(value.items()))
            + b"e"
        )
    raise BitTorrentError("Unsupported bencode value.")


@dataclass(frozen=True, slots=True)
class TorrentFile:
    path: tuple[str, ...]
    length: int
    offset: int


@dataclass(frozen=True, slots=True)
class TorrentMetadata:
    info_hash: bytes
    piece_length: int
    piece_hashes: tuple[bytes, ...]
    files: tuple[TorrentFile, ...]
    trackers: tuple[str, ...]
    total_length: int


def parse_torrent(data: bytes) -> TorrentMetadata:
    """Parse and validate the v1 fields needed for a selective file download."""

    root = _as_dictionary(bdecode(data), "torrent root")
    info = _as_dictionary(root.get(b"info"), "torrent info")
    piece_length = _as_positive_integer(info.get(b"piece length"), "piece length")
    pieces = _as_bytes(info.get(b"pieces"), "piece hashes")
    if not pieces or len(pieces) % 20:
        raise BitTorrentError("Torrent piece hashes are malformed.")

    files: list[TorrentFile] = []
    offset = 0
    raw_files = info.get(b"files")
    if isinstance(raw_files, list):
        for raw_file in raw_files:
            file_info = _as_dictionary(raw_file, "torrent file")
            length = _as_nonnegative_integer(file_info.get(b"length"), "file length")
            raw_path = _as_list(file_info.get(b"path"), "file path")
            path = tuple(_decode_path_part(part) for part in raw_path)
            if not path or any(part in ("", ".", "..") for part in path):
                raise BitTorrentError("Torrent contains an unsafe file path.")
            files.append(TorrentFile(path, length, offset))
            offset += length
    else:
        length = _as_nonnegative_integer(info.get(b"length"), "file length")
        name = _decode_path_part(info.get(b"name"))
        files.append(TorrentFile((name,), length, 0))
        offset = length
    if not files or offset <= 0:
        raise BitTorrentError("Torrent does not contain downloadable files.")

    expected_piece_count = (offset + piece_length - 1) // piece_length
    if len(pieces) // 20 != expected_piece_count:
        raise BitTorrentError("Torrent piece count does not match its files.")

    trackers: list[str] = []
    announce_list = root.get(b"announce-list")
    if isinstance(announce_list, list):
        for tier in announce_list:
            values = tier if isinstance(tier, list) else [tier]
            for value in values:
                if isinstance(value, bytes):
                    trackers.append(value.decode("utf-8", errors="replace"))
    announce = root.get(b"announce")
    if isinstance(announce, bytes):
        trackers.append(announce.decode("utf-8", errors="replace"))
    trackers = list(
        dict.fromkeys(url for url in trackers if urlparse(url).scheme in ("http", "https", "udp"))
    )
    if not trackers:
        raise BitTorrentError("Torrent does not advertise a supported tracker.")

    return TorrentMetadata(
        info_hash=hashlib.sha1(bencode(info), usedforsecurity=False).digest(),
        piece_length=piece_length,
        piece_hashes=tuple(pieces[index : index + 20] for index in range(0, len(pieces), 20)),
        files=tuple(files),
        trackers=tuple(trackers),
        total_length=offset,
    )


def download_torrent_file(
    torrent_url: str,
    file_index: int,
    expected_filename: str,
    destination: Path,
    referer: str,
    timeout_seconds: float,
    progress: TorrentProgress | None = None,
    cancelled: CancelCallback | None = None,
) -> None:
    """Download and verify only one one-based file from a v1 multi-file torrent."""

    _raise_if_cancelled(cancelled)
    torrent_data = _read_url(
        torrent_url,
        referer,
        timeout_seconds,
        _MAX_TORRENT_BYTES,
    )
    _raise_if_cancelled(cancelled)
    metadata = parse_torrent(torrent_data)
    if file_index < 1 or file_index > len(metadata.files):
        raise BitTorrentError("Selected torrent file index is out of range.")
    selected = metadata.files[file_index - 1]
    if selected.path[-1] != expected_filename:
        raise BitTorrentError("The selected torrent file no longer matches the catalogue.")
    if selected.length == 0:
        destination.write_bytes(b"")
        return
    if progress is not None:
        progress(0, selected.length)

    peer_id = b"-DW1000-" + secrets.token_bytes(12)
    peers = discover_peers(metadata, peer_id, timeout_seconds, cancelled)
    start_piece = selected.offset // metadata.piece_length
    end_piece = (selected.offset + selected.length - 1) // metadata.piece_length
    piece_indices = tuple(range(start_piece, end_piece + 1))

    def fetch_piece(piece_index: int) -> tuple[int, bytes]:
        _raise_if_cancelled(cancelled)
        length = min(
            metadata.piece_length,
            metadata.total_length - piece_index * metadata.piece_length,
        )
        data = _download_piece_from_peers(
            metadata,
            peer_id,
            peers,
            piece_index,
            length,
            timeout_seconds,
            cancelled,
        )
        return piece_index, data

    partial = destination.with_name(destination.name + ".part")
    written = 0
    try:
        with partial.open("wb") as output:
            selected_end = selected.offset + selected.length
            with ThreadPoolExecutor(
                max_workers=min(4, len(piece_indices)),
                thread_name_prefix="torrent-piece",
            ) as executor:
                for piece_index, data in executor.map(
                    fetch_piece,
                    piece_indices,
                    buffersize=4,
                ):
                    _raise_if_cancelled(cancelled)
                    piece_start = piece_index * metadata.piece_length
                    piece_end = piece_start + len(data)
                    copy_start = max(selected.offset, piece_start) - piece_start
                    copy_end = min(selected_end, piece_end) - piece_start
                    block = data[copy_start:copy_end]
                    output.write(block)
                    written += len(block)
                    if progress is not None:
                        progress(written, selected.length)
        if written != selected.length:
            raise BitTorrentError("The selected torrent file was truncated.")
        partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def discover_peers(
    metadata: TorrentMetadata,
    peer_id: bytes,
    timeout_seconds: float,
    cancelled: CancelCallback | None = None,
) -> tuple[PeerAddress, ...]:
    """Merge several tracker responses so one stale swarm view cannot block a download."""

    per_tracker_timeout = max(3.0, min(10.0, timeout_seconds / 3))
    trackers = metadata.trackers[:_MAX_TRACKER_QUERIES]

    def announce(tracker: str) -> tuple[PeerAddress, ...]:
        _raise_if_cancelled(cancelled)
        try:
            peers = (
                _announce_udp(tracker, metadata, peer_id, per_tracker_timeout)
                if tracker.startswith("udp://")
                else _announce_http(tracker, metadata, peer_id, per_tracker_timeout)
            )
            _raise_if_cancelled(cancelled)
            return peers
        except BitTorrentCancelled:
            raise
        except BitTorrentError, OSError, TimeoutError, ValueError:
            return ()

    peers: list[PeerAddress] = []
    with ThreadPoolExecutor(
        max_workers=min(8, len(trackers)),
        thread_name_prefix="torrent-tracker",
    ) as executor:
        for discovered in executor.map(announce, trackers):
            _raise_if_cancelled(cancelled)
            peers.extend(discovered)
    peers = list(dict.fromkeys(peer for peer in peers if _is_usable_peer(peer)))
    if not peers:
        raise BitTorrentError("No peers were returned by Minerva's torrent trackers.")
    peers.sort(
        key=lambda peer: hashlib.sha256(
            peer_id + f"{peer[0]}:{peer[1]}".encode(),
        ).digest()
    )
    return tuple(peers[:_MAX_DISCOVERED_PEERS])


def _announce_http(
    tracker: str,
    metadata: TorrentMetadata,
    peer_id: bytes,
    timeout_seconds: float,
) -> tuple[PeerAddress, ...]:
    parameters = urlencode(
        {
            "info_hash": metadata.info_hash,
            "peer_id": peer_id,
            "port": 6881,
            "uploaded": 0,
            "downloaded": 0,
            "left": metadata.total_length,
            "compact": 1,
            "numwant": 80,
        }
    )
    separator = "&" if "?" in tracker else "?"
    response = _read_url(
        f"{tracker}{separator}{parameters}",
        "",
        timeout_seconds,
        _MAX_TRACKER_BYTES,
    )
    payload = _as_dictionary(bdecode(response), "tracker response")
    failure = payload.get(b"failure reason")
    if isinstance(failure, bytes):
        raise BitTorrentError(f"Tracker rejected the announce: {failure.decode(errors='replace')}")
    return _parse_tracker_peers(payload.get(b"peers"))


def _announce_udp(
    tracker: str,
    metadata: TorrentMetadata,
    peer_id: bytes,
    timeout_seconds: float,
) -> tuple[PeerAddress, ...]:
    parsed = urlparse(tracker)
    if not parsed.hostname or not parsed.port:
        raise BitTorrentError("UDP tracker URL is incomplete.")
    address = socket.getaddrinfo(
        parsed.hostname,
        parsed.port,
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )[0][4]
    transaction = secrets.randbits(32)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(timeout_seconds)
        client.connect(address)
        client.send(struct.pack(">QII", _UDP_PROTOCOL_ID, 0, transaction))
        response = client.recv(2048)
        if len(response) < 16:
            raise BitTorrentError("UDP tracker returned a short connect response.")
        action, response_transaction, connection_id = struct.unpack(">IIQ", response[:16])
        if action != 0 or response_transaction != transaction:
            raise BitTorrentError("UDP tracker connect response did not match.")

        transaction = secrets.randbits(32)
        packet = struct.pack(
            ">QII20s20sQQQIIIiH",
            connection_id,
            1,
            transaction,
            metadata.info_hash,
            peer_id,
            0,
            metadata.total_length,
            0,
            0,
            0,
            secrets.randbits(32),
            80,
            6881,
        )
        client.send(packet)
        response = client.recv(65535)
    if len(response) < 20:
        raise BitTorrentError("UDP tracker returned a short announce response.")
    action, response_transaction = struct.unpack(">II", response[:8])
    if action != 1 or response_transaction != transaction:
        raise BitTorrentError("UDP tracker announce response did not match.")
    return _parse_compact_peers(response[20:])


def _parse_tracker_peers(value: BValue | None) -> tuple[PeerAddress, ...]:
    if isinstance(value, bytes):
        return _parse_compact_peers(value)
    if not isinstance(value, list):
        return ()
    peers: list[PeerAddress] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        address = item.get(b"ip")
        port = item.get(b"port")
        if isinstance(address, bytes) and isinstance(port, int) and 0 < port < 65536:
            peers.append((address.decode(errors="replace"), port))
    return tuple(peers)


def _parse_compact_peers(data: bytes) -> tuple[PeerAddress, ...]:
    if len(data) % 6:
        return ()
    return tuple(
        (
            socket.inet_ntoa(data[index : index + 4]),
            struct.unpack(">H", data[index + 4 : index + 6])[0],
        )
        for index in range(0, len(data), 6)
    )


def _download_piece_from_peers(
    metadata: TorrentMetadata,
    peer_id: bytes,
    peers: tuple[PeerAddress, ...],
    piece_index: int,
    piece_length: int,
    timeout_seconds: float,
    cancelled: CancelCallback | None = None,
) -> bytes:
    start = int.from_bytes(peer_id[-4:], "big") + piece_index
    attempts = min(_MAX_PEER_ATTEMPTS, len(peers))
    candidates = tuple(peers[(start + attempt) % len(peers)] for attempt in range(attempts))
    peer_timeout = max(3.0, min(_MAX_PEER_TIMEOUT_SECONDS, timeout_seconds))
    completed = Event()

    def fetch(peer: PeerAddress) -> bytes | None:
        _raise_if_cancelled(cancelled)
        if completed.is_set():
            return None
        try:
            data = _download_piece(
                peer,
                metadata.info_hash,
                peer_id,
                piece_index,
                piece_length,
                peer_timeout,
                completed,
                cancelled,
            )
        except BitTorrentCancelled:
            raise
        except BitTorrentError, OSError, TimeoutError:
            return None
        digest = hashlib.sha1(data, usedforsecurity=False).digest()
        if digest == metadata.piece_hashes[piece_index]:
            completed.set()
            return data
        return None

    executor = ThreadPoolExecutor(
        max_workers=min(_PEER_RACE_WORKERS, len(candidates)),
        thread_name_prefix="torrent-peer",
    )
    futures = [executor.submit(fetch, peer) for peer in candidates]
    try:
        for future in as_completed(futures):
            _raise_if_cancelled(cancelled)
            data = future.result()
            if data is None:
                continue
            for pending in futures:
                pending.cancel()
            return data
    finally:
        for pending in futures:
            pending.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    raise BitTorrentError(f"Could not retrieve verified torrent piece {piece_index}.")


def _download_piece(
    peer: PeerAddress,
    info_hash: bytes,
    peer_id: bytes,
    piece_index: int,
    piece_length: int,
    timeout_seconds: float,
    completed: Event | None = None,
    cancelled: CancelCallback | None = None,
) -> bytes:
    _raise_if_cancelled(cancelled)
    with socket.create_connection(peer, timeout=timeout_seconds) as connection:
        connection.settimeout(timeout_seconds)
        connection.sendall(bytes((len(_PROTOCOL),)) + _PROTOCOL + b"\0" * 8 + info_hash + peer_id)
        handshake = _read_exact(connection, 68)
        if handshake[1:20] != _PROTOCOL or handshake[28:48] != info_hash:
            raise BitTorrentError("Peer returned an invalid handshake.")
        connection.sendall(struct.pack(">IB", 1, 2))

        available: bytes | None = None
        unchoked = False
        deadline = time.monotonic() + timeout_seconds
        while not unchoked and time.monotonic() < deadline:
            _raise_if_cancelled(cancelled)
            if completed is not None and completed.is_set():
                raise BitTorrentError("Another peer completed the requested piece.")
            message_id, payload = _read_peer_message(connection)
            if message_id == 1:
                unchoked = True
            elif message_id == 5:
                available = payload
            elif message_id == 4 and len(payload) == 4:
                announced = struct.unpack(">I", payload)[0]
                if announced == piece_index:
                    available = None
        if not unchoked:
            raise BitTorrentError("Peer did not unchoke the download.")
        if available is not None:
            byte_index, bit_index = divmod(piece_index, 8)
            if byte_index >= len(available) or not available[byte_index] & (1 << (7 - bit_index)):
                raise BitTorrentError("Peer does not have the requested piece.")

        requests = [
            (begin, min(_BLOCK_SIZE, piece_length - begin))
            for begin in range(0, piece_length, _BLOCK_SIZE)
        ]
        pending = iter(requests)
        received: dict[int, bytes] = {}
        in_flight = 0
        for _ in range(min(16, len(requests))):
            begin, length = next(pending)
            _send_piece_request(connection, piece_index, begin, length)
            in_flight += 1
        while in_flight:
            _raise_if_cancelled(cancelled)
            if completed is not None and completed.is_set():
                raise BitTorrentError("Another peer completed the requested piece.")
            message_id, payload = _read_peer_message(connection)
            if message_id == 0:
                raise BitTorrentError("Peer choked the download.")
            if message_id != 7 or len(payload) < 8:
                continue
            response_piece, begin = struct.unpack(">II", payload[:8])
            block = payload[8:]
            if response_piece != piece_index or begin in received:
                continue
            expected = dict(requests).get(begin)
            if expected != len(block):
                raise BitTorrentError("Peer returned an invalid piece block.")
            received[begin] = block
            in_flight -= 1
            try:
                next_begin, next_length = next(pending)
            except StopIteration:
                continue
            _send_piece_request(connection, piece_index, next_begin, next_length)
            in_flight += 1
        return b"".join(received[begin] for begin, _length in requests)


def _send_piece_request(
    connection: socket.socket,
    piece_index: int,
    begin: int,
    length: int,
) -> None:
    connection.sendall(struct.pack(">IBIII", 13, 6, piece_index, begin, length))


def _read_peer_message(connection: socket.socket) -> tuple[int | None, bytes]:
    length = struct.unpack(">I", _read_exact(connection, 4))[0]
    if length == 0:
        return None, b""
    if length > _BLOCK_SIZE + 64:
        raise BitTorrentError("Peer message is unexpectedly large.")
    message = _read_exact(connection, length)
    return message[0], message[1:]


def _read_exact(connection: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise BitTorrentError("Peer closed the connection early.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_url(url: str, referer: str, timeout_seconds: float, limit: int) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as response:
            data = response.read(limit + 1)
    except HTTPError as error:
        raise BitTorrentError("Torrent service returned HTTP %d." % error.code) from error
    except (URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise BitTorrentError(f"Could not reach the torrent service: {reason}") from error
    if len(data) > limit:
        raise BitTorrentError("Torrent service response exceeded the safe size limit.")
    return data


def _as_dictionary(value: BValue | None, label: str) -> dict[bytes, BValue]:
    if not isinstance(value, dict):
        raise BitTorrentError(f"Invalid {label}.")
    return value


def _as_list(value: BValue | None, label: str) -> list[BValue]:
    if not isinstance(value, list):
        raise BitTorrentError(f"Invalid {label}.")
    return value


def _as_bytes(value: BValue | None, label: str) -> bytes:
    if not isinstance(value, bytes):
        raise BitTorrentError(f"Invalid {label}.")
    return value


def _as_positive_integer(value: BValue | None, label: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise BitTorrentError(f"Invalid {label}.")
    return value


def _as_nonnegative_integer(value: BValue | None, label: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise BitTorrentError(f"Invalid {label}.")
    return value


def _decode_path_part(value: BValue | None) -> str:
    raw = _as_bytes(value, "file path")
    decoded = raw.decode("utf-8", errors="replace")
    if "/" in decoded or "\\" in decoded:
        raise BitTorrentError("Torrent contains an unsafe file path.")
    return decoded


def compact_peers(peers: Iterable[PeerAddress]) -> bytes:
    """Encode IPv4 peers for deterministic tracker tests."""

    return b"".join(socket.inet_aton(address) + struct.pack(">H", port) for address, port in peers)


def _is_usable_peer(peer: PeerAddress) -> bool:
    try:
        address = ipaddress.ip_address(peer[0])
    except ValueError:
        return bool(peer[0])
    return address.is_global


def _raise_if_cancelled(cancelled: CancelCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise BitTorrentCancelled("Torrent download cancelled.")
