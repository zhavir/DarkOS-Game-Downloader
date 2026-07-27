from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ph.config import Config
from ph.minerva_store import MinervaStore
from ph.models import Platform, SearchResult
from ph.store import CatalogProgress, GameStore, StoreError
from ph.store_catalog import StoreCatalog
from ph.vimm_store import VimmStore


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


def test_vimm_environment_configuration_is_explicit_and_drops_generic_name() -> None:
    config = Config.from_environment(
        {
            "PH_VIMM_BASE_URL": "https://vimm.test/",
            "PH_TIMEOUT": "12.5",
        }
    )

    assert config.vimm_base_url == "https://vimm.test"
    assert config.timeout_seconds == 12.5


def test_catalog_accepts_future_store_without_tui_or_cli_changes() -> None:
    future = FutureStore()
    catalog = StoreCatalog((future,))

    assert catalog.find("future") is future
    assert catalog.find("missing") is None


def test_store_cache_contract_handles_disabled_and_configured_caches(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    future = FutureStore()
    assert future.catalogue_cache_status("GBA") is None
    assert future.catalogue_cache_file_count() == 0
    future.set_catalogue_ttl(20)
    with pytest.raises(StoreError, match="does not expose"):
        future.refresh_catalogue("GBA")

    future._configure_catalogue_cache(tmp_path, 10)
    result = SearchResult("Future Game", "https://future.example/games/1")
    mocker.patch.object(future, "_fetch_catalogue", return_value=[result])
    assert future.refresh_catalogue("GBA") == [result]
    assert future.catalogue_cache_status("GBA") is not None
    assert future.catalogue_cache_file_count() == 1
    future.set_catalogue_ttl(30)
    assert future._catalogue_cache is not None
    assert future._catalogue_cache.ttl_seconds == 30
