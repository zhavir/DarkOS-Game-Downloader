"""Store contracts shared by the TUI, CLI, and concrete download sources."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar

from dw_cli.models import MediaDownload, Platform, SearchResult

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
