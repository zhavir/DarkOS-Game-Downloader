import json
from pathlib import Path

from dw_cli.compatibility import (
    R36SCompatibilityClient,
    filter_supported_results,
    is_unsupported_system,
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
