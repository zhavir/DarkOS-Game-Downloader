"""Configured game-store registry and lookup helpers."""

from dataclasses import dataclass
from typing import Self

from ph.cache_policy import DEFAULT_CATALOGUE_TTL_DAYS, catalogue_ttl_seconds
from ph.config import Config
from ph.minerva_store import MinervaStore
from ph.store import GameStore
from ph.vimm_store import VimmStore


@dataclass(frozen=True, slots=True)
class StoreCatalog:
    """The stores available to this application run."""

    stores: tuple[GameStore, ...]

    @classmethod
    def from_config(
        cls,
        config: Config,
        ttl_seconds: int = catalogue_ttl_seconds(DEFAULT_CATALOGUE_TTL_DAYS),
    ) -> Self:
        """Create every enabled concrete store from application configuration."""

        available: tuple[GameStore, ...] = (
            VimmStore(
                config.vimm_base_url,
                config.timeout_seconds,
                config.download_directory,
                ttl_seconds,
            ),
            MinervaStore(
                config.minerva_base_url,
                config.minerva_torrent_base_url,
                config.timeout_seconds,
                config.download_directory,
                ttl_seconds,
            ),
        )
        enabled = set(config.enabled_stores)
        return cls(tuple(store for store in available if store.store_id in enabled))

    def find(self, store_id: str) -> GameStore | None:
        """Resolve a store identifier case-insensitively."""

        normalized = store_id.strip().casefold()
        return next(
            (store for store in self.stores if store.store_id.casefold() == normalized),
            None,
        )
