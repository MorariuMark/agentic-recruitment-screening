"""Persist recruiter screening runs and decisions."""
from alembic import op
import sqlalchemy as sa

revision = "c93f1026"
down_revision = "86b66e600ae2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("job_description_data",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_requisitions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False))
    op.create_table("screening_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_requisitions.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_screening_runs_job_id", "screening_runs", ["job_id"])


def downgrade():
    op.drop_table("screening_runs")
    op.drop_table("job_description_data")
