import hashlib
import io
import json
import urllib.error
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
from pytest_mock import MockerFixture

from ph import retrobios as retrobios_module
from ph.models import Platform
from ph.platforms import resolve_platform
from ph.retrobios import (
    MAX_FIRMWARE_BYTES,
    BiosDownloadCancelled,
    BiosError,
    BiosRequirement,
    BiosState,
    RetroBiosCatalog,
    RetroBiosRepository,
    audit_bios,
    audit_bios_roots,
    bios_destinations,
    install_bios,
    unresolved,
    verify_bios_file,
)

REVISION = "a" * 40


class FakeResponse(io.BytesIO):
    def __init__(self, content: bytes, content_length: bool = True) -> None:
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content))} if content_length else {}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def requirement(
    content: bytes = b"bios",
    *,
    name: str = "firmware.bin",
    destination: str | None = None,
    required: bool = True,
    source_path: str | None = "bios/Test System/firmware.bin",
    region: str | None = None,
) -> BiosRequirement:
    return BiosRequirement(
        name=name,
        destination=destination or name,
        required=required,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        sha1=hashlib.sha1(content).hexdigest(),
        md5=hashlib.md5(content).hexdigest(),
        source_path=source_path,
        description="Test firmware",
        region=region,
    )


def manifest(files: list[dict[str, Any]] | None = None) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "fetched_at": 9_999_999_999,
            "source_commit": REVISION,
            "source_generated_at": "2026-04-18T07:32:14Z",
            "retroarch_version": "v1.22.2",
            "systems": {
                "nintendo-gba": {
                    "name": "Nintendo - Game Boy Advance",
                    "core": "gpsp",
                    "docs": "https://example.test/gpsp",
                    "files": files
                    or [
                        {
                            "name": "gba_bios.bin",
                            "destination": "gba_bios.bin",
                            "required": False,
                            "size": 4,
                            "sha256": hashlib.sha256(b"bios").hexdigest(),
                            "source_path": "bios/Nintendo/GBA BIOS.rom",
                            "hle_fallback": True,
                        }
                    ],
                },
                "sony-playstation": {
                    "name": "Sony - PlayStation",
                    "core": "duckstation",
                    "files": [
                        {
                            "name": "scph5500.bin",
                            "destination": "scph5500.bin",
                            "required": True,
                            "size": 4,
                            "sha256": hashlib.sha256(b"bios").hexdigest(),
                            "source_path": "bios/Sony/scph5500.bin",
                            "region": "NTSC-J",
                        },
                        {
                            "name": "scph5501.bin",
                            "destination": "scph5501.bin",
                            "required": True,
                            "size": 4,
                            "sha256": hashlib.sha256(b"bios").hexdigest(),
                            "source_path": "bios/Sony/scph5501.bin",
                            "region": "NTSC-U",
                        },
                        {
                            "name": "common.bin",
                            "destination": "common.bin",
                            "required": True,
                            "size": 4,
                            "sha256": hashlib.sha256(b"bios").hexdigest(),
                            "source_path": "bios/Sony/common.bin",
                        },
                    ],
                },
            },
        }
    )


def test_catalog_parses_maps_regions_and_builds_immutable_urls() -> None:
    catalog = RetroBiosCatalog.from_json(manifest())
    gba = resolve_platform("GBA")
    psx = resolve_platform("PS1")
    assert gba is not None and psx is not None

    system = catalog.system_for(gba)
    assert system is not None
    assert system.core == "gpsp"
    assert system.requirements[0].hle_fallback is True
    assert catalog.generated_at == "2026-04-18T07:32:14Z"
    assert catalog.retroarch_version == "v1.22.2"
    assert not catalog.cache_is_stale()
    assert catalog.source_url(system.requirements[0]) == (
        f"https://raw.githubusercontent.com/Abdess/retrobios/{REVISION}/"
        "bios/Nintendo/GBA%20BIOS.rom"
    )

    usa = catalog.requirements_for(psx, "USA", required_only=True)
    assert [item.name for item in usa] == ["common.bin", "scph5501.bin"]
    assert len(catalog.requirements_for(psx, "Europe", required_only=True)) == 3
    assert len(catalog.requirements_for(psx, "unknown", required_only=True)) == 3
    assert catalog.requirements_for(Platform("Unknown", "unknown", "", "?")) == ()


