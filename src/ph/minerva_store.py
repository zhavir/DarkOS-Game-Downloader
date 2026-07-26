"""Minerva Archive RetroAchievements store and selected-torrent downloads."""

import re
import ssl
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import Request, urlopen

from ph.cache_policy import DEFAULT_CATALOGUE_TTL_DAYS, catalogue_ttl_seconds
from ph.models import MediaDownload, Platform, SearchResult
from ph.platforms import DARKOS_PLATFORMS
from ph.store import USER_AGENT, CatalogProgress, GameStore, StoreError

PLATFORM_DIRECTORIES: dict[str, str] = {
    "3do": "RA - 3DO Interactive Multiplayer",
    "amstrad-cpc": "RA - Amstrad CPC",
    "apple-ii": "RA - Apple II",
    "arcade": "RA - Arcade",
    "arduboy": "RA - Arduboy",
    "atari-2600": "RA - Atari 2600",
    "atari-7800": "RA - Atari 7800",
    "atari-jaguar": "RA - Atari Jaguar",
    "atari-lynx": "RA - Atari Lynx",
    "colecovision": "RA - Colecovision",
    "dreamcast": "RA - Sega Dreamcast",
    "fairchild-channel-f": "RA - Fairchild Channel F",
    "famicom-disk-system": "RA - Nintendo Famicom Disk System",
    "game-boy": "RA - Nintendo Game Boy",
    "game-boy-advance": "RA - Nintendo Game Boy Advance",
    "game-boy-color": "RA - Nintendo Game Boy Color",
    "game-gear": "RA - Sega Game Gear",
    "genesis": "RA - Sega Genesis",
    "intellivision": "RA - Mattel Intellivision",
    "master-system": "RA - Sega Master System",
    "mega-duck": "RA - Mega Duck",
    "msx": "RA - Microsoft MSX",
    "neo-geo-cd": "RA - SNK Neo Geo CD",
    "neo-geo-pocket": "RA - SNK Neo Geo Pocket",
    "neo-geo-pocket-color": "RA - SNK Neo Geo Pocket",
    "nintendo-64": "RA - Nintendo 64",
    "nintendo-ds": "RA - Nintendo DS",
    "nintendo": "RA - Nintendo Entertainment System",
    "odyssey-2": "RA - Magnavox Odyssey 2",
    "pc-engine": "RA - NEC TurboGrafx-16",
    "pc-engine-cd": "RA - NEC TurboGrafx-CD",
    "pc-fx": "RA - NEC PC-FX",
    "playstation": "RA - Sony Playstation",
    "ps-portable": "RA - Sony PSP",
    "pokemon-mini": "RA - Nintendo Pokemon Mini",
    "sega-32x": "RA - Sega 32X",
    "sega-cd": "RA - Sega CD",
    "saturn": "RA - Sega Saturn",
    "sg-1000": "RA - Sega SG-1000",
    "super-nintendo": "RA - Super Nintendo Entertainment System",
    "uzebox": "RA - Uzebox",
    "vectrex": "RA - GCE Vectrex",
    "virtual-boy": "RA - Nintendo Virtual Boy",
    "wasm-4": "RA - WASM-4",
    "watara-supervision": "RA - Watara Supervision",
    "wonderswan": "RA - WonderSwan",
    "wonderswan-color": "RA - WonderSwan",
}
RA_DIRECTORIES = tuple(dict.fromkeys(PLATFORM_DIRECTORIES.values()))
_PLATFORMS_BY_SLUG = {platform.slug: platform for platform in DARKOS_PLATFORMS}
_DISPLAY_SYSTEM = {
    directory: _PLATFORMS_BY_SLUG[slug].alias for slug, directory in PLATFORM_DIRECTORIES.items()
}
_REGION_WORDS = (
    "Australia",
    "Brazil",
    "Canada",
    "China",
    "Europe",
    "France",
    "Germany",
    "Italy",
    "Japan",
    "Korea",
    "Spain",
    "Taiwan",
    "USA",
    "World",
)


@dataclass(frozen=True, slots=True)
class MinervaEntry:
    """One file and its one-based position inside a platform torrent."""

    filename: str
    link: str
    file_index: int


