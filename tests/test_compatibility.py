import io
import json
from pathlib import Path
from types import TracebackType

import pytest
from pytest_mock import MockerFixture

from dw_cli.compatibility import (
    CompatibilityInfo,
    R36SCompatibilityClient,
    filter_supported_results,
    is_unsupported_system,
    normalize_console,
    normalize_title,
    parse_game_index,
    title_match_score,
)
from dw_cli.models import SearchResult
from dw_cli.platforms import resolve_platform


def test_frontend_chunk_parser_matches_regional_title_variants() -> None:
    chunk = (
        'self.data=[{"name":"Advance Wars (USA)","console":"Gameboy Advance",'
        '"slug":"advance-wars-usa","genre":"Strategy"},'
        '{"name":"Super Mario 64","console":"Nintendo 64",'
        '"slug":"super-mario-64","genre":"Platform"}]'
    )

    assert parse_game_index(chunk) == {
        ("gameboy advance", "advance wars"),
        ("nintendo 64", "super mario 64"),
    }
    assert normalize_title("Advance Wars [USA] (Rev 1)") == "advance wars"


def test_client_discovers_frontend_chunk_and_caches_title_index(tmp_path: Path) -> None:
    cache = tmp_path / "compatibility.json"
    requested: list[str] = []

    def fetch(url: str) -> str:
        requested.append(url)
        if url == "https://r36sgamelist.com":
            return '<script src="/_next/static/chunks/games.js"></script>'
        games = ",".join(
            '{"name":"Game %d","console":"Gameboy Advance","slug":"game-%d"}' % (number, number)
            for number in range(101)
        )
        return f"self.games=[{games}]"

    client = R36SCompatibilityClient(cache, fetch_text=fetch)
    platform = resolve_platform("GBA")
    assert platform is not None
    results = [SearchResult("Game 42 (USA)", "https://example.test/42")]

    info = client.lookup_many(results, platform)

    assert info[0].level == "Perfect"
    assert info[0].title_listed is True
    assert requested == [
        "https://r36sgamelist.com",
        "https://r36sgamelist.com/_next/static/chunks/games.js",
    ]
    payload = json.loads(cache.read_text(encoding="utf-8"))
    assert len(payload["games"]) == 101


def test_network_failure_keeps_platform_rating_without_blocking(tmp_path: Path) -> None:
    def fail(_url: str) -> str:
        raise OSError("offline")

    client = R36SCompatibilityClient(tmp_path / "cache.json", fetch_text=fail)
    platform = resolve_platform("N64")
    assert platform is not None

    info = client.lookup_many([SearchResult("Mario", "https://example.test")], platform)

    assert info[0].level == "Playable"
    assert info[0].title_listed is False


def test_compatibility_uses_scored_title_matching_for_release_metadata(tmp_path: Path) -> None:
    client = R36SCompatibilityClient(tmp_path / "cache.json")
    client._game_index = frozenset(
        {
            ("gameboy advance", "advance wars"),
            ("gameboy advance", "pokemon firered"),
            ("gameboy advance", "golden sun"),
        }
    )
    platform = resolve_platform("GBA")
    assert platform is not None

    info = client.lookup_many(
        [
            SearchResult("Advance Wars USA Rev 1", "https://example.test/1"),
            SearchResult("Pokemon Fire Red Version", "https://example.test/2"),
            SearchResult("Golden Axe", "https://example.test/3"),
        ],
        platform,
    )

    assert info[0].title_listed is True
    assert info[0].match_score is not None and info[0].match_score >= 0.9
    assert info[1].title_listed is True
    assert info[1].match_score is not None and info[1].match_score >= 0.82
    assert info[2].title_listed is False
    assert info[2].match_score is None


def test_title_match_score_avoids_simple_substring_false_positives() -> None:
    assert title_match_score("Super Mario", "Super Mario World") < 0.82
    assert title_match_score("Mario", "Mario Kart") < 0.82
    assert title_match_score("Metroid Fusion Rev 1 USA", "Metroid Fusion") >= 0.9


