from fastapi import APIRouter

from api.dependencies import BotAuth, DBSession, GeoProvider
from api.schemas.registration import (
    BirthDateRequest,
    CompleteRequest,
    DisplayNameRequest,
    GenderRequest,
    LocationRequest,
    RegistrationStateResponse,
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


@router.post("/complete", response_model=RegistrationStateResponse)
async def complete_registration(
    body: CompleteRequest,
    session: DBSession,
    _auth: BotAuth,
) -> RegistrationStateResponse:
    await svc.complete_registration(session, body.telegram_id)
    state = await svc.get_registration_state(session, body.telegram_id)
    return RegistrationStateResponse(**state, message="Registration complete!")
