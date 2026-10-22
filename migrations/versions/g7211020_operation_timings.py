"""Persist workflow action timings and parent/child identifiers."""
from alembic import op
import sqlalchemy as sa

revision = "g7211020"
down_revision = "f6211020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("operation_timings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("operation", sa.String(60), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        *[sa.Column(name, sa.String(36), nullable=True) for name in ("parent_id", "batch_id", "run_id", "job_id", "candidate_id")],
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.false()))
    for field in ("operation", "status", "parent_id", "batch_id", "run_id", "job_id", "started_at"):
        op.create_index(f"ix_operation_timings_{field}", "operation_timings", [field])


def downgrade():
    op.drop_table("operation_timings")
