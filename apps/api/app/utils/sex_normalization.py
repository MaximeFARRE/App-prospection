from __future__ import annotations


_MALE_VALUES = {
    "h",
    "m",
    "male",
    "man",
    "homme",
    "masculin",
    "masculine",
}

_FEMALE_VALUES = {
    "f",
    "female",
    "woman",
    "femme",
    "feminin",
    "feminine",
    "féminin",
    "féminine",
}


def normalize_sex(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    if not normalized:
        return None

    if normalized in _MALE_VALUES:
        return "homme"
    if normalized in _FEMALE_VALUES:
        return "femme"
    return None