class _DirectoryParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.entries: list[MinervaEntry] = []
        self._entry_depth = 0
        self._link = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div" and "entry" in (attributes.get("class") or "").split():
            self._entry_depth = 1
            self._link = ""
            self._text = []
        elif self._entry_depth:
            if tag == "div":
                self._entry_depth += 1
            elif tag == "a":
                self._link = attributes.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if not self._entry_depth or tag != "div":
            return
        self._entry_depth -= 1
        if self._entry_depth:
            return
        if urlparse(self._link).path.rstrip("/") != "/rom":
            return
        query = parse_qs(urlparse(self._link).query)
        paths = query.get("name", [])
        if len(paths) != 1:
            return
        filename = PurePosixPath(paths[0]).name
        if not filename:
            filename = " ".join(" ".join(self._text).split())
        if filename:
            self.entries.append(
                MinervaEntry(filename, urljoin(self.base_url, self._link), len(self.entries) + 1)
            )

    def handle_data(self, data: str) -> None:
        if self._entry_depth and data.strip():
            self._text.append(data.strip())


def parse_directory(html: str, base_url: str) -> list[MinervaEntry]:
    """Parse one Minerva browse directory in torrent file order."""

    parser = _DirectoryParser(base_url)
    parser.feed(html)
    return parser.entries


def _title_metadata(filename: str) -> tuple[str, str, str, str]:
    title = Path(filename).stem
    groups = re.findall(r"\(([^()]*)\)", title)
    region = next(
        (group for group in groups if any(word in group for word in _REGION_WORDS)),
        "",
    )
    version = next(
        (group for group in groups if re.match(r"(?i)(?:rev(?:ision)?\s*|v)\d", group)),
        "",
    )
    languages = next(
        (group for group in groups if re.fullmatch(r"(?:[A-Z][a-z](?:,[A-Z][a-z])*)", group)),
        "-",
    )
    return title, region, version, languages


