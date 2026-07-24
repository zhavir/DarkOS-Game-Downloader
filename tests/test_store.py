from pathlib import Path

from dw_cli.config import Config
from dw_cli.minerva_store import MinervaStore
from dw_cli.models import Platform, SearchResult
from dw_cli.store import CatalogProgress, GameStore
from dw_cli.store_catalog import StoreCatalog
from dw_cli.vimm_store import VimmStore


class FutureStore(GameStore):
    store_id = "future"
    display_name = "Future Store"
    description = "Test implementation"

    @property
    def base_url(self) -> str:
        return "https://future.example"

    @property
    def download_referrer(self) -> str:
        return f"{self.base_url}/games/"

    def platform_code(self, platform: Platform) -> str:
        return f"future-{platform.slug}"

    def search(
        self,
        system_code: str,
        query: str,
        catalog_progress: CatalogProgress | None = None,
    ) -> list[SearchResult]:
        return [SearchResult(f"{system_code}: {query}", f"{self.base_url}/games/1")]

    def validate_detail_url(self, url: str) -> bool:
        return url.startswith(self.base_url)

    def retrieve_download_url(self, detail_url: str) -> str:
        return f"{detail_url}/download"


def test_configured_catalog_exposes_all_stores_through_store_contract(tmp_path: Path) -> None:
    config = Config("https://vimm.example", tmp_path, (), 12)

    catalog = StoreCatalog.from_config(config)
    store = catalog.find("VIMM")

    assert isinstance(store, VimmStore)
    assert store.store_id == "vimm"
    assert store.base_url == "https://vimm.example"
    assert store.download_referrer == "https://vimm.example/vault/"
    minerva = catalog.find("MINERVA")
    assert isinstance(minerva, MinervaStore)
    assert minerva.base_url == "https://minerva-archive.org"


def test_catalog_accepts_future_store_without_tui_or_cli_changes() -> None:
    future = FutureStore()
    catalog = StoreCatalog((future,))

    assert catalog.find("future") is future
    assert catalog.find("missing") is None
