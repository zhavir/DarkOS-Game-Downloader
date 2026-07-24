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
to the site's frontend catalogue with that confidence. A plain platform rating means the console
has a published RK3326 level but no sufficiently reliable title match was found.

!!! info "How the integration works"

    r36sgamelist.com performs search in the browser. The downloader discovers its current Next.js
    JavaScript chunks, extracts title/console records, and caches the normalized index for seven
    days. Matching uses a conservative score based on normalized character order and shared title
    words. Region, language, revision, version, prototype, and similar release metadata are
    discounted, so `Advance Wars (USA) (Rev 1)` can match `Advance Wars`; ambiguous low-score
    candidates are left unlisted. It does not depend on a private or nonexistent search API.

If the site or network is unavailable, searching and downloading continue normally with the known
platform-level rating. Compatibility lookup never blocks a download permanently.

## Explicitly excluded families

PS2, PS3, PS4, PS5, Xbox, Xbox 360, Xbox One, GameCube, Wii, Wii U, Nintendo Switch, Nintendo 3DS,
and PlayStation Vita are excluded from discovered ROM folders and **All platforms** results.

Older systems absent from R36S Game List are not automatically removed. dArkOS supports many niche
8-bit, 16-bit, computer, arcade, and port folders beyond that site's catalogue.
