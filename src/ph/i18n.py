"""Type-safe translations loaded from packaged YAML catalogues."""

from dataclasses import dataclass
from importlib.resources import files
from string import Formatter
from typing import Literal

import yaml

from ph.translation_keys import TranslationKey

type LanguageCode = Literal["en", "de", "es", "fr", "it", "pt"]

DEFAULT_LANGUAGE: LanguageCode = "en"


@dataclass(frozen=True, slots=True)
class Language:
    """One selectable interface language."""

    code: LanguageCode
    name: str


LANGUAGES: tuple[Language, ...] = (
    Language("en", "English"),
    Language("de", "Deutsch"),
    Language("es", "Español"),
    Language("fr", "Français"),
    Language("it", "Italiano"),
    Language("pt", "Português"),
)


def _load_catalogue(language: LanguageCode) -> dict[TranslationKey, str]:
    """Load and validate one packaged translation catalogue."""

    resource = files("ph.translations").joinpath(f"{language}.yaml")
    payload: object = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Translation catalogue {language!r} must be a mapping")

    catalogue: dict[TranslationKey, str] = {}
    for raw_key, raw_value in payload.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise TypeError(
                f"Translation catalogue {language!r} must contain string keys and values"
            )
        try:
            key = TranslationKey(raw_key)
        except ValueError as error:
            raise ValueError(
                f"Translation catalogue {language!r} contains unknown key {raw_key!r}"
            ) from error
        catalogue[key] = raw_value

    missing = frozenset(TranslationKey).difference(catalogue)
    if missing:
        names = ", ".join(sorted(key.value for key in missing))
        raise ValueError(f"Translation catalogue {language!r} is missing: {names}")
    return catalogue


_TRANSLATIONS: dict[LanguageCode, dict[TranslationKey, str]] = {
    language.code: _load_catalogue(language.code) for language in LANGUAGES
}
_ENGLISH = _TRANSLATIONS[DEFAULT_LANGUAGE]


def normalize_language(value: object) -> LanguageCode:
    """Return a supported language code, defaulting safely to English."""

    if isinstance(value, str):
        normalized = value.strip().casefold().split("-", maxsplit=1)[0]
        match normalized:
            case "en" | "de" | "es" | "fr" | "it" | "pt":
                return normalized
    return DEFAULT_LANGUAGE


def language_name(code: LanguageCode) -> str:
    """Return the native display name for a supported language."""

    return next(language.name for language in LANGUAGES if language.code == code)


def translate(code: LanguageCode, key: TranslationKey, **values: object) -> str:
    """Translate a type-safe UI key and interpolate its named values."""

    template = _TRANSLATIONS[code][key]
    return template.format_map(values) if values else template


def missing_translation_keys(language: LanguageCode) -> frozenset[TranslationKey]:
    """Expose catalogue completeness for validation tests."""

    return frozenset(_ENGLISH).difference(_TRANSLATIONS[language])


def _placeholder_fields(template: str) -> frozenset[str]:
    formatter = Formatter()
    return frozenset(
        field_name
        for _literal, field_name, _format_spec, _conversion in formatter.parse(template)
        if field_name is not None
    )


def mismatched_placeholder_keys(language: LanguageCode) -> frozenset[TranslationKey]:
    """Return translations whose named format fields differ from English."""

    catalogue = _TRANSLATIONS[language]
    return frozenset(
        key
        for key, english in _ENGLISH.items()
        if _placeholder_fields(catalogue[key]) != _placeholder_fields(english)
    )
