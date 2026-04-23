"""users.registration_completed — gate is_complete and discovery

Revision ID: 005
Revises: 004
Create Date: 2026-04-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "registration_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        """
        UPDATE users u
        SET registration_completed = true
        FROM user_preferences p
        WHERE p.user_id = u.id
        """
    )
    op.alter_column("users", "registration_completed", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "registration_completed")
