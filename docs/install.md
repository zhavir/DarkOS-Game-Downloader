# Install on DarkOS

## Requirements

- An ARM64 handheld running DarkOS. See [Platform compatibility](compatibility.md).
- The latest `pocket-harbor-<version>-darkos-arm64.zip` from the project's GitHub release.
- Network connectivity on the handheld when searching or downloading.

Python, uv, and external installers are not required on the device.

## Copy the package

1. Extract the release ZIP on your computer.
2. Open its `tools` directory.
3. Copy everything inside that directory into the ROM card's `tools` directory. This is normally
   `EASYROMS/tools` on SD1 or `tools` on SD2.
4. Replace an older downloader copy if prompted.
5. Put the card back into the handheld.
6. In EmulationStation, open **Options → Tools → Pocket Harbor**.

The final card layout must be:

```text
tools/
├── Pocket Harbor.sh
└── pocket-harbor/
    ├── pocket-harbor
    ├── ca-certificates.crt
    └── _internal/
```

!!! tip "Updating the tool"

    Versions before 2.0 cannot use the in-application updater for this breaking rename. Remove the
    earlier installation and manually copy the complete new `tools` tree once. Settings from the
    earlier installation are not migrated.

    Starting with 2.0, open **Settings → Check for application update** in the TUI. Confirm a newer
    version and wait for it to finish. The application closes so its Tools launcher can replace the
    executable while preserving `.downloads`, including the selected store, cache lifetime, logging
    preferences, store catalogues, Minerva settings, and RetroBIOS metadata. It returns directly to
    EmulationStation without a second confirmation dialog. Reopen the tool to verify the update; if
    that first TUI launch crashes, the launcher restores the previous application while retaining
    the preferences. No Python, uv, or external update utility is used.

## ROM cards and folders

The DarkOS launcher auto-detects both `/roms` and `/roms2`. When both are present, downloads ask for
the destination card. The application maps more than 100 DarkOS folders and uses an already-existing
alternate folder—such as `famicom`—when appropriate.

## Game-list refresh

Installs, updates, and deletions queue a refresh without closing the TUI. When the user exits, the
tool sends one refresh request and the launcher restarts EmulationStation. A full device reboot is
not required. If the image does not expose the service, use **Select → Update Games Lists** in
EmulationStation.

## Logs and removal

Startup and crash diagnostics are stored in:

```text
tools/pocket-harbor/pocket-harbor.log
```

Application records include timestamps and severity levels. The log rotates automatically. Use
**Settings → Application log level** to change detail and **Settings → Write logs to file** to
enable or disable application records. Startup and update-recovery diagnostics from the launcher
may still be written when application file logging is disabled.

To uninstall, remove `Pocket Harbor.sh` and the `pocket-harbor` directory from `tools`.
