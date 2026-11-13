"""PBI-030 historical snapshots.

IMPORTANT: Check down_revision against the merged Alembic migration head.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "pbi030_snapshots"
down_revision = "pbi022_mentor_actions"
branch_labels = None
depends_on = None


def upgrade():
    if down_revision is None:
        raise RuntimeError(
            "Set down_revision to actual merged head before running migration"
        )
    op.create_table(
        "historical_reanalysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id", sa.BigInteger(), sa.ForeignKey("ita.users.id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True)),
        sa.Column("error_code", sa.String(48)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "owner_id", "idempotency_key", name="uq_reanalysis_owner_key"
        ),
        schema="ita",
    )
    op.create_table(
        "historical_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id", sa.BigInteger(), sa.ForeignKey("ita.users.id"), nullable=False
        ),
        sa.Column(
            "source_job_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True
        ),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("rubric_version", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("skills", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_summary", postgresql.JSONB(), nullable=False),
        sa.Column("source_fingerprint", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_snapshot_score"),
        schema="ita",
    )
    op.create_index(
        "ix_snapshot_owner_created",
        "historical_snapshots",
        ["owner_id", "created_at"],
        schema="ita",
    )
    # DB-level immutability (blocks UPDATE/DELETE, including accidental ORM writes).
    op.execute(
        """
        CREATE FUNCTION ita.pbi030_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'historical snapshots are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER pbi030_no_mutation
        BEFORE UPDATE OR DELETE ON ita.historical_snapshots
        FOR EACH ROW EXECUTE FUNCTION ita.pbi030_immutable()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS pbi030_no_mutation ON ita.historical_snapshots")
    op.execute("DROP FUNCTION IF EXISTS ita.pbi030_immutable()")
    op.drop_index(
        "ix_snapshot_owner_created", table_name="historical_snapshots", schema="ita"
    )
    op.drop_table("historical_snapshots", schema="ita")
    op.drop_table("historical_reanalysis_jobs", schema="ita")
