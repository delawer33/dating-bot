"""Stage 3: interactions, matches, behavior stats, ratings, referral events

Revision ID: 004
Revises: 003
Create Date: 2026-04-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profile_interactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('like', 'skip')",
            name="ck_profile_interactions_action",
        ),
    )
    op.create_index(
        "ix_profile_interactions_actor_created",
        "profile_interactions",
        ["actor_user_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "ix_profile_interactions_target_created",
        "profile_interactions",
        ["target_user_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "ix_profile_interactions_target_action",
        "profile_interactions",
        ["target_user_id", "action"],
    )
    op.create_unique_constraint(
        "uq_profile_interactions_actor_target",
        "profile_interactions",
        ["actor_user_id", "target_user_id"],
    )

    op.create_table(
        "matches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("user_a_id < user_b_id", name="ck_matches_user_order"),
    )
    op.create_unique_constraint(
        "uq_matches_user_pair",
        "matches",
        ["user_a_id", "user_b_id"],
    )

    op.create_table(
        "user_behavior_stats",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("likes_received", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("skips_received", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("views_implied", sa.Integer, nullable=True),
        sa.Column("matches_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("activity_histogram", postgresql.JSONB, nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "user_ratings",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("primary_score", sa.Double, nullable=False),
        sa.Column("behavioral_score", sa.Double, nullable=False),
        sa.Column("referral_bonus", sa.Double, server_default=sa.text("0"), nullable=False),
        sa.Column("combined_score", sa.Double, nullable=False),
        sa.Column("breakdown", postgresql.JSONB, nullable=True),
        sa.Column("algorithm_version", sa.Text, nullable=False),
        sa.Column(
            "computed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_ratings_combined_desc",
        "user_ratings",
        ["combined_score"],
        postgresql_ops={"combined_score": "DESC"},
    )

    op.create_table(
        "referral_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "referrer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "credited_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_referral_events_referee",
        "referral_events",
        ["referee_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_referral_events_referee", "referral_events", type_="unique")
    op.drop_table("referral_events")
    op.drop_index("ix_user_ratings_combined_desc", table_name="user_ratings")
    op.drop_table("user_ratings")
    op.drop_table("user_behavior_stats")
    op.drop_constraint("uq_matches_user_pair", "matches", type_="unique")
    op.drop_table("matches")
    op.drop_constraint("uq_profile_interactions_actor_target", "profile_interactions", type_="unique")
    op.drop_index("ix_profile_interactions_target_action", table_name="profile_interactions")
    op.drop_index("ix_profile_interactions_target_created", table_name="profile_interactions")
    op.drop_index("ix_profile_interactions_actor_created", table_name="profile_interactions")
    op.drop_table("profile_interactions")
