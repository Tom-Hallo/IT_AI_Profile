from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "pbi002_initial_schema"
down_revision = "fe534ebbefc6"
branch_labels = None
depends_on = None


def upgrade() -> None:
# -----------------------------------------------------------------
    # users
    # -----------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
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
        sa.UniqueConstraint("email", name="uq_users_email"),
        comment="Application users",
    )
    # -----------------------------------------------------------------
    # repositories
    # -----------------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("html_url", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "private", sa.Boolean, nullable=False, server_default=sa.text("false")
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
        sa.UniqueConstraint("external_id", name="uq_repositories_external_id"),
        comment="Git repositories monitored by the platform",
    )
    # -----------------------------------------------------------------
    # assessments
    # -----------------------------------------------------------------
    op.create_table(
        "assessments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "taken_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        comment="Assessment results for a user",
    )
    op.create_index("ix_assessments_user_id", "assessments", ["user_id"])
    # -----------------------------------------------------------------
    # cvs (versioned CV data stored as JSONB)
    # -----------------------------------------------------------------
    op.create_table(
        "cvs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        comment="Versioned CV data",
    )
    op.create_index("ix_cvs_user_id", "cvs", ["user_id"])
    # -----------------------------------------------------------------
    # roadmaps (career roadmaps stored as JSONB)
    # -----------------------------------------------------------------
    op.create_table(
        "roadmaps",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("data", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        comment="Career roadmap JSON structure",
    )
    op.create_index("ix_roadmaps_user_id", "roadmaps", ["user_id"])
    # -----------------------------------------------------------------
    # many‑to‑many: users ↔ repositories (e.g. “followed” repos)
    # -----------------------------------------------------------------
    op.create_table(
        "user_repository",
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "repository_id",
            sa.BigInteger,
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        comment="Pivot table linking users and repositories",
    )
    op.create_index(
        "ix_user_repository_user_id", "user_repository", ["user_id"]
    )


def downgrade() -> None:
    # Drop in reverse order to respect FK dependencies
    op.drop_table("user_repository")
    op.drop_index("ix_roadmaps_user_id", table_name="roadmaps")
    op.drop_table("roadmaps")
    op.drop_index("ix_cvs_user_id", table_name="cvs")
    op.drop_table("cvs")
    op.drop_index("ix_assessments_user_id", table_name="assessments")
    op.drop_table("assessments")
    op.drop_table("repositories")
    op.drop_table("users")