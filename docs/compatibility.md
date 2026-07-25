# R36S compatibility

The R36S uses an RK3326 processor. dArkOS exposes many emulators, but a ROM folder existing does not
mean newer console hardware can be emulated acceptably.

## Result badges

The downloader uses these levels from [R36S Game List](https://r36sgamelist.com/):

| Level | Meaning |
| --- | --- |
| Perfect | The platform is expected to run at or near full speed |
| Playable | Many games work, but some need tuning or have slowdowns |
| Limited | Only lighter titles are likely to be usable |
| Not listed | The site does not currently publish a rating for that platform |

`Perfect - 96% match`, `Playable - 91% match`, or a similar badge means the game title was matched
to the compatibility catalogue with that confidence. A plain platform rating means the console
has a published RK3326 level but no sufficiently reliable title match was found.

Region, language, revision, version, prototype, and similar filename text is ignored where possible,
so a stored title such as `Advance Wars (USA) (Rev 1)` can match `Advance Wars`. Ambiguous matches
are shown as unlisted instead of presenting uncertain compatibility as fact.

If the site or network is unavailable, searching and downloading continue normally with the known
platform-level rating.

## Explicitly excluded families

PS2, PS3, PS4, PS5, Xbox, Xbox 360, Xbox One, GameCube, Wii, Wii U, Nintendo Switch, Nintendo 3DS,
and PlayStation Vita are excluded from discovered ROM folders and **All platforms** results.

Older systems absent from R36S Game List are not automatically removed. dArkOS supports many niche
8-bit, 16-bit, computer, arcade, and port folders beyond that site's catalogue.
