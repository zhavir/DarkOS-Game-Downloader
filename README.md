# dArkOS Downloader

[![Latest release](https://img.shields.io/github/v/release/zhavir/DarkOS-Game-Downloader?display_name=tag&sort=semver)](https://github.com/zhavir/DarkOS-Game-Downloader/releases/latest)
[![Coverage](https://raw.githubusercontent.com/zhavir/DarkOS-Game-Downloader/gh-pages/badges/coverage.svg)](https://zhavir.github.io/DarkOS-Game-Downloader/coverage/)

dArkOS Downloader is a controller-first game library manager for RK3326 R36S handhelds running
dArkOS or dArkOSRE. It searches supported stores, downloads games into the correct ROM directory,
and manages installed games on one-card and two-card systems.

The R36S release is self-contained. Python, uv, a torrent client, and a package manager are not
required on the handheld.

[Read the user documentation](https://zhavir.github.io/DarkOS-Game-Downloader/)

## Main features

- Search by a case-insensitive title prefix, or submit an empty search to list a catalogue.
- Search one platform or all platforms supported by the selected store.
- Choose Vimm or Minerva Archive once and change the preferred store later in **Settings**.
- Download to the correct dArkOS ROM folder on SD1 or SD2.
- Show R36S compatibility information before downloading when a reliable match is available.
- Install BIOS files explicitly bundled inside a game's `bios/` directory without overwriting an
  existing BIOS.
- Scan, update, and delete installed games, including grouped `.cue` and `.m3u` files.
- Cancel active downloads with B or Escape and remove incomplete files.
- Refresh the EmulationStation game list once when the TUI closes after a library change.
- Update the application from **Settings**, preserving preferences and rolling back if the new
  version fails its first launch.
- Use Minerva torrents through the built-in Python BitTorrent client; no external downloader is
  needed.

## Install on an R36S

1. Download `darkos-downloader-<version>-r36s-arm64.zip` from the
   [latest release](https://github.com/zhavir/DarkOS-Game-Downloader/releases/latest).
2. Extract the ZIP on your computer.
3. Copy everything inside its `tools` directory into the ROM card's `tools` directory.
4. Put the card back into the R36S.
5. Open **Options → Tools → dArkOS Downloader** in EmulationStation.

The card must contain:

```text
tools/
├── dArkOS Downloader.sh
└── darkos-downloader/
    ├── darkos-downloader
    ├── ca-certificates.crt
    └── _internal/
```

Replacing an older installation is safe. Keep the existing
`tools/darkos-downloader/.downloads` directory if copying files manually because it contains the
preferred store, Minerva settings, and cached data.

## Controls

| R36S control | Action |
| --- | --- |
| D-pad or stick up/down | Move through menus; hold to scroll |
| D-pad or stick left | Back |
| D-pad or stick right | Select |
| A | Select |
| B or Select | Back or cancel an active download |
| L1 / R1 | Previous / next page |
| X | Submit the on-screen keyboard, including an empty search |
| Y | Delete the last character |
| Start | Select in menus; ignored by the on-screen keyboard |

On a computer, use the arrow keys, Enter, Escape, Page Up, Page Down, Backspace, and normal typing.

## Search and download

On first launch, choose the default store. Then:

1. Select **Search the library**.
2. Choose a platform or **All platforms**.
3. Enter the beginning of a title. Matching is case-insensitive.
4. Press X. An empty value lists the selected catalogue.
5. Review the game details and compatibility information.
6. Select **Download** and choose a memory card when both SD1 and SD2 are available.

Downloads are completed in a staging directory before being moved. Existing ROMs are not silently
overwritten.

### Stores

- **Vimm** provides direct downloads and platform catalogues.
- **Minerva Archive** uses its RetroAchievements collection. The application downloads only the
  selected file's verified torrent pieces. Availability depends on public trackers and seeders,
  and the public IP address of the handheld is visible to the swarm while downloading.

The preferred store applies to searches, direct downloads, and installed-game updates. Change it
through **Settings → Change download store**.

## Manage installed games

Open **Manage installed games**, choose the memory card and platform, then select a game.

- **Update from remote** searches the preferred store using the installed title. The old files stay
  in place until the replacement finishes downloading and is installed successfully.
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
uv run dw
```

Use the offline demonstration when you do not want to contact a real store or modify a ROM library:

```sh
uv run python -m scripts.run_local_demo
```

The demo creates temporary SD1 and SD2 directories under `.local-test` and serves small fake game
files from localhost.

Useful automation commands:

```sh
uv run dw search GBA "advance"
uv run dw search GBA
uv run dw --store minerva search ALL "mario"
uv run dw download --platform GBA --roms-directory .local-test/sd1 DETAIL_URL
```

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DW_BASE_URL` | Vimm service root | `https://vimm.net` |
| `DW_MINERVA_BASE_URL` | Minerva browse service root | `https://minerva-archive.org` |
| `DW_MINERVA_TORRENT_BASE_URL` | Minerva torrent metadata root | Minerva CDN |
| `DW_STORES` | Comma-separated enabled stores | `vimm,minerva` |
| `DW_DOWNLOAD_DIR` | Temporary downloads and preferences | Current directory; private application directory on R36S |
| `DW_ROMS_DIR` | One explicit ROM root | Auto-detect |
| `DW_ROMS_DIRS` | Multiple ROM roots separated by the OS path separator | Auto-detect `/roms2`, then `/roms` |
| `DW_TIMEOUT` | Network timeout in seconds | `30` |
| `DW_LOG_FILE` | Diagnostic log destination | Set by the R36S launcher |
| `DW_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` | `INFO` |

Minerva-specific transfer limits can be edited from **Settings → Minerva BitTorrent settings**
when Minerva is selected.

## Diagnostics

On the handheld, structured application logs and launcher diagnostics are stored in:

```text
tools/darkos-downloader/darkos-downloader.log
```

The log rotates automatically so repeated use does not grow one file indefinitely. Set
`DW_LOG_LEVEL=DEBUG` before local startup when more detail is needed.

Common problems:

- **The tool immediately returns to EmulationStation:** copy the complete release again and inspect
  the diagnostic log.
- **No ROM partition is found:** verify that `/roms` or `/roms2` is mounted, or set `DW_ROMS_DIR` for
  local use.
- **Minerva reports no peers:** public seeders may be offline, or the network may block tracker UDP
  or peer TCP traffic. Try again later or switch to Vimm.
- **The terminal is too small locally:** resize it to at least 40 columns by 15 rows.
- **Windows reports that curses is unavailable:** run the application under WSL2.

Only download content you have the legal right to use.
