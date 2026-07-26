"""Structured, atomic game catalogue caches shared by every store."""

import json
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import cast
from urllib.parse import quote

from ph.cache_policy import DEFAULT_CATALOGUE_TTL_DAYS, catalogue_ttl_seconds
from ph.models import SearchResult

LOGGER = logging.getLogger(__name__)
CACHE_SCHEMA_VERSION = 1

type CatalogueFetcher = Callable[[], Sequence[SearchResult]]


class CatalogueCacheError(RuntimeError):
    """A store catalogue could not be saved for offline use."""


@dataclass(frozen=True, slots=True)
class StoreCacheStatus:
    """User-facing state of one store/platform catalogue file."""

    path: Path
    fetched_at: float
    result_count: int
    stale: bool


@dataclass(frozen=True, slots=True)
class _CachedCatalogue:
    fetched_at: float
    results: tuple[SearchResult, ...]


class GameCatalogueCache:
    """Cache complete store catalogues by stable store and platform identifiers."""

    def __init__(
        self,
        root: Path,
        store_id: str,
        source_url: str,
        ttl_seconds: int = catalogue_ttl_seconds(DEFAULT_CATALOGUE_TTL_DAYS),
    ) -> None:
        self.directory = root / "game-catalogues" / store_id
        self.store_id = store_id
        self.source_url = source_url.rstrip("/")
        self.ttl_seconds = ttl_seconds

    def _is_stale(self, cached: _CachedCatalogue) -> bool:
        return time() - cached.fetched_at > self.ttl_seconds

    def path_for(self, system_code: str) -> Path:
        """Return a readable, filesystem-safe path for one platform catalogue."""

        identifier = quote(system_code, safe="") if system_code else "all"
        return self.directory / f"{identifier}.json"

    def status(self, system_code: str) -> StoreCacheStatus | None:
        """Describe a valid cache without contacting the store."""

        path = self.path_for(system_code)
        cached = self._read(path, system_code)
        if cached is None:
            return None
        return StoreCacheStatus(
            path, cached.fetched_at, len(cached.results), self._is_stale(cached)
        )

    def cached_files(self) -> tuple[Path, ...]:
        """List structured catalogue files already stored for this source."""

        try:
            return tuple(sorted(self.directory.glob("*.json")))
        except OSError:
            return ()

    def get_or_fetch(
        self,
        system_code: str,
        fetcher: CatalogueFetcher,
        *,
        force: bool = False,
    ) -> tuple[SearchResult, ...]:
        """Use a fresh cache, refreshing expired data and retaining stale fallback data."""

        path = self.path_for(system_code)
        cached = self._read(path, system_code)
        if cached is not None and not self._is_stale(cached) and not force:
            LOGGER.debug(
                "Using game catalogue cache store=%s system=%r results=%d",
                self.store_id,
                system_code,
                len(cached.results),
            )
            return cached.results
        try:
            results = tuple(fetcher())
        except OSError, TimeoutError, ValueError, RuntimeError:
            if cached is None or force:
                raise
            LOGGER.warning(
                "Store refresh failed; using stale catalogue store=%s system=%r",
                self.store_id,
                system_code,
                exc_info=True,
            )
            return cached.results
        self._write(path, system_code, results, strict=force)
        return results

    def _read(self, path: Path, system_code: str) -> _CachedCatalogue | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version") != CACHE_SCHEMA_VERSION
                or payload.get("store_id") != self.store_id
                or payload.get("system_code") != system_code
                or payload.get("source_url") != self.source_url
                or not isinstance(payload.get("results"), list)
            ):
                return None
            fetched_at = float(payload["fetched_at"])
            results = tuple(_parse_result(item) for item in payload["results"])
        except KeyError, OSError, TypeError, ValueError, json.JSONDecodeError:
            return None
        return _CachedCatalogue(fetched_at, results)

    def _write(
        self,
        path: Path,
        system_code: str,
        results: tuple[SearchResult, ...],
        *,
        strict: bool,
    ) -> None:
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "fetched_at": time(),
            "store_id": self.store_id,
            "system_code": system_code,
            "source_url": self.source_url,
            "results": [asdict(result) for result in results],
        }
        temporary = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            if strict:
                raise CatalogueCacheError(f"Could not save the game catalogue: {error}") from error
            LOGGER.warning("Could not cache game catalogue path=%s: %s", path, error)


def _parse_result(payload: object) -> SearchResult:
    if not isinstance(payload, dict):
        raise ValueError("invalid cached search result")
    values = cast(dict[object, object], payload)
    return SearchResult(
        title=_required_string(values, "title"),
        link=_required_string(values, "link"),
        system=_required_string(values, "system"),
        region=_required_string(values, "region"),
        version=_required_string(values, "version"),
        languages=_required_string(values, "languages"),
        rating=_required_string(values, "rating"),
    )


def _required_string(payload: dict[object, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ValueError("invalid cached search result")
    return value
