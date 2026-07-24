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

1. Choose **Search the library**.
2. Select Vimm or Minerva Archive. Minerva is limited to its RetroAchievements collection and only
   shows platforms it provides.
3. Select a platform or **All platforms**.
4. Enter a title prefix. Matching is case-insensitive and starts at the beginning of the title.
5. Press **X** to search. Empty text is valid and lists the complete catalogue.
6. Review the compatibility badge in the results list and the source detail on the title screen.
7. Select **Download**, then choose SD1 or SD2 when both are available.

Completed downloads are staged first and moved only after success. Existing ROMs are not silently
overwritten.

Minerva distributes games through per-platform torrents. The application has its own Python
BitTorrent client and retrieves only the chosen file's verified pieces. No external torrent client
is installed or invoked. The client does not seed or accept incoming peer connections; your public
IP address is still visible to peers and trackers while downloading.

## Update an installed game

Open **Manage installed games**, choose the memory card and platform, then select the game. **Update
from remote** first asks which store to search, then searches by the installed title and asks which
remote result should replace it. The old copy remains untouched until the new download completes
successfully.

## Delete an installed game

Choose **Delete from device** and confirm. Playlist and disc groups referenced by `.cue` and `.m3u`
files are deleted together.

## Bundled BIOS files

Only files under an explicit `bios/` subtree in a downloaded ZIP are treated as firmware. They are
installed into the selected card's shared BIOS directory and never overwrite an existing file.
Known ROM-local exceptions are handled automatically, including Neo Geo firmware copied beside the
ROM set.
