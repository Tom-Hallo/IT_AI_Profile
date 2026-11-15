"""pbi033_self_reported_skills

Revision ID: 560ffcca5e7c
Revises: scoring_rubric_v21
Create Date: 2026-11-15 09:11:11.287370
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "560ffcca5e7c"
down_revision: str | Sequence[str] | None = "scoring_rubric_v21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "self_reported_skills",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=30),
            server_default="self-reported",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="self-reported",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status = 'self-reported'",
            name=op.f("ck_self_reported_skills_self_reported_skill_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["ita.users.id"],
            name=op.f("fk_self_reported_skills_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_self_reported_skills")),
        schema="ita",
    )

    op.create_index(
        op.f("ix_self_reported_skills_user_id"),
        "self_reported_skills",
        ["user_id"],
        unique=False,
        schema="ita",
    )

    op.create_table(
        "self_reported_skill_evidence",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column(
            "source",
            sa.String(length=30),
            server_default="self-reported",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="self-reported",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source = 'self-reported'",
            name=op.f("ck_self_reported_skill_evidence_self_reported_evidence_source"),
        ),
        sa.CheckConstraint(
            "status = 'self-reported'",
            name=op.f("ck_self_reported_skill_evidence_self_reported_evidence_status"),
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["ita.self_reported_skills.id"],
            name=op.f("fk_self_reported_skill_evidence_skill_id_self_reported_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["ita.users.id"],
            name=op.f("fk_self_reported_skill_evidence_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_self_reported_skill_evidence"),
        ),
        schema="ita",
    )

    op.create_index(
        op.f("ix_self_reported_skill_evidence_skill_id"),
        "self_reported_skill_evidence",
        ["skill_id"],
        unique=False,
        schema="ita",
    )

    op.create_index(
        op.f("ix_self_reported_skill_evidence_user_id"),
        "self_reported_skill_evidence",
        ["user_id"],
        unique=False,
        schema="ita",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_self_reported_skill_evidence_user_id"),
        table_name="self_reported_skill_evidence",
        schema="ita",
    )
    op.drop_index(
        op.f("ix_self_reported_skill_evidence_skill_id"),
        table_name="self_reported_skill_evidence",
        schema="ita",
    )
    op.drop_table("self_reported_skill_evidence", schema="ita")

    op.drop_index(
        op.f("ix_self_reported_skills_user_id"),
        table_name="self_reported_skills",
        schema="ita",
    )
    op.drop_table("self_reported_skills", schema="ita")
