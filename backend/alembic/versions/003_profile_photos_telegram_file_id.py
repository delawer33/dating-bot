"""Deduplicate registration photos by Telegram file_id (unique per profile)

Revision ID: 003
Revises: 002
Create Date: 2026-04-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profile_photos",
        sa.Column("telegram_file_id", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_profile_photos_profile_telegram_file",
        "profile_photos",
        ["profile_id", "telegram_file_id"],
        unique=True,
        postgresql_where=sa.text("telegram_file_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_profile_photos_profile_telegram_file", table_name="profile_photos")
    op.drop_column("profile_photos", "telegram_file_id")
