from pathlib import Path

from ph.vimm_store import CATALOG_SECTIONS, VimmStore, parse_download_url, parse_search_results

ALL_RESULTS = """
<html><table class="rounded"><tr><th>System</th><th>Title</th><th>Region</th><th>Version</th></tr>
<tr><td>GBA</td><td><a href="/vault/123">Advance Wars</a></td>
<td><img title="USA"></td><td>1.0</td></tr></table></html>
"""

SYSTEM_RESULTS = (
    '<table class="rounded"><tr><th>Title</th><th>Region</th><th>Version</th>'
    "<th>Languages</th><th>Rating</th></tr>"
    '<tr><td><a href="/vault/456">Golden Sun</a></td>'
    '<td><img title="Europe"></td><td>Rev 1</td><td>En,Fr</td>'
    "<td><a>9.2</a></td></tr></table>"
)

CATALOG_RESULTS = (
    '<table class="rounded"><caption><table><tr><th>Title</th><th>Region</th>'
    "<th>Version</th></tr></table></caption>"
    '<tr><td><a href="/vault/999999" style="display:none">9</a>'
    '<a href="/vault/789">Advance Wars</a></td>'
    '<td><img title="USA"></td><td>1.0</td><td>en</td><td>9.5</td></tr></table>'
)


class StaticVimmStore(VimmStore):
    def __init__(self, response: str, cache_directory: Path | None = None) -> None:
        super().__init__("https://example.net", cache_directory=cache_directory)
        self.response = response
        self.requested_urls: list[str] = []

    def _get_text(self, url: str) -> str:
        self.requested_urls.append(url)
        return self.response


def test_parse_all_platform_results() -> None:
    results = parse_search_results(ALL_RESULTS, "https://example.net", "")
    assert len(results) == 1
    assert results[0].system == "GBA"
    assert results[0].title == "Advance Wars"
    assert results[0].region == "USA"
    assert results[0].link == "https://example.net/vault/123"


def test_parse_platform_results() -> None:
    results = parse_search_results(SYSTEM_RESULTS, "https://example.net", "GBA")
    assert len(results) == 1
    assert results[0].title == "Golden Sun"
    assert results[0].languages == "En,Fr"
    assert results[0].rating == "9.2"


def test_parse_catalogue_keeps_first_game_and_ignores_hidden_sort_link() -> None:
    results = parse_search_results(CATALOG_RESULTS, "https://example.net", "GBA")
    assert len(results) == 1
    assert results[0].title == "Advance Wars"
    assert results[0].link == "https://example.net/vault/789"


def test_search_uses_case_insensitive_prefix_filter() -> None:
    client = StaticVimmStore(
        SYSTEM_RESULTS.replace(
            "</table>",
            '<tr><td><a href="/vault/457">Sunset Riders</a></td>'
            '<td><img title="USA"></td><td>1.0</td><td>En</td><td>8.0</td></tr></table>',
        )
    )
    results = client.search("GBA", "  sUn ")
    assert [result.title for result in results] == ["Sunset Riders"]
    assert "section=number" in client.requested_urls[0]


def test_all_platform_search_omits_empty_system_and_filters_prefix() -> None:
    client = StaticVimmStore(ALL_RESULTS)

    results = client.search("", "aDvAnCe")

    assert [(result.system, result.title) for result in results] == [("GBA", "Advance Wars")]
    assert "section=number" in client.requested_urls[0]
    assert "system=" not in client.requested_urls[0]


def test_empty_search_loads_and_deduplicates_complete_catalogue() -> None:
    client = StaticVimmStore(CATALOG_RESULTS)
    progress: list[tuple[int, int]] = []
    results = client.search("GBA", "   ", lambda current, total: progress.append((current, total)))
    assert [result.title for result in results] == ["Advance Wars"]
    assert len(client.requested_urls) == len(CATALOG_SECTIONS)
    assert progress[-1] == (len(CATALOG_SECTIONS), len(CATALOG_SECTIONS))


def test_empty_all_platform_search_loads_all_catalogue_sections() -> None:
    client = StaticVimmStore(ALL_RESULTS)

    results = client.search("", "")

    assert [(result.system, result.title) for result in results] == [("GBA", "Advance Wars")]
    assert len(client.requested_urls) == len(CATALOG_SECTIONS)
    assert all("system=" not in url for url in client.requested_urls)


def test_vimm_search_and_forced_refresh_share_structured_catalogue_cache(tmp_path: Path) -> None:
    first = StaticVimmStore(CATALOG_RESULTS, tmp_path)
    assert [result.title for result in first.search("GBA", "advance")] == ["Advance Wars"]
    assert len(first.requested_urls) == len(CATALOG_SECTIONS)

    cached = StaticVimmStore("not used", tmp_path)
    assert [result.title for result in cached.search("GBA", "advance")] == ["Advance Wars"]
    assert cached.requested_urls == []
    status = cached.catalogue_cache_status("GBA")
    assert status is not None and status.result_count == 1

    cached.response = CATALOG_RESULTS.replace("Advance Wars", "Advance Wars 2")
    refreshed = cached.refresh_catalogue("GBA")
    assert [result.title for result in refreshed] == ["Advance Wars 2"]
    assert len(cached.requested_urls) == len(CATALOG_SECTIONS)


def test_parse_download_form_with_relative_action() -> None:
    html = '<form id="dl_form" action="//example.net/download"><input value="99"></form>'
    assert (
        parse_download_url(html, "https://example.net") == "https://example.net/download?mediaId=99"
    )


def test_detail_url_validation_rejects_other_hosts_and_queries() -> None:
    client = VimmStore("https://example.net")
    assert client.validate_detail_url("https://example.net/vault/123")
    assert client.validate_detail_url("https://example.net/vault/123?v=1.1")
    assert not client.validate_detail_url("https://evil.example/vault/123")
    assert not client.validate_detail_url("https://example.net/vault/123?next=evil")
