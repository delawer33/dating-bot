"""Pure registration step ordering and preference completeness checks."""

from __future__ import annotations

from fastapi import HTTPException

from api.schemas.registration import RegistrationStep
from shared.db.models import Profile, UserPreferences

_STEP_ORDER: list[RegistrationStep] = [
    "display_name",
    "birth_date",
    "gender",
    "location",
    "photos",
    "search_preferences",
    "optional_profile",
    "complete",
]


def search_preferences_complete(prefs: UserPreferences | None) -> bool:
    if prefs is None:
        return False
    if prefs.age_min is None or prefs.age_max is None:
        return False
    if prefs.max_distance_km is None:
        return False
    if prefs.gender_preferences is None:
        return False
    return True


def registration_step_from_data(
    profile: Profile | None,
    *,
    registration_completed: bool,
    photo_count: int,
    prefs: UserPreferences | None,
    min_photos: int,
) -> RegistrationStep:
    if registration_completed:
        return "complete"
    if profile is None or profile.display_name is None:
        return "display_name"
    if profile.birth_date is None:
        return "birth_date"
    if profile.gender is None:
        return "gender"
    if profile.city is None:
        return "location"
    if photo_count < min_photos:
        return "photos"
    if not search_preferences_complete(prefs):
        return "search_preferences"
    return "optional_profile"


def assert_registration_step_order(current: RegistrationStep, expected: RegistrationStep) -> None:
    current_idx = _STEP_ORDER.index(current)
    expected_idx = _STEP_ORDER.index(expected)

    if expected_idx < current_idx:
        raise HTTPException(
            status_code=409,
            detail=f"Step '{expected}' already completed. Current step: '{current}'.",
        )
    if expected_idx > current_idx:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot set '{expected}' before completing '{current}'.",
        )
