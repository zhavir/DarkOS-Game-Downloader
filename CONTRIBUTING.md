# Contributing to Pocket Harbor

Thank you for improving Pocket Harbor. Bug fixes, device reports, translations, store integrations,
tests, and user-focused documentation are welcome.

## Before opening a change

1. Search existing issues and pull requests.
2. Open an issue before a large feature, new store, storage-layout change, or updater migration so
   the behavior and legal/safety constraints can be agreed first.
3. Never attach ROMs, BIOS files, authentication material, private tracker data, or download links
   for content you do not have the right to distribute. Use synthetic fixtures in tests.

## Development setup

Install [uv](https://docs.astral.sh/uv/), then run:

```sh
uv sync --frozen
uv run ph
```

The project targets Python 3.14. Use absolute `ph.*` imports and keep source under `src/ph`.
Run the offline demo for a safe SD1/SD2 workflow:

```sh
uv run python -m scripts.run_local_demo
```

## Change rules

- Preserve the `GameStore` abstraction. Store-specific parsing and downloads belong in a store
  implementation, not the TUI.
- Preserve one-card and two-card behavior, target-owned folder aliases, grouped disc files,
  BIOS checks across both cards, and deferred EmulationStation refresh.
- Controller changes must cover menu navigation, the on-screen keyboard, press-and-hold repeat, and
  one-layer Back behavior.
- Add interface text through `src/ph/i18n.py` in English, German, Spanish, Italian, and
  Portuguese. Keep the completeness test passing.
- Use pytest-mock for collaborators. Avoid broad runtime monkeypatching; refactor a dependency
  boundary when code cannot be tested cleanly.
- Keep GitHub tests offline. Real endpoint contracts use the `live` marker and run only when
  explicitly requested outside CI.
- Update functional user documentation for changed behavior. Do not add tests that inspect docs or
  workflow YAML.

## Verify a pull request

```sh
uv lock --check
uv run prek run --all-files
uv run pytest -m "not live" --cov=ph --cov-branch --cov-report=term-missing
uv run zensical build --clean --strict
uv build
```

Coverage must remain at least 95%. Building the ARM64 device ZIP additionally requires Docker:

```sh
sh scripts/build_artifacts.sh
```

The command above builds the default DarkOS target. Target selection is explicit:

```sh
sh scripts/build_artifacts.sh darkos
```

To add another Linux distribution, implement both sides of the target boundary:

1. Register a `LinuxTarget` in `src/ph/targets.py`.
2. Add its platform-folder catalogue in `src/ph/platforms.py` and route it through
   `platform_catalogue()`.
3. Add `packaging/targets/<target>.conf` and reuse an architecture Dockerfile when its ABI is
   suitable; otherwise add a new architecture/ABI Dockerfile.
4. Add the target launcher and make its layout match the runtime profile exactly.
5. Add target, updater, offline workflow, launcher, and clean-runtime smoke coverage.
6. Mark it supported only after physical OS/device verification and documentation.

## Commits and pull requests

Use Conventional Commits, for example `fix(tui): keep back navigation to one layer`. The commit-msg
hook validates messages. Keep a pull request focused, explain user-visible behavior, list the checks
run, and call out live endpoints or physical devices that were not verified.

All required pull-request checks must pass before merge. Releases are generated from conventional
commits pushed to `main` by Python Semantic Release.
