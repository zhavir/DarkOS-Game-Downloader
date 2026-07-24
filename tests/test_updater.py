import io
import json
import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path
from types import TracebackType
from urllib.request import Request

import pytest

from dw_cli.updater import (
    PENDING_UPDATE_DIRECTORY,
    READY_MARKER,
    ReleaseUpdate,
    UpdateCancelled,
    UpdateError,
    find_update,
    stage_update,
)

REPOSITORY_ROOT = Path(__file__).parents[1]


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def test_find_update_selects_exact_r36s_release_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "tag_name": "v1.2.0",
            "assets": [
                {
                    "name": "darkos-downloader-1.2.0-r36s-arm64.zip",
                    "browser_download_url": "https://example.test/device.zip",
                    "size": 1234,
                }
            ],
        }
    ).encode()
    monkeypatch.setattr("dw_cli.updater.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    release = find_update("1.0.1", "https://api.example.test/releases/latest")

    assert release == ReleaseUpdate(
        "1.2.0",
        "v1.2.0",
        "darkos-downloader-1.2.0-r36s-arm64.zip",
        "https://example.test/device.zip",
        1234,
    )


def test_find_update_returns_none_for_same_or_older_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"tag_name": "v1.0.1", "assets": []}).encode()
    monkeypatch.setattr("dw_cli.updater.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    assert find_update("1.0.1", "https://api.example.test/releases/latest") is None


def test_find_update_requires_the_versioned_device_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"tag_name": "v2.0.0", "assets": []}).encode()
    monkeypatch.setattr("dw_cli.updater.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    with pytest.raises(UpdateError, match=r"r36s-arm64\.zip"):
        find_update("1.0.1", "https://api.example.test/releases/latest")


def test_stage_update_validates_bundle_and_leaves_current_install_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_directory = tmp_path / "tools" / "darkos-downloader"
    install_directory.mkdir(parents=True)
    current_executable = install_directory / "darkos-downloader"
    current_executable.write_bytes(b"current")
    archive = _bundle_bytes()
    requested: list[str] = []

    def fake_urlopen(request: Request, **_kwargs: object) -> FakeResponse:
        requested.append(request.full_url)
        return FakeResponse(archive)

    monkeypatch.setattr("dw_cli.updater.urlopen", fake_urlopen)
    release = ReleaseUpdate(
        "1.2.0",
        "v1.2.0",
        "darkos-downloader-1.2.0-r36s-arm64.zip",
        "https://example.test/device.zip",
        len(archive),
    )

    pending = stage_update(release, install_directory)

    assert requested == [release.asset_url]
    assert pending == tmp_path / "tools" / PENDING_UPDATE_DIRECTORY
    assert (pending / READY_MARKER).read_text(encoding="ascii") == "1.2.0\n"
    staged_executable = pending / "darkos-downloader" / "darkos-downloader"
    assert staged_executable.read_bytes() == _arm64_elf()
    assert staged_executable.stat().st_mode & stat.S_IXUSR
    assert (pending / "dArkOS Downloader.sh").is_file()
    assert current_executable.read_bytes() == b"current"
    assert not (tmp_path / "tools" / f"{PENDING_UPDATE_DIRECTORY}.zip.part").exists()


def test_stage_update_rejects_path_traversal_and_removes_partial_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_directory = tmp_path / "tools" / "darkos-downloader"
    install_directory.mkdir(parents=True)
    (install_directory / "darkos-downloader").write_bytes(b"current")
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("tools/../escaped", b"unsafe")
    monkeypatch.setattr(
        "dw_cli.updater.urlopen",
        lambda *_args, **_kwargs: FakeResponse(archive_buffer.getvalue()),
    )
    release = ReleaseUpdate("2.0.0", "v2.0.0", "update.zip", "https://example.test/a", None)

    with pytest.raises(UpdateError, match="Unsafe path"):
        stage_update(release, install_directory)

    assert not (tmp_path / "tools" / "escaped").exists()
    assert not (tmp_path / "tools" / PENDING_UPDATE_DIRECTORY).exists()
    assert not (tmp_path / "tools" / f"{PENDING_UPDATE_DIRECTORY}.incomplete").exists()


def test_stage_update_can_be_cancelled_before_network_access(tmp_path: Path) -> None:
    install_directory = tmp_path / "tools" / "darkos-downloader"
    install_directory.mkdir(parents=True)
    (install_directory / "darkos-downloader").write_bytes(b"current")
    release = ReleaseUpdate("2.0.0", "v2.0.0", "update.zip", "https://example.test/a", None)

    with pytest.raises(UpdateCancelled):
        stage_update(release, install_directory, cancelled=lambda: True)


def test_device_launcher_applies_pending_update_and_preserves_download_state(
    tmp_path: Path,
) -> None:
    tools_directory = tmp_path / "tools"
    install_directory = tools_directory / "darkos-downloader"
    pending = tools_directory / PENDING_UPDATE_DIRECTORY
    staged_install = pending / "darkos-downloader"
    fake_commands = tmp_path / "commands"
    install_directory.mkdir(parents=True)
    staged_install.mkdir(parents=True)
    fake_commands.mkdir()
    launcher = tools_directory / "dArkOS Downloader.sh"
    source_launcher = REPOSITORY_ROOT / "darkos" / "dArkOS Downloader.sh"
    shutil.copy2(source_launcher, launcher)
    shutil.copy2(source_launcher, pending / "dArkOS Downloader.sh")
    current_executable = install_directory / "darkos-downloader"
    current_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    staged_executable = staged_install / "darkos-downloader"
    staged_executable.write_text("#!/bin/sh\n# updated\nexit 0\n", encoding="utf-8")
    current_executable.chmod(0o755)
    staged_executable.chmod(0o755)
    downloads = install_directory / ".downloads"
    downloads.mkdir()
    (downloads / "preference.json").write_text("saved\n", encoding="utf-8")
    (pending / READY_MARKER).write_text("1.2.0\n", encoding="ascii")
    _write_executable(fake_commands / "uname", "#!/bin/sh\nprintf 'aarch64\\n'\n")
    _write_executable(fake_commands / "dialog", "#!/bin/sh\nexit 0\n")
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_commands}{os.pathsep}{environment['PATH']}"

    completed = subprocess.run(
        ["/bin/sh", str(launcher), "--run-on-vt"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "# updated" in (install_directory / "darkos-downloader").read_text(encoding="utf-8")
    assert (install_directory / ".downloads" / "preference.json").read_text() == "saved\n"
    assert not pending.exists()
    assert not (tools_directory / ".darkos-downloader-backup").exists()


def _bundle_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("tools/dArkOS Downloader.sh", b"#!/bin/sh\n")
        archive.writestr("tools/darkos-downloader/darkos-downloader", _arm64_elf())
        archive.writestr("tools/darkos-downloader/_internal/library.zip", b"runtime")
    return output.getvalue()


def _arm64_elf() -> bytes:
    identification = b"\x7fELF" + bytes((2, 1, 1, 0)) + b"\0" * 8
    return identification + b"\x02\x00\xb7\x00" + b"test executable"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
