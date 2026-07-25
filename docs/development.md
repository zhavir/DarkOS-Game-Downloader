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

The plain `pytest` command includes local opt-in remote contracts. GitHub uses the offline selection
shown below.

Generate the same branch-coverage measurement used by GitHub:

```sh
uv run pytest -m "not live" --cov=dw_cli --cov-branch --cov-report=term-missing
```

Run only tests that do not open a local server or contact a live service:

```sh
uv run pytest -m "not e2e and not integration"
```

GitHub runs unit tests, localhost integration tests, and offline E2E workflows with:

```sh
uv run pytest -m "not live"
```

Live remote-contract E2E tests for Vimm, Minerva's browse and torrent endpoints, a real torrent
metadata download, and the R36S compatibility frontend remain available locally with
`uv run pytest -m "e2e and live"`. GitHub does not run them because source services may block shared
runner addresses. Native selective peer transfer remains covered deterministically because public
torrent peers are not a stable CI dependency.

Python Semantic Release updates `pyproject.toml` during a release. Its configured build hook
installs the pinned uv release tool inside the action container, runs every prek hook against the
complete tree, stages the resulting release files with `git add .`, and builds the distributions
before the version commit and tag are created. The prek `uv-lock` hook updates and verifies
`uv.lock`, keeping the release commit usable with `uv sync --frozen`.

Protected releases use a repository-installed GitHub App. `RELEASE_APP_ID` identifies the App in
both the release workflow and the stored ruleset templates, while `RELEASE_APP_PRIVATE_KEY` creates
a short-lived token. The separate ruleset-sync workflow uses the administrator-owned `GH_TOKEN`
secret with repository Administration write permission. Run **Sync GitHub rulesets** manually after
the initial secrets and variable are configured.

The `main` ruleset requires successful PR checks for normal merges without also requiring every
branch to be rebased after `main` advances or every review conversation to be resolved. Repository
administrators and the release App have always-allow exceptions, enabling administrator direct
pushes and semantic release commits. Do not layer a **Restrict updates** rule over it: merges are
branch updates, so such a rule makes administrators use the bypass flow even when checks pass.
Limit non-administrator collaborators to Read or Triage when merges must remain admin-only.

## Documentation

Preview the Zensical site locally:

```sh
uv run zensical serve
```

Build exactly what GitHub Pages publishes:

```sh
uv run zensical build --clean --strict
```

Pull-request and release workflows append the coverage table to the GitHub job summary and upload
the XML, JSON, and browsable HTML reports as a `coverage-*` Actions artifact. After Python Semantic
Release and every release artifact succeed, the release workflow dispatches the Pages workflow.
It reuses that run's coverage artifact, publishes the latest `main` HTML report under `/coverage/`
and its JSON summary at `/coverage.json`, then updates `badges/coverage.svg` on `gh-pages` through
the Marketplace Coverage Badge action. The initial repository checkout uses
`persist-credentials: false` so its token cannot conflict with the badge action's authenticated
`gh-pages` checkout.

The generated `site/` directory is ignored. Documentation-only changes are published with the next
successful semantic release rather than directly on every push to `main`.

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
