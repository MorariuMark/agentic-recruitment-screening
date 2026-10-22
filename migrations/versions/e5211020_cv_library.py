"""Original CV library with exact content identity and 30-day trash."""
from alembic import op
import sqlalchemy as sa

revision = "e5211020"
down_revision = "d4171027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("cv_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), unique=True, nullable=True),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("candidate_id", sa.String(36), unique=True, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table("cv_documents")
