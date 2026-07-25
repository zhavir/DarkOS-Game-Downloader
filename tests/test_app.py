from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from dw_cli import app
from dw_cli.app import build_parser
from dw_cli.config import Config
from dw_cli.downloader import DownloadError
from dw_cli.models import DownloadResult, MediaDownload, Platform, SearchResult
from dw_cli.platforms import resolve_platform
from dw_cli.store import CatalogProgress, GameStore, StoreError


class FakeStore(GameStore):
    store_id = "fake"
    display_name = "Fake Store"
    description = "Test store"

    def __init__(self) -> None:
        self.results: list[SearchResult] = []

    @property
    def base_url(self) -> str:
        return "https://example.test"

    @property
    def download_referrer(self) -> str:
        return "https://example.test/"

    def supports_platform(self, platform: Platform) -> bool:
        del platform
        return True

    def platform_code(self, platform: Platform) -> str:
        return platform.code

    def search(
        self,
        system_code: str,
        query: str,
        catalog_progress: CatalogProgress | None = None,
    ) -> list[SearchResult]:
        del system_code, query, catalog_progress
        return self.results

    def validate_detail_url(self, url: str) -> bool:
        return url.startswith(self.base_url)

    def retrieve_download_url(self, detail_url: str) -> str:
        return detail_url + "/download"

    def download_request(self, detail_url: str) -> MediaDownload:
        return MediaDownload(self.retrieve_download_url(detail_url))


def test_supported_consoles_command_was_removed() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["consoles"])


def test_search_query_is_optional_for_catalogue_listing() -> None:
    arguments = build_parser().parse_args(["search", "GBA"])
    assert arguments.query == []
    assert arguments.store == "vimm"


def test_store_can_be_selected_for_cli_automation() -> None:
    arguments = build_parser().parse_args(["--store", "vimm", "search", "GBA", "Advance"])

    assert arguments.store == "vimm"
    assert arguments.query == ["Advance"]


def test_main_runs_tui_and_reports_terminal_errors(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = Config("https://old.test", Path("downloads"), ())
    mocker.patch.object(app.sys.stdin, "isatty", return_value=True)
    mocker.patch.object(app.sys.stdout, "isatty", return_value=True)
    called: list[Config] = []
    run_tui = mocker.patch.object(app, "run_tui", side_effect=lambda value: called.append(value))

    assert app.main(["--base-url", "https://new.test/", "tui"], runtime_config=config) == 0
    assert called[0].base_url == "https://new.test"

    run_tui.side_effect = ValueError("bad UI")
    assert app.main(["tui"], runtime_config=config) == 2

    run_tui.side_effect = RuntimeError("unexpected")
    assert app.main(["tui"], runtime_config=config) == 2
    assert "diagnostic log" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("stores", "stdin_tty", "stdout_tty", "message"),
    [
        ((), True, True, "no download stores"),
        ((FakeStore(),), False, True, "interactive terminal"),
        ((FakeStore(),), True, False, "interactive terminal"),
    ],
)
def test_main_rejects_invalid_tui_environment(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    stores: tuple[FakeStore, ...],
    stdin_tty: bool,
    stdout_tty: bool,
    message: str,
) -> None:
    enabled_stores = ("vimm",) if stores else ()
    config = Config(
        "https://example.test",
        Path("downloads"),
        (),
        enabled_stores=enabled_stores,
    )
    mocker.patch.object(app.sys.stdin, "isatty", lambda: stdin_tty)
    mocker.patch.object(app.sys.stdout, "isatty", lambda: stdout_tty)

    with pytest.raises(SystemExit, match="2"):
        app.main([], runtime_config=config)

    assert message in capsys.readouterr().err


def test_main_routes_search_and_rejects_unknown_store(mocker: MockerFixture) -> None:
    config = Config("https://example.test", Path("downloads"), ())
    calls: list[tuple[object, str, str]] = []
    mocker.patch.object(app, "_run_search", side_effect=lambda *args: calls.append(args) or 7)

    assert (
        app.main(
            ["--store", "vimm", "search", "GBA", "Advance", "Wars"],
            runtime_config=config,
        )
        == 7
    )
    assert calls[0][1:] == ("GBA", "Advance Wars")
    with pytest.raises(SystemExit, match="2"):
        app.main(["--store", "missing", "search", "GBA"], runtime_config=config)


