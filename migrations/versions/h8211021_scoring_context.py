"""Preserve evaluation criteria and strictness for human score corrections."""
from alembic import op
import sqlalchemy as sa

revision = "h8211021"
down_revision = "g7211020"
branch_labels = None
depends_on = None


def upgrade():
    # Local startup may already have reconciled this nullable column.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("match_evaluations")}
    if "scoring_context_json" not in columns:
        op.add_column("match_evaluations", sa.Column("scoring_context_json", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("match_evaluations", "scoring_context_json")
