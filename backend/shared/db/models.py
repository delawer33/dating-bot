import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Double,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP as PGTIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        PGTIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    registration_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    referral_code: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    referred_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    profile: Mapped["Profile | None"] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    preferences: Mapped["UserPreferences | None"] = relationship(
        "UserPreferences",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    behavior_stats: Mapped["UserBehaviorStats | None"] = relationship(
        "UserBehaviorStats",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ratings: Mapped["UserRating | None"] = relationship(
        "UserRating",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Profile(Base):
    __tablename__ = "profiles"

    # PK is also FK — enforces the 1:1 with users
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Double, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Double, nullable=True)
    interests: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    completeness_score: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(PGTIMESTAMP(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="profile")
    photos: Mapped[list["ProfilePhoto"]] = relationship(
        "ProfilePhoto",
        back_populates="profile",
        order_by="ProfilePhoto.sort_order",
        cascade="all, delete-orphan",
    )


class ProfilePhoto(Base):
    __tablename__ = "profile_photos"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("profiles.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Telegram `file_id` for the chosen size; used to dedupe duplicate deliveries (retries, etc.)
    telegram_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        PGTIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    profile: Mapped["Profile"] = relationship("Profile", back_populates="photos")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    age_min: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    age_max: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    gender_preferences: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(20)), nullable=True
    )
    max_distance_km: Mapped[int | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(PGTIMESTAMP(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="preferences")


class ProfileInteraction(Base):
    __tablename__ = "profile_interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        PGTIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_a_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_b_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        PGTIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class UserBehaviorStats(Base):
    __tablename__ = "user_behavior_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    likes_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skips_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    views_implied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matches_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activity_histogram: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        PGTIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="behavior_stats")


class UserRating(Base):
    __tablename__ = "user_ratings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    primary_score: Mapped[float] = mapped_column(Double, nullable=False)
    behavioral_score: Mapped[float] = mapped_column(Double, nullable=False)
    referral_bonus: Mapped[float] = mapped_column(Double, default=0.0, nullable=False)
    combined_score: Mapped[float] = mapped_column(Double, nullable=False)
    breakdown: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        PGTIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="ratings")


class ReferralEvent(Base):
    __tablename__ = "referral_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referrer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    credited_at: Mapped[datetime] = mapped_column(
        PGTIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
