"""R36S compatibility ratings and cached r36sgamelist.com title matching."""

import json
import logging
import os
import re
import ssl
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from time import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from dw_cli.models import Platform, SearchResult
from dw_cli.store import USER_AGENT

R36S_GAME_LIST_URL = "https://r36sgamelist.com"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

LOGGER = logging.getLogger(__name__)

_SCRIPT_PATTERN = re.compile(r'(?:src|href)="([^"?#]+\.js(?:\?[^"#]*)?)"')
_GAME_PATTERN = re.compile(
    r'\{"name":"((?:\\.|[^"\\])*)","console":"((?:\\.|[^"\\])*)",'
    r'"slug":"((?:\\.|[^"\\])*)"'
)
_BRACKETED_TEXT = re.compile(r"\s*[\[(][^\])]*[\])]\s*")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_MATCH_THRESHOLD = 0.82
_AMBIGUITY_MARGIN = 0.04
_TITLE_NOISE = frozenset(
    {
        "beta",
        "demo",
        "en",
        "eng",
        "europe",
        "eur",
        "fr",
        "fre",
        "germany",
        "hack",
        "ita",
        "italy",
        "japan",
        "jpn",
        "korea",
        "proto",
        "prototype",
        "rev",
        "revision",
        "spa",
        "spain",
        "uk",
        "usa",
        "version",
    }
)

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
type TitleIndex = Mapping[str, Sequence[str]]


class CompatibilityError(RuntimeError):
    """The R36S Game List catalogue could not be downloaded or stored."""


@dataclass(frozen=True, slots=True)
class CompatibilityInfo:
    """Compatibility displayed next to one remote search result."""

    level: str
    title_listed: bool
    match_score: float | None = None

    @property
    def short_label(self) -> str:
        """Return the compact results-list label."""

        if self.level == "Not listed":
            return self.level
        if self.title_listed and self.match_score is not None:
            return f"{self.level} - {round(self.match_score * 100)}% match"
        return f"{self.level}{' - listed' if self.title_listed else ''}"

    @property
    def detail_label(self) -> str:
        """Explain whether the live catalogue reliably matched this title."""

        if self.level == "Not listed":
            return "Not listed by r36sgamelist.com"
        qualifier = (
            f"title match {round(self.match_score * 100)}%"
            if self.title_listed and self.match_score is not None
            else "title listed"
            if self.title_listed
            else "platform rating"
        )
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
        match_indexes = _build_match_indexes(index)
        return [
            self._lookup(result.title, console, index, match_indexes.get(console, {}))
            for result, console in zip(results, consoles, strict=True)
        ]

    def load(self) -> frozenset[GameKey] | None:
        """Load the local catalogue, including a stale but still usable copy."""

        cached = self._read_cache()
        if cached is not None:
            self._game_index = cached
        return cached

    def refresh(self) -> int:
        """Explicitly replace the cache with the current frontend catalogue."""

        try:
            index = self._download_game_index()
            self._write_cache(index, strict=True)
        except CompatibilityError:
            raise
        except (OSError, TimeoutError, ValueError) as error:
            raise CompatibilityError(f"Could not update the R36S Game List: {error}") from error
        self._game_index = index
        LOGGER.info("R36S Game List cached games=%d path=%s", len(index), self.cache_path)
        return len(index)

    def cache_age_seconds(self) -> float | None:
        """Return the age of a valid local cache, or ``None`` when unavailable."""

        payload = self._read_cache_payload()
        return None if payload is None else max(0.0, time() - payload[0])

    def cache_is_stale(self) -> bool:
        """Return whether the local catalogue is older than seven days."""

        age = self.cache_age_seconds()
        return age is not None and age > CACHE_TTL_SECONDS

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
        candidate_index: TitleIndex,
    ) -> CompatibilityInfo:
        if console is None:
            return CompatibilityInfo("Not listed", False)
        level = _CONSOLE_LEVELS[console]
        normalized = normalize_title(title)
        if (console, normalized) in index:
            return CompatibilityInfo(level, True, 1.0)
        candidates = {
            candidate
            for key in _title_match_keys(normalized)
            for candidate in candidate_index.get(key, ())
        }
        ranked = sorted(
            (title_match_score(normalized, candidate), candidate) for candidate in candidates
        )
        if not ranked:
            return CompatibilityInfo(level, False)
        best_score, _best_title = ranked[-1]
        second_score = ranked[-2][0] if len(ranked) > 1 else 0.0
        accepted = best_score >= _MATCH_THRESHOLD and (
            best_score >= 0.97 or best_score - second_score >= _AMBIGUITY_MARGIN
        )
        return CompatibilityInfo(level, accepted, best_score if accepted else None)

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
        payload = self._read_cache_payload()
        return None if payload is None else payload[1]

    def _read_cache_payload(self) -> tuple[float, frozenset[GameKey]] | None:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched_at = float(payload["fetched_at"])
            games = payload["games"]
            if not isinstance(games, list):
                return None
            index = frozenset((str(item[0]), str(item[1])) for item in games)
        except IndexError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError:
            return None
        return (fetched_at, index) if index else None

    def _write_cache(self, index: frozenset[GameKey], *, strict: bool = False) -> None:
        payload = {"fetched_at": time(), "games": sorted(index)}
        temporary = self.cache_path.with_name(self.cache_path.name + ".tmp")
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary, self.cache_path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            if strict:
                raise CompatibilityError(
                    f"Could not save the R36S Game List catalogue: {error}"
                ) from error
            LOGGER.warning("Could not cache the R36S Game List: %s", error)


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


