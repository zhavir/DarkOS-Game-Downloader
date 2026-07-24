"""R36S compatibility ratings and cached r36sgamelist.com title matching."""

import json
import re
import ssl
import unicodedata
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from time import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from dw_cli.models import Platform, SearchResult
from dw_cli.store import USER_AGENT

R36S_GAME_LIST_URL = "https://r36sgamelist.com"
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

_SCRIPT_PATTERN = re.compile(r'(?:src|href)="([^"?#]+\.js(?:\?[^"#]*)?)"')
_GAME_PATTERN = re.compile(
    r'\{"name":"((?:\\.|[^"\\])*)","console":"((?:\\.|[^"\\])*)",'
    r'"slug":"((?:\\.|[^"\\])*)"'
)
_BRACKETED_TEXT = re.compile(r"\s*[\[(][^\])]*[\])]\s*")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")

# r36sgamelist.com currently assigns compatibility at console level.  A title
# match therefore confirms that the game is listed; the level still comes from
# its console's RK3326 profile.
_CONSOLE_LEVELS: dict[str, str] = {
    "arcade": "Perfect",
    "capcom play system i": "Perfect",
    "capcom play system ii": "Perfect",
    "dreamcast": "Limited",
    "famicom": "Perfect",
    "gameboy advance": "Perfect",
    "gameboy color": "Perfect",
    "mega drive": "Perfect",
    "nes": "Perfect",
    "neogeo": "Perfect",
    "neogeo pocket": "Perfect",
    "neogeo pocket color": "Perfect",
    "nintendo 64": "Playable",
    "nintendo ds": "Limited",
    "pc engine": "Perfect",
    "playstation 1": "Perfect",
    "psp": "Limited",
    "sega genesis": "Perfect",
    "sega naomi": "Limited",
    "sfc": "Perfect",
    "snes": "Perfect",
}

_CONSOLE_ALIASES: dict[str, str] = {
    "arcade": "arcade",
    "mame": "arcade",
    "mame 2003": "arcade",
    "mame 2010": "arcade",
    "cps1": "capcom play system i",
    "cps 1": "capcom play system i",
    "capcom play system 1": "capcom play system i",
    "cps2": "capcom play system ii",
    "cps 2": "capcom play system ii",
    "capcom play system 2": "capcom play system ii",
    "dc": "dreamcast",
    "dreamcast": "dreamcast",
    "famicom": "famicom",
    "gba": "gameboy advance",
    "game boy advance": "gameboy advance",
    "gameboy advance": "gameboy advance",
    "gbc": "gameboy color",
    "game boy color": "gameboy color",
    "gameboy color": "gameboy color",
    "gen": "mega drive",
    "genesis": "sega genesis",
    "mega drive": "mega drive",
    "sega genesis": "sega genesis",
    "nes": "nes",
    "nintendo": "nes",
    "nintendo entertainment system": "nes",
    "neogeo": "neogeo",
    "neo geo": "neogeo",
    "ngp": "neogeo pocket",
    "neo geo pocket": "neogeo pocket",
    "neogeo pocket": "neogeo pocket",
    "ngpc": "neogeo pocket color",
    "neo geo pocket color": "neogeo pocket color",
    "neogeo pocket color": "neogeo pocket color",
    "n64": "nintendo 64",
    "nintendo 64": "nintendo 64",
    "nds": "nintendo ds",
    "ds": "nintendo ds",
    "nintendo ds": "nintendo ds",
    "pce": "pc engine",
    "pc engine": "pc engine",
    "turbografx 16": "pc engine",
    "ps1": "playstation 1",
    "psx": "playstation 1",
    "playstation": "playstation 1",
    "playstation 1": "playstation 1",
    "psp": "psp",
    "playstation portable": "psp",
    "naomi": "sega naomi",
    "sega naomi": "sega naomi",
    "sfc": "sfc",
    "snes": "snes",
    "super famicom": "sfc",
    "super nintendo": "snes",
}

_UNSUPPORTED_NAMES = frozenset(
    {
        "3ds",
        "gamecube",
        "nintendo 3ds",
        "nintendo switch",
        "nintendo wii",
        "nintendo wii u",
        "playstation 2",
        "playstation 3",
        "playstation 4",
        "playstation 5",
        "playstation vita",
        "ps2",
        "ps3",
        "ps4",
        "ps5",
        "ps vita",
        "psvita",
        "switch",
        "vita",
        "wii",
        "wii u",
        "wiiu",
        "xbox",
        "xbox 360",
        "xbox one",
        "xbox360",
    }
)

type GameKey = tuple[str, str]
type FetchText = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class CompatibilityInfo:
    """Compatibility displayed next to one remote search result."""

    level: str
    title_listed: bool

    @property
    def short_label(self) -> str:
        """Return the compact results-list label."""

        if self.level == "Not listed":
            return self.level
        return f"{self.level}{' - listed' if self.title_listed else ''}"

    @property
    def detail_label(self) -> str:
        """Explain whether the live catalogue matched this exact title."""

        if self.level == "Not listed":
            return "Not listed by r36sgamelist.com"
        qualifier = "title listed" if self.title_listed else "platform rating"
        return f"{self.level} ({qualifier})"


def normalize_title(value: str) -> str:
    """Normalize regional/version title variants for conservative exact matching."""

    without_brackets = _BRACKETED_TEXT.sub(" ", value)
    decomposed = unicodedata.normalize("NFKD", without_brackets.casefold())
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(_NON_ALPHANUMERIC.sub(" ", ascii_text).split())


