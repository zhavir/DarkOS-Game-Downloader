import curses
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from dw_cli.compatibility import CompatibilityInfo
from dw_cli.gamepad import InputAction
from dw_cli.models import InstalledGame, SearchResult
from dw_cli.platforms import resolve_platform
from dw_cli.store_catalog import StoreCatalog
from dw_cli.tui import GAMEPAD_KEYS, GAMEPAD_START_KEY, DownloaderTui
from dw_cli.vimm_store import VimmStore


class FakeScreen:
    def getmaxyx(self) -> tuple[int, int]:
        return (20, 80)

    def erase(self) -> None:
        pass

    def refresh(self) -> None:
        pass


def keyboard_with_inputs(
    monkeypatch: pytest.MonkeyPatch,
    inputs: tuple[int, ...],
) -> DownloaderTui:
    tui = object.__new__(DownloaderTui)
    tui.screen = FakeScreen()
    tui.gamepad = None
    tui._header = lambda _title: None  # type: ignore[method-assign]
    tui._footer = lambda _text: None  # type: ignore[method-assign]
    tui._safe_add = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    pending: Iterator[int] = iter(inputs)
    tui._get_input = lambda: next(pending)  # type: ignore[method-assign]
    monkeypatch.setattr(curses, "color_pair", lambda _number: 0)
    return tui


def test_start_submits_empty_search(monkeypatch: pytest.MonkeyPatch) -> None:
    tui = keyboard_with_inputs(monkeypatch, (GAMEPAD_START_KEY,))

    assert tui._on_screen_keyboard("SEARCH") == ""


def test_start_submits_current_search_text(monkeypatch: pytest.MonkeyPatch) -> None:
    tui = keyboard_with_inputs(monkeypatch, (ord("a"), ord("D"), ord("v"), GAMEPAD_START_KEY))

    assert tui._on_screen_keyboard("SEARCH") == "aDv"


def test_r36s_horizontal_stick_is_back_and_select() -> None:
    assert GAMEPAD_KEYS[InputAction.LEFT] == 27
    assert GAMEPAD_KEYS[InputAction.RIGHT] == 10


def test_store_picker_returns_registered_store() -> None:
    tui = object.__new__(DownloaderTui)
    store = VimmStore("https://example.test")
    tui.store_catalog = StoreCatalog((store,))
    tui._menu = lambda _title, _options, _footer: 0  # type: ignore[method-assign]

    assert tui._choose_store("CHOOSE A STORE") is store


def test_search_flow_selects_store_before_using_it(monkeypatch: pytest.MonkeyPatch) -> None:
    tui = object.__new__(DownloaderTui)
    store = VimmStore("https://example.test")
    platform = resolve_platform("GBA")
    assert platform is not None
    result = SearchResult("Advance Wars", "https://example.test/vault/1")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        store,
        "search",
        lambda system, query, _progress: calls.append((system, query)) or [result],
    )
    tui.store_catalog = StoreCatalog((store,))
    tui.platforms = (platform,)
    choices = iter((0, 0))
    tui._menu = lambda _title, _options, _footer: next(choices)  # type: ignore[method-assign]
    tui._on_screen_keyboard = lambda *_args, **_kwargs: "ADV"  # type: ignore[method-assign]
    tui._draw_message = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    tui.compatibility_client = SimpleNamespace(
        lookup_many=lambda _results, _platform: [CompatibilityInfo("Perfect", True)]
    )
    selected: list[object] = []
    tui._results_flow = lambda *args: selected.extend(args)  # type: ignore[method-assign]

    tui._search_flow()

    assert calls == [(platform.code, "ADV")]
    assert selected[-1] is store


def test_update_selects_store_before_remote_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tui = object.__new__(DownloaderTui)
    store = VimmStore("https://example.test")
    platform = resolve_platform("GBA")
    assert platform is not None
    game_path = tmp_path / "gba" / "Advance Wars.zip"
    game = InstalledGame("Advance Wars", platform, tmp_path, game_path, (game_path,))
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        store,
        "search",
        lambda system, query: (
            calls.append((system, query))
            or [SearchResult("Advance Wars", "https://example.test/vault/1")]
        ),
    )
    tui._choose_store = lambda _title: store  # type: ignore[method-assign]
    tui._draw_message = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    tui._menu = lambda _title, _options, _footer: None  # type: ignore[method-assign]

    assert tui._update_game(game) is False
    assert calls == [(platform.code, game.title)]
