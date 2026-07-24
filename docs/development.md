# Development and local testing

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Linux, macOS, or WSL2 terminal with `curses` support
- Docker only when building the ARM64 R36S release ZIP

The project pins Python 3.14. uv can install it automatically.

## Install the locked environment

```sh
uv sync --frozen
uv run prek install
```

## Run the safe offline demo

```sh
uv run python -m scripts.run_local_demo
```

The demo creates two temporary ROM cards under `.local-test`, starts a localhost fake catalogue,
and launches the production TUI. Its fake ROM downloads are tiny test payloads.

## Test and type-check

```sh
uv run prek run --all-files
uv run pytest
```

The full test suite includes offline unit/integration tests and real-service E2E contracts for
Vimm, Minerva's browse and torrent endpoints, a complete verified tiny Arduboy download through
real peers, and the R36S compatibility frontend. Use this to skip network tests:

```sh
uv run pytest -m "not live"
```

## Documentation

Preview the Zensical site locally:

```sh
uv run zensical serve
```

Build exactly what GitHub Pages publishes:

```sh
uv run zensical build --clean --strict
```

The generated `site/` directory is ignored. Pushing documentation changes to `main` invokes the
Pages workflow and publishes the generated artifact.

## Add another download store

Implement the abstract `GameStore` contract in `src/dw_cli/store.py`, then register the concrete
class in `StoreCatalog.from_config`. Search, direct downloads, installed-game updates, and CLI
automation consume the registry and do not need store-specific branches. Each implementation owns
its platform-code translation, search behavior, detail-URL validation, media-URL resolution, base
URL, and download referrer. `MediaDownload` can describe either a direct URL or a one-based file
selection in a BitTorrent v1 torrent; both are handled natively by the shared downloader.

## Build all release artifacts

```sh
sh scripts/build_artifacts.sh
```

This creates the uv wheel and source distribution, downloads a fresh Python 3.14 ARM64 runtime,
performs an uncached PyInstaller build, verifies the ELF architecture, and writes the self-contained
R36S ZIP under `dist/`.
