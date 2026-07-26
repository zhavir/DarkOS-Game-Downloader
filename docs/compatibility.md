# Platform and game compatibility

## Operating-system support

| Operating system | Architecture | Status | Tested environment |
| --- | --- | --- | --- |
| DarkOS | ARM64 | Supported and fully tested | R36S, one-card and two-card layouts |
| Other Linux distributions | Not yet released | Portable core prepared for profiles | Contributions welcome |

Only the DarkOS artifact is currently published. Do not install that bundle on another Linux
distribution merely because it uses ARM64: ROM mount points, Tools integration, frontend refresh,
controller access, libc compatibility, and update layout must all be validated by a dedicated
target profile. See [Linux targets](linux-targets.md) for the boundary and acceptance requirements.

## Game compatibility badges

The optional title catalogue currently comes from
[R36S Game List](https://r36sgamelist.com/), whose ratings focus on RK3326 performance. Treat its
badge as advisory on different hardware. The downloader uses these levels:

| Level | Meaning |
| --- | --- |
| Perfect | The platform is expected to run at or near full speed |
| Playable | Many games work, but some need tuning or have slowdowns |
| Limited | Only lighter titles are likely to be usable |
| Not listed | The source does not currently publish a rating for that platform |

`Perfect - 96% match`, `Playable - 91% match`, or a similar badge means the title matched with that
confidence. A plain platform rating means the console has a published level but no sufficiently
reliable title match was found.

Region, language, revision, version, prototype, and similar filename text is ignored where possible.
Ambiguous matches remain unlisted instead of presenting uncertain compatibility as fact. Search and
download continue if the catalogue is unavailable.

## Offline cache

The title catalogue is fetched on the first compatible-platform search and stored in
`.downloads/.game-compatibility-cache.json`. Open **Settings → Update compatibility catalogue** to
replace it. A stale catalogue remains usable offline, and a failed refresh preserves the prior copy.

## Explicitly excluded console families

PS2, PS3, PS4, PS5, Xbox, Xbox 360, Xbox One, GameCube, Wii, Wii U, Nintendo Switch, Nintendo 3DS,
and PlayStation Vita are excluded from discovered ROM folders and **All platforms** results. Older
systems absent from the optional catalogue are not automatically removed.
