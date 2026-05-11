from fastapi import APIRouter, Depends

from api.dependencies import DBSession, require_bot_auth
from api.schemas.profile import SimpleOkResponse
from api.schemas.registration import (
    SearchPrefsAgeRequest,
    SearchPrefsDistanceRequest,
    SearchPrefsGenderRequest,
)
from api.services import preferences_edit_service as pref_edit

router = APIRouter(
    prefix="/preferences",
    tags=["preferences"],
    dependencies=[Depends(require_bot_auth)],
)


@router.post("/age-range", response_model=SimpleOkResponse)
async def preferences_age_range(
    body: SearchPrefsAgeRequest,
    session: DBSession,
) -> SimpleOkResponse:
    await pref_edit.edit_age_range(session, body.telegram_id, body.age_min, body.age_max)
    return SimpleOkResponse(message="Age range updated.")


@router.post("/gender", response_model=SimpleOkResponse)
async def preferences_gender(
    body: SearchPrefsGenderRequest,
    session: DBSession,
) -> SimpleOkResponse:
    await pref_edit.edit_gender_preferences(
        session, body.telegram_id, list(body.gender_preferences)
    )
    return SimpleOkResponse(message="Gender preferences updated.")


@router.post("/max-distance", response_model=SimpleOkResponse)
async def preferences_max_distance(
    body: SearchPrefsDistanceRequest,
    session: DBSession,
) -> SimpleOkResponse:
    await pref_edit.edit_max_distance(session, body.telegram_id, body.max_distance_km)
    return SimpleOkResponse(message="Max distance updated.")