def test_catalogue_reports_seven_day_cache_ttl(mocker: MockerFixture) -> None:
    catalog = RetroBiosCatalog.from_json(manifest())
    mocker.patch.object(retrobios_module, "time", return_value=9_999_999_999 + 8 * 24 * 60 * 60)
    assert catalog.cache_age_seconds() == 8 * 24 * 60 * 60
    assert catalog.cache_is_stale()

    legacy = json.loads(manifest())
    legacy.pop("fetched_at")
    assert RetroBiosCatalog.from_json(json.dumps(legacy)).cache_is_stale()


@pytest.mark.parametrize(
    "content, message",
    [
        ("not json", "invalid"),
        (json.dumps([]), "unsupported"),
        (json.dumps({"schema_version": 2}), "unsupported"),
        (json.dumps({"schema_version": 1}), "incomplete"),
    ],
)
def test_catalog_rejects_invalid_manifests(content: str, message: str) -> None:
    with pytest.raises(BiosError, match=message):
        RetroBiosCatalog.from_json(content)


def test_catalog_skips_malformed_systems_and_requirements() -> None:
    payload = json.loads(manifest())
    payload["systems"]["broken"] = "not an object"
    payload["systems"]["bad-files"] = {"files": "wrong"}
    payload["systems"]["partial"] = {"files": [None, {"name": "missing destination"}]}

    catalog = RetroBiosCatalog.from_json(json.dumps(payload))

    assert "broken" not in catalog.systems
    assert "bad-files" not in catalog.systems
    assert catalog.systems["partial"].requirements == ()


def test_audit_verifies_hashes_and_considers_both_memory_cards(tmp_path: Path) -> None:
    gba = resolve_platform("GBA")
    assert gba is not None
    bios = requirement()
    sd1 = tmp_path / "roms"
    sd2 = tmp_path / "roms2"

    assert audit_bios((bios,), gba, sd1)[0].state is BiosState.MISSING
    invalid = sd1 / "bios" / bios.name
    invalid.parent.mkdir(parents=True)
    invalid.write_bytes(b"wrong")
    assert audit_bios((bios,), gba, sd1)[0].state is BiosState.INVALID
    valid = sd2 / "bios" / bios.name
    valid.parent.mkdir(parents=True)
    valid.write_bytes(b"bios")

    checks = audit_bios_roots((bios,), gba, (sd1, sd2), sd1)

    assert checks[0].state is BiosState.VALID
    assert checks[0].paths == (valid,)
    assert unresolved(checks) == ()


def test_bios_destinations_cover_shared_local_and_unsafe_paths(tmp_path: Path) -> None:
    gba = resolve_platform("GBA")
    neogeo = resolve_platform("NEOGEO")
    advision = resolve_platform("ADV")
    assert gba is not None and neogeo is not None and advision is not None

    nested = requirement(destination="dc/firmware.bin")
    assert bios_destinations(nested, gba, tmp_path) == (tmp_path / "bios/dc/firmware.bin",)
    assert bios_destinations(nested, gba, tmp_path, "firmware") == (
        tmp_path / "firmware/dc/firmware.bin",
    )
    neo = requirement(name="neogeo.zip")
    assert bios_destinations(neo, neogeo, tmp_path) == (
        tmp_path / "bios/neogeo.zip",
        tmp_path / "neogeo/neogeo.zip",
    )
    local = requirement(name="advision.zip")
    assert bios_destinations(local, advision, tmp_path) == (tmp_path / "advision/advision.zip",)
    with pytest.raises(BiosError, match="unsafe"):
        bios_destinations(requirement(destination="../escape.bin"), gba, tmp_path)


