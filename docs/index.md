# dArkOS Downloader

dArkOS Downloader is a controller-first library manager for RK3326 R36S handhelds running dArkOS
or dArkOSRE. The release ZIP is self-contained: it includes an ARM64 executable and Python 3.14,
so neither Python, uv, nor a package manager is required on the handheld.

[Install on an R36S](install.md){ .md-button .md-button--primary }
[Use the downloader](usage.md){ .md-button }

## What it does

- Searches the remote library by a case-insensitive title prefix.
- Remembers the download store selected during first-run setup. It can be changed later in
  **Settings**.
- Downloads selected Minerva files without requiring an external torrent client.
- Accepts an empty search to list the complete selected catalogue, including **All platforms**.
- Downloads a selected game and moves it into the correct dArkOS ROM folder on SD1 or SD2.
- Installs bundled BIOS files first, checks both SD cards, and offers required missing firmware
  through RetroBIOS.
- Provides a manual BIOS catalogue search for required and optional firmware.
- Caches each store/platform game catalogue as structured JSON for fast local searching and safe
  stale-cache fallback when a store is unavailable.
- Caches R36S compatibility scores and RetroBIOS metadata locally and refreshes them only when
  requested in **Settings**.
- Updates and deletes installed games while preserving multi-file `.cue` and `.m3u` groups.
- Queues an EmulationStation game-list refresh after every install, update, or deletion, keeps the
  TUI open, and applies one refresh when the user exits.
- Filters console families that cannot run on the R36S, including PS2, PS3, Xbox, Xbox 360,
  GameCube, Wii, Switch, Nintendo 3DS, and PS Vita.
- Shows an RK3326 compatibility level and title-match confidence before download when the
  [R36S Game List](https://r36sgamelist.com/) has a reliable match.

## Controller-first

The TUI reads the R36S controls directly from `/dev/input/js*`. Up/down moves through menus and
supports press-and-hold scrolling. The on-screen keyboard uses an evenly spaced fixed grid with
letter, symbol, and accented-character pages. All four directions navigate and X submits the
current search—even when it is empty.

## Standalone device package

The application and launcher are independent. Copy the release's `tools` content to the ROM card,
put the card back in the device, and launch it from EmulationStation's Tools menu.