def test_main_routes_download(mocker: MockerFixture) -> None:
    config = Config("https://example.test", Path("staging"), ())
    calls: list[tuple[object, ...]] = []
    mocker.patch.object(app, "_run_download", side_effect=lambda *args: calls.append(args) or 4)

    assert (
        app.main(
            ["--store", "vimm", "download", "https://example.test/game"],
            runtime_config=config,
        )
        == 4
    )
    assert calls[0][3] == Path("staging")


def test_run_search_covers_errors_empty_catalogue_and_results(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = FakeStore()
    assert app._run_search(store, "unknown", "game") == 2
    platform = resolve_platform("GBA")
    assert platform is not None
    mocker.patch.object(store, "supports_platform", lambda _platform: False)
    assert app._run_search(store, "GBA", "game") == 2
    mocker.patch.object(store, "supports_platform", lambda _platform: True)

    store.results = []
    assert app._run_search(store, "GBA", "game") == 0
    assert "No results" in capsys.readouterr().out
    assert app._run_search(store, "GBA", "") == 0
    assert "No catalogue" in capsys.readouterr().out

    store.results = [SearchResult("Advance Wars", "https://example.test/game", system="GBA")]
    assert app._run_search(store, "GBA", "advance") == 0
    assert "Advance Wars" in capsys.readouterr().out
    mocker.patch.object(
        store, "search", lambda *_args: (_ for _ in ()).throw(StoreError("offline"))
    )
    assert app._run_search(store, "GBA", "advance") == 1
    assert "Search failed" in capsys.readouterr().err


def test_run_download_moves_roms_reports_bios_and_requests_refresh(
    tmp_path: Path,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = FakeStore()
    download = DownloadResult("https://example.test/file", tmp_path / "staging" / "game.zip")
    moved = DownloadResult(download.url, tmp_path / "roms" / "gba" / "game.zip")
    config = Config(
        "https://example.test",
        tmp_path / "downloads",
        (tmp_path / "roms",),
        timeout_seconds=2.0,
    )
    mocker.patch.object(app, "download_files", lambda *_args: [download])
    mocker.patch.object(app, "detect_roms_directory", lambda _roots: tmp_path / "roms")

    def move(
        _downloads: object,
        _platform: object,
        _root: Path,
        bios_callback: Callable[[Path], None],
    ) -> list[DownloadResult]:
        bios_callback(tmp_path / "roms" / "bios" / "firmware.bin")
        return [moved]

    mocker.patch.object(app, "move_to_arkos", move)
    refreshed: list[bool] = []
    mocker.patch.object(
        app, "request_emulationstation_refresh", lambda: refreshed.append(True) or True
    )

    assert app._run_download(store, config, ["detail"], tmp_path, "GBA", None) == 0
    output = capsys.readouterr().out
    assert "Completed:" in output and "BIOS installed:" in output
    assert refreshed == [True]

    assert app._run_download(store, config, ["detail"], tmp_path, None, None) == 0
    assert "use --platform" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("platform_name", "roms_root", "exception", "message"),
    [
        ("unknown", Path("roms"), None, "Unknown platform"),
        ("GBA", None, None, "No dArkOS ROM root"),
        (None, None, DownloadError("network"), "network"),
    ],
)
def test_run_download_reports_failures(
    tmp_path: Path,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    platform_name: str | None,
    roms_root: Path | None,
    exception: Exception | None,
    message: str,
) -> None:
    store = FakeStore()
    config = Config(
        "https://example.test",
        tmp_path / "downloads",
        (tmp_path / "roms",),
        timeout_seconds=1.0,
    )
    if exception is None:
        mocker.patch.object(app, "download_files", lambda *_args: [])
    else:
        mocker.patch.object(app, "download_files", lambda *_args: (_ for _ in ()).throw(exception))
    mocker.patch.object(app, "detect_roms_directory", lambda _roots: roms_root)

    assert app._run_download(store, config, ["detail"], tmp_path, platform_name, None) == 1
    assert message in capsys.readouterr().err


def test_progress_and_table_output(capsys: pytest.CaptureFixture[str]) -> None:
    app._print_progress("game", 150, 100)
    app._print_progress("game", 2048, None)
    app._print_results(
        [
            SearchResult(
                "Title",
                "https://example.test/game",
                system="GBA",
                region="USA",
                version="1.0",
            ),
            SearchResult("Other", "https://example.test/other"),
        ]
    )

    output = capsys.readouterr().out
    assert "100%" in output
    assert "2 KiB" in output
    assert "SYSTEM" in output and "Title" in output and "Other" in output
