# Install on an R36S

## Requirements

- An RK3326 R36S running dArkOS or dArkOSRE.
- The latest `darkos-downloader-<version>-r36s-arm64.zip` from the project's GitHub release.
- Network connectivity on the handheld when searching or downloading.

Python, uv, Docker, and external installers are not required on the device.

## Copy the package

1. Extract the release ZIP on your computer.
2. Open its `tools` directory.
3. Copy everything inside that directory into the ROM card's `tools` directory. This is normally
   `EASYROMS/tools` on SD1 or `tools` on SD2.
4. Replace an older downloader copy if prompted.
5. Put the card back into the R36S.
6. In EmulationStation, open **Options → Tools → dArkOS Downloader**.

The final card layout must be:

```text
tools/
├── dArkOS Downloader.sh
└── darkos-downloader/
    ├── darkos-downloader
    ├── ca-certificates.crt
    └── _internal/
```

!!! tip "Updating the tool"

    Open **Settings → Check for application update** in the TUI. Confirm a newer version and wait for
    it to finish. The application closes so its Tools launcher can transactionally replace the
    executable while preserving `.downloads`, including the selected store, Minerva settings, and
    caches. It returns directly to EmulationStation without a second confirmation dialog. Reopen the
    tool to verify the update; if that first TUI launch crashes, the launcher restores the previous
    application while retaining the preferences. No Python, uv, or external update utility is used.

## ROM cards and folders

The launcher auto-detects both `/roms` and `/roms2`. When both are present, downloads ask for the
destination card. The application maps more than 100 dArkOS folders and uses an already-existing
alternate folder—such as `famicom`—when appropriate.

## Game-list refresh

Installs, updates, and deletions queue a refresh without closing the TUI. When the user exits, the
tool sends one refresh request and the launcher restarts EmulationStation. A full device reboot is
not required. If the image does not expose the service, use **Select → Update Games Lists** in
EmulationStation.

## Logs and removal

Startup and crash diagnostics are stored in:

```text
tools/darkos-downloader/darkos-downloader.log
```

The runtime tree under `/proc/device-tree` is read directly, so the packaged `.dtb` does not need to
be located or decompiled. The kernel joystick mapping is still authoritative because the tree does
not reliably map joydev indexes or analog-stick events.

To uninstall, remove `dArkOS Downloader.sh` and the `darkos-downloader` directory from `tools`.
