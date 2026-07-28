# Pocket Harbor

[![Latest release](https://img.shields.io/github/v/release/zhavir/PoketHarbor?display_name=tag&sort=semver)](https://github.com/zhavir/PoketHarbor/releases/latest)
[![Coverage](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fzhavir.github.io%2FPoketHarbor%2Fcoverage.json&query=%24.totals.percent_covered_display&suffix=%25&label=coverage)](https://zhavir.github.io/PoketHarbor/coverage/)

Pocket Harbor is a controller-first game library manager for Linux handhelds. The portable core is
designed for multiple operating-system targets; the current release target is **DarkOS ARM64**, the
only environment tested end to end so far. It searches supported stores, installs games into the
target's ROM directory, and manages one-card and two-card libraries.

The device release is self-contained. Python, uv, a torrent client, and a package manager are not
required on the handheld.

[Read the user documentation](https://zhavir.github.io/PoketHarbor/)

[Contributing](CONTRIBUTING.md) explains development setup, project rules, and required checks.

## Main features

- Search by a case-insensitive title prefix, or submit an empty search to list a catalogue.
- Search one platform or all platforms supported by the selected store.
- Choose Vimm or Minerva Archive once and change the preferred store later in **Settings**.
- Cache complete store catalogues by store and platform for fast offline empty and prefix searches.
- Download to the correct target ROM folder on SD1 or SD2.
- Queue up to three background downloads, with persistent pause, resume, retry, and cancel controls.
- Show game compatibility information before downloading when a reliable catalogue match exists.
- Cache compatibility metadata locally and refresh it only when requested from **Settings**.
- Install BIOS files bundled with a game first, then check required firmware across both SD cards.
- Offer required missing BIOS through RetroBIOS, plus a manual BIOS search from the main menu.
- Scan, update, and delete installed games, including grouped `.cue` and `.m3u` files.
- Resume interrupted HTTP and Minerva downloads automatically after reopening the tool.
- Refresh the EmulationStation game list once when the TUI closes after a library change.
- Update the application from **Settings**, preserving preferences and rolling back if the new
  version fails its first launch.
- Use Minerva torrents through the built-in Python BitTorrent client; no external downloader is
  needed.

## Install on DarkOS

1. Download `pocket-harbor-<version>-darkos-arm64.zip` from the
   [latest release](https://github.com/zhavir/PoketHarbor/releases/latest).
2. Extract the ZIP on your computer.
3. Copy everything inside its `tools` directory into the ROM card's `tools` directory.
4. Put the card back into the handheld.
5. Open the downloader from **Options → Tools** in EmulationStation.

The card must contain:

```text
tools/
├── Pocket Harbor.sh
└── pocket-harbor/
    ├── pocket-harbor
    ├── ca-certificates.crt
    └── _internal/
```

> [!IMPORTANT]
> Versions before 2.0 used different internal package and storage paths. They cannot update to this
> release in place. Remove the earlier installation, copy the complete new `tools` tree, and
> configure the application again. Releases starting with 2.0 preserve
> `tools/pocket-harbor/.downloads` during normal updates.

## Controls

| Handheld control | Action |
| --- | --- |
| D-pad or stick up/down | Move through menus; hold to scroll |
| D-pad or stick left | Back |
| D-pad or stick right | Select |
| A | Select |
| B or Select | Go back one screen |
| L1 / R1 | Previous / next page |
| X | Submit the on-screen keyboard, including an empty search |
| Y | Delete the last character |
| Start | Select in menus; ignored by the on-screen keyboard |

On a computer, use the arrow keys, Enter, Escape, Page Up, Page Down, Backspace, and normal typing.
The on-screen keyboard uses a fixed 12-column grid with equally sized character keys. Use its
`aA`, `#+=`, and `ÁÉ` keys to switch case or enter punctuation, symbols, and accented characters.

## Search and download

On first launch, choose a default store or **Ask every time** to select a store for each search,
direct download, or game update. Then:

1. Select **Search the library**.
2. Choose a platform or **All platforms**.
3. Enter the beginning of a title. Matching is case-insensitive.
4. Press X. An empty value lists the selected catalogue.
5. Review the game details and compatibility information. In the results, press X to filter by
   console and Y to reset the complete list.
6. Select **Download** and choose a memory card when both SD1 and SD2 are available.

Downloads run in the background and are completed in a staging directory before being moved.
Open **Downloads** from the main menu to monitor its auto-refreshing, aligned progress rows or pause,
resume, retry, and cancel jobs. Long selected titles scroll automatically. Unfinished jobs resume
after Pocket Harbor is reopened, while completed entries disappear after their completion notice.
Each queued job keeps its original store even if the preferred store changes. Existing
ROMs are not silently overwritten. If a store responds with HTTP 429, the job waits and retries
automatically with increasing randomized delays instead of failing or blocking another store.

## BIOS requirements and downloads

After a game is installed, the downloader processes any firmware supplied in its explicit `bios/`
directory before checking for anything else. It then compares the game's required firmware with
the BIOS directories on both SD cards. A valid copy on either card counts as installed, so it does
not ask to download a duplicate.

If required firmware is still missing or has the wrong checksum, the TUI explains what was found
and lets you either download the verified file from
[RetroBIOS](https://github.com/Abdess/retrobios) or keep the game without it. Optional firmware is
not prompted automatically. Known ROM-local exceptions are installed in their required locations.

Use **Search and download BIOS** on the main menu to browse all supported firmware, including
optional files, and install one manually. The RetroBIOS catalogue is downloaded on the first BIOS
operation and cached under `.downloads/retrobios`. It is not refreshed automatically; use
**Settings → Update RetroBIOS catalogue** when you want the latest upstream metadata.

The game compatibility catalogue follows the same policy: it is fetched on first use, stored
locally, and refreshed only through **Settings → Update compatibility catalogue**. Settings marks
RetroBIOS and compatibility metadata stale after the configured catalogue lifetime, which defaults
to seven days. Their saved copies remain usable until you choose to update them.

### Stores

- **Vimm** provides direct downloads and platform catalogues.
- **Minerva Archive** uses its RetroAchievements collection. The application downloads only the
  selected file's verified torrent pieces. Availability depends on public trackers and seeders,
  and the public IP address of the handheld is visible to the swarm while downloading.

Each store's complete game catalogue is saved as structured JSON under
`.downloads/game-catalogues/<store>/<platform>.json`. A fresh cache is reused for empty and
case-insensitive prefix searches without contacting the store. After the configured lifetime, the
next search refreshes it automatically; if the store is unavailable, the last valid catalogue is
used. Use **Settings → Refresh store game catalogue** to replace a selected store/platform cache
immediately.

If Minerva reorders a torrent, the downloader finds a unique filename automatically. When a game
was renamed or is ambiguous, the TUI shows the closest torrent files with their position, path,
size, and title similarity so you can explicitly choose one or safely cancel.

The preferred store applies to searches, direct downloads, and installed-game updates. Change it
through **Settings → Change download store**.

## Manage installed games

Open **Manage installed games**, choose the memory card and platform, then select a game.

- **Update from remote** searches the preferred store using the installed title. The old files stay
  in place until the queued background replacement finishes and is installed successfully.
- **Delete from device** removes the selected game after confirmation. Files referenced by `.cue`
  and `.m3u` playlists are treated as one game group.

After an install, update, or deletion, continue using the application normally. EmulationStation is
refreshed once after you confirm **Exit**; a device reboot is not normally required.

## Application updates

Open **Settings → Check for application update**. If a newer release is available, confirm the
download and wait for the TUI to return to EmulationStation. Reopen the tool to verify the new
version.

Preferences and cached data are preserved. The previous application remains available until the
updated TUI exits successfully for the first time. If that launch fails, the launcher restores the
previous version automatically.

## Run locally

Local use requires [uv](https://docs.astral.sh/uv/) and a terminal with curses support. WSL2 is
recommended on Windows.

```sh
uv sync --frozen
uv run ph
```

Use the offline demonstration when you do not want to contact a real store or modify a ROM library:

```sh
uv run python -m scripts.run_local_demo
```

The demo creates temporary SD1 and SD2 directories under `.local-test` and serves small fake game
files from localhost.

Useful automation commands:

```sh
uv run ph search GBA "advance"
uv run ph search GBA
uv run ph --store minerva search ALL "mario"
uv run ph download --platform GBA --roms-directory .local-test/sd1 DETAIL_URL
```

The live RetroBIOS integration test downloads current metadata and one small firmware file from the
real upstream service:

```sh
uv run pytest -m live tests/e2e/test_live_retrobios.py -v
```

Run it only where outbound GitHub access is available. The ordinary test suite remains offline.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `PH_VIMM_BASE_URL` | Vimm service root | `https://vimm.net` |
| `PH_MINERVA_BASE_URL` | Minerva browse service root | `https://minerva-archive.org` |
| `PH_MINERVA_TORRENT_BASE_URL` | Minerva torrent metadata root | Minerva CDN |
| `PH_STORES` | Comma-separated enabled stores | `vimm,minerva` |
| `PH_DOWNLOAD_DIR` | Temporary downloads and preferences | Current directory; private application directory on device |
| `PH_ROMS_DIR` | One explicit ROM root | Auto-detect |
| `PH_ROMS_DIRS` | Multiple ROM roots separated by the OS path separator | Auto-detect `/roms2`, then `/roms` |
| `PH_TIMEOUT` | Network timeout in seconds | `30` |
| `PH_LOG_FILE` | Diagnostic log destination | Set by the device launcher |
| `PH_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` | `INFO` |
| `PH_TARGET_OS` | Linux integration profile | `darkos` |

Only `darkos` is currently registered. An unknown value fails at startup rather than silently using
paths or update packages from the wrong operating system. See [Linux target support](https://zhavir.github.io/PoketHarbor/linux-targets/).

Minerva-specific transfer limits can be edited from **Settings → Minerva BitTorrent settings**
when Minerva is selected.

The interface language, default ROM card, per-store console-folder mappings, shared BIOS folder,
network timeout, catalogue cache lifetime, application log level, and application file logging can
also be changed from **Settings**. Folder mappings use selectors populated from known folders and
folders discovered on the active cards. The global concurrent-download limit accepts 1-8, defaults
to 3, and applies after restarting Pocket Harbor. English is the default; German, Spanish, French,
Italian, and Portuguese are included. Boolean settings use a True/False picker and numeric settings use a
number-only keyboard. The default catalogue lifetime is seven days. HTTP 429 retry settings expose
the initial delay, maximum delay, and jitter; the maximum delay defaults to 3,600 seconds (one
hour).

## Diagnostics

On the handheld, structured application logs and launcher diagnostics are stored in:

```text
tools/pocket-harbor/pocket-harbor.log
```

The log rotates automatically so repeated use does not grow one file indefinitely. Use
**Settings → Application log level** to choose `DEBUG`, `INFO`, `WARNING`, or `ERROR`, and
**Settings → Write logs to file** to enable or disable application records. Environment variables
provide the initial local defaults; saved TUI preferences take precedence. After logging is enabled,
the confirmation screen shows the exact active path. If the launcher path is not writable, Pocket
Harbor falls back to `tools/pocket-harbor/.downloads/pocket-harbor.log` and records the reason there.

Common problems:

- **The tool immediately returns to EmulationStation:** copy the complete release again and inspect
  the diagnostic log.
- **No ROM partition is found:** verify that `/roms` or `/roms2` is mounted, or set `PH_ROMS_DIR` for
  local use.
- **Minerva reports no peers:** public seeders may be offline, or the network may block tracker UDP
  or peer TCP traffic. Try again later or switch to Vimm.
- **The terminal is too small locally:** resize it to at least 40 columns by 15 rows.
- **Windows reports that curses is unavailable:** run the application under WSL2.

Only download content you have the legal right to use.
