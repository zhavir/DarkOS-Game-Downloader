import io
from email.message import Message
from pathlib import Path
from types import TracebackType
from urllib.error import HTTPError, URLError

import pytest
from pytest_mock import MockerFixture

from dw_cli.minerva_store import RA_DIRECTORIES, MinervaEntry, MinervaStore, parse_directory
from dw_cli.models import MediaDownload
from dw_cli.platforms import resolve_platform
from dw_cli.store import StoreError

GBA_DIRECTORY = "RA - Nintendo Game Boy Advance"
HTML = (
    '<div class="entry" data-name="007 - nightfire (usa, europe).zip">'
    '<a href="/rom?name=.%2FRetroAchievements%2FRA%20-%20Nintendo%20Game%20Boy%20'
    'Advance%2F007%20-%20NightFire%20%28USA%2C%20Europe%29.zip">'
    "007 - NightFire (USA, Europe).zip</a><span>4.17 MB</span></div>"
    '<div class="entry" data-name="advance wars (usa) (rev 1).zip">'
    '<a href="/rom?name=.%2FRetroAchievements%2FRA%20-%20Nintendo%20Game%20Boy%20'
    'Advance%2FAdvance%20Wars%20%28USA%29%20%28Rev%201%29.zip">'
    "Advance Wars (USA) (Rev 1).zip</a><span>2.30 MB</span></div>"
)


class StaticMinervaStore(MinervaStore):
    def _get_text(self, url: str) -> str:
        assert GBA_DIRECTORY.replace(" ", "%20") in url
        return HTML