def normalize_console(value: str) -> str | None:
    """Map remote and dArkOS console spellings to the compatibility catalogue."""

    normalized = " ".join(_NON_ALPHANUMERIC.sub(" ", value.casefold()).split())
    return _CONSOLE_ALIASES.get(normalized)


def is_unsupported_system(value: str) -> bool:
    """Return whether a console family cannot reasonably run on an RK3326 R36S."""

    normalized = " ".join(_NON_ALPHANUMERIC.sub(" ", value.casefold()).split())
    return normalized in _UNSUPPORTED_NAMES or any(
        normalized.startswith(f"{name} ") or normalized.endswith(f" {name}")
        for name in _UNSUPPORTED_NAMES
    )


def filter_supported_results(results: Sequence[SearchResult]) -> list[SearchResult]:
    """Remove explicitly unsupported consoles from all-platform remote results."""

    return [result for result in results if not is_unsupported_system(result.system)]


class R36SCompatibilityClient:
    """Fetch and cache the frontend-only r36sgamelist.com game index."""

    def __init__(
        self,
        cache_path: Path,
        base_url: str = R36S_GAME_LIST_URL,
        timeout_seconds: float = 30.0,
        fetch_text: FetchText | None = None,
    ) -> None:
        self.cache_path = cache_path
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._fetch_text_override = fetch_text
        self._game_index: frozenset[GameKey] | None = None

    def lookup_many(
        self,
        results: Sequence[SearchResult],
        platform: Platform,
    ) -> list[CompatibilityInfo]:
        """Return one compatibility record for each result, preserving order."""

        consoles = [self._result_console(result, platform) for result in results]
        should_load_index = any(console is not None for console in consoles)
        index = self._load_game_index() if should_load_index else frozenset()
        return [
            self._lookup(result.title, console, index)
            for result, console in zip(results, consoles, strict=True)
        ]

    @staticmethod
    def _result_console(result: SearchResult, platform: Platform) -> str | None:
        candidates = (
            result.system,
            platform.alias,
            platform.name,
            platform.slug,
            *(platform.arkos_folders),
        )
        return next(
            (console for value in candidates if value and (console := normalize_console(value))),
            None,
        )

    @staticmethod
    def _lookup(
        title: str,
        console: str | None,
        index: frozenset[GameKey],
    ) -> CompatibilityInfo:
        if console is None:
            return CompatibilityInfo("Not listed", False)
        level = _CONSOLE_LEVELS[console]
        return CompatibilityInfo(level, (console, normalize_title(title)) in index)

    def _load_game_index(self) -> frozenset[GameKey]:
        if self._game_index is not None:
            return self._game_index
        cached = self._read_cache()
        if cached is not None:
            self._game_index = cached
            return cached
        try:
            index = self._download_game_index()
        except OSError, TimeoutError, ValueError:
            index = frozenset()
        if index:
            self._write_cache(index)
        self._game_index = index
        return index

    def _download_game_index(self) -> frozenset[GameKey]:
        home = self._fetch_text(self.base_url)
        script_urls = tuple(
            dict.fromkeys(
                urljoin(f"{self.base_url}/", unescape(match))
                for match in _SCRIPT_PATTERN.findall(home)
                if self._same_origin(urljoin(f"{self.base_url}/", unescape(match)))
            )
        )
        with ThreadPoolExecutor(max_workers=4) as executor:
            documents = (home, *executor.map(self._fetch_optional, script_urls))
            index = frozenset(game for document in documents for game in parse_game_index(document))
        if len(index) < 100:
            raise ValueError("r36sgamelist.com did not expose a usable frontend game index")
        return index

    def _same_origin(self, url: str) -> bool:
        expected = urlparse(self.base_url)
        parsed = urlparse(url)
        return parsed.scheme == expected.scheme and parsed.netloc == expected.netloc

    def _fetch_text(self, url: str) -> str:
        if self._fetch_text_override is not None:
            return self._fetch_text_override(url)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
        context = ssl.create_default_context()
        with urlopen(request, timeout=self.timeout_seconds, context=context) as response:
            return response.read().decode("utf-8", errors="replace")

    def _fetch_optional(self, url: str) -> str:
        try:
            return self._fetch_text(url)
        except OSError, TimeoutError, ValueError:
            return ""

    def _read_cache(self) -> frozenset[GameKey] | None:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched_at = float(payload["fetched_at"])
            games = payload["games"]
            if time() - fetched_at > CACHE_MAX_AGE_SECONDS or not isinstance(games, list):
                return None
            index = frozenset((str(item[0]), str(item[1])) for item in games)
        except IndexError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError:
            return None
        return index if index else None

    def _write_cache(self, index: frozenset[GameKey]) -> None:
        payload = {"fetched_at": time(), "games": sorted(index)}
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError:
            pass


def parse_game_index(document: str) -> frozenset[GameKey]:
    """Extract the title/console objects embedded in Next.js frontend chunks."""

    games: set[GameKey] = set()
    for raw_title, raw_console, _raw_slug in _GAME_PATTERN.findall(document):
        try:
            title = json.loads(f'"{raw_title}"')
            console_value = json.loads(f'"{raw_console}"')
        except json.JSONDecodeError:
            continue
        console = normalize_console(console_value)
        normalized_title = normalize_title(title)
        if console is not None and normalized_title:
            games.add((console, normalized_title))
    return frozenset(games)
