"""PBI-002: Initial business schema (users, repositories, assessments, cvs, roadmaps).

Revision chain: fe534ebbefc6 (baseline PBI-001) -> pbi002_initial_schema (this)

All tables are created in the ``ita`` PostgreSQL schema, which is the schema
configured in env.py via ``version_table_schema``.

Naming convention follows app.db.base.NAMING_CONVENTION:
  pk_<table>, uq_<table>_<col>, fk_<table>_<col>_<ref_table>, ix_<col_label>,
  ck_<table>_<constraint_name>
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------
revision = "pbi002_initial_schema"
down_revision = "fe534ebbefc6"
branch_labels = None
depends_on = None

SCHEMA = "ita"


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------
def upgrade() -> None:
    # Ensure the schema exists (idempotent)
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        schema=SCHEMA,
        comment="Application users",
    )

    # ------------------------------------------------------------------
    # repositories
    # ------------------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("html_url", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "private",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_repositories"),
        sa.UniqueConstraint("external_id", name="uq_repositories_external_id"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_repositories_owner_id_users",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
        comment="GitHub repositories linked to a user",
    )
    op.create_index(
        "ix_repositories_owner_id",
        "repositories",
        ["owner_id"],
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # assessments
    # ------------------------------------------------------------------
    op.create_table(
        "assessments",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "taken_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assessments"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_assessments_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_assessments_score_range",
        ),
        schema=SCHEMA,
        comment="Skill assessment results for a user",
    )
    op.create_index(
        "ix_assessments_user_id",
        "assessments",
        ["user_id"],
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # cvs
    # ------------------------------------------------------------------
    op.create_table(
        "cvs",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cvs"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_cvs_user_id_users",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
        comment="Versioned CV data stored as JSONB",
    )
    op.create_index("ix_cvs_user_id", "cvs", ["user_id"], schema=SCHEMA)

    # ------------------------------------------------------------------
    # roadmaps
    # ------------------------------------------------------------------
    op.create_table(
        "roadmaps",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roadmaps"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_roadmaps_user_id_users",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
        comment="Career roadmap stored as JSONB",
    )
    op.create_index(
        "ix_roadmaps_user_id",
        "roadmaps",
        ["user_id"],
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # user_repository  (many-to-many pivot)
    # ------------------------------------------------------------------
    op.create_table(
        "user_repository",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "repository_id", name="pk_user_repository"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_user_repository_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            [f"{SCHEMA}.repositories.id"],
            name="fk_user_repository_repository_id_repositories",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
        comment="Pivot table: users <-> repositories (many-to-many)",
    )
    op.create_index(
        "ix_user_repository_user_id",
        "user_repository",
        ["user_id"],
        schema=SCHEMA,
    )


# ---------------------------------------------------------------------------
# Downgrade - drops in reverse dependency order
# ---------------------------------------------------------------------------
def downgrade() -> None:
    op.drop_index(
        "ix_user_repository_user_id", table_name="user_repository", schema=SCHEMA
    )
    op.drop_table("user_repository", schema=SCHEMA)

    op.drop_index("ix_roadmaps_user_id", table_name="roadmaps", schema=SCHEMA)
    op.drop_table("roadmaps", schema=SCHEMA)

    op.drop_index("ix_cvs_user_id", table_name="cvs", schema=SCHEMA)
    op.drop_table("cvs", schema=SCHEMA)

    op.drop_index("ix_assessments_user_id", table_name="assessments", schema=SCHEMA)
    op.drop_table("assessments", schema=SCHEMA)

    op.drop_index("ix_repositories_owner_id", table_name="repositories", schema=SCHEMA)
    op.drop_table("repositories", schema=SCHEMA)

    op.drop_table("users", schema=SCHEMA)
