from dw_cli.minerva_store import MinervaStore, parse_directory
from dw_cli.models import MediaDownload
from dw_cli.platforms import resolve_platform

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

    assert request == MediaDownload(
        "https://cdn.minerva.example/torrents/"
        "Minerva_Myrient%20-%20RetroAchievements%20-%20"
        "RA%20-%20Nintendo%20Game%20Boy%20Advance.torrent",
        torrent_file_index=2,
        expected_filename="Advance Wars (USA) (Rev 1).zip",
    )


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
