import pytest

from dw_cli.app import build_parser


def test_supported_consoles_command_was_removed() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["consoles"])


def test_search_query_is_optional_for_catalogue_listing() -> None:
    arguments = build_parser().parse_args(["search", "GBA"])
    assert arguments.query == []
    assert arguments.store == "vimm"


def test_store_can_be_selected_for_cli_automation() -> None:
    arguments = build_parser().parse_args(["--store", "vimm", "search", "GBA", "Advance"])

    assert arguments.store == "vimm"
    assert arguments.query == ["Advance"]