class MinervaStore(GameStore):
    """Minerva's RetroAchievements collection, downloaded one torrent file at a time."""

    store_id = "minerva"
    display_name = "Minerva Archive"
    description = "RetroAchievements torrents (native Python)"

    def __init__(
        self,
        base_url: str,
        torrent_base_url: str,
        timeout_seconds: float = 30.0,
        cache_directory: Path | None = None,
        ttl_seconds: int = catalogue_ttl_seconds(DEFAULT_CATALOGUE_TTL_DAYS),
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._torrent_base_url = torrent_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._base = urlparse(self._base_url)
        torrent_base = urlparse(self._torrent_base_url)
        if self._base.scheme not in ("http", "https") or not self._base.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if torrent_base.scheme not in ("http", "https") or not torrent_base.netloc:
            raise ValueError("torrent_base_url must be an absolute HTTP(S) URL")
        self._ssl_context = ssl.create_default_context()
        self._entry_cache: dict[str, tuple[MinervaEntry, ...]] = {}
        self._configure_catalogue_cache(cache_directory, ttl_seconds)

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def download_referrer(self) -> str:
        return f"{self.base_url}/browse/RetroAchievements/"

    def platform_code(self, platform: Platform) -> str:
        if platform.slug == "all":
            return ""
        return PLATFORM_DIRECTORIES.get(platform.slug, "")

    def supports_platform(self, platform: Platform) -> bool:
        return platform.slug == "all" or platform.slug in PLATFORM_DIRECTORIES

    @property
    def headers(self) -> Mapping[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def search(
        self,
        system_code: str,
        query: str,
        catalog_progress: CatalogProgress | None = None,
    ) -> list[SearchResult]:
        catalogue = self._load_catalogue(system_code, catalog_progress)
        normalized_query = " ".join(query.split()).casefold()
        return [
            result for result in catalogue if result.title.casefold().startswith(normalized_query)
        ]

    def _fetch_catalogue(
        self,
        system_code: str,
        catalog_progress: CatalogProgress | None,
    ) -> list[SearchResult]:
        if system_code:
            if system_code not in RA_DIRECTORIES:
                raise StoreError("Minerva does not provide this platform in RetroAchievements.")
            directories = (system_code,)
        else:
            directories = RA_DIRECTORIES

        def fetch(directory: str) -> tuple[str, tuple[MinervaEntry, ...]]:
            return directory, self._entries(directory)

        results: list[SearchResult] = []
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="minerva") as executor:
            for completed, (directory, entries) in enumerate(
                executor.map(fetch, directories),
                start=1,
            ):
                for entry in entries:
                    title, region, version, languages = _title_metadata(entry.filename)
                    results.append(
                        SearchResult(
                            title=title,
                            link=entry.link,
                            system=_DISPLAY_SYSTEM[directory] if not system_code else "",
                            region=region,
                            version=version,
                            languages=languages,
                        )
                    )
                if catalog_progress is not None:
                    catalog_progress(completed, len(directories))
        return sorted(
            results, key=lambda result: (result.title.casefold(), result.system.casefold())
        )

    def validate_detail_url(self, url: str) -> bool:
        target = self._detail_target(url)
        return target is not None

    def retrieve_download_url(self, detail_url: str) -> str:
        directory, _filename, _file_index = self._download_metadata(detail_url)
        torrent_name = f"Minerva_Myrient - RetroAchievements - {directory}.torrent"
        return f"{self._torrent_base_url}/{quote(torrent_name)}"

    def download_request(self, detail_url: str) -> MediaDownload:
        directory, filename, file_index = self._download_metadata(detail_url)
        torrent_name = f"Minerva_Myrient - RetroAchievements - {directory}.torrent"
        return MediaDownload(
            url=f"{self._torrent_base_url}/{quote(torrent_name)}",
            torrent_file_index=file_index,
            expected_filename=filename,
        )

    def _download_metadata(self, detail_url: str) -> tuple[str, str, int]:
        target = self._detail_target(detail_url)
        if target is None:
            raise StoreError(f"Not a valid RetroAchievements detail URL for {self._base.netloc}.")
        directory, filename = target
        entry = next(
            (item for item in self._entries(directory) if item.filename == filename),
            None,
        )
        if entry is None:
            raise StoreError("The selected game is no longer present in Minerva's catalogue.")
        return directory, filename, entry.file_index

    def _detail_target(self, url: str) -> tuple[str, str] | None:
        parsed = urlparse(url.strip())
        if (
            parsed.scheme != self._base.scheme
            or parsed.netloc.casefold() != self._base.netloc.casefold()
            or parsed.path.rstrip("/") != "/rom"
            or parsed.fragment
        ):
            return None
        query = parse_qs(parsed.query, keep_blank_values=True)
        names = query.get("name", [])
        if set(query) != {"name"} or len(names) != 1:
            return None
        raw_path = names[0].removeprefix("./")
        if "\\" in raw_path:
            return None
        parts = PurePosixPath(raw_path).parts
        if len(parts) != 3 or parts[0] != "RetroAchievements" or ".." in parts:
            return None
        directory, filename = parts[1], parts[2]
        if directory not in RA_DIRECTORIES or not filename:
            return None
        return directory, filename

    def _entries(self, directory: str) -> tuple[MinervaEntry, ...]:
        cached = self._entry_cache.get(directory)
        if cached is not None:
            return cached
        url = f"{self.base_url}/browse/RetroAchievements/{quote(directory)}/"
        entries = tuple(parse_directory(self._get_text(url), self.base_url))
        if not entries:
            raise StoreError(f"Minerva returned an empty catalogue for {directory}.")
        self._entry_cache[directory] = entries
        return entries

    def _get_text(self, url: str) -> str:
        request = Request(url, headers=dict(self.headers))
        last_error: BaseException | None = None
        for attempt in range(3):
            try:
                with urlopen(
                    request,
                    timeout=self.timeout_seconds,
                    context=self._ssl_context,
                ) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return cast(str, response.read().decode(charset, errors="replace"))
            except HTTPError as error:
                if error.code < 500 and error.code != 429:
                    raise StoreError(
                        "Minerva returned HTTP %d." % error.code,
                        error.code,
                    ) from error
                last_error = error
            except (URLError, TimeoutError, OSError) as error:
                last_error = error
            if attempt < 2:
                time.sleep(0.25 * (2**attempt))
        reason = getattr(last_error, "reason", last_error)
        raise StoreError(f"Could not reach Minerva after 3 attempts: {reason}") from last_error
