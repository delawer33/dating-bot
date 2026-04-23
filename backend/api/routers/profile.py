from fastapi import APIRouter

from api.dependencies import BotAuth, DBSession, GeoProvider, RedisClient, S3Client
from api.schemas.profile import (
    BioUpdateBody,
    BirthDateUpdateBody,
    DisplayNameUpdateBody,
    GenderUpdateBody,
    InterestsUpdateBody,
    LocationUpdateBody,
    ProfileMeResponse,
    ProfilePhotoAddBody,
    ProfilePhotoDeleteBody,
    ProfilePhotoReorderBody,
    SimpleOkResponse,
    TelegramIdBody,
)
from api.services import profile_edit_service as pe
from api.services import profile_service as profile_svc

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/me", response_model=ProfileMeResponse)
async def profile_me(
    body: TelegramIdBody,
    session: DBSession,
    s3: S3Client,
    _auth: BotAuth,
) -> ProfileMeResponse:
    data = await profile_svc.get_profile_me(session, body.telegram_id, s3)
    return ProfileMeResponse(**data)


@router.post("/display-name", response_model=SimpleOkResponse)
async def profile_display_name(
    body: DisplayNameUpdateBody,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.edit_display_name(session, body.telegram_id, body.display_name)
    return SimpleOkResponse(message="Display name updated.")


@router.post("/birth-date", response_model=SimpleOkResponse)
async def profile_birth_date(
    body: BirthDateUpdateBody,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.edit_birth_date(session, body.telegram_id, body.birth_date)
    return SimpleOkResponse(message="Birth date updated.")


@router.post("/gender", response_model=SimpleOkResponse)
async def profile_gender(
    body: GenderUpdateBody,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.edit_gender(session, body.telegram_id, body.gender)
    return SimpleOkResponse(message="Gender updated.")


@router.post("/location", response_model=SimpleOkResponse)
async def profile_location(
    body: LocationUpdateBody,
    session: DBSession,
    geocoder: GeoProvider,
    redis: RedisClient,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.edit_location(
        session, redis, body.telegram_id, body.latitude, body.longitude, geocoder
    )
    return SimpleOkResponse(message="Location updated.")


@router.post("/bio", response_model=SimpleOkResponse)
async def profile_bio(
    body: BioUpdateBody,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.edit_bio(session, body.telegram_id, body.bio)
    return SimpleOkResponse(message="Bio updated.")


@router.post("/interests", response_model=SimpleOkResponse)
async def profile_interests(
    body: InterestsUpdateBody,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.edit_interests(session, body.telegram_id, body.interest_ids)
    return SimpleOkResponse(message="Interests updated.")


@router.post("/photo", response_model=SimpleOkResponse)
async def profile_add_photo(
    body: ProfilePhotoAddBody,
    session: DBSession,
    s3: S3Client,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.add_profile_photo(session, body.telegram_id, body.file_id, s3)
    return SimpleOkResponse(message="Photo added.")


@router.post("/photo/delete", response_model=SimpleOkResponse)
async def profile_delete_photo(
    body: ProfilePhotoDeleteBody,
    session: DBSession,
    s3: S3Client,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.delete_profile_photo(session, s3, body.telegram_id, body.photo_id)
    return SimpleOkResponse(message="Photo deleted.")


@router.post("/photo/reorder", response_model=SimpleOkResponse)
async def profile_reorder_photos(
    body: ProfilePhotoReorderBody,
    session: DBSession,
    _auth: BotAuth,
) -> SimpleOkResponse:
    await pe.reorder_profile_photos(session, body.telegram_id, body.photo_ids)
    return SimpleOkResponse(message="Photos reordered.")
