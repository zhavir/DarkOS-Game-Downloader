"""Small offline Vault-compatible server for manual and automated end-to-end tests."""

import argparse
import contextlib
import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import parse_qs, urlparse


def _demo_zip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


@dataclass(frozen=True, slots=True)
class DemoGame:
    detail_id: str
    title: str
    version: str
    filename: str
    content: bytes
    region: str = "USA"
    system: str = "GBA"


DEMO_GAMES: tuple[DemoGame, ...] = (
    DemoGame("1001", "Advance Wars", "1.0", "Advance Wars (USA).zip", b"demo-v1"),
    DemoGame(
        "1002",
        "Advance Wars",
        "Rev 2",
        "Advance Wars (USA) (Rev 2).zip",
        b"demo-v2",
    ),
    DemoGame(
        "2001",
        "Golden Sun",
        "1.0",
        "Golden Sun (USA).zip",
        _demo_zip({"Golden Sun.gba": b"golden-sun", "bios/gba_bios.bin": b"demo-bios"}),
    ),
    DemoGame("3001", "007 - Everything or Nothing", "1.0", "007 GBA.zip", b"007"),
)


class LocalVaultServer(ThreadingHTTPServer):
    """Typed HTTP server carrying the request logging preference."""

    verbose_requests: bool
    exact_search_only: bool
    missing_sections_return_404: bool


class LocalVaultHandler(BaseHTTPRequestHandler):
    """Serve just enough HTML and downloads to exercise every application workflow."""

    server_version = "LocalVault/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if parsed.path == "/vault/" and query.get("p") == ["list"]:
            games = self._list_games(query)
            server = cast(LocalVaultServer, self.server)
            if (server.exact_search_only and query.get("q", [""])[0] and not games) or (
                server.missing_sections_return_404 and "section" in query and not games
            ):
                self.send_error(404, "Strict demo search route")
                return
            system_code = query.get("system", [""])[0]
            self._send_html(_results_html(games, include_system=not system_code))
            return

        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) == 3 and path_parts[:2] == ["vault", "GBA"]:
            section = path_parts[2]
            games = tuple(game for game in DEMO_GAMES if _game_is_in_section(game, section))
            self._send_html(_results_html(games, include_system=False, nested_header=True))
            return

        if len(path_parts) == 2 and path_parts[0] == "vault":
            game = _game_by_id(path_parts[1])
            if game is not None:
                self._send_html(
                    '<html><form id="dl_form" action="/download">'
                    f'<input name="mediaId" value="{game.detail_id}"></form></html>'
                )
                return

        if parsed.path == "/download":
            media_id = query.get("mediaId", [""])[0]
            game = _game_by_id(media_id)
            if game is not None:
                self._send_download(game)
                return

        self.send_error(404, "Demo resource not found")

    def _list_games(self, query: dict[str, list[str]]) -> tuple[DemoGame, ...]:
        system = query.get("system", [""])[0]
        games = tuple(game for game in DEMO_GAMES if not system or game.system == system)
        if "section" in query:
            section = query["section"][0]
            return tuple(game for game in games if _game_is_in_section(game, section))
        needle = " ".join(query.get("q", [""])[0].split()).casefold()
        server = cast(LocalVaultServer, self.server)
        if server.exact_search_only:
            return tuple(game for game in games if not needle or needle == game.title.casefold())
        return tuple(game for game in games if not needle or needle in game.title.casefold())

    def _send_html(self, document: str) -> None:
        payload = document.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_download(self, game: DemoGame) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{game.filename}"')
        self.send_header("Content-Length", str(len(game.content)))
        self.end_headers()
        self.wfile.write(game.content)

    def log_message(self, format: str, *args: object) -> None:
        server = cast(LocalVaultServer, self.server)
        if server.verbose_requests:
            super().log_message(format, *args)


def _results_html(
    games: Sequence[DemoGame],
    *,
    include_system: bool,
    nested_header: bool = False,
) -> str:
    headings = (
        "<th>System</th><th>Title</th><th>Region</th><th>Version</th>"
        if include_system
        else "<th>Title</th><th>Region</th><th>Version</th><th>Languages</th><th>Rating</th>"
    )
    heading_row = f"<tr>{headings}</tr>"
    header = f"<caption><table>{heading_row}</table></caption>" if nested_header else heading_row
    rows = []
    for game in games:
        system_cell = f"<td>{escape(game.system)}</td>" if include_system else ""
        rows.append(
            "<tr>"
            f"{system_cell}"
            f'<td><a href="/vault/999999" style="display:none">9</a>'
            f'<a href="/vault/{game.detail_id}">{escape(game.title)}</a></td>'
            f'<td><img title="{escape(game.region)}"></td>'
            f"<td>{escape(game.version)}</td><td>en</td><td>9.0</td>"
            "</tr>"
        )
    return '<html><table class="rounded">{}{}\n</table></html>'.format(
        header,
        "".join(rows),
    )


def _game_by_id(detail_id: str) -> DemoGame | None:
    return next((game for game in DEMO_GAMES if game.detail_id == detail_id), None)


def _game_is_in_section(game: DemoGame, section: str) -> bool:
    first = game.title[0].upper()
    if section.casefold() == "number":
        return not first.isalpha()
    return first == section.upper()


def build_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    verbose: bool = False,
    exact_search_only: bool = False,
    missing_sections_return_404: bool = False,
) -> LocalVaultServer:
    server = LocalVaultServer((host, port), LocalVaultHandler)
    server.verbose_requests = verbose
    server.exact_search_only = exact_search_only
    server.missing_sections_return_404 = missing_sections_return_404
    return server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args(argv)
    server = build_server(arguments.host, arguments.port, verbose=arguments.verbose)
    host, port = server.server_address[:2]
    print(f"Local test catalogue: http://{host}:{port}", flush=True)
    print("Press Ctrl-C to stop it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local test catalogue.")
    finally:
        with contextlib.suppress(OSError):
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
