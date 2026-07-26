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
from pytest_mock import MockerFixture

from ph.updater import (
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


def test_find_update_selects_exact_device_release_asset(mocker: MockerFixture) -> None:
    payload = json.dumps(
        {
            "tag_name": "v1.2.0",
            "assets": [
                {
                    "name": "pocket-harbor-1.2.0-darkos-arm64.zip",
                    "browser_download_url": "https://example.test/device.zip",
                    "size": 1234,
                }
            ],
        }
    ).encode()
    mocker.patch("ph.updater.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    release = find_update("1.0.1", "https://api.example.test/releases/latest")

    assert release == ReleaseUpdate(
        "1.2.0",
        "v1.2.0",
        "pocket-harbor-1.2.0-darkos-arm64.zip",
        "https://example.test/device.zip",
        1234,
    )


def test_find_update_returns_none_for_same_or_older_release(
    mocker: MockerFixture,
) -> None:
    payload = json.dumps({"tag_name": "v1.0.1", "assets": []}).encode()
    mocker.patch("ph.updater.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    assert find_update("1.0.1", "https://api.example.test/releases/latest") is None


def test_find_update_requires_the_versioned_device_bundle(
    mocker: MockerFixture,
) -> None:
    payload = json.dumps({"tag_name": "v2.0.0", "assets": []}).encode()
    mocker.patch("ph.updater.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    with pytest.raises(UpdateError, match=r"pocket-harbor-2\.0\.0-darkos-arm64\.zip"):
        find_update("1.0.1", "https://api.example.test/releases/latest")


def test_stage_update_validates_bundle_and_leaves_current_install_untouched(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    install_directory = tmp_path / "tools" / "pocket-harbor"
    install_directory.mkdir(parents=True)
    current_executable = install_directory / "pocket-harbor"
    current_executable.write_bytes(b"current")
    archive = _bundle_bytes()
    requested: list[str] = []

    def fake_urlopen(request: Request, **_kwargs: object) -> FakeResponse:
        requested.append(request.full_url)
        return FakeResponse(archive)

    mocker.patch("ph.updater.urlopen", fake_urlopen)
    release = ReleaseUpdate(
        "1.2.0",
        "v1.2.0",
        "pocket-harbor-1.2.0-darkos-arm64.zip",
        "https://example.test/device.zip",
        len(archive),
    )

    pending = stage_update(release, install_directory)

    assert requested == [release.asset_url]
    assert pending == tmp_path / "tools" / PENDING_UPDATE_DIRECTORY
    assert (pending / READY_MARKER).read_text(encoding="ascii") == "1.2.0\n"
    staged_executable = pending / "pocket-harbor" / "pocket-harbor"
    assert staged_executable.read_bytes() == _arm64_elf()
    assert staged_executable.stat().st_mode & stat.S_IXUSR
    assert (pending / "Pocket Harbor.sh").is_file()
    assert current_executable.read_bytes() == b"current"
    assert not (tmp_path / "tools" / f"{PENDING_UPDATE_DIRECTORY}.zip.part").exists()


def test_stage_update_rejects_path_traversal_and_removes_partial_state(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    install_directory = tmp_path / "tools" / "pocket-harbor"
    install_directory.mkdir(parents=True)
    (install_directory / "pocket-harbor").write_bytes(b"current")
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("tools/../escaped", b"unsafe")
    mocker.patch(
        "ph.updater.urlopen",
        lambda *_args, **_kwargs: FakeResponse(archive_buffer.getvalue()),
    )
    release = ReleaseUpdate("2.0.0", "v2.0.0", "update.zip", "https://example.test/a", None)

    with pytest.raises(UpdateError, match="Unsafe path"):
        stage_update(release, install_directory)

    assert not (tmp_path / "tools" / "escaped").exists()
    assert not (tmp_path / "tools" / PENDING_UPDATE_DIRECTORY).exists()
    assert not (tmp_path / "tools" / f"{PENDING_UPDATE_DIRECTORY}.incomplete").exists()


def test_stage_update_can_be_cancelled_before_network_access(tmp_path: Path) -> None:
    install_directory = tmp_path / "tools" / "pocket-harbor"
    install_directory.mkdir(parents=True)
    (install_directory / "pocket-harbor").write_bytes(b"current")
    release = ReleaseUpdate("2.0.0", "v2.0.0", "update.zip", "https://example.test/a", None)

    with pytest.raises(UpdateCancelled):
        stage_update(release, install_directory, cancelled=lambda: True)


def test_device_launcher_applies_pending_update_and_preserves_download_state(
    tmp_path: Path,
) -> None:
    tools_directory = tmp_path / "tools"
    install_directory = tools_directory / "pocket-harbor"
    pending = tools_directory / PENDING_UPDATE_DIRECTORY
    staged_install = pending / "pocket-harbor"
    fake_commands = tmp_path / "commands"
    install_directory.mkdir(parents=True)
    staged_install.mkdir(parents=True)
    fake_commands.mkdir()
    launcher = tools_directory / "Pocket Harbor.sh"
    source_launcher = REPOSITORY_ROOT / "darkos" / "Pocket Harbor.sh"
    shutil.copy2(source_launcher, launcher)
    shutil.copy2(source_launcher, pending / "Pocket Harbor.sh")
    current_executable = install_directory / "pocket-harbor"
    current_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    staged_executable = staged_install / "pocket-harbor"
    staged_executable.write_text(
        "#!/bin/sh\n# updated\n"
        'if [ "${1:-}" = "--version" ]; then printf "ph 1.2.0\\n"; exit 0; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    current_executable.chmod(0o755)
    staged_executable.chmod(0o755)
    downloads = install_directory / ".downloads"
    downloads.mkdir()
    preferences = downloads / ".pocket-harbor.json"
    preferences.write_text('{"store": "minerva"}\n', encoding="utf-8")
    (pending / READY_MARKER).write_text("1.2.0\n", encoding="ascii")
    _write_executable(fake_commands / "uname", "#!/bin/sh\nprintf 'aarch64\\n'\n")
    dialog_called = tmp_path / "dialog-called"
    _write_executable(
        fake_commands / "dialog",
        f'#!/bin/sh\ntouch "{dialog_called}"\nexit 0\n',
    )
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
    assert "# updated" in (install_directory / "pocket-harbor").read_text(encoding="utf-8")
    assert preferences.read_text(encoding="utf-8") == '{"store": "minerva"}\n'
    assert not pending.exists()
    assert (tools_directory / ".pocket-harbor-backup").is_dir()
    assert not dialog_called.exists()

    confirmed = subprocess.run(
        ["/bin/sh", str(launcher), "--run-on-vt"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert confirmed.returncode == 0, confirmed.stderr
    assert preferences.read_text(encoding="utf-8") == '{"store": "minerva"}\n'
    assert not (tools_directory / ".pocket-harbor-backup").exists()
    assert not dialog_called.exists()


def test_device_launcher_rolls_back_a_crashing_update_and_keeps_preferences(
    tmp_path: Path,
) -> None:
    tools_directory = tmp_path / "tools"
    install_directory = tools_directory / "pocket-harbor"
    pending = tools_directory / PENDING_UPDATE_DIRECTORY
    staged_install = pending / "pocket-harbor"
    fake_commands = tmp_path / "commands"
    install_directory.mkdir(parents=True)
    staged_install.mkdir(parents=True)
    fake_commands.mkdir()
    launcher = tools_directory / "Pocket Harbor.sh"
    source_launcher = REPOSITORY_ROOT / "darkos" / "Pocket Harbor.sh"
    shutil.copy2(source_launcher, launcher)
    shutil.copy2(source_launcher, pending / "Pocket Harbor.sh")
    current_executable = install_directory / "pocket-harbor"
    current_executable.write_text("#!/bin/sh\n# previous\nexit 0\n", encoding="utf-8")
    staged_executable = staged_install / "pocket-harbor"
    staged_executable.write_text(
        "#!/bin/sh\n# crashing update\n"
        'if [ "${1:-}" = "--version" ]; then printf "ph 1.2.0\\n"; exit 0; fi\n'
        'printf "updated TUI crashed\\n" >&2\nexit 42\n',
        encoding="utf-8",
    )
    current_executable.chmod(0o755)
    staged_executable.chmod(0o755)
    downloads = install_directory / ".downloads"
    downloads.mkdir()
    preferences = downloads / ".pocket-harbor.json"
    preferences.write_text('{"store": "minerva"}\n', encoding="utf-8")
    (pending / READY_MARKER).write_text("1.2.0\n", encoding="ascii")
    _write_executable(fake_commands / "uname", "#!/bin/sh\nprintf 'aarch64\\n'\n")
    dialog_called = tmp_path / "dialog-called"
    _write_executable(
        fake_commands / "dialog",
        f'#!/bin/sh\ntouch "{dialog_called}"\nexit 0\n',
    )
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_commands}{os.pathsep}{environment['PATH']}"

    installed = subprocess.run(
        ["/bin/sh", str(launcher), "--run-on-vt"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert installed.returncode == 0, installed.stderr
    assert "# crashing update" in current_executable.read_text(encoding="utf-8")
    assert (tools_directory / ".pocket-harbor-backup").is_dir()

    recovered = subprocess.run(
        ["/bin/sh", str(launcher), "--run-on-vt"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert recovered.returncode == 0, recovered.stderr
    assert "# previous" in current_executable.read_text(encoding="utf-8")
    assert preferences.read_text(encoding="utf-8") == '{"store": "minerva"}\n'
    assert "updated TUI crashed" in (install_directory / "pocket-harbor.log").read_text()
    assert "Rolled back application update" in (install_directory / "pocket-harbor.log").read_text()
    assert not (tools_directory / ".pocket-harbor-backup").exists()
    assert not dialog_called.exists()


def test_device_launcher_recovers_preferences_after_interrupted_update(
    tmp_path: Path,
) -> None:
    tools_directory = tmp_path / "tools"
    install_directory = tools_directory / "pocket-harbor"
    backup = tools_directory / ".pocket-harbor-backup"
    fake_commands = tmp_path / "commands"
    install_directory.mkdir(parents=True)
    backup.mkdir(parents=True)
    fake_commands.mkdir()
    launcher = tools_directory / "Pocket Harbor.sh"
    source_launcher = REPOSITORY_ROOT / "darkos" / "Pocket Harbor.sh"
    shutil.copy2(source_launcher, launcher)
    shutil.copy2(source_launcher, backup / ".previous-launcher.sh")
    interrupted_executable = install_directory / "pocket-harbor"
    interrupted_executable.write_text("#!/bin/sh\n# incomplete update\nexit 0\n", encoding="utf-8")
    previous_executable = backup / "pocket-harbor"
    previous_executable.write_text("#!/bin/sh\n# previous\nexit 0\n", encoding="utf-8")
    interrupted_executable.chmod(0o755)
    previous_executable.chmod(0o755)
    preferences = backup / ".downloads" / ".pocket-harbor.json"
    preferences.parent.mkdir()
    preferences.write_text('{"store": "minerva"}\n', encoding="utf-8")
    _write_executable(fake_commands / "uname", "#!/bin/sh\nprintf 'aarch64\\n'\n")
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_commands}{os.pathsep}{environment['PATH']}"

    recovered = subprocess.run(
        ["/bin/sh", str(launcher), "--run-on-vt"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert recovered.returncode == 0, recovered.stderr
    assert "# previous" in interrupted_executable.read_text(encoding="utf-8")
    restored_preferences = install_directory / ".downloads" / ".pocket-harbor.json"
    assert restored_preferences.read_text(encoding="utf-8") == '{"store": "minerva"}\n'
    assert (
        "update transaction was interrupted"
        in (install_directory / "pocket-harbor.log").read_text()
    )
    assert not backup.exists()


def _bundle_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("tools/Pocket Harbor.sh", b"#!/bin/sh\n")
        archive.writestr("tools/pocket-harbor/pocket-harbor", _arm64_elf())
        archive.writestr("tools/pocket-harbor/_internal/library.zip", b"runtime")
    return output.getvalue()


def _arm64_elf() -> bytes:
    identification = b"\x7fELF" + bytes((2, 1, 1, 0)) + b"\0" * 8
    return identification + b"\x02\x00\xb7\x00" + b"test executable"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