def test_verify_uses_size_then_hash_and_handles_unreadable_files(tmp_path: Path) -> None:
    path = tmp_path / "bios.bin"
    path.write_bytes(b"bios")
    assert verify_bios_file(path, requirement()) is True
    assert verify_bios_file(path, requirement(b"other")) is False
    size_only = BiosRequirement("bios.bin", "bios.bin", True, 4, None, None, None, None)
    assert verify_bios_file(path, size_only) is True
    no_verification = BiosRequirement("bios.bin", "bios.bin", True, None, None, None, None, None)
    assert verify_bios_file(path, no_verification) is False
    assert verify_bios_file(tmp_path / "missing", requirement()) is False
    sha1_only = BiosRequirement(
        "bios.bin", "bios.bin", True, 4, None, hashlib.sha1(b"bios").hexdigest(), None, None
    )
    md5_only = BiosRequirement(
        "bios.bin", "bios.bin", True, 4, None, None, hashlib.md5(b"bios").hexdigest(), None
    )
    assert verify_bios_file(path, sha1_only) is True
    assert verify_bios_file(path, md5_only) is True


def test_install_bios_downloads_verifies_and_copies_neogeo_bios(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    catalog = RetroBiosCatalog(REVISION, {})
    platform = resolve_platform("NEOGEO")
    assert platform is not None
    bios = requirement(name="neogeo.zip", source_path="bios/SNK/Neo Geo/neogeo.zip")
    progress: list[tuple[str, int, int | None]] = []
    urlopen = mocker.patch.object(
        retrobios_module.urllib.request,
        "urlopen",
        side_effect=lambda *_args, **_kwargs: FakeResponse(b"bios"),
    )

    installed = install_bios(
        catalog,
        bios,
        platform,
        tmp_path,
        5,
        lambda *values: progress.append(values),
    )

    assert installed == (tmp_path / "bios/neogeo.zip", tmp_path / "neogeo/neogeo.zip")
    assert all(path.read_bytes() == b"bios" for path in installed)
    assert progress[-1] == ("neogeo.zip", 4, 4)
    assert "Neo%20Geo" in urlopen.call_args.args[0].full_url
    urlopen.reset_mock()
    assert install_bios(catalog, bios, platform, tmp_path, 5) == installed
    urlopen.assert_not_called()


def test_install_bios_cleans_partial_files_on_cancel_mismatch_and_network_error(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    catalog = RetroBiosCatalog(REVISION, {})
    gba = resolve_platform("GBA")
    assert gba is not None
    bios = requirement()
    urlopen = mocker.patch.object(retrobios_module.urllib.request, "urlopen")

    urlopen.return_value = FakeResponse(b"bios", content_length=False)
    with pytest.raises(BiosDownloadCancelled):
        install_bios(catalog, bios, gba, tmp_path, 5, cancelled=lambda: True)
    assert not (tmp_path / "bios/firmware.bin.part").exists()

    urlopen.return_value = FakeResponse(b"bad!")
    with pytest.raises(BiosError, match="checksum"):
        install_bios(catalog, bios, gba, tmp_path, 5)
    assert not (tmp_path / "bios/firmware.bin.part").exists()

    urlopen.side_effect = urllib.error.URLError("offline")
    with pytest.raises(BiosError, match="Could not install"):
        install_bios(catalog, bios, gba, tmp_path, 5)


def test_install_bios_checks_cancellation_after_response_and_copy_failures(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    catalog = RetroBiosCatalog(REVISION, {})
    gba = resolve_platform("GBA")
    neogeo = resolve_platform("NEOGEO")
    assert gba is not None and neogeo is not None
    urlopen = mocker.patch.object(
        retrobios_module.urllib.request,
        "urlopen",
        side_effect=lambda *_args, **_kwargs: FakeResponse(b"bios"),
    )
    checks = iter((False, True))
    with pytest.raises(BiosDownloadCancelled):
        install_bios(
            catalog,
            requirement(),
            gba,
            tmp_path / "cancel",
            5,
            cancelled=lambda: next(checks),
        )

    neo = requirement(name="neogeo.zip")
    local = tmp_path / "copy" / "neogeo" / "neogeo.zip"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"bios")
    installed = install_bios(catalog, neo, neogeo, tmp_path / "copy", 5)
    assert installed[1] == local

    urlopen.side_effect = lambda *_args, **_kwargs: FakeResponse(b"bios")
    mocker.patch.object(retrobios_module.shutil, "copyfile", side_effect=OSError("disk full"))
    with pytest.raises(BiosError, match="disk full"):
        install_bios(catalog, neo, neogeo, tmp_path / "failure", 5)
    assert not (tmp_path / "failure/neogeo/neogeo.zip.part").exists()


def test_install_bios_rejects_unavailable_and_oversized_entries(tmp_path: Path) -> None:
    catalog = RetroBiosCatalog(REVISION, {})
    gba = resolve_platform("GBA")
    assert gba is not None
    with pytest.raises(BiosError, match="does not provide"):
        install_bios(catalog, requirement(source_path=None), gba, tmp_path, 5)
    huge = BiosRequirement(
        "huge.bin",
        "huge.bin",
        True,
        MAX_FIRMWARE_BYTES + 1,
        "a",
        None,
        None,
        "bios/huge.bin",
    )
    with pytest.raises(BiosError, match="too large"):
        install_bios(catalog, huge, gba, tmp_path, 5)


def test_repository_load_ensure_and_atomic_update(tmp_path: Path, mocker: MockerFixture) -> None:
    repository = RetroBiosRepository(tmp_path, 5)
    assert repository.load() is None
    platform = {
        "version": "v1",
        "systems": {
            "nintendo-gba": {
                "native_id": "Nintendo - GBA",
                "core": "gpsp",
                "docs": "https://example.test",
                "files": [
                    {
                        "name": "gba_bios.bin",
                        "destination": "gba_bios.bin",
                        "required": True,
                        "size": 4,
                        "sha1": "1" * 40,
                    }
                ],
            }
        },
    }
    profile = {
        "files": [
            {
                "name": "gba_bios.bin",
                "required": False,
                "hle_fallback": True,
                "description": "Optional official BIOS",
            }
        ]
    }
    database = {
        "generated_at": "today",
        "files": {
            "1" * 40: {
                "path": "bios/Nintendo/GBA.bin",
                "size": 4,
                "sha1": "1" * 40,
                "sha256": "2" * 64,
            }
        },
        "indexes": {},
    }
    json_download = mocker.patch.object(
        retrobios_module,
        "_download_json",
        side_effect=[{"sha": REVISION}, database],
    )
    mocker.patch.object(
        retrobios_module,
        "_download_yaml",
        side_effect=[platform, profile],
    )
    progress: list[tuple[str, int, int | None]] = []

    catalog = repository.ensure(lambda *values: progress.append(values))

    assert repository.cache_path.is_file()
    gba = resolve_platform("GBA")
    assert gba is not None
    stored = catalog.requirements_for(gba)[0]
    assert stored.required is False
    assert stored.hle_fallback is True
    assert stored.source_path == "bios/Nintendo/GBA.bin"
    assert progress[-1][1:] == (2, 3)
    json_download.reset_mock()
    assert repository.ensure().revision == REVISION
    json_download.assert_not_called()


def test_repository_keeps_cache_when_update_is_invalid(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    repository = RetroBiosRepository(tmp_path, 5)
    repository.cache_path.parent.mkdir(parents=True)
    repository.cache_path.write_text(manifest(), encoding="utf-8")
    original = repository.cache_path.read_bytes()
    mocker.patch.object(retrobios_module, "_download_json", return_value={"sha": "invalid"})

    with pytest.raises(BiosError, match="invalid RetroBIOS revision"):
        repository.update()

    assert repository.cache_path.read_bytes() == original


def test_repository_reports_invalid_cache_and_download_formats(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    repository = RetroBiosRepository(tmp_path, 5)
    repository.cache_path.parent.mkdir(parents=True)
    repository.cache_path.write_text("bad", encoding="utf-8")
    with pytest.raises(BiosError, match="invalid"):
        repository.load()

    mocker.patch.object(
        retrobios_module.urllib.request,
        "urlopen",
        side_effect=[FakeResponse(b"[]"), FakeResponse(b"not yaml")],
    )
    with pytest.raises(BiosError, match="incomplete JSON"):
        retrobios_module._download_json("https://example.test", 5, None, max_bytes=20)
    with pytest.raises(BiosError, match="incomplete YAML"):
        retrobios_module._download_yaml("https://example.test", 5, None)

    mocker.patch.object(
        retrobios_module.urllib.request,
        "urlopen",
        side_effect=[FakeResponse(b"{"), FakeResponse(b"key: [")],
    )
    with pytest.raises(BiosError, match="invalid JSON"):
        retrobios_module._download_json("https://example.test", 5, None, max_bytes=20)
    with pytest.raises(BiosError, match="invalid YAML"):
        retrobios_module._download_yaml("https://example.test", 5, None)


def test_download_bytes_covers_cancellation_limits_and_connection_errors(
    mocker: MockerFixture,
) -> None:
    urlopen = mocker.patch.object(retrobios_module.urllib.request, "urlopen")
    urlopen.return_value = FakeResponse(b"content")
    with pytest.raises(BiosDownloadCancelled):
        retrobios_module._download_bytes(
            "https://example.test",
            5,
            lambda: True,
            max_bytes=20,
        )
    urlopen.return_value = FakeResponse(b"too long")
    with pytest.raises(BiosError, match="safety limit"):
        retrobios_module._download_bytes(
            "https://example.test",
            5,
            None,
            max_bytes=2,
        )
    urlopen.side_effect = OSError("offline")
    with pytest.raises(BiosError, match="Could not reach"):
        retrobios_module._download_bytes(
            "https://example.test",
            5,
            None,
            max_bytes=20,
        )


def test_database_name_index_fallback_and_profile_validation() -> None:
    database = {
        "files": {"key": {"name": "bios.bin", "size": 4, "path": "bios/bios.bin"}},
        "indexes": {"by_name": {"bios.bin": ["key"]}},
    }
    assert retrobios_module._database_file(database, {"name": "BIOS.bin", "size": 4}) == {
        "name": "bios.bin",
        "size": 4,
        "path": "bios/bios.bin",
    }
    assert retrobios_module._database_file(database, {"name": "bios.bin", "size": 8}) is None
    assert retrobios_module._database_file({"files": []}, {"name": "bios.bin"}) is None
    database["indexes"]["by_name"]["bios.bin"] = ["missing", "key"]
    assert retrobios_module._database_file(database, {"name": "bios.bin", "size": 4}) is not None
    assert retrobios_module._profile_files({"files": "wrong"}) == {}
    assert retrobios_module._profile_files(None) == {}


def test_build_manifest_rejects_missing_systems_and_skips_bad_rows() -> None:
    with pytest.raises(BiosError, match="does not contain systems"):
        retrobios_module._build_manifest(REVISION, {}, {}, {})
    built = retrobios_module._build_manifest(
        REVISION,
        {
            "systems": {
                1: {},
                "broken": "wrong",
                "valid": {"files": [None, {"destination": "missing name"}]},
            }
        },
        {},
        {},
    )
    assert built["systems"]["valid"]["files"] == []


def test_repository_read_and_write_errors_are_contextual(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    repository = RetroBiosRepository(tmp_path, 5)
    mocker.patch.object(Path, "read_text", side_effect=OSError("denied"))
    with pytest.raises(BiosError, match="Could not read"):
        repository.load()

    platform = {"systems": {}}
    mocker.patch.object(
        retrobios_module,
        "_download_json",
        side_effect=[{"sha": REVISION}, {"files": {}, "indexes": {}}],
    )
    mocker.patch.object(retrobios_module, "_download_yaml", return_value=platform)
    mocker.patch.object(Path, "write_text", side_effect=OSError("read only"))
    with pytest.raises(BiosError, match="Could not save"):
        repository.update()


def test_repository_rejects_platform_without_systems(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    repository = RetroBiosRepository(tmp_path, 5)
    mocker.patch.object(retrobios_module, "_download_json", return_value={"sha": REVISION})
    mocker.patch.object(retrobios_module, "_download_yaml", return_value={})
    with pytest.raises(BiosError, match="invalid RetroArch"):
        repository.update()


def test_region_normalization_variants() -> None:
    assert retrobios_module._normalize_region("Canada") == "ntsc-u"
    assert retrobios_module._normalize_region("Australia") == "pal"
    assert retrobios_module._normalize_region("Japan") == "ntsc-j"
    assert retrobios_module._normalize_region("World") is None
