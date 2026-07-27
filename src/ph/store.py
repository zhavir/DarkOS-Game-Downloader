"""Store contracts shared by the TUI, CLI, and concrete download sources."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from ph.models import MediaDownload, Platform, SearchResult
from ph.store_cache import GameCatalogueCache, StoreCacheStatus

type CatalogProgress = Callable[[int, int], None]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class StoreError(RuntimeError):
    """A user-facing store network or response error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GameStore(ABC):
    """A searchable source that can resolve its own game detail links."""

    store_id: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]
    timeout_seconds: float

    def _configure_catalogue_cache(
        self,
        cache_directory: Path | None,
        ttl_seconds: int,
    ) -> None:
        self._catalogue_cache = (
            GameCatalogueCache(cache_directory, self.store_id, self.base_url, ttl_seconds)
            if cache_directory is not None
            else None
        )

    def _load_catalogue(
        self,
        system_code: str,
        catalog_progress: CatalogProgress | None,
        *,
        force: bool = False,
    ) -> tuple[SearchResult, ...]:
        def fetcher() -> list[SearchResult]:
            return self._fetch_catalogue(system_code, catalog_progress)

        cache = getattr(self, "_catalogue_cache", None)
        if cache is None:
            return tuple(fetcher())
        return cache.get_or_fetch(system_code, fetcher, force=force)

    def _fetch_catalogue(
        self,
        system_code: str,
        catalog_progress: CatalogProgress | None,
    ) -> list[SearchResult]:
        raise StoreError(f"{self.display_name} does not expose a cacheable catalogue.")

    def refresh_catalogue(
        self,
        system_code: str,
        catalog_progress: CatalogProgress | None = None,
    ) -> list[SearchResult]:
        """Force-download and atomically replace one platform catalogue."""

        return list(self._load_catalogue(system_code, catalog_progress, force=True))

    def catalogue_cache_status(self, system_code: str) -> StoreCacheStatus | None:
        """Return local cache state for one platform without network access."""

        cache = getattr(self, "_catalogue_cache", None)
        if cache is None:
            return None
        return cache.status(system_code)

    def catalogue_cache_file_count(self) -> int:
        """Return how many structured catalogue files exist for this store."""

        cache = getattr(self, "_catalogue_cache", None)
        if cache is None:
            return 0
        return len(cache.cached_files())

    def set_catalogue_ttl(self, ttl_seconds: int) -> None:
        """Apply a changed cache lifetime without rebuilding the store client."""

        cache = getattr(self, "_catalogue_cache", None)
        if cache is not None:
            cache.ttl_seconds = ttl_seconds

    def set_network_timeout(self, timeout_seconds: float) -> None:
        """Apply a changed network timeout without rebuilding the store client."""

        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return the configured root URL for this store."""

    @property
    @abstractmethod
    def download_referrer(self) -> str:
        """Return the HTTP referrer expected while downloading store media."""

    @abstractmethod
    def platform_code(self, platform: Platform) -> str:
        """Translate shared platform metadata to this store's identifier."""

    def supports_platform(self, platform: Platform) -> bool:
        """Return whether this store can search the shared platform."""

        return True

    @abstractmethod
    def search(
        self,
        system_code: str,
        query: str,
        catalog_progress: CatalogProgress | None = None,
    ) -> list[SearchResult]:
        """Search this store using its platform identifier and title prefix."""

    @abstractmethod
    def validate_detail_url(self, url: str) -> bool:
        """Return whether a detail URL belongs to this store."""

    @abstractmethod
    def retrieve_download_url(self, detail_url: str) -> str:
        """Resolve one store detail page to its downloadable media URL."""

    def download_request(self, detail_url: str) -> MediaDownload:
        """Resolve download metadata; direct-download stores only need the URL."""

        return MediaDownload(self.retrieve_download_url(detail_url))
