import pytest

from ph.i18n import (
    LANGUAGES,
    language_name,
    missing_translation_keys,
    normalize_language,
    translate,
)


def test_every_supported_language_has_a_complete_catalogue() -> None:
    assert [language.code for language in LANGUAGES] == ["en", "de", "es", "it", "pt"]
    assert all(not missing_translation_keys(language.code) for language in LANGUAGES)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("EN-us", "en"),
        (" de-CH ", "de"),
        ("pt-BR", "pt"),
        ("fr", "en"),
    ],
)
def test_language_codes_are_normalized_with_an_english_fallback(
    value: object,
    expected: str,
) -> None:
    assert normalize_language(value) == expected


def test_translation_formats_values_and_language_names_are_native() -> None:
    assert translate("it", "loading_all", platform="Game Boy") == (
        "Caricamento di tutti i giochi Game Boy..."
    )
    assert language_name("de") == "Deutsch"


def test_unknown_translation_key_fails_during_development() -> None:
    with pytest.raises(KeyError):
        translate("en", "not-a-real-key")
