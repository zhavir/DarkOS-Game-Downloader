# dArkOS Downloader

[![Latest release](https://img.shields.io/github/v/release/zhavir/DarkOS-Game-Downloader?display_name=tag&sort=semver)](https://github.com/zhavir/DarkOS-Game-Downloader/releases/latest)
[![Coverage](https://raw.githubusercontent.com/zhavir/DarkOS-Game-Downloader/gh-pages/badges/coverage.svg)](https://zhavir.github.io/DarkOS-Game-Downloader/coverage/)

dArkOS Downloader is a controller-first game library manager for RK3326 R36S handhelds running
dArkOS or dArkOSRE. It can also run locally with a keyboard, including in a completely offline demo
environment that uses fake games and temporary SD-card folders.

**Documentation:**
[zhavir.github.io/DarkOS-Game-Downloader](https://zhavir.github.io/DarkOS-Game-Downloader/)

## Features

- Searches by a case-insensitive title prefix, including across all platforms.
- Saves a default download store during first-run setup and lets it be changed later in
  **Settings**. Vimm and Minerva Archive's RetroAchievements collection are implemented behind the
  same store contract.
- Lists a selected platform's complete numeric and A-Z remote catalogue when search text is empty.
- Scores results against the frontend-only [R36S Game List](https://r36sgamelist.com/) index,
  tolerating region, revision, and filename metadata; caches it locally for seven days and shows
  the RK3326 compatibility level and match confidence before download.
- Filters explicitly unsupported modern systems such as PS2, PS3, Xbox, Xbox 360, GameCube, Wii,
  Switch, 3DS, and PS Vita from detected folders and all-platform results.
- Maps more than 100 R36S-compatible ROM destinations and discovers image-specific folders.
- Detects and manages both `/roms` and `/roms2` in a dual-card setup.
- Downloads to a staging directory and then moves the completed file into the selected ROM folder.
- Downloads only the selected file from Minerva's platform torrent with a native Python
  BitTorrent client; no aria2, torrent application, daemon, or external component is required.
- Exposes all native BitTorrent limits under **Settings → Minerva BitTorrent settings** when
  Minerva is selected, and persists customized values locally.
- Installs BIOS files explicitly bundled under a `bios/` directory in a downloaded ZIP, without
  overwriting existing firmware or unpacking ordinary arcade/merged ROM archives.
- Scans installed games on both cards.
- Navigates installed games card-first and platform-first, scanning only the selected platform and
  skipping artwork, manuals, screenshots, and videos.
- Deletes a selected game, including files referenced by `.cue` and `.m3u` playlists.
- Updates a selected game by downloading first and replacing the old copy only after success.
- Checks GitHub Releases from **Settings** and installs the exact newer R36S ARM64 bundle without
  Python, uv, or another updater; preferences and cached data are preserved.
- Queues an EmulationStation game-list refresh after an install, update, or deletion and applies it
  once when the user exits the TUI, without reopening the application or rebooting the handheld.
- Cancels an active direct or torrent download with B/Escape and removes its partial file.
- Supports the R36S D-pad and both analog sticks directly through `/dev/input/js*`, and has an
  on-screen keyboard where every direction navigates and X submits the current text, including an
  empty search.
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
4. Opens the real curses TUI in the current terminal.

The demo data is harmless: downloaded “ROMs” are tiny text payloads with `.zip` names. The
`.local-test` directory persists after exit so update, rescan, and delete behavior can be tested
across multiple launches.

Suggested manual end-to-end walkthrough:

1. Choose Vimm during the one-time first-run setup. Change it later through **Settings** if needed.
2. Open **Search the library**, select **Game Boy Advance**, and search for `ADV`.
3. Confirm both Advance Wars versions appear; prefix matching is case-insensitive and does not
   require the complete title.
4. Search again, leave the text empty, and select **DONE** to list the complete demo catalogue.
5. Download Advance Wars version `1.0` and select SD1 or SD2.
6. Open **Manage installed games**, choose the same card and game, then use **Update from remote**.
7. Choose `Rev 2` and confirm that the replacement appears on the same card.
8. Return to game management and test **Delete from device**.

Keyboard controls are arrow keys, Enter to select, Escape to go back, Page Up/Page Down to page,
Backspace to erase, and normal typing in the on-screen keyboard. In ordinary R36S menus, up/down
navigate and can be held for continuous scrolling, left acts as B, and right acts as A. While the
on-screen keyboard is open, both the D-pad and analog stick navigate in all four directions; press
X to search with the text entered so far. An empty value lists the complete numeric and A-Z
catalogue for the selected platform, including **All platforms**. The R36S controller is optional
when running locally.

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
export DW_STORES=vimm
export DW_DOWNLOAD_DIR="$PWD/.local-test/downloads"
export DW_ROMS_DIRS="$PWD/.local-test/sd1:$PWD/.local-test/sd2"
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

The registered services are Vimm and Minerva Archive. Minerva searches only its
`RetroAchievements` collection and uses public BitTorrent peers, so availability depends on
seeders and your public IP address is visible to the swarm. The native client requests only the
selected file's verified pieces and does not listen for uploads or seed. Downloads may be large and
remote layouts can change, so use the offline demo first. Only download content you have the legal
right to use.

## Environment variables

| Variable | Meaning | Default |
| --- | --- | --- |
| `DW_BASE_URL` | Vimm store root; use the local fake server for offline tests | `https://vimm.net` |
| `DW_MINERVA_BASE_URL` | Minerva browse/detail root | `https://minerva-archive.org` |
| `DW_MINERVA_TORRENT_BASE_URL` | Minerva torrent metadata root | `https://cdn.minerva-archive.org/torrents` |
| `DW_STORES` | Comma-separated enabled store IDs | `vimm,minerva` |
| `DW_DOWNLOAD_DIR` | Temporary download/staging directory | Current directory; device launcher uses its private `.downloads` folder |
| `DW_ROMS_DIR` | One explicit ROM root for local or single-card testing | Auto-detect |
| `DW_ROMS_DIRS` | Multiple ROM roots separated by the OS path separator; takes precedence over `DW_ROMS_DIR` | Auto-detect `/roms2`, then `/roms` |
| `DW_TIMEOUT` | Network timeout in seconds | `30` |
| `DW_UPDATE_API_URL` | Latest-release API endpoint; primarily useful for offline updater tests | Project GitHub Releases API |
| `DW_INSTALL_DIR` | Packaged application directory used by self-update | Set automatically by the device launcher |

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

Search Minerva's RetroAchievements collection with the same prefix and empty-search behavior:

```sh
uv run dw --store minerva search GBA "advance wars"
uv run dw --store minerva search GBA
uv run dw --store minerva search ALL "advance wars"
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

Run everything locally, including the opt-in remote contracts:

```sh
uv run pytest
```

Generate the same branch-coverage measurement used by GitHub:

```sh
uv run pytest -m "not live" --cov=dw_cli --cov-branch --cov-report=term-missing
```

Run only the offline, localhost-backed E2E workflows used on GitHub:

```sh
uv run pytest -m "e2e and not live" -v
```

Run the live remote-contract E2E tests locally when you explicitly want to contact the source
services:

```sh
uv run pytest -m "e2e and live" -v
```

The live targets can be overridden with `DW_LIVE_BASE_URL`, `DW_LIVE_MINERVA_BASE_URL`, and
`DW_LIVE_MINERVA_TORRENT_BASE_URL` when testing compatible deployments.

Run the offline localhost integration workflows:

```sh
uv run pytest -m integration -v
```

Run only unit tests, without opening localhost listeners or contacting live services:

```sh
uv run pytest -m "not e2e and not integration"
```

Run everything that does not need internet access:

```sh
uv run pytest -m "not live"
```

Live E2E tests are local opt-in checks and are never run by GitHub Actions because the source
services may block shared runner addresses. They contact the real Vimm, Minerva, and R36S Game List
URLs and verify case-insensitive prefix searches, all-platform searches, empty catalogues, a real
Minerva torrent download and file mapping, and a known compatibility entry. The native selective
peer transfer is covered by deterministic tests because public torrent peers are not guaranteed to
accept connections from GitHub-hosted runners.

The offline integration/E2E suite binds a random localhost port and exercises:

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
`.github/workflows/docs.yml` workflow publishes the strict build to GitHub Pages only after Python
Semantic Release has created a release and the release artifacts have been built successfully.

### Enable the documentation site on GitHub

Configure the repository once:

1. Open **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. Open **Settings → Actions → General**.
4. Under **Workflow permissions**, select **Read and write permissions**. The docs workflow needs
   `contents: write` so the Coverage Badge action can update `badges/coverage.svg` on `gh-pages`;
   it also declares `pages: write` and `id-token: write` for the documentation deployment.
5. Push a conventional commit to `main`, either directly or by merging a pull request. The
   successful release workflow dispatches the **Documentation** workflow automatically.
6. Wait for the `github-pages` deployment environment to complete, then open
   [zhavir.github.io/DarkOS-Game-Downloader](https://zhavir.github.io/DarkOS-Game-Downloader/).

For a private repository, the GitHub plan must support Pages for private repositories. The Coverage
Badge action creates and maintains `gh-pages`; the documentation site itself still uses the GitHub
Actions Pages source. The initial checkout deliberately does not persist Git credentials because the
badge action performs its own authenticated `gh-pages` checkout. No deploy key, custom token, or
repository secret is required.

Pull requests targeting `main` run a pre-commit job and one all-tests job containing unit tests,
localhost integration tests, and offline E2E workflows. Tests marked `live` are excluded on GitHub.

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
    ├── ca-certificates.crt
    └── _internal/
```

The Tools launcher detects a detached launch, opens the TUI on a real Linux virtual console, and
switches back after exit. Startup and crash details are written to
`tools/darkos-downloader/darkos-downloader.log`.
The selected default store is saved under `tools/darkos-downloader/.downloads`, so replacing the
application files with a newer release keeps the setting.
For future updates, open **Settings → Check for application update**. The TUI downloads and validates
the exact new R36S bundle, closes, and lets the Tools launcher swap it into place while preserving
`.downloads`. The launcher returns directly to EmulationStation without opening a keyboard-only
confirmation dialog. Reopen the tool to verify the update: the previous version remains available
until the updated TUI exits successfully and is restored automatically if that first launch crashes.
Manual copying remains available as a recovery path if an SD-card write is interrupted.
The application reads the live device tree exposed by Linux; you do not need to find or decompile a
`.dtb` file. Device-tree key labels and `linux,code` values are diagnostic clues. The active
joystick ioctl mapping remains authoritative because a DTB does not reliably describe joydev button
indexes or analog-stick behavior.

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
| X | Submit the current on-screen keyboard search, including empty text |
| Y | Delete the last character in the on-screen keyboard |
| Select | Back |
| Start | Select in ordinary menus; ignored by the on-screen keyboard |

## Refresh the EmulationStation game list

After a successful install, update, or delete, the TUI queues a game-list refresh but remains open,
so you can perform more operations. When you later choose **Exit** and confirm, the TUI records one
refresh request and closes. The launcher then uses dArkOS's `systemctl restart emulationstation`
mechanism. It does not reopen the TUI, and the new game list is loaded without rebooting the R36S.
If the image does not expose that service, use
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

Every new commit pushed to `main` starts `.github/workflows/release.yml`, whether it comes from a
pull-request merge or a direct push. Its pre-commit job and full test job run the same offline checks
as the pull-request workflow; remote services are not contacted from GitHub-hosted runners. The official
[Python Semantic Release](https://python-semantic-release.readthedocs.io/) GitHub actions then read
the conventional commits since the previous tag and:

1. Determines the next semantic version.
2. Updates `pyproject.toml` and `CHANGELOG.md`.
3. Runs every prek hook, including the lock-file synchronization, before committing the release.
4. Creates a `v<version>` tag and GitHub release with commit-derived notes.
5. After semantic release succeeds, builds the uv wheel, source distribution, and verified
   self-contained Linux ARM64 dArkOS R36S ZIP.
6. Attaches all three artifacts to the GitHub release.
7. After every artifact succeeds, dispatches the documentation deployment and coverage-badge
   update.

Use conventional commit messages so the release type and notes are deterministic:

- `fix: ...` creates a patch release.
- `feat: ...` creates a minor release.
- `feat!: ...` or a `BREAKING CHANGE:` footer creates a major release.
- Documentation, test, build, and chore-only commits do not create a release by default.

When using squash merges, make the pull-request title conventional because it becomes the commit
subject.

### Enable protected releases and administrator direct pushes

The repository stores one ruleset for `main`. Normal pull-request merges require successful
**Pre-commit** and **All tests** jobs. They do not require an otherwise conflict-free branch to be
rebased whenever `main` advances, and unresolved review conversations are not an additional merge
gate. Repository administrators have an explicit always-allow exception so they can push directly
when necessary; the dedicated release GitHub App has the same exception for Python Semantic
Release's version commit. Granting direct-push access necessarily means administrators can also
bypass pull-request checks, so reserve that role for trusted maintainers.

Do not add a separate **Restrict updates** rule to make merges administrator-only. GitHub treats a
merge as a branch update, so that rule forces every allowed administrator merge through the bypass
flow even after all checks pass. If only administrators should be able to merge, enforce that with
repository access: give other collaborators **Read** or **Triage**, not **Write** or **Maintain**.

Configure GitHub once before syncing the rulesets:

1. Create a GitHub App for this repository with **Contents: Read and write**, generate a private
   key, and install the App on `zhavir/DarkOS-Game-Downloader`.
2. Add an Actions repository variable named `RELEASE_APP_ID` containing the App's numeric ID.
3. Add an Actions repository secret named `RELEASE_APP_PRIVATE_KEY` containing the complete PEM
   private key.
4. Add `GH_TOKEN` as an Actions repository secret. Use a fine-grained personal access token from a
   repository administrator with **Administration: Read and write** for this repository. This token
   only creates and updates rulesets; release pushes use the GitHub App token.
5. Open **Actions → Sync GitHub rulesets → Run workflow** once. This also removes the retired
   `Restrict default branch updates to administrators` ruleset. Later changes under
   `.github/rulesets/` are synchronized automatically after they reach `main`.

The stored ruleset JSON uses integration actor ID `0` as a template placeholder; the sync workflow
replaces it with `RELEASE_APP_ID` before calling GitHub. Do not paste the JSON into GitHub without
that substitution.

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
- **Minerva reports no peers:** its downloads depend on public BitTorrent seeders and outbound HTTP,
  UDP, and peer TCP traffic. Try again later or use Vimm.
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
