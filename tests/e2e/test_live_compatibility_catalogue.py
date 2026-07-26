"""Live contract coverage for the frontend-only compatibility index."""

from pathlib import Path

import pytest

from ph.compatibility import GameCompatibilityClient
from ph.models import SearchResult
from ph.platforms import resolve_platform


@pytest.mark.e2e
@pytest.mark.live
def test_real_compatibility_catalogue_matches_a_known_gba_title(tmp_path: Path) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    client = GameCompatibilityClient(
        tmp_path / "game-compatibility.json",
        timeout_seconds=60,
    )

    result = client.lookup_many(
        [
            SearchResult(
                "Shaman King \N{EN DASH} Master of Spirits (USA)",
                "https://example.test/game",
            )
        ],
        platform,
    )[0]

    assert result.level == "Perfect"
    assert result.title_listed is True
