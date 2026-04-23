import uuid
from datetime import date, datetime, timezone

from botocore.client import BaseClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.schemas.registration import GenderValue, RegistrationStep
from api.services.profile_photo_service import add_photo_from_telegram, count_profile_photos
from api.services.registration_steps import (
    assert_registration_step_order as _assert_step_index,
    registration_step_from_data,
    search_preferences_complete,
)
from shared.db.models import Profile, ReferralEvent, User, UserPreferences
from shared.geo.cascade import CascadeGeocodingProvider
from shared.geo.provider import GeocodingError
from shared.interests_taxonomy import VALID_INTEREST_IDS

_FIELD_SCORES: dict[str, int] = {
    "display_name": 10,
    "birth_date": 10,
    "gender": 10,
    "city": 10,
}

# Sum with _FIELD_SCORES (40) = 100 when core + ≥1 photo + non-empty bio + ≥1 interest.
_COMPLETENESS_PHOTOS: int = 20
_COMPLETENESS_BIO: int = 20
_COMPLETENESS_INTERESTS: int = 20

_MIN_AGE = 18


async def _get_registration_step(
    session: AsyncSession, user: User, profile: Profile | None
) -> RegistrationStep:
    prefs = await get_preferences_if_exists(session, user.id)
    n_photos = await count_profile_photos(session, user.id) if profile is not None else 0
    return registration_step_from_data(
        profile,
        registration_completed=user.registration_completed,
        photo_count=n_photos,
        prefs=prefs,
        min_photos=settings.registration_min_photos,
    )


async def _assert_current_step(
    session: AsyncSession, user: User, profile: Profile | None, expected: RegistrationStep
) -> None:
    current = await _get_registration_step(session, user, profile)
    _assert_step_index(current, expected)


async def _assert_can_add_photo(
    session: AsyncSession, user: User, profile: Profile | None
) -> None:
    current = await _get_registration_step(session, user, profile)
    if current not in ("photos", "search_preferences", "optional_profile"):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot add photos at step '{current}'.",
        )


def _calc_completeness(profile: Profile, photo_count: int) -> int:
    base = sum(pts for f, pts in _FIELD_SCORES.items() if getattr(profile, f, None) is not None)
    if photo_count > 0:
        base += _COMPLETENESS_PHOTOS
    bio = profile.bio
    if bio is not None and str(bio).strip():
        base += _COMPLETENESS_BIO
    intr = profile.interests
    if isinstance(intr, list) and len(intr) > 0:
        base += _COMPLETENESS_INTERESTS
    return min(base, 100)


compute_profile_completeness = _calc_completeness


def _generate_referral_code() -> str:
    return uuid.uuid4().hex[:8].upper()


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
        registration_completed=False,
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
    await _assert_current_step(session, user, profile, "display_name")
    n_photos = await count_profile_photos(session, user.id)

    profile.display_name = display_name
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = _calc_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def set_birth_date(session: AsyncSession, telegram_id: int, birth_date: date) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    _validate_age(birth_date)

    profile = await _get_or_create_profile(session, user.id)
    await _assert_current_step(session, user, profile, "birth_date")
    n_photos = await count_profile_photos(session, user.id)

    profile.birth_date = birth_date
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = _calc_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def set_gender(session: AsyncSession, telegram_id: int, gender: GenderValue) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    profile = await _get_or_create_profile(session, user.id)
    await _assert_current_step(session, user, profile, "gender")
    n_photos = await count_profile_photos(session, user.id)

    profile.gender = gender
    profile.updated_at = datetime.now(timezone.utc)
    profile.completeness_score = _calc_completeness(profile, n_photos)
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
    current = await _get_registration_step(session, user, profile)
    if current not in ("location", "photos", "search_preferences", "optional_profile"):
        _assert_step_index(current, "location")
    n_photos = await count_profile_photos(session, user.id)

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
    profile.completeness_score = _calc_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def add_registration_photo(
    session: AsyncSession,
    telegram_id: int,
    file_id: str,
    s3_client: BaseClient,
) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    profile = await _get_or_create_profile(session, user.id)
    await _assert_can_add_photo(session, user, profile)
    return await add_photo_from_telegram(
        session,
        user.id,
        profile,
        file_id,
        s3_client,
        max_photos=settings.registration_max_photos,
        recalc_completeness=_calc_completeness,
    )


