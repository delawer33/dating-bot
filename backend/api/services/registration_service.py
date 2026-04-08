import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.registration import GenderValue, RegistrationStep
from shared.db.models import Profile, User, UserPreferences
from shared.geo.cascade import CascadeGeocodingProvider
from shared.geo.provider import GeocodingError

_FIELD_SCORES: dict[str, int] = {
    "display_name": 10,
    "birth_date": 10,
    "gender": 10,
    "city": 10,
}

_MIN_AGE = 18


def _infer_step(profile: Profile | None) -> RegistrationStep:
    if profile is None or profile.display_name is None:
        return "display_name"
    if profile.birth_date is None:
        return "birth_date"
    if profile.gender is None:
        return "gender"
    if profile.city is None:
        return "location"
    return "complete"


def _generate_referral_code() -> str:
    return uuid.uuid4().hex[:8].upper()


def _calc_completeness(profile: Profile) -> int:
    return sum(pts for f, pts in _FIELD_SCORES.items() if getattr(profile, f, None) is not None)


async def _get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def registration_start(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    referral_code: str | None,
) -> tuple[User, bool]:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if user:
        user.username = username
        await session.commit()
        return user, False

    referred_by_id: uuid.UUID | None = None
    if referral_code:
        result = await session.execute(
            select(User).where(User.referral_code == referral_code)
        )
        referrer = result.scalar_one_or_none()
        if referrer and referrer.telegram_id != telegram_id:
            referred_by_id = referrer.id

    user = User(
        telegram_id=telegram_id,
        username=username,
        referral_code=_generate_referral_code(),
        referred_by_user_id=referred_by_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True


async def set_display_name(session: AsyncSession, telegram_id: int, display_name: str) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    profile = await _get_or_create_profile(session, user.id)
    _assert_step_order(profile, expected="display_name")

    profile.display_name = display_name
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = _calc_completeness(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def set_birth_date(session: AsyncSession, telegram_id: int, birth_date: date) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    _validate_age(birth_date)

    profile = await _get_or_create_profile(session, user.id)
    _assert_step_order(profile, expected="birth_date")

    profile.birth_date = birth_date
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = _calc_completeness(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def set_gender(session: AsyncSession, telegram_id: int, gender: GenderValue) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    profile = await _get_or_create_profile(session, user.id)
    _assert_step_order(profile, expected="gender")

    profile.gender = gender
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = _calc_completeness(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def set_location(
    session: AsyncSession,
    telegram_id: int,
    lat: float,
    lon: float,
    geocoder: CascadeGeocodingProvider,
) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    profile = await _get_or_create_profile(session, user.id)
    _assert_step_order(profile, expected="location")

    try:
        geo = await geocoder.reverse_geocode(lat, lon)
    except GeocodingError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not determine city from coordinates: {exc}",
        ) from exc

    profile.city = geo.city
    profile.district = geo.district
    profile.latitude = lat
    profile.longitude = lon
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = _calc_completeness(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def complete_registration(
    session: AsyncSession, telegram_id: int
) -> tuple[User, Profile, UserPreferences]:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    profile = await _get_profile(session, user.id)
    if profile is None:
        raise HTTPException(status_code=422, detail="Profile not started.")

    missing = [f for f in _FIELD_SCORES if getattr(profile, f, None) is None]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Registration incomplete. Missing fields: {missing}",
        )

    prefs = await _get_or_create_preferences(session, user.id)
    if prefs.age_min is None:
        prefs.age_min = _MIN_AGE
        prefs.age_max = 35
        prefs.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(profile)
    await session.refresh(prefs)
    return user, profile, prefs


def _assert_step_order(profile: Profile, expected: RegistrationStep) -> None:
    current = _infer_step(profile)
    step_order: list[RegistrationStep] = [
        "display_name", "birth_date", "gender", "location", "complete"
    ]
    current_idx = step_order.index(current)
    expected_idx = step_order.index(expected)

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


def _validate_age(birth_date: date) -> None:
    today = date.today()
    age = (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )
    if birth_date >= today:
        raise HTTPException(status_code=422, detail="Birth date cannot be in the future.")
    if age < _MIN_AGE:
        raise HTTPException(status_code=422, detail=f"You must be at least {_MIN_AGE} years old.")


async def _get_or_create_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    profile = await _get_profile(session, user_id)
    if profile is None:
        profile = Profile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


async def _get_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def _get_or_create_preferences(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreferences:
    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        prefs = UserPreferences(user_id=user_id)
        session.add(prefs)
        await session.flush()
    return prefs


async def get_registration_state(session: AsyncSession, telegram_id: int) -> dict:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    profile = await _get_profile(session, user.id)
    step = _infer_step(profile)
    return {
        "user_id": user.id,
        "telegram_id": telegram_id,
        "registration_step": step,
        "is_complete": step == "complete",
    }
