"""Unit tests for registration service helpers (no DB required)."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.services.registration_service import (
    _assert_step_order,
    _calc_completeness,
    _infer_step,
    _validate_age,
)
from shared.db.models import Profile


def _profile(**kwargs) -> Profile:
    p = Profile.__new__(Profile)
    for k, v in kwargs.items():
        object.__setattr__(p, k, v)
    for field in ("display_name", "birth_date", "gender", "city", "district"):
        if not hasattr(p, field):
            object.__setattr__(p, field, None)
    object.__setattr__(p, "completeness_score", 0)
    return p


# ── _infer_step ───────────────────────────────────────────────────────────────

def test_infer_step_no_profile_returns_display_name() -> None:
    assert _infer_step(None) == "display_name"


def test_infer_step_returns_display_name_when_name_missing() -> None:
    assert _infer_step(_profile()) == "display_name"


def test_infer_step_returns_birth_date_after_name() -> None:
    p = _profile(display_name="Alice")
    assert _infer_step(p) == "birth_date"


def test_infer_step_returns_gender_after_birth_date() -> None:
    p = _profile(display_name="Alice", birth_date=date(1995, 5, 20))
    assert _infer_step(p) == "gender"


def test_infer_step_returns_location_after_gender() -> None:
    p = _profile(display_name="Alice", birth_date=date(1995, 5, 20), gender="female")
    assert _infer_step(p) == "location"


def test_infer_step_returns_complete_when_all_set() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    assert _infer_step(p) == "complete"


# ── _validate_age ─────────────────────────────────────────────────────────────

def test_validate_age_passes_for_adult() -> None:
    _validate_age(date(1990, 1, 1))  # no exception


def test_validate_age_raises_for_minor() -> None:
    young = date.today() - timedelta(days=365 * 17)
    with pytest.raises(HTTPException, match="18"):
        _validate_age(young)


def test_validate_age_raises_for_future_date() -> None:
    with pytest.raises(HTTPException, match="future"):
        _validate_age(date.today() + timedelta(days=1))


# ── _assert_step_order ────────────────────────────────────────────────────────

def test_assert_step_order_allows_current_step() -> None:
    p = _profile(display_name="Alice")
    _assert_step_order(p, "birth_date")  # current step == expected → ok


def test_assert_step_order_rejects_past_step() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    with pytest.raises(HTTPException, match="already completed"):
        _assert_step_order(p, "display_name")


def test_assert_step_order_rejects_future_step() -> None:
    p = _profile()  # current step is display_name
    with pytest.raises(HTTPException, match="Cannot set"):
        _assert_step_order(p, "gender")


# ── _calc_completeness ────────────────────────────────────────────────────────

def test_calc_completeness_zero_for_empty() -> None:
    assert _calc_completeness(_profile()) == 0


def test_calc_completeness_full_stage2() -> None:
    p = _profile(
        display_name="Alice",
        birth_date=date(1995, 5, 20),
        gender="female",
        city="Moscow",
    )
    assert _calc_completeness(p) == 40
