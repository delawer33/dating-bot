import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

RegistrationStep = Literal["display_name", "birth_date", "gender", "location", "complete"]
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


class RegistrationStateResponse(BaseModel):
    user_id: uuid.UUID
    telegram_id: int
    registration_step: RegistrationStep
    is_complete: bool
    is_new_user: bool = False
    message: str = ""