def _validate_search_age_range(age_min: int, age_max: int) -> None:
    if age_min > age_max:
        raise HTTPException(status_code=422, detail="age_min cannot be greater than age_max.")
    if age_min < _MIN_AGE:
        raise HTTPException(status_code=422, detail=f"Minimum search age must be at least {_MIN_AGE}.")
    if age_max > 120:
        raise HTTPException(status_code=422, detail="age_max is out of range.")


def _validate_max_distance_km(km: int) -> None:
    cap = settings.preferences_max_distance_km
    if km > cap:
        raise HTTPException(
            status_code=422,
            detail=f"max_distance_km cannot exceed {cap}.",
        )


async def set_registration_search_age(
    session: AsyncSession, telegram_id: int, age_min: int, age_max: int
) -> UserPreferences:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")
    if user.registration_completed:
        raise HTTPException(status_code=409, detail="Registration already completed.")

    profile = await _get_or_create_profile(session, user.id)
    await _assert_current_step(session, user, profile, "search_preferences")
    _validate_search_age_range(age_min, age_max)

    prefs = await _get_or_create_preferences(session, user.id)
    prefs.age_min = age_min
    prefs.age_max = age_max
    prefs.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(prefs)
    return prefs


async def set_registration_search_gender(
    session: AsyncSession, telegram_id: int, gender_preferences: list[GenderValue]
) -> UserPreferences:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")
    if user.registration_completed:
        raise HTTPException(status_code=409, detail="Registration already completed.")

    profile = await _get_or_create_profile(session, user.id)
    await _assert_current_step(session, user, profile, "search_preferences")

    prefs = await _get_or_create_preferences(session, user.id)
    prefs.gender_preferences = list(gender_preferences)
    prefs.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(prefs)
    return prefs


async def set_registration_search_distance(
    session: AsyncSession, telegram_id: int, max_distance_km: int
) -> UserPreferences:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")
    if user.registration_completed:
        raise HTTPException(status_code=409, detail="Registration already completed.")

    profile = await _get_or_create_profile(session, user.id)
    await _assert_current_step(session, user, profile, "search_preferences")
    _validate_max_distance_km(max_distance_km)

    prefs = await _get_or_create_preferences(session, user.id)
    prefs.max_distance_km = max_distance_km
    prefs.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(prefs)
    return prefs


async def set_registration_bio(session: AsyncSession, telegram_id: int, bio: str) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")
    if user.registration_completed:
        raise HTTPException(status_code=409, detail="Registration already completed.")

    profile = await _get_or_create_profile(session, user.id)
    await _assert_current_step(session, user, profile, "optional_profile")
    if len(bio) > settings.profile_bio_max_length:
        raise HTTPException(
            status_code=422,
            detail=f"Bio cannot exceed {settings.profile_bio_max_length} characters.",
        )

    profile.bio = bio or None
    profile.updated_at = datetime.now(timezone.utc)
    n_photos = await count_profile_photos(session, user.id)
    profile.completeness_score = _calc_completeness(profile, n_photos)
    await session.commit()
    await session.refresh(profile)
    return profile


