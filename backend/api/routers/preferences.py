from fastapi import APIRouter

from api.dependencies import BotAuth, DBSession
from api.schemas.profile import SimpleOkResponse
from api.schemas.registration import (
    SearchPrefsAgeRequest,
    SearchPrefsDistanceRequest,
    SearchPrefsGenderRequest,
)
from api.services import preferences_edit_service as pref_edit

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.post("/age-range", response_model=SimpleOkResponse)
async def preferences_age_range(
    body: SearchPrefsAgeRequest,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pref_edit.edit_age_range(session, body.telegram_id, body.age_min, body.age_max)
    return SimpleOkResponse(message="Age range updated.")


@router.post("/gender", response_model=SimpleOkResponse)
async def preferences_gender(
    body: SearchPrefsGenderRequest,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pref_edit.edit_gender_preferences(
        session, body.telegram_id, list(body.gender_preferences)
    )
    return SimpleOkResponse(message="Gender preferences updated.")


@router.post("/max-distance", response_model=SimpleOkResponse)
async def preferences_max_distance(
    body: SearchPrefsDistanceRequest,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pref_edit.edit_max_distance(session, body.telegram_id, body.max_distance_km)
    return SimpleOkResponse(message="Max distance updated.")
