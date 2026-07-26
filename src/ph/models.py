"""Typed domain models shared by the client and user interfaces."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Platform:
    """A searchable platform and its accepted user-facing names."""

    name: str
    slug: str
    code: str
    alias: str
    rom_folder: str | None = None
    alternate_folders: tuple[str, ...] = ()

    @property
    def rom_folders(self) -> tuple[str, ...]:
        """Return every accepted folder, with the preferred destination first."""

        if self.rom_folder is None:
            return ()
        return (self.rom_folder, *self.alternate_folders)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One row returned by a library search."""

    title: str
    link: str
    system: str = ""
    region: str = ""
    version: str = ""
    languages: str = "-"
    rating: str = "-"


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """A completed download."""

    url: str
    path: Path


@dataclass(frozen=True, slots=True)
class MediaDownload:
    """A resolved media download, optionally selecting one file from a torrent."""

    url: str
    torrent_file_index: int | None = None
    expected_filename: str | None = None
    torrent_file_path: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class InstalledGame:
    """One installed title, optionally composed of several referenced files."""

    title: str
    platform: Platform
    roms_directory: Path
    primary_file: Path
    files: tuple[Path, ...]