def test_explicitly_unsupported_systems_are_filtered_from_all_platform_results() -> None:
    results = [
        SearchResult("Retro Game", "https://example.test/retro", system="GBA"),
        SearchResult("Modern Game", "https://example.test/modern", system="PlayStation 2"),
        SearchResult("Another Modern Game", "https://example.test/xbox", system="Xbox 360"),
    ]

    assert is_unsupported_system("Sony PlayStation 3")
    assert [result.title for result in filter_supported_results(results)] == ["Retro Game"]


def test_compatibility_labels_cover_platform_and_title_states() -> None:
    assert CompatibilityInfo("Not listed", False).short_label == "Not listed"
    assert CompatibilityInfo("Not listed", False).detail_label == "Not listed by r36sgamelist.com"
    assert CompatibilityInfo("Perfect", True).short_label == "Perfect - listed"
    assert CompatibilityInfo("Perfect", True).detail_label == "Perfect (title listed)"
    assert CompatibilityInfo("Playable", False).detail_label == "Playable (platform rating)"
    assert CompatibilityInfo("Perfect", True, 0.956).short_label == "Perfect - 96% match"


def test_unknown_console_does_not_load_remote_index(tmp_path: Path) -> None:
    client = R36SCompatibilityClient(
        tmp_path / "cache.json",
        fetch_text=lambda _url: pytest.fail("network should not be used"),
    )
    platform = resolve_platform("ports")
    assert platform is not None

    info = client.lookup_many([SearchResult("Port", "detail")], platform)

    assert info == [CompatibilityInfo("Not listed", False)]
    assert normalize_console("unknown") is None


def test_client_uses_fresh_cache_and_ignores_stale_or_malformed_cache(tmp_path: Path) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps({"fetched_at": 9_999_999_999, "games": [["gameboy advance", "cached game"]]}),
        encoding="utf-8",
    )
    client = R36SCompatibilityClient(cache, fetch_text=lambda _url: pytest.fail("no network"))
    assert client.lookup_many([SearchResult("Cached Game", "detail")], platform)[0].title_listed
    assert client._load_game_index() == frozenset({("gameboy advance", "cached game")})

    for payload in (
        '{"fetched_at": 0, "games": []}',
        '{"fetched_at": 9999999999, "games": "bad"}',
        '{"fetched_at": 9999999999, "games": [["only-one"]]}',
        "not json",
    ):
        cache.write_text(payload, encoding="utf-8")
        assert R36SCompatibilityClient(cache)._read_cache() is None


def test_small_or_partially_unavailable_frontend_index_is_rejected(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        if url.endswith("bad.js"):
            raise OSError("missing chunk")
        return (
            '<script src="/bad.js"></script>{"name":"One","console":"Gameboy Advance","slug":"one"}'
        )

    client = R36SCompatibilityClient(tmp_path / "cache.json", fetch_text=fetch)

    with pytest.raises(ValueError, match="usable frontend"):
        client._download_game_index()
    assert client._fetch_optional("https://example.test/bad.js") == ""
    assert client._same_origin("https://r36sgamelist.com/chunk.js")
    assert not client._same_origin("https://other.test/chunk.js")


class Response(io.BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def test_default_fetcher_and_cache_write_failure(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    opened = mocker.patch(
        "dw_cli.compatibility.urlopen",
        return_value=Response("café".encode()),
    )
    client = R36SCompatibilityClient(tmp_path / "cache.json")
    assert client._fetch_text("https://r36sgamelist.com") == "café"
    assert opened.call_count == 1

    mocker.patch.object(Path, "write_text", side_effect=OSError("read only"))
    client._write_cache(frozenset({("gameboy advance", "game")}))


def test_parser_skips_invalid_json_and_title_scores_empty_and_exact() -> None:
    document = (
        '{"name":"bad\\uZZZZ","console":"Gameboy Advance","slug":"bad"}'
        '{"name":"Good","console":"Unknown","slug":"good"}'
    )
    assert parse_game_index(document) == frozenset()
    assert title_match_score("", "Game") == 0.0
    assert title_match_score("Game", "Game") == 1.0