def test_minerva_search_uses_structured_disk_cache_and_supports_forced_refresh(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    store = StaticMinervaStore(
        "https://minerva.example",
        "https://cdn.minerva.example/torrents",
        cache_directory=tmp_path,
    )
    fetched = mocker.spy(store, "_get_text")
    assert len(store.search(GBA_DIRECTORY, "advance")) == 1
    assert fetched.call_count == 1

    reloaded = StaticMinervaStore(
        "https://minerva.example",
        "https://cdn.minerva.example/torrents",
        cache_directory=tmp_path,
    )
    no_network = mocker.patch.object(reloaded, "_get_text", side_effect=OSError("offline"))
    assert len(reloaded.search(GBA_DIRECTORY, "advance")) == 1
    no_network.assert_not_called()

    no_network.side_effect = None
    no_network.return_value = HTML
    assert len(reloaded.refresh_catalogue(GBA_DIRECTORY)) == 2


def test_parse_directory_preserves_one_based_torrent_order() -> None:
    entries = parse_directory(HTML, "https://minerva.example")

    assert [entry.file_index for entry in entries] == [1, 2]
    assert entries[1].filename == "Advance Wars (USA) (Rev 1).zip"
    assert entries[1].link.startswith("https://minerva.example/rom?name=")


def test_search_is_empty_or_case_insensitive_prefix_and_returns_metadata() -> None:
    store = StaticMinervaStore(
        "https://minerva.example",
        "https://cdn.minerva.example/torrents",
    )

    matches = store.search(GBA_DIRECTORY, "aDvAnCe")
    catalogue = store.search(GBA_DIRECTORY, "")

    assert [result.title for result in matches] == ["Advance Wars (USA) (Rev 1)"]
    assert matches[0].region == "USA"
    assert matches[0].version == "Rev 1"
    assert len(catalogue) == 2


def test_download_request_selects_only_the_matching_torrent_file() -> None:
    store = StaticMinervaStore(
        "https://minerva.example",
        "https://cdn.minerva.example/torrents",
    )
    detail_url = (
        "https://minerva.example/rom/?name=.%2FRetroAchievements%2F"
        "RA%20-%20Nintendo%20Game%20Boy%20Advance%2F"
        "Advance%20Wars%20%28USA%29%20%28Rev%201%29.zip"
    )

    request = store.download_request(detail_url)
    download_url = store.retrieve_download_url(detail_url)

    assert request == MediaDownload(
        "https://cdn.minerva.example/torrents/"
        "Minerva_Myrient%20-%20RetroAchievements%20-%20"
        "RA%20-%20Nintendo%20Game%20Boy%20Advance.torrent",
        torrent_file_index=2,
        expected_filename="Advance Wars (USA) (Rev 1).zip",
    )
    assert download_url == request.url


def test_detail_url_validation_rejects_other_collections_and_traversal() -> None:
    store = StaticMinervaStore(
        "https://minerva.example",
        "https://cdn.minerva.example/torrents",
    )

    assert not store.validate_detail_url("https://other.example/rom?name=game.zip")
    assert not store.validate_detail_url(
        "https://minerva.example/rom?name=.%2FNo-Intro%2FRA%20-%20Nintendo%2Fgame.zip"
    )
    assert not store.validate_detail_url(
        "https://minerva.example/rom?name=.%2FRetroAchievements%2F..%2Fgame.zip"
    )


def test_supported_platform_mapping_excludes_unavailable_platforms() -> None:
    store = StaticMinervaStore(
        "https://minerva.example",
        "https://cdn.minerva.example/torrents",
    )
    gba = resolve_platform("GBA")
    ports = resolve_platform("ports")
    assert gba is not None and ports is not None

    assert store.supports_platform(gba)
    assert store.platform_code(gba) == GBA_DIRECTORY
    assert not store.supports_platform(ports)


def test_directory_parser_ignores_non_rom_entries_and_uses_text_fallback() -> None:
    html = (
        '<div class="entry"><div><a href="/browse/other">Ignored</a></div></div>'
        '<div class="entry"><a href="/rom?name=.">Fallback Name.zip</a></div>'
        '<div class="entry"><a href="/rom?name=one&name=two">Ambiguous</a></div>'
    )

    entries = parse_directory(html, "https://minerva.example")

    assert [entry.filename for entry in entries] == ["Fallback Name.zip"]


@pytest.mark.parametrize(
    ("base_url", "torrent_url", "message"),
    [
        ("relative", "https://torrent.test", "base_url"),
        ("https://minerva.test", "relative", "torrent_base_url"),
    ],
)
def test_store_requires_absolute_service_urls(
    base_url: str,
    torrent_url: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MinervaStore(base_url, torrent_url)


def test_store_properties_all_platform_search_progress_and_cache(
    mocker: MockerFixture,
) -> None:
    store = MinervaStore("https://minerva.test/", "https://torrent.test/")
    gba = resolve_platform("GBA")
    all_platform = resolve_platform("ALL")
    assert gba is not None and all_platform is not None
    entries = (MinervaEntry("Game (USA) (Rev 2) (En,Fr).zip", "detail", 1),)
    directories = RA_DIRECTORIES[:2]
    mocker.patch("dw_cli.minerva_store.RA_DIRECTORIES", directories)
    fetched = mocker.patch.object(store, "_get_text", return_value=HTML)
    progress: list[tuple[int, int]] = []
    mocker.patch("dw_cli.minerva_store.parse_directory", return_value=list(entries))

    results = store.search("", "game", lambda *args: progress.append(args))

    assert len(results) == 2
    assert all(result.system for result in results)
    assert results[0].region == "USA"
    assert results[0].version == "Rev 2"
    assert results[0].languages == "En,Fr"
    assert progress[-1] == (2, 2)
    assert store.platform_code(all_platform) == ""
    assert store.base_url == "https://minerva.test"
    assert store.download_referrer.endswith("/browse/RetroAchievements/")
    assert "User-Agent" in store.headers
    store._entries(directories[0])
    assert fetched.call_count == 2


def test_store_rejects_unknown_platform_detail_and_missing_catalogue(
    mocker: MockerFixture,
) -> None:
    store = MinervaStore("https://minerva.test", "https://torrent.test")
    with pytest.raises(StoreError, match="does not provide"):
        store.search("unknown", "")
    with pytest.raises(StoreError, match="Not a valid"):
        store.retrieve_download_url("https://other.test/rom?name=x")

    detail = (
        "https://minerva.test/rom?name=./RetroAchievements/"
        "RA%20-%20Nintendo%20Game%20Boy%20Advance/Missing.zip"
    )
    mocker.patch.object(store, "_entries", return_value=())
    with pytest.raises(StoreError, match="no longer present"):
        store.download_request(detail)

    empty_store = MinervaStore("https://minerva.test", "https://torrent.test")
    mocker.patch("dw_cli.minerva_store.parse_directory", return_value=[])
    mocker.patch.object(empty_store, "_get_text", return_value="empty")
    with pytest.raises(StoreError, match="empty catalogue"):
        empty_store._entries(GBA_DIRECTORY)


@pytest.mark.parametrize(
    "url",
    [
        "https://minerva.test/rom?name=./RetroAchievements/RA%20-%20Nintendo%20Game%20Boy%20Advance/Game.zip#fragment",
        "https://minerva.test/rom?name=a&other=b",
        "https://minerva.test/rom?name=one&name=two",
        "https://minerva.test/rom?name=RetroAchievements\\bad",
        "https://minerva.test/rom?name=./RetroAchievements/Unknown/Game.zip",
        "https://minerva.test/rom?name=./RetroAchievements/RA%20-%20Nintendo%20Game%20Boy%20Advance/",
    ],
)
def test_detail_url_validation_rejects_malformed_variants(url: str) -> None:
    store = MinervaStore("https://minerva.test", "https://torrent.test")
    assert store.validate_detail_url(url) is False


class Response(io.BytesIO):
    class Headers:
        @staticmethod
        def get_content_charset() -> str | None:
            return None

    headers = Headers()

    def __enter__(self) -> Response:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def test_get_text_decodes_response_and_retries_transient_errors(mocker: MockerFixture) -> None:
    store = MinervaStore("https://minerva.test", "https://torrent.test")
    opened = mocker.patch(
        "dw_cli.minerva_store.urlopen",
        side_effect=(URLError("temporary"), Response(b"catalogue")),
    )
    sleep = mocker.patch("dw_cli.minerva_store.time.sleep")

    assert store._get_text("https://minerva.test/browse") == "catalogue"
    assert opened.call_count == 2
    sleep.assert_called_once_with(0.25)


def test_get_text_reports_permanent_and_exhausted_errors(mocker: MockerFixture) -> None:
    store = MinervaStore("https://minerva.test", "https://torrent.test")
    mocker.patch(
        "dw_cli.minerva_store.urlopen",
        side_effect=HTTPError("url", 404, "missing", Message(), None),
    )
    with pytest.raises(StoreError, match="HTTP 404") as caught:
        store._get_text("https://minerva.test/browse")
    assert caught.value.status_code == 404

    mocker.patch(
        "dw_cli.minerva_store.urlopen",
        side_effect=HTTPError("url", 503, "down", Message(), None),
    )
    sleep = mocker.patch("dw_cli.minerva_store.time.sleep")
    with pytest.raises(StoreError, match="after 3 attempts"):
        store._get_text("https://minerva.test/browse")
    assert sleep.call_count == 2
