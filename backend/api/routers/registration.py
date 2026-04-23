from fastapi import APIRouter

from api.dependencies import BotAuth, DBSession, GeoProvider, S3Client
from api.schemas.profile import TelegramIdBody
from api.schemas.registration import (
    BirthDateRequest,
    CompleteRequest,
    DisplayNameRequest,
    GenderRequest,
    LocationRequest,
    PhotoRequest,
    ReferralCodeResponse,
    RegistrationBioRequest,
    RegistrationInterestsRequest,
    RegistrationStateResponse,
    SearchPrefsAgeRequest,
    SearchPrefsDistanceRequest,
    SearchPrefsGenderRequest,
    StartRequest,
)
from api.services import registration_service as svc

router = APIRouter(prefix="/registration", tags=["registration"])


@router.post("/start", response_model=RegistrationStateResponse)
async def start_registration(
    body: StartRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    user, is_new = await svc.registration_start(
        session,
        telegram_id=body.telegram_id,
        username=body.username,
        referral_code=body.referral_code,
    )
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, is_new_user=is_new)


@router.post("/referral", response_model=ReferralCodeResponse)
async def get_referral_code(
    body: TelegramIdBody,
    session: DBSession,
    _auth: BotAuth,
) -> ReferralCodeResponse:
    data = await svc.get_referral_info(session, body.telegram_id)
    return ReferralCodeResponse(**data)


@router.post("/display-name", response_model=RegistrationStateResponse)
async def set_display_name(
    body: DisplayNameRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_display_name(session, body.telegram_id, body.display_name)
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Display name saved.")


@router.post("/birth-date", response_model=RegistrationStateResponse)
async def set_birth_date(
    body: BirthDateRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_birth_date(session, body.telegram_id, body.birth_date)
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Birth date saved.")


@router.post("/gender", response_model=RegistrationStateResponse)
async def set_gender(
    body: GenderRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_gender(session, body.telegram_id, body.gender)
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Gender saved.")


@router.post("/location", response_model=RegistrationStateResponse)
async def set_location(
    body: LocationRequest,
    session: DBSession,
    geocoder: GeoProvider,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_location(
        session, body.telegram_id, body.latitude, body.longitude, geocoder
    )
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Location saved.")


@router.post("/photo", response_model=RegistrationStateResponse)
async def add_registration_photo(
    body: PhotoRequest,
    session: DBSession,
    s3: S3Client,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.add_registration_photo(
        session, body.telegram_id, body.file_id, s3
    )
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Photo saved.")


@router.post("/search-preferences/age-range", response_model=RegistrationStateResponse)
async def registration_search_prefs_age(
    body: SearchPrefsAgeRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_registration_search_age(
        session, body.telegram_id, body.age_min, body.age_max
    )
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Search age range saved.")


@router.post("/search-preferences/gender", response_model=RegistrationStateResponse)
async def registration_search_prefs_gender(
    body: SearchPrefsGenderRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_registration_search_gender(
        session, body.telegram_id, list(body.gender_preferences)
    )
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Gender preferences saved.")


@router.post("/search-preferences/distance", response_model=RegistrationStateResponse)
async def registration_search_prefs_distance(
    body: SearchPrefsDistanceRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_registration_search_distance(
        session, body.telegram_id, body.max_distance_km
    )
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Max distance saved.")


@router.post("/bio", response_model=RegistrationStateResponse)
async def registration_bio(
    body: RegistrationBioRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_registration_bio(session, body.telegram_id, body.bio)
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Bio saved.")


@router.post("/interests", response_model=RegistrationStateResponse)
async def registration_interests(
    body: RegistrationInterestsRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.set_registration_interests(session, body.telegram_id, body.interest_ids)
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Interests saved.")


@router.post("/complete", response_model=RegistrationStateResponse)
async def complete_registration(
    body: CompleteRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.complete_registration(session, body.telegram_id)
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Registration complete!")
