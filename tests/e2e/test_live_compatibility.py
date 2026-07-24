"""Live contract coverage for the frontend-only R36S compatibility index."""

from pathlib import Path

import pytest

from dw_cli.compatibility import R36SCompatibilityClient
from dw_cli.models import SearchResult
from dw_cli.platforms import resolve_platform


@pytest.mark.e2e
@pytest.mark.live
def test_real_r36s_game_list_matches_a_known_gba_title(tmp_path: Path) -> None:
    platform = resolve_platform("GBA")
    assert platform is not None
    client = R36SCompatibilityClient(
        tmp_path / "r36s-game-list.json",
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
