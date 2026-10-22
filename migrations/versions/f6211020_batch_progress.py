"""Persist per-file CV parsing progress and concurrency settings."""
from alembic import op
import sqlalchemy as sa

revision = "f6211020"
down_revision = "e5211020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("batch_jobs", sa.Column("progress_json", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("batch_jobs", "progress_json")
