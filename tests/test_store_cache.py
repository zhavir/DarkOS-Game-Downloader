import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from dw_cli import store_cache as cache_module
from dw_cli.models import SearchResult
from dw_cli.store_cache import CatalogueCacheError, GameCatalogueCache


def test_catalogue_cache_writes_structured_platform_file_and_reuses_it(tmp_path: Path) -> None:
    cache = GameCatalogueCache(tmp_path, "test-store", "https://store.example", 60)
    result = SearchResult(
        "Pokémon Émeraude",
        "https://store.example/game/1",
        "GBA",
        "Europe",
        "Rev 1",
        "Fr",
        "9.5",
    )
    calls = 0

    def fetch() -> tuple[SearchResult, ...]:
        nonlocal calls
        calls += 1
        return (result,)

    assert cache.get_or_fetch("Game Boy Advance", fetch) == (result,)
    assert cache.get_or_fetch("Game Boy Advance", fetch) == (result,)
    assert calls == 1
    path = tmp_path / "game-catalogues/test-store/Game%20Boy%20Advance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["store_id"] == "test-store"
    assert payload["system_code"] == "Game Boy Advance"
    assert payload["source_url"] == "https://store.example"
    assert payload["results"][0]["title"] == "Pokémon Émeraude"
    status = cache.status("Game Boy Advance")
    assert status is not None
    assert status.result_count == 1
    assert not status.stale
    assert cache.cached_files() == (path,)
    assert cache.status("missing") is None


def test_expired_cache_refreshes_and_falls_back_only_for_automatic_use(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    now = 1_000_000.0
    mocker.patch.object(cache_module, "time", return_value=now)
    cache = GameCatalogueCache(tmp_path, "store", "https://store.example", 10)
    old = SearchResult("Old Game", "old")
    new = SearchResult("New Game", "new")
    assert cache.get_or_fetch("GBA", lambda: (old,)) == (old,)

    now += 11
    mocker.patch.object(cache_module, "time", return_value=now)
    status = cache.status("GBA")
    assert status is not None
    assert status.stale
    assert cache.get_or_fetch("GBA", lambda: (new,)) == (new,)

    now += 11
    mocker.patch.object(cache_module, "time", return_value=now)

    def offline() -> tuple[SearchResult, ...]:
        raise OSError("offline")

    assert cache.get_or_fetch("GBA", offline) == (new,)
    with pytest.raises(OSError, match="offline"):
        cache.get_or_fetch("GBA", offline, force=True)


@pytest.mark.parametrize(
    "payload",
    (
        "not json",
        '{"schema_version":2}',
        '{"schema_version":1,"store_id":"other","system_code":"GBA",'
        '"source_url":"https://store.example","fetched_at":1,"results":[]}',
        '{"schema_version":1,"store_id":"store","system_code":"GBA",'
        '"source_url":"https://store.example","fetched_at":1,"results":[{}]}',
        '{"schema_version":1,"store_id":"store","system_code":"GBA",'
        '"source_url":"https://store.example","fetched_at":1,"results":[1]}',
    ),
)
def test_invalid_catalogue_files_are_ignored(tmp_path: Path, payload: str) -> None:
    cache = GameCatalogueCache(tmp_path, "store", "https://store.example")
    path = cache.path_for("GBA")
    path.parent.mkdir(parents=True)
    path.write_text(payload, encoding="utf-8")
    expected = (SearchResult("Recovered", "detail"),)
    assert cache.get_or_fetch("GBA", lambda: expected) == expected


def test_forced_cache_write_failure_is_reported_and_old_file_is_preserved(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    cache = GameCatalogueCache(tmp_path, "store", "https://store.example")
    old = (SearchResult("Old", "old"),)
    cache.get_or_fetch("GBA", lambda: old)
    path = cache.path_for("GBA")
    original = path.read_bytes()
    mocker.patch.object(cache_module.os, "replace", side_effect=OSError("read only"))

    with pytest.raises(CatalogueCacheError, match="read only"):
        cache.get_or_fetch("GBA", lambda: (SearchResult("New", "new"),), force=True)

    assert path.read_bytes() == original
    assert not path.with_name(path.name + ".tmp").exists()


def test_optional_cache_write_and_file_listing_failures_do_not_break_search(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    cache = GameCatalogueCache(tmp_path, "store", "https://store.example")
    result = SearchResult("Playable", "detail")
    mocker.patch.object(cache_module.os, "replace", side_effect=OSError("read only"))

    assert cache.get_or_fetch("GBA", lambda: (result,)) == (result,)
    mocker.patch.object(Path, "glob", side_effect=OSError("unreadable"))
    assert cache.cached_files() == ()
