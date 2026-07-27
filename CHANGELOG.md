# CHANGELOG

<!-- version list -->

## v3.0.3 (2026-07-27)

### Bug Fixes

- **tui**: Always show persisted download queue
  ([`8b4567a`](https://github.com/zhavir/PoketHarbor/commit/8b4567a7ec30c9a5115036916d9244956c006839))


## v3.0.2 (2026-07-27)

### Bug Fixes

- **minerva**: Coordinate parallel peer connections
  ([`d4920be`](https://github.com/zhavir/PoketHarbor/commit/d4920bea05b17adba839e400035e06a3d5b16d15))


## v3.0.1 (2026-07-27)

### Bug Fixes

- **build**: Bundle translation catalogues with PyInstaller
  ([`a06242d`](https://github.com/zhavir/PoketHarbor/commit/a06242dcc8044fb0796fc9490b1125a9d19c40b1))


## v3.0.0 (2026-07-27)

### Continuous Integration

- **docs**: Remove obsolete badge publisher
  ([`b3ea32e`](https://github.com/zhavir/PoketHarbor/commit/b3ea32ed1946325d93d892f102d3261128d31498))

### Features

- **settings**: Add storage mappings and YAML localization
  ([`ebf3f53`](https://github.com/zhavir/PoketHarbor/commit/ebf3f53a9fa94de77eb5d3400ce7ae32100a131a))

### Breaking Changes

- **settings**: PH_BASE_URL and --base-url are replaced by PH_VIMM_BASE_URL and --vimm-url.


## v2.1.1 (2026-07-27)

### Bug Fixes

- Make coverage badge use published report
  ([`0d1f449`](https://github.com/zhavir/PoketHarbor/commit/0d1f449cf091bb7023ad0b93da72da885a6c2cd5))

### Continuous Integration

- Pass coverage artifact id to docs
  ([`54dc68d`](https://github.com/zhavir/PoketHarbor/commit/54dc68dbbbe9aff3ca181f1586d8a998eb7c0751))


## v2.1.0 (2026-07-27)

### Continuous Integration

- **release**: Parallelize platform artifact builds
  ([`e52e17a`](https://github.com/zhavir/PoketHarbor/commit/e52e17a79b8d68199d8c4c6caf9f739b2eb6ec1b))

### Features

- Add persistent background download queue
  ([`a532b1a`](https://github.com/zhavir/PoketHarbor/commit/a532b1a31b2862017c3cb87699e89578ae7cf2af))


## v2.0.1 (2026-07-26)

### Bug Fixes

- Cover translation 100%
  ([`81b4c6a`](https://github.com/zhavir/PoketHarbor/commit/81b4c6a92790e6a564bcad7504fe393e463b6e4c))

### Continuous Integration

- Automatically set up issue templates
  ([`b37adbe`](https://github.com/zhavir/PoketHarbor/commit/b37adbe03a906fec69242f8e01200d18a12876b5))


## v2.0.0 (2026-07-26)

### Features

- Rename project internals to Pocket Harbor
  ([`2eda07f`](https://github.com/zhavir/PoketHarbor/commit/2eda07f2ca5f84cc3b78347004bdacc7a2b87265))

### Breaking Changes

- The Python package is now ph, the command is ph, and environment variables use PH_. DarkOS now
  installs under tools/pocket-harbor. Pre-2.0 installations require a manual reinstall; settings are
  not migrated.


## v1.6.2 (2026-07-25)

### Bug Fixes

- Fix back navigation
  ([`dd477fa`](https://github.com/zhavir/PoketHarbor/commit/dd477fa993c0b6fbaa9cf495bf1a41ffebd00fef))


## v1.6.1 (2026-07-25)

### Bug Fixes

- Fix layout of the keyboard and add cache to the stores
  ([`4cc92f9`](https://github.com/zhavir/PoketHarbor/commit/4cc92f90de120444a7d2cb755ac1e4b3d2624ab1))


## v1.6.0 (2026-07-25)

### Features

- Add bios downloader
  ([`a487771`](https://github.com/zhavir/PoketHarbor/commit/a4877711af343edc9254e19deb2626ee474cdd83))


## v1.5.1 (2026-07-25)

### Bug Fixes

- Make the download less strict on the final file name position
  ([`b9523bb`](https://github.com/zhavir/PoketHarbor/commit/b9523bb770e8ea417206204c6f195d621976e109))

### Continuous Integration

- Fix warnings on ci
  ([`51372af`](https://github.com/zhavir/PoketHarbor/commit/51372aff265d70aeb69d17233581b47aeafc3897))


## v1.5.0 (2026-07-25)

### Features

- Refactoring code, tests and docs
  ([`0b7723f`](https://github.com/zhavir/PoketHarbor/commit/0b7723f432cf58727b5f210163729d171dea4c65))


## v1.4.1 (2026-07-25)

### Bug Fixes

- Update docs to push for a new release
  ([`5ae00a0`](https://github.com/zhavir/PoketHarbor/commit/5ae00a075678933dc8259354e5c8c2b1f244f40b))


## v1.4.0 (2026-07-25)

### Bug Fixes

- Fix auto update ([#8](https://github.com/zhavir/PoketHarbor/pull/8),
  [`ca19bd8`](https://github.com/zhavir/PoketHarbor/commit/ca19bd858675e9f366840a924bd3aefce3f927de))

### Continuous Integration

- Make ruleset more admin friendly ([#8](https://github.com/zhavir/PoketHarbor/pull/8),
  [`ca19bd8`](https://github.com/zhavir/PoketHarbor/commit/ca19bd858675e9f366840a924bd3aefce3f927de))

### Features

- Expose torrent option in the tui ([#8](https://github.com/zhavir/PoketHarbor/pull/8),
  [`ca19bd8`](https://github.com/zhavir/PoketHarbor/commit/ca19bd858675e9f366840a924bd3aefce3f927de))


## v1.3.0 (2026-07-25)

### Continuous Integration

- Make ruleset more admin friendly ([#7](https://github.com/zhavir/PoketHarbor/pull/7),
  [`5493859`](https://github.com/zhavir/PoketHarbor/commit/549385925205dc27fb8482b5b64c4004380d777d))

### Features

- Expose torrent option in the tui ([#7](https://github.com/zhavir/PoketHarbor/pull/7),
  [`5493859`](https://github.com/zhavir/PoketHarbor/commit/549385925205dc27fb8482b5b64c4004380d777d))


## v1.2.0 (2026-07-25)

### Features

- Expose torrent option in the tui ([#6](https://github.com/zhavir/PoketHarbor/pull/6),
  [`d45cc3d`](https://github.com/zhavir/PoketHarbor/commit/d45cc3d97b84b532c98f63185f4918e4a7015d29))


## v1.1.0 (2026-07-24)

### Bug Fixes

- Fit game pad mapping
  ([`a9e1d6a`](https://github.com/zhavir/PoketHarbor/commit/a9e1d6aab7b55b794bbcacb1283d05b35c4c0904))

- Fix broken pipeline and add ruleset management
  ([`86dd69d`](https://github.com/zhavir/PoketHarbor/commit/86dd69d7c29da88f6bb84e6d831302b0341c254a))

- Fix broken pipeline and add ruleset management
  ([`2148482`](https://github.com/zhavir/PoketHarbor/commit/2148482d5032198e57055abc97d0a17418d8322e))

### Continuous Integration

- Fix pipeline triggering
  ([`f084f93`](https://github.com/zhavir/PoketHarbor/commit/f084f93dfd3e466399396117094987be03ac93a4))

### Features

- Add auto update feature
  ([`1e93d59`](https://github.com/zhavir/PoketHarbor/commit/1e93d595bf1dd1c6b2db63da0df373f1fcd70749))

- General improvements
  ([`80296f5`](https://github.com/zhavir/PoketHarbor/commit/80296f5bf74497973ee2ae71b533cbb340d012d5))

- Implement client for downloading from minerva
  ([`446f73f`](https://github.com/zhavir/PoketHarbor/commit/446f73ff63ae5553c0942ec827e0190be4e582f9))

### Testing

- Fix broken test
  ([`13d5925`](https://github.com/zhavir/PoketHarbor/commit/13d592555f79322242098d7f64d4374ba92228e7))


## v1.0.1 (2026-07-24)


## v1.0.0 (2026-07-24)

### Features

- First commit
  ([`bfbda4c`](https://github.com/zhavir/PoketHarbor/commit/bfbda4c30de12b15aed22c2fc1afa0245fa681a7))

- Implement client for downloading games
  ([`1b6298c`](https://github.com/zhavir/PoketHarbor/commit/1b6298c97287b1b29972951ce250ffcf36da8334))
