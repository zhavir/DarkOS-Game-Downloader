"""End-to-end coverage for parallel native Minerva torrent downloads."""

import hashlib
import struct
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import socket
from socketserver import BaseRequestHandler, ThreadingTCPServer
from urllib.parse import quote

import pytest

from ph.bittorrent import BValue, bencode
from ph.download_queue import DownloadQueue, DownloadState
from ph.minerva_store import MinervaStore
from ph.platforms import resolve_platform

_PROTOCOL = b"BitTorrent protocol"
_DIRECTORY = "RA - Arduboy"
_FILES = {
    "First Game.zip": b"first-game-rom-" * 8,
    "Second Game.zip": b"second-game-rom" * 8,
}
_PIECE_LENGTH = 16


class _SingleConnectionPeer(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, payload: bytes, info_hash: bytes) -> None:
        self.payload = payload
        self.info_hash = info_hash
        self.peer_id = b"-PH-E2E0-LOCAL-PEER1"
        self.active = False
        self.rejected_connections = 0
        self.activity_lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), _PeerHandler)


class _PeerHandler(BaseRequestHandler):
    server: _SingleConnectionPeer
    request: socket

    def handle(self) -> None:
        with self.server.activity_lock:
            if self.server.active:
                self.server.rejected_connections += 1
                return
            self.server.active = True
        try:
            try:
                time.sleep(0.03)
                handshake = _read_exact(self.request, 68)
                if handshake[28:48] != self.server.info_hash:
                    return
                self.request.sendall(
                    bytes((len(_PROTOCOL),))
                    + _PROTOCOL
                    + b"\0" * 8
                    + self.server.info_hash
                    + self.server.peer_id
                )
                _read_exact(self.request, 5)  # interested
                self.request.sendall(struct.pack(">IB", 1, 1))  # unchoke
                request = _read_exact(self.request, 17)
                _length, message_id, piece_index, begin, length = struct.unpack(">IBIII", request)
                if message_id != 6:
                    return
                piece_start = piece_index * _PIECE_LENGTH + begin
                block = self.server.payload[piece_start : piece_start + length]
                self.request.sendall(
                    struct.pack(">IBII", 9 + len(block), 7, piece_index, begin) + block
                )
            except ConnectionError:
                return
        finally:
            with self.server.activity_lock:
                self.server.active = False


def _read_exact(connection: socket, length: int) -> bytes:
    data = b""
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            raise ConnectionError("peer closed the test connection")
        data += chunk
    return data


def _torrent_info() -> tuple[dict[bytes, BValue], bytes, bytes]:
    payload = b"".join(_FILES.values())
    pieces = b"".join(
        hashlib.sha1(payload[offset : offset + _PIECE_LENGTH], usedforsecurity=False).digest()
        for offset in range(0, len(payload), _PIECE_LENGTH)
    )
    files: list[BValue] = [
        {b"length": len(content), b"path": [filename.encode()]}
        for filename, content in _FILES.items()
    ]
    info: dict[bytes, BValue] = {
        b"name": b"parallel-minerva",
        b"piece length": _PIECE_LENGTH,
        b"pieces": pieces,
        b"files": files,
    }
    info_hash = hashlib.sha1(bencode(info), usedforsecurity=False).digest()
    return info, payload, info_hash


class _MinervaHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, torrent: bytes, peer_port: int) -> None:
        self.torrent = torrent
        self.peer_port = peer_port
        super().__init__(("127.0.0.1", 0), _MinervaHandler)


class _MinervaHandler(BaseHTTPRequestHandler):
    server: _MinervaHttpServer

    def do_GET(self) -> None:
        if self.path.startswith("/announce?"):
            self._respond(
                bencode(
                    {
                        b"peers": [
                            {b"ip": b"localhost", b"port": self.server.peer_port},
                        ],
                    }
                ),
                "text/plain",
            )
            return
        if self.path.endswith(".torrent"):
            self._respond(self.server.torrent, "application/x-bittorrent")
            return
        if self.path.startswith("/browse/RetroAchievements/"):
            entries = "".join(
                '<div class="entry"><a href="/rom?name={}">{}</a></div>'.format(
                    quote(f"RetroAchievements/{_DIRECTORY}/{filename}").replace("%2F", "/"),
                    filename,
                )
                for filename in _FILES
            )
            self._respond(entries.encode(), "text/html")
            return
        self.send_error(404)

    def _respond(self, payload: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _local_minerva() -> Iterator[tuple[str, _SingleConnectionPeer]]:
    info, payload, info_hash = _torrent_info()
    peer = _SingleConnectionPeer(payload, info_hash)
    peer_port = int(peer.server_address[1])
    http = _MinervaHttpServer(b"", peer_port)
    http_port = int(http.server_address[1])
    tracker = f"http://127.0.0.1:{http_port}/announce".encode()
    http.torrent = bencode({b"announce": tracker, b"info": info})
    threads = (
        threading.Thread(target=peer.serve_forever, daemon=True),
        threading.Thread(target=http.serve_forever, daemon=True),
    )
    for thread in threads:
        thread.start()
    try:
        yield f"http://127.0.0.1:{http_port}", peer
    finally:
        peer.shutdown()
        http.shutdown()
        peer.server_close()
        http.server_close()
        for thread in threads:
            thread.join(timeout=5)


def _wait_for_completion(queue: DownloadQueue, job_ids: set[str]) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        jobs = {job.job_id: job for job in queue.jobs()}
        if all(jobs[job_id].state is DownloadState.COMPLETED for job_id in job_ids):
            return
        if any(jobs[job_id].state is DownloadState.FAILED for job_id in job_ids):
            failures = {job_id: jobs[job_id].error for job_id in job_ids}
            raise AssertionError(f"parallel Minerva download failed: {failures}")
        time.sleep(0.02)
    raise AssertionError("parallel Minerva downloads did not finish")


@pytest.mark.e2e
@pytest.mark.integration
def test_parallel_minerva_downloads_share_peer_capacity(tmp_path: Path) -> None:
    with _local_minerva() as (base_url, peer):
        store = MinervaStore(base_url, base_url, timeout_seconds=2)
        results = store.search(_DIRECTORY, "")
        assert [result.title for result in results] == ["First Game", "Second Game"]

        platform = resolve_platform("arduboy")
        assert platform is not None
        roms = tmp_path / "roms"
        queue = DownloadQueue(tmp_path / "downloads", max_concurrent=2)
        jobs = {
            queue.enqueue(
                title=result.title,
                store_id=store.store_id,
                store_name=store.display_name,
                referrer=store.download_referrer,
                media=(store.download_request(result.link),),
                platform=platform,
                roms_directory=roms,
                timeout_seconds=2,
            ).job_id
            for result in results
        }
        try:
            _wait_for_completion(queue, jobs)
        finally:
            queue.shutdown()

        assert peer.rejected_connections == 0
        for filename, content in _FILES.items():
            assert (roms / "arduboy" / filename).read_bytes() == content
