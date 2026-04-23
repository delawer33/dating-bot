"""Curated interest ids for profile registration and settings (labels for bot UI)."""

from __future__ import annotations

# id -> Russian label (reply keyboard)
INTEREST_LABELS_RU: dict[str, str] = {
    "music": "Музыка",
    "travel": "Путешествия",
    "sport": "Спорт",
    "books": "Книги",
    "cinema": "Кино",
    "food": "Кулинария",
    "games": "Игры",
    "art": "Искусство",
    "nature": "Природа",
    "tech": "Технологии",
}

VALID_INTEREST_IDS: frozenset[str] = frozenset(INTEREST_LABELS_RU.keys())


def sorted_interest_choices() -> list[tuple[str, str]]:
    return sorted(INTEREST_LABELS_RU.items(), key=lambda x: x[1])
