"""Profile API schemas."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field

from api.schemas.discovery import DiscoveryProfileOut
from api.schemas.registration import GenderValue, RegistrationStep


class TelegramIdBody(BaseModel):
    telegram_id: int = Field(..., ge=1)


class PreferencesSummaryOut(BaseModel):
    age_min: int | None = None
    age_max: int | None = None
    gender_preferences: list[str] | None = None
    max_distance_km: int | None = None


class OwnProfileCardOut(DiscoveryProfileOut):
    completeness_score: int


class ProfileMeResponse(BaseModel):
    is_complete: bool
    registration_step: RegistrationStep
    profile: OwnProfileCardOut | None = None
    preferences: PreferencesSummaryOut | None = None
    user_id: uuid.UUID


class SimpleOkResponse(BaseModel):
    ok: bool = True
    message: str = ""


class DisplayNameUpdateBody(TelegramIdBody):
    display_name: str = Field(min_length=1, max_length=64)


class BirthDateUpdateBody(TelegramIdBody):
    birth_date: date


class GenderUpdateBody(TelegramIdBody):
    gender: GenderValue


class LocationUpdateBody(TelegramIdBody):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class BioUpdateBody(TelegramIdBody):
    bio: str = Field(default="", max_length=4000)


class InterestsUpdateBody(TelegramIdBody):
    interest_ids: list[str] = Field(default_factory=list, max_length=50)


class ProfilePhotoAddBody(TelegramIdBody):
    file_id: str = Field(min_length=1, max_length=256)


class ProfilePhotoDeleteBody(TelegramIdBody):
    photo_id: uuid.UUID


class ProfilePhotoReorderBody(TelegramIdBody):
    photo_ids: list[uuid.UUID] = Field(min_length=1)
