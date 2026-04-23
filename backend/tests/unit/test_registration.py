"""Unit tests for registration service helpers (no DB required)."""
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.services.registration_service import (
    _assert_step_index,
    _calc_completeness,
    _validate_age,
    registration_step_from_data,
    search_preferences_complete,
)
from shared.db.models import Profile


def _profile(**kwargs: object) -> Profile:
    """Detached Profile for unit tests (no session)."""
    defaults: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "display_name": None,
        "bio": None,
        "birth_date": None,
        "gender": None,
        "city": None,
        "district": None,
        "latitude": None,
        "longitude": None,
        "interests": None,
        "completeness_score": 0,
        "updated_at": None,
    }
    defaults.update(kwargs)
    return Profile(**defaults)


def _prefs(**kwargs: object) -> SimpleNamespace:
    base = dict(
        age_min=None,
        age_max=None,
        gender_preferences=None,
        max_distance_km=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_search_preferences_complete_false_when_none() -> None:
    assert search_preferences_complete(None) is False


def test_search_preferences_complete_true() -> None:
    p = _prefs(age_min=18, age_max=40, gender_preferences=[], max_distance_km=50)
    assert search_preferences_complete(p) is True


def test_search_preferences_complete_false_when_gender_null() -> None:
    p = _prefs(age_min=18, age_max=40, gender_preferences=None, max_distance_km=50)
    assert search_preferences_complete(p) is False


# ── registration_step_from_data ───────────────────────────────────────────────


def test_step_no_profile_returns_display_name() -> None:
    assert (
        registration_step_from_data(
            None,
            registration_completed=False,
            photo_count=0,
            prefs=None,
            min_photos=1,
        )
        == "display_name"
    )


def test_step_returns_display_name_when_name_missing() -> None:
    assert (
        registration_step_from_data(
            _profile(),
            registration_completed=False,
            photo_count=0,
            prefs=None,
            min_photos=1,
        )
        == "display_name"
    )


def test_step_returns_birth_date_after_name() -> None:
    p = _profile(display_name="Alice")
    assert (
        registration_step_from_data(
            p, registration_completed=False, photo_count=0, prefs=None, min_photos=1
        )
        == "birth_date"
    )


def test_step_returns_gender_after_birth_date() -> None:
    p = _profile(display_name="Alice", birth_date=date(1995, 5, 20))
    assert (
        registration_step_from_data(
            p, registration_completed=False, photo_count=0, prefs=None, min_photos=1
        )
        == "gender"
    )


def test_step_returns_location_after_gender() -> None:
    p = _profile(display_name="Alice", birth_date=date(1995, 5, 20), gender="female")
    assert (
        registration_step_from_data(
            p, registration_completed=False, photo_count=0, prefs=None, min_photos=1
        )
        == "location"
    )


def test_step_returns_photos_when_location_set_insufficient_photos() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    assert (
        registration_step_from_data(
            p, registration_completed=False, photo_count=0, prefs=None, min_photos=1
        )
        == "photos"
    )


def test_step_returns_search_preferences_when_photos_ok_prefs_incomplete() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    prefs = _prefs(age_min=18, age_max=None, gender_preferences=[], max_distance_km=None)
    assert (
        registration_step_from_data(
            p, registration_completed=False, photo_count=1, prefs=prefs, min_photos=1
        )
        == "search_preferences"
    )


def test_step_returns_optional_profile_when_prefs_complete() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    prefs = _prefs(age_min=18, age_max=40, gender_preferences=[], max_distance_km=50)
    assert (
        registration_step_from_data(
            p, registration_completed=False, photo_count=1, prefs=prefs, min_photos=1
        )
        == "optional_profile"
    )


def test_step_returns_complete_when_registration_completed() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    prefs = _prefs(age_min=18, age_max=40, gender_preferences=[], max_distance_km=50)
    assert (
        registration_step_from_data(
            p, registration_completed=True, photo_count=1, prefs=prefs, min_photos=1
        )
        == "complete"
    )


# ── _validate_age ─────────────────────────────────────────────────────────────


def test_validate_age_passes_for_adult() -> None:
    _validate_age(date(1990, 1, 1))


def test_validate_age_raises_for_minor() -> None:
    young = date.today() - timedelta(days=365 * 17)
    with pytest.raises(HTTPException, match="18"):
        _validate_age(young)


def test_validate_age_raises_for_future_date() -> None:
    with pytest.raises(HTTPException, match="future"):
        _validate_age(date.today() + timedelta(days=1))


# ── _assert_step_index ────────────────────────────────────────────────────────


def test_assert_step_allows_current_step() -> None:
    _assert_step_index("birth_date", "birth_date")


def test_assert_step_rejects_past_step() -> None:
    with pytest.raises(HTTPException, match="already completed"):
        _assert_step_index("complete", "display_name")


def test_assert_step_rejects_future_step() -> None:
    with pytest.raises(HTTPException, match="Cannot set"):
        _assert_step_index("display_name", "gender")


# ── _calc_completeness ────────────────────────────────────────────────────────


def test_calc_completeness_zero_for_empty() -> None:
    assert _calc_completeness(_profile(), 0) == 0


def test_calc_completeness_full_stage2_no_photos() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    assert _calc_completeness(p, 0) == 40


def test_calc_completeness_includes_photos() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    assert _calc_completeness(p, 1) == 60


def test_calc_completeness_includes_bio() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
        bio="About me",
    )
    assert _calc_completeness(p, 1) == 80


def test_calc_completeness_includes_interests() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
        interests=["music"],
    )
    assert _calc_completeness(p, 1) == 80


def test_calc_completeness_bio_and_interests() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
        bio="Hello",
        interests=["books", "travel"],
    )
    assert _calc_completeness(p, 1) == 100


def test_calc_completeness_whitespace_bio_does_not_count() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
        bio="   \n",
    )
    assert _calc_completeness(p, 1) == 60
