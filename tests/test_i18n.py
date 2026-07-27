import ast
from pathlib import Path

import pytest

from ph import tui as tui_module
from ph.i18n import (
    LANGUAGES,
    language_name,
    mismatched_placeholder_keys,
    missing_translation_keys,
    normalize_language,
    translate,
)
from ph.translation_keys import TranslationKey


def test_every_supported_language_has_a_complete_catalogue() -> None:
    assert [language.code for language in LANGUAGES] == [
        "en",
        "de",
        "es",
        "fr",
        "it",
        "pt",
    ]
    assert all(not missing_translation_keys(language.code) for language in LANGUAGES)
    assert all(not mismatched_placeholder_keys(language.code) for language in LANGUAGES)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("EN-us", "en"),
        (" de-CH ", "de"),
        ("pt-BR", "pt"),
        ("fr-CH", "fr"),
    ],
)
def test_language_codes_are_normalized_with_an_english_fallback(
    value: object,
    expected: str,
) -> None:
    assert normalize_language(value) == expected


def test_translation_formats_values_and_language_names_are_native() -> None:
    assert translate("it", TranslationKey.LOADING_ALL, platform="Game Boy") == (
        "Caricamento di tutti i giochi Game Boy..."
    )
    assert translate("fr", TranslationKey.SEARCH_LIBRARY) == "Rechercher dans la bibliothèque"
    assert language_name("de") == "Deutsch"


def test_unknown_translation_key_fails_during_development() -> None:
    with pytest.raises(ValueError):
        TranslationKey("not-a-real-key")


def test_tui_presentation_text_uses_the_translation_catalogue() -> None:
    source_path = Path(tui_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    presentation_methods = {
        "_choose_from_roots",
        "_draw_message",
        "_error",
        "_footer",
        "_menu",
        "_on_screen_keyboard",
    }
    violations: list[int] = []

    def find_literal_text(node: ast.AST) -> None:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_t"
        ):
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(character.isalpha() for character in node.value):
                violations.append(node.lineno)
            return
        for child in ast.iter_child_nodes(node):
            find_literal_text(child)

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in presentation_methods
        ):
            continue
        for argument in (*node.args, *node.keywords):
            find_literal_text(argument.value if isinstance(argument, ast.keyword) else argument)

    assert not violations, f"Untranslated TUI presentation text at lines {sorted(set(violations))}"
