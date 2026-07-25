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

## Search compatibility is unavailable

Search and downloads continue when the R36S compatibility catalogue cannot be reached. Results then
show only known platform-level information or **Not listed**. Retry later to refresh the cached
catalogue.

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
