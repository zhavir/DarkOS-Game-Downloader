# Using the TUI

## Controls

| R36S control | Action |
| --- | --- |
| D-pad/stick up or down | Move selection; hold to scroll continuously |
| D-pad/stick left | Back (B) |
| D-pad/stick right | Select (A) |
| A | Select |
| B or Select | Back |
| L1 / R1 | Previous / next page |
| X | Submit the on-screen keyboard search, including empty text |
| Y | Delete the last character on the on-screen keyboard |
| Start | Select in ordinary menus; ignored by the on-screen keyboard |

Keyboard users can use arrow keys, Enter, Escape, Page Up, Page Down, Backspace, and normal typing.

The on-screen keyboard has four fixed rows of equally sized character keys and one action row. Use
`aA` for upper/lowercase, `#+=` for punctuation and symbols, and `ÁÉ` for accented characters.
`SPACE`, `BACK`, and `DONE` are aligned to the same 12-column grid. The D-pad and stick navigate
only while the keyboard is open; they do not accidentally submit or cancel the search.

## Search and download

1. On first launch, select Vimm or Minerva Archive as the default store. The choice is saved; use
   **Settings** from the main menu to change it later.
2. Choose **Search the library**.
3. Select a platform or **All platforms**. Minerva is limited to its RetroAchievements collection
   and only shows platforms it provides.
4. Enter a title prefix. Matching is case-insensitive and starts at the beginning of the title.
5. Press **X** to search. Empty text is valid and lists the complete catalogue.
6. Review the compatibility badge and match confidence in the results list, then the source detail
   on the title screen.
7. Select **Download**, then choose SD1 or SD2 when both are available. Press B/Escape during a
   download to cancel it and remove the partial file.

Completed downloads are staged first and moved only after success. Existing ROMs are not silently
overwritten.

## Store catalogue cache

The first search for a store and platform downloads its complete game catalogue and saves structured
JSON under `.downloads/game-catalogues/<store>/<platform>.json`. Empty searches and
case-insensitive title-prefix searches then run against the local file. Vimm and Minerva use the
same cache behavior, including **All platforms**.

The default cache lifetime is seven days. After it expires, the next search tries to replace the
catalogue. If the store cannot be reached, the previous valid cache remains available for offline
searching. Open **Settings → Refresh store game catalogue** to choose a store and platform and force
an immediate refresh. Open **Settings → Catalogue cache lifetime** to set the expiry period from 1
to 3650 days; the change applies to store catalogues, R36S compatibility metadata, and RetroBIOS
metadata.

## Compatibility catalogue

The first compatible-platform search downloads the frontend game index from R36S Game List and
stores it in `.downloads/.r36s-game-list-cache.json`. Later searches use that local copy without a
network request to the compatibility site. Open **Settings → Update R36S Game List** to fetch a new
copy explicitly.

Once it is older than the configured catalogue lifetime, Settings labels it **stale**, while
searches continue using the available offline copy until you decide to refresh it. A failed refresh
does not remove or replace the working catalogue.

Minerva distributes games through per-platform torrents. The application has its own Python
BitTorrent client and retrieves only the chosen file's verified pieces. No external torrent client
is installed or invoked. The client does not seed or accept incoming peer connections; your public
IP address is still visible to peers and trackers while downloading.

If Minerva changes the order of files in a torrent, the catalogue position is treated only as a
hint. A unique filename match is found automatically. If the filename was renamed or appears more
than once, the TUI explains the mismatch and shows the closest candidates with their torrent path,
position, size, and title-match score. Review and explicitly confirm one file, or press B/Escape to
cancel without installing anything.

When Minerva is the selected store, open **Settings → Minerva BitTorrent settings** to edit the
native client's advanced values. They are saved in `.darkos-downloader.json` beside the staging
downloads and used by the next Minerva download. **Reset all to defaults** restores this table:

| Setting | Default |
| --- | ---: |
| UDP protocol ID | `0x41727101980` |
| Block size | 16,384 bytes |
| Maximum torrent metadata | 16,777,216 bytes |
| Maximum tracker response | 2,097,152 bytes |
| Maximum peer attempts | 240 |
| Peer race workers | 8 |
| Maximum peer timeout | 8.0 seconds |
| Maximum tracker queries | 16 |
| Maximum discovered peers | 240 |

All integer limits must be greater than zero, and the protocol ID must fit in an unsigned 64-bit
integer. The peer timeout must be a positive finite number and is also capped by the application's
overall network timeout.

## Update an installed game

Open **Manage installed games**, choose the memory card and platform, then select the game. **Update
from remote** searches the configured default store by the installed title and asks which remote
result should replace it. The old copy remains untouched until the new download completes
successfully. If the configured store does not support that platform, change it through
**Settings** first.

## Delete an installed game

Choose **Delete from device** and confirm. Playlist and disc groups referenced by `.cue` and `.m3u`
files are deleted together.

After a successful install, update, or deletion, acknowledge the completion message and continue
using the TUI if desired. The game-list refresh remains queued until you choose **Exit** and confirm.
The Tools launcher refreshes EmulationStation after the TUI closes and does not reopen it.

## Update dArkOS Downloader

Open **Settings → Check for application update**. The installed semantic version is compared with
the latest GitHub release. Confirming a newer release downloads the matching R36S ARM64 ZIP; press
B/Escape to cancel without changing the installed application. After validation, the TUI exits and
the Tools launcher replaces the application while preserving `.downloads`, then returns directly to
EmulationStation. Reopen the tool to verify the update. The previous version is deleted only after
the updated TUI exits successfully; a crash during that first launch restores the previous version
without losing preferences. Automatic application updates are available in the self-contained R36S
package.

## BIOS requirements and downloads

The downloader handles firmware in this order after installing or updating a game:

1. It installs files supplied under an explicit `bios/` subtree in the downloaded archive. Existing
   firmware is never silently overwritten.
2. It checks the required BIOS files for the selected platform, using checksums where available.
3. It searches the BIOS locations on both SD cards. A valid copy on either card satisfies the
   requirement.
4. Only unresolved required files produce a prompt. Choose **Download from RetroBIOS** or keep the
   game without them after reviewing the details. Optional files are not prompted automatically.

The requirement and checksum catalogue comes from
[RetroBIOS](https://github.com/Abdess/retrobios). It is downloaded once, when a BIOS operation first
needs it, and then loaded from `.downloads/retrobios/catalogue.json`. The application never refreshes
it silently. Settings shows it as **stale** after the configured catalogue lifetime expires; the
saved copy continues to work. Select **Settings → Update RetroBIOS catalogue** to replace the cache
with current upstream metadata; a failed update leaves the working cache intact.

Select **Search and download BIOS** on the main menu to browse by system, platform, filename,
description, or region. An empty search lists the complete supported catalogue. The details screen
shows whether the file is required or optional and whether it is valid, missing, or invalid on the
detected cards. Downloads require explicit confirmation that you may legally obtain the firmware.

Known ROM-local exceptions are installed automatically, including Neo Geo firmware copied beside
the ROM set. Some emulator cores have different optional firmware choices; use the manual search if
the core configured on your image needs a file that was not offered automatically.

## Logging settings

Open **Settings → Application log level** to choose `DEBUG`, `INFO`, `WARNING`, or `ERROR`. Open
**Settings → Write logs to file** to turn application file logging on or off. Both changes apply
immediately and are saved in `.darkos-downloader.json`. When file logging is enabled on the R36S,
records go to `tools/darkos-downloader/darkos-downloader.log`; for local runs without
`DW_LOG_FILE`, they go to `darkos-downloader.log` inside the configured download directory.