def title_match_score(left: str, right: str) -> float:
    """Score normalized titles while discounting common release metadata."""

    left = normalize_title(left)
    right = normalize_title(right)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = left.split()
    right_tokens = right.split()
    left_core = _core_title_tokens(left_tokens, right_tokens)
    right_core = _core_title_tokens(right_tokens, left_tokens)
    if left_core and left_core == right_core:
        return 0.98

    left_value = " ".join(left_core or left_tokens)
    right_value = " ".join(right_core or right_tokens)
    sequence = SequenceMatcher(None, left_value, right_value, autojunk=False).ratio()
    compact = SequenceMatcher(
        None,
        left_value.replace(" ", ""),
        right_value.replace(" ", ""),
        autojunk=False,
    ).ratio()
    left_set = set(left_core or left_tokens)
    right_set = set(right_core or right_tokens)
    token_score = 2 * len(left_set & right_set) / (len(left_set) + len(right_set))
    return max(sequence * 0.7 + token_score * 0.3, compact * 0.85 + token_score * 0.15)


def _core_title_tokens(tokens: Sequence[str], other_tokens: Sequence[str]) -> tuple[str, ...]:
    core: list[str] = []
    shared = set(other_tokens)
    skip_revision_number = False
    for token in tokens:
        if token in ("rev", "revision"):
            skip_revision_number = True
            continue
        if token in _TITLE_NOISE and token not in shared:
            continue
        if skip_revision_number and re.fullmatch(r"v?\d+(?:\.\d+)*", token):
            skip_revision_number = False
            continue
        skip_revision_number = False
        core.append(token)
    return tuple(core)


def _build_match_indexes(index: frozenset[GameKey]) -> dict[str, dict[str, tuple[str, ...]]]:
    mutable: dict[str, dict[str, list[str]]] = {}
    for console, title in index:
        console_index = mutable.setdefault(console, {})
        for key in _title_match_keys(title):
            console_index.setdefault(key, []).append(title)
    return {
        console: {key: tuple(titles) for key, titles in title_index.items()}
        for console, title_index in mutable.items()
    }


def _title_match_keys(title: str) -> frozenset[str]:
    tokens = normalize_title(title).split()
    meaningful = {token for token in tokens if len(token) >= 3 and token not in {"and", "the"}}
    compact = "".join(tokens)
    if len(compact) >= 4:
        meaningful.add(f"#{compact[:4]}")
    return frozenset(meaningful)
