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

Minerva distributes games through per-platform torrents. The application has its own Python
BitTorrent client and retrieves only the chosen file's verified pieces. No external torrent client
is installed or invoked. The client does not seed or accept incoming peer connections; your public
IP address is still visible to peers and trackers while downloading.

## Update an installed game

Open **Manage installed games**, choose the memory card and platform, then select the game. **Update
from remote** searches the configured default store by the installed title and asks which remote
result should replace it. The old copy remains untouched until the new download completes
successfully. If the configured store does not support that platform, change it through
**Settings** first.

## Delete an installed game

Choose **Delete from device** and confirm. Playlist and disc groups referenced by `.cue` and `.m3u`
files are deleted together.

After a successful install, update, or deletion, acknowledge the completion message. The TUI then
closes so the Tools launcher can refresh EmulationStation; it does not reopen automatically.

## Update dArkOS Downloader

Open **Settings → Check for application update**. The installed semantic version is compared with
the latest GitHub release. Confirming a newer release downloads the matching R36S ARM64 ZIP; press
B/Escape to cancel without changing the installed application. After validation, the TUI exits and
the Tools launcher replaces the application while preserving `.downloads`. Reopen the tool after
the success message. This self-update option is intentionally unavailable from a local source
checkout, where `git` and uv remain the update mechanism.

## Bundled BIOS files

Only files under an explicit `bios/` subtree in a downloaded ZIP are treated as firmware. They are
installed into the selected card's shared BIOS directory and never overwrite an existing file.
Known ROM-local exceptions are handled automatically, including Neo Geo firmware copied beside the
ROM set.
