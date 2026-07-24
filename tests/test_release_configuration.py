"""Regression coverage for semantic-release and uv version synchronization."""

import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]


def _read_toml(filename: str) -> dict[str, Any]:
    return tomllib.loads((PROJECT_ROOT / filename).read_text(encoding="utf-8"))


def test_project_version_matches_uv_lock() -> None:
    pyproject = _read_toml("pyproject.toml")
    lock = _read_toml("uv.lock")
    project = pyproject["project"]
    locked_project = next(
        package for package in lock["package"] if package["name"] == project["name"]
    )

    assert locked_project["version"] == project["version"]


def test_semantic_release_runs_prek_and_stages_release_files() -> None:
    pyproject = _read_toml("pyproject.toml")
    release_configuration = pyproject["tool"]["semantic_release"]
    build_command = release_configuration["build_command"]

    assert "uv run prek --all-files" in build_command
    assert "git add ." in build_command
    assert build_command.index("uv run prek --all-files") < build_command.index("git add .")
    assert "uv build" in build_command
    assert pyproject["project"]["optional-dependencies"]["release"] == ["uv==0.11.32"]
