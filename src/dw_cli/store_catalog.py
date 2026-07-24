"""Configured game-store registry and lookup helpers."""

from dataclasses import dataclass
from typing import Self

from dw_cli.config import Config
from dw_cli.minerva_store import MinervaStore
from dw_cli.store import GameStore
from dw_cli.vimm_store import VimmStore


@dataclass(frozen=True, slots=True)
class StoreCatalog:
    """The stores available to this application run."""

    stores: tuple[GameStore, ...]

    @classmethod
    def from_config(cls, config: Config) -> Self:
        """Create every enabled concrete store from application configuration."""

        available: tuple[GameStore, ...] = (
            VimmStore(config.base_url, config.timeout_seconds),
            MinervaStore(
                config.minerva_base_url,
                config.minerva_torrent_base_url,
                config.timeout_seconds,
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