async def set_registration_interests(
    session: AsyncSession, telegram_id: int, interest_ids: list[str]
) -> Profile:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")
    if user.registration_completed:
        raise HTTPException(status_code=409, detail="Registration already completed.")

    profile = await _get_or_create_profile(session, user.id)
    await _assert_current_step(session, user, profile, "optional_profile")
    if len(interest_ids) > settings.profile_max_interests:
        raise HTTPException(
            status_code=422,
            detail=f"At most {settings.profile_max_interests} interests.",
        )
    unknown = [x for x in interest_ids if x not in VALID_INTEREST_IDS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown interest ids: {unknown}",
        )

    profile.interests = list(interest_ids) if interest_ids else None
    profile.updated_at = datetime.now(timezone.utc)
    n_photos = await count_profile_photos(session, user.id)
    profile.completeness_score = _calc_completeness(profile, n_photos)
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

    prefs_existing = await get_preferences_if_exists(session, user.id)
    n_photos = await count_profile_photos(session, user.id)

    if user.registration_completed:
        if prefs_existing is None:
            raise HTTPException(status_code=422, detail="Preferences missing.")
        await session.refresh(profile)
        await session.refresh(prefs_existing)
        return user, profile, prefs_existing

    await _assert_current_step(session, user, profile, "optional_profile")

    missing = [f for f in _FIELD_SCORES if getattr(profile, f, None) is None]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Registration incomplete. Missing fields: {missing}",
        )

    if n_photos < settings.registration_min_photos:
        raise HTTPException(
            status_code=422,
            detail=(
                f"At least {settings.registration_min_photos} profile photo(s) required "
                "to complete registration."
            ),
        )

    if not search_preferences_complete(prefs_existing):
        raise HTTPException(
            status_code=422,
            detail="Search preferences incomplete. Set age range, genders, and max distance.",
        )

    prefs = prefs_existing
    if prefs is None:
        raise HTTPException(status_code=500, detail="Inconsistent preferences state.")
    profile.completeness_score = _calc_completeness(profile, n_photos)

    user.registration_completed = True

    new_referral = False
    if user.referred_by_user_id:
        ref_ins = (
            pg_insert(ReferralEvent)
            .values(
                id=uuid.uuid4(),
                referrer_id=user.referred_by_user_id,
                referee_id=user.id,
            )
            .on_conflict_do_nothing(index_elements=[ReferralEvent.referee_id])
            .returning(ReferralEvent.id)
        )
        ref_res = await session.execute(ref_ins)
        new_referral = ref_res.scalar_one_or_none() is not None

    await session.commit()
    await session.refresh(profile)
    await session.refresh(prefs)

    from api.services import task_helpers

    task_helpers.schedule_rating_recompute(user.id)
    if new_referral and user.referred_by_user_id:
        task_helpers.schedule_rating_recompute(user.referred_by_user_id)

    return user, profile, prefs


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


async def get_preferences_if_exists(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreferences | None:
    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _get_or_create_preferences(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreferences:
    prefs = await get_preferences_if_exists(session, user_id)
    if prefs is None:
        prefs = UserPreferences(user_id=user_id)
        session.add(prefs)
        await session.flush()
    return prefs


async def get_or_create_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    return await _get_or_create_profile(session, user_id)


async def get_or_create_user_preferences(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreferences:
    return await _get_or_create_preferences(session, user_id)


async def get_registration_state(session: AsyncSession, telegram_id: int) -> dict:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    profile = await _get_profile(session, user.id)
    n_photos = await count_profile_photos(session, user.id) if profile is not None else 0
    step = await _get_registration_step(session, user, profile)
    return {
        "user_id": user.id,
        "telegram_id": telegram_id,
        "registration_step": step,
        "is_complete": user.registration_completed,
        "photo_count": n_photos,
    }


async def get_referral_info(session: AsyncSession, telegram_id: int) -> dict[str, str | None]:
    user = await _get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")
    if not user.referral_code:
        user.referral_code = _generate_referral_code()
        await session.commit()
        await session.refresh(user)
    code = user.referral_code
    if not code:
        raise HTTPException(status_code=500, detail="Referral code unavailable.")
    invite_link: str | None = None
    raw = settings.telegram_bot_username
    if raw:
        uname = str(raw).strip().lstrip("@")
        if uname:
            invite_link = f"https://t.me/{uname}?start={code}"
    return {"referral_code": code, "invite_link": invite_link}
