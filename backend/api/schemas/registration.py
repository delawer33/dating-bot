import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RegistrationStep = Literal[
    "display_name",
    "birth_date",
    "gender",
    "location",
    "photos",
    "search_preferences",
    "optional_profile",
    "complete",
]
GenderValue = Literal["male", "female", "non_binary", "other"]


class StartRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    referral_code: str | None = None


class DisplayNameRequest(BaseModel):
    telegram_id: int
    display_name: str = Field(min_length=1, max_length=64)


class BirthDateRequest(BaseModel):
    telegram_id: int
    birth_date: date


class GenderRequest(BaseModel):
    telegram_id: int
    gender: GenderValue


class LocationRequest(BaseModel):
    telegram_id: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CompleteRequest(BaseModel):
    telegram_id: int


class PhotoRequest(BaseModel):
    telegram_id: int
    file_id: str = Field(min_length=1, max_length=256)


class SearchPrefsAgeRequest(BaseModel):
    telegram_id: int
    age_min: int = Field(ge=18, le=120)
    age_max: int = Field(ge=18, le=120)


class SearchPrefsGenderRequest(BaseModel):
    telegram_id: int
    gender_preferences: list[GenderValue] = Field(default_factory=list)


class SearchPrefsDistanceRequest(BaseModel):
    telegram_id: int
    max_distance_km: int = Field(ge=1)


class RegistrationBioRequest(BaseModel):
    telegram_id: int
    bio: str = Field(min_length=0, max_length=4000)


class RegistrationInterestsRequest(BaseModel):
    telegram_id: int
    interest_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("interest_ids")
    @classmethod
    def _dedupe_preserve_order(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in v:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out


class RegistrationStateResponse(BaseModel):
    user_id: uuid.UUID
    telegram_id: int
    registration_step: RegistrationStep
    is_complete: bool
    photo_count: int = 0
    is_new_user: bool = False
    message: str = ""


class ReferralCodeResponse(BaseModel):
    referral_code: str = Field(min_length=1, max_length=64)
    invite_link: str | None = None
