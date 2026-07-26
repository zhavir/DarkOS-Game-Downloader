---
name: pocket-harbor
description: Maintain and extend Pocket Harbor, the controller-first Linux handheld game library manager. Use for TUI navigation or localization, OS target profiles, store and catalogue integrations, ROM or BIOS management, multi-SD behavior, native BitTorrent, device packaging, self-updates, tests, user documentation, or GitHub release workflows in this repository.
---

# Pocket Harbor

## Start with the user contract

Read `README.md` and the relevant page in `docs/`, then inspect the owning source module and tests.
Keep documentation functional: describe what users can do and configure, not development history.
Search the whole repository for affected contracts before and after a change.

Pocket Harbor has a portable Linux core and explicit OS targets. DarkOS ARM64 is currently the only
supported and tested target, with R36S as its physical test environment. Never imply support for a
new distribution merely because source code runs there.

## Preserve the architecture

- Use Python 3.14 syntax and absolute `ph.*` imports. Keep `src/ph/__init__.py` version-free.
- Use `ph` as the public CLI command and `pocket-harbor` for distribution, executable, application
  directory, preferences, logs, and update-state names.
- Use `uv_build`, uv, ty, Ruff, pytest, pytest-mock, prek, and Zensical as configured in
  `pyproject.toml` and `uv.lock`.
- Put store-specific HTTP, parsing, catalogue, and download logic behind `GameStore`; register it in
  `StoreCatalog`. Search, direct download, and installed-game update consume this abstraction.
- Use native Python downloads. Minerva uses the built-in BitTorrent client; never add an external
  downloader or PortMaster dependency.
- Cache structured store/platform catalogues under `.downloads/game-catalogues`. The persisted TTL
  applies to store, RetroBIOS, and compatibility catalogues, defaults to seven days, and retains a
  stale valid cache after refresh failure.
- Resolve destinations through the active `LinuxTarget`, `platform_catalogue()`, `organizer.py`, and
  detected ROM roots. DarkOS supports `/roms`, `/roms2`, alternate folders, and its full catalogue.
  New OS support requires a runtime profile, build profile, launcher, tests, and physical validation.
- Preserve optimized installed-game scans and grouped `.cue`/`.m3u` update and deletion behavior.
- Install explicit archive `bios/` contents first, then audit required firmware across both cards.
  Prompt only for unresolved required files and retain the manual RetroBIOS search.

## Maintain the TUI

- Read `/dev/input/js*`; device-tree data supplies hardware context, not the sole button mapping.
- Menus: up/down navigate and repeat; left is Back; right is Select. Keyboard: all directions only
  navigate, X submits even empty input, Y deletes, and B/Escape returns exactly one layer.
- Keep the keyboard centered on a twelve-column grid with even spans and plain labels.
- Add UI strings through `i18n.py`. Maintain complete English, German, Spanish, Italian, and
  Portuguese catalogues; English is the persisted default. Test catalogue completeness.
- Boolean settings use a False/True menu, integers a digit-only keyboard, floats one decimal point,
  and mixed text the full keyboard.
- Persist settings in `.pocket-harbor.json` inside the `pocket-harbor` install directory.
- Queue one EmulationStation refresh after a library mutation and execute it only after confirmed
  TUI exit. Do not reopen the TUI after refresh or update.

## Test at the correct level

Use pytest-mock for collaborators. Avoid monkeypatching global behavior; refactor toward injected or
narrow collaborator boundaries when mocking is difficult. Unit-test code under `src/ph`; do not
add tests for docs or workflow YAML.

Maintain unit tests, offline end-to-end tests with local HTTP and temporary SD cards, and opt-in
`live` contracts for real Vimm, Minerva, RetroBIOS, and compatibility endpoints. GitHub runs all
non-live scopes together because third-party services can block CI. Keep branch coverage at 95% or
higher.

## Verify and package

Run narrow tests while iterating, then:

```sh
uv lock --check
uv run prek run --all-files
uv run pytest -m "not live" --cov=ph --cov-branch --cov-report=term-missing
uv run zensical build --clean --strict
uv build
sh scripts/build_artifacts.sh
```

If uv cache, network, or Docker restrictions prevent a command, report it exactly. The artifact
builder overwrites `dist/pocket-harbor-<version>-darkos-arm64.zip` each run. It must include the Tools
launcher, CA certificates, executable, Python runtime, and internal dependencies.

Pull requests have only pre-commit and all-tests jobs. Pushes to `main` repeat them, then Python
Semantic Release versions and publishes. Only a successful release builds the device artifact and
dispatches docs. The semantic-release build command runs prek and stages the lock update.

Finish with a case-insensitive search for stale brand, device, artifact, cache, and documentation
names. Preserve unrelated user changes. Report validation, unverified hardware/live-network limits,
and the artifact path.
