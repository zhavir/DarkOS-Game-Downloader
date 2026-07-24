"""Live E2E verification of the real remote search contract."""

import os

import pytest

from dw_cli.config import DEFAULT_BASE_URL
from dw_cli.vimm_store import CATALOG_SECTIONS, VimmStore


@pytest.mark.e2e
@pytest.mark.live
def test_real_prefix_all_platform_and_empty_search_end_to_end() -> None:
    """Exercise actual HTTP, prefix filters, all-platform results, and every section."""

    base_url = os.environ.get("DW_LIVE_BASE_URL", DEFAULT_BASE_URL)
    client = VimmStore(base_url, timeout_seconds=60)

    partial_results = client.search("GBA", "aDvAnCe")
    assert partial_results
    assert all(result.title.casefold().startswith("advance") for result in partial_results)
    assert any(result.title == "Advance Wars" for result in partial_results)

    all_platform_results = client.search("", "aDvAnCe")
    assert all_platform_results
    assert all(result.title.casefold().startswith("advance") for result in all_platform_results)
    assert any(
        result.system == "GBA" and result.title == "Advance Wars" for result in all_platform_results
    )

    progress: list[tuple[int, int]] = []
    catalogue = client.search(
        "GBA",
        "",
        lambda current, total: progress.append((current, total)),
    )
    titles = {result.title for result in catalogue}
    assert len(catalogue) > 100
    assert {"Advance Wars", "Golden Sun"} <= titles
    assert progress[-1] == (len(CATALOG_SECTIONS), len(CATALOG_SECTIONS))
