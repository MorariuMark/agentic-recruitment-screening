"""Cache versioned screening evidence embeddings."""
from alembic import op
import sqlalchemy as sa

revision = "d4171027"
down_revision = "c93f1026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("screening_feature_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table("screening_feature_cache")
