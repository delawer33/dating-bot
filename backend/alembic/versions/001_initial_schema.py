"""Initial schema: users, profiles, user_preferences

Revision ID: 001
Revises:
Create Date: 2026-04-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("telegram_id", sa.BigInteger, nullable=False),
        sa.Column("username", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("referral_code", sa.Text, nullable=True),
        sa.Column(
            "referred_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)

    op.create_table(
        "profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("birth_date", sa.Date, nullable=True),
        # gender values: male | female | non_binary | other
        sa.Column(
            "gender",
            sa.String(20),
            sa.CheckConstraint(
                "gender IN ('male', 'female', 'non_binary', 'other')",
                name="ck_profiles_gender",
            ),
            nullable=True,
        ),
        sa.Column("city", sa.Text, nullable=True),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("latitude", sa.Double, nullable=True),
        sa.Column("longitude", sa.Double, nullable=True),
        sa.Column("interests", postgresql.JSONB, nullable=True),
        sa.Column(
            "completeness_score",
            sa.SmallInteger,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
    )
    op.create_index("ix_profiles_city", "profiles", ["city"])
    op.create_index("ix_profiles_gender", "profiles", ["gender"])

    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("age_min", sa.SmallInteger, nullable=True),
        sa.Column("age_max", sa.SmallInteger, nullable=True),
        sa.Column("gender_preferences", postgresql.ARRAY(sa.String(20)), nullable=True),
        sa.Column("max_distance_km", sa.Integer, nullable=True),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_index("ix_profiles_gender", "profiles")
    op.drop_index("ix_profiles_city", "profiles")
    op.drop_table("profiles")
    op.drop_index("ix_users_referral_code", "users")
    op.drop_index("ix_users_telegram_id", "users")
    op.drop_table("users")
