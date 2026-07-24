from pathlib import Path

from dw_cli.preferences import Preferences, load_preferences, preference_path, save_preferences


def test_store_preference_round_trip(tmp_path: Path) -> None:
    path = preference_path(tmp_path / ".downloads")

    save_preferences(path, Preferences("minerva"))

    assert load_preferences(path) == Preferences("minerva")
    assert not path.with_name(path.name + ".tmp").exists()


def test_invalid_preferences_return_first_run_state(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")

    assert load_preferences(path) == Preferences()
