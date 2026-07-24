# dArkOS Downloader

dArkOS Downloader is a controller-first game library manager for RK3326 R36S handhelds running
dArkOS or dArkOSRE. It can also run locally with a keyboard, including in a completely offline demo
environment that uses fake games and temporary SD-card folders.

## Features

- Searches by a case-insensitive title prefix, including across all platforms.
- Selects a download store before each TUI search and installed-game update. Vimm is the first
  implementation; the store contract and registry are ready for additional sources.
- Lists a selected platform's complete numeric and A-Z remote catalogue when search text is empty.
- Matches results against the frontend-only [R36S Game List](https://r36sgamelist.com/) index,
  caches it locally for seven days, and shows the RK3326 compatibility level before download.
- Filters explicitly unsupported modern systems such as PS2, PS3, Xbox, Xbox 360, GameCube, Wii,
  Switch, 3DS, and PS Vita from detected folders and all-platform results.
- Maps more than 100 R36S-compatible ROM destinations and discovers image-specific folders.
- Detects and manages both `/roms` and `/roms2` in a dual-card setup.
- Downloads to a staging directory and then moves the completed file into the selected ROM folder.
- Installs BIOS files explicitly bundled under a `bios/` directory in a downloaded ZIP, without
  overwriting existing firmware or unpacking ordinary arcade/merged ROM archives.
- Scans installed games on both cards.
- Navigates installed games card-first and platform-first, scanning only the selected platform and
  skipping artwork, manuals, screenshots, and videos.
- Deletes a selected game, including files referenced by `.cue` and `.m3u` playlists.
- Updates a selected game by downloading first and replacing the old copy only after success.
- Requests an EmulationStation game-list refresh after an install, update, or deletion; the
  handheld does not need to be rebooted.
- Supports the R36S D-pad and both analog sticks directly through `/dev/input/js*`, and has an
  on-screen keyboard whose Start button submits the current text, including an empty search.
- Provides typed CLI commands for automation and troubleshooting.

Normal downloads never overwrite an existing ROM silently. An explicit update leaves the installed
copy untouched until the replacement has downloaded successfully.

## Choose a way to run it

| Goal | What you need | Command or artifact |
| --- | --- | --- |
| Safest local UI test | uv and a terminal | `uv run python -m scripts.run_local_demo` |
| Local development against the real service | uv, terminal, network | `uv run dw` |
| Automated unit and E2E tests | uv; network for live E2E | `uv run pytest` |
| R36S use | The prebuilt ZIP only | `dist/darkos-downloader-<version>-r36s-arm64.zip` |
| Rebuild every release artifact | uv plus Docker and host utilities | `sh scripts/build_artifacts.sh` |

The rendered documentation is built with Zensical and published at
[zhavir.github.io/DarkOS-Game-Downloader](https://zhavir.github.io/DarkOS-Game-Downloader/).

## Local prerequisites

Local development is supported on Linux, macOS, and Linux under WSL2. WSL2 is the recommended way
to run it on a Windows computer because the application uses the Unix `curses` terminal API.

You need:

1. [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. A terminal at least 40 columns by 15 rows.
3. Network access when using the real service or running the live search E2E test. The demo,
   unit tests, and integration suite are offline.

You do not need to install Python manually. The repository pins Python 3.14 in `.python-version`,
and uv can install the matching interpreter automatically. Docker is not required for local use or
tests; it is required only to create the R36S ARM64 package.

From the repository root, install the locked development environment:

```sh
uv sync --frozen
```

There is no need to activate `.venv`; all commands below use `uv run`.

Install the repository's Git checks once per clone:

```sh
uv run prek install
```

`prek` is a locked development dependency. `prek install` installs both the `pre-commit` and
`commit-msg` hook types. The hooks validate common repository problems, keep `uv.lock` synchronized,
format TOML/YAML with `pyproject-fmt` and `yamlfmt`, run Ruff and `ty`, and lint conventional commit
messages with gitlint. Every tool hook comes directly from its upstream repository.

## One-command offline UI demo

Run:

```sh
uv run python -m scripts.run_local_demo
```

This command:

1. Starts a localhost-only fake catalogue on a random free port.
2. Creates `.local-test/downloads`, `.local-test/sd1/gba`, and `.local-test/sd2/gba`.
3. Configures the application to see both fake memory cards.
4. Disables the optional aria2 fast path so downloads use the deterministic Python implementation.
5. Opens the real curses TUI in the current terminal.

The demo data is harmless: downloaded “ROMs” are tiny text payloads with `.zip` names. The
`.local-test` directory persists after exit so update, rescan, and delete behavior can be tested
across multiple launches.

Suggested manual end-to-end walkthrough:

1. Open **Search the library**, select **Game Boy Advance**, and search for `ADV`.
2. Confirm both Advance Wars versions appear; prefix matching is case-insensitive and does not
   require the complete title.
3. Search again, leave the text empty, and select **DONE** to list the complete demo catalogue.
4. Download Advance Wars version `1.0` and select SD1 or SD2.
5. Open **Manage installed games**, choose the same card and game, then use **Update from remote**.
6. Choose `Rev 2` and confirm that the replacement appears on the same card.
7. Return to game management and test **Delete from device**.

Keyboard controls are arrow keys, Enter to select, Escape to go back, Page Up/Page Down to page,
Backspace to erase, and normal typing in the on-screen keyboard. On R36S, up/down navigate and can
be held for continuous scrolling, left acts as B, right acts as A, and Start immediately runs the
search with the text entered so far. An empty value lists the complete numeric and A-Z catalogue
for the selected platform, including **All platforms**. The R36S controller is optional when
running locally.

To use a different persistent demo location:

```sh
uv run python -m scripts.run_local_demo --workspace /tmp/darkos-demo
```

## Run the fake server separately

For CLI testing or inspecting requests manually, start the test service in terminal 1:

```sh
uv run python -m scripts.local_vault_server --verbose
```

It listens on `http://127.0.0.1:8765` by default. In terminal 2 on Linux, macOS, or WSL:

```sh
mkdir -p .local-test/downloads .local-test/sd1/gba .local-test/sd2/gba
export DW_BASE_URL=http://127.0.0.1:8765
export DW_DOWNLOAD_DIR="$PWD/.local-test/downloads"
export DW_ROMS_DIRS="$PWD/.local-test/sd1:$PWD/.local-test/sd2"
export DW_DISABLE_ARIA2=1
uv run dw
```

Use `;` instead of `:` between paths in `DW_ROMS_DIRS` on an operating system whose path separator
is a semicolon.

## Run locally against the real service

Create a local ROM root so testing cannot touch a real collection:

```sh
mkdir -p .local-test/real-service/downloads .local-test/real-service/sd1/gba
export DW_DOWNLOAD_DIR="$PWD/.local-test/real-service/downloads"
export DW_ROMS_DIR="$PWD/.local-test/real-service/sd1"
uv run dw
```

The default service is `https://vimm.net`. Downloads may be large and service availability or page
layout can change, so the offline demo should be used first. Only download content you have the
legal right to use.

## Environment variables

| Variable | Meaning | Default |
| --- | --- | --- |
| `DW_BASE_URL` | Vimm store root; use the local fake server for offline tests | `https://vimm.net` |
| `DW_DOWNLOAD_DIR` | Temporary download/staging directory | Current directory; device launcher uses its private `.downloads` folder |
| `DW_ROMS_DIR` | One explicit ROM root for local or single-card testing | Auto-detect |
| `DW_ROMS_DIRS` | Multiple ROM roots separated by the OS path separator; takes precedence over `DW_ROMS_DIR` | Auto-detect `/roms2`, then `/roms` |
| `DW_TIMEOUT` | Network timeout in seconds | `30` |
| `DW_DISABLE_ARIA2` | Set to `1`, `true`, `yes`, or `on` to force the Python downloader | aria2 is used when found |

`TERM` is normally provided by the terminal. If curses reports an unknown terminal locally, try
`TERM=xterm-256color`. The R36S Tools launcher sets a terminal value automatically.

## CLI testing and automation

Run the TUI:

```sh
uv run dw
```

Search by case-insensitive title prefix:

```sh
uv run dw search GBA "advance"
```

Search every remote platform with the `ALL` alias:

```sh
uv run dw search ALL "advance"
```

CLI automation uses Vimm by default. Select it explicitly with a global option when desired:

```sh
uv run dw --store vimm search GBA "advance"
```

Omit the query to list the selected platform's complete numeric and A-Z catalogue:

```sh
uv run dw search GBA
```

Use `ALL` without a query to aggregate every all-platform catalogue section:

```sh
uv run dw search ALL
```

Download from a detail URL and move the result to a ROM folder:

```sh
uv run dw download \
  --platform GBA \
  --directory .local-test/downloads \
  --roms-directory .local-test/sd1 \
  http://127.0.0.1:8765/vault/1001
```

Use the fake server URL above only while `scripts/local_vault_server.py` is running.

## Automated tests

Run everything:

```sh
uv run pytest
```

Run the live search E2E test against the real service:

```sh
uv run pytest -m e2e -v
```

Override the live target when testing a compatible deployment:

```sh
DW_LIVE_BASE_URL=https://vimm.net uv run pytest -m e2e -v
```

Run the offline localhost integration workflows:

```sh
uv run pytest -m integration -v
```

Run everything that does not need internet access:

```sh
uv run pytest -m "not live"
```

The live E2E tests contact the real URLs and verify current HTTP responses and HTML parsing for a
case-insensitive GBA prefix, the same prefix across all platforms, an empty platform search across
every numeric and A-Z catalogue section, and a known title in the frontend-only R36S compatibility
index. They never download a game.

The offline integration suite binds a random localhost port and exercises:

- CLI prefix search and empty catalogue listing.
- Real HTTP request/response handling and HTML parsing.
- Detail-page resolution and streamed downloads with content-disposition filenames.
- `.part` cleanup and movement into the platform's ROM directory.
- Safe bundled-BIOS extraction into the selected card's shared `bios` directory.
- Dual-card configuration and discovery.
- Installed-library scanning.
- Fast installed-platform discovery with ignored media subtrees pruned.
- Transactional update on the same memory card.
- Confirmed game deletion.

The curses event loop is tested manually with the one-command demo. Offline integration automation
tests the production client, downloader, organizer, library, configuration, and CLI entry point
beneath it; the live E2E test detects real search URL or page-layout regressions.

Run all development checks:

```sh
uv run prek run --all-files
uv run pytest
uv run zensical build --clean --strict
uv build
```

Preview the documentation locally with `uv run zensical serve`. The
`.github/workflows/docs.yml` workflow publishes the strict build to GitHub Pages after relevant
changes reach `main`. In the repository's **Settings → Pages**, the source must be set to **GitHub
Actions** once before the first deployment.

Pull requests targeting `main` run those lint/type checks, all offline tests, and a separate live
search E2E job against the real remote service.

## Copy the prebuilt package to dArkOS

The R36S ZIP contains a Linux ARM64 executable and its embedded Python 3.14 runtime. Nothing is
installed globally on the handheld.

1. Download the latest `darkos-downloader-<version>-r36s-arm64.zip` release and extract it on your
   computer.
2. Open the extracted `tools` directory.
3. Copy everything inside it into the ROM card's `tools` directory, normally
   `EASYROMS/tools` on SD1 or `tools` on SD2.
4. Replace the older downloader files if prompted.
5. Put the card back into the R36S.
6. In EmulationStation, open **Options → Tools → dArkOS Downloader**.

Expected layout:

```text
tools/
├── dArkOS Downloader.sh
└── darkos-downloader/
    ├── darkos-downloader
    └── _internal/
```

The Tools launcher detects a detached launch, opens the TUI on a real Linux virtual console, and
switches back after exit. Startup and crash details are written to
`tools/darkos-downloader/darkos-downloader.log`.

To uninstall, remove `dArkOS Downloader.sh` and the `darkos-downloader` directory from the card's
`tools` directory.

## R36S controller layout

| R36S control | Action |
| --- | --- |
| D-pad/stick up or down | Move selection; hold to scroll continuously |
| D-pad/stick left | Back (B) |
| D-pad/stick right | Select (A) |
| A | Select |
| B | Back |
| L1 / R1 | Previous / next page |
| X | Backspace in the on-screen keyboard |
| Y | Space in the on-screen keyboard |
| Select | Back |
| Start | Submit the current search immediately; select in ordinary menus |

## Refresh the EmulationStation game list

After a successful install, update, or delete, the device launcher records a refresh request. When
you exit dArkOS Downloader it uses dArkOS's `systemctl restart emulationstation` mechanism, so the
new game list is loaded without rebooting the R36S. If the image does not expose that service, use
EmulationStation's **Select → Update Games Lists** command; the launcher records the failed restart
in `tools/darkos-downloader/darkos-downloader.log`.

## Bundled BIOS handling

When a downloaded ZIP contains a directory named `bios` at any package depth, those files are
installed on the selected memory card before the game archive is moved. For example,
`package/bios/dc/dc_boot.bin` becomes `bios/dc/dc_boot.bin` on that card.

The installer follows dArkOS placement exceptions for known ROM-local firmware. Adventure Vision,
Astrocade, and CoCo BIOS archives go beside their ROMs. `neogeo.zip` and `aes.zip` are copied to both
the shared BIOS directory and the Neo Geo ROM directory for compatibility. Existing BIOS files are
never overwritten.

Only an explicit `bios/` subtree is extracted. Ordinary game content and flat arcade or merged-set
BIOS members stay inside the original game archive. Extraction rejects path traversal, symbolic
links, excessive file counts, and unexpectedly large firmware payloads.

## Build the R36S ARM64 ZIP

Building the device package requires:

- Docker with BuildKit support.
- `curl` or `wget`.
- `zip` and `file`.
- Network access for the ARM64 Python archive and container images on every build.

Run from the repository root:

```sh
sh scripts/build_artifacts.sh
```

The builder first creates the uv wheel and source distribution, then downloads a fresh Python 3.14
ARM64 runtime, performs an uncached PyInstaller build in an emulated ARM64 Ubuntu 18.04 container,
verifies the ELF architecture, and writes `dist/darkos-downloader-<version>-r36s-arm64.zip`. The
older Ubuntu container is intentional: it gives the binary a conservative glibc baseline suitable
for the Debian-based dArkOS image. Existing versioned artifacts are replaced.

The project itself uses uv's `uv_build` backend. To build only the Python wheel and source archive,
you can still run:

```sh
uv build
```

The single `scripts/build_artifacts.sh` entry point is what release automation uses when all formats
are required.

## Automated releases

Merging a pull request into `main` starts `.github/workflows/release.yml`. Its pre-commit job and
full test job run the same checks as the pull-request workflow, including the real-service E2E test.
The official [Python Semantic Release](https://python-semantic-release.readthedocs.io/) GitHub
actions then read the conventional commits since the previous tag and:

1. Determines the next semantic version.
2. Updates `pyproject.toml` and `CHANGELOG.md`.
3. Builds the uv wheel and source distribution.
4. Builds and verifies the self-contained Linux ARM64 dArkOS R36S ZIP.
5. Creates a `v<version>` tag and GitHub release with commit-derived notes.
6. Attaches the wheel, source archive, and dArkOS ZIP.

Use conventional commit messages so the release type and notes are deterministic:

- `fix: ...` creates a patch release.
- `feat: ...` creates a minor release.
- `feat!: ...` or a `BREAKING CHANGE:` footer creates a major release.
- Documentation, test, build, and chore-only commits do not create a release by default.

When using squash merges, make the pull-request title conventional because it becomes the commit
subject. The release job needs GitHub Actions `contents: write` permission. If `main` has branch
protection that blocks the release bot's version commit, allow GitHub Actions to bypass that rule or
replace `GITHUB_TOKEN` with an appropriately scoped repository token.

Before enabling releases in a brand-new repository, create the one-time baseline tag matching the
version already present in `pyproject.toml`:

```sh
git tag v3.4.0
git push origin v3.4.0
```

Existing repositories that already contain a semantic version tag do not need this step.

## Troubleshooting

- **“The TUI needs an interactive terminal” locally:** run `uv run dw` directly in a terminal, not
  through an IDE output panel or redirected pipe.
- **Terminal too small:** resize it to at least 40 columns by 15 rows.
- **No ROM partition found:** set `DW_ROMS_DIR` or `DW_ROMS_DIRS` to directories you own and create
  them before starting the TUI.
- **Fake server connection refused:** keep `scripts/local_vault_server.py` running or use the
  one-command `scripts/run_local_demo.py` workflow.
- **Different downloader behavior because aria2 is installed:** set `DW_DISABLE_ARIA2=1`.
- **Native Windows import error for curses:** use WSL2.
- **R36S returns immediately to EmulationStation:** copy the complete latest package again and inspect
  `tools/darkos-downloader/darkos-downloader.log`.

## Project layout

```text
src/dw_cli/                    Application, TUI, client, download, and library code
docs/                          Zensical documentation sources
tests/                         Unit tests
tests/e2e/                     Offline end-to-end workflows
scripts/local_vault_server.py  Reusable fake remote service
scripts/run_local_demo.py      One-command interactive local environment
scripts/build_artifacts.sh        Wheel, source archive, and R36S ZIP builder
darkos/dArkOS Downloader.sh    Device Tools launcher
packaging/                     ARM64 frozen-application build files
.github/workflows/             Pull-request checks and merged-PR semantic releases
zensical.toml                  Documentation site configuration
```
