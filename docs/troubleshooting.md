# Troubleshooting

## The tool returns to EmulationStation immediately

Copy the complete latest release to the card again. Confirm that both the launcher and application
directory are present, then inspect:

```text
tools/darkos-downloader/darkos-downloader.log
```

Application messages include a timestamp, severity, module, and description. The launcher adds
startup and update-recovery diagnostics to the same file.

## No ROM partition is found

The handheld normally exposes `/roms`, `/roms2`, or both. Shut down the device, check that the ROM
cards are seated correctly, and allow dArkOS to mount them before opening the tool.

For local use, set `DW_ROMS_DIR` to one test directory or `DW_ROMS_DIRS` to multiple directories
separated by the operating system's path separator.

## A downloaded game is not shown

Exit the downloader normally after installing, updating, or deleting a game. The application
requests one EmulationStation refresh at that point. If the current image does not expose the
EmulationStation service, use **Select → Update Games Lists** from EmulationStation.

## Minerva cannot find peers

Minerva transfers depend on public torrent trackers and seeders. The handheld needs outbound HTTP,
UDP tracker, and TCP peer access. Retry later or select Vimm under **Settings → Change download
store**.

If transfers regularly time out, review **Settings → Minerva BitTorrent settings**. Use **Reset all
to defaults** before changing individual limits.

## Minerva says its torrent changed

Minerva's web catalogue and torrent metadata can be updated at different times. The downloader
automatically follows a uniquely matching filename even when its torrent position changed. If no
unique match exists, it shows the catalogue filename and the closest torrent candidates. Compare
the displayed path, size, and title-match score before confirming. Choose B/Escape if none of the
candidates is clearly the intended game; no ROM is installed when you cancel.

## Search compatibility is unavailable

Search and downloads continue when the R36S compatibility catalogue cannot be reached. Results then
show only known platform-level information or **Not listed**. Retry later to refresh the cached
catalogue.

The R36S Game List is downloaded only when it is missing. Use **Settings → Update R36S Game List**
to refresh it. A cache older than seven days is labelled **stale**, but remains available for
offline matching until you choose to update it. A failed update preserves the existing copy.

## The RetroBIOS catalogue is unavailable

The first automatic BIOS check or manual BIOS search needs GitHub access to download the RetroBIOS
metadata. Retry when the network is available. After the first successful download, the cached
catalogue is used without contacting GitHub.

Use **Settings → Update RetroBIOS catalogue** to refresh it explicitly. If an update fails or the
download is cancelled, the previous valid cache remains available. Settings marks it **stale**
after its seven-day TTL rather than replacing it automatically.

## A BIOS download fails validation

The downloader checks the published file size and strongest available checksum before installing a
BIOS. A mismatch is not copied over an existing file. Update the RetroBIOS catalogue and retry; if
it still fails, keep the existing firmware and report the upstream metadata/source mismatch.

## A game still reports missing firmware

Automatic prompts cover firmware marked as required by the matching RetroBIOS core profile. A
dArkOS image can configure another emulator core with different optional files. Open **Search and
download BIOS**, search for the system or filename, and compare the result with the core's own
documentation. The manual screen also shows whether a valid copy already exists on either SD card.

## Local terminal problems

- The terminal must be at least 40 columns by 15 rows.
- Run the TUI directly in a terminal, not an IDE output pane or redirected pipe.
- On Windows, use WSL2 because the application uses the Unix curses interface.
- If the terminal type is unknown, try `TERM=xterm-256color uv run dw`.

## More diagnostic detail

The device launcher writes logs automatically. For a local session, choose a log file and level:

```sh
DW_LOG_FILE=.local-test/darkos-downloader.log DW_LOG_LEVEL=DEBUG uv run dw
```

Valid levels are `DEBUG`, `INFO`, `WARNING`, and `ERROR`. Logs rotate automatically.
