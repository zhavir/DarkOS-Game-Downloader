# Linux target support

Pocket Harbor separates portable library behavior from operating-system integration. Store search,
downloads, catalogue caches, BIOS validation, game scanning, localization, and the TUI remain shared.
A target profile supplies the parts that vary between Linux distributions.

## Current target

`darkos` is the default and the only registered target. It defines:

- ARM64 release and updater asset names;
- `/roms2` and `/roms` mount discovery, including two-card priority;
- the DarkOS EmulationStation ROM-folder catalogue;
- the Tools launcher and installed application layout;
- the marker used to request an EmulationStation refresh after exit;
- the Ubuntu 18.04/glibc 2.27-compatible build and clean-runtime smoke test.

Set `PH_TARGET_OS=darkos` explicitly when testing target selection. An unknown value stops with a
clear error so Pocket Harbor never installs into guessed paths.

## Requirements for another Linux distribution

A future target is ready to publish only after it has all of the following:

1. A runtime `LinuxTarget` registration with ROM roots, launcher layout, frontend refresh contract,
   architecture, and its platform-folder profile.
2. A build profile under `packaging/targets` selecting a compatible Python runtime, container base,
   Docker platform, launcher, exported layout, and architecture validation.
3. A launcher owned by that target; it must provide a terminal, writable private state, controller
   access, CA certificates, safe update/rollback, and one frontend refresh after normal exit.
4. Unit tests for target selection and paths, offline end-to-end tests for one-card and two-card
   behavior where applicable, updater bundle validation, and a clean-container executable smoke test.
5. Physical testing of launch, display, controls, downloads, BIOS handling, update/rollback, and
   frontend refresh on the named OS and device.
6. A target-specific artifact named
   `pocket-harbor-<version>-<target>-<architecture>.zip` and an updated compatibility table.

Until these conditions are met, another distribution is **not supported**, even if local source runs
successfully with manually configured `PH_ROMS_DIRS`.
